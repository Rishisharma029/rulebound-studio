from pathlib import Path
from rulebound.generator import LayoutGenerator, parse_brief_requirements
from rulebound.loader import load_asset_pack
from rulebound.models import RoomSpec, DoorSpec, EgressSpec

ROOT = Path(__file__).resolve().parents[1]
PACK = load_asset_pack(ROOT / "RuleBound_Round1_Release/data")


def test_brief_parser_on_benchmark_briefs():
    for f in sorted((ROOT / "RuleBound_Round1_Release/data/briefs").glob("*.txt")):
        room_id = f.stem
        room = PACK.rooms_by_id[room_id]
        brief_text = f.read_text(encoding="utf-8")
        
        # Test brief parsing without room ID branching
        item_specs = parse_brief_requirements(brief_text, room, PACK)
        assert len(item_specs) > 0
        total_items = sum(count for _, _, count in item_specs)
        assert total_items >= room.capacity


def test_brief_parser_on_arbitrary_custom_brief():
    # Test on an arbitrary custom client brief completely independent of benchmark IDs
    custom_room = RoomSpec(
        room_id="CUSTOM-ROOM-99",
        name="Apex Innovation Lab",
        boundary_mm=[(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0), (0.0, 6000.0)],
        doors=[DoorSpec("D01", "south", 1000.0, 900.0, "left_inward")],
        windows=[],
        egress=EgressSpec("D01", (4000.0, 3000.0), 1100.0),
        capacity=12,
    )
    
    custom_brief = "Create a 12-person product-design studio with paired desks, ergonomic chairs, two lockable storage units, one compact collaboration table. Prefer natural oak and graphite."
    
    generator = LayoutGenerator()
    item_specs = parse_brief_requirements(custom_brief, custom_room, PACK)
    assert len(item_specs) == 4
    
    # Verify exact item families parsed from plain English
    families = [PACK.catalog_by_sku[sku].family for sku, _, _ in item_specs]
    assert "desk" in families
    assert "chair" in families
    assert "collaboration" in families
    assert "storage" in families
    
    # Generate layout for arbitrary room
    placements = generator._solve_spatial_layout(custom_room, item_specs, PACK)
    assert len(placements) > 0


def test_requirement_satisfaction_7_metrics_scoring():
    from rulebound.ir import extract_requirement_ir, evaluate_requirement_satisfaction

    custom_room = RoomSpec(
        room_id="CUSTOM-ROOM-SCORE",
        name="Scoring Test Room",
        boundary_mm=[(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0), (0.0, 6000.0)],
        doors=[DoorSpec("D01", "south", 1000.0, 900.0, "left_inward")],
        windows=[],
        egress=EgressSpec("D01", (4000.0, 3000.0), 1100.0),
        capacity=6,
    )
    brief_text = "Accommodate 6 team members with 6 workstations, 6 chairs, 2 storage credenzas, and 1 collaboration table. Prefer natural oak."
    ir = extract_requirement_ir(brief_text, custom_room)

    generator = LayoutGenerator()
    item_specs = parse_brief_requirements(brief_text, custom_room, PACK)
    placements = generator._solve_spatial_layout(custom_room, item_specs, PACK)

    satisfaction = evaluate_requirement_satisfaction(ir, placements, custom_room, PACK)

    # 1. Exactly 7 orthogonal metrics reported
    assert len(satisfaction["metrics"]) == 7
    expected_keys = {
        "occupancy",
        "desk_requirement",
        "chair_requirement",
        "storage_requirement",
        "collaboration",
        "finish_preference",
        "openness_score",
    }
    assert set(satisfaction["metrics"].keys()) == expected_keys

    # 2. Mathematical consistency: overall_percentage is the exact average of all 7 metrics
    metric_values = [float(v.rstrip("%")) for v in satisfaction["metrics"].values()]
    assert len(metric_values) == 7
    expected_overall = round(sum(metric_values) / 7.0, 1)
    assert satisfaction["overall_percentage"] == expected_overall

