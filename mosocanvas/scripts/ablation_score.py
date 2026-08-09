#!/usr/bin/env python3
"""Validate and summarize a same-backend MoSoCanvas ablation without one total score."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import mean
from typing import Any

from evidence import EvidenceError, load_object


CONDITIONS = ("B0-direct", "B1-generic-clarify", "M0-mosocanvas")
METRICS = (
    "generation_calls", "elapsed_minutes", "material_user_corrections",
    "protected_decision_losses", "severity3_defects", "analysis_usefulness",
    "interaction_friction",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("study", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    blockers: list[str] = []
    try:
        study = load_object(args.study, "ablation study")
    except EvidenceError as exc:
        study = {}
        blockers.append(str(exc))

    if study.get("schema") != "moso.skill-ablation-study/0.1":
        blockers.append("study must use moso.skill-ablation-study/0.1")
    protocol = study.get("protocol") or {}
    for key in (
        "same_backend", "same_model_version", "same_source_brief", "same_input_assets",
        "same_generation_budget", "condition_order_randomized", "raters_blind_to_condition",
        "criteria_preregistered",
    ):
        if protocol.get(key) is not True:
            blockers.append(f"protocol requires {key}=true")

    task_ids: set[str] = set()
    task_classes: set[str] = set()
    values: dict[str, dict[str, list[float]]] = {
        condition: defaultdict(list) for condition in CONDITIONS
    }
    accepted: dict[str, list[float]] = defaultdict(list)
    rounds: dict[str, list[float]] = defaultdict(list)
    for index, task in enumerate(study.get("tasks") or [], start=1):
        task_id = str(task.get("task_id", ""))
        if not task_id or task_id in task_ids:
            blockers.append(f"task {index} has duplicate or empty task_id")
        task_ids.add(task_id)
        task_classes.add(str(task.get("task_class", "")))
        runs = task.get("runs") or []
        by_condition = {run.get("condition"): run for run in runs if isinstance(run, dict)}
        if set(by_condition) != set(CONDITIONS) or len(runs) != 3:
            blockers.append(f"task {task_id!r} must contain each ablation condition exactly once")
            continue
        budgets = {run.get("generation_calls") for run in runs}
        if len(budgets) != 1:
            blockers.append(f"task {task_id!r} does not have an equal generation budget")
        for condition, run in by_condition.items():
            accepted[condition].append(1.0 if run.get("accepted") else 0.0)
            if run.get("rounds_to_acceptance") is not None:
                rounds[condition].append(float(run["rounds_to_acceptance"]))
            for metric in METRICS:
                value = run.get(metric)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    values[condition][metric].append(float(value))

    comparison_ids: set[str] = set()
    raters: set[str] = set()
    preferences: dict[str, list[float]] = defaultdict(list)
    for index, item in enumerate(study.get("blind_preferences") or [], start=1):
        comparison_id = str(item.get("comparison_id", ""))
        if not comparison_id or comparison_id in comparison_ids:
            blockers.append(f"blind preference {index} has duplicate or empty comparison_id")
        comparison_ids.add(comparison_id)
        if item.get("task_id") not in task_ids:
            blockers.append(f"blind preference {comparison_id!r} references an unknown task")
        rater = str(item.get("rater_id", ""))
        if rater:
            raters.add(rater)
        a, b = item.get("condition_a"), item.get("condition_b")
        if not a or not b or a == b:
            blockers.append(f"blind preference {comparison_id!r} requires two different conditions")
            continue
        winner = item.get("winner")
        pair = " vs ".join(sorted((str(a), str(b))))
        if winner == "tie":
            preferences[pair].append(0.5)
        elif winner == "a":
            preferences[pair].append(1.0 if a == "M0-mosocanvas" else 0.0)
        elif winner == "b":
            preferences[pair].append(1.0 if b == "M0-mosocanvas" else 0.0)

    thresholds = study.get("thresholds") or {}
    task_count = len(task_ids)
    claim_eligible = (
        task_count >= int(thresholds.get("minimum_claim_tasks", 20))
        and len(raters) >= int(thresholds.get("minimum_raters", 3))
        and len(task_classes - {""}) >= 2
    )
    pilot_ready = task_count >= int(thresholds.get("minimum_pilot_tasks", 5))
    summaries: dict[str, Any] = {}
    for condition in CONDITIONS:
        summaries[condition] = {
            "tasks": len(accepted[condition]),
            "acceptance_rate": round(mean(accepted[condition]), 4) if accepted[condition] else None,
            "mean_rounds_to_acceptance_among_accepted": (
                round(mean(rounds[condition]), 4) if rounds[condition] else None
            ),
            "metric_means": {
                metric: round(mean(metric_values), 4) if metric_values else None
                for metric, metric_values in values[condition].items()
            },
        }

    report = {
        "schema": "moso.skill-ablation-summary/0.1",
        "status": "block" if blockers else (
            "claim-eligible" if claim_eligible else "pilot-only" if pilot_ready else "instrumentation-only"
        ),
        "tasks": task_count,
        "task_classes": len(task_classes - {""}),
        "raters": len(raters),
        "conditions": summaries,
        "blind_mosocanvas_preference": {
            pair: {"judgments": len(scores), "mosocanvas_share": round(mean(scores), 4)}
            for pair, scores in sorted(preferences.items()) if "M0-mosocanvas" in pair
        },
        "claim": (
            "No contribution claim is computed. Inspect paired task-level trade-offs and use a "
            "predeclared statistical analysis when the study is claim-eligible."
        ),
        "blockers": blockers,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
