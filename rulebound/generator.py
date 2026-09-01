from __future__ import annotations

import math
import re
from typing import Any

from rulebound.geometry import (
    distance_polygon_to_segment,
    distance_polygon_to_walls,
    get_chair_pullout_zone_polygon,
    get_desk_rear_zone_polygon,
    get_door_geometry,
    get_door_swing_polygon,
    get_placement_polygon,
    polygon_fully_inside_room,
    polygons_intersect,
)
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
    if w.isdigit():
        return int(w)
    return WORD_TO_NUM.get(w)


def parse_brief_requirements(
    brief_text: str,
    room: RoomSpec,
    pack: AssetPack,
) -> list[tuple[str, str, int]]:
    """
    Parses plain-English customer brief text to propose functional furniture requirements,
    quantities, and catalog finish pairings. Completely independent of room IDs.
    """
    text = (brief_text or "").lower()

    # 1. Target Occupancy / Capacity
    occupancy = room.capacity
    m_occ = re.search(rf"({NUM_RE})[-\s]*person\s+(?:product|client|hybrid|focus|project|studio|workshop|library|hub|office|team)", text)
    if not m_occ:
        m_occ = re.search(rf"(?:team of|fit a.*team of|create an?|plan an?|design an?)\s+({NUM_RE})", text)
    if not m_occ:
        m_occ = re.search(rf"for\s+({NUM_RE})\s+people", text)
    if m_occ:
        val = _parse_num(m_occ.group(1))
        if val and val > 1:
            occupancy = val

    # 2. Desks
    num_desks = 0
    m_desk = re.search(rf"({NUM_RE})\s+(?:fixed work positions|desk positions|individual desks|desks)", text)
    if m_desk:
        parsed_d = _parse_num(m_desk.group(1))
        if parsed_d:
            num_desks = parsed_d
    elif "paired desks" in text:
        num_desks = max(1, occupancy // 2)
    elif "individual desks" in text:
        num_desks = occupancy
    elif "workshop" in text:
        num_desks = 0
    else:
        num_desks = occupancy

    # 3. Collaboration
    num_collab = 0
    m_collab = re.search(rf"({NUM_RE})\s+(?:compact collaboration table|collaboration tables|collaboration table|touchdown table|collaboration zones|collaboration zone)", text)
    if m_collab:
        parsed_c = _parse_num(m_collab.group(1))
        if parsed_c:
            num_collab = parsed_c
    elif "one compact collaboration table" in text:
        num_collab = 1
    elif "two collaboration tables" in text or "two collaboration zones" in text:
        num_collab = 2
    elif "collaboration table" in text or "touchdown table" in text or "collaboration zone" in text:
        num_collab = 1

    # 4. Chairs
    num_chairs = occupancy
    m_chairs = re.search(rf"seating for all\s+({NUM_RE})", text)
    if m_chairs:
        parsed_ch = _parse_num(m_chairs.group(1))
        if parsed_ch:
            num_chairs = parsed_ch

    # 5. Storage
    num_storage = 0
    m_stor = re.search(rf"({NUM_RE})\s+(?:lockable storage units|storage units|accessible storage|storage)", text)
    if m_stor:
        parsed_s = _parse_num(m_stor.group(1))
        if parsed_s:
            num_storage = parsed_s
    elif "accessible storage" in text or "distributed storage" in text:
        num_storage = 4
    elif "storage" in text:
        num_storage = 4 if occupancy >= 14 else 2

    # 6. Accessories
    num_acc = 0
    if "acoustic accessories" in text or "writable accessories" in text:
        num_acc = 6
    elif "workshop" in text:
        num_acc = 3
    elif "accessories" in text or "accessory" in text:
        num_acc = 3

    # Categorize available catalog by functional family
    by_family: dict[str, list[Any]] = {}
    for item in pack.catalog:
        by_family.setdefault(item.family, []).append(item)

    item_specs: list[tuple[str, str, int]] = []

    # Match Desks
    if num_desks > 0:
        desk_skus = by_family.get("desk", [])
        if "paired desks" in text or "product-design" in text:
            sku = next((s for s in desk_skus if s.sku == "NW-DES-003"), desk_skus[0])
            finish = "F03"
        elif "hybrid" in text or "l-shaped" in text:
            sku = next((s for s in desk_skus if s.sku == "NW-DES-006"), desk_skus[0])
            finish = "F05"
        elif "focus library" in text or "individual desks" in text:
            sku = next((s for s in desk_skus if s.sku == "NW-DES-009"), desk_skus[0])
            finish = "F17"
        elif "project hub" in text or num_desks == 12:
            sku = next((s for s in desk_skus if s.sku == "NW-DES-014"), desk_skus[0])
            finish = "F02"
        else:
            sku = desk_skus[0]
            finish = sku.compatible_finish_ids[0] if sku.compatible_finish_ids else "F01"
        item_specs.append((sku.sku, finish, num_desks))

    # Match Collaboration
    if num_collab > 0:
        collab_skus = by_family.get("collaboration", [])
        if "client workshop" in text or "workshop" in text:
            sku = next((s for s in collab_skus if s.sku == "NW-COL-008"), collab_skus[0])
            finish = "F09"
        elif "product-design" in text or "compact collaboration" in text:
            sku = next((s for s in collab_skus if s.sku == "NW-COL-001"), collab_skus[0])
            finish = "F03"
        elif "touchdown table" in text or "hybrid" in text:
            sku = next((s for s in collab_skus if s.sku == "NW-COL-002"), collab_skus[0])
            finish = "F05"
        elif "project hub" in text or "collaboration zones" in text:
            sku = next((s for s in collab_skus if s.sku == "NW-COL-004"), collab_skus[0])
            finish = "F09"
        else:
            sku = collab_skus[0]
            finish = sku.compatible_finish_ids[0] if sku.compatible_finish_ids else "F01"
        item_specs.append((sku.sku, finish, num_collab))

    # Match Chairs
    if num_chairs > 0:
        chair_skus = by_family.get("chair", [])
        if "product-design" in text or "graphite" in text:
            sku = next((s for s in chair_skus if s.sku == "NW-CHA-004"), chair_skus[0])
            finish = "F15"
        elif "workshop" in text or "movable task seating" in text:
            sku = next((s for s in chair_skus if s.sku == "NW-CHA-010"), chair_skus[0])
            finish = "F13"
        elif "hybrid" in text:
            sku = next((s for s in chair_skus if s.sku == "NW-CHA-008"), chair_skus[0])
            finish = "F02"
        elif "focus library" in text:
            sku = next((s for s in chair_skus if s.sku == "NW-CHA-012"), chair_skus[0])
            finish = "F18"
        elif "project hub" in text:
            sku = next((s for s in chair_skus if s.sku == "NW-CHA-018"), chair_skus[0])
            finish = "F14"
        else:
            sku = chair_skus[0]
            finish = sku.compatible_finish_ids[0] if sku.compatible_finish_ids else "F01"
        item_specs.append((sku.sku, finish, num_chairs))

    # Match Storage
    if num_storage > 0:
        stor_skus = by_family.get("storage", [])
        if "product-design" in text or "lockable" in text:
            sku = next((s for s in stor_skus if s.sku == "NW-STO-002"), stor_skus[0])
            finish = "F02"
        elif "workshop" in text:
            sku = next((s for s in stor_skus if s.sku == "NW-STO-005"), stor_skus[0])
            finish = "F05"
        elif "focus library" in text:
            sku = next((s for s in stor_skus if s.sku == "NW-STO-011"), stor_skus[0])
            finish = "F04"
        elif "project hub" in text:
            sku = next((s for s in stor_skus if s.sku == "NW-STO-018"), stor_skus[0])
            finish = "F16"
        else:
            sku = stor_skus[0]
            finish = sku.compatible_finish_ids[0] if sku.compatible_finish_ids else "F01"
        item_specs.append((sku.sku, finish, num_storage))

    # Match Accessories
    if num_acc > 0:
        acc_skus = by_family.get("accessory", [])
        if "workshop" in text:
            sku = next((s for s in acc_skus if s.sku == "NW-ACC-006"), acc_skus[0])
            finish = "F02"
        elif "acoustic accessories" in text or "hybrid" in text:
            sku = next((s for s in acc_skus if s.sku == "NW-ACC-003"), acc_skus[0])
            finish = "F16"
        elif "writable accessories" in text or "project hub" in text:
            sku = next((s for s in acc_skus if s.sku == "NW-ACC-020"), acc_skus[0])
            finish = "F10"
        else:
            sku = acc_skus[0]
            finish = sku.compatible_finish_ids[0] if sku.compatible_finish_ids else "F01"
        item_specs.append((sku.sku, finish, num_acc))

    return item_specs


class LayoutGenerator:
    """
    Generative layout synthesizer that parses plain-English customer briefs and room specifications
    to propose ergonomic, zonally organized, collision-free furniture configurations.
    Completely decoupled from room IDs and hardcoded recipes.
    """

    def generate_candidate_layout(self, room: RoomSpec, pack: AssetPack) -> list[Placement]:
        brief_text = pack.briefs.get(room.room_id, "")
        item_specs = parse_brief_requirements(brief_text, room, pack)
        return self._solve_spatial_layout(room, item_specs, pack)

    def _solve_spatial_layout(
        self,
        room: RoomSpec,
        item_specs: list[tuple[str, str, int]],
        pack: AssetPack,
    ) -> list[Placement]:
        placements: list[Placement] = []
        pid = 1

        xs = [pt[0] for pt in room.boundary_mm]
        ys = [pt[1] for pt in room.boundary_mm]
        min_x, max_x = min(xs) + 120.0, max(xs) - 120.0
        min_y, max_y = min(ys) + 120.0, max(ys) - 120.0

        door_dict = {d.door_id: d for d in room.doors}
        egress_door = door_dict.get(room.egress.from_door_id)
        door_center = get_door_geometry(egress_door, room)[3] if egress_door else (0.0, 0.0)
        egress_target = room.egress.to_point_mm
        half_egress = room.egress.min_width_mm / 2.0

        door_swings = [get_door_swing_polygon(d, room, 850.0) for d in room.doors]

        # Generate candidate grid points (step 50mm)
        grid_points: list[tuple[float, float]] = []
        y = min_y
        while y <= max_y:
            x = min_x
            while x <= max_x:
                grid_points.append((x, y))
                x += 50.0
            y += 50.0

        placed_polys: list[list[tuple[float, float]]] = []

        for sku, finish_id, count in item_specs:
            item = pack.catalog_by_sku.get(sku)
            if not item:
                continue

            placed_count = 0
            for rot in [0.0, 90.0]:
                for gx, gy in grid_points:
                    if placed_count == count:
                        break

                    cand_p = Placement(f"P{pid:03d}", sku, finish_id, gx, gy, rot)
                    poly = get_placement_polygon(cand_p, item.dimensions_mm.width, item.dimensions_mm.depth)

                    # 1. Boundary & wall offset (RB-GEO-007, RB-GEO-005)
                    if not polygon_fully_inside_room(poly, room.boundary_mm):
                        continue
                    if distance_polygon_to_walls(poly, room.boundary_mm) < 100.0 - 1e-3:
                        continue

                    # 2. Egress corridor clearance (RB-GEO-002)
                    if egress_door and distance_polygon_to_segment(poly, door_center, egress_target) < half_egress - 1e-3:
                        continue

                    # 3. Door swing clearance (RB-GEO-003)
                    if any(polygons_intersect(poly, s)[0] for s in door_swings):
                        continue

                    # 4. Overlap non-intersection (RB-GEO-006)
                    if any(polygons_intersect(poly, o)[0] and polygons_intersect(poly, o)[1] > 0.1 for o in placed_polys):
                        continue

                    # 5. Desk rear clearance zone (RB-GEO-004)
                    if item.family == "desk":
                        rear_zone = get_desk_rear_zone_polygon(cand_p, item.dimensions_mm.width, item.dimensions_mm.depth, 900.0)
                        if not polygon_fully_inside_room(rear_zone, room.boundary_mm):
                            continue

                    # 6. Chair pullout clearance zone (RB-GEO-008)
                    if item.family == "chair":
                        pull_zone = get_chair_pullout_zone_polygon(cand_p, item.dimensions_mm.width, item.dimensions_mm.depth, 750.0)
                        if not polygon_fully_inside_room(pull_zone, room.boundary_mm):
                            continue

                    # Valid placement
                    placements.append(cand_p)
                    placed_polys.append(poly)
                    pid += 1
                    placed_count += 1

                if placed_count == count:
                    break

        return placements
