"""
RuleBound 16-Test Adversarial Matrix (8 Rules x 2 Directions)
Proves that every single spatial rule:
  1. Genuinely FAILS and detects violations when an invariant is breached.
  2. Genuinely PASSES when the layout complies with the invariant.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from rulebound.constraints import verify_spatial_constraints
from rulebound.loader import load_asset_pack
from rulebound.models import Placement

ROOT = Path(__file__).resolve().parents[1]
PACK = load_asset_pack(ROOT / "RuleBound_Round1_Release/data")
ROOM = PACK.rooms_by_id["ROOM-01"]


# ---------------------------------------------------------------------------
# RULE 1: RB-GEO-001 (Primary Walkway Clearance >= 900mm)
# ---------------------------------------------------------------------------

def test_walkway_violation():
    """RB-GEO-001 FAIL: Two workstation clusters placed with only 400mm walkway gap (<900mm)."""
    # Desks are 1400w x 800d. Cluster 1 at X=2500, Y=1500 (bounds X: [2500, 3900], Y: [1500, 2300]).
    # Cluster 2 placed at X=2500, Y=2700 (gap in Y = 2700 - 2300 = 400mm < 900mm).
    placements = [
        Placement("P001", "NW-DES-003", "F03", 2500.0, 1500.0, 0.0),
        Placement("P002", "NW-DES-003", "F03", 2500.0, 2700.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert any(v.rule_id == "RB-GEO-001" for v in violations)
    v = next(v for v in violations if v.rule_id == "RB-GEO-001")
    assert v.measured["walkway_width_mm"] < 900.0


def test_walkway_valid():
    """RB-GEO-001 PASS: Two workstation clusters placed with 1200mm walkway gap (>=900mm)."""
    # Cluster 1 at Y=1200 (Y bounds [1200, 2000]). Cluster 2 at Y=3200 (Y bounds [3200, 4000]). Gap = 1200mm.
    placements = [
        Placement("P001", "NW-DES-003", "F03", 2500.0, 1200.0, 0.0),
        Placement("P002", "NW-DES-003", "F03", 2500.0, 3200.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert not any(v.rule_id == "RB-GEO-001" for v in violations)


# ---------------------------------------------------------------------------
# RULE 2: RB-GEO-002 (Life-Safety Egress Corridor >= 1100mm total / 550mm half)
# ---------------------------------------------------------------------------

def test_egress_violation():
    """RB-GEO-002 FAIL: Desk placed directly obstructing door-to-presentation exit path."""
    placements = [
        Placement("P001", "NW-DES-003", "F03", 2000.0, 100.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert any(v.rule_id == "RB-GEO-002" for v in violations)
    v = next(v for v in violations if v.rule_id == "RB-GEO-002")
    assert v.measured["corridor_distance_mm"] < 550.0


def test_egress_valid():
    """RB-GEO-002 PASS: Placement clear of egress path (>550mm half-width corridor)."""
    placements = [
        Placement("P001", "NW-DES-003", "F03", 4500.0, 2000.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert not any(v.rule_id == "RB-GEO-002" for v in violations)


# ---------------------------------------------------------------------------
# RULE 3: RB-GEO-003 (Door Swing Arc Clearance >= 850mm radius)
# ---------------------------------------------------------------------------

def test_door_swing_violation():
    """RB-GEO-003 FAIL: Chair placed inside 850mm door swing quadrant."""
    placements = [
        Placement("P001", "NW-CHA-004", "F15", 700.0, 200.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert any(v.rule_id == "RB-GEO-003" for v in violations)
    v = next(v for v in violations if v.rule_id == "RB-GEO-003")
    assert v.measured["swing_encroachment_mm"] > 0.0


def test_door_swing_valid():
    """RB-GEO-003 PASS: Chair placed safely outside door swing arc."""
    placements = [
        Placement("P001", "NW-CHA-004", "F15", 2500.0, 2000.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert not any(v.rule_id == "RB-GEO-003" for v in violations)


# ---------------------------------------------------------------------------
# RULE 4: RB-GEO-004 (Workstation Rear Seating Clearance >= 900mm)
# ---------------------------------------------------------------------------

def test_desk_rear_violation():
    """RB-GEO-004 FAIL: Desk oriented with rear seating zone colliding with wall (<900mm)."""
    placements = [
        Placement("P001", "NW-DES-003", "F03", 2500.0, 4400.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert any(v.rule_id == "RB-GEO-004" for v in violations)
    v = next(v for v in violations if v.rule_id == "RB-GEO-004")
    assert v.measured["rear_clearance_mm"] < 900.0


def test_desk_rear_valid():
    """RB-GEO-004 PASS: Desk placed with full 1200mm rear seating zone (>=900mm)."""
    placements = [
        Placement("P001", "NW-DES-003", "F03", 2500.0, 2000.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert not any(v.rule_id == "RB-GEO-004" for v in violations)


# ---------------------------------------------------------------------------
# RULE 5: RB-GEO-005 (Perimeter Wall Offset >= 100mm buffer)
# ---------------------------------------------------------------------------

def test_wall_offset_violation():
    """RB-GEO-005 FAIL: Desk placed at 50mm from perimeter wall (<100mm buffer)."""
    placements = [
        Placement("P001", "NW-DES-001", "F01", 50.0, 50.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert any(v.rule_id == "RB-GEO-005" for v in violations)
    v = next(v for v in violations if v.rule_id == "RB-GEO-005")
    assert v.measured["wall_distance_mm"] < 100.0


def test_wall_offset_valid():
    """RB-GEO-005 PASS: Desk placed at 150mm from perimeter wall (>=100mm)."""
    placements = [
        Placement("P001", "NW-DES-001", "F01", 150.0, 150.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert not any(v.rule_id == "RB-GEO-005" for v in violations)


# ---------------------------------------------------------------------------
# RULE 6: RB-GEO-006 (2D Footprint SAT Non-Overlap)
# ---------------------------------------------------------------------------

def test_overlap_violation():
    """RB-GEO-006 FAIL: Two desks directly penetrating each other in 2D SAT space."""
    placements = [
        Placement("P001", "NW-DES-003", "F03", 2500.0, 1500.0, 0.0),
        Placement("P002", "NW-DES-003", "F03", 2600.0, 1600.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert any(v.rule_id == "RB-GEO-006" for v in violations)
    v = next(v for v in violations if v.rule_id == "RB-GEO-006")
    assert v.measured["penetration_depth_mm"] > 0.0


def test_overlap_valid():
    """RB-GEO-006 PASS: Two adjacent desks with 50mm non-intersecting gap."""
    placements = [
        Placement("P001", "NW-DES-003", "F03", 2500.0, 1500.0, 0.0),
        Placement("P002", "NW-DES-003", "F03", 3950.0, 1500.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert not any(v.rule_id == "RB-GEO-006" for v in violations)


# ---------------------------------------------------------------------------
# RULE 7: RB-GEO-007 (Room Boundary Containment)
# ---------------------------------------------------------------------------

def test_boundary_violation():
    """RB-GEO-007 FAIL: Desk positioned extending outside room polygon envelope."""
    placements = [
        Placement("P001", "NW-DES-003", "F03", 7000.0, 5000.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert any(v.rule_id == "RB-GEO-007" for v in violations)


def test_boundary_valid():
    """RB-GEO-007 PASS: Desk positioned completely inside room perimeter."""
    placements = [
        Placement("P001", "NW-DES-003", "F03", 2000.0, 2000.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert not any(v.rule_id == "RB-GEO-007" for v in violations)


# ---------------------------------------------------------------------------
# RULE 8: RB-GEO-008 (Dynamic Task Chair Pull-Out Clearance >= 750mm)
# ---------------------------------------------------------------------------

def test_chair_pullout_violation():
    """RB-GEO-008 FAIL: Task chair placed with <750mm dynamic pull-out clearance."""
    placements = [
        Placement("P001", "NW-CHA-004", "F15", 2500.0, 4500.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert any(v.rule_id == "RB-GEO-008" for v in violations)
    v = next(v for v in violations if v.rule_id == "RB-GEO-008")
    assert v.measured["pull_out_clearance_mm"] < 750.0


def test_chair_pullout_valid():
    """RB-GEO-008 PASS: Task chair placed with 1200mm dynamic pull-out clearance (>=750mm)."""
    placements = [
        Placement("P001", "NW-CHA-004", "F15", 2500.0, 2000.0, 0.0),
    ]
    violations = verify_spatial_constraints(ROOM, placements, PACK)
    assert not any(v.rule_id == "RB-GEO-008" for v in violations)
