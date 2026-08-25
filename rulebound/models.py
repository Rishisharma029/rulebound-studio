from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class DoorSpec:
    door_id: str
    wall: Literal["north", "south", "east", "west"]
    offset_mm: float
    width_mm: float
    swing: Literal["inward_left", "inward_right", "outward_left", "outward_right"]


@dataclass(frozen=True)
class WindowSpec:
    wall: Literal["north", "south", "east", "west"]
    offset_mm: float
    width_mm: float


@dataclass(frozen=True)
class EgressSpec:
    from_door_id: str
    to_point_mm: tuple[float, float]
    min_width_mm: float = 1100.0


@dataclass(frozen=True)
class RoomSpec:
    room_id: str
    name: str
    boundary_mm: list[tuple[float, float]]
    doors: list[DoorSpec]
    windows: list[WindowSpec]
    egress: EgressSpec
    capacity: int


@dataclass(frozen=True)
class DimensionsMM:
    width: float
    depth: float
    height: float


@dataclass(frozen=True)
class CatalogItem:
    sku: str
    family: Literal["desk", "chair", "storage", "collaboration", "accessory"]
    name: str
    dimensions_mm: DimensionsMM
    list_price_inr: int
    labour_minutes: int
    lead_time_days: int
    compatible_finish_ids: list[str]


@dataclass(frozen=True)
class Finish:
    finish_id: str
    name: str
    uplift_bps: int
    compatible_families: list[str]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    kind: str
    severity: Literal["error", "pricing", "warning"]
    message: str = ""
    target: str | None = None
    family: str | None = None
    value_mm: float | None = None
    tiers: list[dict[str, Any]] = field(default_factory=list)
    source: str | None = None


@dataclass
class Placement:
    placement_id: str
    sku: str
    finish_id: str
    x_mm: float
    y_mm: float
    rotation_deg: float  # 0, 90, 180, 270

    def to_dict(self) -> dict[str, Any]:
        return {
            "placement_id": self.placement_id,
            "sku": self.sku,
            "finish_id": self.finish_id,
            "x_mm": round(float(self.x_mm), 2),
            "y_mm": round(float(self.y_mm), 2),
            "rotation_deg": round(float(self.rotation_deg), 2),
        }


@dataclass
class Violation:
    violation_id: str
    rule_id: str
    message: str
    affected_placement_ids: list[str]
    repair_options: list[dict[str, Any]] = field(default_factory=list)
    measured: dict[str, Any] = field(default_factory=dict)
    required: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "violation_id": self.violation_id,
            "rule_id": self.rule_id,
            "message": self.message,
            "affected_placement_ids": list(self.affected_placement_ids),
            "repair_options": self.repair_options,
        }
        if self.measured:
            res["measured"] = self.measured
        if self.required:
            res["required"] = self.required
        return res


@dataclass
class LayoutResult:
    room_id: str
    placements: list[Placement]
    violations: list[Violation] = field(default_factory=list)
    status: Literal["valid", "invalid", "unsatisfiable"] = "valid"

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "placements": [p.to_dict() for p in self.placements],
            "violations": [v.to_dict() for v in self.violations],
            "status": self.status,
        }


@dataclass
class PriceTrace:
    rule_id: str
    inputs: dict[str, Any]
    amount_inr: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "inputs": self.inputs,
            "amount_inr": self.amount_inr,
        }


@dataclass
class QuoteLine:
    line_id: str
    sku: str
    finish_id: str
    quantity: int
    unit_list_price_inr: int
    base_amount_inr: int
    finish_uplift_inr: int
    quantity_discount_inr: int
    net_goods_inr: int
    trace: list[PriceTrace] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "sku": self.sku,
            "finish_id": self.finish_id,
            "quantity": self.quantity,
            "unit_list_price_inr": self.unit_list_price_inr,
            "base_amount_inr": self.base_amount_inr,
            "finish_uplift_inr": self.finish_uplift_inr,
            "quantity_discount_inr": self.quantity_discount_inr,
            "net_goods_inr": self.net_goods_inr,
            "trace": [t.to_dict() for t in self.trace],
        }


@dataclass
class QuoteSummary:
    goods_after_adjustments_inr: int
    labour_minutes: int
    labour_rate_inr_per_hour: int
    labour_inr: int
    freight_inr: int
    grand_total_inr: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "goods_after_adjustments_inr": self.goods_after_adjustments_inr,
            "labour_minutes": self.labour_minutes,
            "labour_rate_inr_per_hour": self.labour_rate_inr_per_hour,
            "labour_inr": self.labour_inr,
            "freight_inr": self.freight_inr,
            "grand_total_inr": self.grand_total_inr,
        }


@dataclass
class QuoteResult:
    quote_id: str
    room_id: str
    currency: Literal["INR"] = "INR"
    lines: list[QuoteLine] = field(default_factory=list)
    summary: QuoteSummary | dict[str, Any] = field(default_factory=dict)
    summary_trace: list[PriceTrace] = field(default_factory=list)
    status: Literal["priced", "blocked"] = "priced"
    blocking_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "quote_id": self.quote_id,
            "room_id": self.room_id,
            "currency": self.currency,
            "lines": [line.to_dict() for line in self.lines],
            "summary": self.summary.to_dict() if isinstance(self.summary, QuoteSummary) else self.summary,
            "summary_trace": [t.to_dict() for t in self.summary_trace],
            "status": self.status,
        }
        if self.blocking_reasons:
            res["blocking_reasons"] = list(self.blocking_reasons)
        return res
