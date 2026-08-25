from __future__ import annotations

import json
from pathlib import Path
import pytest

from runner import run_pipeline

ROOT = Path(__file__).resolve().parents[1]


def test_runner_end_to_end(tmp_path: Path):
    input_dir = ROOT / "RuleBound_Round1_Release/data"
    output_dir = tmp_path / "OUTPUT"

    exit_code = run_pipeline(input_dir, output_dir)
    assert exit_code == 0

    # Verify each room has layout.json and quote.json
    for room_id in ["ROOM-01", "ROOM-02", "ROOM-03", "ROOM-04", "ROOM-05"]:
        room_dir = output_dir / room_id
        assert (room_dir / "layout.json").exists()
        assert (room_dir / "quote.json").exists()
        assert (room_dir / "layout.dxf").exists()

        quote = json.loads((room_dir / "quote.json").read_text(encoding="utf-8"))
        assert quote["currency"] == "INR"
        assert quote["status"] in ["priced", "blocked"]
