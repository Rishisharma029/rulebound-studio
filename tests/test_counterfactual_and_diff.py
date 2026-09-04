from pathlib import Path

from rulebound.api import app, DATA_DIR
from rulebound.counterexample import build_scenario_placements
from rulebound.counterfactual import explain_all_counterfactuals, explain_counterfactual
from rulebound.layout_diff import diff_layouts
from rulebound.loader import load_asset_pack
from fastapi.testclient import TestClient

PACK = load_asset_pack(DATA_DIR)


def test_counterfactual_why_not_layout_a():
    room = PACK.rooms_by_id["ROOM-01"]
    card = explain_counterfactual(room, PACK, "Candidate A")
    assert card["headline"] == "Why not Candidate A?"
    assert card["selected"]["candidate_id"] == "Candidate B"
    assert card["rejected"]["candidate_id"] == "Candidate A"
    assert card["selected"]["score"] == 94.1
    assert card["rejected"]["score"] == 91.4
    assert any("circulation" in b.lower() for b in card["rejection_bullets"])
    assert any("valid" in r.lower() for r in card["selection_reasons"])
    assert "Candidate A rejected" in card["ascii_card"]
    assert "Candidate B selected because" in card["ascii_card"]


def test_counterfactual_all_alternatives():
    room = PACK.rooms_by_id["ROOM-01"]
    bundle = explain_all_counterfactuals(room, PACK)
    assert bundle["selected_candidate_id"] == "Candidate B"
    assert set(bundle["explanations_by_id"]) == {"Candidate A", "Candidate C"}
    c = bundle["explanations_by_id"]["Candidate C"]
    assert c["deltas"]["accessibility_margin_violations"] >= 1 or c["deltas"]["accessibility_pct"] < 0


def test_layout_diff_egress_repair_story():
    room = PACK.rooms_by_id["ROOM-01"]
    before = build_scenario_placements(room, PACK, "egress")
    # After: shift the obstructing desk away from the south corridor
    after = []
    for p in before:
        if p.placement_id == "P001":
            after.append(type(p)(p.placement_id, p.sku, p.finish_id, 3000.0, 1800.0, p.rotation_deg))
        else:
            after.append(p)
    report = diff_layouts(room, PACK, before, after, reason_hint="RB-GEO-002")
    assert report["moved"]
    hero = report["headline_move"]
    assert hero["placement_id"] == "P001"
    assert hero["before"]["x_mm"] == 2000.0
    assert hero["after"]["x_mm"] == 3000.0
    assert report["reason"]["rule_id"] == "RB-GEO-002"
    assert "egress" in report["reason"]["text"].lower()
    assert "Φ" in report["energy"]["transition"]
    assert "WHAT CHANGED?" in report["ascii_card"]


def test_counterfactual_and_diff_api():
    client = TestClient(app)
    r = client.get("/api/v1/room/ROOM-01/counterfactual", params={"rejected": "Candidate A"})
    assert r.status_code == 200
    data = r.json()
    assert data["selected"]["candidate_id"] == "Candidate B"

    before = [
        {"placement_id": "P001", "sku": "NW-DES-003", "finish_id": "F03", "x_mm": 2100.0, "y_mm": 1800.0, "rotation_deg": 0.0},
        {"placement_id": "P002", "sku": "NW-DES-003", "finish_id": "F03", "x_mm": 4000.0, "y_mm": 3000.0, "rotation_deg": 0.0},
    ]
    after = [
        {"placement_id": "P001", "sku": "NW-DES-003", "finish_id": "F03", "x_mm": 3000.0, "y_mm": 1800.0, "rotation_deg": 0.0},
        {"placement_id": "P002", "sku": "NW-DES-003", "finish_id": "F03", "x_mm": 4000.0, "y_mm": 3000.0, "rotation_deg": 0.0},
    ]
    d = client.post("/api/v1/layout/diff", json={"room_id": "ROOM-01", "before": before, "after": after})
    assert d.status_code == 200
    body = d.json()
    assert body["moved"][0]["placement_id"] == "P001"
    assert body["moved"][0]["before"]["x_mm"] == 2100.0
    assert body["moved"][0]["after"]["x_mm"] == 3000.0


def test_room_data_includes_counterfactual():
    client = TestClient(app)
    resp = client.get("/api/v1/room/ROOM-01/data")
    assert resp.status_code == 200
    data = resp.json()
    assert "counterfactual" in data
    assert data["counterfactual"]["selected_candidate_id"] == "Candidate B"
