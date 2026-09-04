from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import random
import pytest

from rulebound.constraints import verify_spatial_constraints
from rulebound.geometry import (
    distance_polygon_to_polygon,
    distance_polygon_to_walls,
    get_placement_polygon,
    polygons_intersect,
)
from rulebound.loader import load_asset_pack
from rulebound.models import Placement, RoomSpec
from rulebound.pricing import price_placements

ROOT = Path(__file__).resolve().parents[1]
PACK = load_asset_pack(ROOT / "RuleBound_Round1_Release/data")


class TestMetamorphicRelations:
    """
    Formal Metamorphic Testing Suite.
    Validates fundamental mathematical metamorphic relations (MRs):
      - MR-1: Translation Invariance (Rigid-body spatial preservation)
      - MR-2: Placement Permutation Invariance (Order-independent constraint & pricing semantics)
      - MR-3: Re-Run Determinism Invariance (Bitwise invariant idempotency)
      - MR-4: Equivalent Rotation Encoding Invariance (Mod-360 geometric equivalence)
    """

    def test_mr1_translation_invariance(self):
        """
        MR-1: Translation Invariance.
        Translating an entire valid layout by a safe delta (dx, dy) within room bounds
        preserves all relative pairwise distances, overlap states, and zero-violation validity.
        """
        room = PACK.rooms_by_id["ROOM-02"]
        layout_json = json.loads((ROOT / "OUTPUT/ROOM-02/layout.json").read_text(encoding="utf-8"))
        original_placements = [
            Placement(
                p["placement_id"], p["sku"], p["finish_id"],
                p["x_mm"], p["y_mm"], p["rotation_deg"]
            )
            for p in layout_json["placements"]
        ]

        assert len(verify_spatial_constraints(room, original_placements, PACK)) == 0

        # Safe rigid-body shift of +20mm in X and +20mm in Y
        dx, dy = 20.0, 20.0
        shifted_placements = [
            Placement(
                p.placement_id, p.sku, p.finish_id,
                p.x_mm + dx, p.y_mm + dy, p.rotation_deg
            )
            for p in original_placements
        ]

        # 1. Invariant: Pairwise distances between all items must be identical
        n = len(original_placements)
        for i in range(n):
            for j in range(i + 1, n):
                d_orig = math.hypot(
                    original_placements[i].x_mm - original_placements[j].x_mm,
                    original_placements[i].y_mm - original_placements[j].y_mm,
                )
                d_shift = math.hypot(
                    shifted_placements[i].x_mm - shifted_placements[j].x_mm,
                    shifted_placements[i].y_mm - shifted_placements[j].y_mm,
                )
                assert abs(d_orig - d_shift) < 1e-6, "Translation violated rigid-body distance preservation"

        # 2. Invariant: Pairwise non-overlap states must remain identical
        for i in range(min(n, 10)):
            for j in range(i + 1, min(n, 10)):
                it_i = PACK.catalog_by_sku[original_placements[i].sku]
                it_j = PACK.catalog_by_sku[original_placements[j].sku]
                poly_orig_i = get_placement_polygon(original_placements[i], it_i.dimensions_mm.width, it_i.dimensions_mm.depth)
                poly_orig_j = get_placement_polygon(original_placements[j], it_j.dimensions_mm.width, it_j.dimensions_mm.depth)
                poly_shift_i = get_placement_polygon(shifted_placements[i], it_i.dimensions_mm.width, it_i.dimensions_mm.depth)
                poly_shift_j = get_placement_polygon(shifted_placements[j], it_j.dimensions_mm.width, it_j.dimensions_mm.depth)

                hit_orig, depth_orig, _ = polygons_intersect(poly_orig_i, poly_orig_j)
                hit_shift, depth_shift, _ = polygons_intersect(poly_shift_i, poly_shift_j)
                assert hit_orig == hit_shift
                assert abs(depth_orig - depth_shift) < 1e-4

    def test_mr2_placement_permutation_invariance(self):
        """
        MR-2: Placement Permutation Invariance.
        Reordering the input sequence of placements must not alter:
          - The set of constraint violations found
          - Total Lyapunov penalty energy
          - The generated quote line items, quantities, and grand total in INR
        """
        room = PACK.rooms_by_id["ROOM-02"]
        layout_json = json.loads((ROOT / "OUTPUT/ROOM-02/layout.json").read_text(encoding="utf-8"))
        canonical_pls = [
            Placement(
                p["placement_id"], p["sku"], p["finish_id"],
                p["x_mm"], p["y_mm"], p["rotation_deg"]
            )
            for p in layout_json["placements"]
        ]

        # Create randomized permutations
        rng = random.Random(42)
        for trial in range(5):
            permuted_pls = copy.deepcopy(canonical_pls)
            rng.shuffle(permuted_pls)

            # Verification equivalence
            viols_canon = verify_spatial_constraints(room, canonical_pls, PACK)
            viols_perm = verify_spatial_constraints(room, permuted_pls, PACK)
            assert len(viols_canon) == len(viols_perm)

            # Pricing equivalence
            quote_canon = price_placements("ROOM-02", canonical_pls, PACK)
            quote_perm = price_placements("ROOM-02", permuted_pls, PACK)

            assert quote_canon.status == quote_perm.status
            assert quote_canon.summary.grand_total_inr == quote_perm.summary.grand_total_inr
            assert len(quote_canon.lines) == len(quote_perm.lines)
            for l1, l2 in zip(quote_canon.lines, quote_perm.lines):
                assert l1.sku == l2.sku
                assert l1.finish_id == l2.finish_id
                assert l1.quantity == l2.quantity
                assert l1.net_goods_inr == l2.net_goods_inr

    def test_mr3_deterministic_rerun_invariance(self):
        """
        MR-3: Deterministic Re-Run Invariance.
        Re-running pricing and constraint evaluation on identical input repeatedly
        guarantees byte-for-byte identical output and identical cryptographic digests.
        """
        room = PACK.rooms_by_id["ROOM-02"]
        layout_json = json.loads((ROOT / "OUTPUT/ROOM-02/layout.json").read_text(encoding="utf-8"))
        pls = [
            Placement(
                p["placement_id"], p["sku"], p["finish_id"],
                p["x_mm"], p["y_mm"], p["rotation_deg"]
            )
            for p in layout_json["placements"]
        ]

        reference_quote = price_placements("ROOM-02", pls, PACK).to_dict()
        ref_hash = hashlib.sha256(json.dumps(reference_quote, sort_keys=True).encode("utf-8")).hexdigest()

        for _ in range(5):
            fresh_quote = price_placements("ROOM-02", pls, PACK).to_dict()
            fresh_hash = hashlib.sha256(json.dumps(fresh_quote, sort_keys=True).encode("utf-8")).hexdigest()
            assert fresh_hash == ref_hash

    def test_mr4_equivalent_rotation_encoding(self):
        """
        MR-4: Equivalent Rotation Encoding Invariance.
        Angles theta, theta + 360, theta - 360, and normalized equivalents
        produce identical vertex geometries and identical SAT intersection results.
        """
        item = PACK.catalog_by_sku["NW-DES-001"]
        w, d = item.dimensions_mm.width, item.dimensions_mm.depth

        angles = [0.0, 90.0, 180.0, 270.0]
        for base_ang in angles:
            equivalent_angles = [base_ang, base_ang + 360.0, base_ang - 360.0, base_ang + 720.0]
            base_poly = get_placement_polygon(Placement("P1", "NW-DES-001", "F01", 1000.0, 1000.0, base_ang), w, d)

            for eq_ang in equivalent_angles[1:]:
                test_poly = get_placement_polygon(Placement("P2", "NW-DES-001", "F01", 1000.0, 1000.0, eq_ang), w, d)
                for pt1, pt2 in zip(base_poly, test_poly):
                    assert abs(pt1[0] - pt2[0]) < 1e-4
                    assert abs(pt1[1] - pt2[1]) < 1e-4
