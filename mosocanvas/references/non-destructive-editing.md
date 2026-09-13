# Non-destructive generative editing

Use this workflow for a second semantic edit of the same artwork, any repair of an accepted artifact,
or any claim that content outside a region stayed exact. It addresses recursive image contamination
by separating four things that were previously easy to collapse into one file:

- **clean anchor:** immutable decoded source for model conditioning;
- **commit base:** latest verified canvas that receives a new patch;
- **raw candidate:** generator output that is never a parent by itself;
- **operation:** mask, patch, review, preservation report, and receipt that can be replayed.

The model may still reinterpret pixels inside the target. The native tool has no mask argument, so
transparent input is guidance. Exact outside-mask preservation comes from deterministic composition,
not from the model.

## 1. Initialize once from the clean approved checkpoint

```bash
python3 scripts/edit_state.py init approved.png \
  --document work/edit-state.json --id artwork-01
```

The document stores content-addressed assets and immutable revision snapshots. `current_render` may
advance; `selected_anchor` stays stable. Verify or replay at any time:

```bash
python3 scripts/edit_state.py verify work/edit-state.json
python3 scripts/edit_state.py render work/edit-state.json --output work/replay.png
```

## 2. Define ROI and prepare the next input

Regions use full-canvas top-left pixel coordinates:

```json
{"regions":[{"kind":"rectangle","box":[420,260,980,820]}]}
```

Polygon and ellipse regions are also accepted. Prepare a cropped context when possible:

```bash
python3 scripts/prepare_edit.py work/edit-state.json regions.json \
  --output-dir work/plans/repair-01 \
  --id repair-01 --target "remove repeated maze texture from the jacket" \
  --crop 360,200,720,720 --grow 8 --feather 4
```

This writes `conditioning-render.png`, `prepared-input.png`, `write-mask.png`, `mask-preview.png`,
and `edit-plan.json`. The conditioning render starts from the clean anchor. To include an accepted
prior patch because the new change depends on it, add its operation ID:

```bash
  --depends-on accepted-face-repair
```

Dependencies must already be committed and transitively complete. Do not use this flag merely because
an operation is newer.

Attach the persistent files to run state before `execute`:

```json
{
  "edit_document_ref": "work/edit-state.json",
  "generation_attempts": [{
    "attempt_id": "repair-01",
    "edit_plan_ref": "work/plans/repair-01/edit-plan.json"
  }]
}
```

Compile the repair with `--feedback` and `--edit-plan`. The tool arguments use
`prepared-input.png`; the approved full-canvas image remains the lineage binding.

## 3. Stage, inspect, then commit

Save the model return as a raw candidate. It must have the same size as the prepared input.

```bash
python3 scripts/stage_edit.py work/edit-state.json \
  work/plans/repair-01/edit-plan.json raw-candidate.png \
  --output work/reviews/repair-01-staged.png \
  --report work/reviews/repair-01-preservation.json
```

Inspect the staged composite at use scale and native/detail scale. Create an attempt review whose
`artifact_ref` points to the staged PNG and whose `artifact_sha256` is the printed staged hash.
Commit is blocked unless the target status is `achieved`, protected drift is `none` or
`within-tolerance`, and recommendation is `accept`.

```bash
python3 scripts/commit_edit.py work/edit-state.json \
  work/plans/repair-01/edit-plan.json raw-candidate.png \
  --staged work/reviews/repair-01-staged.png \
  --attempt-review work/reviews/repair-01-review.json \
  --output work/current.png
```

Commit rechecks all hashes, revision freshness, plan/document identity, candidate dimensions,
protected pixels, ICC, staged image identity, and full operation-graph replay. It advances the edit
document by one revision and writes a receipt. A stale plan, tampered review, or failed candidate does
not become the next canvas.

After commit, attach the receipt to the reviewed run-state attempt as `edit_receipt_ref`. Update the
approved checkpoint to the committed render before planning another attempt. The edit document still
retains its earlier clean anchor for the next conditioning view.

## Technical boundary

This workflow prevents whole-canvas model rewrites and accidental raw child-to-parent recursion. It
does not remove artifacts already inside the clean anchor, guarantee that the model repairs the target,
or implement frequency-domain restoration inside the native image model. If texture contamination is
global, branch from a cleaner source or regenerate from the frozen Visual Spec. If periodic lattice
artifacts remain local, a separately validated spectral or deterministic retouching tool can be added
as another patch operation.

The risk model follows the observed iterative-edit degradation described by
[Mi-Ripple](https://arxiv.org/abs/2609.11317), the frequency/identity drift studied by
[FreqEdit](https://arxiv.org/abs/2512.01755), and repeated encode/decode degradation studied by
[REED-VAE](https://reed-vae.github.io/). These sources motivate the controls; they do not benchmark
this exact MoSoCanvas operation-graph implementation.
