# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Stock tools."""

from __future__ import annotations

import frappe
from frappe.utils import cint, flt

from neotec_ai.agents.engine.registry import tool
from neotec_ai.agents.tools._common import ensure_doctype

S = {"type": "string"}
I = {"type": "integer"}
BIN_FIELDS = ["item_code", "warehouse", "actual_qty", "reserved_qty", "ordered_qty", "projected_qty", "stock_value"]


@tool("stock_levels", "Stock levels",
      "Quantity on hand, reserved, ordered and projected per item and warehouse.",
      {"item_code": S, "warehouse": S, "item_group": S, "limit": I}, category="Stock")
def stock_levels(item_code=None, warehouse=None, item_group=None, limit=50):
    ensure_doctype("Bin")
    filters = {}
    if item_code:
        filters["item_code"] = item_code
    if warehouse:
        filters["warehouse"] = warehouse
    if item_group:
        items = frappe.get_list("Item", filters={"item_group": item_group}, pluck="name", limit_page_length=5000)
        if not items:
            return {"rows": [], "note": f"No items in group {item_group}."}
        filters["item_code"] = ["in", items]
    rows = frappe.get_list("Bin", filters=filters, fields=BIN_FIELDS, order_by="actual_qty desc",
                           limit_page_length=max(1, min(cint(limit) or 50, 200)))
    return {"rows": [{k: (flt(v, 3) if isinstance(v, float) else v) for k, v in r.items()} for r in rows]}


@tool("low_stock", "Low stock",
      "Items whose projected quantity is below their re-order level (from the Item's Re-order table) "
      "or below zero.", {"warehouse": S, "limit": I}, category="Stock")
def low_stock(warehouse=None, limit=50):
    ensure_doctype("Bin")
    ensure_doctype("Item")
    rf = {"parenttype": "Item"}
    if warehouse:
        rf["warehouse"] = warehouse
    levels = {}
    for r in frappe.get_all("Item Reorder", filters=rf,
                            fields=["parent", "warehouse", "warehouse_reorder_level", "warehouse_reorder_qty"]):
        levels[(r.parent, r.warehouse)] = r
    bin_filters = {"warehouse": warehouse} if warehouse else {}
    bins = frappe.get_list("Bin", filters=bin_filters, fields=BIN_FIELDS, limit_page_length=50000)
    out = []
    for b in bins:
        lvl = levels.get((b.item_code, b.warehouse))
        reorder = flt(lvl.warehouse_reorder_level) if lvl else 0
        if flt(b.projected_qty) < 0 or (lvl and flt(b.projected_qty) < reorder):
            out.append({"item_code": b.item_code, "warehouse": b.warehouse, "actual_qty": flt(b.actual_qty, 3),
                        "projected_qty": flt(b.projected_qty, 3), "reorder_level": reorder,
                        "suggested_qty": flt(lvl.warehouse_reorder_qty) if lvl else None,
                        "shortfall": round(reorder - flt(b.projected_qty), 3)})
    out.sort(key=lambda r: -r["shortfall"])
    return {"items": out[: max(1, min(cint(limit) or 50, 200))], "total_flagged": len(out)}
