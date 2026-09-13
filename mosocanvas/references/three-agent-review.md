# Three-agent blind review

Use this panel for selected pilots, meaningful repair candidates and final visual review **only
after the user opts in**. Delegation availability, a previous authorization, or the fact that a
panel is useful does not count as consent to spend the user's time. The host agent schedules the
reviewers; the Python helper seals evidence and counts recommendations. It does not spawn agents,
inspect images or execute repairs. Immediate inspection still applies to every generated candidate;
do not spend three full reviews on every discarded exploration.

## Panel-choice gate

Before step 1, ask once when this candidate is eligible for a panel:

> 是否需要三位子智能体盲审？这会增加等待时间：三位评审要先独立看图、封存首次观察，再分别复核并汇总投票。需要就启动；不需要则由你直接审图。

Wait for the user's choice before spawning, sealing, or preparing votes. If the user chooses not to
use the panel, stop this protocol and use the human-review route:

1. Show the actual artifact and the compact rubric (carrier read, composition, narrative,
   color/light, material/physics, AI residue and spec fit).
2. Ask the user to accept, request a local repair, regenerate, branch, or leave it for judgment.
3. Record the human review and the user decision separately. A human review can satisfy an
   independent-review evidence requirement when it actually inspects the artifact, but it does not
   authorize release without the required evidence and explicit user decision.

When a run state is present, record `review_route.status` as `pending-user-choice` while waiting,
`three-agent-panel` after an opt-in, or `human-review` after a decline. Include the time disclosure,
the user's decision time, and the actor; do not use the presence or absence of a panel-result file as
the user's choice.

If the user has not answered, do not start the panel. Leave the choice pending or hand the artifact
to the user when the task can continue without waiting. Silence is not consent. A later request for
the panel starts a new panel with a fresh candidate/context as required below.

## Separate observation from intent

1. Freeze the candidate bytes. Make a neutral-named byte-identical copy in a review directory.
   Keep the source mapping, generation prompt, prior reviews, accepted/rejected labels and Spec
   outside the first-pass packet. Do not edit the art to conceal visible branding. Visible branding
   or recognizable styles can compromise source blindness; record that limitation.
2. Spawn exactly three reviewers with `fork_turns="none"`. Give each only the neutral image path,
   its own output path, and the common first-pass rubric. Tell reviewers not to read project history,
   memory, image metadata, sibling outputs or external sources. This is an isolated, self-contained
   image task. Require actual viewing; an inaccessible image is an incomplete review, never a vote.
3. Each independently writes a [blind observation](../schemas/blind-observation.schema.json): first
   read, eye path, inferred narrative, anomalies, strengths and uncertainties. All three inspect
   composition, narrative, color/light, physical plausibility and visible artifacts. Optional extra
   attention areas do not replace the common rubric. Record viewing scale and limitations.
4. Wait for all three first passes. Seal their exact bytes with the command below **before** exposing
   the requirements. Do not rewrite observations after learning the intended meaning.
5. Give each same-context reviewer the same bounded review brief/Spec and its own sealed observation.
   Never send another reviewer's findings. Each writes an [artifact review](../schemas/artifact-review.schema.json)
   and [vote](../schemas/panel-vote.schema.json). All seven Spec categories require actual findings,
   including positive findings. Preserve the original blind_pass verbatim.
6. Wait for all three committed votes, then aggregate. A new candidate needs new fresh contexts for
   a genuinely blind first pass; reviewers that already know the intent cannot repeat it as blind.

Do not claim three different models unless the host actually used and exposed them. Three fresh
agents on one model can share biases. Independence records are procedural evidence; the helper
cannot enforce host isolation or prove that a visual claim is true.

## Commands and evidence

From the installed skill directory:

```bash
python3 scripts/panel_review.py seal --artifact /work/blind/image.png \
  --observations /work/a-blind.json /work/b-blind.json /work/c-blind.json \
  --generation-context ACTUAL_GENERATING_CONTEXT --output /work/seal.json
python3 scripts/panel_review.py aggregate --seal /work/seal.json --spec /work/brief.json \
  --votes /work/a-vote.json /work/b-vote.json /work/c-vote.json --output /work/panel-result.json
```

Omit generation-context for historical imports whose context ID is unavailable; the result reports
that limit. Do not invent it. Supply vote.seal_sha256 after sealing. Each vote records the review
path/hash, artifact and Spec hashes, context identity, time the Spec was received, and that peer
reviews remained hidden. Each artifact review uses the same identity_ref and its context ID as
session_ref, plus the actual artifact hash. All panel reviews have release_authorized=false.

The helper checks three distinct reviewers/contexts, matching inputs, time order, preserved first
impressions, review hashes, complete rubric coverage and explicit release boundaries. Its output
is created exclusively: use a new filename for a new decision instead of overwriting history.
The brief may be a bounded review brief; do not pretend it is a complete production Visual Spec.

## Count recommendations without erasing evidence

| Situation | Next action |
|---|---|
| Two or three same recommendations, no material conflicts | Adopt the majority as the proposed next action, retaining all dissent. |
| Any severity 2 or 3 finding | Verify the exact region/constraint first; a majority cannot erase it. |
| Three different recommendations | Resolve the named disagreement; defer taste to the user. |
| Missing reviewer, contaminated observation, changed input or incomplete rubric | Panel incomplete/invalid; do not count missing votes as approval. |

Severity follows [critique-protocol.md](critique-protocol.md). Taste disagreement is not a blocker.
A major finding needs a visible region, consequence, confidence and an alternative explanation.
The coordinator checks the original image or deterministic evidence before acting on a disputed
finding. A suspected defect can be rejected after verification; do not automatically regenerate
just because one reviewer raises it. Preserve the original panel and record any adjudication
separately. Corrected votes require traceable new records and a new aggregation, never silent edits.

`valid-panel` means evidence is structurally valid, not that the artwork is approved.
`accept` means recommend acceptance; it never substitutes for actual user acceptance or existing
release evidence gates. Register the panel as supporting evidence, not as a replacement for the
required artifact-review and user-decision records.

## Iterate within existing authorization

For a supported local-repair recommendation, the coordinator identifies the smallest change,
updates the parent-bound Feedback Delta, preserves strengths and approved decisions, and executes
within the current task's authorization and attempt budget. Do not ask again merely because a
panel was used. Inspect the actual result, compare against the parent, and convene fresh reviewers
when another panel is needed. Stop or change method after two non-improving rounds, when the
budget is exhausted, or when a higher-priority invariant would be damaged.

The result's automatic_execution_authorized=false means the report grants no *new* authority and
does not call a tool. Existing task authorization still applies. For a review-only task, report the
recommendation and leave the image intact.

Record lessons using [learning-and-memory.md](learning-and-memory.md). A majority opinion alone is
not proof of a general aesthetic rule or a user preference.
