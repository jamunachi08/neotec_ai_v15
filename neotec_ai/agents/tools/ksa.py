# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Saudi-specific calculators and checks. The arithmetic lives here so the model never estimates it.

The pure functions (vat_split, vat_number_problems, iban_problems, end_of_service) import nothing
from Frappe and are unit-tested.
"""

from __future__ import annotations

import re
from datetime import date

from neotec_ai.agents.engine.registry import tool

S = {"type": "string"}
N = {"type": "number"}

SA_BANKS = {
    "05": "Alinma Bank", "10": "Saudi National Bank", "15": "Bank Albilad", "20": "Riyad Bank",
    "30": "Arab National Bank", "40": "Saudi Awwal Bank", "55": "Banque Saudi Fransi",
    "60": "Bank AlJazira", "65": "Saudi Investment Bank", "80": "Al Rajhi Bank",
}

REASONS = {
    "termination": "Termination by the employer (Art. 84)",
    "contract_end": "Fixed-term contract ended (Art. 84)",
    "resignation": "Resignation (Art. 85)",
    "employer_breach": "Worker left due to the employer's breach (Art. 81)",
    "force_majeure": "Force majeure (Art. 87)",
    "marriage_or_childbirth": "Female worker within 6 months of marriage or 3 months of childbirth (Art. 87)",
    "dismissal_art80": "Dismissal for cause under Art. 80",
}


def _r2(x: float) -> float:
    return float(f"{x:.2f}")


def vat_split(amount: float, inclusive: bool = False, rate: float = 15.0) -> dict:
    amount, rate = float(amount), float(rate)
    if inclusive:
        net = amount / (1 + rate / 100)
        vat = amount - net
        gross = amount
    else:
        net = amount
        vat = amount * rate / 100
        gross = amount + vat
    return {"net": _r2(net), "vat": _r2(vat), "gross": _r2(gross), "rate_pct": rate}


def vat_number_problems(vat: str) -> list[str]:
    v = re.sub(r"\s", "", str(vat or ""))
    problems = []
    if not v.isdigit():
        problems.append("must contain digits only")
    if len(v) != 15:
        problems.append(f"must be 15 digits (has {len(v)})")
    if v[:1] != "3":
        problems.append("must start with 3")
    if v[-1:] != "3":
        problems.append("must end with 3")
    return problems


def iban_problems(iban: str) -> tuple[list[str], str | None]:
    v = re.sub(r"\s", "", str(iban or "")).upper()
    problems = []
    if not v.startswith("SA"):
        problems.append("Saudi IBANs start with SA")
    if len(v) != 24:
        problems.append(f"must be 24 characters (has {len(v)})")
    if not re.fullmatch(r"[A-Z0-9]+", v or "-"):
        problems.append("letters and digits only")
    if not problems:
        moved = v[4:] + v[:4]
        numeric = "".join(str(int(ch, 36)) for ch in moved)
        if int(numeric) % 97 != 1:
            problems.append("check digits do not match (likely a typo)")
    bank = SA_BANKS.get(v[4:6]) if len(v) >= 6 else None
    return problems, bank


def end_of_service(monthly_wage: float, start: date, end: date, reason: str) -> dict:
    """End-of-service award under the Saudi Labor Law (Articles 84, 85, 87; Art. 80 exclusion)."""
    if end < start:
        raise ValueError("end date is before start date")
    days = (end - start).days + 1
    years = days / 365.0
    wage = float(monthly_wage)
    first = min(years, 5) * 0.5 * wage
    rest = max(years - 5, 0) * wage
    full = first + rest
    reason = reason if reason in REASONS else "termination"

    if reason == "dismissal_art80":
        factor, rule = 0.0, "Art. 80 dismissal: no award."
    elif reason == "resignation":
        if years < 2:
            factor, rule = 0.0, "Resignation under 2 years of service: no award (Art. 85)."
        elif years < 5:
            factor, rule = 1 / 3, "Resignation with 2 to 5 years: one third of the award (Art. 85)."
        elif years < 10:
            factor, rule = 2 / 3, "Resignation with 5 to 10 years: two thirds of the award (Art. 85)."
        else:
            factor, rule = 1.0, "Resignation with 10+ years: full award (Art. 85)."
    else:
        factor, rule = 1.0, f"{REASONS[reason]}: full award."

    return {
        "service": {"days": days, "years": round(years, 3)},
        "monthly_wage": _r2(wage),
        "award_first_5_years": _r2(first),
        "award_after_5_years": _r2(rest),
        "full_award": _r2(full),
        "entitlement_factor": round(factor, 4),
        "payable": _r2(full * factor),
        "reason": REASONS[reason],
        "rule": rule,
        "basis": "Half a month's wage per year for the first five years, a full month's wage per year after; "
                 "partial years pro rata. Wage = last actual wage (basic plus regular allowances).",
        "disclaimer": "Estimate. Confirm with HR / legal against the current Labor Law, the contract and any "
                      "more favourable company policy.",
    }


# ---------------------------------------------------------------- tools

@tool("ksa_vat", "VAT calculator (KSA)",
      "Split an amount into net, VAT and gross at the Saudi standard rate (15%) or a given rate.",
      {"amount": N, "inclusive": {"type": "boolean", "description": "True if the amount already includes VAT"},
       "rate": N, "__required__": ["amount"]}, category="KSA Compliance")
def ksa_vat(amount, inclusive=False, rate=15):
    return vat_split(amount, bool(inclusive), rate if rate not in (None, "") else 15)


@tool("ksa_validate_vat_number", "Check a VAT number (KSA)",
      "Check the format of a Saudi VAT registration number (15 digits, starts and ends with 3).",
      {"vat_number": S, "__required__": ["vat_number"]}, category="KSA Compliance")
def ksa_validate_vat_number(vat_number):
    problems = vat_number_problems(vat_number)
    return {"vat_number": vat_number, "valid_format": not problems, "problems": problems,
            "note": "Format check only. Confirm registration on the ZATCA portal."}


@tool("ksa_validate_iban", "Check an IBAN (KSA)",
      "Validate a Saudi IBAN (length, characters, check digits) and name the bank from its code.",
      {"iban": S, "__required__": ["iban"]}, category="KSA Compliance")
def ksa_validate_iban(iban):
    problems, bank = iban_problems(iban)
    return {"valid": not problems, "problems": problems, "bank": bank}


@tool("ksa_end_of_service", "End-of-service calculator (KSA)",
      "Calculate the end-of-service award under the Saudi Labor Law. reason: termination, contract_end, "
      "resignation, employer_breach, force_majeure, marriage_or_childbirth, dismissal_art80.",
      {"monthly_wage": N, "start_date": S, "end_date": S,
       "reason": {"type": "string", "enum": list(REASONS)},
       "__required__": ["monthly_wage", "start_date", "end_date", "reason"]}, category="KSA Compliance")
def ksa_end_of_service(monthly_wage, start_date, end_date, reason="termination"):
    from frappe.utils import getdate

    return end_of_service(float(monthly_wage), getdate(start_date), getdate(end_date), reason)


@tool("ksa_invoice_check", "e-Invoice readiness check (KSA)",
      "Check a Sales or Purchase Invoice for common ZATCA e-invoicing problems: VAT numbers, buyer details "
      "for B2B, address and postal code, VAT amount against the 15% rate, credit-note reference.",
      {"doctype": {"type": "string", "enum": ["Sales Invoice", "Purchase Invoice"]}, "name": S,
       "__required__": ["doctype", "name"]}, category="KSA Compliance")
def ksa_invoice_check(doctype, name):
    import frappe
    from frappe.utils import flt

    if doctype not in ("Sales Invoice", "Purchase Invoice"):
        frappe.throw("Only Sales Invoice or Purchase Invoice can be checked.")
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    checks = []

    def add(ok, label, detail=""):
        checks.append({"check": label, "ok": bool(ok), "detail": detail})

    company_vat = frappe.db.get_value("Company", doc.company, "tax_id")
    p = vat_number_problems(company_vat) if company_vat else ["missing"]
    add(not p, "Seller VAT number" if doctype == "Sales Invoice" else "Our VAT number", ", ".join(p))

    party_type = "Customer" if doctype == "Sales Invoice" else "Supplier"
    party = doc.customer if doctype == "Sales Invoice" else doc.supplier
    party_vat = doc.get("tax_id") or frappe.db.get_value(party_type, party, "tax_id")
    is_company = (frappe.db.get_value(party_type, party, "customer_type" if party_type == "Customer" else "supplier_type")
                  == "Company")
    if party_vat:
        p = vat_number_problems(party_vat)
        add(not p, f"{party_type} VAT number", ", ".join(p))
    elif is_company:
        add(False, f"{party_type} VAT number",
            "missing for a company buyer: the invoice will be simplified (B2C) instead of standard (B2B)"
            if doctype == "Sales Invoice" else "missing; input VAT may not be recoverable")

    addr_field = "customer_address" if doctype == "Sales Invoice" else "supplier_address"
    addr_name = doc.get(addr_field)
    if addr_name:
        addr = frappe.db.get_value("Address", addr_name, ["address_line1", "city", "pincode", "country"], as_dict=True) or {}
        add(bool(addr.get("address_line1") and addr.get("city")), f"{party_type} address street and city")
        if (addr.get("country") or "") == "Saudi Arabia":
            pin = (addr.get("pincode") or "").strip()
            add(bool(re.fullmatch(r"\d{5}", pin)), "Saudi postal code (5 digits)", pin or "missing")
    else:
        add(not is_company, f"{party_type} address", "missing")

    net, tax = flt(doc.base_net_total), flt(doc.base_total_taxes_and_charges)
    if net:
        rate = round(tax / net * 100, 2)
        add(rate in (15.0, 0.0) or abs(rate - 15) < 0.05, "VAT amount vs 15%",
            f"effective rate {rate}% (zero-rated or exempt lines need a reason)" if rate != 15.0 else "15%")
    if doc.get("is_return"):
        add(bool(doc.get("return_against")), "Credit/debit note references the original invoice")
    add(doc.docstatus == 1, "Submitted", {0: "draft", 1: "submitted", 2: "cancelled"}.get(doc.docstatus, ""))
    failed = [c for c in checks if not c["ok"]]
    return {"doctype": doctype, "name": name, "passed": len(checks) - len(failed), "failed": len(failed),
            "checks": checks,
            "note": "Pre-check only. The e-invoicing app and ZATCA validation remain the authority."}
