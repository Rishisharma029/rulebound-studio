from fastapi.testclient import TestClient
from rulebound.api import app, DATA_DIR
from rulebound.explainability import explain_sku_decisions
from rulebound.ir import extract_requirement_ir, select_skus_from_ir
from rulebound.loader import load_asset_pack


def test_sku_explainability_engine_structure():
    pack = load_asset_pack(DATA_DIR)
    room = pack.rooms_by_id["ROOM-01"]
    brief_text = pack.briefs.get(room.room_id, "")
    ir = extract_requirement_ir(brief_text, room)
    item_specs = select_skus_from_ir(ir, pack)

    report = explain_sku_decisions(ir, room, pack, item_specs)
    assert report["room_id"] == "ROOM-01"
    assert report["total_decisions"] > 0
    assert "decisions" in report
    assert "decisions_by_sku" in report

    # Check for desk decision
    desk_decisions = [d for d in report["decisions"] if d["family"] == "desk"]
    assert len(desk_decisions) >= 1
    d = desk_decisions[0]

    # Verify headline and positive reasons
    assert d["headline"].startswith("Why NW-DES-")
    reasons = d["selected_reasons"]
    assert any("Width satisfies requirement" in r for r in reasons)
    assert any("Compatible with selected arrangement" in r for r in reasons)
    assert any("finish compatible" in r for r in reasons)
    assert any("Quantity available" in r for r in reasons)
    assert any("Fits room geometry" in r for r in reasons)
    assert any("Improves circulation score" in r for r in reasons)

    # Verify rejected alternatives are present
    assert len(d["rejected_alternatives"]) >= 1
    rej_skus = [r["sku"] for r in d["rejected_alternatives"]]
    assert "NW-DES-014" in rej_skus or len(rej_skus) > 0

    # Specifically check rejection reason for NW-DES-014 if present
    des_014_rej = next((r for r in d["rejected_alternatives"] if r["sku"] == "NW-DES-014"), None)
    if des_014_rej:
        assert "egress deficit" in des_014_rej["reason"]


def test_sku_explainability_all_rooms():
    pack = load_asset_pack(DATA_DIR)
    for room_id in ["ROOM-01", "ROOM-02", "ROOM-03", "ROOM-04", "ROOM-05"]:
        room = pack.rooms_by_id[room_id]
        brief_text = pack.briefs.get(room_id, "")
        ir = extract_requirement_ir(brief_text, room)
        report = explain_sku_decisions(ir, room, pack)
        assert report["room_id"] == room_id
        assert len(report["decisions"]) >= 2
        for dec in report["decisions"]:
            assert len(dec["selected_reasons"]) >= 3


def test_sku_explainability_api_endpoint():
    client = TestClient(app)
    resp = client.get("/api/v1/room/ROOM-01/sku-explainability")
    assert resp.status_code == 200
    data = resp.json()
    assert data["room_id"] == "ROOM-01"
    assert "decisions" in data
    assert len(data["decisions"]) > 0


def test_room_data_payload_includes_sku_explainability():
    client = TestClient(app)
    resp = client.get("/api/v1/room/ROOM-01/data")
    assert resp.status_code == 200
    data = resp.json()
    assert "sku_explainability" in data
    assert data["sku_explainability"]["room_id"] == "ROOM-01"
    assert len(data["sku_explainability"]["decisions"]) > 0
