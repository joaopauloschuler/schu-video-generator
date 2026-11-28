<!-- topic: iso (also: isometric, village, villages, iso-place) -->
## Isometric places: villages and rooms for a story

**When to make one.** A children's story that happens *in a place*: a village green with houses,
a well and a bridge over a stream, a garden, a room. The place is seen from above at an angle
(isometric, no perspective) and each scene starts on a wide view of it (in 16:9 every spot and
object you placed; in 9:16 the part where the characters stand), so the viewer knows where
everyone is. It is a `stage` scene with an `iso:` place, so everything of `vidgen guide cartoons`
still works: the characters are the same flat cut-outs (lip sync, expressions, gestures), shots,
the camera, sets, light, music. No jumping or gravity here (that is a platform `level`).

**The map.** One line per row, the top line furthest back: `.` grass (boards indoors), `:` a
path, `~` water, `#` a wall, `+` a door, `%` a window, `1`–`9` a raised block (steps of half a
tile; walkers go up one step at a time), `@` a tree, `&` a bush, `*` flowers, `=` a fence, `-`
outside the place, and a **letter** for a *spot*. Name the spots (`spots: {w: well, d: door}`)
and stand characters, small things and objects at them. `objects:` adds ready-made things at a
spot or `{column, row}`: `house`, `tree`, `lamp`, `well`, `bench`, `bridge` (over `~`, walked on),
`flowers`, `sign` (`size: [3, 2]`: a flower bed; a larger `bush` is a hedge); indoors (`place: indoor`, the front walls cut away like a dollhouse) `table`,
`chair`, `bed`, `sofa`, `shelf`, `plant`, `rug`. Put a place used by several scenes in `sets:`
and give each scene `set: village`.

**Telling the story clearly.**
- Each scene starts on the wide view; move the camera only when it helps: `shot: closeup
  <name>` or `two_shot` for a line, `follow: <name>` for a long walk, `zoom: [rowan, lamp]` or
  `- {action: pan, to: well}` (it moves in) to point at something, `shot: wide` to see everyone
  again.
- Give every character its own voice (`voices:` with a `label`): in a wide view the speaker gets a
  **name tag** with that label; without a voice of its own a character lip-syncs the narrator.
  A tagged speaker may say up to 12 words in a wide view; longer lines need a shot.
- Moves go round what is in the way: `walk_to` / `run_to` a spot, `meet` (two walk to each
  other), `after: hazel` (follows), `wander`, `enter` / `exit` over the edge or `door:` a spot
  (a house's door; `open` it first: a closed door does not stop anyone). Two walks at the same
  time do not avoid each other: time crossing walks apart. Give a walk a beat whose line lasts as long as the way (`rushed_animation`
  warns otherwise), and keep the camera on it (`offscreen_action` warns about a walk, a hand-over
  or a door the camera does not show).
- Cause and effect: `pick_up` / `give` / `put_down` small things (`key`, `gift`, `letter`,
  `flower`...) next to each other; `open` a house's door or flowers (they bloom), `switch_on` a
  lamp, `reveal` / `hide` an object (a bridge appears). Each has its sound by itself.
- Mood: `light: morning`, `sunset` (evening), `night` (a lit lamp and windows glow, and a lamp
  lights who stands next to it), and
  `particles: [rain]` (it darkens to an overcast tint by itself, unless the scene sets a `light`;
  drops land on roofs, crowns and the bridge, not under them; `{kind: rain, puddles: true}` grows
  puddles with ripples), `{kind: snow, settle: true}` (the ground, roofs and treetops turn white;
  `settled: 30` starts it white). A `run_to` leaves speed lines along its diagonal.
  Footsteps follow the ground (grass, path, boards, a bridge), birdsong by day, crickets at night.
- Science fiction and magic: a `portal` prop at a spot tears open with `switch_on` (a crackling,
  glowing rift; `switch_off` seals it); a character comes out of it with `- {enter: visitor,
  door: rift}` (the portal's spot) and walks to its own spot in front. A character with `hologram: true` is a glowing,
  translucent projection (an AI, a ghost) that no `light` darkens and that flickers now and then;
  give it an `effect: echo` on its voice. `- materialise: guide` makes it appear (a flickering
  wireframe, then solid; it waits unseen until then), `- dematerialise: guide` vanish.
- A lab: `objects` `console` (glowing screens; a `hologram_display` prop at its spot floats a
  panel of light over it: `pattern: fractal`, `data`, `text`, `equations` (formulas written, and
  formula butterflies fluttering up) or `timelines` (a branching tree, two figures meeting in a
  small panel at each tip; `scale: 1.5` to read them)), `server_rack` (blinking lights),
  `projector_pad` (a glowing platform a hologram stands on), `whiteboard`. A portal's `view:
  coast` (or `stars`, `meadow`) shows another place inside it. `- alarm: start` darkens the room
  under a pulsing red light with a siren (`stop` ends it), `- shutters: close` slams steel
  shutters over the windows; `ambience: hum` gives a lab its hum. Other objects: `laptop`
  (`open: false` closed), `terminal_kiosk`, `quantum_core`, `robot_arm`, `microscope`,
  `centrifuge`, `coffee_machine`, `lab_stool`, `wall_clock` (`at` a cell of a back wall,
  `time: "03:27"`), `grow_rack`, `terrarium`, `specimen_tank` (`color` its liquid; a `detail`
  colour adds a floating shape), `chemistry_bench` (2 x 1), `distillation_rig`, `lab_fridge`
  (`open`), `fume_hood`, `telescope`, `satellite_dish`, `charging_station`, `crate_stack`,
  `airlock` (2 x 1, `open`), `printer_3d`, `hazard_sign` (`kind: biohazard | radiation |
  authorised`), `fire_extinguisher`, `fireplace` (2 x 1), `kitchen_counter` (2 x 1), `stove`,
  `sink`, `bookshelf_tall`, `armchair`, `floor_lamp`, `tv`, `piano` (2 x 1), `bathtub` (2 x 1),
  `wardrobe` (2 x 1, `open`), `crib`, `cafe_table` (2 x 1, two chairs), `counter` (2 x 1),
  `cash_register`, `display_case` (2 x 1, `kind: cakes | jewels`), `market_stall` (2 x 1),
  `vending_machine`, `street_lamp`, `traffic_light`, `bus_stop` (2 x 1), `mailbox`, `fountain`
  (2 x 2), `phone_booth`, `car` (2 x 1, `color` its body), `bicycle`, `newsstand` (2 x 1),
  `campfire`, `tent` (2 x 2), `log` (2 x 1), `stump`, `mushroom_ring` (2 x 2), `pond` (2 x 2),
  `scarecrow`, `beehive`, `vegetable_patch` (2 x 1), `wheelbarrow`, `hay_bale` (2 x 1),
  `school_desk` (with its chair), `desk_with_pc` (2 x 1), `water_cooler`, `printer`, `globe`,
  `trophy_shelf` (2 x 1), `treasure_chest` (`open`: gold glows), `cauldron` (`color` its
  potion), `giant_crystal`, `throne`, `torch_sconce` (`at` a cell of a back wall), `signpost`,
  `archway` (2 x 1), `statue`, `christmas_tree`, `snowman`, `pumpkin`, `gift_pile`,
  `balloon_bunch`, `birthday_cake`, `boat` (2 x 1, on water `~` only), `dock` (1 x 2, over
  water, walked on), `lighthouse`, `train_car` (3 x 1), `rocket` (2 x 2); retro: `googie_building` (3 x 3: a boomerang roof, a starburst sign), `retro_tower` (2 x 2, round, a saucer deck; `height` 4-30), `starburst_sign`, `ray_lamp` (a ray-gun street lamp), `atomic_sculpture`, `monorail` (4 x 1, a beam on pylons; `size` makes it longer), `tube_computer` (2 x 1, tape reels, bulbs), `sunburst_clock` (`at` a cell of a back wall, `time`), `tv_console` (`kind: wave | face`), `retro_desk` (2 x 1, a terminal), `hedge` and `planter` (`size` makes them long), on a back wall's cell `poster` (`kind: rocket | atom | planet`) and `wall_shelf` (books, a plant); a `car` takes `kind: rocket` (tail fins, a bubble canopy); `on: true` /
  `switch_on` makes the laptop, kiosk, core, arm,
  centrifuge, coffee machine, rack, tank, bench, rig, fridge, hood, dish, charging station,
  airlock (its beacon), 3D printer, fireplace, stove, floor lamp, TV, vending machine, street
  lamp, traffic light (cycles), fountain, phone booth, car (headlights), campfire, pond
  (ripples), beehive (bees), desk_with_pc (its screen), water cooler (bubbles), printer
  (prints), globe (spins), cauldron (bubbles), giant crystal (glows), torch sconce, Christmas
  tree (twinkles), pumpkin, balloons (sway), cake (candles), boat (bobs), lighthouse (its beam
  sweeps), rocket (fires) and the retro lights and machines work (a lit fireplace, floor lamp, street lamp, phone booth,
  campfire, cauldron or torch lights who stands near; pools of light and beams show mostly at
  night).
- Vehicles move: `- {drive_to: car, to: shop, via: [corner]}` drives a `car` along the path
  cells (`:`), turning at corners (driving away its tail shows; `switch_on` its headlights);
  `- {sail_to: boat, to: pier}` sails a `boat` across `~`; `drive_to` rolls a `train_car` along
  its row or column (its track is drawn there) until its middle is at `to`; `- lift_off: rocket`
  fires and rises out of the view. `speed` in tiles per second; `follow: car` keeps the camera on
  it; give the beat time for the way; `vidgen validate` names what is in the way.
- Furniture: walk next to an object, then `- {sit_on: pip, to: armchair}` (chair, bench, sofa,
  armchair, throne, lab_stool, log, stump, hay_bale, rock, bus_stop, cafe_table: two face each
  other, school_desk, bed), `- {lie_on: pip, to: bed}`, `- {use: pip, to: laptop, run_time: 4}`
  (types; warms its hands at a campfire or fireplace, takes a book from shelves, presses at a
  machine or stove), `- stand_up: pip`. A seat faces out of the object's front (set its
  `facing`); its near arm, a chair's back or a blanket is drawn over the sitter. Talking, faces
  and looks work seated; walk only after `stand_up`.
- Visitors: `iridescent: true` (skin shifting colours like oil on water, partly self-lit:
  `{glow: 0–1}`, default 0.5) and `afterimages: true` (faint copies trailing a move) on a
  character, a `scale` of 1.5–1.8 on the stage to tower over the others (check it in a
  `two_shot` with a human). Two characters `- {hold_hands: ana, with: ben}` step in close
  enough for the joined hands to show; walk both in one beat with the same `run_time` and they
  go side by side (`let_go_hands`). At night give the stage `fill_light: 0.4` so faces read.
- Ground to the frame's edges: the default wide view fits the whole place (its bounding box), so
  outdoors about half of the frame is background, and a bigger map only pulls the camera back.
  `iso: {wide: fixed}` keeps one scale instead (a character 0.14 / 0.20 / 0.28 of the frame's
  height at `character_size` small / medium / large, which an iso place takes with `wide:
  fixed`; or `wide: {tiles: N}` across), centred on the characters as far as the ground goes:
  a big enough map fills the frame. Square maps of at least 24x24 (16:9) or 16x16 (9:16) at
  medium; 34 / 23 small, 17 / 12 large. Lint `iso_ground` names the size; `zoom: {scale: 2}` is
  then twice as close as that view.
- Framing: `iso: {wide: fill}` (or a number 1–2.5) brings a room's wide view closer;
  `shot: closeup ana ben` frames two faces together, `{kind: closeup, of: guide, clear: true}`
  hides everyone else for the beat. A memory: `flashback: true` on a stage (faded warm colours,
  a soft vignette), with `flower_arch` and `chess_table` objects, and an iris in and out.
- A city at night: `objects` `tower` (`height` 2–30 tiles, `size` its footprint; lit window
  grids, neon trims in `detail`, a blinking antenna; `screen: true` a crawling info screen,
  `garden: true` glowing algae bands) on the blocks between path streets, `light: night`, and
  `traffic: [{from: west, to: east, height: 3, count: 3, seconds: 7, color: "#FF2E8B"}]` under
  `iso:` for hover pods gliding over the streets (`at: 1.0` with `count: 1`: one pod crosses once;
  a `pan` to the end spot with the same `run_time` follows it). `wide: 1.6`–`2.5` lets the towers
  reach out of the top of the frame. Neon rain: `particles: [{kind: rain, glow: true, color:
  ["#5FFFE0", "#4FA8FF"]}]` (`glow` works on any particles).
- Weather outdoors: rain with `puddles: true, settled: 12` (puddles full size from the start)
  mirrors lit windows, lanterns and neon trims at night, wobbling while it rains; `fog: 0.6`
  lies over the place in drifting bands, thicker further back; `wind: windy` (or `- wind:
  gale`) bends trees, bushes, flowers and plants in gusts, swings scarecrows and balloon bunches
  (on their strings) and slants the rain. All fade with `time_of_day`.
- Life in the background: `ambient: {walkers: 3, birds: 4, cat: true, butterflies: true,
  fireflies: true, seed: 1}` on the stage (or `ambient: true`; also `ducks` on `~`, `flies`):
  passers-by stroll the paths, birds peck and fly off, a cat sits and grooms, butterflies by day,
  fireflies at night. They keep away from the characters, never speak, are no targets and hide
  in close shots; walkers are `muted` (smaller, greyer) unless `muted: false`, and lamps light
  them at night. Indoors a cat and
  flies only. They add render time: a handful is enough.
- Other selves: a character with `echo: true` (or `{color, opacity}`) is a translucent other
  self that keeps its own costume, its outlines glowing (a timeline, a memory, a dream); stand
  it beside the one it echoes and bring it with `- materialise: ana_captain`. Accessories
  `medal` (gold, on a ribbon in `colors.accessory`) and `pendant` (a stone glowing and pulsing in
  `colors.accessory`, bright at night) dress a laureate or a keeper of a secret.
- Romance: `- {kiss: ana, with: ben, run_time: 3}` (two standing a step apart: they turn, lean in
  until their faces touch, close their eyes, a small burst of hearts and sparkles, then lean
  back); frame it with a `two_shot`. It lets go of held hands first. Stand a pair side by side on
  the picture: cells on a diagonal of the map (`{column: 5, row: 6}` and `{column: 6, row: 5}`)
  are at the same height on screen. Actions of a beat at different `at` play one after another,
  so two couples kissing at once share one `at`. Long hair that reads in a close-up: `hair: wavy`.
- A retro-future world (1950s "world of tomorrow"): `iso: {style: retro}` gives the place pastel
  ground and objects (mint lawn, cream checker paths, terrazzo floors, turquoise walls; your
  `colors` / `textures` / an object's `color` win); `textures: {path: checker, floor: terrazzo,
  grass: lawn}` work on any place. A night that stays bright and crisp: `light: blue_hour` (colours
  keep their hues, clean contrast) with the lights `on: true`, `fill_light: 0.6` and `fill_color:
  "#FFE2BC"` (a warm key on faces) and a deep sky `background`, e.g. `["#1B2A6B", "#2E8FA8"]`.
  Traffic as saucers or a train on a `monorail` beam: `traffic: [{..., shape: saucer | monorail}]`
  (a monorail lane at `height: 3.15` over the beam's row). Retro looks: `outfit: suit | lab_coat |
  jumpsuit`, `hair: pompadour | bob`, `accessories: [fedora]` or `[pillbox]`; `eyes: bright` (clear
  whites, a fine rim, catchlights) keeps faces friendly in close-ups and at night.
- Rooms that feel like rooms: `iso: {wide: fixed, show_walls: true}` frames a room from its back
  corner so its standing walls fill the top of the frame; stage the action within a few rows of
  the back walls (`character_size: large`), hang `poster`, `wall_shelf`, `sunburst_clock` on wall
  cells next to windows `%`, and crowd the floor round the characters: rugs, plants, lamps, desks.
- A strange door: `iso: {doors: slide}` (steel doors sliding open with a hiss on `- open:
  door_1`) and `haze: [{at: door_in}]` (shimmering air with sparkles over a spot). A room at
  night: dark `colors: {wall, floor}`, `light: night`, `fill_light: 0.45` and `wall_lights:
  ["#5FE8FF", "#FF2E8B"]` (neon strips along its walls).
- Inside someone's head: a scene's `overlays: {implant: {type: hud, at: office_b2, duration: 6,
  alert: "INCOMING ALERT", lines: ["SIGNAL: SECTOR 7"], heart: {bpm: 70, to: 128, at: 1.5,
  skips: 3}, scan: {level: 0.4, to: 1.6, at: 3}}}` draws a HUD over the frame (brackets, a
  blinking alert, readouts, a heart monitor, a scanner meter spiking off its scale).

```yaml
characters:
  - {name: hazel, voice: hazel_voice, look: {species: rabbit, proportions: kid, outfit: dress}}
  - {name: juno, voice: juno_voice, look: {species: bird, proportions: kid}}
voice: {provider: kokoro, voice: bf_emma}          # the narrator
voices:
  hazel_voice: {voice: af_bella, label: Hazel, color: primary}
  juno_voice: {voice: af_heart, label: Juno, color: accent}
scenes:
  - id: green
    type: stage
    params:
      background: ["#9CCBEA", "#E4F3FB"]
      light: sunset
      iso:
        map: |
          -.@......~~...
          ..h......~~...
          ...a..l..~~.y.
          .::::::::~~:..
          ....f....~~...
        spots: {h: home, a: door, l: lamp, f: garden, y: far_bank}
        objects:
          - {object: house, at: home}
          - {object: lamp, at: lamp}
          - {object: bridge, at: {column: 10, row: 4}, facing: right, size: [2, 1]}
          - {object: flowers, name: flower_bed, at: garden, open: false}
      props: [{prop: key, at: door}]
      characters: [{name: hazel, at: door}, {name: juno, at: far_bank}]
    beats:
      - text: "In the evening, Hazel picked up the lamp key and ran to the lamp."
        actions:
          - {pick_up: hazel, to: key, at: 0.2}
          - {run_to: hazel, to: lamp, at: 0.45}
      - text: "Click! The lamp lit up, and Juno could see the bridge."
        actions: [{switch_on: lamp, at: "@Click"}, {walk_to: juno, to: lamp, at: 0.3}]
      - text: "Thank you, Hazel!"
        voice: juno_voice
        shot: two_shot juno hazel
```

`vidgen validate` replays every move and hand-over and names what is in the way (without the bridge:
`'juno' cannot walk from row 3, column 13 to 'lamp': the way stops at row 4, column 12: water (a
bridge crosses it) at row 4, column 11`). A whole story: `examples/iso-story` (a village by a stream and a room,
a key, a lamp lit in the rain, flowers that bloom, a 9:16 variant). Every key: `docs/CONFIG.md`
"Isometric places (`iso`)".

