#!/usr/bin/env python3
"""Seal three blind observations and aggregate evidence-bound review recommendations."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from image_contract import sha256
from review_integrity import CATEGORIES

ROOT = Path(__file__).resolve().parents[1]
BLIND_FIELDS = ("prompt_hidden", "first_read", "eye_path", "inferred_narrative", "observed_anomalies")


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def validate(value: dict, name: str) -> None:
    schema = read(ROOT / "schemas" / name)
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise ValueError(f"{name}: {errors[0].message}")


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("review times must include a timezone")
    return parsed


def resolve(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def checked_blind(path: Path, artifact_hash: str) -> dict:
    value = read(path)
    validate(value, "blind-observation.schema.json")
    if value["artifact_sha256"] != artifact_hash:
        raise ValueError("blind observation names a different artifact")
    return value


def seal_observations(artifact: Path, observations: list[Path], generation_context: str | None = None) -> dict:
    if len(observations) != 3:
        raise ValueError("a panel requires exactly three blind observations")
    artifact_hash = sha256(artifact)
    members = []
    now = datetime.now(timezone.utc)
    for path in observations:
        blind = checked_blind(path, artifact_hash)
        if timestamp(blind["committed_at"]) > now:
            raise ValueError("blind observation cannot be committed in the future")
        members.append({"reviewer_id": blind["reviewer_id"], "review_context_id": blind["review_context_id"],
                        "blind_path": str(path.resolve()), "blind_sha256": sha256(path)})
    if len({m["reviewer_id"] for m in members}) != 3 or len({m["review_context_id"] for m in members}) != 3:
        raise ValueError("panel reviewers and contexts must be distinct")
    if generation_context and generation_context in {m["review_context_id"] for m in members}:
        raise ValueError("a generating context cannot vote as an independent reviewer")
    return {"schema": "moso.review-panel-seal/0.1", "artifact_path": str(artifact.resolve()),
            "artifact_sha256": artifact_hash, "generation_context_id": generation_context,
            "created_at": now.isoformat(), "members": members}


def aggregate(seal_path: Path, spec_path: Path, votes: list[Path]) -> dict:
    if len(votes) != 3:
        raise ValueError("a panel requires exactly three votes; missing reviewers are not abstentions")
    seal = read(seal_path)
    validate(seal, "review-panel-seal.schema.json")
    artifact = resolve(seal["artifact_path"], seal_path.parent)
    artifact_hash = sha256(artifact)
    if artifact_hash != seal["artifact_sha256"]:
        raise ValueError("artifact changed after the blind pass")
    sealed_at = timestamp(seal["created_at"])
    if sealed_at > datetime.now(timezone.utc):
        raise ValueError("seal timestamp is in the future")
    members = {m["reviewer_id"]: m for m in seal["members"]}
    contexts = {m["review_context_id"] for m in seal["members"]}
    if len(members) != 3 or len(contexts) != 3 or seal["generation_context_id"] in contexts:
        raise ValueError("seal requires three distinct non-generating contexts")
    read(spec_path)  # A bounded review brief may be used instead of a full generation Spec.
    spec_hash, seal_hash = sha256(spec_path), sha256(seal_path)
    seen: set[str] = set()
    counts: Counter = Counter()
    risks, records = [], []
    for vote_path in votes:
        vote = read(vote_path)
        validate(vote, "panel-vote.schema.json")
        who = vote["reviewer_id"]
        if who in seen or who not in members:
            raise ValueError("duplicate or unsealed reviewer")
        seen.add(who)
        member = members[who]
        if vote["review_context_id"] != member["review_context_id"]:
            raise ValueError("vote context does not match sealed reviewer")
        if (vote["artifact_sha256"], vote["spec_sha256"], vote["seal_sha256"]) != (artifact_hash, spec_hash, seal_hash):
            raise ValueError("vote does not bind current artifact, spec and seal hashes")
        blind_path = resolve(member["blind_path"], seal_path.parent)
        if sha256(blind_path) != member["blind_sha256"]:
            raise ValueError("sealed blind observation was modified")
        blind = checked_blind(blind_path, artifact_hash)
        if (blind["reviewer_id"], blind["review_context_id"]) != (who, member["review_context_id"]):
            raise ValueError("blind identity does not match seal")
        received = timestamp(vote["spec_received_at"])
        if not timestamp(blind["committed_at"]) <= sealed_at <= received:
            raise ValueError("spec was exposed before all blind observations were sealed")
        review_path = resolve(vote["review_path"], vote_path.parent)
        if sha256(review_path) != vote["review_sha256"]:
            raise ValueError("review changed after the vote")
        review = read(review_path)
        validate(review, "artifact-review.schema.json")
        reviewer = review["reviewer"]
        if reviewer["kind"] != "fresh-context-agent" or reviewer["independent_from_generation"] is not True:
            raise ValueError("this panel requires fresh independent agent contexts")
        if reviewer.get("identity_ref") != who or reviewer.get("session_ref") != member["review_context_id"]:
            raise ValueError("review identity/context does not match vote")
        if review.get("artifact_sha256") != artifact_hash:
            raise ValueError("review does not bind the inspected artifact")
        reviewed = timestamp(reviewer["reviewed_at"])
        if not received <= reviewed <= datetime.now(timezone.utc):
            raise ValueError("review time must follow spec exposure and cannot be in the future")
        if review["blind_pass"] != {key: blind[key] for key in BLIND_FIELDS}:
            raise ValueError("review rewrote the sealed first impression")
        if review["decision"]["release_authorized"] is not False:
            raise ValueError("panel votes cannot authorize publication")
        for category in CATEGORIES:
            findings = review["spec_pass"][category]
            if not findings:
                raise ValueError(f"all reviewers must inspect the common rubric: {category}")
            for finding in findings:
                if finding["severity"] >= 2:
                    if not finding.get("alternative_explanation", "").strip():
                        raise ValueError("major findings require an alternative explanation")
                    risks.append({"reviewer_id": who, "category": category, **finding})
        recommendation = review["decision"]["recommendation"]
        counts[recommendation] += 1
        records.append({"reviewer_id": who, "recommendation": recommendation, "vote_path": str(vote_path.resolve()),
                        "vote_sha256": sha256(vote_path), "review_path": str(review_path),
                        "priority_improvement": review["decision"]["priority_improvement"],
                        "remaining_risks": review["decision"].get("remaining_risks", [])})
    majority = next((name for name, count in counts.items() if count >= 2), None)
    # Disagreement and major evidence remain visible; voting never erases a concrete defect.
    action = "verify-findings" if risks else majority or "user-judgment"
    return {"schema": "moso.review-panel-result/0.1", "status": "valid-panel", "artifact_sha256": artifact_hash,
            "spec_sha256": spec_hash, "seal_sha256": seal_hash, "votes": records,
            "vote_counts": dict(counts), "majority_recommendation": majority,
            "recommended_next_action": action, "findings_requiring_verification": risks,
            "dissent": [r for r in records if r["recommendation"] != majority] if majority else records,
            "release_authorized": False, "automatic_execution_authorized": False,
            "limits": ["Voting records and hashes do not prove visual claims or enforce host context isolation.",
                       "Fresh contexts do not establish different model families or independent statistical errors.",
                       "Unknown historical generation context." if seal["generation_context_id"] is None else "Generation context identity is supplied by the host operator."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    first = sub.add_parser("seal")
    first.add_argument("--artifact", type=Path, required=True)
    first.add_argument("--observations", type=Path, nargs=3, required=True)
    first.add_argument("--generation-context")
    second = sub.add_parser("aggregate")
    second.add_argument("--seal", type=Path, required=True)
    second.add_argument("--spec", type=Path, required=True)
    second.add_argument("--votes", type=Path, nargs=3, required=True)
    for child in (first, second):
        child.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (seal_observations(args.artifact, args.observations, args.generation_context) if args.command == "seal"
                  else aggregate(args.seal, args.spec, args.votes))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Never silently replace a sealed or committed decision record.
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"output": str(args.output.resolve()), "status": result.get("status", "sealed"),
                      "recommended_next_action": result.get("recommended_next_action")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
