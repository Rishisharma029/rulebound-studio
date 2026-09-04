"""
Layout "What changed?" diff.

Given a BEFORE and AFTER placement set, reports moved SKUs, rule-level
clearance deltas, and Lyapunov energy Φ before → after.
"""
from __future__ import annotations

import re
from typing import Any

from rulebound.arbitration import compute_energy_metric
from rulebound.constraints import audit_spatial_constraints, verify_spatial_constraints
from rulebound.loader import AssetPack
from rulebound.models import Placement, RoomSpec


def _placements_by_id(placements: list[Placement]) -> dict[str, Placement]:
    return {p.placement_id: p for p in placements}


def _parse_measured_mm(measured: Any) -> float | None:
    if measured is None:
        return None
    if isinstance(measured, (int, float)):
        return float(measured)
    m = re.search(r"([-+]?\d+(?:\.\d+)?)", str(measured))
    return float(m.group(1)) if m else None


def _audit_map(audits: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {a["rule_id"]: a for a in audits if "rule_id" in a}


def diff_layouts(
    room: RoomSpec,
    pack: AssetPack,
    before: list[Placement],
    after: list[Placement],
    reason_hint: str | None = None,
) -> dict[str, Any]:
    """
    Produce a reviewer-facing placement and constraint delta.

    Example effect line:
      egress clearance 730 → 1130mm
      Φ 6400 → 0
    """
    before_v = verify_spatial_constraints(room, before, pack)
    after_v = verify_spatial_constraints(room, after, pack)
    phi_before = float(compute_energy_metric(before_v))
    phi_after = float(compute_energy_metric(after_v))

    before_audit = audit_spatial_constraints(room, before, pack)
    after_audit = audit_spatial_constraints(room, after, pack)
    ba = _audit_map(before_audit)
    aa = _audit_map(after_audit)

    before_map = _placements_by_id(before)
    after_map = _placements_by_id(after)

    moved: list[dict[str, Any]] = []
    added: list[str] = []
    removed: list[str] = []

    for pid, ap in after_map.items():
        bp = before_map.get(pid)
        if bp is None:
            added.append(pid)
            continue
        dx = round(ap.x_mm - bp.x_mm, 2)
        dy = round(ap.y_mm - bp.y_mm, 2)
        drot = round(ap.rotation_deg - bp.rotation_deg, 2)
        sku_changed = ap.sku != bp.sku
        if dx or dy or drot or sku_changed:
            moved.append({
                "placement_id": pid,
                "sku": ap.sku,
                "before": {"x_mm": bp.x_mm, "y_mm": bp.y_mm, "rotation_deg": bp.rotation_deg, "sku": bp.sku},
                "after": {"x_mm": ap.x_mm, "y_mm": ap.y_mm, "rotation_deg": ap.rotation_deg, "sku": ap.sku},
                "delta_mm": {"dx": dx, "dy": dy, "drot": drot},
            })

    for pid in before_map:
        if pid not in after_map:
            removed.append(pid)

    # Infer primary reason: first violation present before that is gone after
    before_rules = [v.rule_id for v in before_v]
    after_rules = {v.rule_id for v in after_v}
    resolved_rules = [r for r in before_rules if r not in after_rules]
    reason_rule = reason_hint or (resolved_rules[0] if resolved_rules else (before_rules[0] if before_rules else "RB-GEO-002"))
    reason_messages = {
        "RB-GEO-001": "primary walkway clearance",
        "RB-GEO-002": "egress obstruction",
        "RB-GEO-003": "door swing encroachment",
        "RB-GEO-004": "desk rear clearance",
        "RB-GEO-005": "perimeter wall offset",
        "RB-GEO-006": "footprint overlap",
        "RB-GEO-007": "boundary containment",
        "RB-GEO-008": "chair pull-out clearance",
    }
    reason_text = f"{reason_rule} {reason_messages.get(reason_rule, 'constraint repair')}"

    effects: list[dict[str, Any]] = []
    for rule_id in sorted(set(list(ba.keys()) + list(aa.keys()))):
        b_mm = _parse_measured_mm(ba.get(rule_id, {}).get("measured"))
        a_mm = _parse_measured_mm(aa.get(rule_id, {}).get("measured"))
        b_st = ba.get(rule_id, {}).get("status")
        a_st = aa.get(rule_id, {}).get("status")
        if b_mm is None or a_mm is None:
            continue
        if abs(a_mm - b_mm) < 0.5 and b_st == a_st:
            continue
        unit = "mm"
        measured_str = str(aa.get(rule_id, {}).get("measured") or "")
        if "%" in measured_str:
            unit = "%"
        elif "depth" in measured_str:
            unit = "mm depth"
        effects.append({
            "rule_id": rule_id,
            "before": b_mm,
            "after": a_mm,
            "unit": unit,
            "status_before": b_st,
            "status_after": a_st,
            "label": f"{rule_id} {b_mm:.0f} → {a_mm:.0f}{unit}",
        })

    egress_effect = next((e for e in effects if e["rule_id"] == "RB-GEO-002"), None)
    hero_move = moved[0] if moved else None

    ascii_lines = ["WHAT CHANGED?", ""]
    if hero_move:
        ascii_lines.extend([
            "BEFORE",
            f"{hero_move['sku']} {hero_move['placement_id']}: x={hero_move['before']['x_mm']:.0f} y={hero_move['before']['y_mm']:.0f}",
            "",
            "AFTER",
            f"{hero_move['sku']} {hero_move['placement_id']}: x={hero_move['after']['x_mm']:.0f} y={hero_move['after']['y_mm']:.0f}",
            "",
        ])
    ascii_lines.append(f"Reason:\n{reason_text}")
    ascii_lines.append("")
    ascii_lines.append("Effect:")
    if egress_effect:
        ascii_lines.append(
            f"egress clearance {egress_effect['before']:.0f} → {egress_effect['after']:.0f}mm"
        )
    for e in effects[:4]:
        if e["rule_id"] != "RB-GEO-002":
            ascii_lines.append(e["label"])
    ascii_lines.append(f"Φ {phi_before:.0f} → {phi_after:.0f}")

    return {
        "room_id": room.room_id,
        "moved": moved,
        "added": added,
        "removed": removed,
        "reason": {
            "rule_id": reason_rule,
            "text": reason_text,
            "resolved_rules": resolved_rules,
        },
        "effects": effects,
        "energy": {
            "phi_before": round(phi_before, 1),
            "phi_after": round(phi_after, 1),
            "transition": f"Φ {phi_before:.0f} → {phi_after:.0f}",
        },
        "violation_count": {
            "before": len(before_v),
            "after": len(after_v),
        },
        "ascii_card": "\n".join(ascii_lines),
        "headline_move": hero_move,
    }
