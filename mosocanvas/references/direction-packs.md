# Optional direction packs

A pack provides starting decisions for a named viewer relationship. It must not displace the user's
subject, medium, composition, palette, accepted layout or established visual identity. Do not apply
it to an accepted image repair. For a clear single-image request, selection is optional.

The initial original pack is [editorial-depth](../directions/editorial-depth.json), derived from
MoSoCanvas's [visual narrative](visual-narrative.md), [shot grammar](shot-composition-grammar.md)
and [color/light script](color-and-light-script.md). It is organized around reading an event:

| Variant | Viewer relation | Observable check |
|---|---|---|
| `witness` | Watch an action from a situated edge | First read carries the action; a related clue appears later. |
| `address` | Receive a gaze, gesture or object | The spatial relation addresses the viewer without anatomical distortion. |
| `aftermath` | Infer an event through physical traces | Related contact, displacement or use traces support one event. |

Set `generation.direction` to `{"id":"editorial-depth","variant":"aftermath"}`. Explicit
`generation.medium`, `composition` and `color_light` override their respective defaults. The
compiler records exactly which defaults were used. Each pack has provenance, version, appropriate
uses, exclusions and verification conditions. It has no borrowed palette table or fixed print formula.

Preview spatial alternatives from the installed skill directory:

```bash
python3 scripts/build_direction_board.py --pack editorial-depth --output /path/to/work/directions.png
```

The board renders simple geometry from the catalog's current variant IDs. It is a composition
diagram, not AI-generated artwork, evidence of rendering quality or a proof for the user's hero
image. A task-specific mass map must still reflect its actual subject, carrier, crop and safe zones.
The [single-image example](../examples/editorial-depth-spec.example.json) demonstrates an original
brief and explicit overrides. Its title requires later deterministic typesetting.

Add packs only after a recurrent user need is demonstrated. Author their text and examples from
MoSoCanvas's own practice; document any permitted external source explicitly. Schema validation and
composition diagrams do not establish that a pack improves preference or reduces revision cost.
