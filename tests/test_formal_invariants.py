from pathlib import Path
import pytest

from rulebound.arbitration import ArbitrationTraceStep, CandidateEvaluation
from rulebound.invariants import (
    audit_arbitration_invariants,
    audit_geometry_invariants,
    audit_output_invariants,
    audit_pricing_invariants,
    verify_all_system_invariants,
    SystemInvariantsCertificate,
)
from rulebound.loader import load_asset_pack
from rulebound.models import Placement, QuoteResult
from rulebound.pricing import price_placements

ROOT = Path(__file__).resolve().parents[1]
PACK = load_asset_pack(ROOT / "RuleBound_Round1_Release/data")


def test_geometry_invariants_auditing():
    room = PACK.rooms_by_id["ROOM-01"]
    # Base canonical placements
    placements = [
        Placement("P001", "NW-DES-001", "F01", 1000.0, 1000.0, 0.0),
        Placement("P002", "NW-DES-001", "F01", 3000.0, 1000.0, 90.0),
    ]

    report = audit_geometry_invariants(room, placements, PACK)
    assert report.is_valid
    assert report.total_checks == 6
    assert report.passed_checks == 6

    # Test G-INV-001 violation: placement outside room
    bad_placements = [Placement("P001", "NW-DES-001", "F01", 99999.0, 99999.0, 0.0)]
    bad_report = audit_geometry_invariants(room, bad_placements, PACK)
    g1 = next(c for c in bad_report.checks if c.invariant_id == "G-INV-001")
    assert not g1.passed
    assert "P001" in str(g1.diagnostic)

    # Test G-INV-003 violation: non-orthogonal rotation (45 degrees)
    rot_placements = [Placement("P001", "NW-DES-001", "F01", 1000.0, 1000.0, 45.0)]
    rot_report = audit_geometry_invariants(room, rot_placements, PACK)
    g3 = next(c for c in rot_report.checks if c.invariant_id == "G-INV-003")
    assert not g3.passed
    assert "45.0°" in str(g3.diagnostic)


def test_arbitration_invariants_auditing():
    # Valid Lyapunov descent trace
    valid_trace = [
        ArbitrationTraceStep(
            iteration=1,
            violation_rule_id="RB-GEO-006",
            violation_summary="Overlap detected",
            affected_placements=["P001", "P002"],
            phi_before=1500.0,
            candidates_evaluated=[
                CandidateEvaluation(
                    candidate_id="C1",
                    action="Shift X +200mm",
                    phi_before=1500.0,
                    phi_after=0.0,
                    delta_phi=-1500.0,
                    decision="SELECTED",
                    decision_reason="Strict Lyapunov descent",
                )
            ],
            phi_after=0.0,
            status="REPAIRED",
        )
    ]

    report = audit_arbitration_invariants(valid_trace, final_status="valid", is_valid=True)
    assert report.is_valid
    assert report.total_checks == 4
    assert report.passed_checks == 4

    # Test A-INV-002 violation: Non-decreasing energy step
    bad_trace = [
        ArbitrationTraceStep(
            iteration=1,
            violation_rule_id="RB-GEO-006",
            violation_summary="Overlap detected",
            affected_placements=["P001"],
            phi_before=1000.0,
            candidates_evaluated=[
                CandidateEvaluation(
                    candidate_id="C1",
                    action="Invalid action",
                    phi_before=1000.0,
                    phi_after=1200.0,  # Energy increased!
                    delta_phi=200.0,
                    decision="SELECTED",
                    decision_reason="Bad decision",
                )
            ],
            phi_after=1200.0,
            status="IN_PROGRESS",
        )
    ]
    bad_report = audit_arbitration_invariants(bad_trace, final_status="valid", is_valid=True)
    a2 = next(c for c in bad_report.checks if c.invariant_id == "A-INV-002")
    assert not a2.passed

    # Test A-INV-004 violation: UNSAT falsely marked as valid
    unsat_report = audit_arbitration_invariants(valid_trace, final_status="unsatisfiable", is_valid=True)
    a4 = next(c for c in unsat_report.checks if c.invariant_id == "A-INV-004")
    assert not a4.passed


def test_output_invariants_auditing():
    room = PACK.rooms_by_id["ROOM-01"]
    placements = [
        Placement("P001", "NW-DES-001", "F01", 1000.0, 1000.0, 0.0),
        Placement("P002", "NW-CHA-001", "F15", 2000.0, 1000.0, 0.0),
    ]
    quote = price_placements(room.room_id, placements, PACK)

    report = audit_output_invariants(room, placements, quote, PACK)
    assert report.is_valid
    assert report.total_checks == 5
    assert report.passed_checks == 5

    # Test O-INV-001 violation: Placement count vs Quote line quantity mismatch
    fake_quote = price_placements(room.room_id, placements[:1], PACK)  # only 1 priced
    bad_report = audit_output_invariants(room, placements, fake_quote, PACK)
    o1 = next(c for c in bad_report.checks if c.invariant_id == "O-INV-001")
    assert not o1.passed

    # Test O-INV-002 violation: Non-existent catalog SKU
    bad_placements = [Placement("P001", "FAKE-SKU-999", "F01", 1000.0, 1000.0, 0.0)]
    sku_report = audit_output_invariants(room, bad_placements, quote, PACK)
    o2 = next(c for c in sku_report.checks if c.invariant_id == "O-INV-002")
    assert not o2.passed


def test_master_formal_system_invariants_certificate():
    room = PACK.rooms_by_id["ROOM-01"]
    placements = [
        Placement("P001", "NW-DES-001", "F01", 1000.0, 1000.0, 0.0),
        Placement("P002", "NW-CHA-001", "F15", 2000.0, 1000.0, 0.0),
    ]
    quote = price_placements(room.room_id, placements, PACK)

    cert = verify_all_system_invariants(
        room=room,
        placements=placements,
        quote=quote,
        pack=PACK,
    )

    assert isinstance(cert, SystemInvariantsCertificate)
    assert cert.overall_valid
    assert cert.total_invariants == 21  # 6 Geometry + 4 Arbitration + 5 Output + 6 Pricing
    assert cert.passed_invariants == 21
    assert cert.failed_invariants == 0
    assert cert.pass_percentage == 100.0
    assert len(cert.certificate_hash) == 64  # SHA-256 hex digest

    card = cert.render_ascii_card()
    assert "RULEBOUND FORMAL SYSTEM INVARIANTS CERTIFICATE" in card
    assert "21/21 Passed (100.0%)" in card
    assert "G-INV-001" in card
    assert "A-INV-001" in card
    assert "O-INV-001" in card
    assert "P-INV-001" in card
