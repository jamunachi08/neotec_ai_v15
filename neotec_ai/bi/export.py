"""File builders shared by downloads and scheduled e-mails: Excel, CSV and PDF (with charts)."""

import csv
import html
import io

import frappe
from frappe.utils import now_datetime

from neotec_ai.bi import viz as vizlib

NUMBER_FORMATS = {"Currency": "#,##0.00", "Float": "#,##0.00", "Percent": "0.00", "Int": "#,##0"}


def display_table(report):
    """The table a user sees: the pivot when the visualization is a pivot, else the raw result."""
    if report.get("pivot"):
        return report["pivot"]
    return {"columns": report["columns"], "rows": report["rows"]}


def number_value(report):
    v = report.get("viz") or {}
    idx = next((i for i, c in enumerate(report["columns"]) if c["fieldname"] == v.get("column")), None)
    if idx is None:
        return None
    vals = [r[idx] for r in report["rows"] if isinstance(r[idx], (int, float)) and not isinstance(r[idx], bool)]
    agg = v.get("agg") or "sum"
    if agg == "count":
        return len(report["rows"])
    if not vals:
        return None
    return {"sum": sum(vals), "first": vals[0], "avg": sum(vals) / len(vals), "min": min(vals), "max": max(vals)}[agg]


def to_csv(report):
    t = display_table(report)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([_xl(c["label"]) for c in t["columns"]])
    w.writerows([[_xl(v) for v in r] for r in t["rows"]])
    return buf.getvalue().encode("utf-8-sig")


def to_xlsx(reports):
    """One sheet per report."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    wb.remove(wb.active)
    used = set()
    for rep in reports:
        name = _sheet_name(rep.get("title") or "Report", used)
        ws = wb.create_sheet(name)
        t = display_table(rep)
        ws.append([_xl(str(c["label"])) for c in t["columns"]])
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="0F172A")
        for row in t["rows"]:
            ws.append([_xl(v) for v in row])
        for i, c in enumerate(t["columns"], start=1):
            fmt = NUMBER_FORMATS.get(c["fieldtype"])
            letter = ws.cell(row=1, column=i).column_letter
            width = max([len(str(c["label"]))] + [len(str(r[i - 1] or "")) for r in t["rows"][:200]]) + 2
            ws.column_dimensions[letter].width = min(max(width, 8), 50)
            if fmt:
                for cell in ws[letter][1:]:
                    cell.number_format = fmt
        ws.freeze_panes = "A2"
    if not wb.sheetnames:
        wb.create_sheet("Report")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _sheet_name(title, used):
    base = "".join(ch for ch in title if ch not in '[]:*?/\\')[:28] or "Report"
    name, n = base, 2
    while name in used:
        name = f"{base[:25]} {n}"
        n += 1
    used.add(name)
    return name


def _xl(v):
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") and not _is_number(v):
        return "'" + v  # neutralise spreadsheet formula injection from data
    return v


def _is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def report_html(report, max_rows=300, charts=True):
    """HTML block for PDF / e-mail: KPI or chart, then the table."""
    esc = html.escape
    v = report.get("viz") or {}
    out = [f'<div class="nr-block"><h3>{esc(report.get("title") or "")}</h3>']
    if report.get("description"):
        out.append(f'<p class="nr-desc">{esc(report["description"])}</p>')
    if report.get("error"):
        out.append(f'<p class="nr-err">{esc(report["error"])}</p></div>')
        return "".join(out)
    if v.get("type") == "number":
        val = number_value(report)
        out.append(f'<div class="nr-kpi">{esc(v.get("prefix") or "")}{_fmt(val)}{esc(v.get("suffix") or "")}</div>')
    elif charts and v.get("type") in vizlib.CHART_TYPES:
        out.append(vizlib.svg_chart(report, v))
    t = display_table(report)
    out.append('<table class="nr-table"><thead><tr>')
    out.extend(f"<th>{esc(str(c['label']))}</th>" for c in t["columns"])
    out.append("</tr></thead><tbody>")
    for r in t["rows"][:max_rows]:
        out.append("<tr>")
        for c, val in zip(t["columns"], r):
            num = c["fieldtype"] in vizlib.NUMERIC or c["fieldtype"] == "Float"
            out.append(f'<td class="{"num" if num else ""}">{esc(_fmt(val) if num else ("" if val is None else str(val)))}</td>')
        out.append("</tr>")
    out.append("</tbody></table>")
    if len(t["rows"]) > max_rows:
        out.append(f'<p class="nr-desc">Showing {max_rows} of {len(t["rows"])} rows; see the Excel attachment for all rows.</p>')
    out.append("</div>")
    return "".join(out)


def _fmt(v):
    if v is None or v == "":
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f"{v:,.2f}" if isinstance(v, float) and not float(v).is_integer() else f"{v:,.0f}"
    return str(v)


CSS = """
body{font-family:Arial,Helvetica,sans-serif;color:#111;font-size:11px}
h1{font-size:18px;margin:0 0 2px}h3{font-size:14px;margin:18px 0 4px}
.nr-head{border-bottom:2px solid #0d9488;padding-bottom:6px;margin-bottom:8px}
.nr-desc{color:#555;margin:0 0 6px}.nr-err{color:#b91c1c}
.nr-kpi{font-size:28px;font-weight:bold;color:#0f172a;margin:6px 0 10px}
.nr-table{border-collapse:collapse;width:100%;margin-top:6px}
.nr-table th{background:#0f172a;color:#fff;text-align:left;padding:4px 6px}
.nr-table td{border-bottom:1px solid #e5e7eb;padding:3px 6px}.nr-table td.num{text-align:right}
.nr-block{page-break-inside:avoid}
"""


def document_html(title, reports, subtitle=None):
    esc = html.escape
    sub = subtitle or f"Generated {now_datetime().strftime('%Y-%m-%d %H:%M')}"
    body = "".join(report_html(r) for r in reports)
    return (
        f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>"
        f"<div class='nr-head'><h1>{esc(title)}</h1><div class='nr-desc'>{esc(sub)}</div></div>{body}</body></html>"
    )


def to_pdf(title, reports, subtitle=None):
    from frappe.utils.pdf import get_pdf

    return get_pdf(document_html(title, reports, subtitle), {"orientation": "Landscape"})


def send_file(filename, content):
    frappe.response["filename"] = filename
    frappe.response["filecontent"] = content
    frappe.response["type"] = "binary"
