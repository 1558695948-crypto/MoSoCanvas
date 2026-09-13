"""Shared decoded-pixel rules for lossless repair and its evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_input_overwrite(output: Path, inputs: list[Path]) -> None:
    for path in inputs:
        if output.resolve() == path.resolve() or (output.exists() and path.exists() and output.samefile(path)):
            raise ValueError("output must not overwrite an input or its hard-link alias")


def read_raster(path: Path) -> tuple[Image.Image, dict]:
    with Image.open(path) as original:
        original.load()
        if original.mode not in {"RGB", "RGBA"}:
            raise ValueError(f"{path}: use an explicitly prepared RGB or RGBA source, got {original.mode}")
        if original.getexif().get(274, 1) != 1:
            raise ValueError(f"{path}: normalize EXIF orientation before defining pixel coordinates")
        info = {"mode": original.mode, "format": original.format,
                "icc_profile": original.info.get("icc_profile"), "dpi": original.info.get("dpi")}
        raster = original.convert("RGBA") if "transparency" in original.info else original.copy()
        return raster, info


def read_coverage_mask(path: Path) -> Image.Image:
    with Image.open(path) as mask:
        if mask.mode not in {"1", "L"} or "transparency" in mask.info:
            raise ValueError("repair mask must be grayscale coverage: white edits, black protects; API alpha masks need explicit conversion")
        return mask.convert("L")


def placed_box(origin: tuple[int, int], size: tuple[int, int], canvas: tuple[int, int]) -> tuple[int, int, int, int]:
    x, y = origin
    width, height = size
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > canvas[0] or y + height > canvas[1]:
        raise ValueError("placed mask/crop exceeds source bounds")
    return x, y, x + width, y + height


def profile_hash(profile: bytes | None) -> str | None:
    return hashlib.sha256(profile).hexdigest() if profile is not None else None
