from __future__ import annotations

import math
from pathlib import Path
import random
import pytest

from rulebound.constraints import verify_spatial_constraints
from rulebound.geometry import (
    distance_polygon_to_polygon,
    distance_polygon_to_walls,
    get_chair_pullout_zone_polygon,
    get_desk_rear_zone_polygon,
    get_placement_polygon,
    polygon_fully_inside_room,
    polygons_intersect,
)
from rulebound.loader import load_asset_pack
from rulebound.models import Placement, RoomSpec

ROOT = Path(__file__).resolve().parents[1]
PACK = load_asset_pack(ROOT / "RuleBound_Round1_Release/data")


class TestGeometryPropertySuite:
    """
    Property-Based Geometry Testing / Fuzz Suite (1,000 Deterministic Test Invocations).
    Proves mathematical invariants, symmetry, monotonicity, and crash-freedom across
    arbitrary, fuzzed inputs rather than only hand-crafted test cases.
    """

    def test_property_crash_freedom_and_numerical_robustness(self):
        """
        Property 1: Crash Freedom under 300 randomized extreme spatial configurations.
        Includes negative coordinates, massive extents, arbitrary rotations, and degenerate coordinates.
        """
        rng = random.Random(1337)
        room = PACK.rooms_by_id["ROOM-01"]
        catalog_skus = list(PACK.catalog_by_sku.keys())

        for idx in range(300):
            w = rng.uniform(10.0, 15000.0)
            d = rng.uniform(10.0, 15000.0)
            x = rng.uniform(-30000.0, 30000.0)
            y = rng.uniform(-30000.0, 30000.0)
            rot = rng.uniform(-1080.0, 1080.0)
            sku = rng.choice(catalog_skus)

            p = Placement(f"P{idx:04d}", sku, "F01", x, y, rot)
            poly = get_placement_polygon(p, w, d)

            # Must return finite coordinates
            assert len(poly) == 4
            for pt in poly:
                assert math.isfinite(pt[0])
                assert math.isfinite(pt[1])

            # Geometry queries must not crash or raise exceptions
            _inside = polygon_fully_inside_room(poly, room.boundary_mm)
            _wall_d = distance_polygon_to_walls(poly, room.boundary_mm)
            assert math.isfinite(_wall_d)
            assert _wall_d >= 0.0

            # Clearance zone queries must be well-formed
            rear_z = get_desk_rear_zone_polygon(p, w, d, 900.0)
            pull_z = get_chair_pullout_zone_polygon(p, w, d, 750.0)
            assert len(rear_z) >= 3
            assert len(pull_z) >= 3

    def test_property_sat_intersection_symmetry(self):
        """
        Property 2: SAT Overlap Symmetry (200 random polygon pairs).
        For any pair of oriented bounding boxes A and B:
          intersect(A, B) == intersect(B, A)
          depth(A, B) == depth(B, A)
        """
        rng = random.Random(2026)

        for idx in range(200):
            p1 = Placement(
                f"A{idx}", "NW-DES-001", "F01",
                rng.uniform(0.0, 5000.0), rng.uniform(0.0, 5000.0), rng.uniform(0.0, 360.0)
            )
            p2 = Placement(
                f"B{idx}", "NW-DES-002", "F01",
                rng.uniform(0.0, 5000.0), rng.uniform(0.0, 5000.0), rng.uniform(0.0, 360.0)
            )
            poly1 = get_placement_polygon(p1, rng.uniform(500.0, 2000.0), rng.uniform(500.0, 2000.0))
            poly2 = get_placement_polygon(p2, rng.uniform(500.0, 2000.0), rng.uniform(500.0, 2000.0))

            hit_ab, depth_ab, _ = polygons_intersect(poly1, poly2)
            hit_ba, depth_ba, _ = polygons_intersect(poly2, poly1)

            assert hit_ab == hit_ba, f"SAT intersection asymmetry at pair {idx}"
            assert abs(depth_ab - depth_ba) < 1e-4, f"Penetration depth asymmetry at pair {idx}: {depth_ab} != {depth_ba}"

    def test_property_distance_symmetry_and_non_negativity(self):
        """
        Property 3: Distance Metric Symmetry & Non-Negativity (200 random polygon pairs).
        For any two polygons A and B:
          dist(A, B) >= 0
          dist(A, B) == dist(B, A)
        """
        rng = random.Random(4242)

        for idx in range(200):
            p1 = Placement("D1", "NW-CHA-001", "F13", rng.uniform(100.0, 4000.0), rng.uniform(100.0, 4000.0), rng.uniform(0.0, 360.0))
            p2 = Placement("D2", "NW-CHA-002", "F13", rng.uniform(100.0, 4000.0), rng.uniform(100.0, 4000.0), rng.uniform(0.0, 360.0))
            poly1 = get_placement_polygon(p1, 600.0, 600.0)
            poly2 = get_placement_polygon(p2, 600.0, 600.0)

            d_ab = distance_polygon_to_polygon(poly1, poly2)
            d_ba = distance_polygon_to_polygon(poly2, poly1)

            assert d_ab >= 0.0
            assert d_ba >= 0.0
            assert abs(d_ab - d_ba) < 1e-4, f"Distance asymmetry: {d_ab} != {d_ba}"

    def test_property_containment_monotonicity(self):
        """
        Property 4: Room Containment Monotonicity (150 cases).
        If polygon P is contained in room R, expanding room boundaries outwards
        must strictly preserve containment: P in R => P in R_expanded.
        """
        rng = random.Random(7777)

        for idx in range(150):
            bw = rng.uniform(4000.0, 8000.0)
            bh = rng.uniform(4000.0, 8000.0)
            base_room = [(0.0, 0.0), (bw, 0.0), (bw, bh), (0.0, bh)]

            # Place item safely inside base room
            pw = rng.uniform(400.0, 1000.0)
            pd = rng.uniform(400.0, 1000.0)
            px = rng.uniform(200.0, bw - pw - 200.0)
            py = rng.uniform(200.0, bh - pd - 200.0)
            p = Placement(f"P{idx}", "NW-DES-001", "F01", px, py, 0.0)
            poly = get_placement_polygon(p, pw, pd)

            assert polygon_fully_inside_room(poly, base_room)

            # Expand room boundaries by 500mm outwards
            expanded_room = [(-500.0, -500.0), (bw + 500.0, -500.0), (bw + 500.0, bh + 500.0), (-500.0, bh + 500.0)]
            assert polygon_fully_inside_room(poly, expanded_room), "Monotonicity violated: item escaped expanded room"

    def test_property_evaluation_determinism_under_fuzz(self):
        """
        Property 5: Evaluation Determinism under Fuzzing (150 multi-item layout configurations).
        Re-running verification on identical fuzzed scene yields identical results.
        """
        rng = random.Random(9999)
        room = PACK.rooms_by_id["ROOM-01"]

        for idx in range(150):
            item_count = rng.randint(2, 6)
            pls = [
                Placement(
                    f"P{i}",
                    rng.choice(["NW-DES-001", "NW-CHA-001", "NW-STO-001"]),
                    "F01",
                    rng.uniform(0.0, 6000.0),
                    rng.uniform(0.0, 4500.0),
                    rng.choice([0.0, 90.0, 180.0, 270.0]),
                )
                for i in range(item_count)
            ]

            viols_run1 = verify_spatial_constraints(room, pls, PACK)
            viols_run2 = verify_spatial_constraints(room, pls, PACK)

            assert len(viols_run1) == len(viols_run2)
            for v1, v2 in zip(viols_run1, viols_run2):
                assert v1.rule_id == v2.rule_id
                assert v1.affected_placement_ids == v2.affected_placement_ids
                assert v1.measured == v2.measured
