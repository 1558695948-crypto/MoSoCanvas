#!/usr/bin/env python3
"""Composite a generated crop into an immutable source through a supplied mask."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from image_contract import placed_box, read_coverage_mask, read_raster, reject_input_overwrite


def composite(source_path: Path, crop_path: Path, mask_path: Path, origin: tuple[int, int], output_path: Path) -> None:
    reject_input_overwrite(output_path, [source_path, crop_path, mask_path])
    if output_path.suffix.lower() != ".png":
        raise ValueError("bounded repair requires PNG output; lossy encoding can change protected pixels")
    source, source_info = read_raster(source_path)
    generated, generated_info = read_raster(crop_path)
    mask = read_coverage_mask(mask_path)
    if generated.size != mask.size:
        raise ValueError(f"generated crop {generated.size} != mask {mask.size}")
    if source_info["icc_profile"] and generated_info["icc_profile"] and source_info["icc_profile"] != generated_info["icc_profile"]:
        raise ValueError("source and generated crop have different ICC profiles; normalize the crop explicitly")
    box = placed_box(origin, mask.size, source.size)
    mode = "RGBA" if "A" in source.getbands() or "A" in generated.getbands() else "RGB"
    output = source.convert(mode)
    replacement = Image.composite(generated.convert(mode), output.crop(box), mask)
    output.paste(replacement, origin)
    metadata = {key: source_info[key] for key in ("icc_profile", "dpi") if source_info[key] is not None}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.save(output_path, format="PNG", **metadata)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("generated_crop", type=Path)
    parser.add_argument("mask", type=Path)
    parser.add_argument("--crop-origin", required=True, help="x,y in source coordinates")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        x, y = [int(part) for part in args.crop_origin.split(",")]
        composite(args.source, args.generated_crop, args.mask, (x, y), args.output)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
