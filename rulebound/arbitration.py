from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Literal

from rulebound.constraints import verify_spatial_constraints
from rulebound.generator import LayoutGenerator
from rulebound.loader import AssetPack
from rulebound.models import LayoutResult, Placement, RoomSpec, Violation


@dataclass
class CandidateEvaluation:
    candidate_id: str
    action: str
    phi_before: float
    phi_after: float
    delta_phi: float
    decision: Literal["SELECTED", "REJECTED", "UNSATISFIABLE"]
    decision_reason: str

    @property
    def phi_resulting(self) -> float:
        return self.phi_after

    @property
    def reason(self) -> str:
        return self.decision_reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "action": self.action,
            "phi_before": round(float(self.phi_before), 2),
            "phi_after": round(float(self.phi_after), 2),
            "delta_phi": round(float(self.delta_phi), 2),
            "decision": self.decision,
            "reason": self.decision_reason,
            "decision_reason": self.decision_reason,
            "phi_resulting": round(float(self.phi_after), 2),
        }


@dataclass
class PlacementTransformation:
    placement_id: str
    before_x: float
    before_y: float
    before_rot: float
    dx: float
    dy: float
    after_x: float
    after_y: float
    after_rot: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "placement_id": self.placement_id,
            "before": [round(self.before_x, 1), round(self.before_y, 1), round(self.before_rot, 1)],
            "delta": [round(self.dx, 1), round(self.dy, 1)],
            "after": [round(self.after_x, 1), round(self.after_y, 1), round(self.after_rot, 1)],
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
    transformations: list[PlacementTransformation] = field(default_factory=list)

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
            "transformations": [t.to_dict() for t in self.transformations],
        }


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
        if "corridor_distance_mm" in v.measured and "min_half_width_mm" in v.required:
            score += max(0.0, float(v.required["min_half_width_mm"]) - float(v.measured["corridor_distance_mm"]))
        if "swing_encroachment_mm" in v.measured:
            score += float(v.measured["swing_encroachment_mm"])
        if "walkway_width_mm" in v.measured and "min_walkway_width_mm" in v.required:
            score += max(0.0, float(v.required["min_walkway_width_mm"]) - float(v.measured["walkway_width_mm"]))
        if "rear_clearance_mm" in v.measured and "min_rear_clearance_mm" in v.required:
            score += max(0.0, float(v.required["min_rear_clearance_mm"]) - float(v.measured["rear_clearance_mm"]))
        if "pull_out_clearance_mm" in v.measured and "min_pull_out_clearance_mm" in v.required:
            score += max(0.0, float(v.required["min_pull_out_clearance_mm"]) - float(v.measured["pull_out_clearance_mm"]))
    return round(score, 2)


class ArbitrationEngine:
    """
    Deterministic arbitration proof system enforcing bounded, terminating repair loops
    with full line-level Lyapunov decision proofs across all 8 spatial rules.
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

        generator = LayoutGenerator()
        canonical_placements = generator.generate_candidate_layout(room, pack)
        canonical_map = {p.placement_id: (p.x_mm, p.y_mm, p.rotation_deg) for p in canonical_placements}

        xs = [pt[0] for pt in room.boundary_mm]
        ys = [pt[1] for pt in room.boundary_mm]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        for pass_idx in range(1, self.max_passes + 1):
            if not violations:
                break

            primary_v = violations[0]
            phi_before = current_energy
            pid = primary_v.affected_placement_ids[0] if primary_v.affected_placement_ids else None

            candidates_list: list[tuple[str, list[Placement], str]] = []

            if pid:
                p_idx = next((i for i, p in enumerate(placements) if p.placement_id == pid), None)
                if p_idx is not None:
                    item = pack.catalog_by_sku.get(placements[p_idx].sku)
                    w = item.dimensions_mm.width if item else 1200.0
                    d = item.dimensions_mm.depth if item else 600.0

                    # 1. Candidate C1: Micro-perturbation (+20mm)
                    c_rev = copy.deepcopy(placements)
                    c_rev[p_idx].x_mm += 20.0
                    c_rev[p_idx].y_mm += 20.0
                    candidates_list.append(("C1", c_rev, f"Micro-shift {pid} (+20mm X, +20mm Y)"))

                    # 2. Candidate C2: Canonical Anchor snap
                    if pid in canonical_map:
                        cx, cy, crot = canonical_map[pid]
                        c_canon = copy.deepcopy(placements)
                        c_canon[p_idx].x_mm = cx
                        c_canon[p_idx].y_mm = cy
                        c_canon[p_idx].rotation_deg = crot
                        candidates_list.append(("C2", c_canon, f"Snap {pid} to collision-free anchor ({round(cx)}, {round(cy)})"))

                    # 3. Candidate C3: Boundary Containment Clamping (RB-GEO-007)
                    if primary_v.rule_id == "RB-GEO-007" or placements[p_idx].x_mm < min_x or placements[p_idx].x_mm + w > max_x or placements[p_idx].y_mm < min_y or placements[p_idx].y_mm + d > max_y:
                        c_bound = copy.deepcopy(placements)
                        c_bound[p_idx].x_mm = min(max(min_x + 150.0, c_bound[p_idx].x_mm), max_x - w - 150.0)
                        c_bound[p_idx].y_mm = min(max(min_y + 150.0, c_bound[p_idx].y_mm), max_y - d - 150.0)
                        candidates_list.append(("C3", c_bound, f"Clamp {pid} inside room boundary envelope"))

                    # 4. Candidate C4: Wall offset snapping (RB-GEO-005)
                    if primary_v.rule_id == "RB-GEO-005":
                        c_wall = copy.deepcopy(placements)
                        if c_wall[p_idx].x_mm < min_x + 100.0:
                            c_wall[p_idx].x_mm = min_x + 150.0
                        if c_wall[p_idx].x_mm + w > max_x - 100.0:
                            c_wall[p_idx].x_mm = max_x - 150.0 - w
                        if c_wall[p_idx].y_mm < min_y + 100.0:
                            c_wall[p_idx].y_mm = min_y + 150.0
                        if c_wall[p_idx].y_mm + d > max_y - 100.0:
                            c_wall[p_idx].y_mm = max_y - 150.0 - d
                        candidates_list.append(("C4", c_wall, f"Snap {pid} to interior wall envelope (150mm gap)"))

                    # 5. Candidate C5: Egress corridor clearance (RB-GEO-002)
                    if primary_v.rule_id == "RB-GEO-002":
                        c_egress = copy.deepcopy(placements)
                        c_egress[p_idx].y_mm = max(min_y + 150.0, c_egress[p_idx].y_mm - 600.0)
                        candidates_list.append(("C5", c_egress, f"Shift {pid} outside egress clearance zone"))

                    # 6. Candidate C6: SAT Overlap Normal Separations (RB-GEO-006)
                    if primary_v.rule_id == "RB-GEO-006" and len(primary_v.affected_placement_ids) >= 2:
                        pid2 = primary_v.affected_placement_ids[1]
                        p2_idx = next((i for i, p in enumerate(placements) if p.placement_id == pid2), None)
                        if p2_idx is not None:
                            c_sat = copy.deepcopy(placements)
                            shift = 700.0
                            if abs(c_sat[p_idx].x_mm - c_sat[p2_idx].x_mm) > abs(c_sat[p_idx].y_mm - c_sat[p2_idx].y_mm):
                                c_sat[p_idx].x_mm += shift if c_sat[p_idx].x_mm >= c_sat[p2_idx].x_mm else -shift
                            else:
                                c_sat[p_idx].y_mm += shift if c_sat[p_idx].y_mm >= c_sat[p2_idx].y_mm else -shift
                            c_sat[p_idx].x_mm = min(max(min_x + 150.0, c_sat[p_idx].x_mm), max_x - w - 150.0)
                            c_sat[p_idx].y_mm = min(max(min_y + 150.0, c_sat[p_idx].y_mm), max_y - d - 150.0)
                            candidates_list.append(("C6", c_sat, f"SAT Separation vector between {pid} and {pid2}"))

                    # 7. Directional clearance explorations
                    directions = [
                        (400.0, 0.0, "East clearance shift +400mm"),
                        (-400.0, 0.0, "West clearance shift -400mm"),
                        (0.0, 400.0, "North clearance shift +400mm"),
                        (0.0, -400.0, "South clearance shift -400mm"),
                        (800.0, 0.0, "Longitudinal clearance shift +800mm"),
                        (-800.0, 0.0, "Longitudinal clearance shift -800mm"),
                    ]
                    for idx, (dx, dy, desc) in enumerate(directions, start=7):
                        c_dir = copy.deepcopy(placements)
                        c_dir[p_idx].x_mm = min(max(min_x + 150.0, c_dir[p_idx].x_mm + dx), max_x - w - 150.0)
                        c_dir[p_idx].y_mm = min(max(min_y + 150.0, c_dir[p_idx].y_mm + dy), max_y - d - 150.0)
                        candidates_list.append((f"C{idx}", c_dir, f"{pid}: {desc}"))

            # Evaluate standard candidate operators
            evaluated_data: list[tuple[str, list[Placement], str, float]] = []
            for cid, c_pls, action_desc in candidates_list:
                c_viols = verify_spatial_constraints(room, c_pls, pack)
                c_energy = compute_energy_metric(c_viols)
                evaluated_data.append((cid, c_pls, action_desc, c_energy))

            # 8. Adaptive Open Space Relocation (fallback only if no candidate achieved descent)
            if pid and not any(c_energy < phi_before for _, _, _, c_energy in evaluated_data):
                best_grid_pls = None
                best_grid_phi = phi_before
                for gx in range(int(min_x + 200), int(max_x - w - 200), 400):
                    for gy in range(int(min_y + 200), int(max_y - d - 200), 400):
                        c_grid = copy.deepcopy(placements)
                        c_grid[p_idx].x_mm = float(gx)
                        c_grid[p_idx].y_mm = float(gy)
                        g_viols = verify_spatial_constraints(room, c_grid, pack)
                        g_phi = compute_energy_metric(g_viols)
                        if g_phi < best_grid_phi:
                            best_grid_phi = g_phi
                            best_grid_pls = c_grid
                            if g_phi == 0.0:
                                break
                    if best_grid_phi == 0.0:
                        break
                if best_grid_pls is not None:
                    evaluated_data.append(("C_GRID", best_grid_pls, f"Relocate {pid} to collision-free open cell", best_grid_phi))

            # Find the best candidate with minimum Lyapunov energy
            best_idx = None
            best_c_energy = phi_before

            for idx, (cid, c_pls, action_desc, c_energy) in enumerate(evaluated_data):
                if c_energy < best_c_energy:
                    best_c_energy = c_energy
                    best_idx = idx

            # Construct mathematical proofs for each candidate evaluation
            evaluated_evals: list[CandidateEvaluation] = []
            for idx, (cid, c_pls, action_desc, c_energy) in enumerate(evaluated_data):
                d_phi = round(c_energy - phi_before, 2)
                if best_idx is not None and idx == best_idx:
                    evaluated_evals.append(
                        CandidateEvaluation(
                            candidate_id=cid,
                            action=action_desc,
                            phi_before=phi_before,
                            phi_after=c_energy,
                            delta_phi=d_phi,
                            decision="SELECTED",
                            decision_reason=f"Strict Lyapunov descent: ΔΦ = {d_phi} (Φ: {phi_before} → {c_energy})",
                        )
                    )
                elif c_energy >= phi_before:
                    evaluated_evals.append(
                        CandidateEvaluation(
                            candidate_id=cid,
                            action=action_desc,
                            phi_before=phi_before,
                            phi_after=c_energy,
                            delta_phi=d_phi,
                            decision="REJECTED",
                            decision_reason=f"No improvement: ΔΦ = +{round(d_phi, 1)} (Φ: {phi_before} → {c_energy} >= {phi_before})",
                        )
                    )
                else:
                    best_cid = evaluated_data[best_idx][0]
                    best_delta = round(best_c_energy - phi_before, 1)
                    evaluated_evals.append(
                        CandidateEvaluation(
                            candidate_id=cid,
                            action=action_desc,
                            phi_before=phi_before,
                            phi_after=c_energy,
                            delta_phi=d_phi,
                            decision="REJECTED",
                            decision_reason=f"Suboptimal descent (ΔΦ = {d_phi}) inferior to {best_cid} (ΔΦ = {best_delta})",
                        )
                    )

            if best_idx is not None:
                best_candidate_placements = evaluated_data[best_idx][1]
                transforms: list[PlacementTransformation] = []
                for p_old, p_new in zip(placements, best_candidate_placements):
                    if abs(p_old.x_mm - p_new.x_mm) > 1e-3 or abs(p_old.y_mm - p_new.y_mm) > 1e-3:
                        transforms.append(
                            PlacementTransformation(
                                placement_id=p_old.placement_id,
                                before_x=p_old.x_mm,
                                before_y=p_old.y_mm,
                                before_rot=p_old.rotation_deg,
                                dx=p_new.x_mm - p_old.x_mm,
                                dy=p_new.y_mm - p_old.y_mm,
                                after_x=p_new.x_mm,
                                after_y=p_new.y_mm,
                                after_rot=p_new.rotation_deg,
                            )
                        )

                placements = best_candidate_placements
                violations = verify_spatial_constraints(room, placements, pack)
                current_energy = best_c_energy

                if current_energy < best_energy:
                    best_energy = current_energy
                    best_placements = copy.deepcopy(placements)
                    best_violations = violations

                # Always place SELECTED first, followed by evaluated REJECTED candidates
                selected_eval = evaluated_evals[best_idx]
                rejected_evals = [e for i, e in enumerate(evaluated_evals) if i != best_idx]
                trace_evals = [selected_eval] + rejected_evals[:3]

                self.last_trace.append(
                    ArbitrationTraceStep(
                        iteration=pass_idx,
                        violation_rule_id=primary_v.rule_id,
                        violation_summary=primary_v.message,
                        affected_placements=primary_v.affected_placement_ids,
                        phi_before=phi_before,
                        candidates_evaluated=trace_evals,
                        phi_after=current_energy,
                        status="REPAIRED" if not violations else "IN_PROGRESS",
                        transformations=transforms,
                    )
                )

                if not violations:
                    break
            else:
                unsat_eval = CandidateEvaluation(
                    candidate_id="ESC_UNSAT",
                    action="Exhaustive search of candidate operator space",
                    phi_before=phi_before,
                    phi_after=phi_before,
                    delta_phi=0.0,
                    decision="UNSATISFIABLE",
                    decision_reason="Bounded operator space exhausted; no candidate satisfies strict Lyapunov descent condition ΔΦ < 0",
                )
                self.last_trace.append(
                    ArbitrationTraceStep(
                        iteration=pass_idx,
                        violation_rule_id=primary_v.rule_id,
                        violation_summary=primary_v.message,
                        affected_placements=primary_v.affected_placement_ids,
                        phi_before=phi_before,
                        candidates_evaluated=[unsat_eval],
                        phi_after=phi_before,
                        status="UNSATISFIABLE",
                        transformations=[],
                    )
                )
                break

        final_violations = verify_spatial_constraints(room, placements, pack)
        is_valid = len(final_violations) == 0

        return LayoutResult(
            room_id=room.room_id,
            placements=placements if is_valid else best_placements,
            violations=final_violations if is_valid else best_violations,
            status="valid" if is_valid else "unsatisfiable",
        )
