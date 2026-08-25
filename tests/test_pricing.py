from __future__ import annotations

import json
from pathlib import Path
import pytest

from rulebound.loader import load_asset_pack
from rulebound.models import Placement
from rulebound.pricing import price_placements, round_half_up, get_quantity_discount_bps, get_labour_rate_and_cost, get_freight_cost_and_trace

ROOT = Path(__file__).resolve().parents[1]
PACK = load_asset_pack(ROOT / "RuleBound_Round1_Release/data")


def test_round_half_up():
    assert round_half_up(10.4) == 10
    assert round_half_up(10.5) == 11
    assert round_half_up(10.6) == 11
    assert round_half_up(12741.88) == 12742
    assert round_half_up(6037.5) == 6038


def test_ref_quote_01_reconciliation():
    ref_path = ROOT / "RuleBound_Round1_Release/data/reference_quotes/REF-QUOTE-01.json"
    ref = json.loads(ref_path.read_text(encoding="utf-8"))

    placements = []
    pid = 1
    for line in ref["lines"]:
        for _ in range(line["quantity"]):
            placements.append(
                Placement(
                    placement_id=f"P{pid:03d}",
                    sku=line["sku"],
                    finish_id=line["finish_id"],
                    x_mm=100.0,
                    y_mm=100.0,
                    rotation_deg=0.0,
                )
            )
            pid += 1

    quote = price_placements("ROOM-01", placements, PACK, quote_id="REF-QUOTE-01")
    assert quote.status == "priced"
    assert quote.summary.grand_total_inr == 337964
    assert quote.summary.goods_after_adjustments_inr == 318547
    assert quote.summary.labour_inr == 6675
    assert quote.summary.freight_inr == 12742


def test_ref_quote_02_reconciliation():
    ref_path = ROOT / "RuleBound_Round1_Release/data/reference_quotes/REF-QUOTE-02.json"
    ref = json.loads(ref_path.read_text(encoding="utf-8"))

    placements = []
    pid = 1
    for line in ref["lines"]:
        for _ in range(line["quantity"]):
            placements.append(
                Placement(
                    placement_id=f"P{pid:03d}",
                    sku=line["sku"],
                    finish_id=line["finish_id"],
                    x_mm=100.0,
                    y_mm=100.0,
                    rotation_deg=0.0,
                )
            )
            pid += 1

    quote = price_placements("ROOM-02", placements, PACK, quote_id="REF-QUOTE-02")
    assert quote.status == "priced"
    assert quote.summary.grand_total_inr == 452853
    assert quote.summary.goods_after_adjustments_inr == 429630
    assert quote.summary.labour_inr == 6038
    assert quote.summary.freight_inr == 17185


def test_unpriced_sku_blocking():
    # RB-PRC-013: unpriced or fake SKU must block
    fake_placement = [Placement("P001", "NON-EXISTENT-SKU", "F01", 100.0, 100.0, 0.0)]
    quote = price_placements("ROOM-TEST", fake_placement, PACK)
    assert quote.status == "blocked"
    assert any("not found in catalog" in r for r in quote.blocking_reasons)


def test_incompatible_finish_blocking():
    # RB-PRC-013: finish not allowed on family/sku
    # Premium Leather Black (F18) is only compatible with chair, not desk
    bad_placement = [Placement("P001", "NW-DES-001", "F18", 100.0, 100.0, 0.0)]
    quote = price_placements("ROOM-TEST", bad_placement, PACK)
    assert quote.status == "blocked"
    assert any("incompatible" in r for r in quote.blocking_reasons)
