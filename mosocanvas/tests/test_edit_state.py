from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from commit_edit import commit, stage
from compile_generation_brief import compile_brief, digest
from edit_state import asset_index, asset_path, create_document, load_document, render_document
from prepare_edit import prepare


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def brief() -> dict:
    return {
        "objective": "repair one bounded region",
        "viewer_position": "unchanged",
        "first_read": "accepted image",
        "composition_geometry": "immutable frame",
        "narrative_beat": "unchanged",
        "color_light_logic": "preserve",
        "required_content": ["target"],
        "protected_content": ["outside mask"],
        "main_risk": "whole image reinterpretation",
        "communicated_to_user": True,
    }


class EditStateTests(unittest.TestCase):
    def make_source(self, root: Path, size: tuple[int, int] = (32, 24)) -> Path:
        source = root / "source.png"
        Image.new("RGB", size, (10, 20, 30)).save(source)
        return source

    def make_regions(self, root: Path, box: list[int] | None = None) -> Path:
        regions = root / "regions.json"
        write_json(regions, {"regions": [{"kind": "rectangle", "box": box or [8, 6, 20, 16]}]})
        return regions

    def review_candidate(
        self, root: Path, document_path: Path, plan_path: Path, candidate: Path
    ) -> tuple[Path, Path]:
        operation_id = json.loads(plan_path.read_text())["id"]
        staged = root / f"{operation_id}-staged.png"
        report = root / f"{operation_id}-stage-report.json"
        staged_result = stage(document_path, plan_path, candidate, staged, report)
        review = root / f"{operation_id}-review.json"
        write_json(review, {
            "schema": "moso.attempt-review/0.1",
            "id": f"{operation_id}-review",
            "attempt_id": operation_id,
            "artifact_ref": str(staged),
            "artifact_sha256": staged_result["staged_sha256"],
            "reviewed_at": "2026-09-13T00:00:00Z",
            "actual_artifact_inspected": True,
            "scales": ["full-frame", "detail"],
            "strengths": ["The target region changed."],
            "deviations": [],
            "technical_risks": [],
            "target_change": {"variable": "bounded target", "status": "achieved", "evidence": "Visible in the staged composite."},
            "protected_drift": {"status": "none", "evidence": "The preservation report passed."},
            "priority_improvement": "None before this bounded commit.",
            "recommendation": "accept",
            "communicated_to_user": True,
        })
        return staged, review

    def test_commit_is_replayable_and_preserves_outside_mask(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_source(root)
            document_path = root / "document" / "edit-state.json"
            create_document(source, document_path, "doc")
            plan = prepare(
                document_path,
                self.make_regions(root),
                root / "plan",
                "repair-1",
                "remove repeated texture",
                crop_text="4,2,24,20",
                feather=1,
            )
            candidate = root / "candidate.png"
            Image.new("RGB", (24, 20), (200, 50, 40)).save(candidate)
            plan_path = root / "plan" / "edit-plan.json"
            staged, review = self.review_candidate(root, document_path, plan_path, candidate)
            result = commit(document_path, plan_path, candidate, staged, review)
            self.assertEqual(result["revision"], 2)
            document = load_document(document_path)
            self.assertEqual(len(document["operations"]), 1)
            operation = document["operations"][0]
            self.assertEqual(operation["plan_sha256"], digest((root / "plan" / "edit-plan.json").read_bytes()))
            report = json.loads(Path(operation["preservation_report_ref"]).read_text())
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["outside_mask_changed_pixels"], 0)
            replay = root / "replay.png"
            render_document(document, document_path, replay)
            current = asset_path(document, document_path, document["current_render_asset_ref"])
            with Image.open(current) as left, Image.open(replay) as right:
                self.assertIsNone(
                    ImageChops.difference(left.convert("RGBA"), right.convert("RGBA")).getbbox()
                )
            self.assertEqual(plan["base"]["sha256"], asset_index(json.loads((document_path.parent / "revisions/000001.json").read_text()))[json.loads((document_path.parent / "revisions/000001.json").read_text())["current_render_asset_ref"]]["sha256"])

    def test_stale_plan_cannot_become_the_next_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document_path = root / "document" / "edit-state.json"
            create_document(self.make_source(root), document_path, "doc")
            regions = self.make_regions(root)
            prepare(document_path, regions, root / "plan-a", "repair-a", "first repair")
            prepare(document_path, regions, root / "plan-b", "repair-b", "stale repair")
            candidate = root / "candidate.png"
            Image.new("RGB", (32, 24), (100, 80, 60)).save(candidate)
            plan_a = root / "plan-a/edit-plan.json"
            plan_b = root / "plan-b/edit-plan.json"
            staged_a, review_a = self.review_candidate(root, document_path, plan_a, candidate)
            staged_b, review_b = self.review_candidate(root, document_path, plan_b, candidate)
            commit(document_path, plan_a, candidate, staged_a, review_a)
            with self.assertRaisesRegex(ValueError, "stale edit plan"):
                commit(document_path, plan_b, candidate, staged_b, review_b)

    def test_next_round_conditions_from_clean_anchor_unless_dependency_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document_path = root / "document/edit-state.json"
            create_document(self.make_source(root), document_path, "doc")
            regions = self.make_regions(root)
            prepare(document_path, regions, root / "plan-1", "repair-1", "first repair")
            candidate = root / "candidate.png"
            Image.new("RGB", (32, 24), (200, 50, 40)).save(candidate)
            plan_path = root / "plan-1/edit-plan.json"
            staged, review = self.review_candidate(root, document_path, plan_path, candidate)
            commit(document_path, plan_path, candidate, staged, review)

            clean_plan = prepare(
                document_path, regions, root / "plan-clean", "repair-clean", "clean branch"
            )
            dependent_plan = prepare(
                document_path, regions, root / "plan-dependent", "repair-dependent",
                "continue accepted local change", depends_on=["repair-1"],
            )
            with Image.open(clean_plan["conditioning"]["render_ref"]) as clean:
                self.assertEqual(clean.convert("RGB").getpixel((12, 10)), (10, 20, 30))
            with Image.open(dependent_plan["conditioning"]["render_ref"]) as dependent:
                self.assertEqual(dependent.convert("RGB").getpixel((12, 10)), (200, 50, 40))

    def test_tampered_receipt_invalidates_persistent_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document_path = root / "document/edit-state.json"
            create_document(self.make_source(root), document_path, "doc")
            prepare(document_path, self.make_regions(root), root / "plan", "repair-1", "repair")
            candidate = root / "candidate.png"
            Image.new("RGB", (32, 24), (90, 80, 70)).save(candidate)
            plan_path = root / "plan/edit-plan.json"
            staged, review = self.review_candidate(root, document_path, plan_path, candidate)
            result = commit(document_path, plan_path, candidate, staged, review)
            Path(result["receipt"]).write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "receipt.*changed"):
                load_document(document_path)

    def test_fully_editable_mask_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document_path = root / "document/edit-state.json"
            create_document(self.make_source(root), document_path, "doc")
            with self.assertRaisesRegex(ValueError, "bounded edit"):
                prepare(
                    document_path,
                    self.make_regions(root, [0, 0, 31, 23]),
                    root / "plan",
                    "repair-1",
                    "full image",
                )
            self.assertFalse((root / "plan").exists())

    def test_unreviewed_or_failed_candidate_cannot_be_committed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document_path = root / "document/edit-state.json"
            create_document(self.make_source(root), document_path, "doc")
            plan_path = root / "plan/edit-plan.json"
            prepare(document_path, self.make_regions(root), root / "plan", "repair-1", "repair")
            candidate = root / "candidate.png"
            Image.new("RGB", (32, 24), (90, 80, 70)).save(candidate)
            staged, review = self.review_candidate(root, document_path, plan_path, candidate)
            failed = json.loads(review.read_text())
            failed["target_change"]["status"] = "missed"
            failed["recommendation"] = "branch"
            write_json(review, failed)
            with self.assertRaisesRegex(ValueError, "achieved target change"):
                commit(document_path, plan_path, candidate, staged, review)

    def test_compiler_submits_prepared_input_but_keeps_clean_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document_path = root / "document/edit-state.json"
            document = create_document(self.make_source(root), document_path, "doc")
            edit_plan = prepare(
                document_path,
                self.make_regions(root),
                root / "plan",
                "repair-1",
                "repair target",
            )
            with self.assertRaisesRegex(ValueError, "parent-bound"):
                compile_brief(
                    json.loads((ROOT / "examples/editorial-depth-spec.example.json").read_text()),
                    base=root,
                    edit_plan=edit_plan,
                    edit_plan_base=root / "plan",
                )
            parent = asset_path(document, document_path, document["current_render_asset_ref"])
            value = json.loads((ROOT / "examples/editorial-depth-spec.example.json").read_text())
            value["version"] = 2
            generation = value["generation"]
            generation["medium"] = "preserve accepted material"
            generation["references"] = [{
                "id": "parent", "path": str(parent), "role": "edit-parent",
                "use": "bounded repair parent", "exclude": [],
            }]
            generation["parent"] = {
                "checkpoint_ref": "accepted-v1", "spec_ref": value["id"],
                "spec_version": 1, "sha256": digest(parent.read_bytes()),
            }
            del generation["direction"]
            delta = json.loads((ROOT / "examples/feedback-delta.example.json").read_text())
            delta["parent"].update({key: binding for key, binding in generation["parent"].items() if key != "sha256"})
            result = compile_brief(
                value,
                base=root,
                delta=delta,
                edit_plan=edit_plan,
                edit_plan_base=root / "plan",
            )
            reference = result["reference_inputs"][0]
            self.assertEqual(reference["path"], str(parent))
            self.assertEqual(reference["sha256"], digest(parent.read_bytes()))
            self.assertEqual(reference["submitted_path"], edit_plan["region"]["prepared_input_ref"])
            self.assertEqual(result["tool_arguments"]["referenced_image_paths"], [reference["submitted_path"]])
            self.assertIn("确定性合成", result["prompt"])


class StrictPreflightTests(unittest.TestCase):
    def state(self, root: Path) -> dict:
        source = root / "checkpoint.png"
        Image.new("RGB", (8, 8), "gray").save(source)
        return {
            "schema": "moso.run-state/0.6",
            "task_id": "repair",
            "mode": "repair",
            "phase": "preflight",
            "spec_ref": "spec",
            "approved_checkpoint": {
                "source_ref": str(source), "role": "approved-output",
                "sha256": digest(source.read_bytes()),
            },
            "lineage": {
                "parent_ref": str(source), "operation": "masked-generative",
                "depends_on_parent": True,
            },
            "allowed_changes": ["target"],
            "protected_elements": ["outside mask"],
            "attempt_budget": {"generative": 1, "repair": 1, "generative_used": 0, "repair_used": 0},
            "output_requirements": {"carrier": "image"},
            "verification": [{"check": "target", "method": "review", "status": "pending"}],
            "direction_approval_status": "approved",
            "quality_status": {
                "use_scale": "pending", "detail_scale": "pending", "protected_drift": "pending",
                "trajectory": "pending", "independent_review": "pending", "user_acceptance": "pending",
            },
            "generation_attempts": [{
                "attempt_id": "attempt-1", "status": "planned",
                "trajectory_response": "initial", "trajectory_reason": "first", "pre_generation_brief": brief(),
            }],
        }

    def run_preflight(self, root: Path, state: dict) -> subprocess.CompletedProcess[str]:
        path = root / "run-state.json"
        write_json(path, state)
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/preflight_validate.py"), str(path)],
            text=True, capture_output=True, check=False,
        )

    def test_schema_and_parent_graph_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.state(root)
            state["phase"] = "executing"
            state["generation_attempts"][0]["parent_attempt_id"] = "missing"
            result = self.run_preflight(root, state)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("run state schema at phase", result.stdout)
            self.assertIn("earlier attempt", result.stdout)

    def test_execute_requires_persistent_plan_and_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.state(root)
            state["phase"] = "execute"
            result = self.run_preflight(root, state)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires edit_plan_ref", result.stdout)

    def test_execute_accepts_current_hash_bound_plan_and_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.state(root)
            document_path = root / "document/edit-state.json"
            document = create_document(root / "checkpoint.png", document_path, "doc")
            regions = root / "regions.json"
            write_json(regions, {"regions": [{"kind": "rectangle", "box": [2, 2, 5, 5]}]})
            plan = prepare(
                document_path, regions, root / "plan", "attempt-1", "bounded repair"
            )
            current = asset_path(document, document_path, document["current_render_asset_ref"])
            state["phase"] = "execute"
            state["approved_checkpoint"].update(
                source_ref=str(current), sha256=plan["base"]["sha256"]
            )
            state["lineage"]["parent_ref"] = str(current)
            state["edit_document_ref"] = str(document_path)
            state["generation_attempts"][0]["edit_plan_ref"] = str(root / "plan/edit-plan.json")
            result = self.run_preflight(root, state)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_reviewed_edit_requires_and_accepts_bound_commit_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.state(root)
            document_path = root / "document/edit-state.json"
            create_document(root / "checkpoint.png", document_path, "doc")
            regions = root / "regions.json"
            write_json(regions, {"regions": [{"kind": "rectangle", "box": [2, 2, 5, 5]}]})
            plan_path = root / "plan/edit-plan.json"
            prepare(document_path, regions, root / "plan", "attempt-1", "bounded repair")
            candidate = root / "candidate.png"
            Image.new("RGB", (8, 8), (100, 80, 60)).save(candidate)
            staged = root / "staged.png"
            staged_result = stage(
                document_path, plan_path, candidate, staged, root / "stage-report.json"
            )
            review = root / "review.json"
            write_json(review, {
                "schema": "moso.attempt-review/0.1", "id": "review",
                "attempt_id": "attempt-1", "artifact_ref": str(staged),
                "artifact_sha256": staged_result["staged_sha256"],
                "reviewed_at": "2026-09-13T00:00:00Z", "actual_artifact_inspected": True,
                "scales": ["full-frame", "detail"], "strengths": ["target changed"],
                "deviations": [], "technical_risks": [],
                "target_change": {"variable": "target", "status": "achieved", "evidence": "visible"},
                "protected_drift": {"status": "none", "evidence": "pixel check passed"},
                "priority_improvement": "none", "recommendation": "accept",
                "communicated_to_user": True,
            })
            committed = commit(document_path, plan_path, candidate, staged, review)
            state["phase"] = "execute"
            state["edit_document_ref"] = str(document_path)
            attempt = state["generation_attempts"][0]
            attempt.update({
                "status": "reviewed", "edit_plan_ref": str(plan_path),
                "edit_receipt_ref": committed["receipt"], "attempt_review_ref": str(review),
                "execution": {
                    "backend": "test", "interface": "fixture", "model": "fixture",
                    "model_version": "1", "prompt_ref": "prompt",
                    "prompt_sha256": "a" * 64, "parameters": {},
                    "generated_at": "2026-09-13T00:00:00Z", "output_ref": str(candidate),
                },
            })
            result = self.run_preflight(root, state)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads(Path(committed["receipt"]).read_text())
            receipt["attempt_review"]["sha256"] = "0" * 64
            write_json(Path(committed["receipt"]), receipt)
            result = self.run_preflight(root, state)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("attempt review", result.stdout)

    def test_worsening_quality_forbids_same_method(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.state(root)
            state["quality_status"]["trajectory"] = "worsening"
            state["generation_attempts"][0]["trajectory_response"] = "continue"
            result = self.run_preflight(root, state)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("forbids continuing the same method", result.stdout)


if __name__ == "__main__":
    unittest.main()
