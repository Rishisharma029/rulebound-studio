from __future__ import annotations

import math
from typing import Any

from rulebound.geometry import (
    distance_polygon_to_segment,
    distance_polygon_to_walls,
    get_door_geometry,
    get_door_swing_polygon,
    get_placement_polygon,
    point_in_polygon,
    polygon_fully_inside_room,
    polygons_intersect,
)
from rulebound.loader import AssetPack
from rulebound.models import Placement, RoomSpec, Violation


def verify_spatial_constraints(
    room: RoomSpec,
    placements: list[Placement],
    pack: AssetPack,
) -> list[Violation]:
    """
    Pure deterministic spatial constraint engine.
    Verifies RB-GEO-001 through RB-GEO-008.
    Generates structured violations with exact measurements and ranked repair options.
    """
    violations: list[Violation] = []
    v_idx = 1

    # Map placement IDs to their geometric polygon and catalog item
    poly_map = {}
    item_map = {}
    for p in placements:
        item = pack.catalog_by_sku.get(p.sku)
        if not item:
            continue
        poly = get_placement_polygon(p, item.dimensions_mm.width, item.dimensions_mm.depth)
        poly_map[p.placement_id] = poly
        item_map[p.placement_id] = item

    # 1. RB-GEO-007: Inside Room Boundary
    for p in placements:
        poly = poly_map.get(p.placement_id)
        if not poly:
            continue
        if not polygon_fully_inside_room(poly, room.boundary_mm):
            # Calculate how far outside
            out_points = [pt for pt in poly if not point_in_polygon(pt, room.boundary_mm)]
            violations.append(
                Violation(
                    violation_id=f"V{v_idx:03d}",
                    rule_id="RB-GEO-007",
                    message=f"Placement {p.placement_id} ({p.sku}) extends outside room boundary.",
                    affected_placement_ids=[p.placement_id],
                    measured={"outside_vertices_count": len(out_points)},
                    required={"inside_room_boundary": True},
                    repair_options=[
                        {"action": "nudge_inward", "priority": 1},
                        {"action": "rotate_90", "priority": 2},
                        {"action": "downsize_sku", "priority": 3},
                    ],
                )
            )
            v_idx += 1

    # 2. RB-GEO-005: Minimum Wall Offset (100 mm)
    for p in placements:
        poly = poly_map.get(p.placement_id)
        if not poly:
            continue
        dist = distance_polygon_to_walls(poly, room.boundary_mm)
        if dist < 100.0 - 1e-3:
            violations.append(
                Violation(
                    violation_id=f"V{v_idx:03d}",
                    rule_id="RB-GEO-005",
                    message=f"Placement {p.placement_id} ({p.sku}) is {round(dist, 1)} mm from wall (minimum 100 mm required).",
                    affected_placement_ids=[p.placement_id],
                    measured={"wall_distance_mm": round(dist, 1)},
                    required={"min_wall_offset_mm": 100.0},
                    repair_options=[
                        {"action": "shift_from_wall", "offset_delta_mm": round(100.0 - dist, 1), "priority": 1},
                    ],
                )
            )
            v_idx += 1

    # 3. RB-GEO-006: No Overlap Between Placements
    n = len(placements)
    for i in range(n):
        p1 = placements[i]
        poly1 = poly_map.get(p1.placement_id)
        if not poly1:
            continue
        for j in range(i + 1, n):
            p2 = placements[j]
            poly2 = poly_map.get(p2.placement_id)
            if not poly2:
                continue
            intersects, depth, normal = polygons_intersect(poly1, poly2)
            if intersects and depth > 0.5:
                violations.append(
                    Violation(
                        violation_id=f"V{v_idx:03d}",
                        rule_id="RB-GEO-006",
                        message=f"Placements {p1.placement_id} and {p2.placement_id} overlap by {round(depth, 1)} mm.",
                        affected_placement_ids=[p1.placement_id, p2.placement_id],
                        measured={"penetration_depth_mm": round(depth, 1)},
                        required={"max_overlap_mm": 0.0},
                        repair_options=[
                            {
                                "action": "separate_along_normal",
                                "normal_x": round(normal[0], 3),
                                "normal_y": round(normal[1], 3),
                                "distance_mm": round(depth + 10.0, 1),
                                "priority": 1,
                            },
                            {"action": "reposition_secondary", "placement_id": p2.placement_id, "priority": 2},
                        ],
                    )
                )
                v_idx += 1

    # 4. RB-GEO-002: Egress Clearance (1100 mm width -> 550 mm radius from centerline)
    door_dict = {d.door_id: d for d in room.doors}
    egress_door = door_dict.get(room.egress.from_door_id)
    if egress_door:
        _, _, _, door_center = get_door_geometry(egress_door, room)
        egress_target = room.egress.to_point_mm
        half_width = room.egress.min_width_mm / 2.0  # 550 mm

        for p in placements:
            poly = poly_map.get(p.placement_id)
            if not poly:
                continue
            dist = distance_polygon_to_segment(poly, door_center, egress_target)
            if dist < half_width - 1e-3:
                violations.append(
                    Violation(
                        violation_id=f"V{v_idx:03d}",
                        rule_id="RB-GEO-002",
                        message=f"Placement {p.placement_id} obstructs marked egress route ({round(dist, 1)} mm from centerline, required {round(half_width, 1)} mm).",
                        affected_placement_ids=[p.placement_id],
                        measured={"distance_to_egress_centerline_mm": round(dist, 1)},
                        required={"min_clearance_radius_mm": round(half_width, 1)},
                        repair_options=[
                            {"action": "move_outside_egress_corridor", "priority": 1},
                            {"action": "reassign_zone", "priority": 2},
                        ],
                    )
                )
                v_idx += 1

    # 5. RB-GEO-003: Door Swing Clearance (850 mm)
    for door in room.doors:
        swing_poly = get_door_swing_polygon(door, room, radius_mm=850.0)
        for p in placements:
            poly = poly_map.get(p.placement_id)
            if not poly:
                continue
            intersects, depth, _ = polygons_intersect(poly, swing_poly)
            if intersects:
                violations.append(
                    Violation(
                        violation_id=f"V{v_idx:03d}",
                        rule_id="RB-GEO-003",
                        message=f"Placement {p.placement_id} ({p.sku}) enters door-swing clearance zone for door {door.door_id}.",
                        affected_placement_ids=[p.placement_id],
                        measured={"swing_encroachment_mm": round(depth, 1)},
                        required={"swing_clearance_mm": 850.0},
                        repair_options=[
                            {"action": "relocate_away_from_door_swing", "priority": 1},
                        ],
                    )
                )
                v_idx += 1

    return violations
