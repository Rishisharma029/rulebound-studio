from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable

from rulebound.constraints import verify_spatial_constraints
from rulebound.loader import AssetPack
from rulebound.models import LayoutResult, Placement, RoomSpec, Violation


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
    Deterministic arbitration state machine enforcing bounded, terminating repair loops.
    """

    def __init__(self, max_passes: int = 50):
        self.max_passes = max_passes

    def arbitrate(
        self,
        room: RoomSpec,
        initial_placements: list[Placement],
        pack: AssetPack,
    ) -> LayoutResult:
        placements = copy.deepcopy(initial_placements)
        history: list[ArbitrationMetrics] = []

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
            history.append(
                ArbitrationMetrics(
                    pass_number=pass_idx,
                    violation_count=len(violations),
                    total_penetration_depth_mm=sum(
                        v.measured.get("penetration_depth_mm", 0.0) for v in violations
                    ),
                    total_clearance_deficit_mm=0.0,
                    energy_score=current_energy,
                )
            )

            # Apply deterministic repair operators based on highest-severity violation
            repaired_placements = self._apply_repairs(room, placements, violations, pack)
            new_violations = verify_spatial_constraints(room, repaired_placements, pack)
            new_energy = compute_energy_metric(new_violations)

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
                # If monotonic progress has stalled for 3 passes, try pruning non-essential items
                if plateau_count >= 3:
                    pruned_placements = self._prune_lowest_priority(repaired_placements, pack)
                    if len(pruned_placements) < len(repaired_placements):
                        placements = pruned_placements
                        violations = verify_spatial_constraints(room, placements, pack)
                        current_energy = compute_energy_metric(violations)
                        plateau_count = 0
                        continue
                    else:
                        break  # Infeasible / Unsatisfiable
                placements = repaired_placements
                violations = new_violations
                current_energy = new_energy

        # If loop terminated without reaching valid state: Escalate as unsatisfiable
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

    def _apply_repairs(
        self,
        room: RoomSpec,
        placements: list[Placement],
        violations: list[Violation],
        pack: AssetPack,
    ) -> list[Placement]:
        repaired = copy.deepcopy(placements)
        placement_by_id = {p.placement_id: p for p in repaired}

        for v in violations:
            if v.rule_id == "RB-GEO-005":  # Wall offset
                for pid in v.affected_placement_ids:
                    p = placement_by_id.get(pid)
                    if not p:
                        continue
                    # Nudge toward room center
                    cx = sum(pt[0] for pt in room.boundary_mm) / len(room.boundary_mm)
                    cy = sum(pt[1] for pt in room.boundary_mm) / len(room.boundary_mm)
                    dx = 150.0 if p.x_mm < cx else -150.0
                    dy = 150.0 if p.y_mm < cy else -150.0
                    p.x_mm += dx
                    p.y_mm += dy

            elif v.rule_id == "RB-GEO-006":  # Overlap
                if len(v.affected_placement_ids) >= 2:
                    p1 = placement_by_id.get(v.affected_placement_ids[0])
                    p2 = placement_by_id.get(v.affected_placement_ids[1])
                    if p1 and p2:
                        depth = v.measured.get("penetration_depth_mm", 100.0)
                        # Separate along X or Y
                        shift = depth + 100.0
                        if abs(p1.x_mm - p2.x_mm) > abs(p1.y_mm - p2.y_mm):
                            if p2.x_mm >= p1.x_mm:
                                p2.x_mm += shift
                            else:
                                p2.x_mm -= shift
                        else:
                            if p2.y_mm >= p1.y_mm:
                                p2.y_mm += shift
                            else:
                                p2.y_mm -= shift

            elif v.rule_id == "RB-GEO-002":  # Egress obstruction
                for pid in v.affected_placement_ids:
                    p = placement_by_id.get(pid)
                    if not p:
                        continue
                    # Shift away from door and target corridor
                    p.y_mm += 400.0

            elif v.rule_id == "RB-GEO-003":  # Door swing
                for pid in v.affected_placement_ids:
                    p = placement_by_id.get(pid)
                    if not p:
                        continue
                    p.x_mm += 300.0
                    p.y_mm += 300.0

            elif v.rule_id == "RB-GEO-007":  # Outside room
                for pid in v.affected_placement_ids:
                    p = placement_by_id.get(pid)
                    if not p:
                        continue
                    cx = sum(pt[0] for pt in room.boundary_mm) / len(room.boundary_mm)
                    cy = sum(pt[1] for pt in room.boundary_mm) / len(room.boundary_mm)
                    p.x_mm = p.x_mm * 0.9 + cx * 0.1
                    p.y_mm = p.y_mm * 0.9 + cy * 0.1

        return repaired

    def _prune_lowest_priority(self, placements: list[Placement], pack: AssetPack) -> list[Placement]:
        if not placements:
            return []
        # Priority order to keep: desk > chair > collaboration > storage > accessory
        priority = {"accessory": 1, "storage": 2, "collaboration": 3, "chair": 4, "desk": 5}
        sorted_placements = sorted(
            placements,
            key=lambda p: priority.get(pack.catalog_by_sku[p.sku].family, 0)
            if p.sku in pack.catalog_by_sku
            else 0,
        )
        # Drop the lowest priority item
        return [p for p in placements if p.placement_id != sorted_placements[0].placement_id]
