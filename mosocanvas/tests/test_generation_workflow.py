from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from compile_generation_brief import compile_brief, digest


def spec() -> dict:
    return json.loads((ROOT / "examples/editorial-depth-spec.example.json").read_text())


class GenerationWorkflowTests(unittest.TestCase):
    def test_native_arguments_preserve_intent_and_separate_overlay(self):
        value = spec()
        value["generation"]["requested_parameters"] = {"quality": "high", "seed": 5, "model": "requested-model"}
        result = compile_brief(value, base=ROOT)
        self.assertEqual(set(result["tool_arguments"]), {"prompt"})
        self.assertEqual(result["parameters"]["applied"], {})
        self.assertIsNone(result["observed_backend"]["model"])
        self.assertFalse(result["execution_performed"])
        self.assertNotIn("离席之后", result["prompt"])
        self.assertEqual(result["overlay_plan"][0]["text"], "离席之后")
        for section in ("must_include", "preserve", "must_avoid"):
            for invariant in value["constraints"][section]:
                self.assertIn(invariant, result["prompt"])
        self.assertIn(value["strategy"]["familiar_rule"], result["prompt"])
        self.assertEqual(result["prompt_sha256"], digest(result["prompt"].encode()))

    def test_explicit_decisions_override_pack_defaults(self):
        value = spec()
        result = compile_brief(value, base=ROOT)
        self.assertEqual(result["direction"]["applied_defaults"], ["medium"])
        self.assertIn(value["generation"]["composition"], result["prompt"])
        self.assertIn(value["generation"]["color_light"], result["prompt"])

    def test_unknown_direction_or_unresolved_contract_is_blocked(self):
        for mutation in (lambda s: s["generation"]["direction"].update(id="../external"),
                         lambda s: s["generation"]["direction"].update(variant="missing"),
                         lambda s: s["uncertainty"].update(unresolved=["parent unknown"])):
            value = spec()
            mutation(value)
            with self.assertRaises(ValueError):
                compile_brief(value, base=ROOT)

    def test_references_are_ordered_local_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            Image.new("RGB", (10, 10), "red").save(base / "one.png")
            Image.new("RGB", (10, 10), "blue").save(base / "two.png")
            value = spec()
            value["generation"]["references"] = [
                {"id": name, "path": name + ".png", "role": "layout", "use": "只取位置", "exclude": ["不采用文字"]}
                for name in ("two", "one")]
            result = compile_brief(value, base=base)
            self.assertEqual(result["tool_arguments"]["referenced_image_paths"], [str((base / "two.png").resolve()), str((base / "one.png").resolve())])
            self.assertEqual(result["reference_inputs"][0]["sha256"], digest((base / "two.png").read_bytes()))
            value["generation"]["references"].append(copy.deepcopy(value["generation"]["references"][0]))
            with self.assertRaises(ValueError):
                compile_brief(value, base=base)

    def test_exact_generated_text_survives_compilation(self):
        value = spec()
        text = '“再见，明天。” / See you at 8:00'
        value["generation"]["text"][0].update(text=text, method="generated")
        result = compile_brief(value, base=ROOT)
        self.assertIn(json.dumps(text, ensure_ascii=False), result["prompt"])
        self.assertEqual(result["overlay_plan"], [])

    def test_declared_shot_plan_is_required_and_bound(self):
        value = spec()
        value["shot_plan_ref"] = "plan.json"
        with self.assertRaises(ValueError):
            compile_brief(value, base=ROOT)
        plan = json.loads((ROOT / "examples/shot-plan.example.json").read_text())
        with self.assertRaises(ValueError):
            compile_brief(value, base=ROOT, plan=plan)
        plan["spec_ref"] = value["id"]
        result = compile_brief(value, base=ROOT, plan=plan)
        self.assertIn(plan["candidates"][0]["vectors"][0], result["prompt"])

    def test_repair_binds_parent_and_rejects_new_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            parent = base / "parent.png"
            Image.new("RGBA", (10, 10), (10, 20, 30, 40)).save(parent)
            value = spec()
            value["version"] = 2
            g = value["generation"]
            g["medium"] = "保留父图材质"
            g["references"] = [{"id": "parent", "path": str(parent), "role": "edit-parent", "use": "本轮编辑父图", "exclude": []}]
            g["parent"] = {"checkpoint_ref": "accepted-v1", "spec_ref": value["id"], "spec_version": 1, "sha256": digest(parent.read_bytes())}
            delta = json.loads((ROOT / "examples/feedback-delta.example.json").read_text())
            delta["parent"].update({k: v for k, v in g["parent"].items() if k != "sha256"})
            with self.assertRaises(ValueError):
                compile_brief(value, base=base, delta=delta)
            del g["direction"]
            result = compile_brief(value, base=base, delta=delta)
            self.assertIn(delta["changes"][0]["instruction"], result["prompt"])
            self.assertIn(delta["preserve"][0]["invariant"], result["prompt"])
            Image.new("RGBA", (10, 10), (11, 20, 30, 40)).save(parent)
            with self.assertRaises(ValueError):
                compile_brief(value, base=base, delta=delta)

    def test_series_not_silently_compiled_as_one_frame(self):
        value = json.loads((ROOT / "examples/visual-spec.example.json").read_text())
        value["generation"] = spec()["generation"]
        with self.assertRaisesRegex(ValueError, "one frame"):
            compile_brief(value, base=ROOT)

    def test_unknown_model_requires_observation_limits(self):
        schema = json.loads((ROOT / "schemas/run-state.schema.json").read_text())
        execution_schema = schema["properties"]["generation_attempts"]["items"]["properties"]["execution"]
        value = {"backend": "OpenAI", "interface": "native", "model": None, "model_version": None,
                 "prompt_ref": "p", "prompt_sha256": "a" * 64, "parameters": {}, "generated_at": "2026-09-10T00:00:00Z", "output_ref": "o"}
        validator = Draft202012Validator(execution_schema)
        self.assertTrue(list(validator.iter_errors(value)))
        value["observation_limits"] = ["Native tool does not expose model metadata"]
        self.assertFalse(list(validator.iter_errors(value)))

    def test_cli_writes_reviewable_artifact_without_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "request.json"
            result = subprocess.run([sys.executable, str(ROOT / "scripts/compile_generation_brief.py"), "--spec",
                                     str(ROOT / "examples/editorial-depth-spec.example.json"), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(output.read_text())["execution_performed"])


if __name__ == "__main__":
    unittest.main()
