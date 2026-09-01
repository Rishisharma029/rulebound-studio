from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from rulebound.models import DoorSpec, Placement, RoomSpec


Point2D = tuple[float, float]


@dataclass(frozen=True)
class Box2D:
    """Oriented 2D bounding box defined by 4 vertices in counter-clockwise order."""
    corners: list[Point2D]  # 4 points
    center: Point2D
    width: float
    depth: float
    rotation_deg: float


def rotate_point(point: Point2D, center: Point2D, angle_deg: float) -> Point2D:
    """Rotate a point counter-clockwise around center by angle_deg."""
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    dx = point[0] - center[0]
    dy = point[1] - center[1]
    rx = dx * cos_a - dy * sin_a + center[0]
    ry = dx * sin_a + dy * cos_a + center[1]
    return (rx, ry)


def get_placement_polygon(placement: Placement, width: float, depth: float) -> list[Point2D]:
    """
    Returns the 4 corner points of a placement bounding box.
    Placement (x_mm, y_mm) is the bottom-left coordinate before rotation,
    or center coordinate. By standard convention in layout specs:
    (x_mm, y_mm) is the insertion anchor point (bottom-left at rotation 0).
    """
    x = placement.x_mm
    y = placement.y_mm
    rot = placement.rotation_deg % 360

    # Local corners unrotated (bottom-left at x, y)
    c0 = (x, y)
    c1 = (x + width, y)
    c2 = (x + width, y + depth)
    c3 = (x, y + depth)

    if abs(rot) < 1e-4:
        return [c0, c1, c2, c3]

    center = (x + width / 2.0, y + depth / 2.0)
    return [
        rotate_point(c0, center, rot),
        rotate_point(c1, center, rot),
        rotate_point(c2, center, rot),
        rotate_point(c3, center, rot),
    ]


def point_in_polygon(point: Point2D, polygon: list[Point2D]) -> bool:
    """Ray-casting algorithm to test if point is inside a polygon."""
    x, y = point
    n = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def polygon_fully_inside_room(poly: list[Point2D], room_boundary: list[Point2D]) -> bool:
    """Checks if all vertices of polygon are strictly inside room boundary."""
    for pt in poly:
        if not point_in_polygon(pt, room_boundary):
            return False
    return True


def dot(v1: Point2D, v2: Point2D) -> float:
    return v1[0] * v2[0] + v1[1] * v2[1]


def project_polygon_on_axis(poly: list[Point2D], axis: Point2D) -> tuple[float, float]:
    dots = [dot(p, axis) for p in poly]
    return min(dots), max(dots)


def polygons_intersect(poly1: list[Point2D], poly2: list[Point2D]) -> tuple[bool, float, Point2D]:
    """
    Separating Axis Theorem (SAT) for convex polygons.
    Returns (intersects, min_penetration_depth, separation_normal).
    """
    min_overlap = float("inf")
    smallest_axis = (0.0, 0.0)

    for poly in (poly1, poly2):
        n = len(poly)
        for i in range(n):
            p1 = poly[i]
            p2 = poly[(i + 1) % n]
            # Normal to edge (p2 - p1)
            edge = (p2[0] - p1[0], p2[1] - p1[1])
            length = math.hypot(edge[0], edge[1])
            if length < 1e-6:
                continue
            axis = (-edge[1] / length, edge[0] / length)

            min1, max1 = project_polygon_on_axis(poly1, axis)
            min2, max2 = project_polygon_on_axis(poly2, axis)

            if max1 < min2 or max2 < min1:
                # Separating axis found -> no collision
                return False, 0.0, (0.0, 0.0)

            overlap = min(max1, max2) - max(min1, min2)
            if overlap < min_overlap:
                min_overlap = overlap
                smallest_axis = axis

    return True, min_overlap, smallest_axis


def distance_point_to_segment(p: Point2D, a: Point2D, b: Point2D) -> float:
    """Calculates perpendicular or endpoint Euclidean distance from point p to segment ab."""
    ab_x = b[0] - a[0]
    ab_y = b[1] - a[1]
    ab_len_sq = ab_x * ab_x + ab_y * ab_y
    if ab_len_sq < 1e-6:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    
    t = ((p[0] - a[0]) * ab_x + (p[1] - a[1]) * ab_y) / ab_len_sq
    t = max(0.0, min(1.0, t))
    proj_x = a[0] + t * ab_x
    proj_y = a[1] + t * ab_y
    return math.hypot(p[0] - proj_x, p[1] - proj_y)


def distance_polygon_to_segment(poly: list[Point2D], a: Point2D, b: Point2D) -> float:
    """Calculates minimum distance between a polygon and a line segment."""
    min_dist = float("inf")
    # Check distance from each polygon vertex to segment
    for pt in poly:
        d = distance_point_to_segment(pt, a, b)
        if d < min_dist:
            min_dist = d
            
    # Check distance from segment endpoints to polygon edges
    n = len(poly)
    for i in range(n):
        p1 = poly[i]
        p2 = poly[(i + 1) % n]
        d1 = distance_point_to_segment(a, p1, p2)
        d2 = distance_point_to_segment(b, p1, p2)
        min_dist = min(min_dist, d1, d2)
        
    return min_dist


def distance_polygon_to_walls(poly: list[Point2D], room_boundary: list[Point2D]) -> float:
    """Calculates minimum distance from a polygon to any room boundary wall segment."""
    min_dist = float("inf")
    n = len(room_boundary)
    for i in range(n):
        w1 = room_boundary[i]
        w2 = room_boundary[(i + 1) % n]
        for pt in poly:
            d = distance_point_to_segment(pt, w1, w2)
            if d < min_dist:
                min_dist = d
    return min_dist


def get_door_geometry(door: DoorSpec, room: RoomSpec) -> tuple[Point2D, Point2D, Point2D, Point2D]:
    """
    Returns (hinge_point, latch_point, swing_center, door_center) for a door.
    Calculates exact coordinates based on wall alignment.
    """
    # Find bounding box of room to identify walls
    xs = [p[0] for p in room.boundary_mm]
    ys = [p[1] for p in room.boundary_mm]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    if door.wall == "south":
        # South wall: y = min_y, x increases from min_x
        x1 = min_x + door.offset_mm
        x2 = x1 + door.width_mm
        y = min_y
        p1 = (x1, y)
        p2 = (x2, y)
    elif door.wall == "north":
        # North wall: y = max_y, x increases from min_x
        x1 = min_x + door.offset_mm
        x2 = x1 + door.width_mm
        y = max_y
        p1 = (x1, y)
        p2 = (x2, y)
    elif door.wall == "west":
        # West wall: x = min_x, y increases from min_y
        y1 = min_y + door.offset_mm
        y2 = y1 + door.width_mm
        x = min_x
        p1 = (x, y1)
        p2 = (x, y2)
    elif door.wall == "east":
        # East wall: x = max_x, y increases from min_y
        y1 = min_y + door.offset_mm
        y2 = y1 + door.width_mm
        x = max_x
        p1 = (x, y1)
        p2 = (x, y2)
    else:
        p1, p2 = (0.0, 0.0), (0.0, 0.0)

    center = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    hinge = p1 if "left" in door.swing else p2
    latch = p2 if "left" in door.swing else p1
    return hinge, latch, hinge, center


def get_door_swing_polygon(door: DoorSpec, room: RoomSpec, radius_mm: float = 850.0) -> list[Point2D]:
    """
    Generates a conservative polygonal approximation of the 90-degree door swing zone.
    """
    hinge, latch, _, _ = get_door_geometry(door, room)
    hx, hy = hinge
    
    # Generate arc sector approximation (8 points)
    pts = [(hx, hy)]
    num_arc_pts = 6
    
    # Determine base angle and swing direction
    if door.wall == "south":
        base_angle = 0 if "left" in door.swing else 180
        angle_start = 0 if "left" in door.swing else 180
        angle_end = 90 if "left" in door.swing else 90
    elif door.wall == "north":
        angle_start = 0 if "left" in door.swing else 180
        angle_end = -90 if "left" in door.swing else -90
    elif door.wall == "west":
        angle_start = 90 if "left" in door.swing else 270
        angle_end = 0 if "left" in door.swing else 0
    else:  # east
        angle_start = 90 if "left" in door.swing else 270
        angle_end = 180 if "left" in door.swing else 180

    for i in range(num_arc_pts + 1):
        frac = i / float(num_arc_pts)
        theta = math.radians(angle_start + frac * (angle_end - angle_start))
        pts.append((hx + radius_mm * math.cos(theta), hy + radius_mm * math.sin(theta)))

    return pts


def distance_polygon_to_polygon(poly1: list[Point2D], poly2: list[Point2D]) -> float:
    """
    Computes exact Euclidean minimum distance between two disjoint convex polygons.
    Returns 0.0 if the polygons intersect.
    """
    intersects, depth, _ = polygons_intersect(poly1, poly2)
    if intersects and depth > 1e-4:
        return 0.0

    min_dist = float("inf")
    n1, n2 = len(poly1), len(poly2)

    # Check vertices of poly1 against edges of poly2
    for pt in poly1:
        for j in range(n2):
            d = distance_point_to_segment(pt, poly2[j], poly2[(j + 1) % n2])
            if d < min_dist:
                min_dist = d

    # Check vertices of poly2 against edges of poly1
    for pt in poly2:
        for i in range(n1):
            d = distance_point_to_segment(pt, poly1[i], poly1[(i + 1) % n1])
            if d < min_dist:
                min_dist = d

    return min_dist


def build_spatial_clusters(
    poly_map: dict[str, list[Point2D]],
    cluster_threshold_mm: float = 380.0,
) -> list[list[str]]:
    """
    Groups placements into connected spatial clusters/pods.
    Placements within cluster_threshold_mm of each other belong to the same cluster.
    """
    pids = list(poly_map.keys())
    adj = {pid: [] for pid in pids}

    def _get_poly(val):
        if isinstance(val, tuple) and len(val) >= 3:
            return val[2]
        return val

    for i in range(len(pids)):
        pid1 = pids[i]
        poly1 = _get_poly(poly_map[pid1])
        for j in range(i + 1, len(pids)):
            pid2 = pids[j]
            poly2 = _get_poly(poly_map[pid2])
            d = distance_polygon_to_polygon(poly1, poly2)
            if d <= cluster_threshold_mm:
                adj[pid1].append(pid2)
                adj[pid2].append(pid1)

    visited = set()
    clusters: list[list[str]] = []
    for pid in pids:
        if pid not in visited:
            cluster: list[str] = []
            queue = [pid]
            visited.add(pid)
            while queue:
                curr = queue.pop(0)
                cluster.append(curr)
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            clusters.append(cluster)

    return clusters



def get_desk_rear_zone_polygon(placement: Placement, width: float, depth: float, rear_depth_mm: float = 900.0) -> list[Point2D]:
    """
    Returns the oriented 2D polygon for an occupied desk's rear seating zone (RB-GEO-004).
    Extends rear_depth_mm outward along user seating edge (+Y direction before rotation).
    """
    x = placement.x_mm
    y = placement.y_mm
    rot = placement.rotation_deg % 360

    r0 = (x, y + depth)
    r1 = (x + width, y + depth)
    r2 = (x + width, y + depth + rear_depth_mm)
    r3 = (x, y + depth + rear_depth_mm)

    if abs(rot) < 1e-4:
        return [r0, r1, r2, r3]

    center = (x + width / 2.0, y + depth / 2.0)
    return [
        rotate_point(r0, center, rot),
        rotate_point(r1, center, rot),
        rotate_point(r2, center, rot),
        rotate_point(r3, center, rot),
    ]


def get_chair_pullout_zone_polygon(placement: Placement, width: float, depth: float, pullout_depth_mm: float = 750.0) -> list[Point2D]:
    """
    Returns the oriented 2D polygon for a task chair's dynamic pull-out zone (RB-GEO-008).
    Extends pullout_depth_mm outward behind the chair (+Y direction before rotation).
    """
    x = placement.x_mm
    y = placement.y_mm
    rot = placement.rotation_deg % 360

    p0 = (x, y + depth)
    p1 = (x + width, y + depth)
    p2 = (x + width, y + depth + pullout_depth_mm)
    p3 = (x, y + depth + pullout_depth_mm)

    if abs(rot) < 1e-4:
        return [p0, p1, p2, p3]

    center = (x + width / 2.0, y + depth / 2.0)
    return [
        rotate_point(p0, center, rot),
        rotate_point(p1, center, rot),
        rotate_point(p2, center, rot),
        rotate_point(p3, center, rot),
    ]
