import json

from neotec_ai.platform import compress, router, shield


# ---------------------------------------------------------------- shield
def test_mask_roundtrip_and_stable_placeholders():
    text = "Mail ali@example.com or call 0551234567; IBAN SA0380000000608010167519; again ali@example.com"
    masked, vault = shield.mask(text)
    assert "ali@example.com" not in masked and "0551234567" not in masked and "SA038" not in masked
    assert masked.count("\u27e6EMAIL_1\u27e7") == 2
    assert shield.unmask(masked, vault) == text


def test_mask_shared_vault_and_no_double_masking():
    v = {}
    a, v = shield.mask("ali@example.com", v)
    b, v = shield.mask(a + " and sara@example.com", v)
    assert b == "\u27e6EMAIL_1\u27e7 and \u27e6EMAIL_2\u27e7"
    assert shield.unmask(b, v) == "ali@example.com and sara@example.com"


def test_card_needs_luhn():
    masked, _ = shield.mask("card 4111 1111 1111 1111 ref 1234 5678 9012 3456")
    assert "CARD_1" in masked and "1234 5678 9012 3456" in masked


def test_unmask_obj_tool_arguments():
    _m, v = shield.mask("ali@example.com")
    assert shield.unmask_obj({"to": ["\u27e6EMAIL_1\u27e7"]}, v) == {"to": ["ali@example.com"]}


# ---------------------------------------------------------------- compress
ROWS = [{"name": f"SINV-2026-{i:05d}", "customer": "Al Noor Trading", "grand_total": 1000 + i * 3.5,
         "status": "Unpaid"} for i in range(30)]


def test_json_tables_lossless_and_smaller():
    text = json.dumps({"rows": ROWS}, indent=1)
    out = compress.compress_text(text)
    assert len(out) < len(text) * 0.6
    body = json.loads(out[out.index("{"):])
    assert compress.decode(body) == {"rows": ROWS}


def test_fidelity_gate_rejects_lost_numbers():
    assert not compress.faithful("total 1,250.00 SAR", "total SAR")
    assert compress.faithful("Error: refused by policy\ntotal 5", "total 5\nError: refused by policy")


def test_supersede_keeps_latest_result():
    call = {"id": "a", "name": "get_document", "arguments": {"doctype": "Customer", "name": "X"}}
    call2 = {**call, "id": "b"}
    msgs = [{"role": "user", "content": "q"},
            {"role": "assistant", "content": "", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": "a", "name": "get_document", "content": "x" * 300},
            {"role": "assistant", "content": "", "tool_calls": [call2]},
            {"role": "tool", "tool_call_id": "b", "name": "get_document", "content": "y" * 300}]
    out = compress.supersede(msgs)
    assert out[2]["content"].startswith("[Superseded") and out[4]["content"] == "y" * 300


def test_compress_messages_never_touches_last_user():
    big = json.dumps(ROWS)
    msgs = [{"role": "user", "content": big}, {"role": "assistant", "content": "ok"},
            {"role": "user", "content": big}]
    out, saved = compress.compress_messages(msgs, "Lossless")
    assert out[-1]["content"] == big and saved > 0


# ---------------------------------------------------------------- router
P = [{"name": "ext", "enabled": 1, "data_location": "External"},
     {"name": "ksa", "enabled": 1, "data_location": "In Kingdom (KSA)"},
     {"name": "prem", "enabled": 1, "data_location": "On-Premises", "supports_vision": 1}]


def test_route_resolution_order():
    idx = router.build_index([{"name": "Default"}, {"name": "CRM", "used_by": "crm_app"},
                              {"name": "Spell", "used_by": "crm_app:spell_check"}, {"name": "Writing"}])
    assert router.pick_route(idx, "crm_app", "spell_check")["name"] == "Spell"
    assert router.pick_route(idx, "crm_app", "brief")["name"] == "CRM"
    assert router.pick_route(idx, "other", "x", "Writing")["name"] == "Writing"
    assert router.pick_route(idx, "other")["name"] == "Default"


def test_chain_is_residency_monotonic():
    chain, skipped = router.order_chain([P[1], P[0], P[2]], residency_mode="Guarded")
    assert [p["name"] for p in chain] == ["ksa", "prem"]
    assert ("ext", "fallback would move data further away") in skipped


def test_strict_and_sensitive():
    chain, _ = router.order_chain(P, residency_mode="Strict")
    assert [p["name"] for p in chain] == ["ksa", "prem"]
    chain, _ = router.order_chain(P, residency_mode="Guarded", sensitive=True)
    assert chain[0]["name"] == "ksa"
    chain, _ = router.order_chain(P, residency_mode="Open", sensitive=True)
    assert chain[0]["name"] == "ext"


def test_cooldown_moves_to_end_and_vision_filter():
    chain, _ = router.order_chain(P, residency_mode="Open", cooled={"ext": 1})
    assert [p["name"] for p in chain] == ["ksa", "prem", "ext"]
    chain, _ = router.order_chain(P, residency_mode="Open", need_vision=True)
    assert [p["name"] for p in chain] == ["prem"]
    assert router.cooldown_seconds(1) == 30 and router.cooldown_seconds(99) == 3600
    assert router.within(0, 10**9) and not router.within(10, 9, 2)
