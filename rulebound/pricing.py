from __future__ import annotations

import decimal
from decimal import Decimal
from typing import Any

from rulebound.loader import AssetPack
from rulebound.models import (
    CatalogItem,
    Finish,
    Placement,
    PriceTrace,
    QuoteLine,
    QuoteResult,
    QuoteSummary,
)


def round_half_up(value: int | float | Decimal) -> int:
    """
    Standard mathematical half-up rounding to nearest integer INR.
    Used universally across RuleBound pricing engine.
    """
    d = Decimal(str(value))
    return int(d.quantize(Decimal("1"), rounding=decimal.ROUND_HALF_UP))


def get_quantity_discount_bps(quantity: int) -> int:
    """
    RB-PRC-009: Quantity discount tiers.
    - 1-4: 0 bps
    - 5-9: 300 bps (3%)
    - 10-19: 700 bps (7%)
    - 20+: 1000 bps (10%)
    """
    if quantity < 5:
        return 0
    elif quantity < 10:
        return 300
    elif quantity < 20:
        return 700
    else:
        return 1000


def get_labour_rate_and_cost(total_minutes: int) -> tuple[int, int]:
    """
    RB-PRC-011: Labour rates by cumulative minutes band.
    - <= 240 mins: ₹900/hr
    - 241-480 mins: ₹800/hr
    - > 480 mins: ₹750/hr
    """
    if total_minutes <= 240:
        rate = 900
    elif total_minutes <= 480:
        rate = 800
    else:
        rate = 750

    cost = round_half_up(Decimal(total_minutes) * Decimal(rate) / Decimal(60))
    return rate, cost


def get_freight_cost_and_trace(goods_net_inr: int) -> tuple[int, dict[str, Any]]:
    """
    RB-PRC-012: Freight tiered on total net goods.
    - <= 100,000: flat ₹5,000
    - 100,001 - 250,000: flat ₹9,000
    - > 250,000: 4% of net goods (400 bps), round half up
    """
    if goods_net_inr <= 100000:
        return 5000, {
            "band": "up_to_100000",
            "flat_inr": 5000,
            "goods_inr": goods_net_inr,
        }
    elif goods_net_inr <= 250000:
        return 9000, {
            "band": "100001_to_250000",
            "flat_inr": 9000,
            "goods_inr": goods_net_inr,
        }
    else:
        cost = round_half_up(Decimal(goods_net_inr) * Decimal(400) / Decimal(10000))
        return cost, {
            "band": "above_250000",
            "percent_bps": 400,
            "goods_inr": goods_net_inr,
        }


def price_placements(
    room_id: str,
    placements: list[Placement],
    pack: AssetPack,
    quote_id: str | None = None,
) -> QuoteResult:
    """
    Pure deterministic pricing engine executing PRICING_SPEC.md.
    Guarantees byte-identical, line-traceable, mathematically reconciled outputs.
    """
    qid = quote_id or f"QUOTE-{room_id}"

    if not placements:
        return QuoteResult(
            quote_id=qid,
            room_id=room_id,
            currency="INR",
            lines=[],
            summary={"grand_total_inr": 0},
            summary_trace=[],
            status="blocked",
            blocking_reasons=["No placements provided to pricing engine."],
        )

    # Aggregate quantities by (sku, finish_id)
    aggregated: dict[tuple[str, str], int] = {}
    for p in placements:
        key = (p.sku, p.finish_id)
        aggregated[key] = aggregated.get(key, 0) + 1

    lines: list[QuoteLine] = []
    blocking_reasons: list[str] = []
    total_labour_minutes = 0
    line_index = 1

    for (sku, finish_id), qty in sorted(aggregated.items()):
        line_id = f"L{line_index:03d}"
        line_index += 1

        catalog_item = pack.catalog_by_sku.get(sku)
        finish = pack.finishes_by_id.get(finish_id)

        # Validation under RB-PRC-013
        if not catalog_item:
            blocking_reasons.append(f"RB-PRC-013: SKU '{sku}' not found in catalog.")
            continue
        if not finish:
            blocking_reasons.append(f"RB-PRC-013: Finish '{finish_id}' not found in finishes.")
            continue
        if finish_id not in catalog_item.compatible_finish_ids:
            blocking_reasons.append(
                f"RB-PRC-013: Finish '{finish_id}' is incompatible with SKU '{sku}'."
            )

        unit_price = catalog_item.list_price_inr
        base_amount = unit_price * qty
        uplift_bps = finish.uplift_bps
        finish_uplift = round_half_up(Decimal(base_amount) * Decimal(uplift_bps) / Decimal(10000))
        discount_bps = get_quantity_discount_bps(qty)
        quantity_discount = round_half_up(Decimal(base_amount) * Decimal(discount_bps) / Decimal(10000))
        net_goods = base_amount + finish_uplift - quantity_discount

        total_labour_minutes += catalog_item.labour_minutes * qty

        traces = [
            PriceTrace(
                rule_id="CATALOG",
                inputs={"unit_price": unit_price, "quantity": qty},
                amount_inr=base_amount,
            ),
            PriceTrace(
                rule_id="RB-PRC-010",
                inputs={"uplift_bps": uplift_bps, "base_amount_inr": base_amount},
                amount_inr=finish_uplift,
            ),
            PriceTrace(
                rule_id="RB-PRC-009",
                inputs={"discount_bps": discount_bps, "base_amount_inr": base_amount},
                amount_inr=-quantity_discount if quantity_discount > 0 else 0,
            ),
        ]

        lines.append(
            QuoteLine(
                line_id=line_id,
                sku=sku,
                finish_id=finish_id,
                quantity=qty,
                unit_list_price_inr=unit_price,
                base_amount_inr=base_amount,
                finish_uplift_inr=finish_uplift,
                quantity_discount_inr=quantity_discount,
                net_goods_inr=net_goods,
                trace=traces,
            )
        )

    if blocking_reasons:
        return QuoteResult(
            quote_id=qid,
            room_id=room_id,
            currency="INR",
            lines=lines,
            summary={"grand_total_inr": 0},
            summary_trace=[],
            status="blocked",
            blocking_reasons=sorted(blocking_reasons),
        )

    total_net_goods = sum(line.net_goods_inr for line in lines)
    labour_rate, labour_inr = get_labour_rate_and_cost(total_labour_minutes)
    freight_inr, freight_trace_inputs = get_freight_cost_and_trace(total_net_goods)
    grand_total_inr = total_net_goods + labour_inr + freight_inr

    summary = QuoteSummary(
        goods_after_adjustments_inr=total_net_goods,
        labour_minutes=total_labour_minutes,
        labour_rate_inr_per_hour=labour_rate,
        labour_inr=labour_inr,
        freight_inr=freight_inr,
        grand_total_inr=grand_total_inr,
    )

    summary_trace = [
        PriceTrace(
            rule_id="RB-PRC-011",
            inputs={
                "total_labour_minutes": total_labour_minutes,
                "rate_inr_per_hour": labour_rate,
            },
            amount_inr=labour_inr,
        ),
        PriceTrace(
            rule_id="RB-PRC-012",
            inputs=freight_trace_inputs,
            amount_inr=freight_inr,
        ),
    ]

    return QuoteResult(
        quote_id=qid,
        room_id=room_id,
        currency="INR",
        lines=lines,
        summary=summary,
        summary_trace=summary_trace,
        status="priced",
    )
