from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rulebound.models import (
    CatalogItem,
    DimensionsMM,
    DoorSpec,
    EgressSpec,
    Finish,
    RoomSpec,
    Rule,
    WindowSpec,
)


@dataclass
class AssetPack:
    catalog: list[CatalogItem]
    catalog_by_sku: dict[str, CatalogItem]
    finishes: list[Finish]
    finishes_by_id: dict[str, Finish]
    rules: list[Rule]
    rules_by_id: dict[str, Rule]
    rooms: list[RoomSpec]
    rooms_by_id: dict[str, RoomSpec]
    briefs: dict[str, str]
    historical_jobs: list[dict[str, Any]] = field(default_factory=list)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_room_spec(data: dict[str, Any]) -> RoomSpec:
    doors = [
        DoorSpec(
            door_id=d["door_id"],
            wall=d["wall"],
            offset_mm=float(d["offset_mm"]),
            width_mm=float(d["width_mm"]),
            swing=d["swing"],
        )
        for d in data.get("doors", [])
    ]
    windows = [
        WindowSpec(
            wall=w["wall"],
            offset_mm=float(w["offset_mm"]),
            width_mm=float(w["width_mm"]),
        )
        for w in data.get("windows", [])
    ]
    egress_data = data.get("egress", {})
    egress = EgressSpec(
        from_door_id=egress_data.get("from_door_id", ""),
        to_point_mm=(
            float(egress_data.get("to_point_mm", [0, 0])[0]),
            float(egress_data.get("to_point_mm", [0, 0])[1]),
        ),
        min_width_mm=float(egress_data.get("min_width_mm", 1100.0)),
    )
    boundary = [(float(pt[0]), float(pt[1])) for pt in data.get("boundary_mm", [])]
    return RoomSpec(
        room_id=data["room_id"],
        name=data.get("name", data["room_id"]),
        boundary_mm=boundary,
        doors=doors,
        windows=windows,
        egress=egress,
        capacity=int(data.get("capacity", 1)),
    )


def parse_catalog_item(data: dict[str, Any]) -> CatalogItem:
    dims = data.get("dimensions_mm", {})
    return CatalogItem(
        sku=data["sku"],
        family=data["family"],
        name=data.get("name", data["sku"]),
        dimensions_mm=DimensionsMM(
            width=float(dims.get("width", 0)),
            depth=float(dims.get("depth", 0)),
            height=float(dims.get("height", 0)),
        ),
        list_price_inr=int(data["list_price_inr"]),
        labour_minutes=int(data["labour_minutes"]),
        lead_time_days=int(data.get("lead_time_days", 0)),
        compatible_finish_ids=list(data.get("compatible_finish_ids", [])),
    )


def parse_finish(data: dict[str, Any]) -> Finish:
    return Finish(
        finish_id=data["finish_id"],
        name=data["name"],
        uplift_bps=int(data.get("uplift_bps", 0)),
        compatible_families=list(data.get("compatible_families", [])),
    )


def parse_rule(data: dict[str, Any]) -> Rule:
    return Rule(
        rule_id=data["rule_id"],
        kind=data["kind"],
        severity=data.get("severity", "error"),
        message=data.get("message", ""),
        target=data.get("target"),
        family=data.get("family"),
        value_mm=float(data["value_mm"]) if "value_mm" in data else None,
        tiers=list(data.get("tiers", [])),
        source=data.get("source"),
    )


def load_asset_pack(input_dir: str | Path) -> AssetPack:
    root = Path(input_dir).resolve()

    # Catalog
    catalog_path = root / "catalog.json"
    catalog_data = _load_json(catalog_path) if catalog_path.exists() else []
    catalog = [parse_catalog_item(item) for item in catalog_data]
    catalog_by_sku = {item.sku: item for item in catalog}

    # Finishes
    finishes_path = root / "finishes.json"
    finishes_data = _load_json(finishes_path) if finishes_path.exists() else []
    finishes = [parse_finish(item) for item in finishes_data]
    finishes_by_id = {item.finish_id: item for item in finishes}

    # Rules
    rules_path = root / "rules.json"
    rules_raw = _load_json(rules_path) if rules_path.exists() else {"rules": []}
    rules_list = rules_raw.get("rules", [])
    rules = [parse_rule(r) for r in rules_list]
    rules_by_id = {r.rule_id: r for r in rules}

    # Rooms
    rooms_dir = root / "rooms"
    rooms: list[RoomSpec] = []
    if rooms_dir.exists():
        for path in sorted(rooms_dir.glob("*.json")):
            rooms.append(parse_room_spec(_load_json(path)))
    rooms_by_id = {r.room_id: r for r in rooms}

    # Briefs
    briefs_dir = root / "briefs"
    briefs: dict[str, str] = {}
    if briefs_dir.exists():
        for path in sorted(briefs_dir.glob("*.txt")):
            briefs[path.stem] = path.read_text(encoding="utf-8").strip()

    # Historical Jobs
    jobs_path = root / "historical_jobs.json"
    historical_jobs = _load_json(jobs_path) if jobs_path.exists() else []

    return AssetPack(
        catalog=catalog,
        catalog_by_sku=catalog_by_sku,
        finishes=finishes,
        finishes_by_id=finishes_by_id,
        rules=rules,
        rules_by_id=rules_by_id,
        rooms=rooms,
        rooms_by_id=rooms_by_id,
        briefs=briefs,
        historical_jobs=historical_jobs,
    )
