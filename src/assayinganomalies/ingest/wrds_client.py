"""
Thin wrapper around the WRDS Python client.

Credential resolution is deliberately headless-friendly: a batch node with no
desktop secret service and no TTY must still be able to connect. The password
is looked for in this order

    1. environment variables (``WRDS_PASSWORD``, else ``PGPASSWORD``)
    2. ``~/.pgpass`` (or ``PGPASSFILE``; ``%APPDATA%\\postgresql\\pgpass.conf`` on
       Windows), the standard libpq password file
    3. ``keyring`` (desktop secret service)
    4. an interactive prompt, only when prompting is safe

The username comes from the config, else ``WRDS_USERNAME``, else the first
WRDS line in the password file, so a saved password file makes a run
prompt-free.

Any failure in the keyring step (package missing, no backend, locked keyring)
logs at DEBUG and falls through instead of raising: a headless Linux node has
no keyring backend, so that failure is the normal case there.

A build logs in once. :meth:`WRDSClient.open_session` opens one connection,
without the ``wrds`` library's own fallback prompts, and every
:meth:`WRDSClient.connect` borrows it, so WRDS asks for one Duo approval per
run rather than one per download.
"""

from __future__ import annotations

from contextlib import contextmanager, redirect_stdout, suppress
from dataclasses import dataclass, field
import getpass
import io
import logging
import os
from pathlib import Path
import sys
from typing import Any, Iterator

try:  # pragma: no cover - optional dependency
    import wrds
except ImportError:  # pragma: no cover
    wrds = None  # type: ignore

logger = logging.getLogger(__name__)

# WRDS PostgreSQL endpoint; used to match ~/.pgpass lines.
WRDS_HOST = "wrds-pgdata.wharton.upenn.edu"
WRDS_PORT = "9737"
WRDS_DBNAME = "wrds"


def _import_keyring():
    """
    Return the ``keyring`` module, or None if it cannot be used here.

    Importing keyring can fail outright (not installed) or succeed but blow up
    later when no backend exists. Both are survivable on a headless node, so we
    log and return None rather than propagate.
    """
    try:
        import keyring

        return keyring
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("keyring unavailable (%s); skipping keyring credential lookup", exc)
        return None


def _pgpass_path() -> Path:
    """
    Location of the libpq password file.

    ``PGPASSFILE`` wins; else ``%APPDATA%\\postgresql\\pgpass.conf`` on Windows
    (where libpq and ``wrds.Connection.create_pgpass_file`` put it) and
    ``~/.pgpass`` elsewhere.
    """
    env = os.getenv("PGPASSFILE")
    if env:
        return Path(env)
    appdata = os.getenv("APPDATA")
    if sys.platform == "win32" and appdata:
        return Path(appdata) / "postgresql" / "pgpass.conf"
    return Path.home() / ".pgpass"


def pgpass_save_path() -> Path:
    """Where ``wrds.Connection.create_pgpass_file`` writes (it ignores PGPASSFILE)."""
    appdata = os.getenv("APPDATA")
    if sys.platform == "win32" and appdata:
        return Path(appdata) / "postgresql" / "pgpass.conf"
    return Path(os.getenv("HOME") or Path.home()) / ".pgpass"


def _unescape_pgpass_field(field: str) -> str:
    r"""libpq escapes ``:`` and ``\`` inside .pgpass fields with a backslash."""
    out: list[str] = []
    esc = False
    for ch in field:
        if esc:
            out.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        else:
            out.append(ch)
    return "".join(out)


def _split_pgpass_line(line: str) -> list[str]:
    """Split a .pgpass line on unescaped colons, then unescape each field."""
    fields: list[str] = []
    cur: list[str] = []
    esc = False
    for ch in line:
        if esc:
            cur.append("\\")
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if esc:  # trailing lone backslash
        cur.append("\\")
    fields.append("".join(cur))
    return [_unescape_pgpass_field(f) for f in fields]


def _wrds_pgpass_lines() -> Iterator[list[str]]:
    """
    The ``host:port:database:user:password`` lines of the password file that
    can apply to WRDS, in file order (``*`` matches anything).
    """
    path = _pgpass_path()
    try:
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:  # pragma: no cover - permission edge case
        logger.warning("could not read %s (%s); skipping .pgpass lookup", path, exc)
        return

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = _split_pgpass_line(line)
        if len(parts) != 5:
            continue
        host, port, dbname, user, pw = parts
        if host not in ("*", WRDS_HOST):
            continue
        if port not in ("*", WRDS_PORT):
            continue
        if dbname not in ("*", WRDS_DBNAME):
            continue
        yield parts


def _password_from_pgpass(username: str | None) -> str | None:
    """
    Look up the WRDS password in ~/.pgpass.

    The first matching line wins, as in libpq.
    """
    for _host, _port, _dbname, user, pw in _wrds_pgpass_lines():
        if username is not None and user not in ("*", username):
            continue
        if pw:
            return pw
    return None


def _username_from_pgpass() -> str | None:
    """The user of the first WRDS line in ~/.pgpass that names one."""
    for _host, _port, _dbname, user, pw in _wrds_pgpass_lines():
        if user and user != "*" and pw:
            return user
    return None


def _password_from_keyring(username: str | None) -> str | None:
    """Look up the WRDS password in the desktop keyring; never raises."""
    if not username:
        return None
    keyring = _import_keyring()
    if keyring is None:
        return None
    try:
        return keyring.get_password("wrds", username)
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("keyring lookup failed (%s); falling through", exc)
        return None


@dataclass
class WRDSClient:
    username: str | None = None
    # Where the password came from: "env", ".pgpass", "keyring" or "prompt";
    # None until resolved. Never the password itself.
    credential_source: str | None = field(default=None, init=False)
    _prompted_password: str | None = field(default=None, init=False, repr=False)
    _conn: Any = field(default=None, init=False, repr=False)

    def _get_username(self) -> str | None:
        return self.username or os.getenv("WRDS_USERNAME") or _username_from_pgpass()

    def _resolve_password(self) -> tuple[str | None, str | None]:
        """``(password, source)``: env -> ~/.pgpass -> keyring; ``(None, None)``."""
        uname = self._get_username()

        env_pw = os.getenv("WRDS_PASSWORD")
        if env_pw:
            if self._prompted_password is not None and env_pw == self._prompted_password:
                return env_pw, "prompt"
            return env_pw, "env"
        # PGPASSWORD is the libpq convention; honor it, but only alongside a
        # username, so we never hand wrds a password with no account.
        pg_pw = os.getenv("PGPASSWORD")
        if pg_pw and uname:
            return pg_pw, "env"

        file_pw = _password_from_pgpass(uname)
        if file_pw:
            return file_pw, ".pgpass"

        key_pw = _password_from_keyring(uname)
        if key_pw:
            return key_pw, "keyring"
        return None, None

    def _get_password(self) -> str | None:
        """Resolve the password: env -> ~/.pgpass -> keyring; None if unfound."""
        pw, source = self._resolve_password()
        if pw:
            self.credential_source = source
        return pw

    def _can_prompt(self) -> bool:
        """
        Return True if it's safe/appropriate to prompt the user for credentials.

        We avoid prompting in non-interactive contexts (e.g., pytest/CI), because
        it would hang the process.
        """
        if os.getenv("ASSAYINGANOMALIES_NO_PROMPT") == "1" or os.getenv("AA_NO_PROMPT") == "1":
            return False
        # Pytest sets this env var for each test; avoid blocking prompts.
        if os.getenv("PYTEST_CURRENT_TEST"):
            return False
        # Common CI env var convention.
        if os.getenv("CI") == "true" or os.getenv("CI") == "1" or os.getenv("GITHUB_ACTIONS") == "true":
            return False
        try:
            # Don't require a TTY: many IDE/Jupyter environments can still accept input().
            return sys.stdin is not None and sys.stdout is not None
        except Exception:
            return False

    def ensure_credentials(self, *, prompt: bool = True) -> bool:
        """
        Ensure credentials are available, optionally prompting the user.

        Priority:
        1) Explicit username passed to WRDSClient (else WRDS_USERNAME, else
           the first WRDS line of ~/.pgpass).
        2) Password from WRDS_PASSWORD / PGPASSWORD, then ~/.pgpass, then keyring.
        3) Interactive prompt (if enabled).

        Returns True if credentials are available after this call, else False.
        """
        uname = self._get_username()
        pwd = self._get_password()
        if uname and pwd:
            return True

        if prompt and self._can_prompt():
            print(
                "WRDS_USERNAME / WRDS_PASSWORD are not set in this shell, and no "
                f"{_pgpass_path()} entry was found.",
                flush=True,
            )
            # Username: allow empty input to keep existing (env/config) if present.
            default = uname or ""
            prompt_txt = f"WRDS username [{default}]: " if default else "WRDS username: "
            try:
                entered = input(prompt_txt).strip()
            except EOFError:
                return False
            if entered:
                self.username = entered
            elif default:
                self.username = default
            uname = self._get_username()

            # Password: always prompt hidden if still missing.
            pwd = self._get_password()
            if uname and not pwd:
                try:
                    pw = getpass.getpass("WRDS password: ")
                except EOFError:
                    return False
                if pw:
                    # Do NOT persist password; keep in-process only by stashing into env for this run.
                    os.environ["WRDS_PASSWORD"] = pw
                    self._prompted_password = pw
            uname = self._get_username()
            pwd = self._get_password()
            if uname and pwd:
                return True

        return False

    def open_session(self) -> Any:
        """
        Log in to WRDS once and keep the connection for this client.

        This is the step that triggers the Duo push. The ``wrds`` library's
        own ``Connection.connect`` falls back to ``input``/``getpass`` prompts
        and an interactive "Create .pgpass file now [y/n]?" when a login
        fails, and prints the library list; neither belongs in a build. So
        the engine is made directly with ``raise_err=True`` (the library's
        private ``_Connection__make_sa_engine_conn``, pinned by a test against
        the installed ``wrds``) and a failure raises. ``load_library_list`` is
        skipped: ingest only ever calls ``raw_sql``.
        """
        if self._conn is not None:
            return self._conn
        if wrds is None:
            raise RuntimeError("wrds package not installed.")
        if not self.ensure_credentials(prompt=True):
            raise RuntimeError(
                "WRDS credentials not found. Set WRDS_USERNAME and WRDS_PASSWORD "
                "(or PGPASSWORD) env vars, add a wrds-pgdata line to ~/.pgpass, "
                "store the password via keyring, or run interactively to be prompted."
            )
        conn = wrds.Connection(
            autoconnect=False,
            wrds_username=self._get_username(),
            wrds_password=self._get_password(),
        )
        conn._Connection__make_sa_engine_conn(raise_err=True)
        self._conn = conn
        return conn

    @contextmanager
    def connect(self) -> Iterator[Any]:
        """
        Borrow the shared connection; leaving the block does not close it.

        The connection is checked with ``SELECT 1`` first and reopened once if
        that fails (WRDS drops idle connections). With no session open yet
        (a one-off client, not the pipeline's), the connection is opened for
        this block and closed when it ends.
        """
        borrowed = self._conn is not None
        if borrowed:
            try:
                self._conn.raw_sql("SELECT 1")
            except Exception as exc:  # noqa: BLE001 - any driver error means a dead handle
                logger.info("WRDS connection is gone (%s); reconnecting", exc)
                self.close()
        try:
            yield self.open_session()
        finally:
            if not borrowed:
                self.close()

    def reconnect(self) -> Any:
        """Drop the shared connection and log in again."""
        self.close()
        return self.open_session()

    def close(self) -> None:
        """Close the shared connection, if open; never raises."""
        conn, self._conn = self._conn, None
        if conn is not None:
            with suppress(Exception):
                conn.close()

    def save_pgpass(self) -> Path:
        """
        Write the current credentials to the libpq password file.

        Reuses ``wrds.Connection.create_pgpass_file``, which keeps other
        entries, escapes colons, uses ``%APPDATA%\\postgresql\\pgpass.conf`` on
        Windows and restricts the file's permissions elsewhere. Its prints are
        swallowed. Returns the file written.
        """
        conn = self.open_session()
        with redirect_stdout(io.StringIO()):
            conn.create_pgpass_file()
        return pgpass_save_path()

    def run_query(self, sql: str, **kwargs: Any):  # pragma: no cover
        with self.connect() as conn:
            return conn.raw_sql(sql, **kwargs)
