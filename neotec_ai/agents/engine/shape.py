# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Fitting a tool result into the model's budget without cutting it mid-record.

A plain character cut leaves broken JSON and half a row. Instead: encode record lists as compact tables
(lossless), and if still too long keep the first rows of the largest list and say how many were left out, so
the model knows to narrow the filter or aggregate. Character truncation is the last resort.

Pure Python.
"""

from __future__ import annotations

import json

from neotec_ai.platform import compress


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))


def _largest_list(obj, path=()):
    best = (0, None)
    if isinstance(obj, list):
        best = (len(obj), path)
        for i, v in enumerate(obj[:5]):
            cand = _largest_list(v, path + (i,))
            if cand[0] > best[0]:
                best = cand
    elif isinstance(obj, dict):
        for k, v in obj.items():
            cand = _largest_list(v, path + (k,))
            if cand[0] > best[0]:
                best = cand
    return best


def _get(obj, path):
    for p in path:
        obj = obj[p]
    return obj


def _set(obj, path, value):
    if not path:
        return value
    parent = _get(obj, path[:-1])
    parent[path[-1]] = value
    return obj


def fit(payload, limit: int) -> str:
    text = _dump(payload)
    if len(text) <= limit:
        return text
    encoded = compress._encode(payload)
    etext = _dump(encoded)
    if encoded != payload and len(etext) <= limit:
        return "(Lists of records are __table__ objects with columns and rows.) " + etext
    work = json.loads(_dump(payload))
    size, path = _largest_list(work)
    if path is not None and size > 1:
        full = _get(work, path)
        lo, hi, best = 1, len(full), None
        while lo <= hi:
            mid = (lo + hi) // 2
            trial = json.loads(_dump(work))
            trial = _set(trial, path, full[:mid])
            note = {"_omitted": f"{len(full) - mid} more of {len(full)} rows not shown. Narrow the filters, "
                                 "ask for fewer fields, or aggregate."}
            candidate = _dump({"result": trial, **note}) if not isinstance(trial, dict) else _dump({**trial, **note})
            if len(candidate) <= limit:
                best, lo = candidate, mid + 1
            else:
                hi = mid - 1
        if best:
            return best
    cut = len(text) - limit
    return text[:limit] + f" …[truncated {cut} more characters; narrow the request]"
