"""Prompt text describing the BI query and visualization formats (shared by chat and the builder AI)."""

from neotec_ai.bi.engine import AGGS, DATE_PARTS, TIMESPANS

QUERY_FORMAT = f"""## Query format (JSON)
{{
  "source": "<DocType from the dictionary>",
  "joins": [{{"doctype": "<DocType>", "from": "<DocType already in the query>", "via": "<field shown in the dictionary 'join ->' lines>", "type": "left|inner"}}],
  "columns": [
    {{"field": "<DocType>.<field>", "label": "<optional>"}},
    {{"field": "<DocType>.<date field>", "date_part": "year_month", "alias": "month"}},
    {{"field": "<DocType>.<numeric field>", "agg": "sum", "alias": "revenue", "label": "Revenue"}},
    {{"field": "*", "agg": "count", "alias": "orders"}},
    {{"formula": "revenue / orders", "alias": "avg_order", "label": "Average Order"}}
  ],
  "filters": [{{"field": "<DocType>.<field>", "op": "<operator>", "value": <value>}}],
  "having": [{{"column": "<alias of an aggregated column>", "op": ">", "value": 1000}}],
  "order_by": [{{"column": "<alias>", "dir": "desc"}}],
  "limit": 50
}}
Rules:
- Use only DocTypes/fields listed in the dictionary; write fields as "DocType.field".
- Join only along the "join ->" relationships listed (child tables via their table field, line items back to the parent via "parent", links via the link field). Each DocType at most once.
- agg: {", ".join(AGGS)}. When any column is aggregated, all other non-formula columns become the grouping.
- date_part (Date/Datetime fields only): {", ".join(DATE_PARTS)}. Use year_month for monthly trends.
- operators: =, !=, >, <, >=, <=, like, not like, in, not in, between ([from, to]), is ("set"/"not set"), timespan.
- timespan values: {", ".join(TIMESPANS)}. Dates are "YYYY-MM-DD".
- formula: arithmetic on earlier column aliases (+ - * / round abs min max). having: filters on aggregated aliases.
- order_by uses column aliases (field name is the alias when none is given). Prefer aggregation over raw rows.
- If a result says permission denied, tell the user they lack access to that data; do not try to work around it."""

VIZ_FORMAT = """## Visualization format (JSON)
{"type": "table|bar|line|area|pie|donut|percentage|number|pivot",
 "x": ["<label column alias>"] (1-2), "y": ["<numeric alias>", ...], "series": "<optional category alias to split lines/bars>", "stacked": false,
 "column": "<numeric alias>" (number card), "agg": "sum|first|avg" (number card), "prefix": "", "suffix": "",
 "pivot": {"rows": ["<alias>"], "columns": "<alias>", "values": "<numeric alias>", "agg": "sum"}}
- line/area for trends over time; bar for comparing categories; pie/donut/percentage for shares (one y, <= 12 slices);
  number for a single KPI; pivot for a cross-tab (e.g. rows = customer, columns = month); table for detailed lists."""
