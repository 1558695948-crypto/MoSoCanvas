# Preservation and Repair

Load this file before modifying an accepted artifact or claiming that a repair preserved approved
content.

## Freeze checkpoints, not methods

- Keep the original and every user-approved checkpoint immutable.
- Give each candidate a parent reference and change reason.
- Record source dimensions and hash when available.
- Freeze approved decisions, relationships, and pixels where required; allow the execution method
  to change when evidence supports it.
- Do not confuse “latest” with “best.” Promote a candidate only after verification and user
  acceptance.

Repeated repair is valuable when it preserves decisions and produces measurable improvement.
Repeated full-frame synthesis is risky because a prompt-scoped request does not protect non-target
pixels. Raw child-to-parent chaining also lets generated microstructure enter the next conditioning
input. Keep a persistent clean anchor, explicit patch dependencies, lineage, and verification rather
than using a universal repair-count limit. Follow
[non-destructive-editing.md](non-destructive-editing.md) for the executable workflow.

## Choose the parent deliberately

Choose among:

1. **Last accepted checkpoint:** use when it is clean and the new change depends on its accepted
   improvement.
2. **Earlier clean checkpoint:** use when the latest branch accumulated non-target drift or when
   the new change is independent.
3. **Frozen Visual Spec:** regenerate a new branch when composition, material system, or subject
   must be rebuilt.

Conditioning V3 on V2 is allowed only when V2 is accepted, the next repair truly depends on its local
change, and that operation ID is explicit in the new plan. A later commit may still preserve other
accepted patches on the canvas without showing them to the model. Branch from the clean anchor when
the previous edit failed or added unrelated damage.

## Route by operation and risk

| Operation | Preferred method | Default verification |
|---|---|---|
| exact text, logo, crop, color, size | deterministic layout/compositing | dimensions, glyphs, pixel bounds |
| remove or replace a local object | mask/region edit | mask preview, outside-mask comparison |
| local pose, light, or material | masked generative edit | semantic review plus protected-region drift |
| new composition or global material system | full regeneration from Visual Spec | spec-based visual review |
| uncertain locality | branch or handoff | state preservation as unverified |

For organic-surface artifacts, also load [texture-integrity.md](texture-integrity.md).

## Write a repair contract

```yaml
parent_ref: <immutable asset or accepted checkpoint>
target: <region, object, or property>
observed_problem: <fact, not causal speculation>
allowed_changes: [<specific properties>]
preserve: [<identity, pixels, text, layout, lighting, approved content>]
method: deterministic|masked-generative|full-regeneration|handoff
pass_conditions: [<observable checks>]
verification: pixel-diff|perceptual-diff|visual-only|user-judgment
```

Expand scope or attempt budget only after reporting why it is useful and what new risk it creates.

## Inspect at the right scales

1. **Use scale:** thumbnail, feed, poster distance, packaging shelf, or physical mockup.
2. **Detail scale:** 100%; use 200% for identity, hands, small type, logos, repeated patterns, or
   multi-round generative edits.

Record these separately:

- use-scale function;
- detail-scale technical risk;
- protected-region drift;
- trend versus the parent and earlier checkpoints.

A defect visible only at 200% is not automatically a product failure. Escalate when it affects the
real carrier, violates a production requirement, spreads across rounds, or predicts downstream
failure such as print enlargement.

## Verify preservation

When tools allow:

- compare dimensions, format, color mode, and alpha;
- compute changed-pixel bounds for lossless operations;
- compare protected pixels or perceptual distance with a declared tolerance;
- inspect semantic identity separately from pixel difference;
- store evidence with the source, candidate, and parent relationship.

Pixel equality is inappropriate after compression or color-profile conversion. Perceptual
similarity is not proof of exact preservation.

## Executable pixel boundary

`composite_region.py` accepts an explicitly prepared RGB/RGBA source and crop. The local mask is
grayscale coverage: white replaces, black protects, gray blends all RGBA channels. It is not the
transparent-alpha convention of an API mask. Source coordinates must have EXIF orientation already
normalized. Convert palette/CMYK images explicitly before freezing the parent and selecting a mask.

The helper outputs PNG, retains source alpha and ICC, rejects out-of-bounds crops, conflicting
embedded ICC profiles, and attempts to overwrite inputs. An untagged crop uses the source's color
interpretation; normalize it first when that assumption is not valid. Other metadata preservation
is not guaranteed. Keep the accepted parent immutable.

```bash
python3 scripts/composite_region.py parent.png crop.png coverage.png \
  --crop-origin 120,240 --output repaired.png
python3 scripts/verify_mask_preservation.py parent.png repaired.png coverage.png \
  --mask-origin 120,240 --output preservation.json
```

Verification compares decoded RGBA samples where coverage is zero, checks ICC identity, and binds
source/candidate/mask file hashes. A full-white mask proves no protected region and is blocked.
`status: pass` means those specific samples and ICC were preserved; it does not prove that the mask
was correctly chosen, the semantic change succeeded, or the image is attractive.

Attach an explicit check to run state when claiming exact preservation:

```json
{
  "source_ref": "parent.png",
  "candidate_ref": "repaired.png",
  "mask_ref": "coverage.png",
  "mask_origin": [120, 240],
  "report_ref": "preservation.json"
}
```

Place this in `preservation_checks`. The preflight validator recomputes measurements and checks
hashes instead of trusting a stored pass. Use `method: "decoded-rgba-and-icc"` in the corresponding
verification entry and bind its `evidence_ref` to the report. The claim applies only to the named
candidate. At acceptance, replace paths with evidence IDs: source/candidate are artifacts; mask and
report use kind `other`. Native Canvas coordinates or a semantic local edit provide localization
intent only; a preservation guarantee still requires the measured candidate.

## Track quality debt

Use four states:

| State | Use scale | Detail scale | Trend | Decision |
|---|---|---|---|---|
| safe | passes | minor | stable | continue |
| watch | passes | visible risk | stable | continue with evidence |
| warning | weakening | material risk | worsening | branch or change method |
| block | fails | severe | spreading or damaging | stop this branch |

Do not promote a technically cleaner result that loses a more important identity, narrative,
hierarchy, or material quality.

## Stop or branch

Stop the current method when:

- hard constraints pass and the user accepts remaining tradeoffs;
- two consecutive rounds fail the predefined criterion;
- new damage appears outside the target;
- quality debt increases across accepted checkpoints;
- a deterministic tool, authoritative asset, or real selection is required but unavailable;
- the change has become a new direction rather than a repair.

Preserve useful checkpoints. Explain whether the next action is a new parent, a new method, a new
direction, or a handoff.
