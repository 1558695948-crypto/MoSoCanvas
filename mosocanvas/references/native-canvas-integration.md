# Codex native image Canvas integration

Use Codex Image Canvas as the review and feedback surface. Do not describe it as a structured
editing API unless the current host actually exposes selection geometry to the agent.

## Translate host actions

| Canvas action | MoSoCanvas meaning |
|---|---|
| Focused-view comment | one artifact-bound observation or correction |
| Multi-select comment | shared feedback that must be rebound separately to every edit parent |
| Multi-select without edit language | comparison or candidate selection, not an edit |
| “keep this” | preservation constraint or user-approved promotion |
| “change this area” | semantic locator unless coordinates or a mask are actually available |
| Accept/reject | user decision, not generator self-approval |

Create [native-canvas-feedback.schema.json](../schemas/native-canvas-feedback.schema.json) before
compiling an edit into one or more parent-bound Feedback Deltas.

## Bind before execution

1. Bind every selected image to an artifact reference and, when known, an attempt ID.
2. Classify the interaction as edit, compare, select, accept, or reject.
3. For an edit, name at least one `edit-parent`. Create a separate Feedback Delta for every parent;
   a multi-select comment is not one shared mutable state.
4. Use `semantic-local-edit` when the target is an object or named region but no geometry is
   available. Use `pixel-bounded-edit` only with a real mask or machine-readable geometry.
5. If the target image or intended region is ambiguous, ask one short clarification and block the
   generative call. Do not guess which thumbnail “this one” means.
6. Show the compact change/preserve/prohibit/relationship/pass contract before execution.

## Locator truthfulness

- `host-selection`: the user acted on a visible host selection. This does not prove that coordinates
  or a mask reached the Skill.
- `natural-language`: a semantic object or region such as “the cat's wings.”
- `grid-region`: a 3×3 fallback locator.
- `normalized-box` or `normalized-polygon`: coordinates in a 0–1000 space, confirmed by the user or
  produced by an actual annotation tool.
- `mask`: a resolvable mask artifact. This is the preferred basis for pixel-bounded repair.

When structured selection is unavailable, retain a fallback description and record the limitation.
Never derive a mask from the mere fact that the user commented in Canvas.

## Return to Canvas

After execution, inspect the actual artifact, bind it as a child attempt, and present it with the
parent for Canvas comparison. Record the target change and protected drift separately. If the user
comments again, start a new adapter record rather than overwriting the prior comment.

This adapter is procedural in a pure Skill. Hard interception, persistent region locks, and a true
version tree require a Plugin with an MCP App UI.
