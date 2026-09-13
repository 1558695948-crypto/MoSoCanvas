#!/usr/bin/env python3
"""Commit a reviewed bounded-edit preview as a non-destructive operation."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil
import tempfile

from PIL import ImageChops

from attempt_review_validate import validate as validate_attempt_review
from composite_region import composite
from edit_state import (
    asset_index, asset_path, atomic_write_json, commit_revision, load_document,
    load_json, now, register_asset, render_document, resolve_ref, validate_schema,
    verify_document,
)
from image_contract import read_coverage_mask, read_raster, reject_input_overwrite, sha256
from verify_mask_preservation import verify


def verify_binding(path: Path, expected_hash: str, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")
    if sha256(path) != expected_hash:
        raise ValueError(f"{label} changed after it was bound")


def decoded_equal(first: Path, second: Path) -> bool:
    left, left_info = read_raster(first)
    right, right_info = read_raster(second)
    return (
        left.size == right.size
        and left_info["icc_profile"] == right_info["icc_profile"]
        and ImageChops.difference(left.convert("RGBA"), right.convert("RGBA")).getbbox() is None
    )


def load_context(
    document_path: Path, plan_path: Path, candidate_path: Path
) -> tuple[dict, dict, Path, Path, dict]:
    document_path = document_path.resolve()
    plan_path = plan_path.resolve()
    candidate_path = candidate_path.resolve()
    document = load_document(document_path)
    plan = load_json(plan_path)
    validate_schema(plan, "edit-plan.schema.json")
    if plan["document_id"] != document["document_id"]:
        raise ValueError("edit plan belongs to a different document")
    if plan["expected_revision"] != document["revision"]:
        raise ValueError(
            f"stale edit plan: expected revision {plan['expected_revision']}, current is {document['revision']}"
        )
    if plan["id"] in {operation["id"] for operation in document["operations"]}:
        raise ValueError(f"operation is already committed: {plan['id']}")
    known_operations = {operation["id"] for operation in document["operations"]}
    missing = set(plan["depends_on"]) - known_operations
    if missing:
        raise ValueError(f"edit plan has unknown dependencies: {sorted(missing)}")

    base_ref = document["current_render_asset_ref"]
    base_asset = asset_index(document)[base_ref]
    base_path = asset_path(document, document_path, base_ref)
    base_binding = plan["base"]
    if base_binding["asset_ref"] != base_ref or base_binding["sha256"] != base_asset["sha256"]:
        raise ValueError("edit plan base is not the current committed render")
    if Path(base_binding["path"]).resolve() != base_path:
        raise ValueError("edit plan base path is not the current committed render")
    verify_binding(base_path, base_binding["sha256"], "base render")

    region = plan["region"]
    conditioning = plan["conditioning"]
    if conditioning["anchor_asset_ref"] != document["selected_anchor_asset_ref"]:
        raise ValueError("edit plan conditioning anchor is no longer selected")
    if conditioning["included_operation_ids"] != plan["depends_on"]:
        raise ValueError("edit plan conditioning operations do not match depends_on")
    conditioning_path = resolve_ref(plan_path, conditioning["render_ref"])
    verify_binding(conditioning_path, conditioning["render_sha256"], "conditioning render")
    mask_path = resolve_ref(plan_path, region["write_mask_ref"])
    prepared_path = resolve_ref(plan_path, region["prepared_input_ref"])
    verify_binding(mask_path, region["write_mask_sha256"], "write mask")
    verify_binding(prepared_path, region["prepared_input_sha256"], "prepared input")
    mask = read_coverage_mask(mask_path)
    candidate, _ = read_raster(candidate_path)
    if list(mask.size) != region["prepared_input_size"] or candidate.size != mask.size:
        raise ValueError("candidate, prepared input and write mask dimensions must match")
    return document, plan, base_path, mask_path, region


def stage(
    document_path: Path, plan_path: Path, candidate_path: Path,
    output_path: Path, report_path: Path,
) -> dict:
    document_path, plan_path, candidate_path = (
        document_path.resolve(), plan_path.resolve(), candidate_path.resolve()
    )
    output_path, report_path = output_path.resolve(), report_path.resolve()
    _, _, base_path, mask_path, region = load_context(
        document_path, plan_path, candidate_path
    )
    for output in (output_path, report_path):
        if output.exists():
            raise ValueError(f"staged edit evidence already exists: {output}")
        reject_input_overwrite(
            output, [document_path, plan_path, candidate_path, base_path, mask_path]
        )
    composite(base_path, candidate_path, mask_path, tuple(region["mask_origin_xy"]), output_path)
    preservation = verify(base_path, output_path, mask_path, tuple(region["mask_origin_xy"]))
    if preservation["status"] != "pass":
        output_path.unlink(missing_ok=True)
        raise ValueError("staged composite failed exact protected-pixel verification")
    atomic_write_json(report_path, preservation)
    return {
        "staged": str(output_path), "staged_sha256": sha256(output_path),
        "preservation_report": str(report_path), "preservation_status": "pass",
    }


def commit(
    document_path: Path, plan_path: Path, candidate_path: Path,
    staged_path: Path, review_path: Path,
) -> dict:
    document_path, plan_path, candidate_path = (
        document_path.resolve(), plan_path.resolve(), candidate_path.resolve()
    )
    staged_path, review_path = staged_path.resolve(), review_path.resolve()
    document, plan, base_path, mask_path, region = load_context(
        document_path, plan_path, candidate_path
    )
    review = load_json(review_path)
    validate_schema(review, "attempt-review.schema.json")
    review_blockers, _ = validate_attempt_review(review)
    if review_blockers:
        raise ValueError("attempt review is invalid: " + "; ".join(review_blockers))
    if review.get("attempt_id") != plan["id"]:
        raise ValueError("attempt review does not match the edit plan")
    if resolve_ref(review_path, str(review.get("artifact_ref", ""))) != staged_path:
        raise ValueError("attempt review must bind to the staged composite")
    if not review.get("artifact_sha256"):
        raise ValueError("attempt review requires artifact_sha256 before commit")
    verify_binding(staged_path, review["artifact_sha256"], "reviewed staged composite")
    if (review.get("target_change") or {}).get("status") != "achieved":
        raise ValueError("only an achieved target change can be committed")
    if (review.get("protected_drift") or {}).get("status") not in {"none", "within-tolerance"}:
        raise ValueError("protected drift must be within tolerance before commit")
    if review.get("recommendation") != "accept":
        raise ValueError("attempt review must recommend accept before commit")

    workspace = document_path.parent
    report_path = workspace / "reports" / f"{plan['id']}-preservation.json"
    receipt_path = workspace / "receipts" / f"{plan['id']}.json"
    for output in (report_path, receipt_path):
        if output.exists():
            raise ValueError(f"commit evidence already exists: {output}")
        reject_input_overwrite(
            output, [document_path, plan_path, candidate_path, staged_path, review_path, base_path, mask_path]
        )

    with tempfile.TemporaryDirectory(prefix="mosocanvas-commit-") as directory:
        fresh, replay = Path(directory) / "render.png", Path(directory) / "replay.png"
        composite(base_path, candidate_path, mask_path, tuple(region["mask_origin_xy"]), fresh)
        if not decoded_equal(fresh, staged_path):
            raise ValueError("reviewed staged composite differs from the current plan and candidate")
        preservation = verify(base_path, fresh, mask_path, tuple(region["mask_origin_xy"]))
        if preservation["status"] != "pass":
            raise ValueError("deterministic composite failed exact protected-pixel verification")
        atomic_write_json(report_path, preservation)

        updated = copy.deepcopy(document)
        raw_candidate = register_asset(updated, document_path, candidate_path, "raw-candidate")
        patch = register_asset(updated, document_path, candidate_path, "patch")
        mask_asset = register_asset(updated, document_path, mask_path, "mask")
        render_asset = register_asset(updated, document_path, fresh, "render")
        receipt = {
            "schema": "moso.edit-receipt/0.1", "operation_id": plan["id"],
            "document_id": document["document_id"], "from_revision": document["revision"],
            "to_revision": document["revision"] + 1, "committed_at": now(),
            "plan": {"path": str(plan_path), "sha256": sha256(plan_path)},
            "candidate": {"path": str(candidate_path), "sha256": sha256(candidate_path)},
            "attempt_review": {"path": str(review_path), "sha256": sha256(review_path)},
            "patch_asset_ref": patch["id"], "mask_asset_ref": mask_asset["id"],
            "render_asset_ref": render_asset["id"],
            "preservation_report_ref": str(report_path), "preservation_status": "pass",
        }
        validate_schema(receipt, "edit-receipt.schema.json")
        atomic_write_json(receipt_path, receipt)
        operation = {
            "id": plan["id"], "status": "committed", "target": plan["target"],
            "depends_on": plan["depends_on"], "raw_candidate_asset_ref": raw_candidate["id"],
            "patch_asset_ref": patch["id"], "mask_asset_ref": mask_asset["id"],
            "mask_origin_xy": region["mask_origin_xy"], "plan_ref": str(plan_path),
            "plan_sha256": sha256(plan_path), "attempt_review_ref": str(review_path),
            "attempt_review_sha256": sha256(review_path), "receipt_ref": str(receipt_path),
            "receipt_sha256": sha256(receipt_path), "preservation_report_ref": str(report_path),
            "preservation_report_sha256": sha256(report_path),
        }
        updated["operations"].append(operation)
        updated["current_render_asset_ref"] = render_asset["id"]
        verify_document(updated, document_path)
        render_document(updated, document_path, replay)
        if not decoded_equal(fresh, replay):
            raise ValueError("operation graph replay differs from the reviewed composite")
        committed = commit_revision(document_path, updated, document["revision"])
    return {
        "document": str(document_path), "revision": committed["revision"],
        "operation_id": plan["id"], "receipt": str(receipt_path),
        "render": str(asset_path(committed, document_path, committed["current_render_asset_ref"])),
        "preservation_status": "pass",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--staged", type=Path, required=True)
    parser.add_argument("--attempt-review", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = commit(args.document, args.plan, args.candidate, args.staged, args.attempt_review)
        if args.output:
            render_path = Path(result["render"])
            reject_input_overwrite(
                args.output, [args.document, args.plan, args.candidate, args.staged, args.attempt_review, render_path]
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(render_path, args.output)
            result["output"] = str(args.output.resolve())
            result["output_sha256"] = sha256(args.output)
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
