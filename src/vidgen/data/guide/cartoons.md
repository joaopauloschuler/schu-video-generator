<!-- topic: cartoons (also: cartoon, characters, character, stage, dialogue, acting) -->
## Cartoons: characters on a stage

**When to make one.** When the idea has people in it: two points of view arguing it out, a
mistake and its fix, a story with a turn, a gentle explainer for beginners or children. A short
sketch also works as the hook of an explainer, before the charts. Not for numbers, code or
formulas: those have their own scene types, and a character pointing at a chart is slower than
the chart. Keep it small: 2–3 characters, one set per scene, 30–90 s.

**Original characters only.** Build them with the generator (`look:`) or from your own SVG
(`look: {svg: ...}`, `docs/CONFIG.md` "Characters"). Never imitate a known character, mascot,
brand figure or logo: not its silhouette and colours, its name or catchphrase, an SVG traced
from it, nor "in the style of" a studio in a `generate:` prompt or `cartoon_style`. If someone
asks for one, say schu-video-generator makes original characters and offer one with the same role.
- Tell them apart at a glance: a different `body` (`round`, `tall`, `pear`, `triangle`...),
  hair (`ponytail`, `braids`, `afro`, or bald with `facial_hair: beard`), one signature item
  each (`hat`, `cap`, `bow`, `scarf`, `glasses`, `backpack`...), an `outfit` (`dress`,
  `overalls`, `coat`, `shorts`, `apron`; second colour `colors.trim`) in different theme tokens,
  maybe a `pattern` (`stripes`, `dots`) or `shoes`. A good test: would the two silhouettes,
  filled black, still differ? A child: `proportions: kid` (or `tall_kid`) and a smaller `scale`
  on the stage (about 0.7). An animal: `species: cat | dog | bird | bear | rabbit | mouse |
  fox | owl | frog | turtle | penguin | snail` (fur colour `colors.skin`: natural tones or theme
  tokens, different for each; a turtle's or a snail's shell `colors.hair`; it gets a `tail`, not a
  frog or a snail; a turtle walks slowly, a snail more slowly still, a penguin waddles, a frog jumps higher). A robot: `species: robot` with `robot:
  {head: box | round, face: eyes | screen, antenna: true | false, moves_on: legs | wheels}` (no
  hair; plating `colors.skin`; a screen face shows its mouth shapes; on wheels it rolls; a
  `[beep]` in its lines). Costume pieces for anyone: `crown`, `wizard_hat`, `party_hat` (one
  thing on top of the head, like `hat` or `cap`) and a `cape` that trails in the wind
  (`docs/CONFIG.md` "Robots and costumes"). `vidgen character-sheet` shows every pose and the front view. `vidgen cast --random 4
  [--seed S] [--species cat dog]` writes a cast chosen to differ (looks, colours, voice kinds
  and voices, original names) for `include:`; lint `look_alike` warns when two look too alike.
- Arms: by default (`front`) both arms hang clear at the sides, the far arm drawn over the body;
  `cartoon_arms: classic` (or a look's `arms: classic`) keeps the older look, most of the side
  view's far arm hidden behind the body.
- Give each a want and a temper (the eager one, the doubter); their starting `pose` and
  `expression` say it before they speak. Short names, easy to say (the voice says them).
- One voice each (`voices:` + `characters[].voice`), clearly different; keep the narrator's
  voice for the few lines that set the scene.

**Staging.**
- **Marks**: two characters on `left` and `right` face each other (`facing: auto` turns them
  towards the stage's middle; on a wide stage, or with both on one side, set `facing`). A third
  goes at `centre` or further back. Keep characters at least a mark apart and the space above
  their heads free for speech bubbles.
- **Depth**: what matters stands in front (`depth: 0`); the set goes back (`depth: 0.5`–`0.8`:
  higher, smaller, behind; the `ground_color` band reaches up to the deepest of them). Nothing in
  front of a speaker's face (`hidden_speaker`). A character can walk in depth (`- {walk_to: kit,
  to: {mark: 0.6, depth: 0.7}}`: it shrinks and passes behind what it walks by) and come forward
  to speak (`depth: 0`). `facing: front` (or `- {turn: kit, to: front}`) turns a generated
  character to the viewer, for a line said to the audience; it turns back with `turn`.
- **The set**: things at the edges (a `house`, a `tree`), the middle free for the action.
  Props stay inside the frame: `far_left` / `far_right` cut a wide prop (`off_frame`). A
  drawn set is a gradient `background`, a `ground_color`, `layers` (`hills`) and props; a
  generated one (`generate:`) gets one top-level `cartoon_style` ("flat colours, thick outlines,
  soft shadows") so all stages match, and a prompt that describes a set, not a scene: things at
  the edges, an empty middle, the ground across the lower part, `negative: "people, animals,
  text"` (`docs/CONFIG.md` "Generated backgrounds").
- **Drawing style**: one top-level `drawing: {outline: thin | bold, shading: soft, texture:
  paper | storybook}` restyles every stage (a stage's own `drawing` wins key by key); the
  default draws as before; captions and overlays are never textured.
- **Room to move**: a walk takes the time its distance needs (about 4 s from `left` to `right`
  in 16:9), so give it a beat that long and end it on a free mark (`walk_overlap`). On a stage wider than
  the frame (`width: 2`), the camera goes along with `follow`.
- **Light and mood**: `light: morning | sunset | night | indoor` (or `{tint, strength}`) grades
  the whole set and the characters, never the bubbles or text; `night` adds stars on a colour
  background. Time passing is a `- light: night` action (it fades, 2 s), or a whole evening in
  one shot: `- {time_of_day: night, run_time: 6}` (the sky turns gold then dark, the lamps light
  themselves at dusk; `time_of_day: morning` puts them out again); `fill_light: 0.4` keeps
  the characters' faces readable in a dark light (the set stays dark). Characters and props on
  the ground get soft shadows on their own (`shadows: false` for none). `wind: breeze | windy |
  gale` (or 0..1; negative blows left) sways trees and bushes, makes scarves, long hair, ears and
  hats trail and particles drift; `- wind: gale` fades it in a beat. From `windy` on it shows
  clearly; add `particles: [leaves, streaks]` so it reads at once. `- blow_away: napkin` blows a
  light prop off the stage (or `to:` a mark), out of a hand too; the wind must blow then.
- **Rain**: `particles: [rain]` (or `- particles: rain` from a beat) on a stage ends on the
  ground with small splashes; an open umbrella (held or standing) and a tree's crown keep the
  rain off whoever stands under them; `{kind: rain, puddles: true}` grows puddles. A generated
  rain sound plays under it while it lasts, ducked less than music (off with `foley: false`).
- **Snow and fog**: `{kind: snow, settle: true}` lands on the ground and on the props, where a
  white layer grows (a blanket on the ground, caps on roofs, crowns, tables; full after 24 s at
  density 1; thin under trees and open umbrellas); `settled: 30` starts it already white. `fog:
  true` (or a density 0..1) lays fog in bands between the characters and props by depth: the
  further back, the more hidden; it drifts slowly and with the wind. Both outdoors only.
- **Storms, rainbows, sunsets**: `- lightning: right` flashes the set with a bolt there and plays
  `thunder` after it (`distance: 2` km: ~6 s later, quieter; in a room the windows flash); rain
  with `lightning: true` strikes every 8 s or so on its own. `- rainbow: centre` fades a rainbow in
  behind the hills (after the rain). With a `sun` (or `moon`) prop, `{light: sunset, move_sun:
  true, run_time: 4}` sinks the sun to the right while the light fades, the shadows stretching
  away from it; `night` sets it and raises the moon.
- **Indoors**: `room: {wallpaper: stripes, windows: [0.3], doors: [{at: 0.8}]}` (or `room:
  true`) replaces the sky and ground with a wall, a floor (`flooring: boards | tiles`) and a
  skirting board; windows show the sky of the stage's `light` (`indoor`: lamplight inside, evening
  outside; `- light: night` darkens it and brings out stars), doors are `door` props whose name is
  a mark: `- {enter: kit, door: door}` brings a character in through it, `exit` with `door:`
  takes it out. No wind, rain or snow inside; a set (`sets:`) can be a room. Furniture props:
  `sofa`, `armchair`, `bed`, `bookshelf`, `counter`, `fridge`, `picture`, `rug`, `houseplant`,
  `clock`, `tv`, `desk`; `{prop: sofa, at: 0.3, against: wall}` stands it at the wall's depth
  (`picture` and `clock` hang on the wall by themselves). Characters that sit on such furniture
  stand at the wall's depth too (`depth: 0.4`, or walk there: `- {walk_to: dot, to: {mark: 0.42,
  depth: 0.4}}`; `vidgen validate` says where); a sofa or a bed seats two.
- **Props that move by themselves**: `{prop: clock, time: "21:45"}` runs (`speed: 60` = a minute
  a second); `{prop: tv, on: true}` shows a flickering picture, `{prop: lamp, on: true}` glows;
  `- switch_on: lamp` / `- switch_off: tv` switch them in a beat (with a click). A lamp at
  `light: night` makes a warm spot, it does not light the whole room. A `fireplace` (furniture,
  `against: wall`) burns with flickering flames, a warm glow and a crackle while `on`; a `kettle`
  (on a `counter` with a `lift`) steams while `on`.
- **Nature that moves**: `{prop: tree, fruit: true}` carries fruits and `- drop_fruit: tree` (`to:
  pip` for a head, stars) lets one fall; `birds: true` (or `- birds: 4`) sends a flock across the
  sky (outdoors only).
- **Small props**: `cake`, `muffin`, `book`, `phone`, `letter`, `gift`, `balloons`, `vase`,
  `watering_can`, `flower` to hold, give and set on a table (`lift: 0.17` on a `table`). A book, a letter
  and a gift `open` / `close` like an umbrella (held in front, not overhead). A `phone` that is on
  rings (`on: true` or `- switch_on: phone`; it shakes in bursts with a trill, `- switch_off:
  phone` answers it). Held balloons rise behind the head; `- let_go: pip` floats them away for
  good. `- pour: kit` tilts the watering can kit holds and water drops fall. A `scanner` that is on
  shows a live readout (`scan: {level: 0.4, to: 1.6, at: 3}`: above 1 it goes off its scale,
  flashing red; `- {hold: max, to: scanner}` to carry it); `takeout` boxes and glowing data
  `crystal`s (`on: true`) clutter a desk.
- **Ready-made sets**: `set: city_street`, `park`, `beach`, `forest` or `snowy_hills` on a stage
  scene gives a whole outdoor set without `sets:` (backdrop, props, light, ambience: a street
  sounds like a city, a park and a forest have birdsong by day). Put two characters on its
  `stand_left` and `stand_right` marks (clear of the props; other marks: `bench`, `bus_stop`,
  `fountain`, `umbrella`, `log`...); the scene's params override it like any set (`light:
  sunset`, `props: [{name: shop_2, color: tertiary}]`, `props: []`). Their props work on any
  stage: `shop`, `bench` and `log` (sit two), `bus_stop`, `fountain`, `flowers`, `fence`,
  `beach_umbrella`, `shell`, `pine`, `mushroom`, and flat `road` / `path` bands.
- **Ready-made rooms**: `set: classroom`, `kitchen`, `shop`, `living_room` or `bedroom` gives a
  furnished room (a door, windows, daylight or lamplight, a room tone) with the same `stand_left` /
  `stand_right` marks. Furniture stands at the wall (depth 0.4): to sit or lean, walk there first
  (`- walk_to: pip, to: {mark: sofa, depth: 0.4}`, then `- sit_on: pip, to: sofa`); pupils' desks
  are at depth 0.25 (marks `pupil`, `pupil_2`), the kitchen table and chairs at 0.2. `light: day`
  for a daytime room. New props: `blackboard` (hangs on the wall), `school_desk` (with its chair:
  sit at it), `shelf_with_goods` and `wardrobe` (lean on them), `till` (`lift` it onto a counter).

**Shot variety.** Change the shot every few beats, as a comic changes panels. A beat's `shot:`
key cuts the camera to a framing of the characters for that beat; the next beat without one cuts
back (`shot: {kind: closeup, of: kit, move: true}` eases instead):
- **wide** (the whole stage, no `shot` or `shot: wide`): the first beat of a scene, entrances,
  anything two characters do together;
- **`two_shot`** (two characters, whole) and **`over_shoulder kit pip`** (kit seen past pip, who
  stands cut at the edge): a dialogue, alternating the speaker's over-the-shoulder shots;
- **`medium kit`** / **`closeup kit`** (hips up / head and shoulders): the punchline or the
  reaction to it; about one close-up per scene, or close-ups stop meaning anything. A `zoom`
  (`scale: 2`) pushes in and comes back within the beat instead of cutting;
- **moving**: `pan` to a character or a mark (`- {action: pan, to: right}`) and `follow` a
  character or a flying prop across a wide stage (either ends a shot).
A shot is framed where the characters stand as the beat starts and does not follow a walk.
In a 9:16 variant the camera follows the speaker across the landscape stage on its own
(`reframe`, see the `social` topic): write the dialogue for 16:9 and check `vidgen storyboard
--variant ...`.

**Reaction shots.** The listener's face is often the joke. While one character speaks, the other
`react`s (`expression` and / or `pose`, for that beat only) and `look_at`s the speaker; `emote` and
`pose` change them for good. A `shot: closeup` of the listener while the other talks is the
reaction shot. `look_at: camera` turns a character to the viewer for an aside. Put the reaction where it
happens: `at: 0.8` lands it on the end of the line, not on its first word.

**Expressions.** `neutral`, `happy`, `sad`, `angry`, `surprised`, `worried`, `thinking`, and the
big ones: `laughing` (shoulders bouncing; it keeps laughing while it talks), `blushing`,
`tongue_out`, `crying` (streams of tears, sobbing), `dizzy` (swirling eyes, swaying) and
`frightened` (wide eyes, hair, fur or feathers standing up, shivering; a robot's antenna springs
up). They work on people, animals and robots, side and front. `[laugh]` / `[giggle]` in a line
make the speaker laugh. Save the big ones for the moments that earn them.

**Effect symbols.** `- {effect: pip, to: idea}` pops a small symbol over a head for the beat: an
`idea` bulb, a `question` or `exclaim` mark, a `sweat` drop, an `anger` mark, `sleep` Zs, `hearts`,
dizzy `stars`, a `sparkle`, a `tear`. It follows the character, sounds with foley (`sound: false`
for none) and goes at the next beat (`until:` keeps it longer). Use one per line at most, on the
moment the feeling lands (`at`); it says "she has an idea" without a word.

**Title cards and irises.** A `card` scene is the cartoon's title card: the episode's name, a
"Later that day…" between two scenes, "The End" (`style: burst`, `frame` or `plain`; `sting:
reveal`, `comic` or `sad` as the text pops in). The classic way between them is an iris: a black
circle closes on the scene before and opens on the next. `transition: {type: iris_out,
character: pip}` closes on Pip's head (a pause on the face, then black); `{type: iris_in,
character: kit}` opens on Kit in the scene it leads into; `at: [x, y]` (fractions of the frame
from the top left) for a point, `color` for another colour. The other side opens or closes on
the frame's centre. `iris_in` on the first scene opens the video.

```yaml
characters: [{name: pip, look: {body: bean}}, {name: kit, look: {body: tall}}]
scenes:
  - id: yard
    type: stage
    params: {characters: [{name: pip, at: left}]}
    beats: [{text: "And that was the last Pip saw of the kite."}]
  - id: later
    type: card
    params: {text: "Later that day…"}
    duration: 2.5
    transition: {type: iris_out, character: pip}
  - id: hill
    type: stage
    params: {characters: [{name: kit, at: right}]}
    transition: {type: iris_in, character: kit}
    beats: [{text: "Up on the hill, Kit found something."}]
```

**Automatic directing.** `auto_direct: true` (top level, a stage's param or a beat's key) adds
the routine looks and reactions for you: listeners `look_at` whoever speaks, the speaker looks at
the one it answers, and after a line with `?`, a negation or `!` the listeners `react` in the
pause (`thinking`, `worried`, `surprised`...). The speaker gestures on the line's stressed word
(mark it `*word*`: the asterisks are not spoken or shown; or write it in CAPITALS; else the
longest word counts; at most one per line), and a short punchy line
right after a long one gets a close-up on its speaker (a short push-in, or a `shot: closeup` when
the line is too short for it). A strong change of face gets its symbol (surprised an
exclamation mark, thinking a question mark, angry an anger mark, dizzy stars, frightened a sweat
drop; one per line). Nothing it adds may cause an `off_stage`
or `facing_away` lint warning (it checks the stage's layout first). Actions you write win: a
character with its own action in a beat gets nothing automatic there. So turn it on, then write only the moments that
matter (the reaction shot, the punchline's look to camera). `vidgen direct` lists what it adds,
`vidgen direct --print` writes it as YAML to paste into the beats and edit; the storyboard shows
an `auto:` line under each beat.

**From a screenplay.** When the story comes as a script, write it as a screenplay and let
`vidgen screenplay story.md --out DIR` (MCP tool `screenplay`) make the project: one `stage`
scene per `# Scene:` heading, one beat per line, a generated look and a voice for each character
not declared in the front matter, `auto_direct: true`. Then refine the YAML as usual (check the
`# TODO:` lines: directions and manners it could not map). `# Card: Later that day…` makes a
title card (silent unless lines follow), coming in with an `iris_out`; the scene after it opens
with an `iris_in`.

```markdown
---
title: The Humming Box            # optional: video.yaml keys (voice, theme, characters...)
---
# Scene: yard
set: background: day; props: box (crate) at 0.6, tree at 0.84; characters: fen at left, bram at right

On a quiet Sunday, Fen heard a sound that did not belong in the yard.

FEN (surprised): Bram, listen! That box is humming a song.

[Fen walks to the crate and points at it.]

BRAM: Boxes do not hum, Fen. Boxes do not do *anything*.
```

Indoors: `set: room: stripes, window at 0.3, door at right; props: sofa against the wall at 0.4,
picture frame on the wall, rug at 0.5`. `NAME (manner):` turns an expression or pose word (`doubtful`, `glad`, `arms crossed`) into a
`react` and a feeling word (`cross`, `whispering`, `sleepy`) into the beat's `emotion` (how the
voice says it), and a pronoun there states the voice kind (`FEN (she):`, `BRAM (he, doubtful):`,
`GUS (they):`; once per character is enough): the generated look and voice then suit it (without
one, the voice follows the look's kind); a plain paragraph is the narrator; `[...]` maps walk / run to, enter, exit, jump, look
at, point at, wave, nod, shrug and shake head, and effect symbols (`[Pip has an idea]`, `is
confused`, `falls asleep`, `cries`...) (on its own line: at the next line's start; inside a
line: at that word), except a voice sound such as `[laugh]` inside a line, which stays in the
line. Undeclared characters get looks that differ from the others (`--species cat dog` for
animals, `--seed` for other random ones). `docs/CONFIG.md` "Cartoons from a screenplay" has the
whole format.

**From a story in prose.** `vidgen story draft story.md -o DIR [--style iso|flat] [--format 9:16]
[--narrator VOICE]` (MCP tool `story_draft`) drafts the whole project without AI: scenes at
headings, `***` breaks and time cues, a cast with distinct Kokoro voices (first person: the narrator
is the protagonist's voice), each quoted line (double quotes, or British `‘…’`) given a speaker with
a confidence (`said the old man` adds an `old_man`), iso places with a little `ambient` life, light,
weather and objects from the story's words, placeholder walks and shots, a title card in the
story's mood, an end card, a music bed. Read its `story_draft.md` first: fix the speakers marked **check** (`voice:` of those
beats), the cast, then the places and walks (they are placeholders), and run the usual loop.

**A series: one cast, shared sets.** Put the characters and their voices in `shared/cast.yaml`
and the places in `shared/sets.yaml` (`sets: {meadow: {background, props, marks, light...}}`);
each episode writes `include: [../shared/cast.yaml, ../shared/sets.yaml]` and a stage scene
`set: meadow` with only what differs in its `params` (`light: sunset`, its characters). The
scene's own params win; props, layers and characters add to the set's (`{name: tree, at: 0.3}`
moves the set's tree); an episode's `characters:` entry of a cast name changes that character
for the episode. `vidgen validate` names the file a problem is in; `vidgen screenplay story.md
--cast shared/cast.yaml` writes an episode that includes the cast and turns `set: meadow` lines
into the set. `examples/cartoon_series/` shows it (CONFIG "Shared casts and sets").

**Comic timing.**
- **Short lines**: one line per beat, one speaker per beat (the beat's `voice`), 6–12 words.
  Kokoro needs about 8 words to sound natural, and a two-word beat with actions trips
  `rushed_animation`. It also reads fast (3.5–4.5 words a second): `speed: 0.8`–`0.85` on each
  voice gives the lines room (`narration_speed` warns above 3.5 once the audio is real).
- **Pauses**: every beat ends with `narration.pad` seconds of silence (0.35). Raise it for a
  cartoon (`narration: {pad: 0.7}`) and put the reaction in it (`at: 0.8`): line, pause,
  reaction. Commas and "..." are pauses in the voice (not in the word-count preview).
- **Setup, pause, punchline**: the punchline is its own beat, after the reaction to the setup.
  The narrator undercutting a character ("Moss was not, in fact, an expert") is a cheap, good
  laugh.
- **One thing at a time**: a move, then a line; at most one or two actions per character per
  beat. Speech bubbles only for short lines (`bubble: "Up there!"`).
- **Motion**: anticipation, squash and stretch, overshoot and follow-through are built in;
  `cartoon_motion: calm` (top level, a stage or a character) tones them down for a quiet story.
  Motion effects come with them: dust where a `run_to` (or a fast walk) sets off and stops and
  where a jump lands, speed lines behind runs and thrown or blown props, stars on a high jump's
  landing, a whoosh arc on a `gesture` with `big: true`; `motion_effects: false` (top level or a
  stage) turns them off. For a move no action has, `keyframes` and `move_along` move a character, a prop or one part
  (`kit.arm_left`); `docs/CONFIG.md` "Keyframes and motion paths". Generated characters bend
  at the elbows and knees: `arm_left` is the upper arm, `arm_left_lower` the forearm (its angle
  is the elbow's bend), the legs are `leg_left` / `leg_right` (+ `_lower`); own poses can bend
  them too (`docs/CONFIG.md` "Bending arms and legs").
- **Props in hands**: `walk_to` next to a prop, `pick_up` it, walk with it, then `put_down`,
  `give` (to a character standing next to it) or `throw` it; `hold` puts a prop in a hand at
  the start. `vidgen validate` replays the scene and says when a prop is too far, held by
  someone else or not held (`docs/CONFIG.md` "Props in hands"). A character crouches by
  itself for a prop on the ground. For a picnic or the weather: `basket`, `napkin` and
  `umbrella` props; `- open: umbrella` raises a held umbrella overhead, `- close: umbrella`.
- **Sitting and leaning**: `sit_on: pip, to: chair` (a `chair`, `rock`, `box`, `sofa`,
  `armchair`, `bed`, `desk`, or an SVG prop with `data-seat`), `lean_on: kit, to: tree` (a `tree`,
  `door`, `sign`, `lamp`, `house`, `bookshelf`, `counter`, `fridge`, or an SVG prop with
  `data-lean`), then `stand_up` before it walks, jumps or turns again. While it sits
  or leans it can talk, gesture, emote and handle props; a look turns only its head. `vidgen
  validate` says when the prop is too far, the seat taken, or a seated character walks
  (`docs/CONFIG.md` "Sitting and leaning").
- **Vehicles**: props `bicycle`, `car`, `bus`. `get_in: [pip, kit], to: car` (each must stand
  beside it), `ride_to: car, to: right` (or `{mark, depth}`; the riders go along, a cyclist
  pedals), `get_out: [pip, kit]`; no walking while riding. They are big next to the characters
  (a bus is 3.2 characters long): give it a `scale` or the stage a smaller `size`
  (`docs/CONFIG.md` "Vehicles"). Outdoors only: a `boat` floats on the stage's `water: true` (or
  `{left, right}`) and rides along it, bobbing; a `hot_air_balloon` (2 stand in its basket; 2.1
  characters tall, so use `size: 0.3`) rises, drifts with the wind and lands at `to`; a
  `toy_rocket` (nobody rides it) launches with smoke and floats down under a parachute to `to`.
  `land: false` flies a balloon or a rocket out of the top of the frame, gone for the scene.
- **Sound**: walks, entrances, exits, jumps, a `surprised` face and most effect symbols make their own sounds
  (foley: footsteps, whoosh, boing, pop, an idea's ding; a thrown prop lands with a thud; a ride rings a bell or starts an engine and brakes, a balloon's burner roars, a toy rocket fizzes off; a door creaks as it opens or closes; water splashes; on a platform `level` a jump lands softly, each coin goes `coin` and each star `twinkle`, a key `unlock`s a locked door, a blocker shuffles aside; on an iso place footsteps by what the feet walk on: grass, a path, boards, a bridge, stone), timed to the action,
  and rain plays a rain sound bed. Each stage also plays a quiet bed of its set: birdsong
  outdoors by day (not at night, not in rain), a room tone in a room; `ambience: city` on a stage
  names the street sounds instead (or `birdsong`, `room_tone`, `hum` for a lab or a ship, a list), `ambience: false` none.
  `foley: false` (top level or a stage) turns all of them off. A beat's `sting: reveal | comic | sad` adds a short music sting
  (`reveal` as the beat starts, `comic` and `sad` in the pause after the line), ducked under the
  voice; under composed music the music's own instruments play it, in its key. One or two per
  cartoon, on the real punchline, or they stop being funny. For music that follows the story
  (a mood per scene, a pause before the punchline) see *Composed music* in `vidgen guide audio`.
- **Voice sounds**: `[gasp]`, `[hmm]`, `[laugh]`, `[sigh]`, `[giggle]`, `[groan]`, `[beep]` in a line
  (`text: "[gasp] The box is open! [laugh]"`) are made by the voice at that point (`Ha ha ha!`,
  `Hmm.`; a gasp or sigh at the line's start or end is a generated breath, a beep a generated
  robot chirp) and never shown in
  captions; the speaker's mouth follows and its face changes (laugh happy, gasp surprised, sigh
  sad) unless the beat's own `emote` / `react` sets it. A line needs words besides its sounds
  (`docs/CONFIG.md` "Voice sounds").
- **Talking at once**: `overlap: 0.4` on a beat starts it 0.4 s before the line before it ends
  (both heard, both mouths move, captions show both lines); `interrupt: true` cuts that line off
  where the beat starts (inside its last word, or `overlap` seconds before its end). Not on a
  scene's first beat, and not on a line of the same voice. Keep overlaps short: `vidgen lint`
  (`talked_over`) warns when whole words of the earlier line are lost under the new one or cut by
  an interrupt (`docs/CONFIG.md` "Overlapping lines").

**The loop for a cartoon.**
1. `vidgen character-sheet NAME` (or `--all`): every pose, expression and mouth shape on one PNG.
   Fix looks that are hard to tell apart now, before writing scenes.
2. `vidgen validate --json`: unknown marks, poses and expressions, a `say` by a character
   without a voice, and warnings for actions a character lacks the parts for (an SVG without
   arms cannot `wave`).
3. `vidgen storyboard --scene ID`: each still is a comic panel. The ½ stills are half-way
   through a walk, gesture, jump or path. Ask: is it clear who speaks? Are both faces visible,
   facing each other? Does the reaction read without the words? Is anything cut by the edge?
4. `vidgen lint --json`: the cartoon rules `off_stage`, `character_overlap`, `walk_overlap`,
   `prop_overlap`, `bubble_overlap`, `facing_away`, `hidden_speaker`, `small_speaker` (a face too small to read: a
   `shot: closeup` or `character_size: large`), `offscreen_action` (iso), `mouth_without_voice` and `look_alike` (fixes in
   `vidgen guide troubleshooting`).
5. Voices: with Kokoro (`vidgen guide audio`) `vidgen tts` is free and writes the lip sync
   tracks; then storyboard and lint again, since real lines change the timing.

```yaml
voice: {provider: kokoro, voice: bf_emma, speed: 0.8}   # the narrator, slowed down
voices:
  dot_voice: {voice: af_bella, speed: 0.85, label: Dot}
  moss_voice: {voice: am_michael, speed: 0.85, label: Moss}
narration: {pad: 0.7}                              # room for reactions after each line
characters:
  - {name: dot, voice: dot_voice, look: {body: round, hair: bun, accessories: [scarf]}}
  - {name: moss, voice: moss_voice, look: {body: tall, eyes: sleepy, accessories: [hat, glasses]}}
scenes:
  - id: yard
    type: stage
    params:
      background: ["#9CCBEA", "#E4F3FB"]
      ground_color: tertiary
      props: [{prop: house, at: 0.17, depth: 0.7}, {prop: box, name: kite, at: 0.43}]
      characters:
        - {name: dot, at: left}
        - {name: moss, at: right, pose: arms_crossed}
    beats:
      - text: "On the windiest day of the year, Dot had a plan."
      - text: "Moss, look! I built a kite that flies by itself."
        voice: dot_voice
        actions:
          - {jump: dot, at: 0.1}
          - {look_at: moss, to: kite, at: 0.5}
      - text: "Dot, that is a cardboard box with a string on it."
        voice: moss_voice
        actions:
          - {look_at: moss, to: dot}
          - {react: dot, expression: worried, at: 0.8}   # in the pause after the line
      - text: "Moss was not, in fact, an expert on boxes."
        sting: comic                                     # ba-dum-tss after the line
        actions:                                         # the narrator's aside: a close-up
          - {zoom: moss, scale: 2, at: 0.1}
          - {look_at: moss, to: camera, at: 0.4}
```

A complete two-scene cartoon (under a minute, a wide stage, `follow` on a flying prop, a close-up
punchline) is `examples/cartoon/` in the schu-video-generator repository.

**A host for an explainer.** `host: NAME` (a character of `characters:`) puts that character
beside the content of every scene: bullets, charts, code, diagrams... Each scene lays its content
out in the room left (a column beside it; in 9:16 a band below it), so nothing needs moving by
hand. Its mouth follows the narration (`speaks: narrator`, the default; `own`: only beats in its
own voice), it blinks and breathes, and a scene can change it (`host: {expression: thinking}`) or
drop it (`host: false`; a title or end card often looks better without). `stage` and `card`
scenes never show it. Keep the host small next to dense content (`size: 0.4`), and check the
storyboard: lint's `host_overlap` reports anything drawn over it.

```yaml
characters: [{name: dot, look: {body: bean, hair: bun, accessories: [glasses]}}]
host: {character: dot, side: right}        # size, place (beside / below), floor, facing, pose, expression
scenes:
  - id: steps
    type: bullets
    params: {heading: "How it works", items: ["Write the beats", "Render a preview"]}
    beats: [{text: "First, you write the narration as short beats."}]
  - id: chart
    type: bar_chart
    host: {expression: happy}
    params: {title: "Render minutes", labels: ["480p", "1080p"], values: [0.4, 2.6]}
    beats: [{text: "Previews are the fast way to iterate."}]
```

**Make the host act.** Beat actions: `host_point: item2` (its arm reaches towards a target of
the scene and it looks there; `line: true` adds a thin pointer line, best when nothing lies
between the host and the target), `host_look: bar3`, `host_react: happy` (`effect: sparkle` adds
a symbol), `host_move: other_side` (it walks across and the content slides to the other side
with it; one move per beat), `host_enter` / `host_exit` (a scene whose first passage is
`host_enter` starts without it). With `auto_direct: true` (or the host's own `auto_direct`) the
host points at each new bullet, bar, series or code highlight, looks at written highlights, and
reacts to results (a chart going up: happy; down: worried; an error in the code: surprised); it
never moves by itself, and anything you write in a beat wins. `vidgen direct` lists what it adds.
A complete example is `examples/host-explainer/`.

```yaml
auto_direct: true
characters: [{name: mo, look: {species: mouse, outfit: apron}}]
host: mo
scenes:
  - id: hello
    type: title
    params: {title: "Why Bread Rises"}
    beats: [{text: "Hi, I'm Mo!", actions: [{action: host_enter}]}]
  - id: bake
    type: process
    params: {stages: ["Mix", "Rise", "Bake"], layout: column}
    beats:
      - text: "Mix it, and let it rise."
      - text: "Then into the oven."
        actions: [{host_point: stage3, line: true, at: 0.5}]
```

