"""
PUNARVAAS · one place where numbers become JSON.

Three float values are legal in Python and illegal in JSON: `inf`, `-inf` and
`nan`. `json.dumps` writes them anyway, as the bare tokens `Infinity` and `NaN`,
which Python reads back happily and which every conforming parser — the browser
`JSON.parse` this project's own console uses, PostgreSQL's `jsonb`, jq — rejects
outright. RFC 8259 has no such literals.

That asymmetry is a trap: an artefact written by the pipeline round-trips
perfectly in the test that wrote it and fails the first time anything outside
Python reads it. So the conversion happens once, here, and it is a *conversion*
rather than a silent drop:

  inf, -inf, nan  →  null
  numpy scalars   →  the corresponding Python scalar
  numpy arrays    →  lists
  sets, tuples    →  lists
  dataclasses     →  their `as_dict()` if they have one, else `asdict()`
  datetimes/Path  →  ISO / str

`null` is the honest encoding for all three: JSON has no way to say "unbounded",
so the caller has to be told separately (see `ResourceCapacity.limiting`).
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import math
from pathlib import Path

import numpy as np


def json_safe(obj):
    """Recursively convert `obj` into something `json.dumps(allow_nan=False)` accepts."""
    if obj is None or isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, np.ndarray):
        return [json_safe(x) for x in obj.tolist()]
    if isinstance(obj, dict):
        return {(k if isinstance(k, str) else str(k)): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [json_safe(x) for x in obj]
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        as_dict = getattr(obj, "as_dict", None)
        return json_safe(as_dict() if callable(as_dict) else dataclasses.asdict(obj))
    if isinstance(obj, (_dt.datetime, _dt.date)):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def dumps(obj, **kw) -> str:
    """`json.dumps` that cannot emit non-conforming JSON."""
    import json
    kw.setdefault("allow_nan", False)
    return json.dumps(json_safe(obj), **kw)
