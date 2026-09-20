from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from compile_generation_brief import compile_brief, digest, validate_schema


def spec():
    return json.loads((ROOT / "examples/selective-expression-spec.example.json").read_text())


def shot_plan(mode="flat"):
    plan = json.loads((ROOT / "examples/shot-plan.example.json").read_text())
    plan["schema"] = "moso.shot-plan/0.2"
    plan["spec_ref"] = spec()["id"]
    plan["candidates"] = plan["candidates"][:1]
    shot = plan["candidates"][0]
    for field in ("narrative_verb", "viewer_position", "camera", "depth_layers", "horizon_y_pct"):
        shot.pop(field)
    shot["spatial_mode"] = mode
    return plan


class ExpressionPlanningTests(unittest.TestCase):
    def test_simple_expression_needs_no_hidden_story_or_camera(self):
        value = spec()
        plan = shot_plan()
        result = compile_brief(value, base=ROOT, plan=plan)
        self.assertEqual(result["compilation_mode"], "selective")
        self.assertEqual(result["decision_record"]["spec"], value)
        self.assertEqual(result["decision_record"]["shot_plan"], plan)
        self.assertNotIn("已选构图 camera", result["prompt"])
        self.assertNotIn("暂不揭示", result["prompt"])

    def test_context_and_omission_remain_auditable_but_outside_model_arguments(self):
        value = spec()
        result = compile_brief(value, base=ROOT)
        model_payload = json.dumps(result["tool_arguments"], ensure_ascii=False)
        for item in value["expression_plan"]["concepts"]:
            if item["treatment"] in {"context-only", "omit"}:
                for field in ("concept", "reason", "expected_loss"):
                    self.assertNotIn(item[field], model_payload)
                self.assertIn(item, result["decision_record"]["spec"]["expression_plan"]["concepts"])
        self.assertNotIn(value["task"]["purpose"], model_payload)
        decisions = [r for r in result["coverage"] if r.get("treatment") == "omit"]
        self.assertEqual(decisions[0]["destination"], "decision_record")

    def test_relationship_is_rendered_once_without_abstract_explanation(self):
        value = spec()
        value["expression_plan"]["concepts"].append({
            "id": "distance", "concept": "疏离", "treatment": "relational",
            "relationship_refs": ["isolation-gap"], "reason": "与孤独共用一个视觉关系。"})
        result = compile_brief(value, base=ROOT)
        relation = value["relationships"][0]
        self.assertEqual(result["prompt"].count(relation["relation"]), 1)
        self.assertNotIn(relation["intended_effect"], result["prompt"])
        self.assertIn(relation["pass_condition"], result["prompt"])
        mappings = [r for r in result["coverage"] if r.get("treatment") == "relational" and r["destination"] == "prompt"]
        self.assertEqual(len(mappings), 2)

    def test_hard_constraints_text_and_detail_are_preserved(self):
        value = spec()
        repeated = copy.deepcopy(value["expression_plan"]["concepts"][0])
        repeated["id"] = "same-visible-decision"
        value["expression_plan"]["concepts"].append(repeated)
        value["generation"]["text"].append({"id": "required", "text": "Exact 文案", "method": "generated", "placement": "下方"})
        result = compile_brief(value, base=ROOT)
        for items in value["constraints"].values():
            for item in items:
                self.assertIn(item, result["prompt"])
        # Same-role duplicates share a render instruction; hard obligations retain their label.
        self.assertEqual(result["prompt"].count("可见表达：" + value["constraints"]["must_include"][0]), 1)
        self.assertIn("必须包含：" + value["constraints"]["must_include"][0], result["prompt"])
        self.assertTrue(any(r.get("reuses") for r in result["coverage"]))
        self.assertIn("Exact 文案", result["prompt"])
        self.assertNotIn("在场之外", result["prompt"])
        self.assertEqual(result["overlay_plan"][0]["text"], "在场之外")
        for item in value["expression_plan"]["detail_distribution"]:
            self.assertIn(item["instruction"], result["prompt"])

    def test_deduplication_never_erases_constraint_polarity(self):
        value = spec()
        value["constraints"]["must_avoid"].append(value["constraints"]["must_include"][0])
        result = compile_brief(value, base=ROOT)
        content = value["constraints"]["must_include"][0]
        self.assertIn("必须包含：" + content, result["prompt"])
        self.assertIn("禁止结果：" + content, result["prompt"])
        # Resolving this semantic conflict remains a pre-generation review duty.

    def test_required_visible_content_cannot_be_reclassified(self):
        for treatment in ("context-only", "omit", "relational"):
            value = spec()
            item = value["expression_plan"]["concepts"][0]
            item.pop("render_instruction")
            item["treatment"] = treatment
            if treatment == "relational":
                item["relationship_refs"] = ["isolation-gap"]
            else:
                item["expected_loss"] = "删掉人物"
            with self.subTest(treatment=treatment), self.assertRaises(ValueError):
                compile_brief(value, base=ROOT)

    def test_bound_constraints_cannot_be_omitted_even_without_visible_flag(self):
        value = spec()
        item = value["expression_plan"]["concepts"][1]
        item.pop("relationship_refs")
        item.update(treatment="omit", expected_loss="失去核心关系")
        with self.assertRaises(ValueError):
            compile_brief(value, base=ROOT)

    def test_exact_hard_content_cannot_be_hidden_as_background(self):
        value = spec()
        value["expression_plan"]["concepts"][-1]["concept"] = value["constraints"]["must_include"][0]
        with self.assertRaisesRegex(ValueError, "hard constraint"):
            compile_brief(value, base=ROOT)

    def test_unbound_relationships_constraints_and_duplicate_ids_fail(self):
        changes = [
            lambda s: s["expression_plan"]["concepts"][1].update(relationship_refs=["missing"]),
            lambda s: s["expression_plan"]["concepts"][0].update(constraint_refs=["constraints.must_include[99]"]),
            lambda s: s["expression_plan"]["concepts"].append(copy.deepcopy(s["expression_plan"]["concepts"][0])),
            lambda s: s["relationships"].append(copy.deepcopy(s["relationships"][0])),
        ]
        for change in changes:
            value = spec()
            change(value)
            with self.subTest(change=change), self.assertRaises(ValueError):
                compile_brief(value, base=ROOT)

    def test_omission_needs_loss_and_cannot_smuggle_render_instructions(self):
        for field in ("expected_loss", "render_instruction"):
            value = spec()
            item = value["expression_plan"]["concepts"][-1]
            if field == "expected_loss":
                item.pop(field)
            else:
                item[field] = "画出文明演进史"
            with self.subTest(field=field), self.assertRaises(ValueError):
                compile_brief(value, base=ROOT)

    def test_flat_shot_allows_optional_camera_without_forcing_depth(self):
        plan = shot_plan()
        plan["candidates"][0]["camera"] = {"height": "overhead", "angle": "normal to plane",
            "distance": "full", "lens_behavior": "compressed"}
        self.assertEqual(compile_brief(spec(), base=ROOT, plan=plan)["status"], "compiled")
        plan["candidates"][0]["depth_layers"] = ["near spatial plane", "far spatial plane"]
        with self.assertRaises(ValueError):
            compile_brief(spec(), base=ROOT, plan=plan)

    def test_shallow_shot_can_use_a_single_plane(self):
        value = spec()
        value["expression_plan"]["space"].update(mode="shallow", instruction="压缩前后距离。")
        plan = shot_plan("shallow")
        plan["candidates"][0]["depth_layers"] = ["single working plane"]
        self.assertEqual(compile_brief(value, base=ROOT, plan=plan)["status"], "compiled")

    def test_organized_complexity_and_functional_depth_are_allowed(self):
        value = spec()
        value["constraints"] = {"must_include": [f"必需人物{i}" for i in range(10)], "must_avoid": [], "preserve": []}
        value["expression_plan"]["concepts"] = [{
            "id": str(i), "concept": name, "treatment": "explicit", "required_visible": True,
            "constraint_refs": [f"constraints.must_include[{i}]"], "render_instruction": name,
            "reason": "用户要求所有参与者出现。"} for i, name in enumerate(value["constraints"]["must_include"])]
        value["expression_plan"]["space"] = {"mode": "deep", "instruction": "沿前中后景展示队伍位置。", "reason": "距离表达排序关系。"}
        plan = shot_plan("deep")
        plan["candidates"][0].update(depth_layers=["front group", "middle group", "far group"], spatial_reason="距离表达排序关系。")
        result = compile_brief(value, base=ROOT, plan=plan)
        for name in value["constraints"]["must_include"]:
            self.assertIn(name, result["prompt"])
        self.assertIn("far group", result["prompt"])
        value["expression_plan"]["space"].pop("reason")
        with self.assertRaises(ValueError):
            compile_brief(value, base=ROOT, plan=plan)

    def test_selected_shot_cannot_conflict_with_space_decision(self):
        with self.assertRaisesRegex(ValueError, "spatial_mode"):
            compile_brief(spec(), base=ROOT, plan=shot_plan("shallow"))

    def test_selective_repair_retains_feedback_and_parent_hash_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            parent = base / "parent.png"
            Image.new("RGBA", (10, 10), (10, 20, 30, 40)).save(parent)
            value = spec()
            value["version"] = 2
            value["generation"]["references"] = [{"id": "parent", "path": str(parent),
                "role": "edit-parent", "use": "唯一编辑父图", "exclude": []}]
            binding = {"checkpoint_ref": "accepted-v1", "spec_ref": value["id"],
                       "spec_version": 1, "sha256": digest(parent.read_bytes())}
            value["generation"]["parent"] = binding
            delta = json.loads((ROOT / "examples/feedback-delta.example.json").read_text())
            delta["parent"].update({k: v for k, v in binding.items() if k != "sha256"})
            result = compile_brief(value, base=base, delta=delta)
            for item in delta["changes"]:
                self.assertIn(item["instruction"], result["prompt"])
            for item in delta["preserve"]:
                self.assertIn(item["invariant"], result["prompt"])
            for item in delta["prohibit"]:
                self.assertIn(item["outcome"], result["prompt"])
            self.assertEqual(result["decision_record"]["feedback_delta"], delta)
            self.assertEqual(result["tool_arguments"]["referenced_image_paths"], [str(parent.resolve())])
            Image.new("RGBA", (10, 10), (11, 20, 30, 40)).save(parent)
            with self.assertRaisesRegex(ValueError, "hash"):
                compile_brief(value, base=base, delta=delta)

    def test_new_decisions_require_explicit_version_upgrade(self):
        value = json.loads((ROOT / "examples/editorial-depth-spec.example.json").read_text())
        self.assertEqual(compile_brief(value, base=ROOT)["compilation_mode"], "legacy")
        value["expression_plan"] = spec()["expression_plan"]
        with self.assertRaises(ValueError):
            compile_brief(value, base=ROOT)
        legacy_plan = shot_plan()
        legacy_plan["schema"] = "moso.shot-plan/0.1"
        with self.assertRaises(ValueError):
            validate_schema(legacy_plan, "shot-plan.schema.json")


if __name__ == "__main__":
    unittest.main()
