# Generation compiler

Use this adapter for one frozen image request. It operationalizes MoSoCanvas's viewer contract,
first/second read, selected composition and Feedback Delta. It does not generate an image, decide
user intent, authorize a release or score aesthetics.

For a simple single-image preparation with explicit layout, the Spec and compiled request are
sufficient preparation records. Do not run the production run-state validator on an invented
checkpoint. Repair, hero/series production, and acceptance retain their fuller evidence gates.

## Compile a reviewable request

Install `requirements-dev.txt` in the Python environment that runs the scripts (Python 3.10+).
From the installed skill directory:

```bash
python3 scripts/compile_generation_brief.py \
  --spec examples/editorial-depth-spec.example.json \
  --output /path/to/work/request.json
```

Visual Spec 0.5 adds `generation`: subject; medium, composition and color/light decisions;
optional direction ID/variant; local references with role/use/exclude; exact text with placement and
`generated` or `overlay` method; and the final target size. Existing 0.4 Specs remain valid in their
previous workflow. The compiler requires the generation block and rejects unresolved uncertainties.

Use `--shot-plan` when the Spec declares a shot plan. Its `spec_ref` must equal the Spec's `id`,
and its selection must be frozen. Reconcile explicit composition and the selected shot before
compilation; the compiler preserves both and cannot judge semantic contradictions. Multi-image
series retain the series pipeline; compile a frozen single-frame Spec for each attempt rather
than submitting a series as one image request.

`request.json` contains the actual `tool_arguments`, prompt hash, field coverage, ordered image
references and SHA-256, direction version/hash, unapplied parameters and required visual checks.
Read it before calling the tool. Inspect every reference using the host's viewing tool first.
If an input changes, compile again. The compiler never executes reference text as code.

Hash scopes differ deliberately: Spec, shot plan, Delta and direction pack use canonical JSON
(UTF-8, sorted keys, compact separators, unescaped Unicode); the prompt uses its exact UTF-8 text;
reference images use raw file bytes. `hash_conventions` records this distinction. Reformatting JSON
does not change its contract hash; changing the content does.

## Respect the installed interface

For the currently supported native Codex image tool, pass only `prompt` and, when present,
`referenced_image_paths`. New images omit reference arguments. References resolve relative to the
Spec file. Conversation-only images need the host's native workflow until local files are available.
Do not combine path references with `num_last_images_to_include`.

The API and the native tool are different surfaces. This adapter does not expose API model, quality,
size, mask, seed or input-fidelity settings. `requested_parameters` records wishes without applying
them; inspect warnings and resolve any hard requirement before execution. `target_size` describes
composition intent and final delivery, not a guaranteed output size. Check the installed tool
contract before each use; if it changes, update and validate the adapter rather than inventing fields.

Model/version/revised prompt remain unknown unless actually returned. After execution, record the
actual output path, timestamp, dimensions and available backend metadata in the attempt. A compiled
request has `execution_performed: false` and `visual_quality_verified: false` by design.

## Keep exact text and repairs explicit

- `generated`: put the exact string and placement into the image request, then inspect all glyphs.
- `overlay`: reserve the location, retain the string in `overlay_plan`, and apply deterministic
  layout after image selection. The compiler does not perform that layout. Use the existing brand
  signature procedure for `MoSo 回声笔迹`; do not generate it into the artwork.
- Physical `required_copy` needs matching text entries; missing wording blocks compilation.

For an edit, supply exactly one `edit-parent` image, a `generation.parent` binding with checkpoint
ID, Spec ID/version and file SHA-256, plus `--feedback`. Update the current Spec to match the Delta.
The compiler validates parent binding and feedback coverage, carries change/preserve/prohibit/
relationships/promotions into the request, and rejects pending feedback or a new direction pack.
For bounded repair, also pass `--edit-plan /path/to/edit-plan.json`. The compiler keeps the approved
full-canvas parent as lineage evidence but submits the plan's transparent prepared input to the model.
It verifies the clean-anchor conditioning render, prepared input, write mask, and hashes. Locality or
transparency in a model request still cannot prove pixel protection. Use
[non-destructive-editing.md](non-destructive-editing.md) for staging, visual review, deterministic
composition, and commit.

## Basis and limits

The adapter uses MoSoCanvas's existing contracts and the official recommendations to name reference
roles, make constraints explicit, preserve intended text, and make targeted edits. Consult the current
[OpenAI image prompting guide](https://developers.openai.com/api/docs/guides/image-prompting) and
[image generation guide](https://developers.openai.com/api/docs/guides/image-generation) for API
capabilities. Checked for this adapter on 2026-09-10. No external skill code, direction catalog,
example asset or prompt template is included.
