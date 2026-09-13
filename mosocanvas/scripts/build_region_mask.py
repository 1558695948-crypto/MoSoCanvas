#!/usr/bin/env python3
"""Build a reusable soft region mask and transparent edit input from JSON shapes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from image_contract import placed_box, read_raster, reject_input_overwrite


def parse_crop(value: str | None, image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    if value is None:
        return 0, 0, image_size[0], image_size[1]
    parts = [int(part) for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("crop must be x,y,width,height")
    x, y, width, height = parts
    placed_box((x, y), (width, height), image_size)
    return x, y, width, height


def draw_regions(size: tuple[int, int], region_data: dict) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    regions = region_data.get("regions")
    if not isinstance(regions, list) or not regions:
        raise ValueError("regions document requires a non-empty regions list")
    for region in regions:
        kind = region.get("kind")
        if kind == "polygon":
            draw.polygon([tuple(point) for point in region["points"]], fill=255)
        elif kind == "ellipse":
            draw.ellipse(tuple(region["box"]), fill=255)
        elif kind == "rectangle":
            draw.rectangle(tuple(region["box"]), fill=255)
        else:
            raise ValueError(f"unsupported region kind: {kind}")
    return mask


def build_region_assets(
    source_path: Path,
    region_data: dict,
    crop: tuple[int, int, int, int] | None = None,
    *,
    grow: int = 0,
    feather: float = 0,
    warm_skin_gate: bool = False,
) -> tuple[Image.Image, Image.Image, Image.Image, tuple[int, int, int, int]]:
    source, _ = read_raster(source_path)
    source = source.convert("RGB")
    if crop is None:
        crop = (0, 0, source.width, source.height)
    crop_x, crop_y, crop_width, crop_height = crop
    placed_box((crop_x, crop_y), (crop_width, crop_height), source.size)
    crop_box = (crop_x, crop_y, crop_x + crop_width, crop_y + crop_height)

    full_mask = draw_regions(source.size, region_data)
    if warm_skin_gate:
        red, green, blue = source.split()
        gate = Image.new("L", source.size, 0)
        gate_pixels = gate.load()
        red_pixels = red.load()
        green_pixels = green.load()
        blue_pixels = blue.load()
        for y in range(source.height):
            for x in range(source.width):
                r = red_pixels[x, y]
                g = green_pixels[x, y]
                b = blue_pixels[x, y]
                luminance = (r * 54 + g * 183 + b * 19) // 256
                if luminance >= 42 and r >= g + 2 and g >= b + 1:
                    gate_pixels[x, y] = 255
        # Close small tonal gaps while keeping dark clothing and background excluded.
        gate = gate.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(3))
        full_mask = ImageChops.multiply(full_mask, gate)

    if grow < 0 or feather < 0:
        raise ValueError("grow and feather must be nonnegative")
    if grow > 0:
        kernel = grow * 2 + 1
        full_mask = full_mask.filter(ImageFilter.MaxFilter(kernel))
    if feather > 0:
        full_mask = full_mask.filter(ImageFilter.GaussianBlur(feather))

    cropped_source = source.crop(crop_box)
    cropped_mask = full_mask.crop(crop_box)

    rgba = cropped_source.convert("RGBA")
    # The native edit input shows the requested region through inverse alpha.
    rgba.putalpha(cropped_mask.point(lambda value: 255 - value))

    overlay = cropped_source.convert("RGBA")
    red = Image.new("RGBA", overlay.size, (255, 40, 20, 0))
    red.putalpha(cropped_mask.point(lambda value: round(value * 0.58)))
    preview = Image.alpha_composite(overlay, red)

    if cropped_mask.getbbox() is None:
        raise ValueError("the prepared crop contains no editable mask coverage")
    return cropped_mask, rgba, preview, crop


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("regions", type=Path)
    parser.add_argument("--mask", type=Path, required=True)
    parser.add_argument("--rgba", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--crop", help="x,y,width,height in source coordinates")
    parser.add_argument("--grow", type=int, default=0)
    parser.add_argument("--feather", type=float, default=0)
    parser.add_argument(
        "--warm-skin-gate",
        action="store_true",
        help="Intersect regions with a conservative warm, non-dark pixel gate.",
    )
    args = parser.parse_args()
    try:
        source, _ = read_raster(args.image)
        crop = parse_crop(args.crop, source.size)
        region_data = json.loads(args.regions.read_text(encoding="utf-8"))
        mask, rgba, preview, _ = build_region_assets(
            args.image,
            region_data,
            crop,
            grow=args.grow,
            feather=args.feather,
            warm_skin_gate=args.warm_skin_gate,
        )
        for output in (args.mask, args.rgba, args.preview):
            reject_input_overwrite(output, [args.image, args.regions])
        if len({str(path.resolve()) for path in (args.mask, args.rgba, args.preview)}) != 3:
            raise ValueError("mask, rgba and preview outputs must be distinct")
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    for path in (args.mask, args.rgba, args.preview):
        path.parent.mkdir(parents=True, exist_ok=True)
    mask.save(args.mask)
    rgba.save(args.rgba)
    preview.save(args.preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
