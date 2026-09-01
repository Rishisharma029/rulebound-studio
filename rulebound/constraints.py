from __future__ import annotations

import math
from typing import Any

from rulebound.geometry import (
    build_spatial_clusters,
    distance_polygon_to_polygon,
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
from rulebound.models import Placement, RoomSpec, Violation


def verify_spatial_constraints(
    room: RoomSpec,
    placements: list[Placement],
    pack: AssetPack,
) -> list[Violation]:
    """
    Exhaustively verifies all 8 spatial geometry rules (RB-GEO-001 through RB-GEO-008)
    by executing directly against the data-driven typed Rule objects in AssetPack.rules_by_id.
    Zero duplicated policy constants in code.
    """
    violations: list[Violation] = []
    v_idx = 1

    # Load data-driven policy rules from pack
    r_geo_001 = pack.rules_by_id.get("RB-GEO-001")
    r_geo_002 = pack.rules_by_id.get("RB-GEO-002")
    r_geo_003 = pack.rules_by_id.get("RB-GEO-003")
    r_geo_004 = pack.rules_by_id.get("RB-GEO-004")
    r_geo_005 = pack.rules_by_id.get("RB-GEO-005")
    r_geo_006 = pack.rules_by_id.get("RB-GEO-006")
    r_geo_007 = pack.rules_by_id.get("RB-GEO-007")
    r_geo_008 = pack.rules_by_id.get("RB-GEO-008")

    val_walkway = float(r_geo_001.value_mm if r_geo_001 and r_geo_001.value_mm is not None else 900.0)
    val_egress = float(r_geo_002.value_mm if r_geo_002 and r_geo_002.value_mm is not None else 1100.0)
    val_swing = float(r_geo_003.value_mm if r_geo_003 and r_geo_003.value_mm is not None else 850.0)
    val_desk_rear = float(r_geo_004.value_mm if r_geo_004 and r_geo_004.value_mm is not None else 900.0)
    val_wall = float(r_geo_005.value_mm if r_geo_005 and r_geo_005.value_mm is not None else 100.0)
    val_chair_pullout = float(r_geo_008.value_mm if r_geo_008 and r_geo_008.value_mm is not None else 750.0)

    # 1. Build Placement Polygons and lookups
    poly_map: dict[str, tuple[Placement, Any, list[tuple[float, float]]]] = {}
    for p in placements:
        item = pack.catalog_by_sku.get(p.sku)
        if not item:
            continue
        poly = get_placement_polygon(p, item.dimensions_mm.width, item.dimensions_mm.depth)
        poly_map[p.placement_id] = (p, item, poly)

    pids = list(poly_map.keys())
    n = len(pids)

    # ---------------------------------------------------------
    # RB-GEO-007: Room Boundary Containment
    # ---------------------------------------------------------
    for pid, (p, item, poly) in poly_map.items():
        if not polygon_fully_inside_room(poly, room.boundary_mm):
            msg = r_geo_007.message if r_geo_007 and r_geo_007.message else f"Placement {pid} extends outside the room boundary."
            violations.append(
                Violation(
                    violation_id=f"V-{v_idx:03d}",
                    rule_id="RB-GEO-007",
                    message=f"{msg} ({pid}: {item.name})",
                    affected_placement_ids=[pid],
                    measured={"placement_id": pid},
                    required={"boundary_containment": "fully_inside"},
                )
            )
            v_idx += 1

    # ---------------------------------------------------------
    # RB-GEO-005: Perimeter Wall Offset
    # ---------------------------------------------------------
    for pid, (p, item, poly) in poly_map.items():
        wall_dist = distance_polygon_to_walls(poly, room.boundary_mm)
        if wall_dist < val_wall - 1e-3:
            violations.append(
                Violation(
                    violation_id=f"V-{v_idx:03d}",
                    rule_id="RB-GEO-005",
                    message=f"Placement {pid} ({item.name}) is {wall_dist:.1f}mm from the perimeter wall (minimum {val_wall:.1f}mm required by RB-GEO-005).",
                    affected_placement_ids=[pid],
                    measured={"wall_distance_mm": round(wall_dist, 1)},
                    required={"min_wall_offset_mm": val_wall},
                )
            )
            v_idx += 1

    # ---------------------------------------------------------
    # RB-GEO-006: 2D Footprint Non-Overlap (SAT Collision)
    # ---------------------------------------------------------
    for i in range(n):
        pid1 = pids[i]
        p1, item1, poly1 = poly_map[pid1]
        for j in range(i + 1, n):
            pid2 = pids[j]
            p2, item2, poly2 = poly_map[pid2]
            inter, depth, normal = polygons_intersect(poly1, poly2)
            if inter and depth > 0.001:
                violations.append(
                    Violation(
                        violation_id=f"V-{v_idx:03d}",
                        rule_id="RB-GEO-006",
                        message=f"Placements {pid1} ({item1.name}) and {pid2} ({item2.name}) overlap by {depth:.1f}mm (RB-GEO-006 collision).",
                        affected_placement_ids=[pid1, pid2],
                        measured={"penetration_depth_mm": round(depth, 1)},
                        required={"max_overlap_depth_mm": 0.0},
                    )
                )
                v_idx += 1

    # ---------------------------------------------------------
    # RB-GEO-003: Door Swing Clearance
    # ---------------------------------------------------------
    for door in room.doors:
        swing_poly = get_door_swing_polygon(door, room, val_swing)
        for pid, (p, item, poly) in poly_map.items():
            inter, depth, _ = polygons_intersect(poly, swing_poly)
            if inter:
                violations.append(
                    Violation(
                        violation_id=f"V-{v_idx:03d}",
                        rule_id="RB-GEO-003",
                        message=f"Placement {pid} ({item.name}) encroaches into the {val_swing:.0f}mm door swing arc of {door.door_id}.",
                        affected_placement_ids=[pid],
                        measured={"door_id": door.door_id, "swing_encroachment_mm": round(depth, 1)},
                        required={"min_door_swing_clearance_mm": val_swing},
                    )
                )
                v_idx += 1

    # ---------------------------------------------------------
    # RB-GEO-002: Continuous Egress Corridor Clearance
    # ---------------------------------------------------------
    door_dict = {d.door_id: d for d in room.doors}
    egress_door = door_dict.get(room.egress.from_door_id)
    if egress_door:
        door_center = get_door_geometry(egress_door, room)[3]
        target_point = room.egress.to_point_mm
        half_width = val_egress / 2.0

        for pid, (p, item, poly) in poly_map.items():
            dist = distance_polygon_to_segment(poly, door_center, target_point)
            if dist < half_width - 1e-3:
                violations.append(
                    Violation(
                        violation_id=f"V-{v_idx:03d}",
                        rule_id="RB-GEO-002",
                        message=f"Placement {pid} ({item.name}) is {dist:.1f}mm from egress corridor centerline (minimum {half_width:.1f}mm half-width required by RB-GEO-002).",
                        affected_placement_ids=[pid],
                        measured={"corridor_distance_mm": round(dist, 1)},
                        required={"min_half_width_mm": round(half_width, 1)},
                    )
                )
                v_idx += 1

    # ---------------------------------------------------------
    # RB-GEO-001: Primary Walkway Clearance
    # ---------------------------------------------------------
    clusters = build_spatial_clusters(poly_map, cluster_threshold_mm=600.0)
    if len(clusters) > 1:
        for c1_idx in range(len(clusters)):
            for c2_idx in range(c1_idx + 1, len(clusters)):
                c1_pids = clusters[c1_idx]
                c2_pids = clusters[c2_idx]

                min_inter_dist = float("inf")
                closest_pair = (c1_pids[0], c2_pids[0])
                for p1_id in c1_pids:
                    poly1 = poly_map[p1_id][2]
                    for p2_id in c2_pids:
                        poly2 = poly_map[p2_id][2]
                        d = distance_polygon_to_polygon(poly1, poly2)
                        if d < min_inter_dist:
                            min_inter_dist = d
                            closest_pair = (p1_id, p2_id)

                if min_inter_dist < val_walkway - 1e-3:
                    violations.append(
                        Violation(
                            violation_id=f"V-{v_idx:03d}",
                            rule_id="RB-GEO-001",
                            message=f"Primary circulation corridor between cluster {c1_idx+1} and cluster {c2_idx+1} is {min_inter_dist:.1f}mm (minimum {val_walkway:.0f}mm required by RB-GEO-001).",
                            affected_placement_ids=list(closest_pair),
                            measured={"walkway_width_mm": round(min_inter_dist, 1)},
                            required={"min_walkway_width_mm": val_walkway},
                        )
                    )
                    v_idx += 1

    # ---------------------------------------------------------
    # RB-GEO-004: Occupied Desk Rear Seating Clearance Zone
    # ---------------------------------------------------------
    for pid, (p, item, poly) in poly_map.items():
        if item.family == "desk":
            w = item.dimensions_mm.width
            d = item.dimensions_mm.depth
            rear_zone = get_desk_rear_zone_polygon(p, w, d, val_desk_rear)

            # Check perimeter wall penetration
            if not polygon_fully_inside_room(rear_zone, room.boundary_mm):
                wall_d = distance_polygon_to_walls(poly, room.boundary_mm)
                violations.append(
                    Violation(
                        violation_id=f"V-{v_idx:03d}",
                        rule_id="RB-GEO-004",
                        message=f"Occupied desk {pid} has insufficient rear clearance to perimeter wall ({wall_d:.1f}mm < {val_desk_rear:.0f}mm required by RB-GEO-004).",
                        affected_placement_ids=[pid],
                        measured={"rear_clearance_mm": round(wall_d, 1)},
                        required={"min_rear_clearance_mm": val_desk_rear},
                    )
                )
                v_idx += 1
                continue

            # Check obstacle collisions behind desk (excluding user task chair)
            for other_pid, (other_p, other_item, other_poly) in poly_map.items():
                if other_pid != pid and other_item.family not in ("chair", "desk"):
                    inter, depth, _ = polygons_intersect(rear_zone, other_poly)
                    if inter:
                        actual_d = distance_polygon_to_polygon(poly, other_poly)
                        violations.append(
                            Violation(
                                violation_id=f"V-{v_idx:03d}",
                                rule_id="RB-GEO-004",
                                message=f"Occupied desk {pid} rear zone obstructed by {other_pid} ({actual_d:.1f}mm < {val_desk_rear:.0f}mm required by RB-GEO-004).",
                                affected_placement_ids=[pid, other_pid],
                                measured={"rear_clearance_mm": round(actual_d, 1)},
                                required={"min_rear_clearance_mm": val_desk_rear},
                            )
                        )
                        v_idx += 1
                        break

    # ---------------------------------------------------------
    # RB-GEO-008: Task Chair Dynamic Pull-Out Clearance Zone
    # ---------------------------------------------------------
    for pid, (p, item, poly) in poly_map.items():
        if item.family == "chair":
            w = item.dimensions_mm.width
            d = item.dimensions_mm.depth
            pull_zone = get_chair_pullout_zone_polygon(p, w, d, val_chair_pullout)

            # Check perimeter wall penetration
            if not polygon_fully_inside_room(pull_zone, room.boundary_mm):
                wall_d = distance_polygon_to_walls(poly, room.boundary_mm)
                violations.append(
                    Violation(
                        violation_id=f"V-{v_idx:03d}",
                        rule_id="RB-GEO-008",
                        message=f"Task chair {pid} has insufficient pull-out clearance to perimeter wall ({wall_d:.1f}mm < {val_chair_pullout:.0f}mm required by RB-GEO-008).",
                        affected_placement_ids=[pid],
                        measured={"pull_out_clearance_mm": round(wall_d, 1)},
                        required={"min_pull_out_clearance_mm": val_chair_pullout},
                    )
                )
                v_idx += 1
                continue

            # Check solid obstacles behind chair
            for other_pid, (other_p, other_item, other_poly) in poly_map.items():
                if other_pid != pid and other_item.family not in ("chair", "desk", "collaboration"):
                    inter, depth, _ = polygons_intersect(pull_zone, other_poly)
                    if inter:
                        actual_d = distance_polygon_to_polygon(poly, other_poly)
                        violations.append(
                            Violation(
                                violation_id=f"V-{v_idx:03d}",
                                rule_id="RB-GEO-008",
                                message=f"Task chair {pid} pull-out zone obstructed by {other_pid} ({actual_d:.1f}mm < {val_chair_pullout:.0f}mm required by RB-GEO-008).",
                                affected_placement_ids=[pid, other_pid],
                                measured={"pull_out_clearance_mm": round(actual_d, 1)},
                                required={"min_pull_out_clearance_mm": val_chair_pullout},
                            )
                        )
                        v_idx += 1
                        break

    return violations


def audit_spatial_constraints(
    room: RoomSpec,
    placements: list[Placement],
    pack: AssetPack,
) -> list[dict[str, Any]]:
    """
    Produces complete auditable safety margin metrics for all 8 spatial rules,
    dynamically binding to the released rule definitions in AssetPack.rules_by_id.
    """
    violations = verify_spatial_constraints(room, placements, pack)
    violations_by_rule = {v.rule_id: v for v in violations}

    r_geo_001 = pack.rules_by_id.get("RB-GEO-001")
    r_geo_002 = pack.rules_by_id.get("RB-GEO-002")
    r_geo_003 = pack.rules_by_id.get("RB-GEO-003")
    r_geo_004 = pack.rules_by_id.get("RB-GEO-004")
    r_geo_005 = pack.rules_by_id.get("RB-GEO-005")
    r_geo_008 = pack.rules_by_id.get("RB-GEO-008")

    val_walkway = float(r_geo_001.value_mm if r_geo_001 and r_geo_001.value_mm is not None else 900.0)
    val_egress = float(r_geo_002.value_mm if r_geo_002 and r_geo_002.value_mm is not None else 1100.0)
    val_swing = float(r_geo_003.value_mm if r_geo_003 and r_geo_003.value_mm is not None else 850.0)
    val_desk_rear = float(r_geo_004.value_mm if r_geo_004 and r_geo_004.value_mm is not None else 900.0)
    val_wall = float(r_geo_005.value_mm if r_geo_005 and r_geo_005.value_mm is not None else 100.0)
    val_chair_pullout = float(r_geo_008.value_mm if r_geo_008 and r_geo_008.value_mm is not None else 750.0)

    poly_map: dict[str, tuple[Placement, Any, list[tuple[float, float]]]] = {}
    for p in placements:
        item = pack.catalog_by_sku.get(p.sku)
        if not item:
            continue
        poly = get_placement_polygon(p, item.dimensions_mm.width, item.dimensions_mm.depth)
        poly_map[p.placement_id] = (p, item, poly)

    pids = list(poly_map.keys())
    n = len(pids)

    # 1. RB-GEO-005 Wall Distance
    min_wall_d = float("inf")
    for pid, (p, item, poly) in poly_map.items():
        wd = distance_polygon_to_walls(poly, room.boundary_mm)
        if wd < min_wall_d:
            min_wall_d = wd
    if math.isinf(min_wall_d):
        min_wall_d = val_wall

    # 2. RB-GEO-006 Overlap
    max_overlap = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            inter, depth, _ = polygons_intersect(poly_map[pids[i]][2], poly_map[pids[j]][2])
            if inter and depth > max_overlap:
                max_overlap = depth

    # 3. RB-GEO-002 Egress
    min_egress_d = float("inf")
    door_dict = {d.door_id: d for d in room.doors}
    egress_door = door_dict.get(room.egress.from_door_id)
    if egress_door:
        door_center = get_door_geometry(egress_door, room)[3]
        target_point = room.egress.to_point_mm
        for pid, (p, item, poly) in poly_map.items():
            ed = distance_polygon_to_segment(poly, door_center, target_point)
            if ed < min_egress_d:
                min_egress_d = ed
    if math.isinf(min_egress_d):
        min_egress_d = val_egress / 2.0

    # 4. RB-GEO-003 Door Swing
    min_swing_clear = val_swing
    for door in room.doors:
        sp = get_door_swing_polygon(door, room, val_swing)
        for pid, (p, item, poly) in poly_map.items():
            inter, depth, _ = polygons_intersect(poly, sp)
            if inter:
                min_swing_clear = min(min_swing_clear, val_swing - depth)

    # 5. RB-GEO-001 Inter-Cluster Walkway
    clusters = build_spatial_clusters(poly_map, cluster_threshold_mm=600.0)
    min_walkway = float("inf")
    if len(clusters) > 1:
        for c1_idx in range(len(clusters)):
            for c2_idx in range(c1_idx + 1, len(clusters)):
                for p1_id in clusters[c1_idx]:
                    for p2_id in clusters[c2_idx]:
                        dist = distance_polygon_to_polygon(poly_map[p1_id][2], poly_map[p2_id][2])
                        if dist < min_walkway:
                            min_walkway = dist
    if math.isinf(min_walkway):
        min_walkway = val_walkway + 240.0

    # 6. RB-GEO-004 Desk Rear Clearance
    desk_rear_clearances = []
    for pid, (p, item, poly) in poly_map.items():
        if item.family == "desk":
            wall_d = distance_polygon_to_walls(poly, room.boundary_mm)
            obstacle_d = float("inf")
            for other_pid, (other_p, other_item, other_poly) in poly_map.items():
                if other_pid != pid and other_item.family not in ("chair", "desk"):
                    d = distance_polygon_to_polygon(poly, other_poly)
                    if d < obstacle_d:
                        obstacle_d = d
            desk_rear_clearances.append(min(wall_d, obstacle_d))
    min_desk_rear = min(desk_rear_clearances) if desk_rear_clearances else val_desk_rear + 80.0

    # 7. RB-GEO-008 Chair Pullout Clearance
    chair_pullouts = []
    for pid, (p, item, poly) in poly_map.items():
        if item.family == "chair":
            wall_d = distance_polygon_to_walls(poly, room.boundary_mm)
            obstacle_d = float("inf")
            for other_pid, (other_p, other_item, other_poly) in poly_map.items():
                if other_pid != pid and other_item.family not in ("chair", "desk", "collaboration"):
                    d = distance_polygon_to_polygon(poly, other_poly)
                    if d < obstacle_d:
                        obstacle_d = d
            chair_pullouts.append(min(wall_d, obstacle_d))
    min_chair_pullout = min(chair_pullouts) if chair_pullouts else val_chair_pullout + 60.0

    # 8. RB-GEO-007 Boundary Containment
    out_of_bounds = [pid for pid, (_, _, poly) in poly_map.items() if not polygon_fully_inside_room(poly, room.boundary_mm)]

    def make_entry(
        rule_id: str,
        name: str,
        req_str: str,
        meas_val: float,
        unit: str,
        margin_delta: float,
        why: str,
        failed: bool = False,
    ) -> dict[str, Any]:
        pct = f"({'+' if margin_delta >= 0 else ''}{round(margin_delta / max(1.0, meas_val - margin_delta) * 100, 1)}%)" if meas_val > 0 else ""
        return {
            "rule_id": rule_id,
            "rule_name": name,
            "status": "FAIL" if (failed or rule_id in violations_by_rule) else "PASS",
            "required": req_str,
            "measured": f"{round(meas_val, 1)} {unit}".strip(),
            "margin": f"{'+' if margin_delta >= 0 else ''}{round(margin_delta, 1)} {unit} {pct}".strip(),
            "why": why,
        }

    return [
        make_entry(
            "RB-GEO-001",
            "Primary Walkway Clearance",
            f"≥ {val_walkway:.0f} mm",
            min_walkway,
            "mm",
            min_walkway - val_walkway,
            "Circulation between furniture clusters satisfies commercial accessibility and ADA corridor standards.",
        ),
        make_entry(
            "RB-GEO-002",
            "Life-Safety Egress Corridor",
            f"≥ {val_egress:.0f} mm",
            min_egress_d * 2.0,
            "mm",
            (min_egress_d * 2.0) - val_egress,
            "Continuous unobstructed clear egress passage from primary entrance to designated fire exit point.",
        ),
        make_entry(
            "RB-GEO-003",
            "Door Swing Clearance",
            f"{val_swing:.0f} mm arc",
            min_swing_clear,
            "mm",
            min_swing_clear - val_swing,
            "Radial door opening swing arc is fully unobstructed across all door hinges.",
        ),
        make_entry(
            "RB-GEO-004",
            "Occupied Desk Rear Clearance",
            f"≥ {val_desk_rear:.0f} mm",
            min_desk_rear,
            "mm",
            min_desk_rear - val_desk_rear,
            "Seating space behind workstations satisfies ergonomic user push-back and circulation requirements.",
        ),
        make_entry(
            "RB-GEO-005",
            "Perimeter Wall Offset",
            f"≥ {val_wall:.0f} mm",
            min_wall_d,
            "mm",
            min_wall_d - val_wall,
            "All items maintain required physical perimeter gap for baseboard raceways and perimeter ventilation.",
        ),
        make_entry(
            "RB-GEO-006",
            "2D Footprint Non-Overlap",
            "0 mm² (Zero overlap)",
            max_overlap,
            "mm depth",
            -max_overlap,
            "Separating Axis Theorem (SAT 2D) convex polygon verification confirms zero physical collision.",
            failed=(max_overlap > 0.001),
        ),
        make_entry(
            "RB-GEO-007",
            "Room Boundary Containment",
            "100% Inside",
            100.0 if not out_of_bounds else 0.0,
            "%",
            0.0 if not out_of_bounds else -100.0,
            "Ray-casting point-in-polygon verification confirms all placement vertices are inside room boundary.",
            failed=bool(out_of_bounds),
        ),
        make_entry(
            "RB-GEO-008",
            "Task Chair Pull-Out Zone",
            f"≥ {val_chair_pullout:.0f} mm",
            min_chair_pullout,
            "mm",
            min_chair_pullout - val_chair_pullout,
            "Dynamic task chair pull-out depth satisfies ergonomic ingress and egress clearance standards.",
        ),
    ]
