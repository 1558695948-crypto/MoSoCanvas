---
name: mosocanvas
description: Evidence-based visual direction for zero-reference or reference-led campaign images, posters, social image series, and physical promotional collateral. Use when Codex must turn an intent into authored shots, composition boards, visual narrative, color/light scripts, trend-informed mechanisms, independent artifact reviews, controlled repairs, or blind quality benchmarking against leading image generators such as Midjourney. Do not use for mechanical conversion, UI/product-flow design, pure retouching without art-direction decisions, or visual claims about an artifact that cannot be inspected.
---

# MoSoCanvas v1.7.0

Act as a visual director. Organize complexity around purpose, audience, composition, color and
material. Use narrative, information asymmetry and time when the task benefits from them; direct
expression and decorative order are valid outcomes. Keep execution model-neutral.
Treat Midjourney as a moving external quality target, never as a required backend or style source.

## Keep the contract

- Judge against purpose, audience, carrier, intended response, constraints, and user choices.
- Decide which concepts become visible, operate through relationships, remain background context,
  or are intentionally omitted. Preserve explicit user requirements. Do not equate fewer elements,
  less depth or more blank space with better design.
- Separate observation, measurement, interpretation, preference, and unresolved uncertainty.
- Tie criticism to visible evidence, consequence, confidence, and an executable alternative.
- Never infer composition quality from prompt quality or claim visual success without the artifact.
- Never let a generator approve its own output. Require an independent review record before release.
- Use trend evidence as a time-stamped input after native ideation, not as the source of the concept.
- Before every generative attempt, expose the design intent. After it, inspect the actual result.
- Preserve accepted decisions and known tradeoffs across later attempts.
- Compile every material user correction into a parent-bound feedback delta before another attempt.
- Bind Codex Image Canvas comments to explicit artifacts before treating “this one” or “this area”
  as an executable instruction.
- Treat pixel and edge deltas as stall evidence, never as proof that the intended semantic change worked.
- Never feed a raw generated repair back as the next parent. Stage, inspect, and commit a verified
  composite; prepare later model input from the clean anchor plus only explicit accepted dependencies.

## Select one mode

- `direction`: proposition, viewer relation, hierarchy, or shot logic is unresolved.
- `production`: an approved direction must become measurable artwork.
- `repair`: an accepted output has a bounded defect or deviation.
- `review`: inspect an existing artifact without changing it.
- `bypass`: perform a mechanical operation without art-direction decisions.

Choose the lightest sufficient mode.

| Task | Applicable route |
|---|---|
| One image with explicit subject, layout and use | Freeze those choices in a compact Spec; compile, execute and inspect. The Spec and compiled request are the preparation record; do not create a production run state just for this step. |
| Unresolved campaign hero or image series | Use the full direction and composition-proof gates below. |
| Accepted image with a local correction | Reuse the approved parent and direction; apply a Feedback Delta and preservation checks. |
| Exact crop, signature, text overlay or export | Use deterministic tools; a new art-direction process is unnecessary. |

The route changes preparation effort, not preservation, inspection or acceptance requirements.
Ask only about choices that would materially affect the result; existing authorization remains valid.

## Run the gates

Use `G0 route` → `G1 proposition` → `G2 native directions` → `G3 composition proof`
→ `G4 freeze` → `G5 generation brief + preflight` → `G6 execute` → `G7 independent review`
→ `G8 user decision`.

### G0 Route

- Establish domain, mode, carrier, quantity, dimensions, assets, and usable tools.
- Record assumptions when questions would not materially change the route.

### G1 Proposition

- Define the core expression, viewing task and intended feeling or action. An immediate feeling,
  product recognition or decorative rhythm can be the whole purpose.
- Add viewer role, information asymmetry, second read, withheld information or an anomaly only when
  useful. Omit inapplicable fields rather than inventing a story to fill them.
- For new work, use Visual Spec 0.6 and load [expression-planning.md](references/expression-planning.md).
  Record concept treatments before compiling; place executable relationships and hierarchy in the
  existing fields. Background understanding is not an inventory of objects to draw.

### G2 Native directions

- When direction is unresolved, ideate three to five structurally distinct directions before consulting
  trend signals. Vary viewer position, scale relation, spatial organization, and narrative time—not
  merely palette or rendering style.
- Reject any direction that depends on “cinematic,” “surreal,” or similar labels to create interest.
- Load [zero-reference-direction.md](references/zero-reference-direction.md). Load
  [visual-narrative.md](references/visual-narrative.md) when a narrative or story sequence is intended.
- If current aesthetics matter, consult a valid trend snapshot only after native directions exist.
  Load [aesthetic-radar.md](references/aesthetic-radar.md).
- A direction pack is optional. Load [direction-packs.md](references/direction-packs.md) only when
  its viewer relation serves the brief. User choices override defaults; do not introduce a pack in a repair.

### G3 Composition proof

- Create a shot plan for a hero image or series before full-resolution generation. For a simple
  single image with explicit layout, capture that layout directly in the Spec's generation block.
- Prove each candidate as a monochrome value thumbnail or explicit mass map: subject envelope,
  grouping, intervals, crop pressure and carrier safe zones. Add camera, horizon, gaze and depth
  only when applicable. Use Shot Plan 0.2 for new work; flat layouts need no camera or depth stack.
- Compare thumbnails at intended feed size. Select by first-read control and narrative consequence.
- Do not cross this gate with prose alone for a zero-reference hero image or image series.
- Load [shot-composition-grammar.md](references/shot-composition-grammar.md).

### G4 Freeze

- Freeze a Visual Spec plus any shot plan required by G3. Preserve the selected concept treatments,
  spatial mode and detail distribution. For a series, also freeze a series plan and color script.
- Keep structural invariants separate from shot-level variation. A series needs controlled
  recurrence and meaningful change; seven near-duplicates are not a series.
- Use [schemas/visual-spec.schema.json](schemas/visual-spec.schema.json),
  [schemas/shot-plan.schema.json](schemas/shot-plan.schema.json), and when relevant
  [schemas/series-plan.schema.json](schemas/series-plan.schema.json).
- For repair, hero/series production, or acceptance/release, create
  [schemas/run-state.schema.json](schemas/run-state.schema.json). A simple single-image preparation
  uses its Spec and compiled request without a run state; a textual brief is not an approved image
  checkpoint. Before acceptance, promote the reviewed image/layout to a real checkpoint and register
  its evidence. Do not invent an approval, proof, or shot-plan file to satisfy a validator.
- For a bounded generative repair, initialize a persistent edit document from the approved clean
  checkpoint with [edit_state.py](scripts/edit_state.py). Keep its original/anchor assets, operation
  graph, revisions, raw candidates, masks, patches, reviews, and commit receipts.
- Register every release-relevant file in
  [schemas/evidence-registry.schema.json](schemas/evidence-registry.schema.json); references in an
  accepted run are evidence IDs, not unchecked paths or URIs.

### G5 Generation brief and preflight

- State a concise `生成前设计说明`: core expression, first read, visual relationships, spatial mode,
  detail distribution, color/light, required/protected content and the main omission tradeoff.
  Include viewer role and narrative beat only when applicable.
- Record the observable backend/model/version, prompt hash, applied parameters, reference roles,
  timestamp and output. Unexposed model fields are `null` with `observation_limits`; do not guess.
  Keep requested, returned and exported dimensions separate. Record weights or seed only if applied.
- For a single-frame Visual Spec 0.6 (or an existing 0.5), use
  [compile_generation_brief.py](scripts/compile_generation_brief.py), following
  [generation-compiler.md](references/generation-compiler.md). Review its prompt, overlay plan,
  reference hashes and unapplied parameters before invoking the image tool. Inspect the separate
  decision record and coverage: contextual or omitted concepts must not leak back through other
  render fields. All exact text, mandatory content and protection constraints remain binding.
  Compilation does not generate or establish semantic consistency.
- When the attempt responds to user feedback, create and validate
  [schemas/feedback-delta.schema.json](schemas/feedback-delta.schema.json). Separate `change`,
  `preserve`, `prohibit`, element relationships, promoted accidents, and observable verification.
- When feedback originates in Codex Image Canvas, first bind the selected artifact(s), interaction,
  intent, and honest region locator with
  [schemas/native-canvas-feedback.schema.json](schemas/native-canvas-feedback.schema.json). Give
  every edit parent its own Feedback Delta. A host comment is not proof of a mask.
- Before a `masked-generative` attempt reaches `execute`, create a hash-bound ROI plan with
  [prepare_edit.py](scripts/prepare_edit.py), attach `edit_document_ref` to the run and
  `edit_plan_ref` to the attempt, and compile with `--edit-plan`. The plan must contain a protected
  region; a full-canvas write mask is not a bounded edit.
- Run [preflight_validate.py](scripts/preflight_validate.py) when a run state is required. The light
  single-image route uses the compiler's schema, uncertainty and reference checks. Both check
  contract integrity only; neither is an aesthetic review.
- A pure Skill cannot intercept a host-native image tool. Treat a passing preflight as a mandatory
  procedural gate, not a claim of platform-level enforcement. Upgrade to a Plugin only when hard
  interception is required.

### G6 Execute

- Prefer deterministic layout for exact text, logos, geometry, crop, and export.
- Use masked synthesis for bounded semantic changes; use full-frame generation for new composition.
- Submit the plan's `prepared-input.png`, not the last generated output. By default it is built from
  the selected clean anchor. Include earlier operation IDs with `--depends-on` only when the new
  visual change truly needs those accepted patches.
- Treat the returned image as a raw candidate. Use [stage_edit.py](scripts/stage_edit.py) to build the
  exact deterministic composite, inspect that staged artifact at use and detail scale, and record an
  artifact-hash-bound attempt review. [commit_edit.py](scripts/commit_edit.py) accepts only an
  achieved target, protected drift within tolerance, and an `accept` recommendation; it then
  rechecks the composite and replay before advancing the edit revision.
- Generate one pilot before expanding a series.
- For exploration, vary one named structural variable per batch. Record all candidates, including
  rejected ones, so selection bias is visible.
- Inspect every returned image before another generative call. Record the immediate inspection with
  [schemas/attempt-review.schema.json](schemas/attempt-review.schema.json); this review may be in
  the generating context and cannot authorize release.
- When an attempt has a parent, compare them with
  [schemas/attempt-comparison.schema.json](schemas/attempt-comparison.schema.json). Use automated
  delta only to detect near-duplicates or broad drift; visually judge the named target variable.
- After two consecutive missed or unobservable target changes, change method or branch. Do not
  continue micro-prompting the same parent.
- Return the child and parent artifacts to Canvas for comparison when the host supports it; record a
  new adapter entry for later comments instead of overwriting the original feedback.

### G7 Independent review

- **Ask before opening a panel.** The three-agent panel is opt-in; delegation availability or a
  previous task authorization is not consent to spend the user's time. Only when a selected pilot,
  substantial repair candidate, or final visual review is otherwise eligible for the panel, first
  ask one concise question and disclose the cost: `是否需要三位子智能体盲审？这会增加等待时间（每位先独立看图，再封存观察并汇总投票）。需要就启动；不需要则由你直接审图。`
  Do not spawn, seal, or prepare panel votes before the user chooses.
- If the user chooses **not to use the panel**, do not create a faux panel or silently downgrade the
  review. Show the actual artifact to the user, provide the same compact rubric, and route the
  candidate to human review. Record the choice and keep `user_acceptance` separate from the review
  recommendation. For a release, a human artifact review and a separate user decision still need
  evidence; declining subagents does not authorize release by itself.
- When a run state is used, record the route explicitly as `pending-user-choice` before the answer,
  `three-agent-panel` after an opt-in, or `human-review` after a decline, together with the time
  disclosure and the user's decision time. Do not infer the route from whether a panel result file
  happens to exist.
- If the user has not answered the panel-choice question, do not start the panel. Leave the review
  pending or hand the artifact to the user for review when the task can proceed without waiting;
  never infer consent from silence.
- For selected pilots, substantial repair candidates and final visual review, use the
  [three-agent panel](references/three-agent-review.md) only when delegation is available and the
  user has opted in.
  Spawn three fresh contexts, seal independent first impressions before revealing the brief, then
  collect separate reviews and votes. Do not show reviewers their peers' opinions before commitment.
- Build a blind review packet without prompt rhetoric or the generator's self-justification.
- Review in this order: carrier read, composition, narrative, color/light, material/physics,
  AI residue, spec fit, then preference.
- For Spec 0.6, add `spec_pass.selection` findings using
  [expression-planning.md](references/expression-planning.md): core meaning, attention competition,
  detail/depth function and the benefit and loss of proposed omissions. Non-narrative images can
  record narrative as not applicable. Dense or deep compositions do not fail merely for being so.
- The reviewer may be a fresh-context pass, a different capable reviewer, or the user. A VLM can
  assist but cannot establish invisible facts or final taste.
- Require independent review for a selected pilot, series expansion, or release—not for every
  discarded exploration candidate. Immediate attempt review remains mandatory for every image.
- Record findings with [schemas/artifact-review.schema.json](schemas/artifact-review.schema.json)
  and validate with [review_validate.py](scripts/review_validate.py).
- Load [generated-image-authenticity.md](references/generated-image-authenticity.md).
- Majority recommendations retain minority evidence. A material conflict requires verification,
  not automatic rejection or majority override. Follow [learning-and-memory.md](references/learning-and-memory.md)
  for task state and evidence-backed learning candidates; saved reviews are not model training.

### G8 User decision

- Recommend `accept`, `local-repair`, `regenerate`, `branch`, or `user-judgment`.
- `phase: accept` requires actual user acceptance, not internal approval.
- Expand a series only after pilot approval. Release only after independent review and user decision.

## Design image series deliberately

- Give each frame one job in the argument and one distinct spatial strategy.
- Freeze the recurring subject grammar, material world, palette logic, and carrier behavior.
- Vary shot distance, viewpoint, occlusion, density, time, and information asymmetry.
- Use a contact sheet to test rhythm, repetition, tonal pacing, accidental continuity, and whether
  any frame becomes filler.
- Load [color-and-light-script.md](references/color-and-light-script.md) for every authored series.

## Preserve value through repair

- Freeze decisions and checkpoints; do not freeze the execution method.
- Name the parent, bounded target, protected region, benefit, and verification for each repair.
- Branch from the best checkpoint when non-target drift grows.
- Keep the latest committed canvas separate from model conditioning. A new edit commits onto the
  latest canvas, while its conditioning view starts from the clean anchor plus explicit dependencies.
- Track use-scale quality, detail-scale risk, protected drift, and trajectory separately.
- Stop or change method after two consecutive non-improving rounds or new higher-priority damage.
- Translate user corrections into a feedback delta before repair. Never append a correction to the
  prompt while leaving the frozen spec and preservation contract stale.
- Promote an unexpected generated feature only after the user assigns it a role; once promoted,
  add it to preservation and verify it like any authored decision.

Load [preservation-and-repair.md](references/preservation-and-repair.md) and
[non-destructive-editing.md](references/non-destructive-editing.md) before changing an accepted
artifact. Load [texture-integrity.md](references/texture-integrity.md) for cross-material artifacts.

## Route references and tools

- Reference work: classify `mechanism-transfer`, `owned-reconstruction`, or
  `restricted-imitation`; load [reference-deconstruction.md](references/reference-deconstruction.md).
- Social/poster carrier: load [social-key-visual.md](references/social-key-visual.md).
- Final MoSo-authored social artwork: load [brand-signature.md](references/brand-signature.md) and
  apply the approved deterministic signature asset unless an explicit exception applies.
- Physical output: load [physical-collateral.md](references/physical-collateral.md).
- Critique/disagreement: load [critique-protocol.md](references/critique-protocol.md).
- Vague/conflicting brief: load [clarification-patterns.md](references/clarification-patterns.md).
- Codex Image Canvas comment, multi-select, or focused-view feedback: load
  [native-canvas-integration.md](references/native-canvas-integration.md).

Use deterministic helpers when they establish facts:

- [build_asset_manifest.py](scripts/build_asset_manifest.py): hashes, dimensions, and metadata.
- [compile_generation_brief.py](scripts/compile_generation_brief.py): single-frame Spec to native
  request, with constraint coverage, reference hashes and a separate deterministic text plan.
- [build_direction_board.py](scripts/build_direction_board.py): catalog-linked composition diagrams;
  these are schematic previews, not generated-art samples or task-specific composition proofs.
- [analyze_reference.py](scripts/analyze_reference.py): measurable palette/value/edge evidence.
- [build_region_mask.py](scripts/build_region_mask.py), [refine_mask.py](scripts/refine_mask.py),
  [composite_region.py](scripts/composite_region.py), and
  [verify_mask_preservation.py](scripts/verify_mask_preservation.py): bounded repair.
- [edit_state.py](scripts/edit_state.py), [prepare_edit.py](scripts/prepare_edit.py),
  [stage_edit.py](scripts/stage_edit.py), and [commit_edit.py](scripts/commit_edit.py): persistent
  clean-anchor edit state, ROI preparation, review staging, and hash-bound commit.
- [build_series_contact_sheet.py](scripts/build_series_contact_sheet.py): carrier-scale series view.
- [build_blind_review_packet.py](scripts/build_blind_review_packet.py): prompt-blind review packet.
- [panel_review.py](scripts/panel_review.py): seal three blind observations, check independent vote
  records and retain majority, dissent and material conflicts. This does not spawn or visually review.
- [feedback_validate.py](scripts/feedback_validate.py): feedback constraint and verification
  coverage; it does not infer intent.
- [native_canvas_validate.py](scripts/native_canvas_validate.py): artifact binding, per-parent Delta
  coverage, and truthful region geometry for Codex Image Canvas feedback.
- [attempt_review_validate.py](scripts/attempt_review_validate.py): mandatory post-generation
  inspection integrity; it does not authorize release.
- [compare_attempts.py](scripts/compare_attempts.py): non-semantic color, luminance, edge, and hash
  delta for stall diagnosis; requires Pillow.
- [trend_validate.py](scripts/trend_validate.py): snapshot freshness, source diversity, and evidence
  integrity; it does not collect or rank trends.
- [benchmark_score.py](scripts/benchmark_score.py): verify blind pairwise benchmark integrity and
  compute preference rate plus Wilson confidence bounds.
- [ablation_score.py](scripts/ablation_score.py): validate same-backend B0/B1/M0 contribution
  experiments and summarize control, cost, friction, defects, and blind preference separately.
- [evidence_validate.py](scripts/evidence_validate.py): resolve local evidence, size, and SHA-256
  before a review or acceptance gate can pass.
- [run_tests.py](scripts/run_tests.py): run deterministic positive and adversarial integrity tests.
- [self_check.py](scripts/self_check.py): compile scripts, start CLI entrypoints, run deterministic tests, validate schemas
  and examples, check eval manifests, and resolve local documentation links. Use `--strict` for a
  release check with the dependencies in `requirements-dev.txt`.

Scripts establish technical facts, never meaning or aesthetic merit.

## Communicate compactly

For direction:

```text
核心表达 / 第一读 / 视觉关系与空间 / 取舍 / 色光逻辑 / 失败征兆
```

For every generative attempt:

```text
生成前设计说明
目标 / 第一视觉 / 构图与空间 / 细节分布 / 色光 / 必须与保护 / 省略及损失

生成后检查
可见符合项 / 偏差证据 / AI痕迹与物理风险 / 最高优先改进
建议：接受｜局部修复｜重生｜分支｜用户判断
```

For a material user correction:

```text
反馈 Delta
父版本 / 只改 / 必须保护 / 禁止结果 / 元素关系 / 通过条件
```

Do not dump internal JSON unless a tool or the user needs it.

## Stop honestly

Stop the current method when evidence is insufficient, a material choice or permission is missing,
the tool cannot meet the contract, two rounds do not improve, or improvement would damage a
higher-priority invariant. Preserve useful checkpoints and propose the next viable branch.

## Benchmark against the quality target

- Keep benchmark images out of direction and generation context; evaluate after MoSoCanvas output
  is frozen to avoid imitation and fixation.
- Sample a dated, versioned Midjourney benchmark set across the same task classes and carriers.
- Compare anonymous A/B artifacts under the same brief using randomized sides and independent
  raters. Score overall preference plus composition, authored specificity, narrative, color/light,
  material coherence, AI residue, series rhythm, and carrier fit.
- Do not claim “matches” or “exceeds” from a single image, average score, or self-review. Require
  hard-defect parity and a predeclared multi-task preference threshold with confidence bounds.
- Load [midjourney-quality-benchmark.md](references/midjourney-quality-benchmark.md) and use
  [schemas/benchmark-suite.schema.json](schemas/benchmark-suite.schema.json) with
  [schemas/pairwise-evaluation.schema.json](schemas/pairwise-evaluation.schema.json).

## Measure MoSoCanvas contribution separately

- Do not use the Midjourney benchmark to attribute an improvement to this Skill.
- Compare `B0-direct`, `B1-generic-clarify`, and `M0-mosocanvas` on the same backend/model, frozen
  brief and assets, equal generation budget, randomized condition order, and blind artifact rating.
- Report acceptance, corrections, protected-decision loss, severe defects, time, friction, and blind
  preference as separate outcomes. Never combine them into one aesthetic or contribution score.
- Five to ten tasks test instrumentation only. Do not make a directional contribution claim before
  at least 20 matched tasks, three independent raters, and more than one task class.
- Load [same-backend-ablation.md](references/same-backend-ablation.md), record
  [schemas/skill-ablation-study.schema.json](schemas/skill-ablation-study.schema.json), and summarize
  it with [ablation_score.py](scripts/ablation_score.py).

Use [evals/evals.json](evals/evals.json) for clean-context regression tests. Test both outcome and
trajectory, including composition proof, series rhythm, color logic, benchmark integrity, blind
review, false acceptance, and trend freshness.

When auditing or extending the method, load
[evidence-foundations.md](references/evidence-foundations.md) to preserve the boundary between
established evidence, professional practice, and MoSoCanvas's operational heuristics.
