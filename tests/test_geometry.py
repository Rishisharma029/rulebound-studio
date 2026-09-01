from __future__ import annotations

from pathlib import Path
import pytest

from rulebound.geometry import (
    distance_polygon_to_segment,
    distance_polygon_to_walls,
    get_door_geometry,
    get_door_swing_polygon,
    get_placement_polygon,
    point_in_polygon,
    polygon_fully_inside_room,
    polygons_intersect,
)
from rulebound.loader import load_asset_pack
from rulebound.models import Placement

ROOT = Path(__file__).resolve().parents[1]
PACK = load_asset_pack(ROOT / "RuleBound_Round1_Release/data")


def test_point_in_polygon():
    poly = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0), (0.0, 1000.0)]
    assert point_in_polygon((500.0, 500.0), poly) is True
    assert point_in_polygon((1500.0, 500.0), poly) is False


def test_polygons_intersect_sat():
    poly1 = [(0.0, 0.0), (500.0, 0.0), (500.0, 500.0), (0.0, 500.0)]
    poly2 = [(400.0, 0.0), (900.0, 0.0), (900.0, 500.0), (400.0, 500.0)]
    poly3 = [(600.0, 0.0), (1100.0, 0.0), (1100.0, 500.0), (600.0, 500.0)]

    # Overlap between poly1 and poly2
    inter, depth, _ = polygons_intersect(poly1, poly2)
    assert inter is True
    assert depth > 0.0

    # No overlap between poly1 and poly3
    inter, depth, _ = polygons_intersect(poly1, poly3)
    assert inter is False


def test_wall_distance_and_offset():
    room_poly = [(0.0, 0.0), (5000.0, 0.0), (5000.0, 5000.0), (0.0, 5000.0)]
    item_poly_near = [(50.0, 50.0), (450.0, 50.0), (450.0, 450.0), (50.0, 450.0)]
    item_poly_far = [(200.0, 200.0), (600.0, 200.0), (600.0, 600.0), (200.0, 600.0)]

    assert distance_polygon_to_walls(item_poly_near, room_poly) < 100.0
    assert distance_polygon_to_walls(item_poly_far, room_poly) >= 100.0


def test_polygon_to_polygon_distance():
    from rulebound.geometry import distance_polygon_to_polygon
    poly1 = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0), (0.0, 1000.0)]
    poly2 = [(2000.0, 0.0), (3000.0, 0.0), (3000.0, 1000.0), (2000.0, 1000.0)]
    dist = distance_polygon_to_polygon(poly1, poly2)
    assert abs(dist - 1000.0) < 1e-4


def test_spatial_constraints_all_8_rules_executable():
    from rulebound.constraints import verify_spatial_constraints, audit_spatial_constraints
    room = PACK.rooms_by_id["ROOM-01"]
    
    # Create valid placements
    placements = [
        Placement("P001", "NW-DES-003", "F03", 2720.0, 120.0, 0.0),
        Placement("P002", "NW-DES-003", "F03", 4320.0, 120.0, 0.0),
    ]
    violations = verify_spatial_constraints(room, placements, PACK)
    assert len(violations) == 0

    # Audit returns all 8 rules with explicit measurements
    audit = audit_spatial_constraints(room, placements, PACK)
    assert len(audit) == 8
    rule_ids = [a["rule_id"] for a in audit]
    assert rule_ids == [
        "RB-GEO-001", "RB-GEO-002", "RB-GEO-003", "RB-GEO-004",
        "RB-GEO-005", "RB-GEO-006", "RB-GEO-007", "RB-GEO-008"
    ]
    for a in audit:
        assert a["status"] == "PASS"
        assert "measured" in a
        assert "margin" in a

