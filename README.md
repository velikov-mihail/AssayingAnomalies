# Assaying Anomalies

`assayinganomalies` is a Python package for testing whether a new cross-sectional
return predictor is really new. It implements the anomaly-testing protocol of
Novy-Marx and Velikov,
["Assaying Anomalies"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4338007)
(2026): give it a signal (a stock-month panel), and it runs the paper's battery of
portfolio sorts, factor-model alphas, trading-cost-adjusted performance, Fama–MacBeth
regressions and comparisons against a zoo of about 160 published anomalies, and writes
the results up as a LaTeX/PDF report.

To get there it builds a local research database from CRSP and Compustat (a DuckDB file,
one per project directory). The building blocks are public functions you can use on their
own: univariate and bivariate portfolio sorts, factor regressions, Fama–MacBeth, trading
costs, generalized alphas.

> **You need a WRDS subscription.** The database is built from your own WRDS account:
> CRSP monthly and daily stock files (CIZ, Flat File Format 2.0), the CRSP/Compustat
> merged link table, Compustat annual and quarterly fundamentals, and the Fama–French
> factors on WRDS. The anomaly zoo is downloaded from the public
> [Chen–Zimmerman Open Source Asset Pricing](https://www.openassetpricing.com/) release
> and needs no subscription. Without WRDS you can only build a
> [synthetic demo database](#trying-it-without-wrds).

The Chen–Zimmerman files are downloaded from Hugging Face, which needs both
`huggingface.co` and its download CDN `*.hf.co` to be reachable; some networks and
firewalls block one of them. The C-Z stage (23 of 24) runs near the end of the build, so
**we recommend downloading the two C-Z files yourself before you start** (see
[step 2 of the Quickstart](#2-download-the-chen-zimmerman-files-recommended)).
If you don't and the download fails, the rest of the database is still built, the run ends
with a summary of what did not complete, and
`aa setup-database --start-from fetch-cz-anomalies` fetches only the C-Z zoo later instead of
repeating the WRDS stages.

## Install

Python 3.11 or 3.12, in a fresh environment. Any environment manager works; the three
recipes below are equivalent, so pick the one you already use.

Each recipe creates an environment, activates it and installs the package from
[PyPI](https://pypi.org/project/assayinganomalies/) with its `analytics` extra.

**conda**

```bash
conda create -n assaying-anomalies python=3.11
conda activate assaying-anomalies
pip install "assayinganomalies[analytics]"
```

**`python -m venv`** (the standard library; no extra tools)

```bash
python3 -m venv .venv                 # Windows: py -3.11 -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install "assayinganomalies[analytics]"
```

`python3` must be 3.11 or newer; check with `python3 --version`. On macOS it is usually
Apple's Python 3.9, and the install then fails with `requires a different Python: 3.9.6
not in '>=3.11'`. Install a newer one (`brew install python@3.11`, or the installer from
python.org) and create the environment with `python3.11 -m venv .venv`, or use uv below,
which downloads the Python it needs.

**uv**

```bash
uv venv --python 3.11 .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
uv pip install "assayinganomalies[analytics]"
```

A uv environment has no `pip` of its own: use `uv pip install`, not a bare `pip install`,
which would run some other environment's `pip` and install the package there.

**Versions.** This package's releases start at 0.9.0, the version the paper's revision
was run on; fixes are 0.9.x. To reproduce a result, pin the version you used
(`pip install "assayinganomalies[analytics]==0.9.0"`); `assayinganomalies.__version__`
and `aa --version` print the installed one, and every database build, protocol run and
report records it. The releases numbered 0.1 to 2.0.6 that PyPI lists under this name
(2024) are an earlier, unrelated implementation; they are withdrawn and `pip` does not
install them.

### Install from the source tree

To install a development state instead of a release, install from the repository, with
any of the three environments active (`uv pip install` for uv):

```bash
pip install "assayinganomalies[analytics] @ git+https://github.com/velikov-mihail/AssayingAnomalies"
```

or from a clone, which also gives you the files under `inputs/`:

```bash
git clone https://github.com/velikov-mihail/AssayingAnomalies
pip install "./AssayingAnomalies[analytics]"
```

The `analytics` extra brings in scipy, scikit-learn, matplotlib, seaborn and jinja2, which
the protocol and its report need. Without it you can build the database and load data, but
not run the protocol. Turning the report into a PDF also needs a LaTeX installation with
`latexmk`; without one you still get the `.tex` file and figures.

To confirm the install, run `aa --help`; it lists the commands used in the Quickstart below.

### Check which `aa` you are running

The package installs a command-line tool, `aa`. If another Python environment on your
machine (often base Anaconda) also has the package installed, a bare `aa` can resolve to
*that* environment's copy, with different numpy, scipy and scikit-learn versions, and your
results will quietly differ. Before a long run, check where `aa` comes from:

```bash
which aa              # macOS / Linux (zsh, bash)
where aa              # Windows, Command Prompt
Get-Command aa        # Windows, PowerShell
python -c "import assayinganomalies, sys; print(sys.executable, assayinganomalies.__file__)"
```

`where` lists every `aa` on your `PATH`; the first one is the one that runs. Both paths should
point inside the environment you just created. If they do not, activate
the environment again, or put its `bin/` (Windows: `Scripts\`) directory first on your
`PATH`.

**macOS and Linux shells cache command locations.** zsh (the macOS default) and bash
remember where they last found a command. If you ran `aa` (or tried to) before installing
into an environment that was already active, the shell can keep running the old copy, or
keep saying "command not found", even though the new `aa` is installed. Clear the cache and
check again:

```bash
rehash                # zsh
hash -r               # bash
```

Activating an environment clears the cache, so this only bites when you install into an
environment that was already active. In bash, `which` searches `PATH` afresh and can
disagree with what the shell will actually run; `type aa` shows the cached path
("aa is hashed (...)").

## Quickstart

### 1. Choose a project folder and set parameters

First tell the toolkit where your project lives. The project folder holds the database
(`Data/aa.duckdb`, with your settings stored inside it) and the outputs (`Scratch/Assay/`).
You set it once; every later command, notebook or IDE session finds it from any folder.

```bash
aa set-params --project-dir ~/research/my-project     # Windows: aa set-params --project-dir "D:\research\my-project"
aa set-params --sample-start 1963          # sample_end defaults to 'latest'
aa show-config
```

`sample_end` defaults to `latest`: the last complete calendar year on the WRDS tapes when
`aa setup-database` runs (see [Which CRSP tape?](#which-crsp-tape)). For a paper, pin a year
(`aa set-params --sample-end 2025`) so a later rebuild covers the same window.

Every `aa` command first prints `Using database: ...`, so you can see which project it is
working on. `aa show-config` lists the project folder and every setting with its value and
the `aa set-params` flag that changes it; flags take either spelling (`--sample-start` or
`--sample_start`). To work on another project for one terminal session, set
`AA_PROJECT_DIR` to its folder.

### 2. Download the Chen-Zimmerman files (recommended)

Each Chen–Zimmerman release is a branch of the Hugging Face dataset
[OpenSourceAP/CrossSection](https://huggingface.co/datasets/OpenSourceAP/CrossSection):
2026.10 is
[`Data-Release-2026.10`](https://huggingface.co/datasets/OpenSourceAP/CrossSection/tree/Data-Release-2026.10),
earlier ones are named after the release (`2025.10`, `2024.10`, ...). From the release's
branch (the newest, unless you set `aa set-params --cz-release-version`), download

- `signed_predictors_dl_wide.parquet` (about 1.9 GB, under *Firm Level Characteristics*), and
- `SignalDoc.csv` from the same branch.

Keep the names they download with. Either save both in the `Data/` folder of your project
folder (the build looks for them under `Data/staging/`, `Data/`, then anywhere under the
folder you run `aa` from), or keep them anywhere and pin them in the config:

```bash
aa set-params --cz-signals-path /path/to/signed_predictors_dl_wide.parquet \
              --cz-signal-doc-path /path/to/SignalDoc.csv
```

Use absolute paths for pins: a relative one is read from wherever you run `aa`. With a
JSON config file (`AA_CONFIG_PATH`), set `cz_signals_path` and `cz_signal_doc_path` there
instead. A `signed_predictors_dl_wide.zip` or `.csv` from an older release, downloaded
from Google Drive before the move to Hugging Face, still works.
The first lines of the `aa setup-database` log say which C-Z files it found, or that it will
download them:

```text
Found CZ signals file: /home/you/research/my-project/Data/signed_predictors_dl_wide.parquet (release unknown, manual file (database dir))
Found CZ SignalDoc file: /home/you/research/my-project/Data/SignalDoc.csv (release unknown, manual file (database dir))
```

A file you supply does not say which release it is from, so the run manifest records it as
a manual file. Take both files from the same release.

### 3. Build the database

```bash
export WRDS_USERNAME=your_username   # Windows PowerShell: $env:WRDS_USERNAME = "your_username"
export WRDS_PASSWORD=your_password   # Windows PowerShell: $env:WRDS_PASSWORD = "your_password"
aa setup-database
```

`export` (bash) and `$env:` (PowerShell) last only for the terminal you type them in: run
`aa setup-database` in that same terminal, and set them again in a new one. With none set,
an interactive run asks for your username and password once, and after a successful login
offers to save them to `~/.pgpass` so later runs don't ask.

To set credentials once for good, either

- save them in the PostgreSQL password file, one line, readable only by you:

  ```bash
  echo 'wrds-pgdata.wharton.upenn.edu:9737:wrds:your_username:your_password' >> ~/.pgpass
  chmod 600 ~/.pgpass
  ```

  On Windows the file is `%APPDATA%\postgresql\pgpass.conf` (same line format). The
  username is read from this file too, so nothing else needs setting; or
- add the two `export` lines to `~/.bashrc` (or `~/.zshrc`).

The system keyring (service `wrds`) also works. The build logs in to WRDS once, before its
first stage, so approve the Duo push on your phone when `Connecting to WRDS. Approve the Duo
push on your phone now...` appears; a wrong password or an unapproved push stops the run
there. All WRDS downloads run first, so a later `--start-from` at a load or transform stage
needs no credentials. The build writes `Data/aa.duckdb` in the project folder and a run
manifest beside it
(`aa.manifest.json`) recording the code version, sample, input hashes and WRDS pull dates.
Expect a few hours (see [Timings](#timings)).

### 4. Run a portfolio sort

```python
import assayinganomalies as aa

panel = aa.load({"ret", "me", "nyse_flag"}, panel=True).sort_index()  # (date, permno) panel

# Size quintiles: NYSE breakpoints, value-weighted
res = aa.run_univariate_sort(
    returns=panel["ret"],
    signal=panel["me"],
    mcap=panel["me"],
    n_bins=5,
    breaks="NYSE",
    nyse_flag=panel["nyse_flag"],
    weighting="v",
)

ff = aa.load({"mktrf", "smb", "hml", "rf", "umd"}, panel=False)  # monthly factors
```

A sort buys each portfolio in a month in which the signal has values and holds it, without
rebalancing, until the next such month. **The data decide when it trades.** Size has a value
every month, so the sort above trades every month. Annual Compustat columns (`at`, `be`,
`gp`, …) are stored in the June they become available only, so a signal built from them
trades each June and is held for the year; `aa.fill_months(signal)` or
`aa.load(..., fill_annual=True)` carries the June value through the following May, and the
sort then trades every month. With `tcosts=` (per-stock half-spreads, the `tcost` column)
the result also has the cost of those trades and net returns; `convention="dollar"` (the
default) or `"capital"` sets the size of the two legs after a trade. The first purchase is
not charged; its cost is `res.entry_cost`.

Returns are decimals and dates are month-ends. A Fama–MacBeth regression of returns (in
percent) on log size and momentum:

```python
from assayinganomalies.analytics.regressions import run_fama_macbeth

df = aa.load({"ret", "me", "R12_2"}, panel=True).sort_index()
fm = run_fama_macbeth(100 * df["ret"], [aa.log(df["me"]), df["R12_2"]], time_period=196307)
fm.print_results()
```

Data of your own keyed by Compustat `gvkey` joins the panel through the build's cleaned
CRSP-Compustat link, the `ccm_link` table: `aa.merge_on_link(my_frame, link, date_col=...)`
adds a `permno` wherever the date falls inside a link window.
A Compustat variable the build does not carry is added to the panel without a rebuild:
`aa add-compustat-vars --annual xrd` (one Duo push, a few minutes) downloads only that
column, aligns it like the panel's own (annual like `at`, on the June row only; `--quarterly`
like `ibq`, filled month by month) and keeps its name, so `aa.load({"xrd"})` reads it; later
builds re-apply it.

### 5. Run the protocol on your signal

Save your signal as a long CSV with columns `permno`, `dates` (YYYYMM) and one column
named after the signal's acronym:

```text
permno,dates,MYSIG
10006,197501,-2.18
10006,197502,-2.76
```

Then:

```python
import assayinganomalies as aa

info = {
    "authors": "Your Name",
    "paper_title": "Your Paper",
    "signal_name": "My Signal",
    "acronym": "MYSIG",
}
result = aa.test_signal("mysig.csv", info, out_dir="Assay")
print(result.tex_path)   # Assay/tex/MYSIG.tex, plus the eight figure PDFs
```

The run writes `Assay/MYSIG_Results.pkl`, the LaTeX report and its figures, and
`Assay/MYSIG_manifest.json`, which records everything that determines the numbers,
including the seeds. Compile the report with `latexmk -pdf MYSIG.tex` in `Assay/tex/`. The evaluation window is inferred from the signal; pass
`time_period=(197501, 202112)` to fix it.

#### From the command line

`aa run-protocol` runs the same protocol on the project folder's database (`Data/aa.duckdb`),
from any folder, and writes its outputs under the project folder's `Scratch/Assay/` (or
`--out-dir`):

```bash
aa run-protocol --signal mysig.csv \
    --acronym MYSIG --signal-name "My Signal" \
    --authors "Your Name and Coauthor Name" --paper-title "Your Paper"
```

It writes the same files as the Python call and then compiles the PDF itself with
`latexmk` (a missing LaTeX installation only logs a warning and leaves the `.tex`). Useful
options:

| Option | What it does |
|---|---|
| `--acronym MYSIG` | Names the output files (`MYSIG_Results.pkl`, `tex/MYSIG.tex`) and labels the report. Default: the CSV's signal column |
| `--signal-name "My Signal"` | The signal's name in the report title and abstract. Default: the acronym |
| `--authors "A and B"` | The report's authors; separate several with ` and `. Default: blank |
| `--paper-title "Your Paper"` | Title of the paper that introduces the signal, stored with the signal's metadata (not printed: the report is titled "Assaying Anomalies Performance Report for Cross-Sectional Return Predictor *Signal Name*"). Default: blank |
| `--email` | Contact email stored with the signal's metadata (not printed in the report) |
| `--time-period 197501 202112` | Fix the evaluation window (default: inferred from the signal) |
| `--convention dollar` | Size of the two legs of every long/short strategy after a trade: `dollar` (default; $1 each) or `capital` (both legs at the strategy's capital). Gross returns are the same; trading costs differ. The factor costs of the same convention are read from the database |
| `--n-jobs N` | Worker processes for the per-anomaly loops (default: `protocol_n_jobs`, else cores − 1) |
| `--db-path PATH` | Run on another database file |
| `--no-pdf` | Write the `.tex` and figures but do not compile them |
| `--no-figures` | Write the `.tex` without the eight figure PDFs |
| `--quiet` | Less progress logging |

`aa run-protocol --help` lists the rest. Expect about two hours (see [Timings](#timings));
the run is long enough that `nohup aa run-protocol ... > protocol.log 2>&1 &` (or a
`tmux`/`screen` session) is worth using on a remote machine.

Leave out `--authors` and the report's author line is blank (the run says so when it
starts). If the signal is the paper's example, Monetary Policy Exposure (acronym
`MPE`), every option you leave out takes the example's value instead. The names go into the
LaTeX as given, so write a character LaTeX treats specially, such as `&`, `%` or `_`, with a
backslash (`\&`).

#### Protocol memory

The protocol is memory-hungry at full sample, and a run that runs out is killed by the
operating system with a bare `Killed` and no Python error. Two things use the memory:

- **The main process** holds the anomaly zoo, its filled-in copy and each stage's
  results. At full sample (1925–2025, 157 anomalies kept) that is roughly 30–40 GB.
  The combination-strategies stage (average rank, weighted average rank, Fama–MacBeth,
  PLS) works in this process too and adds several GB of temporary data.
- **Each worker process** of the per-anomaly, IPCA and LASSO pools needs about 4 GB.

These are estimates from the code and one 15-worker run, not measurements on a range of
machines. Each pool sizes itself when it starts: as many workers as you asked for
(`--n-jobs`, default cores − 1), but no more than fit in the budget left after the main
process, which is (budget − main process's memory) / 4 GB. The budget is 75% of the
machine's memory: physical RAM, or a container's memory limit when that is smaller
(Docker, Kubernetes, Coder workspaces). When a pool is capped, the log says so:

```text
strats: starting 7 worker(s) instead of 17: 70.6 GiB budget, 41.2 GiB already in use by this process, 4.0 GiB per worker
```

If a run is still killed:

- lower the budget so the pools leave more headroom: `export AA_MEMORY_GB=50` for one
  shell, or `aa set-params --memory-budget-gb 50` to keep it;
- or set the worker count yourself: `aa run-protocol ... --n-jobs 4`;
- memory grows with the database's sample, so a database built from a later
  `--sample-start` needs less. `--time-period` does not help, because the zoo strategies
  always span the full sample.

Rerun with the same `--out-dir`. The combination strategies save each finished method there
(`comb_strats_<method>.pkl`), and a rerun reuses them, though it redoes the earlier stages
(about 10 minutes at full sample).

## Timings

Measured on one workstation (16 cores, 15 protocol workers) on 2026-09-17, CIZ tape,
sample 1925–2024, full trading-cost estimates:

| Step | Wall clock |
|---|---|
| `aa setup-database`, from scratch | 2 h 45 m |
| Protocol on one signal (core computation) | about 2 h (7,042 s) |
| `aa run-protocol`, including the PDF | 1 h 58 m |

The WRDS downloads are a large share of the build and depend on your connection. The
finished database is about 16 GB, and the build also downloads about 10 GB of
Chen–Zimmerman zoo files. The protocol's per-anomaly loops run in parallel; set the pool
size with `aa set-params --protocol-n-jobs N` (default: cores − 1).

### Memory

The build's peak memory is in `transform-crsp-daily` and grows with the number of CRSP daily
rows in the sample. Recommended RAM, for samples ending in 2025:

| Sample start | CRSP daily rows | Recommended RAM |
|---|---|---|
| 1925 | 110M | 80 GB |
| 1963 | 101M | 72 GB |
| 1973 | 95M | 68 GB |
| 1990 | 70M | 52 GB |

Other windows are interpolated from these by their daily rows. `aa setup-database` checks
this before its first stage and stops, naming the earliest sample start that would fit, if
the machine has less (`AA_MEMORY_GB` or `memory_budget_gb`, when set, count as the
machine's RAM); `aa setup-database --skip-memory-check` starts anyway. In a container
with a memory limit below the machine's RAM, the check uses the limit. For the protocol's
memory, see [Protocol memory](#protocol-memory).

## Which CRSP tape?

CRSP froze its legacy stock files (Flat File Format 1.0, "SIZ") in January 2025; they end
in December 2024. Everything since is on Flat File Format 2.0 ("CIZ"). The package builds
from either:

- **CIZ is the default** and the only tape that extends past 2024.
- **SIZ** (`aa set-params --crsp-format siz`) is there to reproduce results built on the
  legacy tape. Changing tapes requires `aa setup-database --full-refresh`.

**Sample end.** The default `sample_end` is `latest`: right after the WRDS login,
`aa setup-database` asks for the last December month on the tape's monthly stock file
(`crsp.msf_v2` for CIZ, `crsp.msf` for SIZ) and the last December fiscal year end on
Compustat `funda`, and builds through the earlier of the two years, so a year whose December
is not out yet is left out. On SIZ, which ends in 2024, `latest` is 2024 and an explicit later
year is lowered to 2024 with a warning. The year is stored in the database
(`metadata.sample_end_resolved`, shown by `aa show-config`) and in the run manifest; a run
that fetches nothing from WRDS (`--start-from` a later stage) reuses it. To compare the two
tapes over the same years, or to fix the window for a paper, pin a year:
`aa set-params --sample-end 2024`. Changing the sample needs `aa setup-database
--full-refresh`.

**The two tapes give different numbers.** CIZ monthly returns compound daily returns with
dividends reinvested on the ex-date and already include CRSP's delisting adjustment. On the
full 1925–2024 window the two builds' universes overlap 99.9%, 9.5% of monthly returns
differ by at least 1 bp, and 19–33% of long-short portfolio months differ by more than
10 bp; but no anomaly premium changes sign, the largest premium movement is 6 bp/month, and
the protocol keeps the same anomaly set. Results reproduce to the research conclusion, not
to the basis point, so any table should say which tape it came from. See Schwarz, Walter
and Weiss, "Rewriting CRSP's History: Impact of Altered Monthly Returns on Asset Pricing",
*JFQA* 2026 ([doi:10.1017/S0022109026102774](https://doi.org/10.1017/S0022109026102774)).

## Trading costs: what you need

The build estimates each stock-month's trading cost (effective half-spread) and stores it
for the protocol's net-of-cost results. Choose how with `aa set-params --tcosts-type`:

| `tcosts_type` | What it uses | What you need to do |
|---|---|---|
| `lf_combo` (default) | Average of four low-frequency estimators from CRSP daily data, one of them Hasbrouck's Gibbs | Nothing. The Gibbs estimates (`crspgibbs.csv`) ship with the package; a `pip install` downloads them once, about 42 MB, and checks their SHA-256. |
| `full` | High-frequency TAQ/ISSM effective spreads where they exist, `lf_combo` elsewhere | Build `hf_monthly.csv` yourself on WRDS Cloud with Chen and Velikov's public code, [hf-spreads-all](https://github.com/chenandrewy/hf-spreads-all) (needs ISSM, Daily TAQ, Monthly TAQ and WRDS TAQ IID subscriptions; about an hour), and put it anywhere in the project folder. See the note below the table for months after December 2024. |
| `gibbs` | Gibbs alone | Nothing. |

If a required file is missing, `aa setup-database` stops before its first WRDS stage and says
what to do. The SAS code that builds the Gibbs file, with its instructions, is in
[`inputs/gibbs/`](inputs/gibbs/README.md).

**`hf_monthly.csv` after December 2024.** The public code attaches a `permno` to each spread
in `add_permnos.sas`, from CRSP's legacy names file, which ends in December 2024. Run as it
is, the job finishes, but no later spread gets a `permno` and the file ends there. To go
further, change `add_permnos.sas` to read CRSP's CIZ names file, `crsp.stksecurityinfohist`.

## Trying it without WRDS

```bash
aa setup-database --demo
```

builds a small database from deterministic synthetic data so you can try the API. It is
stamped as synthetic: the protocol refuses it unless you pass `--allow-demo-data`, and then
labels every output `SYNTHETIC DEMO DATA — NOT REAL RESEARCH OUTPUT`. Never use it for
research. Without `--demo`, a build with no WRDS credentials stops with an error rather than
substituting synthetic data.

## Known limitations

Each item is a summary; the full text will be on the package's website,
[assayinganomalies.com](https://assayinganomalies.com).

- **No trading costs at holding periods longer than one month.** Costs are those of held
  legs (bought at a trade, left alone until the next). With `holding_period > 1` the
  portfolios overlap and are not held legs: `run_univariate_sort` returns gross returns and
  raises if a per-stock cost panel is passed as well. The protocol uses one-month holding
  and is unaffected.
- **Factor trading costs are those of a reconstruction.** The Fama–French factors are
  priced on the toolkit's own 2×3 portfolios, held between trades and re-split to equal
  shares every month; their weights drift with returns, not with market cap.
- **A stock with no panel row in June has no annual data that year**, also after a fill.
- **The random seed is part of the specification.** Tie-break noise in the sorts and the
  LASSO cross-validation folds are seeded; a different seed is a different result, mainly
  for tie-heavy signals such as event dummies. Seeds are recorded in every run manifest.
- **The demo-database stamp is a guard, not a proof of provenance.** An unstamped database
  is treated as real, only the protocol checks the stamp, and only a full rebuild clears it.
- **`run_bivariate_sort` has no per-stock trading costs.** It reports gross returns only,
  and its `tcosts=` argument is currently ignored.

## Citation

If you use this package, please cite the paper (and, optionally, the software; see
[`CITATION.cff`](CITATION.cff)):

```bibtex
@article{NovyMarxVelikov2026,
  author  = {Novy-Marx, Robert and Velikov, Mihail},
  title   = {Assaying Anomalies},
  journal = {SSRN Working Paper},
  year    = {2026},
  doi     = {10.2139/ssrn.4338007},
  url     = {https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4338007}
}
```

## Contact

Bug reports and questions: the repository's
[issue tracker](https://github.com/velikov-mihail/AssayingAnomalies/issues), or
assayinganomalies@gmail.com.

## The MATLAB version

This package replaces the original MATLAB toolkit. The MATLAB code remains available,
unmaintained, on the
[`matlab-legacy` branch](https://github.com/velikov-mihail/AssayingAnomalies/tree/matlab-legacy).

## License

MIT. See [`LICENSE`](LICENSE).
