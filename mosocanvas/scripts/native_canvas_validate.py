#!/usr/bin/env python3
"""Validate Codex native Canvas feedback binding without inventing selection geometry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("native Canvas feedback must be a JSON object")
    return value


def validate(value: dict[str, Any]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    if value.get("schema") != "moso.native-canvas-feedback/0.1":
        blockers.append("native Canvas feedback must use moso.native-canvas-feedback/0.1")
    for field in (
        "id", "task_id", "created_at", "host", "interaction", "intent",
        "execution_scope", "bindings", "region_locators", "binding_status",
    ):
        if field not in value:
            blockers.append(f"native Canvas feedback requires {field}")
    if value.get("user_visible_contract") is not True:
        blockers.append("the compiled Canvas contract must be shown to the user before execution")

    host = value.get("host") or {}
    structured = host.get("structured_selection_available") is True
    if structured and not host.get("selection_payload_ref"):
        blockers.append("structured host selection requires selection_payload_ref")

    bindings = value.get("bindings")
    artifact_refs: set[str] = set()
    edit_parents: list[dict[str, Any]] = []
    if not isinstance(bindings, list) or not bindings:
        blockers.append("native Canvas feedback requires at least one artifact binding")
        bindings = []
    for index, binding in enumerate(bindings, start=1):
        if not isinstance(binding, dict):
            blockers.append(f"binding {index} must be an object")
            continue
        artifact_ref = str(binding.get("artifact_ref", ""))
        if not artifact_ref:
            blockers.append(f"binding {index} requires artifact_ref")
        elif artifact_ref in artifact_refs:
            blockers.append(f"duplicate Canvas artifact binding: {artifact_ref}")
        artifact_refs.add(artifact_ref)
        if binding.get("role") == "edit-parent":
            edit_parents.append(binding)

    intent = value.get("intent")
    scope = value.get("execution_scope")
    status = value.get("binding_status") or {}
    if intent == "edit":
        if not edit_parents:
            blockers.append("Canvas edit requires at least one edit-parent binding")
        for binding in edit_parents:
            if not binding.get("feedback_delta_ref"):
                blockers.append(
                    f"edit parent {binding.get('artifact_ref', '<unknown>')} requires its own feedback_delta_ref"
                )
        delta_refs = [
            str(binding.get("feedback_delta_ref"))
            for binding in edit_parents
            if binding.get("feedback_delta_ref")
        ]
        if len(delta_refs) != len(set(delta_refs)):
            blockers.append("each Canvas edit parent requires a distinct feedback delta")
        if status.get("status") != "bound":
            blockers.append("ambiguous or unbound Canvas edit cannot authorize execution")
        if status.get("confidence") == "low":
            blockers.append("low-confidence Canvas edit requires clarification")
        if scope in {"compare-only", "decision-only"}:
            blockers.append("Canvas edit uses an incompatible execution_scope")
    elif intent in {"compare", "select"} and scope != "compare-only":
        blockers.append("Canvas compare/select requires compare-only execution_scope")
    elif intent in {"accept", "reject"} and scope != "decision-only":
        blockers.append("Canvas accept/reject requires decision-only execution_scope")

    locators = value.get("region_locators")
    if not isinstance(locators, list):
        blockers.append("region_locators must be a list")
        locators = []
    locator_ids: set[str] = set()
    has_machine_geometry = False
    for index, locator in enumerate(locators, start=1):
        if not isinstance(locator, dict):
            blockers.append(f"region locator {index} must be an object")
            continue
        locator_id = str(locator.get("id", ""))
        if not locator_id or locator_id in locator_ids:
            blockers.append(f"region locator {index} has duplicate or empty id")
        locator_ids.add(locator_id)
        kind = locator.get("kind")
        geometry = locator.get("machine_geometry_available") is True
        if geometry:
            has_machine_geometry = True
        if kind == "mask" and not locator.get("mask_ref"):
            blockers.append(f"region locator {locator_id!r} requires mask_ref")
        if kind == "normalized-box" and not locator.get("normalized_box"):
            blockers.append(f"region locator {locator_id!r} requires normalized_box")
        if kind == "normalized-polygon" and not locator.get("normalized_polygon"):
            blockers.append(f"region locator {locator_id!r} requires normalized_polygon")
        if kind == "grid-region" and not locator.get("grid_region"):
            blockers.append(f"region locator {locator_id!r} requires grid_region")
        if kind == "host-selection" and not structured:
            if geometry:
                blockers.append("host-selection cannot claim machine geometry when the host did not expose it")
            if not locator.get("fallback_description"):
                blockers.append("unstructured host-selection requires fallback_description")
        if not geometry and kind not in {"natural-language", "grid-region", "host-selection"}:
            warnings.append(f"region locator {locator_id!r} is recorded without machine-readable geometry")

    if scope == "pixel-bounded-edit" and not has_machine_geometry:
        blockers.append("pixel-bounded edit requires a real mask or machine-readable geometry")
    if scope == "semantic-local-edit" and not locators:
        blockers.append("semantic local edit requires at least one region locator")
    if intent == "edit" and not structured:
        limitations = value.get("known_limitations") or []
        if not any("not" in str(item).lower() or "不可" in str(item) for item in limitations):
            warnings.append("unstructured Canvas edit should disclose that exact selection geometry is unavailable")

    return blockers, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate native Canvas binding; this does not inspect visual correctness."
    )
    parser.add_argument("canvas_feedback", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        value = load(args.canvas_feedback)
        blockers, warnings = validate(value)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        blockers, warnings = [f"native Canvas feedback cannot be loaded: {exc}"], []
    report = {
        "schema": "moso.native-canvas-validation/0.1",
        "canvas_feedback": str(args.canvas_feedback.resolve()),
        "status": "block" if blockers else "pass",
        "blockers": blockers,
        "warnings": warnings,
        "not_evaluated": [
            "whether the host selection corresponds to the intended pixels",
            "whether the generated edit satisfies the user's visual intent"
        ]
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
