#!/usr/bin/env python3
"""Prepare an immutable bounded-edit plan and transparent model input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile

from build_region_mask import build_region_assets, parse_crop
from edit_state import (
    asset_index,
    asset_path,
    atomic_write_json,
    load_document,
    now,
    render_operations,
    validate_schema,
)
from image_contract import reject_input_overwrite, sha256


def prepare(
    document_path: Path,
    regions_path: Path,
    output_dir: Path,
    operation_id: str,
    target: str,
    *,
    crop_text: str | None = None,
    grow: int = 0,
    feather: float = 0,
    warm_skin_gate: bool = False,
    depends_on: list[str] | None = None,
    generation_scope: str = "cropped-context",
) -> dict:
    document_path = document_path.resolve()
    regions_path = regions_path.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ValueError(f"edit plan output directory already exists: {output_dir}")
    document = load_document(document_path)
    if operation_id in {item["id"] for item in document["operations"]}:
        raise ValueError(f"operation ID is already committed: {operation_id}")
    dependencies = depends_on or []
    known_operations = {item["id"] for item in document["operations"]}
    missing = set(dependencies) - known_operations
    if missing:
        raise ValueError(f"depends_on contains unknown operations: {sorted(missing)}")
    if generation_scope not in {"cropped-context", "full-frame-context"}:
        raise ValueError(f"unsupported generation scope: {generation_scope}")

    outputs = {
        "mask": output_dir / "write-mask.png",
        "prepared": output_dir / "prepared-input.png",
        "preview": output_dir / "mask-preview.png",
        "conditioning": output_dir / "conditioning-render.png",
        "plan": output_dir / "edit-plan.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing:
        raise ValueError(f"edit plan output already exists: {existing[0]}")
    if len({str(path) for path in outputs.values()}) != len(outputs):
        raise ValueError("edit plan outputs must be distinct")

    base_ref = document["current_render_asset_ref"]
    base = asset_index(document)[base_ref]
    base_path = asset_path(document, document_path, base_ref)
    for output in outputs.values():
        reject_input_overwrite(output, [document_path, regions_path, base_path])
    try:
        region_data = json.loads(regions_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid regions JSON: {exc}") from exc
    if not isinstance(region_data, dict):
        raise ValueError("regions JSON must be an object")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="mosocanvas-prepare-", dir=output_dir.parent
    ) as directory:
        temporary_conditioning = Path(directory) / "conditioning-render.png"
        render_operations(document, document_path, dependencies, temporary_conditioning)
        crop = parse_crop(crop_text, (base["width"], base["height"]))
        mask, prepared, preview, placed = build_region_assets(
            temporary_conditioning,
            region_data,
            crop,
            grow=grow,
            feather=feather,
            warm_skin_gate=warm_skin_gate,
        )
        mask_minimum, mask_maximum = mask.getextrema()
        if mask_minimum != 0 or mask_maximum == 0:
            raise ValueError(
                "write mask must contain editable and protected pixels for a bounded edit"
            )
        output_dir.mkdir()
        shutil.copyfile(temporary_conditioning, outputs["conditioning"])
    mask.save(outputs["mask"], format="PNG")
    prepared.save(outputs["prepared"], format="PNG")
    preview.save(outputs["preview"], format="PNG")
    x, y, width, height = placed
    plan = {
        "schema": "moso.edit-plan/0.1",
        "id": operation_id,
        "document_id": document["document_id"],
        "expected_revision": document["revision"],
        "created_at": now(),
        "target": target,
        "depends_on": dependencies,
        "base": {
            "asset_ref": base_ref,
            "path": str(base_path),
            "sha256": base["sha256"],
            "width": base["width"],
            "height": base["height"],
        },
        "conditioning": {
            "policy": "clean-anchor-plus-explicit-dependencies",
            "anchor_asset_ref": document["selected_anchor_asset_ref"],
            "included_operation_ids": dependencies,
            "render_ref": str(outputs["conditioning"]),
            "render_sha256": sha256(outputs["conditioning"]),
        },
        "operation": {
            "scope": "region",
            "generation_scope": generation_scope,
            "commit_scope": "coverage-mask",
            "preservation_requirement": "exact-outside-write-mask",
        },
        "region": {
            "coordinate_space": "canvas-pixels-top-left",
            "read_box_xywh": [x, y, width, height],
            "mask_origin_xy": [x, y],
            "write_mask_ref": str(outputs["mask"]),
            "write_mask_sha256": sha256(outputs["mask"]),
            "prepared_input_ref": str(outputs["prepared"]),
            "prepared_input_sha256": sha256(outputs["prepared"]),
            "prepared_input_size": [width, height],
            "mask_convention": "white-replace-black-protect-gray-blend",
            "preview_ref": str(outputs["preview"]),
            "preview_sha256": sha256(outputs["preview"]),
        },
        "capabilities": {
            "native_mask_argument": False,
            "deterministic_compositing": True,
            "pixel_preservation_from_model": "unverified",
        },
        "expected_checks": [
            "outside-mask-rgba-and-icc",
            "target-semantic-success",
            "mask-boundary-and-context",
        ],
    }
    validate_schema(plan, "edit-plan.schema.json")
    atomic_write_json(outputs["plan"], plan)
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("regions", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--crop", help="x,y,width,height in canvas coordinates")
    parser.add_argument("--grow", type=int, default=0)
    parser.add_argument("--feather", type=float, default=0)
    parser.add_argument("--warm-skin-gate", action="store_true")
    parser.add_argument("--depends-on", action="append", default=[])
    parser.add_argument(
        "--generation-scope",
        choices=["cropped-context", "full-frame-context"],
        default="cropped-context",
    )
    args = parser.parse_args(argv)
    try:
        plan = prepare(
            args.document,
            args.regions,
            args.output_dir,
            args.id,
            args.target,
            crop_text=args.crop,
            grow=args.grow,
            feather=args.feather,
            warm_skin_gate=args.warm_skin_gate,
            depends_on=args.depends_on,
            generation_scope=args.generation_scope,
        )
    except (KeyError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"plan": str((args.output_dir / "edit-plan.json").resolve()), "id": plan["id"], "expected_revision": plan["expected_revision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
