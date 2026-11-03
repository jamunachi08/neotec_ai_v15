"""Visualization specs: validation, defaults and server-side SVG charts (for PDF / e-mail)."""

import html
import math

from neotec_ai.query_engine import PlanError as QueryError

VIZ_TYPES = ("table", "bar", "line", "area", "pie", "donut", "percentage", "number", "pivot")
CHART_TYPES = ("bar", "line", "area", "pie", "donut", "percentage")
SINGLE_SERIES = ("pie", "donut", "percentage")
NUMERIC = {"Int", "Float", "Currency", "Percent", "Duration", "Rating"}
PALETTE = ["#0d9488", "#2563eb", "#f59e0b", "#db2777", "#7c3aed", "#16a34a", "#ea580c", "#0891b2", "#64748b", "#dc2626"]


def from_legacy_chart(chart):
    if not chart:
        return None
    return {"type": chart.get("type") or "bar", "x": chart.get("x"), "y": chart.get("y")}


def suggest(columns, row_count=0):
    num = [c["fieldname"] for c in columns if c["fieldtype"] in NUMERIC]
    lab = [c for c in columns if c["fieldtype"] not in NUMERIC]
    if row_count == 1 and num and not lab:
        return {"type": "number", "column": num[0]}
    if not num or not lab:
        return {"type": "table"}
    x = lab[0]
    is_time = x["fieldtype"] == "Date" or any(k in x["fieldname"] for k in ("month", "year", "week", "quarter", "date", "day"))
    return {"type": "line" if is_time else "bar", "x": [x["fieldname"]], "y": num[:3]}


def validate(viz, columns):
    """Return a clean viz dict. Unknown/empty -> a sensible default."""
    if not viz:
        return suggest(columns)
    if not isinstance(viz, dict):
        raise QueryError("Visualization must be an object.")
    names = {c["fieldname"]: c for c in columns}
    numeric = [n for n, c in names.items() if c["fieldtype"] in NUMERIC]
    vtype = str(viz.get("type") or "table").lower()
    if vtype not in VIZ_TYPES:
        raise QueryError(f"Visualization type must be one of: {', '.join(VIZ_TYPES)}.")

    def cols(v):
        v = v if isinstance(v, list) else ([v] if v else [])
        return [str(x).lower() for x in v if x]

    if vtype == "table":
        return {"type": "table"}

    if vtype == "number":
        col = str(viz.get("column") or (numeric[0] if numeric else "")).lower()
        if col not in numeric:
            raise QueryError("A number card needs a numeric column.")
        agg = viz.get("agg") or "sum"
        if agg not in ("sum", "first", "avg", "min", "max", "count"):
            raise QueryError("Number card aggregate must be sum, first, avg, min, max or count.")
        return {
            "type": "number", "column": col, "agg": agg,
            "prefix": str(viz.get("prefix") or "")[:10], "suffix": str(viz.get("suffix") or "")[:10],
        }

    if vtype == "pivot":
        p = viz.get("pivot") or viz
        rows, col, val = cols(p.get("rows")), str(p.get("columns") or "").lower(), str(p.get("values") or "").lower()
        if not rows or len(rows) > 3 or any(r not in names for r in rows):
            raise QueryError("Pivot needs 1-3 row columns from the results.")
        if col not in names or col in rows:
            raise QueryError("Pivot needs a column field (different from the rows).")
        if val not in numeric:
            raise QueryError("Pivot values must be a numeric column.")
        agg = (p.get("agg") or "sum").lower()
        if agg not in ("sum", "count", "avg", "min", "max"):
            raise QueryError("Pivot aggregate must be sum, count, avg, min or max.")
        return {"type": "pivot", "pivot": {"rows": rows, "columns": col, "values": val, "agg": agg}}

    xs = cols(viz.get("x"))
    if not xs:
        xs = [next((n for n, c in names.items() if n not in numeric), next(iter(names)))]
    if len(xs) > 2 or any(x not in names for x in xs):
        raise QueryError(f"Chart X must be one or two result columns: {', '.join(names)}.")
    ys = [y for y in cols(viz.get("y")) if y not in xs]
    if not ys:
        ys = [n for n in numeric if n not in xs][:1]
    bad = [y for y in ys if y not in numeric]
    if not ys or bad:
        raise QueryError(f"Chart Y must be numeric result columns; problem with: {', '.join(bad) or 'none'}.")
    series = str(viz.get("series") or "").lower() or None
    if series and (series not in names or series in xs or series in numeric):
        raise QueryError("Series must be a non-numeric column that is not the X column.")
    if vtype in SINGLE_SERIES:
        ys, series, xs = ys[:1], None, xs[:1]
    if series:
        ys = ys[:1]
    return {
        "type": vtype, "x": xs, "y": ys[:6], "series": series,
        "stacked": bool(viz.get("stacked")) and vtype in ("bar", "area", "line"),
    }


# --------------------------------------------------------------------------------------
# Server-side SVG (PDF exports and scheduled e-mails)
# --------------------------------------------------------------------------------------

def chart_data(result, viz, max_points=40):
    """Return (labels, [(name, values)]) in the same shape the browser chart uses."""
    idx = {c["fieldname"]: i for i, c in enumerate(result["columns"])}
    label_of = {c["fieldname"]: c["label"] for c in result["columns"]}
    rows = result["rows"]

    def xlabel(r):
        return "-".join("" if r[idx[x]] is None else str(r[idx[x]]) for x in viz["x"])

    if viz.get("series"):
        s_i, y_i = idx[viz["series"]], idx[viz["y"][0]]
        labels, series = [], {}
        for r in rows:
            lab = xlabel(r)
            if lab not in labels:
                labels.append(lab)
            series.setdefault(str(r[s_i]), {})[lab] = _f(r[y_i])
        labels = labels[:max_points]
        data = [(name, [vals.get(lab, 0) for lab in labels]) for name, vals in list(series.items())[:10]]
        return labels, data

    rows = rows[:max_points]
    labels = [xlabel(r) for r in rows]
    data = [(label_of[y], [_f(r[idx[y]]) for r in rows]) for y in viz["y"]]
    return labels, data


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def svg_chart(result, viz, width=720, height=300):
    if not viz or viz.get("type") not in CHART_TYPES or not result["rows"]:
        return ""
    labels, data = chart_data(result, viz)
    if not labels or not data:
        return ""
    esc = html.escape
    if viz["type"] in SINGLE_SERIES:
        return _svg_pie(labels, data[0][1], width, height, donut=viz["type"] != "pie")

    pad_l, pad_r, pad_t, pad_b = 60, 16, 16, 60
    w, h = width - pad_l - pad_r, height - pad_t - pad_b
    stacked = viz.get("stacked")
    if stacked:
        top = max([sum(v[i] for _, v in data) for i in range(len(labels))] + [0])
    else:
        top = max([max(v) for _, v in data] + [0])
    low = min([min(v) for _, v in data] + [0])
    span = (top - low) or 1
    y = lambda v: pad_t + h - (v - low) / span * h  # noqa: E731
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="Arial" font-size="10">']
    for k in range(5):
        val = low + span * k / 4
        yy = y(val)
        parts.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{pad_l - 6}" y="{yy + 3:.1f}" text-anchor="end" fill="#6b7280">{_short(val)}</text>')
    n = len(labels)
    step = w / max(n, 1)
    if viz["type"] == "bar":
        groups = 1 if stacked else len(data)
        bw = step * 0.7 / groups
        base_acc = [0.0] * n
        for si, (_, vals) in enumerate(data):
            for i, v in enumerate(vals):
                if stacked:
                    y0, y1 = y(base_acc[i]), y(base_acc[i] + v)
                    base_acc[i] += v
                    x = pad_l + i * step + step * 0.15
                else:
                    y0, y1 = y(0), y(v)
                    x = pad_l + i * step + step * 0.15 + si * bw
                top_y, hh = min(y0, y1), abs(y0 - y1)
                parts.append(f'<rect x="{x:.1f}" y="{top_y:.1f}" width="{bw:.1f}" height="{hh:.1f}" fill="{PALETTE[si % 10]}"/>')
    else:
        for si, (_, vals) in enumerate(data):
            pts = " ".join(f"{pad_l + i * step + step / 2:.1f},{y(v):.1f}" for i, v in enumerate(vals))
            if viz["type"] == "area":
                first = pad_l + step / 2
                last = pad_l + (n - 1) * step + step / 2
                parts.append(f'<polygon points="{first:.1f},{y(0):.1f} {pts} {last:.1f},{y(0):.1f}" fill="{PALETTE[si % 10]}" fill-opacity="0.15"/>')
            parts.append(f'<polyline points="{pts}" fill="none" stroke="{PALETTE[si % 10]}" stroke-width="2"/>')
    every = max(1, math.ceil(n / 14))
    for i, lab in enumerate(labels):
        if i % every:
            continue
        x = pad_l + i * step + step / 2
        parts.append(
            f'<text x="{x:.1f}" y="{height - pad_b + 14}" text-anchor="end" transform="rotate(-35 {x:.1f} {height - pad_b + 14})" fill="#374151">{esc(_trim(lab))}</text>'
        )
    if len(data) > 1:
        lx = pad_l
        for si, (name, _) in enumerate(data):
            parts.append(f'<rect x="{lx}" y="{height - 12}" width="10" height="10" fill="{PALETTE[si % 10]}"/>')
            parts.append(f'<text x="{lx + 14}" y="{height - 3}" fill="#374151">{esc(_trim(name, 18))}</text>')
            lx += 130
    parts.append("</svg>")
    return "".join(parts)


def _svg_pie(labels, values, width, height, donut):
    esc = html.escape
    pairs = sorted(zip(labels, values), key=lambda p: -p[1])
    if len(pairs) > 10:
        pairs = pairs[:9] + [("Other", sum(v for _, v in pairs[9:]))]
    total = sum(max(v, 0) for _, v in pairs) or 1
    cx, cy, r = height / 2, height / 2, height / 2 - 10
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="Arial" font-size="11">']
    angle = -math.pi / 2
    for i, (lab, v) in enumerate(pairs):
        frac = max(v, 0) / total
        if frac <= 0:
            continue
        a2 = angle + frac * 2 * math.pi
        large = 1 if frac > 0.5 else 0
        x1, y1 = cx + r * math.cos(angle), cy + r * math.sin(angle)
        x2, y2 = cx + r * math.cos(a2), cy + r * math.sin(a2)
        if frac >= 0.9999:
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{PALETTE[i % 10]}"/>')
        else:
            parts.append(
                f'<path d="M{cx},{cy} L{x1:.1f},{y1:.1f} A{r},{r} 0 {large} 1 {x2:.1f},{y2:.1f} Z" fill="{PALETTE[i % 10]}"/>'
            )
        angle = a2
        ly = 20 + i * 20
        parts.append(f'<rect x="{height + 20}" y="{ly - 9}" width="11" height="11" fill="{PALETTE[i % 10]}"/>')
        parts.append(f'<text x="{height + 36}" y="{ly}" fill="#374151">{esc(_trim(lab, 30))} ({frac * 100:.1f}%)</text>')
    if donut:
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r * 0.55:.1f}" fill="#fff"/>')
    parts.append("</svg>")
    return "".join(parts)


def _short(v):
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:.1f}B"
    if a >= 1e6:
        return f"{v / 1e6:.1f}M"
    if a >= 1e3:
        return f"{v / 1e3:.1f}K"
    return f"{v:.0f}" if a >= 10 else f"{v:.1f}"


def _trim(s, n=16):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"
