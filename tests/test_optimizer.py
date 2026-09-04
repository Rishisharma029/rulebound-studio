from pathlib import Path
import pytest

from rulebound.loader import load_asset_pack
from rulebound.optimizer import (
    evaluate_layout_quality,
    evaluate_and_rank_candidates,
    LayoutQualityReport,
    QualityMetricDimension,
)

ROOT = Path(__file__).resolve().parents[1]
PACK = load_asset_pack(ROOT / "RuleBound_Round1_Release/data")


def test_layout_quality_dimensions_structure():
    room = PACK.rooms_by_id["ROOM-01"]
    report, rankings = evaluate_and_rank_candidates(room, PACK)

    assert isinstance(report, LayoutQualityReport)
    assert len(report.dimensions) == 8

    keys = [d.key for d in report.dimensions]
    expected_keys = [
        "hard_constraints",
        "brief_satisfaction",
        "space_utilization",
        "circulation_efficiency",
        "furniture_count_compliance",
        "preference_match",
        "accessibility_margin",
        "cost_efficiency",
    ]
    assert keys == expected_keys

    # Sum of weights equals 1.0
    total_weight = sum(d.weight for d in report.dimensions)
    assert abs(total_weight - 1.0) < 1e-4

    # Mathematical consistency: final score equals sum of weighted contributions
    expected_score = round(sum(d.score * d.weight for d in report.dimensions), 1)
    assert report.final_quality_score == expected_score


def test_multi_candidate_ranking_and_selection():
    room = PACK.rooms_by_id["ROOM-01"]
    report, rankings = evaluate_and_rank_candidates(room, PACK)

    assert len(rankings) == 3
    candidate_ids = [c["candidate_id"] for c in rankings]
    assert candidate_ids == ["Candidate B", "Candidate A", "Candidate C"]

    # Candidate B is selected as optimal
    assert rankings[0]["candidate_id"] == "Candidate B"
    assert rankings[0]["decision"] == "SELECTED"
    assert rankings[0]["score"] >= rankings[1]["score"]
    assert rankings[1]["score"] >= rankings[2]["score"]

    # Scores match expected decision quality targets
    assert rankings[0]["score"] == 94.1
    assert rankings[1]["score"] == 91.4
    assert rankings[2]["score"] == 88.7

    # Suboptimal decisions have explicit rationales
    assert rankings[1]["decision"] == "SUBOPTIMAL"
    assert "circulation efficiency" in rankings[1]["reason"].lower()
    assert rankings[2]["decision"] == "SUBOPTIMAL"
    assert "accessibility margin" in rankings[2]["reason"].lower()

    # ASCII card formatting produces complete audit block
    ascii_card = report.render_ascii_card()
    assert "LAYOUT QUALITY" in ascii_card
    assert "FINAL QUALITY SCORE" in ascii_card
    assert "Candidate B" in ascii_card
    assert "SELECTED (OPTIMAL)" in ascii_card
