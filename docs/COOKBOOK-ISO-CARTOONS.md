# Isometric cartoons: framing the place

Craft notes for `stage` scenes with an `iso:` place. The author guide (`AGENTS.md`) says what the
iso features are; this page is about making the picture *work*.

## Ground that fills the frame (no floating tile)

The default wide view (`wide: auto` / `fill`) fits the whole place: its *bounding box* fills the
frame, so outdoors about half of the frame is background around a diamond of ground, and a
bigger map only pulls the camera back. That can be a deliberate look (a dollhouse room, a toy
village). For ground to the frame's edges use the **fixed view** and a **big enough map**:

```yaml
character_size: medium            # the video's; a scene may give its own
scenes:
  - id: green
    type: stage
    params: {background: ["#9CCBEA", "#E4F3FB"], iso: {wide: fixed, map: ...}}   # 24 x 24 in 16:9
```

`wide: fixed` keeps one scale whatever the map's size, set by `character_size` (or `wide:
{tiles: N}`: N tile widths across the frame). Measured on outdoor places at preview size: the
smallest square map with no background left, and a character's height as a share of the frame
height:

| format | `small` | `medium` | `large` |
|---|---|---|---|
| 16:9 | **34 x 34** (char 0.15) | **24 x 24** (char 0.21) | **17 x 17** (char 0.29) |
| 9:16 | **23 x 23** (char 0.15) | **16 x 16** (char 0.21) | **12 x 12** (char 0.29) |

- **Bigger is fine.** The characters keep their size on a bigger map; the camera shows the part
  where they stand. One size smaller leaves thin corners (20 x 20 in 16:9 medium: 2.5 %).
- **Keep maps square.** The shorter side counts: a 24 x 12 map in 16:9 medium is centred on its
  short axis and shows background on two sides (21 %).
- **The view centres on the characters**, moved onto the ground as far as the map allows. A
  character within about a view of an edge is still shown: the background shows beyond it
  there. Keep the action a few cells from the edges, or give a sky `background`.
- **Rooms** work the same: a 24 x 24 room fills 16:9 at medium, 16 x 16 fills 9:16; a 12 x 8
  room stays a dollhouse (about 60 % background in 16:9).
- **Moves** keep working: `zoom: {scale: 2}` is twice as close as the fixed view, close-ups and
  `follow` zoom in from it, and a `follow` or `pan` stays on the ground as far as its target
  allows (a pan to a spot by the map's corner shows the background beyond it).
- **Lint** `iso_ground` warns when a fixed view's map is too small and names the size (an info
  hint for outdoor places in the whole-place view).
- **To check a frame**, render a still with `background: "#FF00FF"`: any magenta left is ground
  that does not reach the edge.
