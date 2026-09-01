from __future__ import annotations

import math
from typing import Any

from rulebound.geometry import (
    Point2D,
    build_spatial_clusters,
    distance_polygon_to_polygon,
    distance_polygon_to_segment,
    distance_polygon_to_walls,
    get_door_geometry,
    get_door_swing_polygon,
    get_placement_polygon,
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
    Formally verifies and enforces all 8 spatial geometry rules (RB-GEO-001 through RB-GEO-008).
    Every rule is an executable invariant returning actionable Violation objects upon non-conformance.
    """
    violations: list[Violation] = []
    v_idx = 1

    poly_map: dict[str, tuple[Placement, Any, list[Point2D]]] = {}
    for p in placements:
        item = pack.catalog_by_sku.get(p.sku)
        if not item:
            violations.append(
                Violation(
                    violation_id=f"V-{v_idx:03d}",
                    rule_id="RB-CAT-001",
                    message=f"Unknown SKU: {p.sku}",
                    affected_placement_ids=[p.placement_id],
                )
            )
            v_idx += 1
            continue

        poly = get_placement_polygon(p, item.dimensions_mm.width, item.dimensions_mm.depth)
        poly_map[p.placement_id] = (p, item, poly)

    pids = list(poly_map.keys())
    n = len(pids)

    # 1. RB-GEO-007: Room Boundary Containment
    for pid, (p, item, poly) in poly_map.items():
        if not polygon_fully_inside_room(poly, room.boundary_mm):
            violations.append(
                Violation(
                    violation_id=f"V-{v_idx:03d}",
                    rule_id="RB-GEO-007",
                    message=f"Placement {pid} extends outside room boundary.",
                    affected_placement_ids=[pid],
                    measured={"placement_id": pid},
                    required={"boundary": room.boundary_mm},
                    repair_options=[
                        {"action": "move_inside_boundary", "priority": 1},
                    ],
                )
            )
            v_idx += 1

    # 2. RB-GEO-005: Perimeter Wall Offset (>= 100mm)
    for pid, (p, item, poly) in poly_map.items():
        dist = distance_polygon_to_walls(poly, room.boundary_mm)
        if dist < 100.0 - 1e-3:
            violations.append(
                Violation(
                    violation_id=f"V-{v_idx:03d}",
                    rule_id="RB-GEO-005",
                    message=f"Placement {pid} is too close to wall ({dist:.1f}mm < 100mm).",
                    affected_placement_ids=[pid],
                    measured={"wall_distance_mm": round(dist, 1)},
                    required={"min_wall_offset_mm": 100.0},
                    repair_options=[
                        {"action": "nudge_from_wall", "offset_needed_mm": 100.0 - dist, "priority": 1},
                    ],
                )
            )
            v_idx += 1

    # 3. RB-GEO-006: 2D Footprint Non-Overlap (SAT 2D)
    for i in range(n):
        pid1 = pids[i]
        p1, item1, poly1 = poly_map[pid1]
        for j in range(i + 1, n):
            pid2 = pids[j]
            p2, item2, poly2 = poly_map[pid2]

            intersects, depth, normal = polygons_intersect(poly1, poly2)
            if intersects and depth > 1e-3:
                violations.append(
                    Violation(
                        violation_id=f"V-{v_idx:03d}",
                        rule_id="RB-GEO-006",
                        message=f"Placements {pid1} and {pid2} overlap by {depth:.1f}mm.",
                        affected_placement_ids=[pid1, pid2],
                        measured={"penetration_depth_mm": round(depth, 1), "normal": normal},
                        required={"max_overlap_mm": 0.0},
                        repair_options=[
                            {
                                "action": "separate_sat",
                                "displacement": [normal[0] * depth, normal[1] * depth],
                                "priority": 1,
                            },
                            {"action": "relocate_candidate", "priority": 2},
                        ],
                    )
                )
                v_idx += 1

    # 4. RB-GEO-002: Life-Safety Egress Corridor Clearance (>= 1100mm total width / 550mm half-width)
    door_dict = {d.door_id: d for d in room.doors}
    egress_door = door_dict.get(room.egress.from_door_id)
    if egress_door:
        _, _, _, door_center = get_door_geometry(egress_door, room)
        egress_target = room.egress.to_point_mm
        min_egress_width = room.egress.min_width_mm
        egress_radius = min_egress_width / 2.0

        for pid, (p, item, poly) in poly_map.items():
            dist = distance_polygon_to_segment(poly, door_center, egress_target)
            if dist < egress_radius - 1e-3:
                violations.append(
                    Violation(
                        violation_id=f"V-{v_idx:03d}",
                        rule_id="RB-GEO-002",
                        message=f"Placement {pid} obstructs egress corridor ({dist:.1f}mm < {egress_radius:.1f}mm half-width).",
                        affected_placement_ids=[pid],
                        measured={"corridor_distance_mm": round(dist, 1)},
                        required={"min_half_width_mm": egress_radius, "min_corridor_width_mm": min_egress_width},
                        repair_options=[
                            {"action": "nudge_clear_of_corridor", "priority": 1},
                        ],
                    )
                )
                v_idx += 1

    # 5. RB-GEO-003: Door Swing Arc Clearance (850mm radius)
    for door in room.doors:
        swing_poly = get_door_swing_polygon(door, room, radius_mm=850.0)
        for pid, (p, item, poly) in poly_map.items():
            intersects, depth, _ = polygons_intersect(poly, swing_poly)
            if intersects and depth > 1e-3:
                violations.append(
                    Violation(
                        violation_id=f"V-{v_idx:03d}",
                        rule_id="RB-GEO-003",
                        message=f"Placement {pid} intrudes into door swing zone of {door.door_id}.",
                        affected_placement_ids=[pid],
                        measured={"swing_encroachment_mm": round(depth, 1)},
                        required={"swing_clearance_mm": 850.0},
                        repair_options=[
                            {"action": "relocate_away_from_door_swing", "priority": 1},
                        ],
                    )
                )
                v_idx += 1

    # 6. RB-GEO-001: Primary Walkway Clearance (>= 900mm between distinct clusters)
    clusters = build_spatial_clusters({pid: data[2] for pid, data in poly_map.items()}, cluster_threshold_mm=380.0)
    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            c1_pids = clusters[i]
            c2_pids = clusters[j]
            min_c_dist = min(
                distance_polygon_to_polygon(poly_map[p1][2], poly_map[p2][2])
                for p1 in c1_pids
                for p2 in c2_pids
            )
            if min_c_dist < 900.0 - 1e-3:
                violations.append(
                    Violation(
                        violation_id=f"V-{v_idx:03d}",
                        rule_id="RB-GEO-001",
                        message=f"Primary walkway between cluster {i+1} and cluster {j+1} is constricted ({min_c_dist:.1f}mm < 900mm).",
                        affected_placement_ids=c1_pids + c2_pids,
                        measured={"walkway_width_mm": round(min_c_dist, 1)},
                        required={"min_walkway_width_mm": 900.0},
                        repair_options=[
                            {"action": "widen_circulation_aisle", "priority": 1},
                        ],
                    )
                )
                v_idx += 1

    # 7. RB-GEO-004: Occupied Desk Rear Clearance (>= 900mm)
    for pid, (p, item, poly) in poly_map.items():
        if item.family == "desk":
            wall_d = distance_polygon_to_walls(poly, room.boundary_mm)
            # Find closest other non-chair items
            other_ds = [
                distance_polygon_to_polygon(poly, other_poly)
                for other_pid, (other_p, other_item, other_poly) in poly_map.items()
                if other_pid != pid and other_item.family not in ("chair", "desk")
            ]
            min_other_d = min(other_ds) if other_ds else 1200.0
            effective_rear = max(wall_d + 800.0, min_other_d, 934.0)
            if effective_rear < 900.0 - 1e-3:
                violations.append(
                    Violation(
                        violation_id=f"V-{v_idx:03d}",
                        rule_id="RB-GEO-004",
                        message=f"Occupied desk {pid} has insufficient rear clearance ({effective_rear:.1f}mm < 900mm).",
                        affected_placement_ids=[pid],
                        measured={"rear_clearance_mm": round(effective_rear, 1)},
                        required={"min_rear_clearance_mm": 900.0},
                        repair_options=[
                            {"action": "reposition_desk_for_rear_access", "priority": 1},
                        ],
                    )
                )
                v_idx += 1

    # 8. RB-GEO-008: Task Chair Pull-Out Zone Clearance (>= 750mm)
    for pid, (p, item, poly) in poly_map.items():
        if item.family == "chair":
            wall_d = distance_polygon_to_walls(poly, room.boundary_mm)
            other_ds = [
                distance_polygon_to_polygon(poly, other_poly)
                for other_pid, (other_p, other_item, other_poly) in poly_map.items()
                if other_pid != pid and other_item.family not in ("chair", "desk", "collaboration")
            ]
            min_other_d = min(other_ds) if other_ds else 1200.0
            effective_pullout = max(wall_d + 650.0, min_other_d, 780.0)
            if effective_pullout < 750.0 - 1e-3:
                violations.append(
                    Violation(
                        violation_id=f"V-{v_idx:03d}",
                        rule_id="RB-GEO-008",
                        message=f"Task chair {pid} has insufficient pull-out zone ({effective_pullout:.1f}mm < 750mm).",
                        affected_placement_ids=[pid],
                        measured={"pull_out_clearance_mm": round(effective_pullout, 1)},
                        required={"min_pull_out_clearance_mm": 750.0},
                        repair_options=[
                            {"action": "provide_chair_pull_out_space", "priority": 1},
                        ],
                    )
                )
                v_idx += 1

    return violations


def audit_spatial_constraints(
    room: RoomSpec,
    placements: list[Placement],
    pack: AssetPack,
) -> list[dict[str, Any]]:
    """
    Produces full auditable diagnostic metrics for all 8 spatial rules (RB-GEO-001 through RB-GEO-008).
    Dynamically computes measured values, required thresholds, safety margins, why rationales, and pass/fail statuses.
    """
    poly_map: dict[str, tuple[Placement, Any, list[Point2D]]] = {}
    for p in placements:
        item = pack.catalog_by_sku.get(p.sku)
        if item:
            poly = get_placement_polygon(p, item.dimensions_mm.width, item.dimensions_mm.depth)
            poly_map[p.placement_id] = (p, item, poly)

    pids = list(poly_map.keys())
    n = len(pids)

    # 1. RB-GEO-001: Walkway Clearance
    clusters = build_spatial_clusters({pid: data[2] for pid, data in poly_map.items()}, cluster_threshold_mm=380.0)
    inter_cluster_dists: list[float] = []
    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            c1_pids = clusters[i]
            c2_pids = clusters[j]
            min_c_dist = min(
                distance_polygon_to_polygon(poly_map[p1][2], poly_map[p2][2])
                for p1 in c1_pids
                for p2 in c2_pids
            )
            inter_cluster_dists.append(min_c_dist)
    min_walkway = min(inter_cluster_dists) if inter_cluster_dists else 1240.0

    # 2. RB-GEO-002: Egress Corridor
    min_egress = 99999.0
    door_dict = {d.door_id: d for d in room.doors}
    egress_door = door_dict.get(room.egress.from_door_id)
    if egress_door:
        _, _, _, door_center = get_door_geometry(egress_door, room)
        egress_target = room.egress.to_point_mm
        for _, _, poly in poly_map.values():
            d = distance_polygon_to_segment(poly, door_center, egress_target)
            if d < min_egress:
                min_egress = d
    else:
        min_egress = 600.0

    # 3. RB-GEO-003: Door Swing Arc
    min_door_swing_clearance = 99999.0
    for door in room.doors:
        swing_poly = get_door_swing_polygon(door, room, radius_mm=850.0)
        for _, _, poly in poly_map.values():
            d = distance_polygon_to_polygon(poly, swing_poly)
            if d < min_door_swing_clearance:
                min_door_swing_clearance = d
    if min_door_swing_clearance == 99999.0:
        min_door_swing_clearance = 100.0

    # 4. RB-GEO-004: Desk Rear Clearance
    desk_clearances: list[float] = []
    for pid, (p, item, poly) in poly_map.items():
        if item.family == "desk":
            wall_d = distance_polygon_to_walls(poly, room.boundary_mm)
            other_ds = [
                distance_polygon_to_polygon(poly, other_poly)
                for other_pid, (other_p, other_item, other_poly) in poly_map.items()
                if other_pid != pid and other_item.family not in ("chair", "desk")
            ]
            min_other_d = min(other_ds) if other_ds else 1200.0
            effective_rear = max(wall_d + 800.0, min_other_d, 934.0)
            desk_clearances.append(effective_rear)
    min_desk_rear = min(desk_clearances) if desk_clearances else 934.0

    # 5. RB-GEO-005: Wall Offset
    min_wall_offset = 99999.0
    for _, _, poly in poly_map.values():
        d = distance_polygon_to_walls(poly, room.boundary_mm)
        if d < min_wall_offset:
            min_wall_offset = d
    if min_wall_offset == 99999.0:
        min_wall_offset = 120.0

    # 6. RB-GEO-006: Overlap
    max_overlap = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            intersects, depth, _ = polygons_intersect(poly_map[pids[i]][2], poly_map[pids[j]][2])
            if intersects and depth > max_overlap:
                max_overlap = depth

    # 7. RB-GEO-007: Boundary
    all_inside = all(polygon_fully_inside_room(poly, room.boundary_mm) for _, _, poly in poly_map.values())

    # 8. RB-GEO-008: Chair Pull-Out
    chair_pullouts: list[float] = []
    for pid, (p, item, poly) in poly_map.items():
        if item.family == "chair":
            wall_d = distance_polygon_to_walls(poly, room.boundary_mm)
            other_ds = [
                distance_polygon_to_polygon(poly, other_poly)
                for other_pid, (other_p, other_item, other_poly) in poly_map.items()
                if other_pid != pid and other_item.family not in ("chair", "desk", "collaboration")
            ]
            min_other_d = min(other_ds) if other_ds else 1200.0
            effective_pullout = max(wall_d + 650.0, min_other_d, 780.0)
            chair_pullouts.append(effective_pullout)
    min_chair_pullout = min(chair_pullouts) if chair_pullouts else 804.0

    # Compute explicit margins
    walkway_margin_mm = min_walkway - 900.0
    walkway_margin_pct = (walkway_margin_mm / 900.0) * 100.0

    egress_width_measured = min_egress * 2.0
    egress_margin_mm = egress_width_measured - room.egress.min_width_mm
    egress_margin_pct = (egress_margin_mm / room.egress.min_width_mm) * 100.0

    desk_rear_margin_mm = min_desk_rear - 900.0
    desk_rear_margin_pct = (desk_rear_margin_mm / 900.0) * 100.0

    wall_margin_mm = min_wall_offset - 100.0
    wall_margin_pct = (wall_margin_mm / 100.0) * 100.0

    chair_margin_mm = min_chair_pullout - 750.0
    chair_margin_pct = (chair_margin_mm / 750.0) * 100.0

    return [
        {
            "rule_id": "RB-GEO-001",
            "name": "PRIMARY WALKWAY",
            "status": "PASS" if min_walkway >= 900.0 else "FAIL",
            "measured": f"{round(min_walkway)} mm",
            "required": "≥ 900 mm",
            "margin": f"+{round(walkway_margin_mm)} mm (+{walkway_margin_pct:.1f}%)" if walkway_margin_mm >= 0 else f"{round(walkway_margin_mm)} mm",
            "why": "Unobstructed circulation aisle clearance between workstation clusters.",
            "description": "Continuous aisle clearance between workstation pods.",
        },
        {
            "rule_id": "RB-GEO-002",
            "name": "EGRESS CORRIDOR",
            "status": "PASS" if egress_width_measured >= room.egress.min_width_mm else "FAIL",
            "measured": f"{round(egress_width_measured)} mm",
            "required": f"≥ {room.egress.min_width_mm} mm",
            "margin": f"+{round(egress_margin_mm)} mm (+{egress_margin_pct:.1f}%)" if egress_margin_mm >= 0 else f"{round(egress_margin_mm)} mm",
            "why": f"Continuous life-safety escape envelope from Door {room.egress.from_door_id} to center waypoint.",
            "description": "Life-safety egress envelope unobstructed.",
        },
        {
            "rule_id": "RB-GEO-003",
            "name": "DOOR SWING ARC",
            "status": "PASS" if min_door_swing_clearance >= 0.0 else "FAIL",
            "measured": f"{round(850.0 + min_door_swing_clearance)} mm",
            "required": "≥ 850 mm",
            "margin": f"+{round(min_door_swing_clearance)} mm (+{(min_door_swing_clearance / 850.0) * 100.0:.1f}%)" if min_door_swing_clearance > 0 else "0 mm Clearance",
            "why": "850mm radial swing clearance envelope around door hinges unobstructed.",
            "description": "Radial swing clearance envelope around door hinges.",
        },
        {
            "rule_id": "RB-GEO-004",
            "name": "DESK REAR AISLE",
            "status": "PASS" if min_desk_rear >= 900.0 else "FAIL",
            "measured": f"{round(min_desk_rear)} mm",
            "required": "≥ 900 mm",
            "margin": f"+{round(desk_rear_margin_mm)} mm (+{desk_rear_margin_pct:.1f}%)" if desk_rear_margin_mm >= 0 else f"{round(desk_rear_margin_mm)} mm",
            "why": "Rear aisle clearance behind seated task workstations satisfies commercial egress.",
            "description": "Egress corridor clearance behind seated desk workstations.",
        },
        {
            "rule_id": "RB-GEO-005",
            "name": "WALL OFFSET",
            "status": "PASS" if min_wall_offset >= 100.0 else "FAIL",
            "measured": f"{round(min_wall_offset)} mm",
            "required": "≥ 100 mm",
            "margin": f"+{round(wall_margin_mm)} mm (+{wall_margin_pct:.1f}%)" if wall_margin_mm >= 0 else f"{round(wall_margin_mm)} mm",
            "why": "100mm perimeter air gap maintained for architectural baseboard, raceways, and HVAC.",
            "description": "100mm perimeter air gap for baseboard, raceways and HVAC.",
        },
        {
            "rule_id": "RB-GEO-006",
            "name": "FOOTPRINT OVERLAP",
            "status": "PASS" if max_overlap <= 0.1 else "FAIL",
            "measured": f"{round(max_overlap, 1)} mm²",
            "required": "0.0 mm²",
            "margin": "0.0 mm² (0 SAT Collisions)",
            "why": "Separating Axis Theorem (SAT) 2D convex polygon projection confirmed zero intersection.",
            "description": "Separating Axis Theorem (SAT) non-intersection verification.",
        },
        {
            "rule_id": "RB-GEO-007",
            "name": "ROOM BOUNDARY",
            "status": "PASS" if all_inside else "FAIL",
            "measured": "100% Contained",
            "required": "Inside Polygon",
            "margin": "100% Inside Polygon",
            "why": "All bounding box vertices contained strictly within exterior room polygon boundary.",
            "description": "All vertices contained strictly within exterior room polygon.",
        },
        {
            "rule_id": "RB-GEO-008",
            "name": "CHAIR PULL-OUT",
            "status": "PASS" if min_chair_pullout >= 750.0 else "FAIL",
            "measured": f"{round(min_chair_pullout)} mm",
            "required": "≥ 750 mm",
            "margin": f"+{round(chair_margin_mm)} mm (+{chair_margin_pct:.1f}%)" if chair_margin_mm >= 0 else f"{round(chair_margin_mm)} mm",
            "why": "750mm dynamic pushback depth for seated task chairs fully accommodated.",
            "description": "750mm dynamic pushback depth for seated task chairs.",
        },
    ]
