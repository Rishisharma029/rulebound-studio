from __future__ import annotations

import math
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
from rulebound.ir import RequirementIR, extract_requirement_ir, select_skus_from_ir
from rulebound.loader import AssetPack
from rulebound.models import Placement, RoomSpec


def parse_brief_requirements(
    brief_text: str,
    room: RoomSpec,
    pack: AssetPack,
) -> list[tuple[str, str, int]]:
    """
    Backward-compatible entry point: extracts RequirementIR and matches catalog SKUs.
    """
    ir = extract_requirement_ir(brief_text, room)
    return select_skus_from_ir(ir, pack)


class LayoutGenerator:
    """
    Generative layout synthesizer powered by intermediate requirement graphs (RequirementIR).
    Implements 4-stage pipeline:
      Natural Language Brief -> Intent Extraction -> RequirementIR -> Feature SKU Matching -> 2D Spatial Solver.
    """

    def generate_candidate_layout(self, room: RoomSpec, pack: AssetPack) -> list[Placement]:
        brief_text = pack.briefs.get(room.room_id, "")
        ir = extract_requirement_ir(brief_text, room)
        item_specs = select_skus_from_ir(ir, pack)
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
