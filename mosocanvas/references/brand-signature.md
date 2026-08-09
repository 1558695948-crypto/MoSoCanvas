# MoSo brand signature

The approved default signature is `MoSo 回声笔迹`, asset ID
`moso-echo-signature-v1`. Its canonical assets and machine-readable rules live in
`../assets/brand/`.

## Apply deterministically

- Add the signature after image generation and after the final crop is frozen.
- Use the canonical SVG markup stored in the `.xml` assets. Render it deterministically to a
  transparent raster only when the compositor requires one. The vector source depends on
  `SignPainter-HouseScript Regular`; never replace a missing font by generative redrawing.
- Prefer the bottom-right corner. Move to bottom-left only when the preferred corner contains a
  face, required copy, high-contrast narrative evidence, or the dominant visual exit.
- Choose the dark variant on light or warm mid-value fields and the light variant on dark fields.
  Inspect the actual local background; do not choose from the overall image average.
- Keep visible signature width between 4% and 5% of the final canvas width, with 4.5% preferred.
- Keep the nearest edge margin between 2.25% and 3.5% of the relevant canvas dimension, with 2.75%
  preferred.
- Use 60%–70% opacity, with 66% preferred. Reduce or relocate the mark if it competes at thumbnail
  scale; do not solve competition by shrinking below legibility.

## Preserve the mark

Do not regenerate, trace, stretch, rotate, outline, shadow, glow, or freely recolor the signature.
Do not place it during generative synthesis. Never allow it to cover a face, required text, or
narrative evidence.

Apply it by default to final MoSo-authored social images and series unless the user requests a clean
master, a client brand system prohibits secondary marks, or the carrier explicitly disallows marks.
When useful, retain an unsigned archival master alongside the signed delivery.
