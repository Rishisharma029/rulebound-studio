from fastapi.testclient import TestClient
from rulebound.api import app, DATA_DIR
from rulebound.generator import LayoutGenerator
from rulebound.arbitration import ArbitrationEngine
from rulebound.ir import extract_requirement_ir
from rulebound.loader import load_asset_pack
from rulebound.traceability import build_traceability_matrix


def test_traceability_matrix_lifecycle_stages():
    pack = load_asset_pack(DATA_DIR)
    room = pack.rooms_by_id["ROOM-01"]
    brief_text = pack.briefs.get(room.room_id, "")
    ir = extract_requirement_ir(brief_text, room)

    generator = LayoutGenerator()
    placements = generator.generate_candidate_layout(room, pack)
    arbitrator = ArbitrationEngine()
    layout_res = arbitrator.arbitrate(room, placements, pack)

    rtm = build_traceability_matrix(ir, layout_res.placements, room, pack, brief_text)
    assert rtm.room_id == "ROOM-01"
    assert len(rtm.entries) == 7

    req_ids = [e.req_id for e in rtm.entries]
    assert req_ids == [
        "REQ-001",
        "REQ-002",
        "REQ-003",
        "REQ-004",
        "REQ-005",
        "REQ-006",
        "REQ-007",
    ]

    # Verify REQ-001 has full 6-stage lifecycle
    req_001 = rtm.entries[0]
    assert req_001.name == "Occupancy"
    assert "✅" in req_001.score_display
    assert req_001.status == "PASS"

    stages = req_001.stages
    assert "team" in stages.brief_requirement or "capacity" in stages.brief_requirement.lower()
    assert stages.ir_expression.startswith("occupancy =")
    assert "chairs" in stages.catalog_allocation
    assert "placed" in stages.layout_placement
    assert "PASS" in stages.verification_status
    assert "requirement satisfied" in stages.output_satisfaction


def test_traceability_matrix_human_readable_text_table():
    pack = load_asset_pack(DATA_DIR)
    room = pack.rooms_by_id["ROOM-01"]
    brief_text = pack.briefs.get(room.room_id, "")
    ir = extract_requirement_ir(brief_text, room)

    generator = LayoutGenerator()
    placements = generator.generate_candidate_layout(room, pack)
    arbitrator = ArbitrationEngine()
    layout_res = arbitrator.arbitrate(room, placements, pack)

    rtm = build_traceability_matrix(ir, layout_res.placements, room, pack, brief_text)
    table_text = rtm.to_text_table()

    assert "Requirement Traceability" in table_text
    assert "REQ-001 Occupancy" in table_text
    assert "REQ-002 Desks" in table_text
    assert "REQ-003 Seating" in table_text
    assert "REQ-004 Storage" in table_text
    assert "REQ-005 Collaboration" in table_text
    assert "REQ-006 Finish preference" in table_text
    assert "REQ-007 Openness" in table_text


def test_traceability_all_rooms():
    pack = load_asset_pack(DATA_DIR)
    for room_id in ["ROOM-01", "ROOM-02", "ROOM-03", "ROOM-04", "ROOM-05"]:
        room = pack.rooms_by_id[room_id]
        brief_text = pack.briefs.get(room_id, "")
        ir = extract_requirement_ir(brief_text, room)
        generator = LayoutGenerator()
        placements = generator.generate_candidate_layout(room, pack)

        rtm = build_traceability_matrix(ir, placements, room, pack, brief_text)
        assert len(rtm.entries) == 7
        assert rtm.overall_satisfaction_pct >= 90.0


def test_traceability_api_endpoint():
    client = TestClient(app)
    resp = client.get("/api/v1/room/ROOM-01/traceability")
    assert resp.status_code == 200
    data = resp.json()
    assert data["room_id"] == "ROOM-01"
    assert data["total_requirements"] == 7
    assert "text_table" in data
    assert "requirements" in data
    assert len(data["requirements"]) == 7
