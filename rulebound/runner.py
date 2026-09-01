#!/usr/bin/env python3
"""
RuleBound CLI Runner
Official submission runner for LV8 Tech RuleBound Sealed Challenge.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from rulebound.arbitration import ArbitrationEngine
from rulebound.dxf import export_layout_to_dxf
from rulebound.generator import LayoutGenerator
from rulebound.loader import load_asset_pack
from rulebound.pricing import price_placements


def write_json(path: Path, value: object) -> None:
    """Serialize JSON as UTF-8, sorted keys, two-space indentation and trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(serialized, encoding="utf-8")


def run_pipeline(input_dir: str | Path, output_dir: str | Path) -> int:
    """
    Executes the end-to-end RuleBound generation, constraint verification,
    arbitration, and pricing pipeline.
    """
    pack = load_asset_pack(input_dir)
    out_root = Path(output_dir)
    generator = LayoutGenerator()
    arbitrator = ArbitrationEngine(max_passes=50)

    for room in sorted(pack.rooms, key=lambda r: r.room_id):
        room_id = room.room_id

        # Phase 1: Propose candidate layout
        candidate_placements = generator.generate_candidate_layout(room, pack)

        # Phase 2: Arbitrate & enforce hard spatial constraints
        layout_result = arbitrator.arbitrate(room, candidate_placements, pack)

        # Phase 3: Deterministic line-traceable pricing
        if layout_result.status == "valid":
            quote_result = price_placements(room_id, layout_result.placements, pack)
        else:
            quote_result = price_placements(room_id, [], pack)
            quote_result.status = "blocked"
            quote_result.blocking_reasons = [
                f"Layout arbitration concluded with status '{layout_result.status}'."
            ]

        # Phase 4: Emit byte-identical canonical JSON outputs
        room_out_dir = out_root / room_id
        write_json(room_out_dir / "layout.json", layout_result.to_dict())
        write_json(room_out_dir / "quote.json", quote_result.to_dict())

        # Bonus: Export CAD DXF layout
        try:
            export_layout_to_dxf(room, layout_result.placements, pack, room_out_dir / "layout.dxf")
        except Exception:
            pass

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RuleBound: Deterministic Layout & Pricing Runner"
    )
    parser.add_argument(
        "--input",
        "-i",
        default="RuleBound_Round1_Release/data",
        help="Path to input data directory (default: RuleBound_Round1_Release/data)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="OUTPUT",
        help="Path to output directory (default: OUTPUT)",
    )
    args = parser.parse_args()

    exit_code = run_pipeline(args.input, args.output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
