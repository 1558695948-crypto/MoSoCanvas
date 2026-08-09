#!/usr/bin/env python3
"""Validate the mandatory immediate review after one generative attempt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("attempt review must be a JSON object")
    return value


def validate(value: dict[str, Any]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    if value.get("schema") != "moso.attempt-review/0.1":
        blockers.append("attempt review must use moso.attempt-review/0.1")
    for field in (
        "id", "attempt_id", "artifact_ref", "reviewed_at", "scales",
        "strengths", "deviations", "technical_risks", "target_change",
        "protected_drift", "priority_improvement", "recommendation"
    ):
        if field not in value:
            blockers.append(f"attempt review requires {field}")
    if value.get("actual_artifact_inspected") is not True:
        blockers.append("attempt review must inspect the actual artifact")
    if value.get("communicated_to_user") is not True:
        blockers.append("attempt review must be communicated to the user")
    if not isinstance(value.get("scales"), list) or not value.get("scales"):
        blockers.append("attempt review requires at least one inspection scale")

    target = value.get("target_change") or {}
    if target.get("status") not in {
        "achieved", "partial", "missed", "unobservable", "not-applicable"
    }:
        blockers.append("target_change requires an observed status")
    if not target.get("variable") or not target.get("evidence"):
        blockers.append("target_change requires variable and evidence")
    if target.get("status") in {"missed", "unobservable"}:
        warnings.append("target change did not produce verified improvement")

    drift = value.get("protected_drift") or {}
    if drift.get("status") not in {
        "none", "within-tolerance", "exceeded", "unobservable"
    }:
        blockers.append("protected_drift requires an observed status")
    if not drift.get("evidence"):
        blockers.append("protected_drift requires evidence")
    if drift.get("status") == "exceeded":
        warnings.append("protected content drift exceeded tolerance")
    return blockers, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate immediate output inspection; this is not an independent release review."
    )
    parser.add_argument("attempt_review", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        value = load(args.attempt_review)
        blockers, warnings = validate(value)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        blockers, warnings = [f"attempt review cannot be loaded: {exc}"], []
    report = {
        "schema": "moso.attempt-review-validation/0.1",
        "attempt_review": str(args.attempt_review.resolve()),
        "status": "block" if blockers else "pass",
        "blockers": blockers,
        "warnings": warnings,
        "not_evaluated": ["whether the visual claims are correct", "release authorization"],
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
