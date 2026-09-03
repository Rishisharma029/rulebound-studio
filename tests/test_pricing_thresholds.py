from decimal import Decimal
import pytest
from rulebound.pricing import (
    get_quantity_discount_bps,
    get_labour_rate_and_cost,
    get_freight_cost_and_trace,
    round_half_up,
)

def test_round_half_up_exact():
    # Exactly half rounds UP
    assert round_half_up(Decimal("10.5")) == 11
    assert round_half_up(Decimal("2.5")) == 3
    assert round_half_up(Decimal("3.5")) == 4
    assert round_half_up(Decimal("2.49999")) == 2
    assert round_half_up(Decimal("2.50001")) == 3

def test_quantity_discount_thresholds():
    # RB-PRC-009: 1-4 (0%), 5-9 (3%), 10-19 (7%), 20+ (10%)
    assert get_quantity_discount_bps(1) == 0
    assert get_quantity_discount_bps(4) == 0
    assert get_quantity_discount_bps(5) == 300
    assert get_quantity_discount_bps(9) == 300
    assert get_quantity_discount_bps(10) == 700
    assert get_quantity_discount_bps(19) == 700
    assert get_quantity_discount_bps(20) == 1000
    assert get_quantity_discount_bps(21) == 1000
    assert get_quantity_discount_bps(100) == 1000

def test_labour_rate_thresholds():
    # RB-PRC-011: <=240 (900/hr), 241-480 (800/hr), >480 (750/hr)
    rate_240, cost_240 = get_labour_rate_and_cost(240)
    assert rate_240 == 900
    assert cost_240 == 3600  # 240 * 900 / 60 = 3600

    rate_241, cost_241 = get_labour_rate_and_cost(241)
    assert rate_241 == 800
    assert cost_241 == round_half_up(Decimal(241) * Decimal(800) / Decimal(60))

    rate_480, cost_480 = get_labour_rate_and_cost(480)
    assert rate_480 == 800
    assert cost_480 == 6400  # 480 * 800 / 60 = 6400

    rate_481, cost_481 = get_labour_rate_and_cost(481)
    assert rate_481 == 750
    assert cost_481 == round_half_up(Decimal(481) * Decimal(750) / Decimal(60))

def test_freight_cost_thresholds():
    # RB-PRC-012: <=100,000 (Flat 5000), 100,001 - 250,000 (Flat 9000), >250,000 (4% / 400 bps)
    c_100k, t_100k = get_freight_cost_and_trace(100000)
    assert c_100k == 5000
    assert t_100k["band"] == "up_to_100000"

    c_100k_1, t_100k_1 = get_freight_cost_and_trace(100001)
    assert c_100k_1 == 9000
    assert t_100k_1["band"] == "100001_to_250000"

    c_250k, t_250k = get_freight_cost_and_trace(250000)
    assert c_250k == 9000
    assert t_250k["band"] == "100001_to_250000"

    c_250k_1, t_250k_1 = get_freight_cost_and_trace(250001)
    assert c_250k_1 == round_half_up(Decimal(250001) * Decimal(400) / Decimal(10000))
    assert t_250k_1["band"] == "above_250000"
    assert t_250k_1["percent_bps"] == 400


def test_quote_grand_total_exact_reconciliation():
    """
    Formally verifies that for all generated quotes:
    grand_total == goods_after_adjustments + labour + freight
    """
    from pathlib import Path
    from rulebound.loader import load_asset_pack
    from rulebound.pricing import price_placements, validate_quote_invariants
    from rulebound.models import Placement

    pack = load_asset_pack(Path(__file__).resolve().parents[1] / "RuleBound_Round1_Release/data")
    for room in pack.rooms:
        # Test varied quantity mixes triggering all discount and freight tiers
        for q in [4, 5, 9, 10, 19, 20]:
            placements = [
                Placement(f"P{i:03d}", "NW-DES-001", "F01", 1000.0, 1000.0, 0.0)
                for i in range(q)
            ]
            quote = price_placements(room.room_id, placements, pack)
            assert quote.status == "priced"
            assert quote.summary.grand_total_inr == (
                quote.summary.goods_after_adjustments_inr
                + quote.summary.labour_inr
                + quote.summary.freight_inr
            )
            is_valid, errors = validate_quote_invariants(quote, pack)
            assert is_valid is True
            assert len(errors) == 0
