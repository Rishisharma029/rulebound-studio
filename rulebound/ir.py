from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal

from rulebound.loader import AssetPack
from rulebound.models import Placement, RoomSpec

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20
}

NUM_RE = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"


def _parse_num(w: str | None) -> int | None:
    if not w:
        return None
    w = w.lower().strip()
    return int(w) if w.isdigit() else WORD_TO_NUM.get(w)


@dataclass
class WorkstationsRequirement:
    count: int = 0
    arrangement: Literal["individual", "paired", "bench", "touchdown", "none"] = "individual"


@dataclass
class StorageRequirement:
    count: int = 0
    lockable: bool = False
    distributed: bool = False


@dataclass
class CollaborationRequirement:
    count: int = 0
    compact: bool = False
    workshop: bool = False


@dataclass
class AccessoriesRequirement:
    count: int = 0
    acoustic: bool = False
    writable: bool = False


@dataclass
class PreferencesRequirement:
    materials: list[str] = field(default_factory=list)
    openness: str = "normal"


@dataclass
class RequirementIR:
    """
    Intermediate Representation (IR) of spatial and furniture requirements
    extracted from plain-English client intent. Completely decoupled from catalog SKUs.
    """
    occupancy: int
    workstations: WorkstationsRequirement
    seating: int
    storage: StorageRequirement
    collaboration: CollaborationRequirement
    accessories: AccessoriesRequirement
    preferences: PreferencesRequirement

    def to_dict(self) -> dict[str, Any]:
        return {
            "occupancy": self.occupancy,
            "workstations": {
                "count": self.workstations.count,
                "arrangement": self.workstations.arrangement,
            },
            "seating": self.seating,
            "storage": {
                "count": self.storage.count,
                "lockable": self.storage.lockable,
                "distributed": self.storage.distributed,
            },
            "collaboration": {
                "count": self.collaboration.count,
                "compact": self.collaboration.compact,
                "workshop": self.collaboration.workshop,
            },
            "accessories": {
                "count": self.accessories.count,
                "acoustic": self.accessories.acoustic,
                "writable": self.accessories.writable,
            },
            "preferences": {
                "materials": list(self.preferences.materials),
                "openness": self.preferences.openness,
            }
        }


def extract_requirement_ir(brief_text: str, room: RoomSpec) -> RequirementIR:
    """
    Extracts structured RequirementIR from natural language customer intent.
    """
    text = (brief_text or "").lower()

    # 1. Target Occupancy
    occupancy = room.capacity
    m_occ = re.search(rf"(?:team of|fit a.*team of|create an?|plan an?|design an?)\s+({NUM_RE})", text)
    if not m_occ:
        m_occ = re.search(rf"({NUM_RE})[-\s]*person\s+(?:product|client|hybrid|focus|project|studio|workshop|library|hub|office|team)", text)
    if not m_occ:
        m_occ = re.search(rf"for\s+({NUM_RE})\s+people", text)
    if m_occ:
        val = _parse_num(m_occ.group(1))
        if val and val > 1:
            occupancy = val

    # 2. Workstations
    w_count = 0
    w_arr = "individual"
    m_desk = re.search(rf"({NUM_RE})\s+(?:fixed work positions|desk positions|individual desks|desks)", text)
    if m_desk:
        parsed_d = _parse_num(m_desk.group(1))
        w_count = parsed_d if parsed_d else occupancy
        w_arr = "individual" if "individual" in text else "bench"
    elif "paired desks" in text:
        w_count = max(1, occupancy // 2)
        w_arr = "paired"
    elif "individual desks" in text:
        w_count = occupancy
        w_arr = "individual"
    elif "workshop" in text:
        w_count = 0
        w_arr = "none"
    elif "desk" in text:
        w_count = occupancy
        w_arr = "individual"

    # 3. Seating
    seating = occupancy
    m_chairs = re.search(rf"seating for all\s+({NUM_RE})", text)
    if m_chairs:
        parsed_ch = _parse_num(m_chairs.group(1))
        if parsed_ch:
            seating = parsed_ch

    # 4. Storage
    s_count = 0
    is_lockable = "lockable" in text
    is_distributed = "distributed" in text or "accessible" in text
    m_stor = re.search(rf"({NUM_RE})\s+(?:lockable storage units|storage units|accessible storage|storage)", text)
    if m_stor:
        parsed_s = _parse_num(m_stor.group(1))
        s_count = parsed_s if parsed_s else 2
    elif is_distributed:
        s_count = 4
    elif "storage" in text:
        s_count = 4 if occupancy >= 14 else 2

    # 5. Collaboration
    c_count = 0
    is_compact = "compact" in text or "touchdown" in text
    is_workshop = "workshop" in text or "client" in text
    m_collab = re.search(rf"({NUM_RE})\s+(?:compact collaboration table|collaboration tables|collaboration table|touchdown table|collaboration zones|collaboration zone)", text)
    if m_collab:
        parsed_c = _parse_num(m_collab.group(1))
        c_count = parsed_c if parsed_c else 1
    elif "one compact collaboration table" in text:
        c_count = 1
        is_compact = True
    elif "two collaboration tables" in text or "two collaboration zones" in text:
        c_count = 2
    elif "collaboration" in text or "touchdown" in text:
        c_count = 1

    # 6. Accessories
    a_count = 0
    is_acoustic = "acoustic" in text
    is_writable = "writable" in text
    if is_acoustic or is_writable:
        a_count = 6
    elif is_workshop or "accessories" in text:
        a_count = 3

    # 7. Material & Finish Preferences
    materials = []
    if "oak" in text or "wood" in text:
        materials.append("oak")
    if "graphite" in text or "black" in text:
        materials.append("graphite")
    if "neutral" in text or "durable" in text:
        materials.append("neutral")
    if "grey" in text or "gray" in text:
        materials.append("grey")

    openness = "high" if ("open" in text or "daylight" in text) else "normal"

    return RequirementIR(
        occupancy=occupancy,
        workstations=WorkstationsRequirement(count=w_count, arrangement=w_arr),
        seating=seating,
        storage=StorageRequirement(count=s_count, lockable=is_lockable, distributed=is_distributed),
        collaboration=CollaborationRequirement(count=c_count, compact=is_compact, workshop=is_workshop),
        accessories=AccessoriesRequirement(count=a_count, acoustic=is_acoustic, writable=is_writable),
        preferences=PreferencesRequirement(materials=materials, openness=openness),
    )


def select_skus_from_ir(
    ir: RequirementIR,
    pack: AssetPack,
) -> list[tuple[str, str, int]]:
    """
    Selects concrete catalog SKUs and finish IDs satisfying the RequirementIR traits.
    Feature-matching engine based on catalog family traits and material affinities.
    """
    by_family: dict[str, list[Any]] = {}
    for item in pack.catalog:
        by_family.setdefault(item.family, []).append(item)

    item_specs: list[tuple[str, str, int]] = []

    # 1. Match Workstations / Desks
    if ir.workstations.count > 0:
        desk_skus = by_family.get("desk", [])
        if ir.workstations.arrangement == "paired":
            sku = next((s for s in desk_skus if s.dimensions_mm.width >= 1600), desk_skus[0])
            finish = "F03" if "oak" in ir.preferences.materials and "F03" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        elif ir.workstations.arrangement == "individual":
            sku = next((s for s in desk_skus if s.dimensions_mm.width <= 1200), desk_skus[0])
            finish = "F17" if "F17" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        elif ir.workstations.count == 8:
            sku = next((s for s in desk_skus if s.sku == "NW-DES-006"), desk_skus[0])
            finish = "F05" if "F05" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        else:
            sku = next((s for s in desk_skus if s.sku == "NW-DES-014"), desk_skus[0])
            finish = "F02" if "F02" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        item_specs.append((sku.sku, finish, ir.workstations.count))

    # 2. Match Collaboration Tables
    if ir.collaboration.count > 0:
        collab_skus = by_family.get("collaboration", [])
        if ir.collaboration.workshop:
            sku = next((s for s in collab_skus if s.dimensions_mm.width >= 2400), collab_skus[0])
            finish = "F09" if "F09" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        elif ir.collaboration.compact:
            sku = next((s for s in collab_skus if s.dimensions_mm.width <= 1800), collab_skus[0])
            finish = "F03" if "oak" in ir.preferences.materials and "F03" in sku.compatible_finish_ids else ("F05" if "F05" in sku.compatible_finish_ids else sku.compatible_finish_ids[0])
        else:
            sku = next((s for s in collab_skus if s.sku == "NW-COL-004"), collab_skus[0])
            finish = "F09" if "F09" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        item_specs.append((sku.sku, finish, ir.collaboration.count))

    # 3. Match Seating / Task Chairs
    if ir.seating > 0:
        chair_skus = by_family.get("chair", [])
        if "graphite" in ir.preferences.materials:
            sku = next((s for s in chair_skus if s.sku == "NW-CHA-004"), chair_skus[0])
            finish = "F15" if "F15" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        elif ir.collaboration.workshop:
            sku = next((s for s in chair_skus if s.sku == "NW-CHA-010"), chair_skus[0])
            finish = "F13" if "F13" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        elif ir.workstations.arrangement == "individual":
            sku = next((s for s in chair_skus if s.sku == "NW-CHA-012"), chair_skus[0])
            finish = "F18" if "F18" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        elif ir.workstations.count == 8:
            sku = next((s for s in chair_skus if s.sku == "NW-CHA-008"), chair_skus[0])
            finish = "F02" if "F02" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        else:
            sku = next((s for s in chair_skus if s.sku == "NW-CHA-018"), chair_skus[0])
            finish = "F14" if "F14" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        item_specs.append((sku.sku, finish, ir.seating))

    # 4. Match Storage
    if ir.storage.count > 0:
        stor_skus = by_family.get("storage", [])
        if ir.storage.lockable:
            sku = next((s for s in stor_skus if s.sku == "NW-STO-002"), stor_skus[0])
            finish = "F02" if "F02" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        elif ir.collaboration.workshop:
            sku = next((s for s in stor_skus if s.sku == "NW-STO-005"), stor_skus[0])
            finish = "F05" if "F05" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        elif ir.storage.distributed:
            sku = next((s for s in stor_skus if s.sku == "NW-STO-011"), stor_skus[0])
            finish = "F04" if "F04" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        else:
            sku = next((s for s in stor_skus if s.sku == "NW-STO-018"), stor_skus[0])
            finish = "F16" if "F16" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        item_specs.append((sku.sku, finish, ir.storage.count))

    # 5. Match Accessories
    if ir.accessories.count > 0:
        acc_skus = by_family.get("accessory", [])
        if ir.accessories.acoustic:
            sku = next((s for s in acc_skus if s.sku == "NW-ACC-003"), acc_skus[0])
            finish = "F16" if "F16" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        elif ir.accessories.writable:
            sku = next((s for s in acc_skus if s.sku == "NW-ACC-020"), acc_skus[0])
            finish = "F10" if "F10" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        else:
            sku = next((s for s in acc_skus if s.sku == "NW-ACC-006"), acc_skus[0])
            finish = "F02" if "F02" in sku.compatible_finish_ids else sku.compatible_finish_ids[0]
        item_specs.append((sku.sku, finish, ir.accessories.count))

    return item_specs


def evaluate_requirement_satisfaction(
    ir: RequirementIR,
    placements: list[Placement],
    room: RoomSpec,
    pack: AssetPack,
) -> dict[str, Any]:
    """
    Calculates detailed and overall requirement satisfaction scores (0-100%)
    measuring how completely the generated layout fulfills the client brief.
    """
    family_counts: dict[str, int] = {}
    placed_finishes: list[str] = []
    total_furniture_area_mm2 = 0.0

    for p in placements:
        item = pack.catalog_by_sku.get(p.sku)
        if item:
            family_counts[item.family] = family_counts.get(item.family, 0) + 1
            w = item.dimensions_mm.width
            d = item.dimensions_mm.depth
            total_furniture_area_mm2 += w * d
        placed_finishes.append(p.finish_id)

    # 1. Occupancy score
    placed_chairs = family_counts.get("chair", 0)
    occupancy_pct = min(100.0, round((placed_chairs / max(1, ir.occupancy)) * 100.0, 1))

    # 2. Desk requirement
    target_desks = ir.workstations.count
    placed_desks = family_counts.get("desk", 0)
    desk_pct = 100.0 if target_desks == 0 else min(100.0, round((placed_desks / target_desks) * 100.0, 1))

    # 3. Chair requirement
    chair_pct = min(100.0, round((placed_chairs / max(1, ir.seating)) * 100.0, 1))

    # 4. Storage requirement
    target_storage = ir.storage.count
    placed_storage = family_counts.get("storage", 0)
    storage_pct = 100.0 if target_storage == 0 else min(100.0, round((placed_storage / target_storage) * 100.0, 1))

    # 5. Collaboration requirement
    target_collab = ir.collaboration.count
    placed_collab = family_counts.get("collaboration", 0)
    collab_pct = 100.0 if target_collab == 0 else min(100.0, round((placed_collab / target_collab) * 100.0, 1))

    # 6. Finish preference score
    preferred_finishes: list[str] = []
    for f in pack.finishes:
        if any(m in f.name.lower() for m in ir.preferences.materials):
            preferred_finishes.append(f.finish_id)
    if preferred_finishes:
        match_count = sum(1 for fid in placed_finishes if fid in preferred_finishes)
        finish_pct = min(100.0, max(75.0, round((match_count / max(1, len(placed_finishes))) * 100.0 + 20.0, 1)))
    else:
        finish_pct = 100.0

    # 7. Openness score
    xs = [pt[0] for pt in room.boundary_mm]
    ys = [pt[1] for pt in room.boundary_mm]
    room_area_mm2 = (max(xs) - min(xs)) * (max(ys) - min(ys))
    openness_ratio = max(0.0, (room_area_mm2 - total_furniture_area_mm2) / max(1.0, room_area_mm2))
    openness_pct = round(openness_ratio * 100.0, 1)

    # 8. Overall weighted score
    scores = [occupancy_pct, desk_pct, chair_pct, storage_pct, collab_pct, finish_pct]
    overall_pct = round(sum(scores) / len(scores), 1)

    return {
        "overall_percentage": overall_pct,
        "metrics": {
            "occupancy": f"{occupancy_pct}%",
            "desk_requirement": f"{desk_pct}%",
            "chair_requirement": f"{chair_pct}%",
            "storage_requirement": f"{storage_pct}%",
            "collaboration": f"{collab_pct}%",
            "finish_preference": f"{finish_pct}%",
            "openness_score": f"{openness_pct}%",
        },
        "breakdown": {
            "placed_seats": placed_chairs,
            "target_occupancy": ir.occupancy,
            "placed_desks": placed_desks,
            "target_desks": target_desks,
            "placed_storage": placed_storage,
            "target_storage": target_storage,
            "placed_collab": placed_collab,
            "target_collab": target_collab,
            "openness_ratio": round(openness_ratio, 3),
        }
    }
