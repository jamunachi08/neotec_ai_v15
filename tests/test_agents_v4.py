import json

from neotec_ai.agents.engine import shape, toolsearch

SPECS = [{"name": n, "description": d, "category": c} for n, d, c in [
    ("receivables_ageing", "Customer receivables by age bucket", "Finance"),
    ("stock_levels", "Stock balance per warehouse", "Stock"),
    ("vat_return_check", "Check the ZATCA VAT return boxes", "KSA Compliance"),
    ("eosb_calculator", "End of service benefit under Saudi labour law", "KSA Compliance"),
] + [(f"tool_{i}", "misc", "Data") for i in range(30)]]


def test_split_threshold():
    specs, on_demand = toolsearch.split(SPECS, [], 20)
    assert on_demand and specs[-1]["name"] == "find_tools" and len(specs) < 20
    specs, on_demand = toolsearch.split(SPECS[:5], [], 20)
    assert not on_demand and len(specs) == 5
    specs, _ = toolsearch.split(SPECS, ["vat_return_check"], 20)
    assert "vat_return_check" in [s["name"] for s in specs]


def test_rank_finds_relevant_tools():
    assert toolsearch.rank("overdue receivables by age", SPECS)[0]["name"] == "receivables_ageing"
    assert toolsearch.rank("end of service", SPECS)[0]["name"] == "eosb_calculator"
    assert toolsearch.rank("the of", SPECS) == []


def test_fit_keeps_whole_rows():
    rows = [{"name": f"PO-{i:05d}", "supplier": "Gulf Steel", "amount": i * 10} for i in range(400)]
    out = shape.fit({"status": "ok", "result": {"rows": rows}}, 3000)
    assert len(out) <= 3200
    if out.startswith("{"):
        data = json.loads(out)
        assert "_omitted" in data
    small = shape.fit({"status": "ok", "result": {"n": 1}}, 3000)
    assert json.loads(small) == {"status": "ok", "result": {"n": 1}}
