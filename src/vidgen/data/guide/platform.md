<!-- topic: platform (also: level, levels, platformer, jumping, story-props) -->
## Platform stories: levels, jumps and story props

**When to make one.** A children's adventure where the hero *goes somewhere*: skips along the
grass, climbs a ladder, hops over a gap and up onto the clouds, finds a key for a locked gate,
meets someone grumpy in the way and asks nicely. It is a `stage` scene with a `level:` (a side
view drawn from a small map), so everything of `vidgen guide cartoons` still works: lip sync,
expressions, shots, the camera, sets, light, music. Keep a level to one part of the journey
(30–60 s, 8–12 beats) and use a few scenes for a 2–3 minute story.

**The map.** One line per row, top row first: `.` air, `#` ground, `=` a floating plank, `~` a
cloud (stand on it, jump up through it), `|` a ladder, `$` a coin and `*` a star (picked up when
the hero touches them, in the air too), and a **letter** for a *spot*: a place to stand, on the
first tile below the letter. Name the spots (`spots: {a: start, k: key_spot}`) and send every
move to a spot: it reads better than numbers and survives map edits. A character is two tiles
tall: leave two rows of air under a plank to walk under it.

**Moves.** `walk_to` / `run_to` go along the tiles (steps of one tile, ladders on the way,
never across a gap); `jump` with `to:` plans the arc itself (a crouch, the flight, a squash and a
little wobble on landing), at most 5 tiles across, 3 up and 8 down. `vidgen validate` replays
every move and says why one fails and what to write (`'nutmeg' cannot walk to spot 'far_side':
the way stops at map column 22: a gap at column 23; jump there instead`). A walk goes about 1.4
tiles a second (a ladder rung counts double): give each move a beat whose line lasts as long, or
`vidgen lint` warns `rushed_animation`; split a long way over two beats, or `run_to`.

**Story props.** A `door` prop is in the way until it opens; `locks: {gate: garden_key}` locks it
until the holder of the key prop stands next to it (`- open: gate, by: nutmeg`). `blockers:
[mossby]` puts a character in the way until `- step_aside: mossby` (after the line that asks it
nicely). `react: {when: pickup | land | arrive, expression, effect}` on a move puts the joy or
the surprise on the right frame. The sounds come by themselves (a boing, a soft landing, a coin's
pling, a star's twinkle, the unlock and the creak, the shuffle aside).

**Camera and size.** `level: {follow: nutmeg}` keeps the camera on the hero, gently, up and down
too. `character_size: small | medium | large` (top level or per scene) sets how big everyone is:
`medium` shows about 14 x 8 tiles in 16:9; use `large` for a 9:16 Short (a variant), whose
narrow frame shows about 6 x 10. A map must be at least as wide as the frame. For a dialogue,
cut to `shot: closeup <name>` or `two_shot`: small level characters' faces are hard to read
(`small_speaker` warns).

```yaml
characters:
  - {name: nutmeg, look: {species: mouse, proportions: kid, outfit: overalls}}
  - {name: mossby, look: {species: snail, eyes: oval}}
scenes:
  - id: garden
    type: stage
    set: park                       # its sky, hills, light and birdsong; not its props
    params:
      props:
        - {prop: door, name: gate, at: gate_spot}
        - {prop: key, name: garden_key, at: start}
      level:
        map: |
          ..............................
          ...................*..........
          ..a..gd..s..m...b....l...$$.e.
          #################....#########
        spots: {a: start, g: near_gate, d: gate_spot, s: stop, m: path, b: brink, l: over, e: end}
        locks: {gate: garden_key}
        blockers: [mossby]
        follow: nutmeg
      characters: [{name: nutmeg, at: start}, {name: mossby, at: path, facing: left, expression: angry}]
    beats:
      - text: "Nutmeg carried the golden key to the garden gate."
        actions: [{hold: nutmeg, to: garden_key, at: 0}, {walk_to: nutmeg, to: near_gate, at: 0.3}]
      - text: "Click, went the key. And creak, went the little gate."
        actions: [{open: gate, by: nutmeg, at: 0.2}]
      - text: "But Mister Mossby, the grumpiest snail in the garden, sat on the path."
        actions: [{walk_to: nutmeg, to: stop, at: 0.1}, {react: nutmeg, expression: surprised, at: 0.8}]
      - text: "Please, Mister Mossby, may I pass?"
        shot: closeup nutmeg
      - text: "Well, since you asked so nicely, he smiled, and shuffled aside."
        actions: [{emote: mossby, to: happy, at: 0.2}, {step_aside: mossby, at: 0.5}]
      - text: "Nutmeg ran to the edge, then jumped, and caught a star in the air!"
        actions:
          - {run_to: nutmeg, to: brink, at: 0.05}
          - {jump: nutmeg, to: over, at: 0.5, react: {when: land, expression: laughing, effect: sparkle}}
```

**From a screenplay**: put the level in a set of the front matter (`sets: {meadow: {level:
{map: ..., spots: ...}}}`) and start the scene's `set:` line with it (`set: meadow; characters:
nutmeg at start`); spots are marks there, and `[Nutmeg jumps onto over.]` is a jump.

A whole story: `examples/platform-story` (three levels, a key and a gate, coins and stars, a
grumpy snail, clouds up to a picnic, a 9:16 variant). Every key: `docs/CONFIG.md` "Platform levels
(`level`)" and the sections after it.

