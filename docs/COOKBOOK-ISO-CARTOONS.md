# Isometric cartoons: framing the place

Craft notes for `stage` scenes with an `iso:` place. The author guide (`AGENTS.md`) says what the
iso features are; this page is about making the picture *work*.

## Ground that fills the frame (no floating tile)

A small map in the wide view reads as a diorama floating in empty space. That can be a deliberate
look (a dollhouse room, a toy village); when you want the ground to fill the frame instead, size
the map for the format. Measured on outdoor places at preview size (background share of the
frame, and a character's height as a share of the frame height):

| format | map | `wide` | background | character |
|---|---|---|---|---|
| 16:9 | any size | `auto` / `fill` | 55–65 % (diorama) | 0.09–0.33 |
| 16:9 | 16×16 | `2.5` | about 7 % (top and sides) | 0.28 |
| 16:9 | **24×24** | **`2.5`** | **about 2 % (two top corners)** | **0.20** |
| 16:9 | 32×32 | `2.5` | under 0.5 % | 0.16 |
| 9:16 | any size | `auto` … `2.5` | 30–85 % | 0.07–0.26 |
| 9:16 | 16×16 | `shot: medium` | 0 % | 0.33 |

- **16:9:** a square map of **24×24 with `iso: {wide: 2.5}`** fills the frame (only two thin top
  corners show); 32×32 hides them. A character is then about 4.6 ÷ N of the frame height, so
  bigger maps mean smaller characters: 20×20 to 24×24 is the comfortable middle.
- **9:16:** no `wide` value fills a portrait frame today (the zoom stops at 2.5; portrait needs
  about 5). Open on `shot: medium` / `closeup` or a `zoom`/`pan` onto the action for full-frame
  ground, and keep the wide view for a short establishing beat.
- **Keep maps square.** Only the shorter side counts: a 16×8 map frames like 8×8, and the extra
  length only makes the default view emptier.
- **Keep the action in the middle**, about 9–12 cells from every edge in 16:9. The wide view
  centres a little above the ground, so the top corners are the first to show.
- **Indoors**, rooms are dioramas by design (the front walls are cut away). In 16:9 a 12×8 room at
  `wide: 2.0`–`2.5` nearly fills the frame (a character about 0.40); in 9:16 use shots.
- **When corners do show**, give the stage a `background` sky (a gradient for day, dark blue for
  night) so they read as sky, not as a void.
- **To check a frame**, render a still with `background: "#FF00FF"`: any magenta left is ground
  that does not reach the edge.
