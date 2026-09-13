#!/usr/bin/env python3
"""Create, verify and deterministically replay a MoSoCanvas edit document."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

from composite_region import composite
from image_contract import profile_hash, read_raster, reject_input_overwrite, sha256


ROOT = Path(__file__).resolve().parents[1]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def validate_schema(value: dict[str, Any], name: str) -> None:
    schema = load_json(ROOT / "schemas" / name)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
        key=lambda error: str(list(error.path)),
    )
    if errors:
        error = errors[0]
        location = ".".join(map(str, error.path)) or "<root>"
        raise ValueError(f"{name} at {location}: {error.message}")


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    os.replace(temporary, path)


def resolve_ref(document_path: Path, ref: str) -> Path:
    path = Path(ref).expanduser()
    return path.resolve() if path.is_absolute() else (document_path.parent / path).resolve()


def asset_index(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    assets = document.get("assets") or []
    indexed = {str(item.get("id")): item for item in assets if isinstance(item, dict)}
    if len(indexed) != len(assets) or "None" in indexed:
        raise ValueError("edit state has duplicate or empty asset IDs")
    return indexed


def operation_index(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    operations = document.get("operations") or []
    indexed = {str(item.get("id")): item for item in operations if isinstance(item, dict)}
    if len(indexed) != len(operations) or "None" in indexed:
        raise ValueError("edit state has duplicate or empty operation IDs")
    return indexed


def verify_document(document: dict[str, Any], document_path: Path) -> None:
    validate_schema(document, "edit-state.schema.json")
    assets = asset_index(document)
    for field in ("original_asset_ref", "selected_anchor_asset_ref", "current_render_asset_ref"):
        if document[field] not in assets:
            raise ValueError(f"{field} does not resolve to a registered asset")

    canvas = document["canvas"]
    for ref in (document["selected_anchor_asset_ref"], document["current_render_asset_ref"]):
        asset = assets[ref]
        if [asset["width"], asset["height"]] != [canvas["width"], canvas["height"]]:
            raise ValueError(f"canvas asset {ref} has incompatible dimensions")

    for asset in assets.values():
        path = resolve_ref(document_path, asset["content_ref"])
        if not path.is_file():
            raise ValueError(f"registered asset is missing: {path}")
        if path.stat().st_size != asset["size_bytes"] or sha256(path) != asset["sha256"]:
            raise ValueError(f"registered asset changed after registration: {asset['id']}")

    operations = operation_index(document)
    seen: set[str] = set()
    for operation in document["operations"]:
        missing = set(operation["depends_on"]) - seen
        if missing:
            raise ValueError(
                f"operation {operation['id']} depends on missing or later operations: {sorted(missing)}"
            )
        patch = assets.get(operation["patch_asset_ref"])
        mask = assets.get(operation["mask_asset_ref"])
        raw_candidate = assets.get(operation["raw_candidate_asset_ref"])
        if patch is None or mask is None or raw_candidate is None:
            raise ValueError(
                f"operation {operation['id']} references an unknown candidate, patch or mask asset"
            )
        if patch["kind"] != "patch" or mask["kind"] != "mask" or raw_candidate["kind"] != "raw-candidate":
            raise ValueError(f"operation {operation['id']} uses an asset with the wrong kind")
        if [patch["width"], patch["height"]] != [mask["width"], mask["height"]]:
            raise ValueError(f"operation {operation['id']} patch and mask dimensions differ")
        x, y = operation["mask_origin_xy"]
        if x + patch["width"] > canvas["width"] or y + patch["height"] > canvas["height"]:
            raise ValueError(f"operation {operation['id']} exceeds the canvas")
        for ref_key, hash_key, label in (
            ("plan_ref", "plan_sha256", "edit plan"),
            ("attempt_review_ref", "attempt_review_sha256", "attempt review"),
            ("receipt_ref", "receipt_sha256", "edit receipt"),
            ("preservation_report_ref", "preservation_report_sha256", "preservation report"),
        ):
            evidence = resolve_ref(document_path, operation[ref_key])
            if not evidence.is_file() or sha256(evidence) != operation[hash_key]:
                raise ValueError(f"operation {operation['id']} {label} is missing or changed")
        seen.add(operation["id"])
    if len(seen) != len(operations):
        raise ValueError("edit operation graph is invalid")


def register_asset(
    document: dict[str, Any], document_path: Path, source: Path, kind: str
) -> dict[str, Any]:
    source = source.resolve()
    if not source.is_file():
        raise ValueError(f"asset source does not exist: {source}")
    digest = sha256(source)
    asset_id = f"asset-{kind}-{digest[:16]}"
    for asset in document.get("assets") or []:
        if asset["id"] == asset_id:
            if asset["sha256"] != digest:
                raise ValueError(f"asset ID collision: {asset_id}")
            return asset

    with Image.open(source) as image:
        image.load()
        width, height = image.size
        image_format = image.format or source.suffix.lstrip(".").upper() or "UNKNOWN"
        mode = image.mode
    suffix = source.suffix.lower() or ".bin"
    relative = Path("assets") / f"{digest}{suffix}"
    destination = document_path.parent / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256(destination) != digest:
            raise ValueError(f"content-addressed asset collision: {destination}")
    else:
        shutil.copyfile(source, destination)
    record = {
        "id": asset_id,
        "kind": kind,
        "content_ref": str(relative),
        "sha256": digest,
        "size_bytes": destination.stat().st_size,
        "width": width,
        "height": height,
        "format": image_format,
        "mode": mode,
    }
    document.setdefault("assets", []).append(record)
    return record


def create_document(source: Path, document_path: Path, document_id: str) -> dict[str, Any]:
    if document_path.exists():
        raise ValueError(f"edit document already exists: {document_path}")
    with Image.open(source) as image:
        image.load()
        if image.mode not in {"RGB", "RGBA"}:
            raise ValueError("edit document source must be explicitly prepared as RGB or RGBA")
        if image.getexif().get(274, 1) != 1:
            raise ValueError("normalize EXIF orientation before creating an edit document")
        width, height = image.size
        icc = image.info.get("icc_profile")
        mode = image.mode
    timestamp = now()
    document: dict[str, Any] = {
        "schema": "moso.edit-state/0.1",
        "document_id": document_id,
        "revision": 1,
        "created_at": timestamp,
        "updated_at": timestamp,
        "canvas": {
            "epoch": "canvas-0001",
            "width": width,
            "height": height,
            "mode": mode,
            "orientation": "normalized",
            "icc_sha256": profile_hash(icc),
        },
        "original_asset_ref": "pending",
        "selected_anchor_asset_ref": "pending",
        "current_render_asset_ref": "pending",
        "assets": [],
        "operations": [],
    }
    original = register_asset(document, document_path, source, "original")
    document["original_asset_ref"] = original["id"]
    document["selected_anchor_asset_ref"] = original["id"]
    document["current_render_asset_ref"] = original["id"]
    verify_document(document, document_path)
    atomic_write_json(document_path.parent / "revisions" / "000001.json", document)
    atomic_write_json(document_path, document)
    return document


def load_document(document_path: Path) -> dict[str, Any]:
    document_path = document_path.resolve()
    document = load_json(document_path)
    verify_document(document, document_path)
    return document


def asset_path(document: dict[str, Any], document_path: Path, ref: str) -> Path:
    asset = asset_index(document).get(ref)
    if asset is None:
        raise ValueError(f"unknown asset reference: {ref}")
    return resolve_ref(document_path, asset["content_ref"])


def render_operations(
    document: dict[str, Any],
    document_path: Path,
    operation_ids: list[str],
    output: Path,
) -> None:
    verify_document(document, document_path)
    inputs = [
        asset_path(document, document_path, ref)
        for ref in (document["selected_anchor_asset_ref"], document["current_render_asset_ref"])
    ]
    reject_input_overwrite(output, inputs)
    assets = asset_index(document)
    requested = set(operation_ids)
    if len(requested) != len(operation_ids):
        raise ValueError("operation replay list contains duplicate IDs")
    known = operation_index(document)
    missing = requested - set(known)
    if missing:
        raise ValueError(f"operation replay references unknown IDs: {sorted(missing)}")
    for operation_id in requested:
        missing_dependencies = set(known[operation_id]["depends_on"]) - requested
        if missing_dependencies:
            raise ValueError(
                f"operation replay omits dependencies of {operation_id}: {sorted(missing_dependencies)}"
            )
    with tempfile.TemporaryDirectory(prefix="mosocanvas-replay-") as directory:
        current = asset_path(document, document_path, document["selected_anchor_asset_ref"])
        step_index = 0
        for operation in document["operations"]:
            if operation["id"] not in requested:
                continue
            step_index += 1
            patch = resolve_ref(document_path, assets[operation["patch_asset_ref"]]["content_ref"])
            mask = resolve_ref(document_path, assets[operation["mask_asset_ref"]]["content_ref"])
            step = Path(directory) / f"step-{step_index:04d}.png"
            composite(current, patch, mask, tuple(operation["mask_origin_xy"]), step)
            current = step
        output.parent.mkdir(parents=True, exist_ok=True)
        if step_index:
            shutil.copyfile(current, output)
        else:
            image, info = read_raster(current)
            metadata = {
                key: info[key] for key in ("icc_profile", "dpi") if info[key] is not None
            }
            image.save(output, format="PNG", **metadata)


def render_document(document: dict[str, Any], document_path: Path, output: Path) -> None:
    render_operations(
        document,
        document_path,
        [operation["id"] for operation in document["operations"]],
        output,
    )


def commit_revision(
    document_path: Path, updated: dict[str, Any], expected_revision: int
) -> dict[str, Any]:
    document_path = document_path.resolve()
    lock_path = document_path.parent / ".edit-state.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        current = load_document(document_path)
        if current["revision"] != expected_revision:
            raise ValueError(
                f"stale edit state: expected revision {expected_revision}, current is {current['revision']}"
            )
        if updated.get("document_id") != current["document_id"]:
            raise ValueError("updated edit state belongs to a different document")
        updated["revision"] = expected_revision + 1
        updated["updated_at"] = now()
        verify_document(updated, document_path)
        revision_path = document_path.parent / "revisions" / f"{updated['revision']:06d}.json"
        atomic_write_json(revision_path, updated)
        atomic_write_json(document_path, updated)
        return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init")
    init.add_argument("source", type=Path)
    init.add_argument("--document", type=Path, required=True)
    init.add_argument("--id", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("document", type=Path)
    render = subparsers.add_parser("render")
    render.add_argument("document", type=Path)
    render.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            document = create_document(args.source, args.document, args.id)
            result = {"document": str(args.document.resolve()), "revision": document["revision"]}
        elif args.command == "verify":
            document = load_document(args.document)
            result = {
                "document": str(args.document.resolve()),
                "revision": document["revision"],
                "assets": len(document["assets"]),
                "operations": len(document["operations"]),
                "status": "pass",
            }
        else:
            document = load_document(args.document)
            render_document(document, args.document.resolve(), args.output)
            result = {"output": str(args.output.resolve()), "sha256": sha256(args.output)}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
