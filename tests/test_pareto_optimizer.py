from pathlib import Path
import pytest

from rulebound.loader import load_asset_pack
from rulebound.optimizer import (
    build_pareto_optimization_suite,
    compute_pareto_frontier,
    generate_deterministic_20_candidates,
    ParetoFrontierReport,
)

ROOT = Path(__file__).resolve().parents[1]
PACK = load_asset_pack(ROOT / "RuleBound_Round1_Release/data")


def test_20_deterministic_candidates_generation():
    room = PACK.rooms_by_id["ROOM-01"]
    candidates = generate_deterministic_20_candidates(room, PACK)

    assert len(candidates) == 20
    candidate_ids = [c.candidate_id for c in candidates]
    expected_ids = [f"C{i:02d}" for i in range(1, 21)]
    assert candidate_ids == expected_ids

    # Verify topologies represented
    archetypes = {c.archetype for c in candidates}
    assert archetypes == {"dual_pod", "perimeter", "high_density", "central_hub"}

    # Phase 1: Feasibility separation
    feasible_cands = [c for c in candidates if c.is_feasible]
    infeasible_cands = [c for c in candidates if not c.is_feasible]

    assert len(feasible_cands) >= 16
    assert len(infeasible_cands) >= 2  # C15 and C20 forced infeasible test cases
    for inf in infeasible_cands:
        assert inf.energy_score > 0.0
        assert inf.violation_count > 0

    for feas in feasible_cands:
        assert feas.energy_score == 0.0
        assert feas.violation_count == 0


def test_pareto_frontier_dominance_and_selection():
    room = PACK.rooms_by_id["ROOM-01"]
    suite = build_pareto_optimization_suite(room, PACK)

    assert isinstance(suite, ParetoFrontierReport)
    assert suite.separation_statement == "RuleBound separates feasibility from optimization."
    assert len(suite.candidates) == 20
    assert len(suite.pareto_frontier_ids) > 0

    # Infeasible candidates can NEVER be on the Pareto frontier
    for c in suite.candidates:
        if not c.is_feasible:
            assert not c.is_pareto_optimal
            assert c.selection_status == "INFEASIBLE"
            assert c.candidate_id not in suite.pareto_frontier_ids

    # Selected candidate must be Pareto-optimal and have status 'SELECTED'
    selected = next(c for c in suite.candidates if c.candidate_id == suite.selected_candidate_id)
    assert selected.is_pareto_optimal
    assert selected.is_selected
    assert selected.selection_status == "SELECTED"
    assert selected.is_feasible
    assert selected.energy_score == 0.0
    assert selected.quality_score >= 90.0

    # Dominated candidates must list their dominating candidate IDs
    dominated_cands = [c for c in suite.candidates if c.is_feasible and not c.is_pareto_optimal]
    for dom in dominated_cands:
        assert len(dom.dominating_candidates) > 0
        assert dom.selection_status == "DOMINATED"
        assert "Dominated by" in dom.suboptimal_reason

    # ASCII plot output contains all required elements
    plot = suite.render_ascii_plot()
    assert "RULEBOUND MULTI-OBJECTIVE PARETO FRONTIER PLOT" in plot
    assert "RuleBound separates feasibility from optimization" in plot
    assert suite.selected_candidate_id in plot
    assert "SELECTED PARETO-OPTIMAL" in plot


def test_pareto_dominance_strictly_respects_cost_and_quality():
    """Formally proves that no candidate in the Pareto frontier is dominated by another candidate."""
    room = PACK.rooms_by_id["ROOM-01"]
    suite = build_pareto_optimization_suite(room, PACK)

    frontier_cands = [c for c in suite.candidates if c.is_pareto_optimal]
    assert len(frontier_cands) >= 2

    # Check that no frontier candidate dominates another frontier candidate
    for a in frontier_cands:
        for b in frontier_cands:
            if a.candidate_id != b.candidate_id:
                # It is impossible for a to strictly dominate b
                a_dominates_b = (a.quality_score >= b.quality_score and a.cost_inr <= b.cost_inr) and (
                    a.quality_score > b.quality_score or a.cost_inr < b.cost_inr
                )
                assert not a_dominates_b, f"{a.candidate_id} improperly dominates {b.candidate_id} on the frontier!"
