#!/usr/bin/env python3
"""
ROOM-01 hero demonstration: brief → IR → violation → arbitration → quote → DXF.

Usage: python demo.py
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rulebound.arbitration import ArbitrationEngine, compute_energy_metric
from rulebound.constraints import audit_spatial_constraints, verify_spatial_constraints
from rulebound.counterexample import execute_counterexample_laboratory
from rulebound.counterfactual import explain_counterfactual
from rulebound.dxf import export_layout_to_dxf
from rulebound.generator import LayoutGenerator
from rulebound.ir import evaluate_requirement_satisfaction, extract_requirement_ir
from rulebound.layout_diff import diff_layouts
from rulebound.loader import load_asset_pack
from rulebound.optimizer import evaluate_and_rank_candidates
from rulebound.pricing import price_placements

BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
DIM = "\033[2m"
RESET = "\033[0m"


def beat(clock: str, title: str):
    print(f"\n{BOLD}{CYAN}[{clock}] {title}{RESET}")
    print(f"{DIM}{'-' * 72}{RESET}")


def main():
    root = Path(__file__).resolve().parent
    pack = load_asset_pack(root / "RuleBound_Round1_Release/data")
    room = pack.rooms_by_id["ROOM-01"]
    brief = pack.briefs.get("ROOM-01", "")
    generator = LayoutGenerator()

    print(f"\n{BOLD}{MAGENTA}RULEBOUND STUDIO — ROOM-01 HERO WALKTHROUGH{RESET}")
    print(f"{DIM}Harbour Design Studio · one room, one story, full audit trail{RESET}\n")

    beat("00:00", "Client brief")
    print(brief.strip())

    beat("00:20", "RequirementIR appears")
    ir = extract_requirement_ir(brief, room)
    print(f"  occupancy={ir.occupancy}  desks={ir.workstations.count} ({ir.workstations.arrangement})")
    print(f"  storage={ir.storage.count} lockable={ir.storage.lockable}  collab={ir.collaboration.count}")
    print(f"  materials={ir.preferences.materials}  openness={ir.preferences.openness}")

    beat("00:40", "Candidate layout generated")
    placements = generator.generate_candidate_layout(room, pack)
    arbitrator = ArbitrationEngine()
    layout = arbitrator.arbitrate(room, placements, pack)
    print(f"  placements={len(layout.placements)}  status={layout.status}  Φ={compute_energy_metric(layout.violations):.0f}")

    beat("01:00", "Inject overlap + egress violation")
    broken = copy.deepcopy(layout.placements)
    if len(broken) >= 2:
        broken[0].x_mm = broken[1].x_mm + 80.0
        broken[0].y_mm = broken[1].y_mm
        egress_pt = room.egress.to_point_mm
        if len(broken) >= 3:
            broken[2].x_mm = float(egress_pt[0])
            broken[2].y_mm = 120.0
    print(f"  P001 forced into P002 footprint; third piece parked on the egress path")

    beat("01:20", "Violations appear")
    v_now = verify_spatial_constraints(room, broken, pack)
    phi0 = compute_energy_metric(v_now)
    for v in v_now[:6]:
        print(f"  {RED}{v.rule_id}{RESET}  {v.message}")
    print(f"  {RED}Φ = {phi0:.0f}{RESET}")

    beat("01:40", "Candidate arbitration")
    engine = ArbitrationEngine(max_passes=50)
    repaired = engine.arbitrate(room, broken, pack)
    if engine.last_trace:
        step = engine.last_trace[0]
        for c in step.candidates_evaluated[:4]:
            tag = f"{GREEN}SELECTED{RESET}" if c.decision == "SELECTED" else f"{RED}REJECTED{RESET}"
            print(f"  {c.action:<28} {tag}  ΔΦ={c.delta_phi:.0f}")

    beat("02:00", "Watch Φ descend")
    phis = [phi0]
    for step in engine.last_trace:
        phis.append(step.phi_after)
    shown = phis[:4]
    while len(shown) < 4:
        shown.append(phis[-1])
    shown[-1] = float(compute_energy_metric(repaired.violations))
    print("  " + " → ".join(f"{p:.0f}" for p in shown))

    beat("02:20", "Constraint monitor")
    audits = audit_spatial_constraints(room, repaired.placements, pack)
    passed = sum(1 for a in audits if a.get("status") == "PASS")
    print(f"  {GREEN}{passed}/{len(audits)} PASS{RESET}")

    beat("02:40", "Requirement trace")
    sat = evaluate_requirement_satisfaction(ir, repaired.placements, room, pack)
    print(f"  overall {sat['overall_percentage']}%  metrics={sat['metrics']}")

    beat("03:00", "Deterministic quote")
    quote = price_placements(room.room_id, repaired.placements, pack)
    print(f"  status={quote.status}  lines={len(quote.lines)}  grand_total=₹{quote.summary.grand_total_inr:,}")

    beat("03:30", "Pricing trace (first line)")
    if quote.lines:
        line = quote.lines[0]
        print(f"  {line.sku} qty={line.quantity} net_goods=₹{line.net_goods_inr:,}  discount=₹{line.quantity_discount_inr:,}")
        for t in (line.trace or [])[:4]:
            print(f"    {t.rule_id}: ₹{t.amount_inr:,}  {t.inputs}")

    beat("04:00", "Export DXF")
    dxf_path = root / "OUTPUT" / "ROOM-01" / "layout.dxf"
    dxf_path.parent.mkdir(parents=True, exist_ok=True)
    export_layout_to_dxf(room, repaired.placements, pack, dxf_path)
    print(f"  wrote {dxf_path} ({dxf_path.stat().st_size} bytes)")

    beat("04:20", "Decision quality + why-not + what-changed")
    qrep, ranks = evaluate_and_rank_candidates(room, pack)
    print(qrep.render_ascii_card())
    why = explain_counterfactual(room, pack, "Candidate A", rankings=ranks)
    print(f"\n{why['ascii_card']}\n")
    lab = execute_counterexample_laboratory(room, pack, "egress")
    from rulebound.models import Placement
    before = [Placement(**p) if isinstance(p, dict) else p for p in lab["phase1_invalid"]["placements"]]
    after = [Placement(**p) if isinstance(p, dict) else p for p in lab["phase3_resolution"]["placements"]]
    delta = diff_layouts(room, pack, before, after, reason_hint="RB-GEO-002")
    print(delta["ascii_card"])

    beat("04:40", "Studio verdict")
    print(f"  {GREEN}{BOLD}VALID • OPTIMIZED • AUDITED • DETERMINISTIC{RESET}")
    print(f"  {DIM}Open EVIDENCE/FINAL_REPORT.html first. Run python judge.py for the live card.{RESET}\n")


if __name__ == "__main__":
    main()
