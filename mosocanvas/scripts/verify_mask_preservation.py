#!/usr/bin/env python3
"""Check protected decoded RGBA samples and ICC identity, bound to source hashes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from image_contract import placed_box, profile_hash, read_coverage_mask, read_raster, sha256, reject_input_overwrite


def parse_origin(value: str) -> tuple[int, int]:
    try:
        x_text, y_text = value.split(",", 1)
        return int(x_text), int(y_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("origin must be x,y") from exc


def verify(source_path: Path, candidate_path: Path, mask_path: Path, origin: tuple[int, int] = (0, 0)) -> dict:
    source_image, source_info = read_raster(source_path)
    candidate_image, candidate_info = read_raster(candidate_path)
    if source_image.size != candidate_image.size:
        raise ValueError(f"dimension mismatch: {source_image.size} != {candidate_image.size}")
    coverage = read_coverage_mask(mask_path)
    box = placed_box(origin, coverage.size, source_image.size)
    full_mask = np.zeros((source_image.height, source_image.width), dtype=np.uint8)
    full_mask[box[1]:box[3], box[0]:box[2]] = np.asarray(coverage)
    source = np.asarray(source_image.convert("RGBA"))
    candidate = np.asarray(candidate_image.convert("RGBA"))
    changed = np.any(source != candidate, axis=2)
    protected = full_mask == 0
    outside_changed = changed & protected
    alpha_changed = source[:, :, 3] != candidate[:, :, 3]
    ys, xs = np.where(changed)
    profiles_equal = source_info["icc_profile"] == candidate_info["icc_profile"]
    protected_count = int(np.count_nonzero(protected))
    pixel_pass = not bool(np.any(outside_changed))
    lossless_candidate = candidate_info["format"] == "PNG"
    passed = pixel_pass and profiles_equal and protected_count > 0 and lossless_candidate
    return {
        "schema": "moso.mask-preservation/0.2",
        "scope": "decoded-rgba-and-icc-only",
        "status": "pass" if passed else "block",
        "inputs": {name: {"path": str(path.resolve()), "sha256": sha256(path)} for name, path in
                   (("source", source_path), ("candidate", candidate_path), ("mask", mask_path))},
        "source_dimensions": list(source_image.size),
        "candidate_dimensions": list(candidate_image.size),
        "source_mode": source_info["mode"],
        "candidate_mode": candidate_info["mode"],
        "mask_origin": list(origin),
        "mask_dimensions": list(coverage.size),
        "mask_convention": "white=replace, black=protect, gray=blend",
        "mask_nonzero_pixels": int(np.count_nonzero(full_mask)),
        "protected_pixels": protected_count,
        "changed_pixels": int(np.count_nonzero(changed)),
        "outside_mask_changed_pixels": int(np.count_nonzero(outside_changed)),
        "outside_mask_alpha_changed_pixels": int(np.count_nonzero(alpha_changed & protected)),
        "outside_mask_preserved_exactly": pixel_pass,
        "icc_profile_preserved": profiles_equal,
        "source_icc_sha256": profile_hash(source_info["icc_profile"]),
        "candidate_icc_sha256": profile_hash(candidate_info["icc_profile"]),
        "candidate_is_lossless_format": lossless_candidate,
        "protected_region_verified": passed,
        "changed_bbox": None if xs.size == 0 else [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
        "not_evaluated": ["target semantic success", "identity", "aesthetics", "metadata other than ICC", "correctness of the chosen mask"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("mask", type=Path)
    parser.add_argument("--mask-origin", type=parse_origin, default=(0, 0))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output:
            reject_input_overwrite(args.output, [args.source, args.candidate, args.mask])
        report = verify(args.source, args.candidate, args.mask, args.mask_origin)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
