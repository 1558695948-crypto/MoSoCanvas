#!/usr/bin/env python3
"""Render catalog variants as original composition diagrams, not generated-art samples."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from compile_generation_brief import ROOT, canonical_digest, load_json, validate_schema


def build_board(pack_id: str, output: Path) -> dict:
    packs = {p.stem: p for p in (ROOT / "directions").glob("*.json")}
    if pack_id not in packs:
        raise ValueError(f"unknown direction pack: {pack_id}")
    pack = load_json(packs[pack_id])
    validate_schema(pack, "direction-pack.schema.json")
    variants = pack["variants"]
    if len({v["id"] for v in variants}) != len(variants):
        raise ValueError("direction variants must have unique IDs")
    if output.suffix.lower() != ".png" or output.resolve().is_relative_to(ROOT):
        raise ValueError("write a PNG outside the installed skill directory")
    width, column, height = max(840, len(variants) * 360 + 48), 360, 640
    board = Image.new("RGB", (width, height), "#f3f3f0")
    draw = ImageDraw.Draw(board)
    title = ImageFont.load_default(size=28)
    body = ImageFont.load_default(size=17)
    small = ImageFont.load_default(size=14)
    draw.text((28, 24), "MoSoCanvas / " + pack_id, font=title, fill="#20242b")
    draw.text((28, 69), "Composition diagrams / catalog v" + pack["version"], font=body, fill="#535b66")
    for i, variant in enumerate(variants):
        x, y = 28 + i * column, 138
        draw.rectangle((x, y, x + 320, y + 352), fill="#dfe3e8")
        # The same technical grayscale key makes the spatial decision comparable.
        if variant["preview"] == "occlusion":
            draw.polygon([(x+55,y+352),(x+135,y+208),(x+276,y+352)], fill="#a1a9b5")
            draw.ellipse((x+155,y+101,x+199,y+145), fill="#343b46")
            draw.polygon([(x+173,y+144),(x+140,y+244),(x+210,y+243)], fill="#343b46")
            draw.line((x+186,y+171,x+255,y+151), fill="#343b46", width=13)
            draw.polygon([(x,y),(x+70,y),(x+97,y+352),(x,y+352)], fill="#626b77")
            draw.ellipse((x+268,y+230,x+284,y+246), fill="#343b46")
            caption = "A side view; a clue beyond the action."
        elif variant["preview"] == "address":
            draw.ellipse((x+125,y+61,x+202,y+138), fill="#626b77")
            draw.polygon([(x+139,y+142),(x+84,y+318),(x+247,y+318),(x+190,y+142)], fill="#626b77")
            draw.polygon([(x+151,y+189),(x+235,y+235),(x+270,y+310),(x+201,y+324)], fill="#343b46")
            draw.rectangle((x+190,y+276,x+245,y+307), fill="#fafafa")
            draw.line((x+23,y+26,x+92,y+26), fill="#a1a9b5", width=9)
            caption = "The gesture addresses the viewer."
        elif variant["preview"] == "trace":
            draw.line((x,y+201,x+320,y+201), fill="#a1a9b5", width=2)
            draw.ellipse((x+126,y+255,x+242,y+290), fill="#a1a9b5")
            draw.ellipse((x+162,y+223,x+228,y+257), outline="#626b77", width=5)
            draw.polygon([(x+98,y+137),(x+174,y+166),(x+143,y+241),(x+73,y+211)], fill="#343b46")
            draw.line((x+203,y+274,x+272,y+319), fill="#626b77", width=6)
            caption = "Two connected traces imply an event."
        else:
            raise ValueError("unsupported diagram grammar")
        draw.text((x,y+371), f"{i+1:02d} / {variant['id']}", font=body, fill="#20242b")
        draw.text((x,y+404), caption, font=small, fill="#535b66")
    draw.text((28, 589), "SCHEMATIC ONLY / No image model run / Subject, palette and lighting remain task-specific.", font=small, fill="#535b66")
    output.parent.mkdir(parents=True, exist_ok=True)
    board.save(output, format="PNG")
    return {"output": str(output.resolve()), "pack": pack_id, "pack_sha256": canonical_digest(pack),
            "variants": [v["id"] for v in variants], "type": "composition-diagram", "generated_artwork": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", default="editorial-depth")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build_board(args.pack, args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
