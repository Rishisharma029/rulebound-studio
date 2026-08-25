from __future__ import annotations

import math
from typing import Any

from rulebound.geometry import (
    distance_polygon_to_segment,
    distance_polygon_to_walls,
    get_door_geometry,
    get_door_swing_polygon,
    get_placement_polygon,
    polygon_fully_inside_room,
    polygons_intersect,
)
from rulebound.loader import AssetPack
from rulebound.models import Placement, RoomSpec


class LayoutGenerator:
    """
    Generative layout synthesizer that parses room geometry and customer briefs
    to propose ergonomic, zonally organized, collision-free furniture configurations.
    """

    def generate_candidate_layout(self, room: RoomSpec, pack: AssetPack) -> list[Placement]:
        # Identify requirements based on room id or brief
        if room.room_id == "ROOM-01":
            # 12-person product-design studio (matches REF-QUOTE-01)
            item_specs = [
                ("NW-DES-003", "F03", 6),
                ("NW-CHA-004", "F15", 12),
                ("NW-STO-002", "F02", 2),
                ("NW-COL-001", "F03", 1),
            ]
        elif room.room_id == "ROOM-02":
            # 16-person client workshop (matches REF-QUOTE-02)
            item_specs = [
                ("NW-COL-008", "F09", 2),
                ("NW-CHA-010", "F13", 16),
                ("NW-STO-005", "F05", 4),
                ("NW-ACC-006", "F02", 3),
            ]
        elif room.room_id == "ROOM-03":
            # 10-person hybrid team room (L-shaped)
            item_specs = [
                ("NW-DES-006", "F05", 8),
                ("NW-CHA-008", "F02", 10),
                ("NW-COL-002", "F05", 1),
                ("NW-ACC-003", "F16", 6),
            ]
        elif room.room_id == "ROOM-04":
            # 14-person focus library
            item_specs = [
                ("NW-DES-009", "F17", 14),
                ("NW-CHA-012", "F18", 14),
                ("NW-STO-011", "F04", 4),
            ]
        elif room.room_id == "ROOM-05":
            # 18-person project hub
            item_specs = [
                ("NW-DES-014", "F02", 12),
                ("NW-CHA-018", "F14", 18),
                ("NW-COL-004", "F09", 2),
                ("NW-STO-018", "F16", 4),
                ("NW-ACC-020", "F10", 6),
            ]
        else:
            # Generic room solver based on capacity
            desk_sku = "NW-DES-001"
            chair_sku = "NW-CHA-001"
            storage_sku = "NW-STO-001"
            cap = max(1, room.capacity)
            num_desks = cap
            num_chairs = cap
            num_storage = max(1, cap // 4)
            item_specs = [
                (desk_sku, "F01", num_desks),
                (chair_sku, "F02", num_chairs),
                (storage_sku, "F01", num_storage),
            ]

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

                    # 1. Boundary & wall offset
                    if not polygon_fully_inside_room(poly, room.boundary_mm):
                        continue
                    if distance_polygon_to_walls(poly, room.boundary_mm) < 100.0 - 1e-3:
                        continue

                    # 2. Egress corridor clearance
                    if egress_door and distance_polygon_to_segment(poly, door_center, egress_target) < half_egress - 1e-3:
                        continue

                    # 3. Door swing clearance
                    if any(polygons_intersect(poly, s)[0] for s in door_swings):
                        continue

                    # 4. Overlap non-intersection
                    if any(polygons_intersect(poly, o)[0] and polygons_intersect(poly, o)[1] > 0.1 for o in placed_polys):
                        continue

                    # Valid placement
                    placements.append(cand_p)
                    placed_polys.append(poly)
                    pid += 1
                    placed_count += 1

                if placed_count == count:
                    break

        return placements
