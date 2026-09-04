from __future__ import annotations

from pathlib import Path
import pytest

from rulebound.arbitration import ArbitrationEngine, compute_energy_metric
from rulebound.constraints import verify_spatial_constraints
from rulebound.loader import load_asset_pack
from rulebound.models import Placement

ROOT = Path(__file__).resolve().parents[1]
PACK = load_asset_pack(ROOT / "RuleBound_Round1_Release/data")


def test_arbitration_deliberate_violation_repair():
    """
    Demonstrates deliberate constraint violation and autonomous repair by ArbitrationEngine.
    We place two overlapping desks violating RB-GEO-006 and RB-GEO-005.
    """
    room = PACK.rooms_by_id["ROOM-01"]
    
    # Deliberate violation: two overlapping desks at (50, 50) violating wall offset and overlap
    bad_placements = [
        Placement("P001", "NW-DES-001", "F01", 50.0, 50.0, 0.0),
        Placement("P002", "NW-DES-001", "F01", 100.0, 50.0, 0.0),
    ]

    initial_violations = verify_spatial_constraints(room, bad_placements, PACK)
    assert len(initial_violations) > 0
    initial_energy = compute_energy_metric(initial_violations)
    assert initial_energy > 0.0

    # Execute Arbitration
    arbitrator = ArbitrationEngine(max_passes=20)
    result = arbitrator.arbitrate(room, bad_placements, PACK)

    assert result.status == "valid"
    assert len(result.violations) == 0


def test_arbitration_unsatisfiable_escalation():
    """
    Demonstrates escalation when room is physically incapable of holding requested furniture.
    """
    room = PACK.rooms_by_id["ROOM-01"]

    # Deliberate impossible load: 15 giant collaboration tables in a 7.2m x 5.4m room
    impossible_placements = [
        Placement(f"P{i:03d}", "NW-COL-008", "F09", 1000.0 + (i % 5) * 500.0, 1000.0 + (i // 5) * 500.0, 0.0)
        for i in range(15)
    ]

    arbitrator = ArbitrationEngine(max_passes=5)
    result = arbitrator.arbitrate(room, impossible_placements, PACK)

    assert result.status == "unsatisfiable"
    assert len(result.violations) > 0


def test_arbitration_trace_strictly_unambiguous_decisions():
    """
    Verifies that every candidate in the arbitration trace receives exactly one unambiguous outcome:
    - SELECTED -> with mathematical Lyapunov delta reason
    - REJECTED -> with explicit non-improvement or suboptimal reason
    - UNSATISFIABLE -> with escalation reason
    """
    room = PACK.rooms_by_id["ROOM-01"]
    bad_placements = [
        Placement("P001", "NW-DES-001", "F01", 50.0, 50.0, 0.0),
        Placement("P002", "NW-DES-001", "F01", 100.0, 50.0, 0.0),
    ]

    arbitrator = ArbitrationEngine(max_passes=10)
    result = arbitrator.arbitrate(room, bad_placements, PACK)
    assert len(arbitrator.last_trace) > 0

    for step in arbitrator.last_trace:
        selected_count = 0
        for cand in step.candidates_evaluated:
            assert cand.decision in ("SELECTED", "REJECTED", "UNSATISFIABLE")
            assert len(cand.reason) > 0
            if cand.decision == "SELECTED":
                selected_count += 1
                assert "Lyapunov descent" in cand.reason
            elif cand.decision == "REJECTED":
                assert ("No improvement" in cand.reason) or ("Suboptimal descent" in cand.reason)
        # In any improving step, exactly 1 candidate is SELECTED
        if step.status != "UNSATISFIABLE":
            assert selected_count == 1


def test_arbitration_strictly_decreases_phi():
    """
    Formally proves the Lyapunov property and bounded termination of the arbitration engine:
    1. Every accepted repair strictly decreases energy: phi_after < phi_before (Delta_Phi < 0).
    2. Bounded termination: trace length <= Kmax (50 passes).
    3. Escalation: physically impossible layout terminates with status == 'unsatisfiable'.
    """
    room = PACK.rooms_by_id["ROOM-01"]

    # Multi-violation scenario: overlapping desks with wall breaches and corridor intrusion
    bad_placements = [
        Placement("P001", "NW-DES-003", "F03", 50.0, 50.0, 0.0),
        Placement("P002", "NW-DES-003", "F03", 100.0, 100.0, 0.0),
        Placement("P003", "NW-DES-003", "F03", 2000.0, 4400.0, 0.0),
    ]

    arbitrator = ArbitrationEngine(max_passes=50)
    result = arbitrator.arbitrate(room, bad_placements, PACK)

    # Invariant 1: Bounded termination (Kmax <= 50)
    assert len(arbitrator.last_trace) <= 50

    # Invariant 2: Strict Lyapunov decrease on every accepted pass
    for step in arbitrator.last_trace:
        assert step.phi_after < step.phi_before
        selected_cand = next((c for c in step.candidates_evaluated if c.decision == "SELECTED"), None)
        if selected_cand:
            assert selected_cand.phi_after < selected_cand.phi_before
            assert selected_cand.delta_phi < 0.0

    # Invariant 3: Impossible layout escalates to unsatisfiable within bounded passes
    impossible_pls = [
        Placement(f"P{i:03d}", "NW-COL-008", "F09", 1000.0 + (i % 3) * 600.0, 1000.0 + (i // 3) * 600.0, 0.0)
        for i in range(15)
    ]
    arbitrator_unsat = ArbitrationEngine(max_passes=5)
    result_unsat = arbitrator_unsat.arbitrate(room, impossible_pls, PACK)

    assert result_unsat.status == "unsatisfiable"
    assert len(arbitrator_unsat.last_trace) <= 50

