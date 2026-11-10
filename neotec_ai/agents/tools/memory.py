# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Personal memory: short facts a user wants every coworker to keep in mind."""

from __future__ import annotations

import frappe

from neotec_ai.agents.engine.registry import tool

MAX_FACTS = 200


@tool("remember_fact", "Remember a fact",
      "Save a short, durable fact or preference the user asked you to remember (e.g. 'Report figures in SAR "
      "thousands'). Only when the user asks you to remember something. Never store passwords, ID numbers, "
      "IBANs, salaries or health details.",
      {"fact": {"type": "string"}, "__required__": ["fact"]}, category="Memory")
def remember_fact(fact):
    from neotec_ai.agents.engine.redact import mask_all

    fact = (fact or "").strip()[:280]
    if not fact:
        frappe.throw("Nothing to remember.")
    if mask_all(fact) != fact:
        frappe.throw("That looks like personal or secret data, which coworkers do not store in memory.")
    user = frappe.session.user
    if frappe.db.count("Coworker Memory", {"user": user}) >= MAX_FACTS:
        frappe.throw("Memory is full. Ask the user to remove old facts under Coworker Memory.")
    if frappe.db.exists("Coworker Memory", {"user": user, "fact": fact}):
        return {"saved": False, "note": "Already remembered."}
    doc = frappe.get_doc({"doctype": "Coworker Memory", "user": user, "fact": fact, "source": "Coworker",
                          "coworker": None, "enabled": 1})
    doc.insert()
    return {"saved": True, "id": doc.name}
