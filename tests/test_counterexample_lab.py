from __future__ import annotations

from pathlib import Path
import pytest

from rulebound.counterexample import (
    SCENARIOS,
    get_counterexample_scenarios,
    build_scenario_placements,
    execute_counterexample_laboratory,
)
from rulebound.loader import load_asset_pack

ROOT = Path(__file__).resolve().parents[1]
PACK = load_asset_pack(ROOT / "RuleBound_Round1_Release/data")
ROOM = PACK.rooms_by_id["ROOM-01"]


def test_scenario_catalog_count():
    scenarios = get_counterexample_scenarios()
    assert len(scenarios) == 7
    ids = [s["id"] for s in scenarios]
    assert "overlap" in ids
    assert "egress" in ids
    assert "door_swing" in ids
    assert "wall" in ids
    assert "desk_rear" in ids
    assert "chair_pullout" in ids
    assert "impossible" in ids


@pytest.mark.parametrize("scenario_id", ["overlap", "egress", "door_swing", "wall", "desk_rear", "chair_pullout"])
def test_repairable_counterexample_scenarios(scenario_id: str):
    res = execute_counterexample_laboratory(ROOM, PACK, scenario_id)

    # Phase 1: Candidate invalid
    assert res["phase1_invalid"]["status"] == "Candidate invalid"
    assert res["phase1_invalid"]["phi_initial"] > 0
    assert len(res["phase1_invalid"]["rule_id"]) > 0
    assert len(res["phase1_invalid"]["measurement"]) > 0

    # Phase 2: Arbitration
    assert len(res["phase2_arbitration"]["candidates"]) >= 2
    decisions = [c["decision"] for c in res["phase2_arbitration"]["candidates"]]
    assert "rejected" in decisions
    assert "selected" in decisions

    # Phase 3: Resolution to VALID
    assert res["phase3_resolution"]["status"] == "VALID"
    assert res["phase3_resolution"]["is_valid"] is True
    assert res["phase3_resolution"]["phi_final"] == 0
    assert "→ 0" in res["phase3_resolution"]["energy_transition"]


def test_impossible_counterexample_scenario():
    res = execute_counterexample_laboratory(ROOM, PACK, "impossible")

    # Phase 1: Invalid
    assert res["phase1_invalid"]["status"] == "Candidate invalid"
    assert res["phase1_invalid"]["phi_initial"] > 0

    # Phase 3: Unsatisfiable
    assert res["phase3_resolution"]["status"] == "UNSATISFIABLE"
    assert res["phase3_resolution"]["is_valid"] is False
    assert len(res["phase3_resolution"]["trade_offs"]) == 3
