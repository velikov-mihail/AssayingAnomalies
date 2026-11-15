"""
The random streams of the anomalies' tie-breaking noise.

The zoo's signals get ``N(0, 1e-12)`` noise before they are sorted or ranked,
so that exactly tied values have a definite order (MATLAB does the same with
an unseeded ``randn``). Each anomaly draws from its own stream, and the stream
is keyed by the anomaly's **name**: an anomaly has the same noise, and so the
same strategy and the same filled ranks, whatever the other anomalies passed
with it and whatever its place among them.
"""

from __future__ import annotations

import hashlib

import numpy as np

__all__ = ["NOISE_STREAM_RULE", "noise_stream_key", "anomaly_noise_rng"]

# Recorded in the protocol manifest's ``seeds`` block.
NOISE_STREAM_RULE: str = "default_rng([seed, sha256(name)[:8]])"


def noise_stream_key(name: object) -> int:
    """The stream key of an anomaly: the first 8 bytes of SHA-256 of its name.

    ``str(name)`` in UTF-8, read as a big-endian unsigned integer. Unlike
    Python's ``hash``, it is the same in every process and on every machine.
    """
    digest = hashlib.sha256(str(name).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def anomaly_noise_rng(seed: int, name: object) -> np.random.Generator:
    """The generator anomaly ``name`` draws its tie-breaking noise from."""
    return np.random.default_rng([int(seed), noise_stream_key(name)])
