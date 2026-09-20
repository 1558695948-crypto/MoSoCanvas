#!/usr/bin/env python3
"""Validate MoSoCanvas execution contracts without claiming visual quality."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from evidence import EvidenceError, load_object, load_registry, require_evidence
from attempt_review_validate import validate as validate_attempt_review
from feedback_validate import validate as validate_feedback_delta
from native_canvas_validate import validate as validate_native_canvas_feedback
from review_integrity import validate_authorized_review

PHASES_AFTER_FREEZE = {
    "preflight", "execute", "independent-review", "decision", "accept"
}
PHASES_AFTER_EXECUTION = {"independent-review", "decision", "accept"}
GENERATIVE_OPERATIONS = {
    "masked-generative", "full-frame-generative", "full-regeneration"
}
ROOT = Path(__file__).resolve().parents[1]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str, blockers: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        blockers.append(f"{label} cannot be loaded: {exc}")
        return {}
    if not isinstance(value, dict):
        blockers.append(f"{label} must be a JSON object")
        return {}
    return value


def resolve_local(ref: str, base: Path) -> Path | None:
    if not ref or ref.startswith(("http://", "https://", "codex://")):
        return None
    path = Path(ref).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def flag_missing_keys(
    value: dict[str, Any], keys: tuple[str, ...], label: str, blockers: list[str]
) -> None:
    for key in keys:
        if key not in value:
            blockers.append(f"{label} missing required field: {key}")


def validate_json_schema(
    value: dict[str, Any], schema_name: str, label: str, blockers: list[str]
) -> bool:
    schema = load_json(ROOT / "schemas" / schema_name, schema_name, blockers)
    if not schema:
        return False
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
        key=lambda error: str(list(error.path)),
    )
    for error in errors:
        location = ".".join(map(str, error.path)) or "<root>"
        blockers.append(f"{label} schema at {location}: {error.message}")
    return not errors


def same_reference(first: str, second: str, base: Path) -> bool:
    if first == second:
        return True
    first_path = resolve_local(first, base)
    second_path = resolve_local(second, base)
    return bool(first_path and second_path and first_path.resolve() == second_path.resolve())


def validate_edit_plan_attempt(
    state: dict[str, Any],
    attempt: dict[str, Any],
    label: str,
    base: Path,
    blockers: list[str],
) -> None:
    plan_ref = attempt.get("edit_plan_ref")
    if not plan_ref:
        blockers.append(f"{label} masked-generative execution requires edit_plan_ref")
        return
    plan_path = resolve_local(str(plan_ref), base)
    if plan_path is None or not plan_path.is_file():
        blockers.append(f"{label} edit plan is not a local file: {plan_ref}")
        return
    plan = load_json(plan_path, f"{label} edit plan", blockers)
    if not validate_json_schema(plan, "edit-plan.schema.json", f"{label} edit plan", blockers):
        return
    if plan.get("id") != attempt.get("attempt_id"):
        blockers.append(f"{label} edit plan id does not match attempt_id")
    checkpoint = state.get("approved_checkpoint") or {}
    checkpoint_hash = checkpoint.get("sha256")
    checkpoint_path = resolve_local(str(checkpoint.get("source_ref", "")), base)
    if checkpoint_hash and plan["base"]["sha256"].lower() != str(checkpoint_hash).lower():
        blockers.append(f"{label} edit plan base hash does not match approved checkpoint")
    elif checkpoint_path and checkpoint_path.is_file() and file_sha256(checkpoint_path) != plan["base"]["sha256"]:
        blockers.append(f"{label} edit plan base bytes do not match approved checkpoint")
    for ref_key, hash_key, name in (
        ("prepared_input_ref", "prepared_input_sha256", "prepared input"),
        ("write_mask_ref", "write_mask_sha256", "write mask"),
    ):
        path = resolve_local(str(plan["region"][ref_key]), plan_path.parent)
        if path is None or not path.is_file():
            blockers.append(f"{label} {name} is missing")
        elif file_sha256(path) != plan["region"][hash_key]:
            blockers.append(f"{label} {name} changed after planning")
    conditioning = plan["conditioning"]
    conditioning_path = resolve_local(str(conditioning["render_ref"]), plan_path.parent)
    if conditioning_path is None or not conditioning_path.is_file():
        blockers.append(f"{label} conditioning render is missing")
    elif file_sha256(conditioning_path) != conditioning["render_sha256"]:
        blockers.append(f"{label} conditioning render changed after planning")
    if conditioning["included_operation_ids"] != plan["depends_on"]:
        blockers.append(f"{label} conditioning operations do not match depends_on")

    document_ref = state.get("edit_document_ref")
    if not document_ref:
        blockers.append(f"{label} masked-generative execution requires edit_document_ref")
    else:
        document_path = resolve_local(str(document_ref), base)
        if document_path is None or not document_path.is_file():
            blockers.append(f"{label} edit document is not a local file")
        else:
            document = load_json(document_path, f"{label} edit document", blockers)
            if validate_json_schema(document, "edit-state.schema.json", f"{label} edit document", blockers):
                try:
                    from edit_state import verify_document as verify_edit_document

                    verify_edit_document(document, document_path)
                except (ImportError, OSError, ValueError) as exc:
                    blockers.append(f"{label} edit document integrity failed: {exc}")
                if document.get("document_id") != plan.get("document_id"):
                    blockers.append(f"{label} edit plan belongs to a different edit document")
                if document.get("selected_anchor_asset_ref") != conditioning.get("anchor_asset_ref"):
                    blockers.append(f"{label} conditioning anchor is not the selected clean anchor")
                assets = {
                    item.get("id"): item for item in document.get("assets", [])
                    if isinstance(item, dict)
                }
                current = assets.get(document.get("current_render_asset_ref")) or {}
                status = attempt.get("status")
                if status in {"planned", "generated"}:
                    if document.get("revision") != plan.get("expected_revision"):
                        blockers.append(f"{label} edit plan is stale for the current document revision")
                    if current.get("sha256") != plan["base"]["sha256"]:
                        blockers.append(f"{label} edit plan base is not the current committed render")
                elif status == "reviewed" and document.get("revision", 0) < plan.get("expected_revision", 0) + 1:
                    blockers.append(f"{label} reviewed edit was not committed to the edit document")

    if attempt.get("status") == "reviewed":
        receipt_ref = attempt.get("edit_receipt_ref")
        if not receipt_ref:
            blockers.append(f"{label} reviewed masked edit requires edit_receipt_ref")
            return
        receipt_path = resolve_local(str(receipt_ref), base)
        if receipt_path is None or not receipt_path.is_file():
            blockers.append(f"{label} edit receipt is not a local file")
            return
        receipt = load_json(receipt_path, f"{label} edit receipt", blockers)
        if not validate_json_schema(receipt, "edit-receipt.schema.json", f"{label} edit receipt", blockers):
            return
        if receipt.get("operation_id") != attempt.get("attempt_id"):
            blockers.append(f"{label} receipt operation_id does not match attempt_id")
        if (receipt.get("plan") or {}).get("sha256") != file_sha256(plan_path):
            blockers.append(f"{label} receipt does not bind to the attached edit plan")
        review_ref = attempt.get("attempt_review_ref")
        review_path = resolve_local(str(review_ref or ""), base)
        if (
            review_path is None
            or not review_path.is_file()
            or (receipt.get("attempt_review") or {}).get("sha256") != file_sha256(review_path)
        ):
            blockers.append(f"{label} receipt does not bind to the attached attempt review")
        if receipt.get("preservation_status") != "pass":
            blockers.append(f"{label} edit receipt lacks a passing preservation check")


def finish(
    args: argparse.Namespace, blockers: list[str], warnings: list[str]
) -> int:
    report = {
        "schema": "moso.preflight-report/0.6",
        "scope": "contract-integrity-only",
        "run_state": str(args.run_state.resolve()),
        "status": "block" if blockers else "pass",
        "blockers": blockers,
        "warnings": warnings,
        "not_evaluated": [
            "composition quality",
            "narrative effectiveness",
            "color and lighting quality",
            "physical plausibility",
            "AI residue",
            "user preference"
        ]
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 1 if blockers else 0


def validate_release_evidence(
    state: dict[str, Any], registry_path: Path, blockers: list[str]
) -> None:
    try:
        _, indexed = load_registry(registry_path)
    except EvidenceError as exc:
        blockers.append(str(exc))
        return

    required: list[tuple[str, set[str]]] = []
    for field, kinds in (
        ("spec_ref", {"visual-spec"}),
        ("shot_plan_ref", {"shot-plan"}),
        ("series_plan_ref", {"series-plan"}),
        ("release_review_ref", {"artifact-review"}),
        ("user_decision_ref", {"user-decision"}),
    ):
        value = state.get(field)
        if value:
            required.append((str(value), kinds))
        elif field in {"spec_ref", "release_review_ref", "user_decision_ref"}:
            blockers.append(f"phase accept requires {field}")

    checkpoint = state.get("approved_checkpoint") or {}
    if checkpoint.get("role") not in {None, "none", "reference"}:
        required.append((
            str(checkpoint.get("source_ref", "")),
            {"artifact", "composition-proof"}
        ))

    output_ids: set[str] = set()
    independent_review_ids: set[str] = set()
    attempt_review_ids: set[str] = set()
    comparison_ids: set[str] = set()
    feedback_ids: set[str] = set()
    canvas_feedback_ids: set[str] = set()
    for attempt in state.get("generation_attempts") or []:
        execution = attempt.get("execution") or {}
        prompt_ref = execution.get("prompt_ref")
        if prompt_ref:
            required.append((str(prompt_ref), {"prompt"}))
        output_ref = execution.get("output_ref")
        if output_ref:
            output_ids.add(str(output_ref))
            required.append((str(output_ref), {"artifact"}))
        attempt_review_ref = attempt.get("attempt_review_ref")
        if attempt_review_ref:
            attempt_review_ids.add(str(attempt_review_ref))
            required.append((str(attempt_review_ref), {"attempt-review"}))
        comparison_ref = attempt.get("attempt_comparison_ref")
        if comparison_ref:
            comparison_ids.add(str(comparison_ref))
            required.append((str(comparison_ref), {"attempt-comparison"}))
        for feedback_ref in attempt.get("feedback_delta_refs") or []:
            feedback_ids.add(str(feedback_ref))
            required.append((str(feedback_ref), {"feedback-delta"}))
        for canvas_ref in attempt.get("native_canvas_feedback_refs") or []:
            canvas_feedback_ids.add(str(canvas_ref))
            required.append((str(canvas_ref), {"native-canvas-feedback"}))
        review_ref = attempt.get("independent_review_ref")
        if review_ref:
            independent_review_ids.add(str(review_ref))
            required.append((str(review_ref), {"artifact-review"}))
    for feedback_ref in state.get("feedback_delta_refs") or []:
        feedback_ids.add(str(feedback_ref))
        required.append((str(feedback_ref), {"feedback-delta"}))
    for canvas_ref in state.get("native_canvas_feedback_refs") or []:
        canvas_feedback_ids.add(str(canvas_ref))
        required.append((str(canvas_ref), {"native-canvas-feedback"}))

    resolved: dict[str, Path] = {}
    for evidence_id, kinds in required:
        if not evidence_id:
            blockers.append("release evidence contains an empty id")
            continue
        try:
            _, path = require_evidence(evidence_id, indexed, registry_path, kinds)
            resolved[evidence_id] = path
        except EvidenceError as exc:
            blockers.append(str(exc))

    checkpoint_path = resolved.get(str(checkpoint.get("source_ref", "")))
    if checkpoint_path and checkpoint.get("sha256"):
        if file_sha256(checkpoint_path).lower() != checkpoint["sha256"].lower():
            blockers.append("checkpoint sha256 does not match registered source")

    for review_id in attempt_review_ids:
        if review_id not in resolved:
            continue
        try:
            review = load_object(resolved[review_id], "attempt review")
            review_blockers, _ = validate_attempt_review(review)
            blockers.extend(f"attempt review {review_id}: {item}" for item in review_blockers)
        except EvidenceError as exc:
            blockers.append(str(exc))
    for feedback_id in feedback_ids:
        if feedback_id not in resolved:
            continue
        try:
            delta = load_object(resolved[feedback_id], "feedback delta")
            delta_blockers, _ = validate_feedback_delta(delta)
            blockers.extend(f"feedback delta {feedback_id}: {item}" for item in delta_blockers)
        except EvidenceError as exc:
            blockers.append(str(exc))
    for canvas_id in canvas_feedback_ids:
        if canvas_id not in resolved:
            continue
        try:
            canvas_feedback = load_object(resolved[canvas_id], "native Canvas feedback")
            canvas_blockers, _ = validate_native_canvas_feedback(canvas_feedback)
            blockers.extend(
                f"native Canvas feedback {canvas_id}: {item}" for item in canvas_blockers
            )
            if canvas_feedback.get("task_id") != state.get("task_id"):
                blockers.append(
                    f"native Canvas feedback {canvas_id} task_id does not match run state"
                )
            linked_deltas = {
                str(binding.get("feedback_delta_ref"))
                for binding in canvas_feedback.get("bindings") or []
                if binding.get("feedback_delta_ref")
            }
            missing = linked_deltas - feedback_ids
            if missing:
                blockers.append(
                    f"native Canvas feedback {canvas_id} links unregistered feedback deltas: {sorted(missing)}"
                )
        except EvidenceError as exc:
            blockers.append(str(exc))
    for comparison_id in comparison_ids:
        if comparison_id not in resolved:
            continue
        try:
            comparison = load_object(resolved[comparison_id], "attempt comparison")
            if comparison.get("schema") != "moso.attempt-comparison/0.1":
                blockers.append(f"attempt comparison {comparison_id} has the wrong schema")
            if (comparison.get("target_change") or {}).get("status") == "unreviewed":
                blockers.append(f"attempt comparison {comparison_id} lacks visual target review")
        except EvidenceError as exc:
            blockers.append(str(exc))

    review_id = state.get("release_review_ref")
    decision_id = state.get("user_decision_ref")
    if review_id not in resolved or decision_id not in resolved:
        return
    if state.get("generation_attempts") and str(review_id) not in independent_review_ids:
        blockers.append(
            "release_review_ref must be an independent review from a recorded attempt"
        )
    try:
        review = load_object(resolved[str(review_id)], "release review")
        decision = load_object(resolved[str(decision_id)], "user decision")
    except EvidenceError as exc:
        blockers.append(str(exc))
        return

    spec_id = state.get("spec_ref")
    if spec_id in resolved:
        try:
            spec_document = load_object(resolved[str(spec_id)], "visual spec")
            if spec_document.get("schema") not in {
                "moso.visual-spec/0.1", "moso.visual-spec/0.2",
                "moso.visual-spec/0.3", "moso.visual-spec/0.4", "moso.visual-spec/0.5", "moso.visual-spec/0.6"
            }:
                blockers.append("registered visual spec has the wrong schema")
        except EvidenceError as exc:
            blockers.append(str(exc))

    shot_id = state.get("shot_plan_ref")
    if shot_id in resolved:
        try:
            shot_document = load_object(resolved[str(shot_id)], "shot plan")
            selection = shot_document.get("selection") or {}
            if selection.get("status") != "selected":
                blockers.append("registered shot plan must contain a selected composition")
            if selection.get("proof_type") not in {
                "three-value-thumbnail", "mass-map", "approved-layout"
            }:
                blockers.append("registered shot plan selection requires a composition proof")
            proof_ref = str(selection.get("proof_ref", ""))
            if not proof_ref:
                blockers.append("registered shot plan selection requires proof_ref")
            else:
                try:
                    require_evidence(
                        proof_ref, indexed, registry_path, {"composition-proof"}
                    )
                except EvidenceError as exc:
                    blockers.append(str(exc))
        except EvidenceError as exc:
            blockers.append(str(exc))

    series_id = state.get("series_plan_ref")
    if series_id in resolved:
        try:
            series_document = load_object(resolved[str(series_id)], "series plan")
            expected_frames = (state.get("output_requirements") or {}).get("frame_count")
            if series_document.get("frame_count") != expected_frames:
                blockers.append(
                    "registered series plan frame_count conflicts with output requirements"
                )
            pilot = series_document.get("pilot_gate") or {}
            if pilot.get("status") != "approved":
                blockers.append("registered series plan requires an approved pilot")
            pilot_review_ref = str(pilot.get("review_ref", ""))
            if not pilot_review_ref:
                blockers.append("approved pilot requires review_ref")
            else:
                try:
                    require_evidence(
                        pilot_review_ref, indexed, registry_path, {"artifact-review"}
                    )
                except EvidenceError as exc:
                    blockers.append(str(exc))
        except EvidenceError as exc:
            blockers.append(str(exc))

    reviewer = review.get("reviewer") or {}
    blind = review.get("blind_pass") or {}
    review_decision = review.get("decision") or {}
    if review.get("schema") != "moso.artifact-review/0.1":
        blockers.append("release review has the wrong schema")
    if reviewer.get("independent_from_generation") is not True:
        blockers.append("release review is not independent from generation")
    if reviewer.get("actual_artifact_inspected") is not True:
        blockers.append("release review did not inspect the actual artifact")
    if blind.get("prompt_hidden") is not True:
        blockers.append("release review did not perform a prompt-blind first pass")
    if review_decision.get("recommendation") != "accept":
        blockers.append("release review must recommend accept")
    if review_decision.get("release_authorized") is not True:
        blockers.append("release review does not authorize release")
    blockers.extend(
        validate_authorized_review(review, resolved[str(review_id)], registry_path)
    )

    artifact_id = str(review.get("artifact_ref", ""))
    try:
        require_evidence(artifact_id, indexed, registry_path, {"artifact"})
    except EvidenceError as exc:
        blockers.append(str(exc))
    checkpoint_id = str(checkpoint.get("source_ref", ""))
    if artifact_id not in output_ids | {checkpoint_id}:
        blockers.append("release review artifact is not a generated output or approved checkpoint")

    if decision.get("schema") != "moso.user-decision/0.1":
        blockers.append("user decision has the wrong schema")
    if decision.get("task_id") != state.get("task_id"):
        blockers.append("user decision task_id does not match run state")
    if decision.get("artifact_ref") != artifact_id:
        blockers.append("user decision artifact does not match release review")
    expected_user_decision = (state.get("quality_status") or {}).get("user_acceptance")
    if decision.get("decision") != expected_user_decision:
        blockers.append("user decision does not match quality_status.user_acceptance")
    if decision.get("actor") != "user":
        blockers.append("user decision actor must be user")


def validate_preservation_checks(
    state: dict[str, Any], base: Path, blockers: list[str], registry_path: Path | None = None
) -> None:
    """Recompute each explicit per-candidate pixel claim; never trust a stored pass flag."""
    checks = state.get("preservation_checks") or []
    claimed_reports = {
        item.get("evidence_ref") for item in state.get("verification", [])
        if item.get("method") == "decoded-rgba-and-icc" and item.get("status") == "pass"
    }
    if not checks and not claimed_reports:
        return
    try:
        from verify_mask_preservation import verify
        indexed = load_registry(registry_path)[1] if registry_path else None

        def resolve(ref: str, kinds: set[str]) -> Path:
            if indexed is not None:
                return require_evidence(ref, indexed, registry_path, kinds)[1]
            path = resolve_local(ref, base)
            if path is None or not path.is_file():
                raise ValueError(f"preservation input is not a local file: {ref}")
            return path.resolve()

        checked_reports: set[str] = set()
        checkpoint = state.get("approved_checkpoint") or {}
        for check in checks:
            paths = {name: resolve(check[name + "_ref"], {"artifact", "composition-proof"} if name == "source" else
                                   {"artifact"} if name == "candidate" else {"other"})
                     for name in ("source", "candidate", "mask", "report")}
            if checkpoint.get("role") not in {None, "none", "reference"}:
                expected = resolve(checkpoint.get("source_ref", ""), {"artifact", "composition-proof"})
                if paths["source"] != expected or (checkpoint.get("sha256") and file_sha256(expected).lower() != checkpoint["sha256"].lower()):
                    raise ValueError("preservation source does not match the approved checkpoint")
            origin = check["mask_origin"]
            if len(origin) != 2 or any(type(v) is not int or v < 0 for v in origin):
                raise ValueError("preservation mask_origin must contain two nonnegative integers")
            fresh = verify(paths["source"], paths["candidate"], paths["mask"], tuple(origin))
            stored = load_object(paths["report"], "preservation report")
            # Paths can change when a evidence package moves; hash-bound content and measurements cannot.
            for name in ("source", "candidate", "mask"):
                if (stored.get("inputs", {}).get(name) or {}).get("sha256") != fresh["inputs"][name]["sha256"]:
                    raise ValueError(f"preservation report has a stale {name} hash")
            for key, value in fresh.items():
                if key != "inputs" and stored.get(key) != value:
                    raise ValueError(f"preservation report does not match recomputed {key}")
            if fresh["status"] != "pass":
                raise ValueError("protected RGBA samples or ICC failed preservation verification")
            checked_reports.add(check["report_ref"])
        if claimed_reports - checked_reports:
            raise ValueError("pixel preservation pass requires a matching, recomputed preservation_checks report")
    except (ImportError, EvidenceError, OSError, ValueError, KeyError, TypeError) as exc:
        blockers.append(f"preservation: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check structural readiness; this does not inspect or approve image aesthetics."
    )
    parser.add_argument("run_state", type=Path)
    parser.add_argument("--shot-plan", type=Path)
    parser.add_argument("--series-plan", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    blockers: list[str] = []
    warnings: list[str] = []
    state = load_json(args.run_state, "run state", blockers)
    base = args.run_state.resolve().parent

    if state.get("schema") != "moso.run-state/0.6":
        blockers.append(
            "run state must migrate to moso.run-state/0.6; legacy review fields cannot "
            "authorize execution or acceptance"
        )
        if state.get("phase") == "accept":
            legacy_quality = state.get("quality_status") or {}
            if legacy_quality.get("user_acceptance") not in {
                "accepted", "accepted-with-tradeoff"
            }:
                blockers.append("legacy phase accept lacks actual user acceptance")
            blockers.append("legacy phase accept lacks an independent release review")
        return finish(args, blockers, warnings)

    schema_valid = validate_json_schema(
        state, "run-state.schema.json", "run state", blockers
    )
    if not schema_valid and (
        not isinstance(state.get("approved_checkpoint", {}), dict)
        or not isinstance(state.get("attempt_budget", {}), dict)
        or not isinstance(state.get("quality_status", {}), dict)
        or not isinstance(state.get("output_requirements", {}), dict)
        or not isinstance(state.get("generation_attempts", []), list)
        or any(
            not isinstance(item, dict)
            for item in state.get("generation_attempts", [])
        )
        or not isinstance(state.get("verification", []), list)
    ):
        return finish(args, blockers, warnings)

    flag_missing_keys(
        state,
        (
            "schema", "task_id", "mode", "phase", "approved_checkpoint",
            "allowed_changes", "protected_elements", "attempt_budget",
            "output_requirements", "verification", "direction_approval_status",
            "quality_status"
        ),
        "run state",
        blockers,
    )

    mode = state.get("mode")
    phase = state.get("phase")
    checkpoint = state.get("approved_checkpoint") or {}
    budget = state.get("attempt_budget") or {}
    quality = state.get("quality_status") or {}
    output = state.get("output_requirements") or {}
    release_registry_mode = phase == "accept" and bool(
        args.registry or state.get("evidence_registry_ref")
    )

    if mode in {"production", "repair"}:
        if checkpoint.get("role") in {None, "none", "reference"}:
            blockers.append("production/repair requires an approved composition, pilot, mockup, master, or output")
        if not state.get("allowed_changes"):
            blockers.append("production/repair requires at least one allowed change")
        if not state.get("protected_elements"):
            blockers.append("production/repair requires protected elements")

    if mode == "repair":
        lineage = state.get("lineage") or {}
        if not lineage.get("parent_ref") or not lineage.get("operation"):
            blockers.append("repair requires lineage.parent_ref and lineage.operation")
        elif not same_reference(
            str(lineage["parent_ref"]), str(checkpoint.get("source_ref", "")), base
        ):
            blockers.append("repair lineage.parent_ref must match the approved checkpoint source")

    source_ref = checkpoint.get("source_ref", "")
    local_checkpoint = None if release_registry_mode else resolve_local(source_ref, base)
    if local_checkpoint:
        if not local_checkpoint.exists():
            blockers.append(f"checkpoint source does not exist: {local_checkpoint}")
        elif checkpoint.get("sha256"):
            if file_sha256(local_checkpoint).lower() != checkpoint["sha256"].lower():
                blockers.append("checkpoint sha256 does not match source")
        else:
            warnings.append("local checkpoint has no sha256")

    for asset in state.get("required_assets") or []:
        if asset.get("status") == "missing":
            blockers.append(f"required asset is missing: {asset.get('role', 'unknown')}")
        elif asset.get("status") in {"placeholder", "unverified"}:
            warnings.append(f"asset is not authoritative: {asset.get('role', 'unknown')}")

    for kind in ("generative", "repair"):
        used = budget.get(f"{kind}_used")
        allowed = budget.get(kind)
        if used is None or allowed is None:
            blockers.append(f"attempt_budget requires {kind} and {kind}_used")
        elif used > allowed:
            blockers.append(f"{kind} attempt budget exceeded: {used}>{allowed}")

    shot_plan_path = args.shot_plan
    if (
        not shot_plan_path
        and state.get("shot_plan_ref")
        and not release_registry_mode
    ):
        shot_plan_path = resolve_local(state["shot_plan_ref"], base)
    if phase in PHASES_AFTER_FREEZE and mode in {"direction", "production"}:
        if not state.get("shot_plan_ref") and not shot_plan_path:
            blockers.append("post-freeze direction/production requires shot_plan_ref")
        elif shot_plan_path:
            shot = load_json(shot_plan_path, "shot plan", blockers)
            selection = shot.get("selection") or {}
            if selection.get("status") != "selected":
                blockers.append("shot plan must contain a selected composition")
            if selection.get("proof_type") not in {
                "three-value-thumbnail", "mass-map", "approved-layout"
            }:
                blockers.append("selected shot requires a composition proof")
            if not selection.get("proof_ref"):
                blockers.append("selected shot requires proof_ref")

    frame_count = output.get("frame_count", 1)
    series_plan_path = args.series_plan
    if (
        not series_plan_path
        and state.get("series_plan_ref")
        and not release_registry_mode
    ):
        series_plan_path = resolve_local(state["series_plan_ref"], base)
    if frame_count and frame_count > 1:
        if not state.get("series_plan_ref") and not series_plan_path:
            blockers.append("multi-frame output requires series_plan_ref")
        elif series_plan_path:
            series = load_json(series_plan_path, "series plan", blockers)
            if series.get("frame_count") != frame_count:
                blockers.append("series plan frame_count conflicts with output requirements")
            pilot = series.get("pilot_gate") or {}
            if phase in {"execute", "independent-review", "decision", "accept"}:
                if pilot.get("status") != "approved":
                    blockers.append("series expansion requires an approved pilot")
                if not pilot.get("review_ref"):
                    blockers.append("approved pilot requires an independent review_ref")

    attempts = state.get("generation_attempts") or []
    lineage = state.get("lineage") or {}
    is_generative = (
        (budget.get("generative") or 0) > 0
        or lineage.get("operation") in GENERATIVE_OPERATIONS
    )
    if is_generative and not attempts:
        blockers.append("generative execution requires generation_attempts")
    attempt_ids = [attempt.get("attempt_id") for attempt in attempts]
    if len(set(attempt_ids)) != len(attempt_ids):
        blockers.append("generation attempt IDs must be unique")
    prior_attempt_ids: set[str] = set()
    for index, attempt in enumerate(attempts, start=1):
        parent_id = attempt.get("parent_attempt_id")
        if parent_id and parent_id not in prior_attempt_ids:
            blockers.append(
                f"generation attempt {index} parent_attempt_id must refer to an earlier attempt"
            )
        if attempt.get("attempt_id"):
            prior_attempt_ids.add(str(attempt["attempt_id"]))

    def validate_feedback_refs(refs: list[str], label: str) -> None:
        for ref in refs:
            if release_registry_mode:
                continue
            path = resolve_local(str(ref), base)
            if not path:
                warnings.append(f"{label} feedback delta is not locally verifiable: {ref}")
                continue
            document = load_json(path, f"{label} feedback delta", blockers)
            delta_blockers, delta_warnings = validate_feedback_delta(document)
            blockers.extend(f"{label}: {item}" for item in delta_blockers)
            warnings.extend(f"{label}: {item}" for item in delta_warnings)

    def validate_canvas_refs(
        refs: list[str], feedback_refs: list[str], label: str
    ) -> None:
        feedback_set = {str(ref) for ref in feedback_refs}
        for ref in refs:
            if release_registry_mode:
                continue
            path = resolve_local(str(ref), base)
            if not path:
                warnings.append(f"{label} native Canvas feedback is not locally verifiable: {ref}")
                continue
            document = load_json(path, f"{label} native Canvas feedback", blockers)
            canvas_blockers, canvas_warnings = validate_native_canvas_feedback(document)
            blockers.extend(f"{label}: {item}" for item in canvas_blockers)
            warnings.extend(f"{label}: {item}" for item in canvas_warnings)
            if document.get("task_id") != state.get("task_id"):
                blockers.append(f"{label} native Canvas feedback task_id does not match run state")
            linked_deltas = {
                str(binding.get("feedback_delta_ref"))
                for binding in document.get("bindings") or []
                if binding.get("feedback_delta_ref")
            }
            missing = linked_deltas - feedback_set
            if missing:
                blockers.append(
                    f"{label} native Canvas feedback links deltas not attached to the same run/attempt: {sorted(missing)}"
                )

    validate_feedback_refs(state.get("feedback_delta_refs") or [], "run state")
    validate_canvas_refs(
        state.get("native_canvas_feedback_refs") or [],
        state.get("feedback_delta_refs") or [],
        "run state",
    )
    observed_target_statuses: list[str] = []
    comparison_decisions: list[str] = []

    for index, attempt in enumerate(attempts, start=1):
        prefix = f"generation attempt {index}"
        flag_missing_keys(
            attempt,
            ("attempt_id", "status", "trajectory_response", "trajectory_reason"),
            prefix,
            blockers,
        )
        validate_feedback_refs(attempt.get("feedback_delta_refs") or [], prefix)
        validate_canvas_refs(
            attempt.get("native_canvas_feedback_refs") or [],
            attempt.get("feedback_delta_refs") or [],
            prefix,
        )
        brief = attempt.get("pre_generation_brief") or {}
        flag_missing_keys(
            brief,
            (
                "objective", "viewer_position", "first_read", "composition_geometry",
                "narrative_beat", "color_light_logic", "required_content",
                "protected_content", "main_risk", "communicated_to_user"
            ),
            f"{prefix} brief",
            blockers,
        )
        if brief.get("communicated_to_user") is not True:
            blockers.append(f"{prefix} brief must be communicated before generation")

        status = attempt.get("status")
        if (
            phase in {"execute", "independent-review", "decision", "accept"}
            and lineage.get("operation") == "masked-generative"
        ):
            validate_edit_plan_attempt(state, attempt, prefix, base, blockers)
        execution = attempt.get("execution") or {}
        if status in {"generated", "reviewed", "rejected"}:
            flag_missing_keys(
                execution,
                (
                    "backend", "interface", "model", "model_version", "prompt_ref",
                    "prompt_sha256", "parameters", "generated_at", "output_ref"
                ),
                f"{prefix} execution",
                blockers,
            )
            if (execution.get("model") is None or execution.get("model_version") is None) and not execution.get("observation_limits"):
                blockers.append(f"{prefix} unknown model metadata requires observation_limits")
        if phase in PHASES_AFTER_EXECUTION and status in {"planned", "generated"}:
            blockers.append(f"{prefix} must complete immediate review after execution")
        if status in {"reviewed", "rejected"}:
            review_ref = attempt.get("attempt_review_ref")
            if not review_ref:
                blockers.append(f"{prefix} {status} status requires attempt_review_ref")
            elif not release_registry_mode:
                review_path = resolve_local(str(review_ref), base)
                if not review_path:
                    warnings.append(f"{prefix} attempt review is not locally verifiable")
                else:
                    review = load_json(review_path, f"{prefix} attempt review", blockers)
                    review_blockers, review_warnings = validate_attempt_review(review)
                    blockers.extend(f"{prefix}: {item}" for item in review_blockers)
                    warnings.extend(f"{prefix}: {item}" for item in review_warnings)
                    if review.get("attempt_id") != attempt.get("attempt_id"):
                        blockers.append(f"{prefix} review attempt_id does not match")
                    observed_target_statuses.append(
                        str((review.get("target_change") or {}).get("status", "unobservable"))
                    )

            if attempt.get("parent_attempt_id"):
                comparison_ref = attempt.get("attempt_comparison_ref")
                if not comparison_ref:
                    blockers.append(f"{prefix} with parent_attempt_id requires attempt_comparison_ref")
                elif not release_registry_mode:
                    comparison_path = resolve_local(str(comparison_ref), base)
                    if not comparison_path:
                        warnings.append(f"{prefix} attempt comparison is not locally verifiable")
                    else:
                        comparison = load_json(
                            comparison_path, f"{prefix} attempt comparison", blockers
                        )
                        if comparison.get("schema") != "moso.attempt-comparison/0.1":
                            blockers.append(f"{prefix} comparison has the wrong schema")
                        target_status = (comparison.get("target_change") or {}).get("status")
                        if target_status == "unreviewed":
                            blockers.append(f"{prefix} comparison requires visual target review")
                        decision = str(comparison.get("trajectory_decision", ""))
                        comparison_decisions.append(decision)

    for index, attempt in enumerate(attempts[:-1], start=1):
        if attempt.get("status") == "generated" and any(
            later.get("status") == "planned" for later in attempts[index:]
        ):
            blockers.append(
                f"generation attempt {index} must be reviewed before another generation"
            )

    if attempts and attempts[-1].get("status") == "planned":
        response = attempts[-1].get("trajectory_response")
        if response == "continue" and (
            quality.get("protected_drift") == "exceeded"
            or quality.get("trajectory") == "worsening"
        ):
            blockers.append(
                "worsening trajectory or exceeded protected drift forbids continuing the same method"
            )
        non_improving = {"missed", "unobservable"}
        if len(observed_target_statuses) >= 2 and all(
            status in non_improving for status in observed_target_statuses[-2:]
        ) and response not in {"change-method", "branch"}:
            blockers.append(
                "two consecutive non-improving rounds require change-method or branch"
            )
        if comparison_decisions and comparison_decisions[-1] in {
            "change-method", "branch", "stop"
        } and response == "continue":
            blockers.append(
                "the latest comparison forbids continuing the same method"
            )

    if phase in {"execute", "independent-review", "decision", "accept"}:
        if state.get("direction_approval_status") not in {
            "approved", "user-overrode", "not-required"
        }:
            blockers.append("execution cannot proceed while direction approval is pending")

    if phase == "accept":
        if quality.get("user_acceptance") not in {"accepted", "accepted-with-tradeoff"}:
            blockers.append("phase accept requires actual user acceptance")
        if quality.get("independent_review") not in {"pass", "conditional"}:
            blockers.append("phase accept requires an independent review pass or conditional pass")
        if not state.get("release_review_ref"):
            blockers.append("phase accept requires release_review_ref")
        if not state.get("user_decision_ref"):
            blockers.append("phase accept requires user_decision_ref")
        reviewed_attempts = [
            attempt for attempt in attempts if attempt.get("status") == "reviewed"
        ]
        if is_generative and not reviewed_attempts:
            blockers.append("phase accept requires at least one reviewed generative attempt")
        registry_path = args.registry
        if not registry_path and state.get("evidence_registry_ref"):
            registry_path = resolve_local(str(state["evidence_registry_ref"]), base)
        if not registry_path:
            blockers.append("phase accept requires a local evidence registry")
        else:
            validate_release_evidence(state, registry_path, blockers)

    preservation_registry = args.registry
    if not preservation_registry and phase == "accept" and state.get("evidence_registry_ref"):
        preservation_registry = resolve_local(str(state["evidence_registry_ref"]), base)
    if phase == "accept" and state.get("preservation_checks") and not preservation_registry:
        blockers.append("accepted preservation checks require an evidence registry")
    else:
        validate_preservation_checks(state, base, blockers, preservation_registry if phase == "accept" else None)

    return finish(args, blockers, warnings)


if __name__ == "__main__":
    raise SystemExit(main())
