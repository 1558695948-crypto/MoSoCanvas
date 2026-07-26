#!/usr/bin/env python3
"""Validate MoSoCanvas state before production or repair execution."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_state", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    state = json.loads(args.run_state.read_text(encoding="utf-8"))
    blockers: list[str] = []
    warnings: list[str] = []

    required = [
        "schema", "task_id", "mode", "phase", "approved_checkpoint",
        "allowed_changes", "protected_elements", "attempt_budget",
        "output_requirements", "verification", "approval_status"
    ]
    for key in required:
        if key not in state:
            blockers.append(f"missing required field: {key}")

    mode = state.get("mode")
    phase = state.get("phase")
    checkpoint = state.get("approved_checkpoint") or {}
    if mode in {"production", "repair"}:
        if checkpoint.get("role") in {None, "none", "reference"}:
            blockers.append("production/repair requires an approved mockup, master, or output checkpoint")
        if not state.get("allowed_changes"):
            blockers.append("production/repair requires at least one allowed change")
        if not state.get("protected_elements"):
            blockers.append("production/repair requires protected elements")
    if mode == "repair":
        lineage = state.get("lineage") or {}
        if not lineage.get("parent_ref"):
            blockers.append("repair requires lineage.parent_ref")
        if not lineage.get("operation"):
            blockers.append("repair requires lineage.operation")

    source_ref = checkpoint.get("source_ref")
    if source_ref and not source_ref.startswith(("http://", "https://", "codex://")):
        source = Path(source_ref).expanduser()
        if not source.exists():
            blockers.append(f"checkpoint source does not exist: {source}")
        elif checkpoint.get("sha256"):
            actual = sha256(source)
            if actual.lower() != checkpoint["sha256"].lower():
                blockers.append("checkpoint sha256 does not match source")
        else:
            warnings.append("local checkpoint has no sha256")

    assets = state.get("required_assets") or []
    for asset in assets:
        if asset.get("status") == "missing":
            blockers.append(f"required asset is missing: {asset.get('role', 'unknown')}")
        elif asset.get("status") in {"placeholder", "unverified"}:
            warnings.append(f"asset is not authoritative: {asset.get('role', 'unknown')}")

    budget = state.get("attempt_budget") or {}
    for kind in ("generative", "repair"):
        used = budget.get(f"{kind}_used", 0)
        allowed = budget.get(kind)
        if allowed is not None and used > allowed:
            blockers.append(f"{kind} attempt budget exceeded: {used}>{allowed}")

    if phase in {"execute", "verify", "accept"} and state.get("approval_status") == "pending":
        blockers.append("execution cannot proceed while approval is pending")
    if not state.get("verification"):
        blockers.append("at least one verification check is required")

    report = {
        "schema": "moso.preflight-report/0.2",
        "run_state": str(args.run_state.resolve()),
        "status": "block" if blockers else "pass",
        "blockers": blockers,
        "warnings": warnings,
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
