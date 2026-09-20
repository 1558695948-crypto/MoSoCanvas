#!/usr/bin/env python3
"""Compile a frozen Visual Spec into a reviewable native-tool request, without generating images."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from PIL import Image

from feedback_validate import validate as validate_delta
from image_contract import read_coverage_mask, read_raster, reject_input_overwrite, sha256

ROOT = Path(__file__).resolve().parents[1]
HOSTS = {"native-codex", "prompt-only"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value: Any) -> str:
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def validate_schema(value: dict, name: str) -> None:
    schema = load_json(ROOT / "schemas" / name)
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        error = errors[0]
        raise ValueError(f"{name} at {'.'.join(map(str, error.path)) or '<root>'}: {error.message}")


def load_direction(direction: dict) -> tuple[dict, dict]:
    # IDs name bundled data, never arbitrary paths supplied by a prompt.
    available = {path.stem: path for path in (ROOT / "directions").glob("*.json")}
    if direction["id"] not in available:
        raise ValueError(f"unknown direction pack: {direction['id']}")
    pack = load_json(available[direction["id"]])
    validate_schema(pack, "direction-pack.schema.json")
    variants = {v["id"]: v for v in pack["variants"]}
    if len(variants) != len(pack["variants"]):
        raise ValueError("direction pack contains duplicate variant IDs")
    if direction["variant"] not in variants:
        raise ValueError(f"unknown direction variant: {direction['variant']}")
    return pack, variants[direction["variant"]]


def selected_shot(plan: dict, spec: dict) -> dict:
    validate_schema(plan, "shot-plan.schema.json")
    if plan["spec_ref"] != spec["id"]:
        raise ValueError("shot plan must bind to this Visual Spec ID")
    selection = plan["selection"]
    shots = {shot["shot_id"]: shot for shot in plan["candidates"]}
    if len(shots) != len(plan["candidates"]) or selection.get("status") != "selected" or selection.get("selected_shot_id") not in shots:
        raise ValueError("shot plan requires a unique, selected shot")
    return shots[selection["selected_shot_id"]]


def resolve_file(ref: str, base: Path) -> Path:
    path = Path(ref).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def validate_expression_plan(spec: dict, shot: dict | None) -> None:
    """Check declared bindings, never infer semantic equivalence or permission to omit."""
    expression = spec["expression_plan"]
    concepts = expression["concepts"]
    if len({item["id"] for item in concepts}) != len(concepts):
        raise ValueError("expression concept IDs must be unique")
    relationships = spec.get("relationships", [])
    relationship_ids = {item["id"] for item in relationships}
    if len(relationship_ids) != len(relationships):
        raise ValueError("relationship IDs must be unique")
    hard_content = set(spec["constraints"]["must_include"] + spec["constraints"]["preserve"])
    for item in concepts:
        if item["treatment"] in {"context-only", "omit"} and item["concept"] in hard_content:
            raise ValueError("a hard constraint cannot be routed to context-only or omit")
        for ref in item.get("relationship_refs", []):
            if ref not in relationship_ids:
                raise ValueError(f"unknown expression relationship: {ref}")
        for ref in item.get("constraint_refs", []):
            field, index = ref.removeprefix("constraints.").rstrip("]").split("[")
            if int(index) >= len(spec["constraints"][field]):
                raise ValueError(f"unknown expression constraint: {ref}")
    if shot and shot.get("spatial_mode") != expression["space"]["mode"]:
        raise ValueError("selected shot spatial_mode must match expression_plan.space.mode; use Shot Plan 0.2")


def compile_brief(
    spec: dict,
    *,
    base: Path,
    host: str = "native-codex",
    plan: dict | None = None,
    delta: dict | None = None,
    edit_plan: dict | None = None,
    edit_plan_base: Path | None = None,
) -> dict:
    if host not in HOSTS:
        raise ValueError(f"unsupported host: {host}")
    validate_schema(spec, "visual-spec.schema.json")
    g = spec.get("generation")
    if not g:
        raise ValueError("compilation needs a generation block; existing 0.4 specs remain valid for their original workflow")
    if (spec.get("uncertainty") or {}).get("unresolved"):
        raise ValueError("resolve material Visual Spec uncertainties before compiling a generation request")
    if spec["task"]["domain"] == "social-image-series":
        raise ValueError("compile one frame spec at a time; retain the series plan in the existing series workflow")
    if spec.get("shot_plan_ref") and plan is None:
        raise ValueError("this spec declares a shot plan; supply --shot-plan so its decisions are not omitted")
    warnings: list[str] = []
    coverage: list[dict] = []
    blocks: list[str] = []
    overlay: list[dict] = []
    selective = spec["schema"] == "moso.visual-spec/0.6"
    emitted: dict[tuple[str, str], str] = {}

    def add(label: str, value: str, source: str) -> None:
        key = (label, value)  # Identical nouns under include/avoid have different obligations.
        if selective and key in emitted:
            coverage.append({"source": source, "destination": "prompt", "value": value,
                             "reuses": emitted[key]})
            return
        blocks.append(f"{label}：{value}")
        emitted[key] = source
        coverage.append({"source": source, "destination": "prompt", "value": value})

    shot = selected_shot(plan, spec) if plan else None
    if selective:
        validate_expression_plan(spec, shot)
    pack = variant = None
    if "direction" in g:
        if g.get("parent") or delta:
            raise ValueError("bounded repair cannot introduce a direction pack; carry accepted rendering decisions explicitly")
        pack, variant = load_direction(g["direction"])
    resolved: dict[str, str] = {}
    resolved_sources: dict[str, str] = {}
    defaults: list[str] = []
    for field in ("medium", "composition", "color_light"):
        if g.get(field):
            resolved[field] = g[field]
            resolved_sources[field] = f"generation.{field}"
        elif variant:
            resolved[field] = variant[field]
            resolved_sources[field] = f"direction.{field}"
            defaults.append(field)
        elif field == "composition" and shot:
            resolved[field] = shot["masses"]["dominant"]
            resolved_sources[field] = "shot.masses.dominant"
        elif field == "color_light" and shot:
            resolved[field] = shot["value_plan"]["contrast_locus"]
            resolved_sources[field] = "shot.value_plan.contrast_locus"
        else:
            raise ValueError(f"generation.{field} needs an explicit decision or a selected direction default")

    if selective:
        for field in ("task", "proposition", "viewer_contract", "strategy"):
            coverage.append({"source": field, "destination": "decision_record", "value": spec[field]})
        add("用途", spec["task"]["domain"], "task.domain")
    else:
        add("用途", spec["task"]["purpose"] + "；" + spec["task"]["output_context"], "task")
        if spec["task"].get("audience"):
            add("观众", spec["task"]["audience"], "task.audience")
        for field, value in spec["proposition"].items():
            add("画面命题 " + field, value, "proposition." + field)
    add("主体", g["subject"], "generation.subject")
    add("媒介", resolved["medium"], resolved_sources["medium"])
    if not selective:
        viewer = spec["viewer_contract"]
        add("观看关系", f"{viewer['position']}；{viewer['information_power']}", "viewer_contract")
        add("第一读", viewer["first_read"], "viewer_contract.first_read")
        add("第二读", viewer["second_read"], "viewer_contract.second_read")
        add("暂不揭示", viewer["withheld"], "viewer_contract.withheld")
    add("画面组织", resolved["composition"], resolved_sources["composition"])
    add("色彩与照明", resolved["color_light"], resolved_sources["color_light"])
    for field, value in spec["hierarchy"].items():
        add("视觉层级 " + field, "；".join(value) if isinstance(value, list) else value, "hierarchy." + field)
    if selective:
        expression = spec["expression_plan"]
        for i, item in enumerate(expression["concepts"]):
            source = f"expression_plan.concepts[{i}]"
            coverage.append({"source": source, "destination": "decision_record",
                             "treatment": item["treatment"], "value": item})
            if item["treatment"] == "explicit":
                add("可见表达", item["render_instruction"], source + ".render_instruction")
            elif item["treatment"] == "relational":
                coverage.append({"source": source, "destination": "prompt",
                                 "treatment": "relational", "relationship_refs": item["relationship_refs"]})
        add("空间方式", expression["space"]["mode"], "expression_plan.space.mode")
        add("空间组织", expression["space"]["instruction"], "expression_plan.space.instruction")
        if "reason" in expression["space"]:
            coverage.append({"source": "expression_plan.space.reason", "destination": "decision_record",
                             "value": expression["space"]["reason"]})
        for i, item in enumerate(expression.get("detail_distribution", [])):
            add("细节分布", f"{item['region']}：{item['instruction']}", f"expression_plan.detail_distribution[{i}]")
    else:
        for field in ("selected_direction", "structural_mechanisms", "familiar_rule", "designed_anomaly"):
            value = spec["strategy"][field]
            add("结构意图 " + field, "；".join(value) if isinstance(value, list) else value, "strategy." + field)
    if shot:
        for name in ("camera", "masses", "value_plan"):
            if name in shot:
                add(f"已选构图 {name}", json.dumps(shot[name], ensure_ascii=False), f"shot.{name}")
        for name in ("vectors", "depth_layers", "safe_zones"):
            if shot.get(name):
                add(f"已选构图 {name}", "；".join(shot[name]), f"shot.{name}")
        for name in ("first_fixation", "horizon_y_pct"):
            if name in shot:
                add(f"已选构图 {name}", json.dumps(shot[name], ensure_ascii=False), f"shot.{name}")
    for i, relationship in enumerate(spec.get("relationships", [])):
        add("元素关系", f"{relationship['subject']} / {relationship['relation']} / {relationship['object']}。{relationship['pass_condition']}", f"relationships[{i}]")
    for i, reveal in enumerate(spec.get("perceptual_reveals", [])):
        add("显现层次", f"{reveal['element']}：首次可见 {reveal['first_detectable_at']}；不得主导 {reveal['must_not_dominate_at']}；{reveal['pass_condition']}", f"perceptual_reveals[{i}]")

    refs: list[dict] = []
    ref_ids: set[str] = set()
    ref_paths: set[str] = set()
    for i, ref in enumerate(g.get("references", []), 1):
        path = resolve_file(ref["path"], base)
        if ref["id"] in ref_ids or str(path) in ref_paths:
            raise ValueError("reference IDs and file paths must be unique; combine the intended uses of one image")
        ref_ids.add(ref["id"])
        ref_paths.add(str(path))
        if not path.is_file():
            raise ValueError(f"reference is not a local image file: {path}; resolve conversation images to local files or use the host workflow directly")
        with Image.open(path) as im:
            im.verify()
        record = dict(ref, index=i, path=str(path), sha256=digest(path.read_bytes()))
        refs.append(record)
        add(f"参考图 {i} ({ref['role']})", ref["use"] + ("；不采用：" + "；".join(ref["exclude"]) if ref["exclude"] else ""), f"generation.references[{i-1}]")

    texts = g.get("text", [])
    if len({t["id"] for t in texts}) != len(texts):
        raise ValueError("text IDs must be unique")
    supplied = {t["text"] for t in texts}
    required_copy = set((spec.get("physical_output") or {}).get("required_copy", []))
    if required_copy - supplied:
        raise ValueError("every physical required_copy item needs a generation.text entry with exact wording and placement")
    for i, text in enumerate(texts):
        if text["method"] == "generated":
            add("准确文字", f"在{text['placement']}仅写 {json.dumps(text['text'], ensure_ascii=False)}，保持原文语言、字形顺序和标点。", f"generation.text[{i}]")
        else:
            overlay.append(text)
            add("排版预留", f"在{text['placement']}保留后续排版空间，此处不要生成文字。", f"generation.text[{i}].placement")
            coverage.append({"source": f"generation.text[{i}].text", "destination": "overlay_plan", "value": text["text"]})
    add("文字范围", "只生成上面明确交给图像模型的文字，不添加其他文案或伪造标识。", "compiler.text_boundary")
    for field, label in (("must_include", "必须包含"), ("preserve", "必须保留"), ("must_avoid", "禁止结果")):
        for i, value in enumerate(spec["constraints"][field]):
            add(label, value, f"constraints.{field}[{i}]")

    parents = [ref for ref in refs if ref["role"] == "edit-parent"]
    if edit_plan is not None and not (parents or g.get("parent") or delta):
        raise ValueError("an edit plan can only be used with a parent-bound Feedback Delta edit")
    if parents or g.get("parent") or delta:
        if len(parents) != 1 or not g.get("parent") or not delta:
            raise ValueError("editing requires exactly one edit-parent reference, a generation.parent binding, and a Feedback Delta")
        parent = g["parent"]
        if parents[0]["sha256"] != parent["sha256"]:
            raise ValueError("edit parent bytes do not match the approved checkpoint hash")
        validate_schema(delta, "feedback-delta.schema.json")
        blockers, delta_warnings = validate_delta(delta)
        if blockers or delta["confirmation_status"] == "pending":
            raise ValueError("Feedback Delta is not executable: " + "; ".join(blockers or ["confirmation pending"]))
        warnings.extend(delta_warnings)
        for key in ("checkpoint_ref", "spec_ref", "spec_version"):
            if parent[key] != delta["parent"].get(key):
                raise ValueError(f"Feedback Delta parent {key} does not match the approved binding")
        if parent["spec_ref"] != spec["id"] or parent["spec_version"] > spec["version"]:
            raise ValueError("parent spec binding does not match this spec lineage")
        add("编辑父图", f"参考图 {parents[0]['index']} 是本轮唯一编辑父图。仅执行下列改动，其他内容按保护约束保留。", "generation.parent")
        for i, change in enumerate(delta["changes"]):
            add("本轮修改", change["target"] + "：" + change["instruction"], f"delta.changes[{i}]")
        for i, item in enumerate(delta["preserve"]):
            add("本轮保护", item["target"] + "：" + item["invariant"], f"delta.preserve[{i}]")
        for i, item in enumerate(delta["prohibit"]):
            add("本轮禁止", item["outcome"], f"delta.prohibit[{i}]")
        for i, item in enumerate(delta["relationships"]):
            add("本轮关系", f"{item['subject']} / {item['relation']} / {item['object']}。{item['pass_condition']}", f"delta.relationships[{i}]")
        for i, item in enumerate(delta["promotions"]):
            add("已接受的新特征", f"{item['unexpected_feature']}；作用：{item['new_role']}；保留：{item['preserve_as']}", f"delta.promotions[{i}]")
        if edit_plan is None:
            warnings.append("Legacy whole-parent edit: prepare a bounded edit plan before execute when exact preservation or multi-turn repair is required.")
        else:
            validate_schema(edit_plan, "edit-plan.schema.json")
            plan_base = edit_plan_base or base
            binding = edit_plan["base"]
            bound_base = resolve_file(binding["path"], plan_base)
            if bound_base != Path(parents[0]["path"]).resolve():
                raise ValueError("edit plan base path does not match the approved edit-parent reference")
            if binding["sha256"] != parents[0]["sha256"] or sha256(bound_base) != binding["sha256"]:
                raise ValueError("edit plan base bytes do not match the approved edit-parent hash")
            region = edit_plan["region"]
            conditioning = edit_plan["conditioning"]
            conditioning_render = resolve_file(conditioning["render_ref"], plan_base)
            if not conditioning_render.is_file() or sha256(conditioning_render) != conditioning["render_sha256"]:
                raise ValueError("edit plan conditioning render is missing or changed")
            if conditioning["included_operation_ids"] != edit_plan["depends_on"]:
                raise ValueError("edit plan conditioning operations do not match depends_on")
            prepared = resolve_file(region["prepared_input_ref"], plan_base)
            mask = resolve_file(region["write_mask_ref"], plan_base)
            if not prepared.is_file() or sha256(prepared) != region["prepared_input_sha256"]:
                raise ValueError("edit plan prepared input is missing or changed")
            if not mask.is_file() or sha256(mask) != region["write_mask_sha256"]:
                raise ValueError("edit plan write mask is missing or changed")
            prepared_image, _ = read_raster(prepared)
            coverage_mask = read_coverage_mask(mask)
            if list(prepared_image.size) != region["prepared_input_size"] or prepared_image.size != coverage_mask.size:
                raise ValueError("edit plan prepared input and write mask dimensions do not match")
            mask_minimum, mask_maximum = coverage_mask.getextrema()
            if mask_minimum != 0 or mask_maximum == 0:
                raise ValueError("edit plan mask must include both editable and protected pixels")
            parents[0]["submitted_path"] = str(prepared)
            parents[0]["submitted_sha256"] = region["prepared_input_sha256"]
            add(
                "局部编辑范围",
                f"只修改局部输入中的白色遮罩对应区域；画布坐标 {region['read_box_xywh']}。返回与局部输入相同尺寸的完整候选图。",
                "edit_plan.region",
            )
            add(
                "像素提交规则",
                "模型输出只是候选补丁；必须经 write mask 确定性合成并通过遮罩外像素校验，才可成为下一轮已提交画布。",
                "edit_plan.operation",
            )
            warnings.append("The model has no native mask argument here. The transparent prepared input is guidance; exact preservation is enforced only during deterministic commit.")

    size = g.get("target_size")
    if size:
        add("目标载体", f"最终交付 {size['width']}×{size['height']} px；构图按此宽高关系规划，实际返回尺寸须检查。", "generation.target_size")
    requested = g.get("requested_parameters", {})
    if requested:
        warnings.append("This native interface exposes no model/quality/size/mask/seed request parameters; requested values are recorded but not applied.")
    prompt = "\n\n".join(blocks)
    args: dict[str, Any] = {"prompt": prompt}
    if refs:
        args["referenced_image_paths"] = [ref.get("submitted_path", ref["path"]) for ref in refs]
    checks = list(spec["evaluation"]["observable_pass_conditions"])
    if variant:
        checks.extend(variant["verification"])
    if delta:
        checks.extend(item["pass_condition"] for item in delta["verification"])
    return {
        "schema": "moso.compiled-brief/0.3", "spec_id": spec["id"], "spec_version": spec["version"],
        "compilation_mode": "selective" if selective else "legacy",
        "decision_record": {"spec": copy.deepcopy(spec), "shot_plan": copy.deepcopy(plan),
                            "feedback_delta": copy.deepcopy(delta)},
        "hash_conventions": {"structured_inputs_and_direction": "SHA-256 of UTF-8 JSON with sorted keys, compact separators and unescaped Unicode",
                             "prompt": "SHA-256 of exact UTF-8 prompt text", "reference_images": "SHA-256 of file bytes"},
        "input_hashes": {"spec": canonical_digest(spec), "shot_plan": canonical_digest(plan) if plan else None, "feedback_delta": canonical_digest(delta) if delta else None,
                         "edit_plan": canonical_digest(edit_plan) if edit_plan else None},
        "host": host, "tool": "image_gen.imagegen" if host == "native-codex" else None,
        "tool_arguments": args if host == "native-codex" else None,
        "prompt": prompt, "prompt_sha256": digest(prompt.encode()),
        "reference_inputs": refs, "overlay_plan": overlay, "coverage": coverage,
        "edit_plan": None if edit_plan is None else {
            "id": edit_plan["id"], "document_id": edit_plan["document_id"],
            "expected_revision": edit_plan["expected_revision"],
            "operation": edit_plan["operation"], "conditioning": edit_plan["conditioning"],
            "region": edit_plan["region"],
        },
        "direction": None if pack is None else {"id": pack["id"], "version": pack["version"], "sha256": canonical_digest(pack), "variant": variant["id"], "applied_defaults": defaults},
        "parameters": {"requested": requested, "applied": {}, "unavailable": sorted(requested)},
        "dimensions": {"target": size, "requested": None, "returned": None, "exported": None},
        "observed_backend": {"model": None, "model_version": None, "revised_prompt": None,
                             "limits": ["These values are not exposed by the current native tool contract."]},
        "verification_required": list(dict.fromkeys(checks)), "warnings": warnings,
        "known_failure_signs": spec["evaluation"]["known_failure_signs"],
        "user_judgment_required": spec["evaluation"]["user_judgment_required"],
        "status": "compiled", "execution_performed": False, "visual_quality_verified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--shot-plan", type=Path)
    parser.add_argument("--feedback", type=Path)
    parser.add_argument("--edit-plan", type=Path)
    parser.add_argument("--host", choices=sorted(HOSTS), default="native-codex")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        inputs = [path for path in (args.spec, args.shot_plan, args.feedback, args.edit_plan) if path]
        reject_input_overwrite(args.output, inputs)
        result = compile_brief(load_json(args.spec), base=args.spec.resolve().parent, host=args.host,
                               plan=load_json(args.shot_plan) if args.shot_plan else None,
                               delta=load_json(args.feedback) if args.feedback else None,
                               edit_plan=load_json(args.edit_plan) if args.edit_plan else None,
                               edit_plan_base=args.edit_plan.resolve().parent if args.edit_plan else None)
        reference_files = [Path(r["path"]) for r in result["reference_inputs"]]
        reference_files.extend(
            Path(r["submitted_path"])
            for r in result["reference_inputs"]
            if r.get("submitted_path")
        )
        reject_input_overwrite(args.output, reference_files)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"output": str(args.output.resolve()), "prompt_sha256": result["prompt_sha256"],
                      "status": result["status"], "warnings": result["warnings"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
