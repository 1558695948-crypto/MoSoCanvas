#!/usr/bin/env python3
"""Materialize the approved text-distributed signature asset as an SVG file."""

from __future__ import annotations

import argparse
from pathlib import Path


BRAND_DIR = Path(__file__).resolve().parents[1] / "assets" / "brand"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=("dark", "light"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = BRAND_DIR / f"moso-echo-signature-{args.variant}.xml"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source.read_text())
    print(args.output.resolve())


if __name__ == "__main__":
    main()
