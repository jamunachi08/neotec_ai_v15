# Copyright (c) 2026, Neotec Integrated Solutions
# License: Proprietary
"""Knowledge base: Arabic-aware keyword retrieval with citations. No external vector service needed,
so it runs on Frappe Cloud and keeps documents in the site's own database."""

from __future__ import annotations

import math
import re
from collections import Counter

import frappe
from frappe.utils import cint, strip_html

from neotec_ai.agents.engine import arabic
from neotec_ai.agents.engine.registry import tool

CHUNK = 1200


def split_passages(text: str, size: int = CHUNK) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n|\r\n\r\n", text or "") if p.strip()]
    out, buf = [], ""
    for p in paras:
        while len(p) > size:  # very long paragraph: cut on sentence boundary
            cut = max(p.rfind(". ", 0, size), p.rfind("۔", 0, size), p.rfind("، ", 0, size))
            cut = cut + 1 if cut > size // 3 else size
            pieces, p = p[:cut].strip(), p[cut:].strip()
            if buf:
                out.append(buf)
                buf = ""
            out.append(pieces)
        if len(buf) + len(p) + 2 <= size:
            buf = f"{buf}\n\n{p}" if buf else p
        else:
            if buf:
                out.append(buf)
            tail = buf.split("\n\n")[-1] if buf else ""
            buf = f"{tail}\n\n{p}" if tail and len(tail) + len(p) < size else p
    if buf:
        out.append(buf)
    return out


def extract_file_text(file_url: str) -> str:
    file_doc = frappe.get_doc("File", {"file_url": file_url})
    name = (file_doc.file_name or file_url).lower()
    if name.endswith(".pdf"):
        try:
            from io import BytesIO

            from pypdf import PdfReader
        except ImportError:
            frappe.throw("PDF extraction needs the pypdf package. Paste the text into Content instead.")
        reader = PdfReader(BytesIO(file_doc.get_content()))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages[:300])
    content = file_doc.get_content()
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="ignore")
    return content


def reindex(doc):
    frappe.db.delete("Coworker Knowledge Chunk", {"knowledge": doc.name})
    text = strip_html(doc.content or "")
    passages = split_passages(text) if doc.enabled else []
    for i, passage in enumerate(passages, start=1):
        frappe.get_doc({
            "doctype": "Coworker Knowledge Chunk", "knowledge": doc.name, "coworker": doc.coworker,
            "seq": i, "content": passage, "search_text": arabic.search_text(f"{doc.title}\n{passage}"),
        }).insert(ignore_permissions=True)
    frappe.db.set_value("Coworker Knowledge", doc.name, "chunk_count", len(passages), update_modified=False)
    return len(passages)


def search(query: str, coworker: str | None = None, limit: int = 5) -> list[dict]:
    terms = list(dict.fromkeys(arabic.tokens(query)))[:12]
    if not terms:
        return []
    conditions = " or ".join(["c.search_text like %(t{})s".format(i) for i in range(len(terms))])
    params = {f"t{i}": f"%{t}%" for i, t in enumerate(terms)}
    params["cw"] = coworker or ""
    rows = frappe.db.sql(f"""
        select c.name, c.knowledge, c.seq, c.content, c.search_text, k.title
        from `tabCoworker Knowledge Chunk` c join `tabCoworker Knowledge` k on k.name = c.knowledge
        where k.enabled = 1 and (ifnull(k.coworker, '') = '' or k.coworker = %(cw)s) and ({conditions})
        limit 400
    """, params, as_dict=True)
    if not rows:
        return []
    docs = [Counter(r.search_text.split()) for r in rows]
    n = len(rows)
    df = {t: sum(1 for d in docs if any(w.startswith(t) for w in d)) for t in terms}
    scored = []
    for r, d in zip(rows, docs):
        score = 0.0
        for t in terms:
            tf = sum(c for w, c in d.items() if w.startswith(t))
            if tf:
                score += (1 + math.log(tf)) * math.log(1 + n / (df[t] or 1))
        coverage = sum(1 for t in terms if any(w.startswith(t) for w in d)) / len(terms)
        score *= 0.5 + coverage
        scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    return [{"source": r.title, "knowledge": r.knowledge, "passage": r.seq, "score": round(s, 2),
             "text": r.content[:1500]} for s, r in scored[: max(1, min(cint(limit) or 5, 10))]]


@tool("search_knowledge", "Search the knowledge base",
      "Search company policies, procedures and manuals loaded into Neotec AI. Works in Arabic and English. "
      "Quote the source title when you rely on a passage. If nothing relevant is found, say so.",
      {"query": {"type": "string"}, "limit": {"type": "integer"}, "__required__": ["query"]},
      category="Knowledge")
def search_knowledge(query, limit=5):
    hits = search(query, frappe.flags.get("ntc_coworker"), limit)
    return {"query": query, "results": hits,
            "note": "" if hits else "No passage in the knowledge base matches this question."}
