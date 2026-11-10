"""Lightweight keyword relevance, used to decide which data sources, reports and playbooks get full
detail in the AI prompt. No external services; good enough to pick a handful of candidates out of dozens.
"""

import re

STOP = frozenset(
    "a an and any all are as at be by can could do does for from get give how i in into is it its list me my of on "
    "or our please show tell than that the their them there these this those to us we what when where which who "
    "why with would you your per vs versus".split()
)

# Business synonyms: a question word -> words that appear in source/report names and descriptions.
SYNONYMS = {
    "revenue": {"sale", "sales", "invoice", "income", "turnover"},
    "sale": {"invoice", "revenue", "order"},
    "profit": {"income", "expense", "margin", "loss", "gross"},
    "margin": {"profit", "gross"},
    "expense": {"cost", "purchase", "ledger", "loss"},
    "cost": {"expense", "purchase", "valuation"},
    "owe": {"receivable", "outstanding", "payable", "overdue"},
    "overdue": {"receivable", "outstanding", "due", "ageing"},
    "ageing": {"receivable", "payable", "overdue", "age"},
    "debtor": {"receivable", "customer", "outstanding"},
    "creditor": {"payable", "supplier", "outstanding"},
    "cash": {"payment", "bank", "flow"},
    "collection": {"payment", "receive", "receivable"},
    "stock": {"inventory", "warehouse", "bin", "item", "balance"},
    "inventory": {"stock", "warehouse", "bin", "item"},
    "product": {"item"},
    "client": {"customer"},
    "vendor": {"supplier"},
    "pipeline": {"opportunity", "lead", "stage"},
    "prospect": {"lead", "opportunity"},
    "staff": {"employee"},
    "headcount": {"employee"},
    "spend": {"purchase", "expense", "supplier"},
    "approval": {"workflow", "approve"},
    "ticket": {"issue", "support"},
}


def singular(w):
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("ses", "xes", "ches", "shes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def words(text):
    return {singular(w) for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOP and len(w) > 1}


def expand(ws):
    out = set(ws)
    for w in ws:
        out |= {singular(x) for x in SYNONYMS.get(w, ())}
    return out


def score(query_words, name, text=""):
    """Name matches count three times as much as description matches."""
    if not query_words:
        return 0
    name_w = words(name)
    text_w = words(text)
    direct = len(query_words & name_w) * 3 + len(query_words & text_w)
    return direct


def rank(query, items, key_name, key_text, k=5, min_score=1):
    """items: iterable of objects/dicts; returns the top-k (item, score) with score >= min_score."""
    q = expand(words(query))
    scored = []
    for it in items:
        name = key_name(it)
        s = score(q, name, key_text(it))
        if s >= min_score:
            scored.append((s, name, it))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [(it, s) for s, _, it in scored[:k]]
