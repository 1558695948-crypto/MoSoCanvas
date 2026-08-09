# Same-backend contribution ablation

This experiment answers a narrower question than the external quality benchmark: does the
MoSoCanvas workflow improve outcomes when the image backend itself is held constant?

## Conditions

- `B0-direct`: execute the user's original brief directly with the same backend.
- `B1-generic-clarify`: allow ordinary high-value clarification and a competent generic prompt,
  but do not load MoSoCanvas schemas, critique rules, preservation gates, or repair loop.
- `M0-mosocanvas`: use the released MoSoCanvas package and its normal gates.

Do not weaken the baselines, reveal condition names to raters, or let one condition receive more
generation calls, source assets, manual curation, or hidden design help.

## What to record

For every task and condition, retain the frozen brief, artifact, backend/model version, generation
calls, elapsed time, acceptance, rounds to acceptance, material user corrections, protected
decision losses, and severity-3 defects. Ask the user for analysis usefulness and interaction
friction only when they experienced that condition; missing ratings remain null.

Run blind pairwise artifact preference separately. Preference measures output selection, while the
operational fields measure control, repair cost, and friction. Never collapse them into one score.

## Interpretation

- Fewer corrections without higher acceptance is not an improvement.
- Higher blind preference with materially higher time or friction is a trade-off, not a clean win.
- Better acceptance with more protected-decision loss contradicts the minimum-change promise.
- Self-review, one hero image, or comparisons across different model versions cannot establish
  contribution.

Use 5–10 tasks only as an instrumentation pilot. Require at least 20 matched tasks, at least three
independent raters, more than one task class, and task-level reporting before a directional product
claim. A publishable causal claim needs repeated runs and appropriate statistical review beyond
this Skill's built-in summary.

Use [skill-ablation-study.schema.json](../schemas/skill-ablation-study.schema.json) and summarize it
with [ablation_score.py](../scripts/ablation_score.py).
