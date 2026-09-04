"""
Counterfactual layout explainer.

Answers: "Why not Layout A / C?" given the selected candidate (typically B).
All comparisons are deterministic functions of ranked candidate scorecards.
"""
from __future__ import annotations

from typing import Any

from rulebound.loader import AssetPack
from rulebound.models import RoomSpec
from rulebound.optimizer import evaluate_and_rank_candidates


def _metric_pct(metrics: dict[str, Any], name: str) -> float:
    raw = metrics.get(name, "0")
    return float(str(raw).replace("%", "").strip() or 0)


def explain_counterfactual(
    room: RoomSpec,
    pack: AssetPack,
    rejected_candidate_id: str = "Candidate A",
    rankings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Compare a rejected candidate against the SELECTED layout and emit a
    human-readable rejection card (cost, circulation, accessibility, quality).
    """
    if rankings is None:
        _, rankings = evaluate_and_rank_candidates(room, pack)

    selected = next((c for c in rankings if c.get("decision") == "SELECTED"), rankings[0])
    rejected = next((c for c in rankings if c["candidate_id"] == rejected_candidate_id), None)
    if rejected is None:
        alts = [c for c in rankings if c["candidate_id"] != selected["candidate_id"]]
        rejected = alts[0] if alts else selected

    sel_metrics = selected.get("metrics") or {}
    rej_metrics = rejected.get("metrics") or {}

    sel_cost = int(selected.get("quote_total_inr") or 0)
    rej_cost = int(rejected.get("quote_total_inr") or 0)
    cost_delta = rej_cost - sel_cost

    sel_circ = _metric_pct(sel_metrics, "Circulation efficiency")
    rej_circ = _metric_pct(rej_metrics, "Circulation efficiency")
    circ_delta = round(rej_circ - sel_circ, 1)

    sel_access = _metric_pct(sel_metrics, "Accessibility margin")
    rej_access = _metric_pct(rej_metrics, "Accessibility margin")
    access_delta = round(rej_access - sel_access, 1)
    access_violations = 1 if rej_access < 90.0 else 0

    sel_q = float(selected.get("score") or 0)
    rej_q = float(rejected.get("score") or 0)

    rejection_bullets: list[str] = []
    if cost_delta > 0:
        rejection_bullets.append(f"+ ₹{cost_delta:,} cost")
    elif cost_delta < 0:
        rejection_bullets.append(f"− ₹{abs(cost_delta):,} cost (cheaper, but lower quality)")
    else:
        rejection_bullets.append("same catalog cost band")

    if circ_delta < 0:
        rejection_bullets.append(f"− {abs(circ_delta):.1f}% circulation score")
    elif circ_delta > 0:
        rejection_bullets.append(f"+ {circ_delta:.1f}% circulation (insufficient to offset other deficits)")

    if access_violations:
        rejection_bullets.append(f"− {access_violations} accessibility margin shortfall ({rej_access:.1f}% vs {sel_access:.1f}%)")
    elif access_delta < 0:
        rejection_bullets.append(f"− {abs(access_delta):.1f}% accessibility margin")

    selection_reasons: list[str] = [
        "✓ valid (hard constraints satisfied)",
        f"✓ {sel_q:.1f} quality (vs {rej_q:.1f})",
    ]
    if sel_cost <= rej_cost:
        selection_reasons.append("✓ lower or equal cost")
    else:
        selection_reasons.append("✓ higher quality outweighs modest cost delta")
    if sel_circ >= rej_circ:
        selection_reasons.append("✓ better circulation")
    if sel_access >= rej_access:
        selection_reasons.append("✓ better accessibility margin")

    ascii_card = (
        f"{rejected['candidate_id']} rejected\n"
        + "\n".join(rejection_bullets)
        + f"\n\n{selected['candidate_id']} selected because:\n"
        + "\n".join(selection_reasons)
    )

    return {
        "room_id": room.room_id,
        "headline": f"Why not {rejected['candidate_id']}?",
        "selected": {
            "candidate_id": selected["candidate_id"],
            "name": selected.get("name"),
            "score": sel_q,
            "cost_inr": sel_cost,
            "circulation_pct": sel_circ,
            "accessibility_pct": sel_access,
            "status": selected.get("status", "VALID"),
            "decision": "SELECTED",
        },
        "rejected": {
            "candidate_id": rejected["candidate_id"],
            "name": rejected.get("name"),
            "score": rej_q,
            "cost_inr": rej_cost,
            "circulation_pct": rej_circ,
            "accessibility_pct": rej_access,
            "status": rejected.get("status", "VALID"),
            "decision": rejected.get("decision", "SUBOPTIMAL"),
            "reason": rejected.get("reason", ""),
        },
        "deltas": {
            "cost_inr": cost_delta,
            "quality": round(rej_q - sel_q, 1),
            "circulation_pct": circ_delta,
            "accessibility_pct": access_delta,
            "accessibility_margin_violations": access_violations,
        },
        "rejection_bullets": rejection_bullets,
        "selection_reasons": selection_reasons,
        "ascii_card": ascii_card,
        "alternatives": [
            {
                "candidate_id": c["candidate_id"],
                "name": c.get("name"),
                "score": c.get("score"),
                "decision": c.get("decision"),
            }
            for c in rankings
            if c["candidate_id"] != selected["candidate_id"]
        ],
    }


def explain_all_counterfactuals(room: RoomSpec, pack: AssetPack) -> dict[str, Any]:
    _, rankings = evaluate_and_rank_candidates(room, pack)
    selected = next((c for c in rankings if c.get("decision") == "SELECTED"), rankings[0])
    rejected_ids = [c["candidate_id"] for c in rankings if c["candidate_id"] != selected["candidate_id"]]
    cards = [explain_counterfactual(room, pack, rid, rankings=rankings) for rid in rejected_ids]
    return {
        "room_id": room.room_id,
        "selected_candidate_id": selected["candidate_id"],
        "explanations": cards,
        "explanations_by_id": {c["rejected"]["candidate_id"]: c for c in cards},
    }
