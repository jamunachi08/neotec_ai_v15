"""A minimal stand-in for frappe so pure helpers in Frappe-importing modules can be unit-tested."""
import sys
import types


def install():
    if "frappe" in sys.modules:
        return
    f = types.ModuleType("frappe")
    f._ = lambda s, *a: s
    f.whitelist = lambda *a, **k: (lambda fn: fn)
    f.flags = {}
    f._dict = dict
    utils = types.ModuleType("frappe.utils")
    for name in ("cint", "flt"):
        setattr(utils, name, (lambda v, *_a: int(float(v or 0))) if name == "cint" else (lambda v, *_a: float(v or 0)))
    for name in ("add_days", "add_to_date", "get_datetime", "now_datetime", "nowdate", "get_first_day"):
        setattr(utils, name, lambda *a, **k: None)
    f.utils = utils
    sys.modules["frappe"] = f
    sys.modules["frappe.utils"] = utils
