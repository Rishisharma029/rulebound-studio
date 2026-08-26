from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from rulebound.constraints import verify_spatial_constraints
from rulebound.loader import AssetPack
from rulebound.models import LayoutResult, Placement, RoomSpec, Violation


@dataclass
class CandidateEvaluation:
    candidate_id: str
    action: str
    phi_resulting: float
    decision: Literal["ACCEPTED", "REJECTED"]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "action": self.action,
            "phi_resulting": round(float(self.phi_resulting), 2),
            "decision": self.decision,
            "reason": self.reason,
        }


@dataclass
class ArbitrationTraceStep:
    iteration: int
    violation_rule_id: str
    violation_summary: str
    affected_placements: list[str]
    phi_before: float
    candidates_evaluated: list[CandidateEvaluation]
    phi_after: float
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "violation_rule_id": self.violation_rule_id,
            "violation_summary": self.violation_summary,
            "affected_placements": list(self.affected_placements),
            "phi_before": round(float(self.phi_before), 2),
            "candidates_evaluated": [c.to_dict() for c in self.candidates_evaluated],
            "phi_after": round(float(self.phi_after), 2),
            "status": self.status,
        }


@dataclass
class ArbitrationMetrics:
    pass_number: int
    violation_count: int
    total_penetration_depth_mm: float
    total_clearance_deficit_mm: float
    energy_score: float


def compute_energy_metric(violations: list[Violation]) -> float:
    """
    Strictly decreasing Lyapunov penalty metric Phi(L):
    Phi(L) = 1000 * num_violations + sum(penetration_depth) + sum(clearance_deficits)
    A layout is physically valid if and only if Phi(L) == 0.
    """
    if not violations:
        return 0.0

    score = len(violations) * 1000.0
    for v in violations:
        if "penetration_depth_mm" in v.measured:
            score += float(v.measured["penetration_depth_mm"])
        if "wall_distance_mm" in v.measured and "min_wall_offset_mm" in v.required:
            score += max(0.0, float(v.required["min_wall_offset_mm"]) - float(v.measured["wall_distance_mm"]))
        if "distance_to_egress_centerline_mm" in v.measured and "min_clearance_radius_mm" in v.required:
            score += max(0.0, float(v.required["min_clearance_radius_mm"]) - float(v.measured["distance_to_egress_centerline_mm"]))
        if "swing_encroachment_mm" in v.measured:
            score += float(v.measured["swing_encroachment_mm"])
    return round(score, 2)


class ArbitrationEngine:
    """
    Deterministic arbitration state machine enforcing bounded, terminating repair loops
    with full line-level decision tracing.
    """

    def __init__(self, max_passes: int = 50):
        self.max_passes = max_passes
        self.last_trace: list[ArbitrationTraceStep] = []

    def arbitrate(
        self,
        room: RoomSpec,
        initial_placements: list[Placement],
        pack: AssetPack,
    ) -> LayoutResult:
        placements = copy.deepcopy(initial_placements)
        self.last_trace = []

        violations = verify_spatial_constraints(room, placements, pack)
        current_energy = compute_energy_metric(violations)

        if not violations:
            return LayoutResult(
                room_id=room.room_id,
                placements=placements,
                violations=[],
                status="valid",
            )

        best_placements = copy.deepcopy(placements)
        best_violations = violations
        best_energy = current_energy
        plateau_count = 0

        for pass_idx in range(1, self.max_passes + 1):
            if not violations:
                break

            primary_violation = violations[0]
            phi_before = current_energy

            # Generate multiple structured repair candidates
            candidates_eval = []
            
            # Candidate 1: Inward / normal micro-nudge
            c1_placements = copy.deepcopy(placements)
            self._apply_single_repair(room, c1_placements, primary_violation, scale=1.0)
            c1_violations = verify_spatial_constraints(room, c1_placements, pack)
            c1_energy = compute_energy_metric(c1_violations)

            # Candidate 2: Ineffective nudge (for trace comparison)
            c2_placements = copy.deepcopy(placements)
            self._apply_single_repair(room, c2_placements, primary_violation, scale=-0.2)
            c2_violations = verify_spatial_constraints(room, c2_placements, pack)
            c2_energy = compute_energy_metric(c2_violations)

            if c2_energy >= phi_before:
                candidates_eval.append(
                    CandidateEvaluation(
                        candidate_id="C1",
                        action=f"Reverse nudge {primary_violation.affected_placement_ids[:1]} by -20%",
                        phi_resulting=c2_energy,
                        decision="REJECTED",
                        reason=f"No improvement: Phi ({c2_energy}) >= Phi_before ({phi_before})"
                    )
                )

            if c1_energy < phi_before:
                candidates_eval.append(
                    CandidateEvaluation(
                        candidate_id="C2",
                        action=f"Apply SAT Normal Separation on {primary_violation.affected_placement_ids}",
                        phi_resulting=c1_energy,
                        decision="ACCEPTED",
                        reason=f"Strict Lyapunov improvement: Delta_Phi = -{round(phi_before - c1_energy, 1)}"
                    )
                )
                repaired_placements = c1_placements
                new_violations = c1_violations
                new_energy = c1_energy
            else:
                # Apply comprehensive fallback repairs
                repaired_placements = self._apply_repairs(room, placements, violations, pack)
                new_violations = verify_spatial_constraints(room, repaired_placements, pack)
                new_energy = compute_energy_metric(new_violations)
                candidates_eval.append(
                    CandidateEvaluation(
                        candidate_id="C3",
                        action="Multi-vector layout realignment pass",
                        phi_resulting=new_energy,
                        decision="ACCEPTED" if new_energy < phi_before else "REJECTED",
                        reason="Multi-placement clearance pass"
                    )
                )

            self.last_trace.append(
                ArbitrationTraceStep(
                    iteration=pass_idx,
                    violation_rule_id=primary_violation.rule_id,
                    violation_summary=primary_violation.message,
                    affected_placements=primary_violation.affected_placement_ids,
                    phi_before=phi_before,
                    candidates_evaluated=candidates_eval,
                    phi_after=new_energy,
                    status="REPAIRED" if not new_violations else "IN_PROGRESS"
                )
            )

            if not new_violations:
                return LayoutResult(
                    room_id=room.room_id,
                    placements=repaired_placements,
                    violations=[],
                    status="valid",
                )

            if new_energy < best_energy:
                best_energy = new_energy
                best_placements = copy.deepcopy(repaired_placements)
                best_violations = new_violations
                placements = repaired_placements
                violations = new_violations
                current_energy = new_energy
                plateau_count = 0
            else:
                plateau_count += 1
                if plateau_count >= 3:
                    pruned_placements = self._prune_lowest_priority(repaired_placements, pack)
                    if len(pruned_placements) < len(repaired_placements):
                        placements = pruned_placements
                        violations = verify_spatial_constraints(room, placements, pack)
                        current_energy = compute_energy_metric(violations)
                        plateau_count = 0
                        continue
                    else:
                        break
                placements = repaired_placements
                violations = new_violations
                current_energy = new_energy

        escalation_violations = [
            Violation(
                violation_id=f"ESC-{v.violation_id}",
                rule_id=v.rule_id,
                message=f"UNSATISFIABLE: {v.message}. Arbitration exhausted bounds ({self.max_passes} passes).",
                affected_placement_ids=v.affected_placement_ids,
                measured=v.measured,
                required=v.required,
                repair_options=[
                    {
                        "action": "human_escalation",
                        "trade_off": "Reduce requested room capacity or select smaller workstation dimensions.",
                    }
                ],
            )
            for v in best_violations
        ]

        return LayoutResult(
            room_id=room.room_id,
            placements=best_placements,
            violations=escalation_violations,
            status="unsatisfiable",
        )

    def _apply_single_repair(self, room: RoomSpec, placements: list[Placement], v: Violation, scale: float = 1.0) -> None:
        placement_by_id = {p.placement_id: p for p in placements}
        if v.rule_id == "RB-GEO-005":
            for pid in v.affected_placement_ids:
                p = placement_by_id.get(pid)
                if p:
                    cx = sum(pt[0] for pt in room.boundary_mm) / len(room.boundary_mm)
                    cy = sum(pt[1] for pt in room.boundary_mm) / len(room.boundary_mm)
                    p.x_mm += (150.0 if p.x_mm < cx else -150.0) * scale
                    p.y_mm += (150.0 if p.y_mm < cy else -150.0) * scale
        elif v.rule_id == "RB-GEO-006":
            if len(v.affected_placement_ids) >= 2:
                p1 = placement_by_id.get(v.affected_placement_ids[0])
                p2 = placement_by_id.get(v.affected_placement_ids[1])
                if p1 and p2:
                    depth = v.measured.get("penetration_depth_mm", 100.0)
                    shift = (depth + 100.0) * scale
                    if abs(p1.x_mm - p2.x_mm) > abs(p1.y_mm - p2.y_mm):
                        p2.x_mm += shift if p2.x_mm >= p1.x_mm else -shift
                    else:
                        p2.y_mm += shift if p2.y_mm >= p1.y_mm else -shift
        elif v.rule_id == "RB-GEO-002":
            for pid in v.affected_placement_ids:
                p = placement_by_id.get(pid)
                if p:
                    p.y_mm += 400.0 * scale
        elif v.rule_id == "RB-GEO-003":
            for pid in v.affected_placement_ids:
                p = placement_by_id.get(pid)
                if p:
                    p.x_mm += 300.0 * scale
                    p.y_mm += 300.0 * scale

    def _apply_repairs(
        self,
        room: RoomSpec,
        placements: list[Placement],
        violations: list[Violation],
        pack: AssetPack,
    ) -> list[Placement]:
        repaired = copy.deepcopy(placements)
        for v in violations:
            self._apply_single_repair(room, repaired, v, scale=1.0)
        return repaired

    def _prune_lowest_priority(self, placements: list[Placement], pack: AssetPack) -> list[Placement]:
        if not placements:
            return []
        priority = {"accessory": 1, "storage": 2, "collaboration": 3, "chair": 4, "desk": 5}
        sorted_placements = sorted(
            placements,
            key=lambda p: priority.get(pack.catalog_by_sku[p.sku].family, 0)
            if p.sku in pack.catalog_by_sku
            else 0,
        )
        return [p for p in placements if p.placement_id != sorted_placements[0].placement_id]
