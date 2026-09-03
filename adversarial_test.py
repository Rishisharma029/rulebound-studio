#!/usr/bin/env python3
"""
RuleBound Adversarial Competition Verification Suite
Demonstrates that all 8 spatial rules, pricing invariants, arbitration repairs,
and impossible escalations are genuinely executable, tested, and passing.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from rulebound.arbitration import ArbitrationEngine
from rulebound.constraints import verify_spatial_constraints
from rulebound.loader import load_asset_pack
from rulebound.models import Placement
from rulebound.pricing import price_placements


def run_adversarial_suite() -> int:
    pack = load_asset_pack(ROOT / "RuleBound_Round1_Release/data")
    room1 = pack.rooms_by_id["ROOM-01"]
    arbitrator = ArbitrationEngine(max_passes=50)

    results: list[tuple[str, bool]] = []

    # 1. RB-GEO-001: Walkway breach (<900mm)
    bad_walkway = [
        Placement("P001", "NW-DES-003", "F03", 2500.0, 1500.0, 0.0),
        Placement("P002", "NW-DES-003", "F03", 2500.0, 2700.0, 0.0),
    ]
    v_walkway = verify_spatial_constraints(room1, bad_walkway, pack)
    results.append(("RB-GEO-001", any(v.rule_id == "RB-GEO-001" for v in v_walkway)))

    # 2. RB-GEO-002: Egress corridor breach
    bad_egress = [
        Placement("P001", "NW-DES-003", "F03", 2000.0, 100.0, 0.0),
    ]
    v_egress = verify_spatial_constraints(room1, bad_egress, pack)
    results.append(("RB-GEO-002", any(v.rule_id == "RB-GEO-002" for v in v_egress)))

    # 3. RB-GEO-003: Door swing arc breach (850mm radius)
    bad_swing = [
        Placement("P001", "NW-CHA-004", "F15", 700.0, 200.0, 0.0),
    ]
    v_swing = verify_spatial_constraints(room1, bad_swing, pack)
    results.append(("RB-GEO-003", any(v.rule_id == "RB-GEO-003" for v in v_swing)))

    # 4. RB-GEO-004: Desk rear clearance breach (<900mm)
    bad_desk_rear = [
        Placement("P001", "NW-DES-003", "F03", 2500.0, 4400.0, 0.0),
    ]
    v_desk_rear = verify_spatial_constraints(room1, bad_desk_rear, pack)
    results.append(("RB-GEO-004", any(v.rule_id == "RB-GEO-004" for v in v_desk_rear)))

    # 5. RB-GEO-005: Perimeter wall offset breach (<100mm)
    bad_wall = [
        Placement("P001", "NW-DES-001", "F01", 50.0, 50.0, 0.0),
    ]
    v_wall = verify_spatial_constraints(room1, bad_wall, pack)
    results.append(("RB-GEO-005", any(v.rule_id == "RB-GEO-005" for v in v_wall)))

    # 6. RB-GEO-006: SAT Polygon Overlap breach
    bad_overlap = [
        Placement("P001", "NW-DES-003", "F03", 2500.0, 1500.0, 0.0),
        Placement("P002", "NW-DES-003", "F03", 2600.0, 1600.0, 0.0),
    ]
    v_overlap = verify_spatial_constraints(room1, bad_overlap, pack)
    results.append(("RB-GEO-006", any(v.rule_id == "RB-GEO-006" for v in v_overlap)))

    # 7. RB-GEO-007: Room boundary breach
    bad_bound = [
        Placement("P001", "NW-DES-003", "F03", 7000.0, 5000.0, 0.0),
    ]
    v_bound = verify_spatial_constraints(room1, bad_bound, pack)
    results.append(("RB-GEO-007", any(v.rule_id == "RB-GEO-007" for v in v_bound)))

    # 8. RB-GEO-008: Chair pullout clearance breach (<750mm)
    bad_chair = [
        Placement("P001", "NW-CHA-004", "F15", 2500.0, 4500.0, 0.0),
    ]
    v_chair = verify_spatial_constraints(room1, bad_chair, pack)
    results.append(("RB-GEO-008", any(v.rule_id == "RB-GEO-008" for v in v_chair)))

    # 9. RB-PRC-013: Invalid SKU & Invalid Finish blocking
    q_sku = price_placements("ROOM-01", [Placement("P001", "NW-FAKE-999", "F01", 1000.0, 1000.0, 0.0)], pack)
    q_fin = price_placements("ROOM-01", [Placement("P001", "NW-DES-001", "F99", 1000.0, 1000.0, 0.0)], pack)
    results.append(("RB-PRC-013", q_sku.status == "blocked" and q_fin.status == "blocked"))

    # 10. ARBITRATION: Autonomous repair of multi-violation layout to VALID
    bad_multi = [
        Placement("P001", "NW-DES-003", "F03", 50.0, 50.0, 0.0),
        Placement("P002", "NW-DES-003", "F03", 100.0, 100.0, 0.0),
    ]
    res_arb = arbitrator.arbitrate(room1, bad_multi, pack)
    results.append(("ARBITRATION", res_arb.status == "valid" and len(res_arb.violations) == 0))

    # 11. ESCALATION: Provable termination to UNSATISFIABLE for impossible room
    impossible_pls = [
        Placement(f"P{i:03d}", "NW-COL-008", "F09", 1000.0 + (i % 3) * 600.0, 1000.0 + (i // 3) * 600.0, 0.0)
        for i in range(15)
    ]
    res_unsat = ArbitrationEngine(max_passes=2).arbitrate(room1, impossible_pls, pack)
    results.append(("ESCALATION", res_unsat.status == "unsatisfiable"))

    # Print results
    print("RULEBOUND ADVERSARIAL VERIFICATION\n")
    passed_count = 0
    for name, ok in results:
        status_str = "PASS" if ok else "FAIL"
        if ok:
            passed_count += 1
        print(f"{name:<12} {status_str}")

    print(f"\n{passed_count}/{len(results)} PASS")
    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(run_adversarial_suite())
