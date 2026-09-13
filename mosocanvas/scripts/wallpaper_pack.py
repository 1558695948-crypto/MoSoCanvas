#!/usr/bin/env python3
"""Build deterministic, signed wallpaper sales packs from approved artwork.

The command deliberately performs layout work only: EXIF normalization, high-quality
resampling, aspect-ratio cover crops, approved signature compositing, contact-sheet
preview, manifest generation, and deterministic ZIP packaging. It never generates or
extends image content.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable
import zipfile

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, ImageStat
except ImportError:  # pragma: no cover - exercised by the CLI error path.
    Image = ImageChops = ImageDraw = ImageFont = ImageOps = ImageStat = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = PROJECT_ROOT / "mosocanvas"
BRAND_ROOT = SKILL_ROOT / "assets" / "brand"
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}


@dataclass(frozen=True)
class Target:
    id: str
    family: str
    width: int
    height: int
    display_name: str


SELLABLE_TARGETS: tuple[Target, ...] = (
    Target("iphone-15-pro-max", "phone", 1290, 2796, "iPhone 15 Pro Max"),
    Target("iphone-16-pro-max", "phone", 1320, 2868, "iPhone 16 Pro Max"),
    Target("macbook-air-15", "computer", 2880, 1864, "MacBook Air 15-inch"),
    Target("macbook-pro-16", "computer", 3456, 2234, "MacBook Pro 16-inch"),
    Target("desktop-4k", "computer", 3840, 2160, "通用电脑 4K 16:9"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_pillow() -> None:
    if Image is None:
        raise RuntimeError(
            "wallpaper-pack requires Pillow. Install the project development dependencies "
            "with: python3 -m pip install -r mosocanvas/requirements-dev.txt"
        )


def slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return normalized.strip("-._") or "wallpaper"


def parse_focus(value: str) -> tuple[float, float]:
    try:
        x, y = (float(part.strip()) for part in value.split(",", 1))
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("focus must be written as x,y, for example 0.5,0.5") from exc
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise argparse.ArgumentTypeError("focus coordinates must be between 0 and 1")
    return x, y


def collect_inputs(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported image format: {path.suffix or path.name}")
        return [path.resolve()]
    if not path.is_dir():
        raise FileNotFoundError(path)
    files = sorted(
        item.resolve()
        for item in path.rglob("*")
        if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not files:
        raise FileNotFoundError(f"No supported image files found in {path}")
    return files


def load_rgb(path: Path) -> tuple[Image.Image, bytes | None]:
    with Image.open(path) as source:
        profile = source.info.get("icc_profile")
        image = ImageOps.exif_transpose(source).convert("RGB")
        return image.copy(), profile


def orientation(image: Image.Image) -> str:
    if image.height >= image.width * 1.05:
        return "portrait"
    if image.width >= image.height * 1.05:
        return "landscape"
    return "square"


def target_orientation(target: Target) -> str:
    return "portrait" if target.family == "phone" else "landscape"


def cover_resize_crop(
    source: Image.Image,
    target: Target,
    focus: tuple[float, float],
) -> tuple[Image.Image, dict]:
    source_width, source_height = source.size
    scale = max(target.width / source_width, target.height / source_height)
    scaled_size = (
        max(target.width, round(source_width * scale)),
        max(target.height, round(source_height * scale)),
    )
    resized = source.resize(scaled_size, Image.Resampling.LANCZOS)
    max_left = max(0, scaled_size[0] - target.width)
    max_top = max(0, scaled_size[1] - target.height)
    left = min(max_left, max(0, round(max_left * focus[0])))
    top = min(max_top, max(0, round(max_top * focus[1])))
    crop_box = (left, top, left + target.width, top + target.height)
    output = resized.crop(crop_box)
    resized_area = scaled_size[0] * scaled_size[1]
    target_area = target.width * target.height
    crop_percent = max(0.0, (1.0 - target_area / resized_area) * 100.0)
    return output, {
        "source_size_px": [source_width, source_height],
        "scaled_size_px": list(scaled_size),
        "cover_crop_box_px": list(crop_box),
        "crop_percent": round(crop_percent, 3),
        "focus": [focus[0], focus[1]],
    }


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("Signature asset has no visible alpha pixels")
    return bbox


def load_signature(variant: str, visible_width: int, opacity_percent: int) -> Image.Image:
    path = BRAND_ROOT / f"moso-echo-signature-{variant}.png"
    with Image.open(path) as source:
        mark = source.convert("RGBA")
    mark = mark.crop(alpha_bbox(mark))
    mark_height = max(1, round(mark.height * visible_width / mark.width))
    mark = mark.resize((visible_width, mark_height), Image.Resampling.LANCZOS)
    alpha = mark.getchannel("A").point(
        lambda value: round(value * opacity_percent / 100.0)
    )
    mark.putalpha(alpha)
    return mark


def local_luminance(image: Image.Image, box: tuple[int, int, int, int]) -> float:
    sample = image.crop(box).resize((32, 32), Image.Resampling.BILINEAR)
    mean = ImageStat.Stat(sample.convert("RGB")).mean
    return 0.2126 * mean[0] + 0.7152 * mean[1] + 0.0722 * mean[2]


def apply_signature(
    image: Image.Image,
    signature_mode: str,
    visible_width_percent: float = 4.5,
    edge_margin_percent: float = 2.75,
    opacity_percent: int = 66,
) -> tuple[Image.Image, dict]:
    if signature_mode == "clean":
        return image.convert("RGB"), {"status": "not-applied", "mode": "clean"}

    width, height = image.size
    visible_width = max(1, round(width * visible_width_percent / 100.0))
    probe = load_signature("light", visible_width, opacity_percent)
    margin_x = round(width * edge_margin_percent / 100.0)
    margin_y = round(height * edge_margin_percent / 100.0)
    x = width - margin_x - probe.width
    y = height - margin_y - probe.height
    box = (x, y, x + probe.width, y + probe.height)
    luminance = local_luminance(image, box)
    variant = "light" if luminance < 128 else "dark"
    mark = load_signature(variant, visible_width, opacity_percent)
    result = image.convert("RGBA")
    result.alpha_composite(mark, (x, y))
    diff = ImageChops.difference(image.convert("RGB"), result.convert("RGB"))
    diff_box = diff.getbbox()
    if diff_box and not (
        diff_box[0] >= box[0]
        and diff_box[1] >= box[1]
        and diff_box[2] <= box[2]
        and diff_box[3] <= box[3]
    ):
        raise RuntimeError("Signature compositing changed pixels outside its declared region")
    return result.convert("RGB"), {
        "status": "applied",
        "asset": "moso-echo-signature-v1",
        "variant": variant,
        "corner": "bottom-right",
        "opacity_percent": opacity_percent,
        "visible_width_px": visible_width,
        "visible_width_percent": visible_width_percent,
        "edge_margin_percent": edge_margin_percent,
        "box_px": list(box),
        "local_luminance": round(luminance, 2),
        "actual_pixel_diff_bounds": list(diff_box) if diff_box else None,
    }


def save_png(image: Image.Image, path: Path, icc_profile: bytes | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {"optimize": True, "compress_level": 9}
    if icc_profile:
        kwargs["icc_profile"] = icc_profile
    image.save(path, format="PNG", **kwargs)


def fit_thumbnail(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    thumbnail = ImageOps.contain(image.convert("RGB"), size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (21, 24, 28))
    left = (size[0] - thumbnail.width) // 2
    top = (size[1] - thumbnail.height) // 2
    canvas.paste(thumbnail, (left, top))
    return canvas


def build_contact_sheet(records: list[dict], output: Path) -> None:
    if not records:
        return
    card_width, card_height = 560, 470
    columns = 2
    rows = (len(records) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * card_width, rows * card_height), (12, 14, 17))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, record in enumerate(records):
        image = Image.open(record["output"]).convert("RGB")
        card = fit_thumbnail(image, (card_width - 40, card_height - 90))
        x = (index % columns) * card_width + 20
        y = (index // columns) * card_height + 20
        sheet.paste(card, (x, y))
        label = f"{record['target_id']}  {record['dimensions'][0]}x{record['dimensions'][1]}"
        draw.text((x, y + card.height + 12), label, fill=(239, 228, 205), font=font)
        draw.text(
            (x, y + card.height + 28),
            f"crop {record['crop']['crop_percent']}%  |  {record['signature']['status']}",
            fill=(170, 177, 185),
            font=font,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG", optimize=True)


def write_readme(output_dir: Path, preset: str, records: list[dict], skipped: list[dict]) -> Path:
    path = output_dir / "README.md"
    lines = [
        "# MoSoCanvas 壁纸销售包",
        "",
        f"预设：`{preset}`",
        "",
        "本包由同一张已确认的原图按设备比例确定性适配生成：只做高质量缩放、比例裁切和标准 MoSo 签名合成，不做生成式扩图，不重新绘制主体。",
        "",
        "## 文件说明",
        "",
        "- `signed/`：带 MoSo 签名的销售预览/交付图；",
        "- `preview/contact-sheet.png`：多尺寸快速核对图；",
        "- `manifest.json`：源文件、尺寸、裁切、签名和 SHA-256 记录。",
        "",
        "## 使用提示",
        "",
        "电脑和手机屏幕比例不同，建议按设备类型分别使用对应文件，不要再次拉伸图片。",
        "签名已统一放在右下角；如需无签名母版，请在受控流程中使用 `--signature clean` 单独导出。",
    ]
    if skipped:
        lines.extend([
            "",
            "## 未输出的尺寸",
            "",
            "为保护构图，方向不匹配的目标默认跳过；如确实需要跨方向适配，可重新运行并加 `--include-mismatched`，但必须人工复核。",
        ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def create_zip(
    output_dir: Path,
    archive_path: Path,
    records: list[dict],
    readme_path: Path,
    preview_path: Path | None,
    manifest_path: Path,
) -> None:
    current_files = [readme_path, manifest_path]
    if preview_path is not None:
        current_files.append(preview_path)
    current_files.extend(Path(record["output"]) for record in records)
    files = sorted(
        path for path in current_files
        if path.is_file() and path.resolve() != archive_path.resolve()
    )
    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in files:
            info = zipfile.ZipInfo(
                f"{output_dir.name}/{path.relative_to(output_dir).as_posix()}",
                date_time=(2020, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def process_source(
    source_path: Path,
    output_dir: Path,
    targets: Iterable[Target],
    focus: tuple[float, float],
    signature_mode: str,
    include_mismatched: bool,
    source_count: int,
) -> tuple[list[dict], list[dict], dict]:
    source, icc_profile = load_rgb(source_path)
    source_orientation = orientation(source)
    source_hash = sha256(source_path)
    source_prefix = slug(source_path.stem)
    if source_count > 1:
        source_prefix = f"{source_prefix}--{source_hash[:8]}"
    records: list[dict] = []
    skipped: list[dict] = []

    for target in targets:
        matches = source_orientation == "square" or source_orientation == target_orientation(target)
        if not matches and not include_mismatched:
            skipped.append({
                "source": str(source_path),
                "target_id": target.id,
                "family": target.family,
                "dimensions": [target.width, target.height],
                "status": "skipped",
                "reason": f"source orientation {source_orientation} does not match target orientation {target_orientation(target)}",
            })
            continue

        adapted, crop = cover_resize_crop(source, target, focus)
        signed, signature = apply_signature(adapted, signature_mode)
        filename = f"{source_prefix}__{target.id}__{target.width}x{target.height}.png"
        output_path = output_dir / "signed" / filename
        save_png(signed, output_path, icc_profile)
        records.append({
            "source": str(source_path),
            "source_sha256": source_hash,
            "source_orientation": source_orientation,
            "target_id": target.id,
            "display_name": target.display_name,
            "family": target.family,
            "dimensions": [target.width, target.height],
            "output": str(output_path),
            "output_sha256": sha256(output_path),
            "crop": crop,
            "signature": signature,
        })
    return records, skipped, {
        "path": str(source_path),
        "sha256": source_hash,
        "dimensions": list(source.size),
        "orientation": source_orientation,
    }


def build_pack(args: argparse.Namespace) -> dict:
    require_pillow()
    input_path = args.input.resolve()
    sources = collect_inputs(input_path)
    if args.output_dir:
        output_dir = args.output_dir.resolve()
    else:
        stem = slug(input_path.stem if input_path.is_file() else input_path.name)
        output_dir = input_path.parent / f"{stem}-sellable-wallpaper-pack"
    output_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    skipped: list[dict] = []
    source_records: list[dict] = []
    for source_path in sources:
        generated, omitted, source_record = process_source(
            source_path=source_path,
            output_dir=output_dir,
            targets=SELLABLE_TARGETS,
            focus=args.focus,
            signature_mode=args.signature,
            include_mismatched=args.include_mismatched,
            source_count=len(sources),
        )
        records.extend(generated)
        skipped.extend(omitted)
        source_records.append(source_record)

    if not records:
        raise RuntimeError("No compatible wallpaper targets were generated")

    preview_path = output_dir / "preview" / "contact-sheet.png"
    if not args.no_preview:
        build_contact_sheet(records, preview_path)
    readme_path = write_readme(output_dir, args.preset, records, skipped)

    manifest = {
        "schema": "mosocanvas.wallpaper-pack/1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "preset": args.preset,
        "source_policy": "preserve-approved-artwork; deterministic-resize-crop-signature-only",
        "signature_mode": args.signature,
        "include_mismatched": args.include_mismatched,
        "focus": list(args.focus),
        "sources": source_records,
        "generated": records,
        "skipped": skipped,
        "files": {
            "readme": str(readme_path),
            "preview": str(preview_path) if not args.no_preview else None,
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    archive_path = output_dir.with_suffix(".zip")
    if not args.no_zip:
        create_zip(
            output_dir=output_dir,
            archive_path=archive_path,
            records=records,
            readme_path=readme_path,
            preview_path=None if args.no_preview else preview_path,
            manifest_path=manifest_path,
        )

    return {
        "schema": "mosocanvas.wallpaper-pack-result/1",
        "preset": args.preset,
        "output_dir": str(output_dir),
        "archive": str(archive_path) if not args.no_zip else None,
        "manifest": str(manifest_path),
        "generated_count": len(records),
        "skipped_count": len(skipped),
        "generated_dimensions": sorted({tuple(item["dimensions"]) for item in records}),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mosocanvas wallpaper-pack",
        description="Build a deterministic, signed wallpaper sales pack from approved artwork.",
    )
    parser.add_argument("input", type=Path, help="one image file or a directory of image masters")
    parser.add_argument("--preset", choices=("sellable",), default="sellable")
    parser.add_argument("--output-dir", type=Path, help="output pack directory")
    parser.add_argument(
        "--signature",
        choices=("signed", "clean"),
        default="signed",
        help="signed (default) applies the approved MoSo mark; clean omits it",
    )
    parser.add_argument(
        "--focus",
        type=parse_focus,
        default=(0.5, 0.5),
        metavar="X,Y",
        help="normalized cover-crop focus point, default 0.5,0.5",
    )
    parser.add_argument(
        "--include-mismatched",
        action="store_true",
        help="also force targets with the opposite orientation; review these manually",
    )
    parser.add_argument("--no-preview", action="store_true", help="skip contact-sheet generation")
    parser.add_argument("--no-zip", action="store_true", help="skip ZIP packaging")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = build_pack(args)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"mosocanvas wallpaper-pack: error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
