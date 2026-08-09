#!/usr/bin/env python3
"""Measure visual delta between attempts without pretending to judge semantic success."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageFilter, ImageStat
except ImportError as exc:  # pragma: no cover - dependency error is explicit at runtime
    raise SystemExit("compare_attempts.py requires Pillow") from exc


def normalized_mae(left: Image.Image, right: Image.Image) -> float:
    stat = ImageStat.Stat(ImageChops.difference(left, right))
    return round(sum(stat.mean) / (len(stat.mean) * 255.0), 6)


def average_hash(image: Image.Image) -> int:
    small = image.convert("L").resize((8, 8))
    if hasattr(small, "get_flattened_data"):
        values = list(small.get_flattened_data())
    else:  # Pillow < 14
        values = list(small.getdata())
    mean = sum(values) / len(values)
    result = 0
    for value in values:
        result = (result << 1) | int(value >= mean)
    return result


def diagnostic_flag(color_mae: float, edge_mae: float) -> str:
    if color_mae < 0.012 and edge_mae < 0.012:
        return "very-low-delta"
    if color_mae < 0.03 and edge_mae < 0.03:
        return "low-delta"
    if color_mae < 0.12 and edge_mae < 0.12:
        return "visible-delta"
    return "large-delta"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a non-semantic visual-delta report for two image attempts."
    )
    parser.add_argument("parent", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--id", required=True)
    parser.add_argument("--target-variable", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    parent_source = Image.open(args.parent).convert("RGB")
    candidate_source = Image.open(args.candidate).convert("RGB")
    size = (256, 256)
    parent = parent_source.resize(size)
    candidate = candidate_source.resize(size)
    parent_l = parent.convert("L")
    candidate_l = candidate.convert("L")
    color_mae = normalized_mae(parent, candidate)
    luminance_mae = normalized_mae(parent_l, candidate_l)
    parent_edge = parent_l.filter(ImageFilter.FIND_EDGES)
    candidate_edge = candidate_l.filter(ImageFilter.FIND_EDGES)
    edge_mae = normalized_mae(parent_edge, candidate_edge)
    hash_distance = (average_hash(parent) ^ average_hash(candidate)).bit_count()

    report = {
        "schema": "moso.attempt-comparison/0.1",
        "id": args.id,
        "parent_artifact_ref": str(args.parent.resolve()),
        "candidate_artifact_ref": str(args.candidate.resolve()),
        "target_variable": args.target_variable,
        "automated_delta": {
            "normalized_color_mae": color_mae,
            "normalized_luminance_mae": luminance_mae,
            "edge_mae": edge_mae,
            "average_hash_distance": hash_distance,
            "diagnostic_flag": diagnostic_flag(color_mae, edge_mae),
            "not_semantic_proof": True,
        },
        "target_change": {
            "status": "unreviewed",
            "evidence": "Requires inspection of the named target variable in both artifacts."
        },
        "protected_drift": {
            "status": "unreviewed",
            "evidence": "Requires region-aware or semantic preservation inspection."
        },
        "trajectory_decision": "needs-visual-review",
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
