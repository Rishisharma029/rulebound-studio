#!/usr/bin/env python3
"""
RuleBound Main Entrypoint
Official submission runner for LV8 Tech RuleBound Sealed Challenge.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from runner import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RuleBound: Deterministic Layout & Pricing Runner"
    )
    parser.add_argument("--input", required=True, help="Path to input data directory")
    parser.add_argument("--output", required=True, help="Path to output directory")
    args = parser.parse_args()

    exit_code = run_pipeline(args.input, args.output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
