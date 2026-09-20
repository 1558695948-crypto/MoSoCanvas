# MoSoCanvas

Evidence-based visual direction for campaign images, posters, social key visuals, and physical promotional collateral.

MoSoCanvas turns vague visual requests and reference images into a controlled production workflow:

- deconstruct references into transferable visual mechanisms;
- freeze a measurable Visual Spec before production;
- select deterministic, masked, or full-frame generation methods according to risk;
- preserve approved decisions across iterative repairs;
- bind Codex Image Canvas comments and multi-select feedback to explicit parent versions;
- distinguish semantic regions from real masks before promising bounded edits;
- compile every material correction into change, preserve, prohibit, relationship, and verification constraints;
- verify real outputs at use scale and detail scale;
- detect ineffective retries and record lineage, drift, risks, and acceptance decisions.

## What is included

- `mosocanvas/SKILL.md` — the main visual-direction workflow;
- `mosocanvas/references/` — critique, reference analysis, repair, social, print, and texture protocols;
- `mosocanvas/schemas/` — machine-readable schemas for specs, run state, critique, and reference analysis;
- `mosocanvas/scripts/` — deterministic inspection, masking, compositing, and preservation helpers;
- `mosocanvas/examples/` — example specs and calibrated cases;
- `mosocanvas/evals/` — clean-context regression evaluations;
- `mosocanvas/directions/` — original, optional viewer-relation direction packs;
- `dist/` — packaged releases and integrity manifests.

## Design principle

MoSoCanvas does not try to replace taste with a universal score. It makes visual decisions explicit, testable, reversible, and easier to preserve through production.

## Status

Current release: `1.7.0`.

New work uses Visual Spec 0.6 to choose which concepts are
explicit, expressed through relationships, background context, or intentionally omitted. Narrative
devices are optional, and Shot Plan 0.2 supports flat, shallow, deep and mixed space. The compiler
keeps a complete decision record separate from the executable prompt while preserving hard content,
text and repair obligations. Reviews check meaning retained and omission tradeoffs, including dense
and deep work. Existing 0.4/0.5 specs retain legacy compilation. See
[expression planning](mosocanvas/references/expression-planning.md). The release passes 83
automated tests; improved image quality has not yet been demonstrated through a controlled visual study.

Download the [v1.7.0 ZIP](dist/mosocanvas-1.7.0.zip), verify it with the
[SHA-256 manifest](dist/mosocanvas-1.7.0.manifest.json), and read the
[version notes](release-notes/v1.7.0.md).

Version 1.3 adds a truthful Codex Image Canvas adapter: focused comments bind to one artifact,
multi-select edits retain separate parent lineages, and region claims require honest localization.
Version 1.4 adds RGBA/ICC preservation checks bound to source hashes; geometry alone does not prove
that protected pixels survived.

This repository is public for viewing and evaluation. It is not an open-source grant. See [LICENSE](LICENSE).

Version 1.5 adds a three-agent review protocol: fresh-context image observations are sealed before
requirements are revealed, then evidence-bound recommendations are counted without suppressing
minority findings. The host schedules agents; the deterministic helper checks records. Majority
votes do not authorize release or automatically establish user preferences. See
[three-agent review](mosocanvas/references/three-agent-review.md) and
[learning and memory](mosocanvas/references/learning-and-memory.md).

Version 1.6 adds a persistent, non-destructive edit document. A clean anchor remains immutable,
accepted regional changes are stored as replayable operations, and later generation inputs contain
only the clean anchor plus explicitly selected dependencies. Each commit is bound to a plan, source
hashes, a staged composite, an attempt review, and an exact outside-mask preservation report. See
[non-destructive editing](mosocanvas/references/non-destructive-editing.md).

## Non-destructive regional editing

Create one edit document from the approved clean image, then prepare each bounded change from that
document instead of feeding the latest generated full frame back into the model:

```bash
./bin/mosocanvas edit-state init approved-clean.png \
  --document work/edit-state.json --id campaign-key-visual
./bin/mosocanvas prepare-edit work/edit-state.json regions.json \
  --output-dir work/attempt-001 --id op-001 --target "repair the selected leaf texture"
```

Send `work/attempt-001/prepared-input.png` to the image tool. Keep the raw result separate, then
stage the exact mask composite for visual review:

```bash
./bin/mosocanvas stage-edit work/edit-state.json \
  work/attempt-001/edit-plan.json raw-candidate.png \
  --output work/attempt-001/staged.png \
  --report work/attempt-001/preservation.json
```

After an attempt review accepts that staged image, commit the operation and render the document:

```bash
./bin/mosocanvas commit-edit work/edit-state.json \
  work/attempt-001/edit-plan.json raw-candidate.png \
  --staged work/attempt-001/staged.png \
  --attempt-review work/attempt-001/attempt-review.json \
  --output work/current.png
./bin/mosocanvas edit-state verify work/edit-state.json
```

Later attempts return to the clean anchor by default. Pass `--depends-on op-001` to `prepare-edit`
only when the new target needs that accepted operation as visible context.

## Image request compilation

Version 1.4 compiles a single-frame Visual Spec into a reviewable native image-tool request. It
preserves reference roles, exact copy, constraints and parent-bound feedback, and lists unsupported
parameters without pretending to apply them. Its optional `editorial-depth` pack builds on
MoSoCanvas's own first/second-read and viewer-position method. No external skill catalog or code
is incorporated. Explicit user decisions override direction defaults.

Use Python 3.10+ in an environment with `mosocanvas/requirements-dev.txt` installed:

```bash
python3 bin/mosocanvas compile \
  --spec mosocanvas/examples/editorial-depth-spec.example.json \
  --output /path/to/work/request.json
python3 bin/mosocanvas direction-board --pack editorial-depth --output /path/to/work/directions.png
python3 mosocanvas/scripts/self_check.py --strict
```

Compilation does not generate or typeset an image. Inspect the request and references, invoke the
available image tool, then inspect the actual result. The preview is a spatial diagram, not a
generated-art benchmark. See [the compiler guide](mosocanvas/references/generation-compiler.md).

The repository's `mosocanvas/` is the maintained source. Active `.agents/skills/mosocanvas` copies
are installation mirrors: compare and back them up before synchronization, preserve local edits,
and run the strict self-check from the synchronized copy. Do not maintain both copies independently.
Local checks and packaging do not authorize publication or demonstrate improved visual quality.

## Wallpaper sales packs

MoSoCanvas also includes a local, deterministic wallpaper packager. It converts one approved
portrait or landscape master into the compatible phone or computer targets, applies the approved
MoSo signature, writes a contact sheet and manifest, and creates a ZIP sales pack. It does not use
generative expansion or redraw the artwork.

From this repository root:

```bash
python3 -m pip install -r mosocanvas/requirements-dev.txt
./bin/mosocanvas wallpaper-pack /path/to/master.png --preset sellable
```

The command accepts a single image or a directory of masters. A portrait source produces the two
iPhone targets; a landscape source produces the three computer targets. A directory containing
both orientations produces the complete pack. Opposite-orientation targets are skipped by default
to protect composition; use `--include-mismatched` only when you intend to inspect those crops.

Useful options:

```bash
./bin/mosocanvas wallpaper-pack /path/to/masters \
  --preset sellable \
  --output-dir /path/to/love-is-fury-wallpaper-pack \
  --focus 0.5,0.5
```

The output contains `signed/`, `preview/contact-sheet.png`, `manifest.json`, `README.md`, and a
ZIP archive beside the pack directory. Use `--signature clean` only for a controlled clean-master
export; the default is the signed sales output.
