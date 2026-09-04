from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest

from rulebound.loader import load_asset_pack

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "OUTPUT"
GOLDEN_DIR = ROOT / "tests/golden"
PACK = load_asset_pack(ROOT / "RuleBound_Round1_Release/data")


def test_golden_corpus_completeness():
    """Asserts that all 5 canonical challenge rooms have golden regression baselines."""
    expected_rooms = ["ROOM-01", "ROOM-02", "ROOM-03", "ROOM-04", "ROOM-05"]
    for rid in expected_rooms:
        golden_file = GOLDEN_DIR / f"{rid}_expected.json"
        assert golden_file.exists(), f"Golden expectation file missing for {rid}"
        data = json.loads(golden_file.read_text(encoding="utf-8"))
        assert data["room_id"] == rid
        assert "expected_placement_count" in data
        assert "expected_grand_total_inr" in data


@pytest.mark.parametrize("room_id", ["ROOM-01", "ROOM-02", "ROOM-03", "ROOM-04", "ROOM-05"])
def test_golden_semantic_regression(room_id: str):
    """
    Asserts semantic stability against the golden corpus:
    Not just 'same bytes', but 'same important meaning':
      - Status (valid vs unsatisfiable)
      - Placement counts & furniture family allocation
      - Hard constraint violations
      - Procurement grand total in INR
    """
    golden_file = GOLDEN_DIR / f"{room_id}_expected.json"
    golden = json.loads(golden_file.read_text(encoding="utf-8"))

    room_out = OUTPUT_DIR / room_id
    assert room_out.exists(), f"Output directory missing for {room_id}"

    layout_file = room_out / "layout.json"
    quote_file = room_out / "quote.json"
    assert layout_file.exists()
    assert quote_file.exists()

    layout_data = json.loads(layout_file.read_text(encoding="utf-8"))
    quote_data = json.loads(quote_file.read_text(encoding="utf-8"))

    # 1. Status equivalence
    assert layout_data["status"] == golden["expected_layout_status"]
    assert quote_data["status"] == golden["expected_quote_status"]

    # 2. Count equivalence
    placements = layout_data.get("placements", [])
    assert len(placements) == golden["expected_placement_count"]

    # 3. Family count breakdown
    family_counts: dict[str, int] = {}
    for p in placements:
        item = PACK.catalog_by_sku.get(p["sku"])
        fam = item.family if item else "unknown"
        family_counts[fam] = family_counts.get(fam, 0) + 1

    assert family_counts == golden["expected_family_counts"]

    # 4. Violations count
    assert len(layout_data.get("violations", [])) == golden["expected_violations_count"]

    # 5. Grand total in INR
    assert quote_data.get("summary", {}).get("grand_total_inr", 0) == golden["expected_grand_total_inr"]


@pytest.mark.parametrize("room_id", ["ROOM-01", "ROOM-02", "ROOM-03", "ROOM-04", "ROOM-05"])
def test_golden_sha256_canonical_hashes(room_id: str):
    """
    Asserts bitwise determinism and byte-exact reproducibility
    against canonical SHA-256 hashes.
    """
    golden_file = GOLDEN_DIR / f"{room_id}_expected.json"
    golden = json.loads(golden_file.read_text(encoding="utf-8"))

    room_out = OUTPUT_DIR / room_id
    layout_bytes = (room_out / "layout.json").read_bytes()
    quote_bytes = (room_out / "quote.json").read_bytes()

    layout_hash = hashlib.sha256(layout_bytes).hexdigest()
    quote_hash = hashlib.sha256(quote_bytes).hexdigest()

    assert layout_hash == golden["layout_sha256"], f"Layout SHA-256 drift in {room_id}"
    assert quote_hash == golden["quote_sha256"], f"Quote SHA-256 drift in {room_id}"
