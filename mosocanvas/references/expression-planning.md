# Expression planning

Use Visual Spec 0.6 for new work. Decide how meaning becomes visible before compiling a prompt.
The aim is purposeful organization at any complexity, not a minimal house style. These controls
are operational hypotheses; the named coverage, depth and semantic-density tendencies are not
established universal laws or proven explanations of model training.

## Make the selection explicit

Keep the core expression in `proposition` and viewing intent in `viewer_contract`. Narrative
fields (position, information power, second read, withheld information, residual question,
familiar rule and designed anomaly) are optional. Do not fill them with invented storytelling.
Place actionable attention instructions in `hierarchy`, visible relationships in `relationships`,
and delayed visibility constraints in `perceptual_reveals` when needed.

`expression_plan.concepts` covers the important meanings in the brief, not every word:

| treatment | What reaches the image tool | What stays in the decision record |
|---|---|---|
| `explicit` | The selected `render_instruction` | Concept label and reason |
| `relational` | Existing `relationships` linked by `relationship_refs` | Concept label and reason |
| `context-only` | No instruction from this concept entry | Context, reason and `expected_loss` |
| `omit` | No instruction from this concept entry | Deliberate omission, reason and `expected_loss` |

Use context to make a concrete choice elsewhere, such as a material or scale relation. Do not
repeat the contextual concept in `generation.subject` or composition as an unselected object.
Several concepts may share one relationship. Do not assume that a compact symbol conveys the
intended meaning: the result must still be read without the prompt.

Mark user-required visible content `required_visible: true`; it must remain `explicit`. Bind
existing requirements with `constraint_refs`, for example `constraints.must_include[0]` or
`constraints.preserve[1]`. Bound requirements cannot use `context-only` or `omit`. A required
relationship may use `relational`; a required visible object must remain explicit. The original
`must_include`, `must_avoid` and `preserve` arrays always reach the image tool, whether mapped or not.
Exact wording and official assets retain their existing text/overlay and reference procedures.

The compiler validates IDs, references and declared visibility; it cannot identify every semantic
contradiction or determine whether the agent correctly extracted a user requirement. Inspect the
compiled prompt against the original brief. Never use omission to silently relax that brief.

## Choose space and detail

Record `expression_plan.space.mode` as `flat`, `shallow`, `deep` or `mixed`, with an executable
`instruction`. Deep/mixed choices also record a `reason` describing their function. The reason
stays in the decision record. Use the same `spatial_mode` in a selected Shot Plan 0.2.

`detail_distribution` is optional: each entry names a region and its rendering instruction.
Quiet regions may retain texture, low contrast or repetition. There is no fixed blank-space
quota, element limit, attention percentage or penalty for deep space. A task requiring ten objects
still needs ten objects. Texture complexity, the number of independent meanings and expression
efficiency are different properties.

## Compile and inspect

See [generation-compiler.md](generation-compiler.md) and the
[selective expression example](../examples/selective-expression-spec.example.json).
The compiled request contains both `decision_record` and `prompt`; only `tool_arguments` is sent
to the model. `coverage` records destinations and relationship mappings, including deliberately
non-rendered content. It proves routing, not visual comprehension.

Before execution, check that concrete fields retain all selected visual decisions and hard
constraints, without reintroducing omitted material. In particular, copy an important narrative
action from the rationale into the actual scene/relationship instructions if it is meant to appear.
Do not send the complete request JSON or decision record to the image tool.

## Review selection as well as execution

Keep the existing prompt-blind pass. For a non-narrative image, `inferred_narrative` may truthfully
say that no story was inferred; do not reward an invented interpretation. This is a reviewer
observation, not a measurement of actual audience gaze or understanding.

After revealing the brief, add nonempty `spec_pass.selection` findings on:

- the core meaning actually inferred and any essential meaning lost;
- competing attention and whether detail contributes useful distinctions or repeats an explanation;
- the function of depth and whether the chosen spatial mode survived;
- the benefit AND information loss of any proposed deletion or weakening.

Use the existing evidence-region, consequence, confidence and severity fields. Dense or deep work
can pass. Sparse work can fail. A possible simplification is not automatically a defect. Record
tradeoffs and uncertainty; do not invent a numerical organization or beauty score. Spec 0.6 release
reviews and panels require this category; legacy review records remain usable for legacy specs.

## Check contribution

Extend [same-backend-ablation.md](same-backend-ablation.md) with a versioned comparison of the
released workflow and this candidate. Include sparse and dense, flat and deep, direct and narrative
tasks, plus briefs with many mandatory items. Preserve all outputs and keep budgets equal.
An optional intermediate condition that only relaxes defaults can separate that effect from
selection/compilation. Freeze conditions before running and hide them from raters.

Report core-meaning readings, mandatory-content retention, organization findings and preference
separately. A shorter prompt or passing schema is not evidence of improved images. Deterministic
regressions check routing and preservation; clean-context behavior and actual audience response
require separate experiments under the existing benchmark standards.
