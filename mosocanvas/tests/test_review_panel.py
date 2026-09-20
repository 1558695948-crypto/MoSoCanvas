from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from panel_review import aggregate, seal_observations, BLIND_FIELDS
from image_contract import sha256


class ReviewPanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.image = self.base / "image.png"
        Image.new("RGB", (8, 8), "gray").save(self.image)
        self.spec = self.base / "spec.json"
        self.write(self.spec, {"task": "fixture only"})
        self.blinds = []
        start = datetime.now(timezone.utc) - timedelta(minutes=5)
        for who in "ABC":
            path = self.base / f"{who}-blind.json"
            value = {"schema": "moso.blind-observation/0.1", "reviewer_id": who, "review_context_id": "review-"+who,
                     "artifact_sha256": sha256(self.image), "committed_at": start.isoformat(), "actual_artifact_inspected": True,
                     "prompt_hidden": True, "source_hidden": True, "first_read": "gray field", "eye_path": ["center"],
                     "inferred_narrative": "none", "observed_anomalies": [], "strengths": ["flat field"], "uncertainties": []}
            self.write(path, value)
            self.blinds.append(path)
        seal = seal_observations(self.image, self.blinds, "generation")
        seal["created_at"] = (start+timedelta(minutes=1)).isoformat()
        self.seal = self.base / "seal.json"
        self.write(self.seal, seal)
        self.votes = []
        template = json.loads((ROOT / "examples/artifact-review.example.json").read_text())
        for who, blind_path in zip("ABC", self.blinds):
            blind = json.loads(blind_path.read_text())
            review = copy.deepcopy(template)
            review["artifact_sha256"] = sha256(self.image)
            review["reviewer"].update(identity_ref=who, session_ref="review-"+who, reviewed_at=(start+timedelta(minutes=3)).isoformat())
            review["blind_pass"] = {key: blind[key] for key in BLIND_FIELDS}
            for category in review["spec_pass"]:
                review["spec_pass"][category] = [{"severity": 0, "claim": "fixture pass", "evidence_region": "whole image",
                                                "consequence": "fixture condition met", "confidence": "high"}]
            review["decision"]["recommendation"] = "accept"
            review_path = self.base / f"{who}-review.json"
            self.write(review_path, review)
            vote_path = self.base / f"{who}-vote.json"
            self.write(vote_path, {"schema": "moso.panel-vote/0.1", "reviewer_id": who, "review_context_id": "review-"+who,
                                  "artifact_sha256": sha256(self.image), "spec_sha256": sha256(self.spec), "seal_sha256": sha256(self.seal),
                                  "review_path": str(review_path), "review_sha256": sha256(review_path),
                                  "spec_received_at": (start+timedelta(minutes=2)).isoformat(), "peer_reviews_hidden": True})
            self.votes.append(vote_path)

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def change_review(self, index, change):
        vote = json.loads(self.votes[index].read_text())
        path = Path(vote["review_path"])
        review = json.loads(path.read_text())
        change(review)
        self.write(path, review)
        vote["review_sha256"] = sha256(path)
        self.write(self.votes[index], vote)

    def test_majority_keeps_dissent_and_never_authorizes_release(self):
        self.change_review(2, lambda r: r["decision"].update(recommendation="local-repair"))
        result = aggregate(self.seal, self.spec, self.votes)
        self.assertEqual(result["recommended_next_action"], "accept")
        self.assertEqual(len(result["dissent"]), 1)
        self.assertFalse(result["release_authorized"])
        self.assertFalse(result["automatic_execution_authorized"])

    def test_one_major_finding_cannot_be_outvoted(self):
        def change(review):
            review["decision"]["recommendation"] = "local-repair"
            review["spec_pass"]["spec_fit"][0].update(severity=2, claim="required text missing", alternative_explanation="possibly outside current crop")
        self.change_review(2, change)
        result = aggregate(self.seal, self.spec, self.votes)
        self.assertEqual(result["majority_recommendation"], "accept")
        self.assertEqual(result["recommended_next_action"], "verify-findings")

    def test_no_majority_does_not_invent_acceptance(self):
        self.change_review(1, lambda r: r["decision"].update(recommendation="local-repair"))
        self.change_review(2, lambda r: r["decision"].update(recommendation="regenerate"))
        result = aggregate(self.seal, self.spec, self.votes)
        self.assertIsNone(result["majority_recommendation"])
        self.assertEqual(result["recommended_next_action"], "user-judgment")

    def test_duplicate_reviewers_and_generating_context_are_rejected(self):
        with self.assertRaises(ValueError):
            seal_observations(self.image, [self.blinds[0]]*3)
        with self.assertRaises(ValueError):
            seal_observations(self.image, self.blinds, "review-A")
        with self.assertRaises(ValueError):
            aggregate(self.seal, self.spec, self.votes[:2]+self.votes[:1])

    def test_changed_artifact_or_blind_commit_is_rejected(self):
        original = self.image.read_bytes()
        Image.new("RGB", (8, 8), "red").save(self.image)
        with self.assertRaisesRegex(ValueError, "artifact changed"):
            aggregate(self.seal, self.spec, self.votes)
        self.image.write_bytes(original)
        self.blinds[0].write_text(self.blinds[0].read_text()+" ")
        with self.assertRaisesRegex(ValueError, "observation was modified"):
            aggregate(self.seal, self.spec, self.votes)

    def test_first_impression_cannot_be_rewritten_after_brief(self):
        self.change_review(0, lambda r: r["blind_pass"].update(first_read="new interpretation"))
        with self.assertRaisesRegex(ValueError, "rewrote"):
            aggregate(self.seal, self.spec, self.votes)

    def test_early_spec_exposure_and_missing_votes_are_rejected(self):
        vote = json.loads(self.votes[0].read_text())
        vote["spec_received_at"] = "2000-01-01T00:00:00+00:00"
        self.write(self.votes[0], vote)
        with self.assertRaisesRegex(ValueError, "before"):
            aggregate(self.seal, self.spec, self.votes)
        with self.assertRaises(ValueError):
            aggregate(self.seal, self.spec, self.votes[:2])

    def test_missing_rubric_category_cannot_cast_a_vote(self):
        self.change_review(0, lambda r: r["spec_pass"].update(carrier=[]))
        with self.assertRaisesRegex(ValueError, "common rubric"):
            aggregate(self.seal, self.spec, self.votes)

    def test_selective_spec_requires_selection_and_keeps_its_dissent(self):
        self.write(self.spec, json.loads((ROOT / "examples/selective-expression-spec.example.json").read_text()))
        for path in self.votes:
            vote = json.loads(path.read_text())
            vote["spec_sha256"] = sha256(self.spec)
            self.write(path, vote)
        with self.assertRaisesRegex(ValueError, "selection findings"):
            aggregate(self.seal, self.spec, self.votes)
        for i in range(3):
            self.change_review(i, lambda r: r["spec_pass"].update(selection=[{
                "severity": 0, "claim": "essential relation survives", "evidence_region": "figure to array gap",
                "consequence": "background omission does not erase the core relation", "confidence": "medium"}]))
        self.assertEqual(aggregate(self.seal, self.spec, self.votes)["recommended_next_action"], "accept")
        self.change_review(2, lambda r: r["spec_pass"]["selection"][0].update(
            severity=2, claim="depth obscures the essential relation", alternative_explanation="possibly intentional scale ambiguity"))
        result = aggregate(self.seal, self.spec, self.votes)
        self.assertEqual(result["recommended_next_action"], "verify-findings")
        self.assertEqual(result["findings_requiring_verification"][0]["category"], "selection")


if __name__ == "__main__":
    unittest.main()
