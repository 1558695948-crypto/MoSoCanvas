#!/usr/bin/env python3
"""Validate a structured MoSoCanvas feedback delta before it changes a frozen run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SECTIONS = ("changes", "preserve", "prohibit", "relationships", "promotions")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("feedback delta must be a JSON object")
    return value


def validate(value: dict[str, Any]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    if value.get("schema") != "moso.feedback-delta/0.1":
        blockers.append("feedback delta must use moso.feedback-delta/0.1")
    for field in ("id", "task_id", "created_at", "source", "parent"):
        if not value.get(field):
            blockers.append(f"feedback delta requires {field}")

    source = value.get("source") or {}
    for field in ("kind", "message_ref", "summary"):
        if not source.get(field):
            blockers.append(f"feedback source requires {field}")
    parent = value.get("parent") or {}
    for field in ("spec_ref", "checkpoint_ref"):
        if not parent.get(field):
            blockers.append(f"feedback parent requires {field}")

    all_ids: set[str] = set()
    for section in SECTIONS:
        items = value.get(section)
        if not isinstance(items, list):
            blockers.append(f"feedback delta {section} must be a list")
            continue
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict) or not item.get("id"):
                blockers.append(f"{section} item {index} requires an id")
                continue
            item_id = str(item["id"])
            if item_id in all_ids:
                blockers.append(f"duplicate feedback constraint id: {item_id}")
            all_ids.add(item_id)

    if not all_ids:
        blockers.append("feedback delta must contain at least one change or constraint")

    verification = value.get("verification")
    covered: set[str] = set()
    if not isinstance(verification, list) or not verification:
        blockers.append("feedback delta requires verification")
    else:
        verification_ids: set[str] = set()
        for index, check in enumerate(verification, start=1):
            if not isinstance(check, dict):
                blockers.append(f"verification item {index} must be an object")
                continue
            check_id = check.get("id")
            if not check_id:
                blockers.append(f"verification item {index} requires id")
            elif check_id in verification_ids:
                blockers.append(f"duplicate verification id: {check_id}")
            else:
                verification_ids.add(str(check_id))
            for field in ("method", "pass_condition"):
                if not check.get(field):
                    blockers.append(f"verification item {index} requires {field}")
            covers = check.get("covers")
            if not isinstance(covers, list) or not covers:
                blockers.append(f"verification item {index} requires covers")
            else:
                covered.update(str(item) for item in covers)

    unknown = covered - all_ids
    uncovered = all_ids - covered
    if unknown:
        blockers.append(f"verification covers unknown ids: {sorted(unknown)}")
    if uncovered:
        blockers.append(f"feedback constraints lack verification: {sorted(uncovered)}")

    status = value.get("confirmation_status")
    if status == "pending":
        blockers.append("pending feedback cannot authorize execution")
    elif status not in {"confirmed", "inferred"}:
        blockers.append("confirmation_status must be confirmed, inferred, or pending")
    if status == "inferred":
        warnings.append("inferred feedback may require user confirmation if it changes strategy")

    return blockers, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate feedback coverage; this does not infer user intent."
    )
    parser.add_argument("feedback_delta", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        value = load(args.feedback_delta)
        blockers, warnings = validate(value)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        blockers, warnings = [f"feedback delta cannot be loaded: {exc}"], []

    report = {
        "schema": "moso.feedback-validation/0.1",
        "feedback_delta": str(args.feedback_delta.resolve()),
        "status": "block" if blockers else "pass",
        "blockers": blockers,
        "warnings": warnings,
        "not_evaluated": ["whether the feedback interpretation matches the user's intent"],
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
