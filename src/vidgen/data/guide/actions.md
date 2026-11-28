<!-- topic: actions (also: targets, callouts, highlight, zoom) -->
## Pointing at things: beat actions and callouts

A beat can act on named **targets** of its scene while it is spoken: `vidgen list-scenes`
prints each type's targets (`bar:<label>`, `item<N>`, `node:<id>`, `point:<series>@<x>`...), and
`vidgen validate` lists the valid names when one is wrong.

| action | use it to | restraint |
|---|---|---|
| `highlight` | make the thing the voice names stand out (`style: color`, `box`, `underline`, `fill`, `flash`) | one target per beat |
| `dim` | push the rest back (`opacity`) | pair with a highlight, undo with `until` |
| `callout` | label or point at something (`kind: box`, `circle`, `arrow`, `label`, `spotlight`, `magnifier`) | one per beat; gone at the next beat |
| `zoom` | look closer at a detail, then come back (`hold: true`: stay close, e.g. a Short's last shot; `cut: true`: jump there, at 0 of a scene's first beat the scene opens on it); on a `plot`, `x: [from, to]` / `y: [...]` zoom its axes to that region of the data instead of moving the camera | at most one per scene |
| `pan` | on a `stage`: move the camera to a character or a mark (`to: right`); on an iso place to a spot (`to: well`) across and up the picture, moving in from the wide view | on a stage wider than the frame (`width: 2`), or on an iso place to look at a thing |
| `follow` | on a `stage`: keep the camera on a character as it moves (on a platform `level` gently, up and down too; `level: {follow: hero}` follows from the start; on an iso place it zooms in first, to a plain stage's size) | one at a time |
| `reveal` | bring a later element in early; on an iso place an object with `shown: false` appears (a bridge over the pond) | rarely: the default order is usually right |
| `hide` | on an iso place: an object fades away (`- hide: rock`; a bridge gone cannot be crossed) | cause and effect in the story |
| `transform` | morph one target into another (`into`) | for equations and before / after |
| `fit` | on a `plot`: draw a fit on a word (`- fit: "fit:decay"`: its band, curve, parameters and residual panel) | when the narration says the data are fitted |
| `annotate` | on a `plot`: show an annotation on a word (`- annotate: annotation2`: its mark and text) | when the narration names the marked point, line or range |
| `grow` | on a `plot`: grow live series (a model's) from a word until the next action or the beat's end (`- grow: "series:x"`, `to: 4` in the model's time; `axes`: all of them) | when the narration follows the simulation as it runs |
| `substitute` | on a `calculation`: show a calculation's values put into its formula on a word (`- substitute: calc1`; the formula first if it is not on screen); `reveal: formula2` shows a formula, `highlight: "symbol:G"` marks a symbol | when the narration says the numbers |
| `compute` | on a `calculation`: show its result on a word (`- compute: calc1`; the steps before it come first) | when the narration says the result |
| `convert` | on a `calculation`: show the result in its `convert` units on a word (`- convert: calc1`) | when the narration says the result in other units |
| `sweep` | on an `orbit`: start a body's equal-time sectors on a word (`- sweep: "sectors:Comet"`); `reveal: "foci:Comet"` (`axes:`, `periapsis:`, `velocity:`) shows an overlay, `highlight: "periapsis:Comet"` marks it | when the narration starts counting equal times |
| `launch` | on an `orbit` with a `cannonball`: fire a shot on a word (`- launch: "shot:3"`; without launches every shot flies from the start) | when the narration says the speed of the shot |
| `burn` | on an `orbit` with burns or a `transfer`: the clock runs so the burn happens on a word (`- burn: "burn:2"`); one speed-up before, another after, both in the panel | when the narration says "burn" |
| `flyby` | on an `orbit` with a `flyby`: the closest approach on a word (`- action: flyby`) | when the narration says the probe swings past |
| `pause` | on an `orbit`: hold the clock still from a word (`- action: pause`) until a `coast` (or the end of the beat); the panel says "clock paused" | while the narration explains a moment (the launch window) |
| `coast` | on an `orbit`: run the clock again after a `pause` (`- action: coast`) | when the narration moves on |
| `camera_orbit` | on a `3d` scene: circle the camera around an object (`- camera_orbit: tower`, `degrees: 90`, `up`) or the point it looks at | one camera move per idea; let it finish before the next |
| `camera_dolly` | on a `3d` scene: push in towards what the camera looks at (`- action: camera_dolly`, `by: 2`; negative pulls back) | when the narration gets to a detail |
| `camera_fly_to` | on a `3d` scene: fly to an object so it fills the frame (`- camera_fly_to: ball`) | when the narration names the object |
| `camera_look_at` | on a `3d` scene: turn the camera to an object (`- camera_look_at: ball`) or a `point` | a small turn reads better than a long flight |
| `camera_move` | on a `3d` scene: move the camera to `to: [x, y, z]`, looking at `look_at` (an object or a point) | to pull back to the whole scene |
| `object_move` | on a `3d` scene: move an object to `to: [x, y, z]` or `by` (`- object_move: ball`); its children come along; the camera and arrows follow it | when the narration says where it goes |
| `object_path` | on a `3d` scene: move an object along a smooth curve through `points` (`turn: true` faces along it) | a journey with a few stops |
| `object_rotate` | on a `3d` scene: turn an object to `to: [x, y, z]` degrees or `by` | "it tips over", "the lid opens" |
| `object_spin` | on a `3d` scene: spin an object `turns` times about `axis` (y) during the beat | a quick spin on a word; `spin:` in params turns it all the time |
| `object_scale` | on a `3d` scene: grow or shrink an object to `to` times its size | "it doubles in size" |
| `object_show` | on a `3d` scene: bring in an object written with `visible: false` (fade, or `style: grow`) | on the word that names it |
| `object_hide` | on a `3d` scene: take an object away (fade, or `style: grow` shrinks it) | when it is done with |
| `object_highlight` | on a `3d` scene: make an object glow (theme `highlight`) until the end of the beat | when the narration names it (the 2D `highlight` works on `view`/`title` only) |
| `object_walk` | on a `3d` scene: a stand-in turns and walks to `to` (`[x, z]` or an object's id: it stops in front of it) | "Ana walks over to the crate" |
| `object_face` | on a `3d` scene: turn an object (a stand-in's nose) to face `to` (an object's id or a point) | before a stand-in talks to another |
| `corotate` | on an `orbit` with a three-body `system`: turn the view into the frame rotating with the pair (`- action: corotate`, `run_time: 2`): both primaries and the Lagrange points stand still, trails redraw in that frame | "now let the frame turn with Jupiter" (a Trojan's tadpole appears) |
| `inertial` | on an `orbit` with a three-body `system`: turn the view back to the fixed stars (`- action: inertial`) | "seen from the stars again" |
| `antiparticles` | on a `standard_model` chart: turn quark and lepton cells into their antiparticles (`- action: antiparticles` for all, or `antiparticles: "group:leptons"`): the charge reverses, the symbol takes its bar or sign (ū, ν̄ₑ, e⁺), the name changes; `until:` turns them back | "every particle has an antiparticle with the opposite charge" |
| `couplings` | on a `standard_model` chart: outline the particles a boson couples to (`couplings: "particle:photon"`; g, Z, W, H too), ring the bosons it meets, dim the rest and say why; undone at the next beat | "the photon couples to electric charge" |
| `travel` | on a `feynman` diagram: a particle dot runs along lines in time order (`travel: "line:mu"`, or `travel: diagram` for a dot on every line at once) | "follow the electron through" |
| `vertex_rule` | on a `feynman` diagram: ring a vertex and state its rule (`vertex_rule: "vertex:v1"`; `show: [rule, coupling, checks]`): the vertex type, the coupling (α ≈ 1/137, α_s ≈ 0.118, g ≈ 0.65, y ∝ mass), the charge and lepton numbers in and out; undone at the next beat | "at this vertex the photon couples to the charge" |
| `swap_channel` | on a `feynman` scene with several diagrams: morph into another (`- action: swap_channel`, `to: t`): s ↔ t channel, photon ↔ Z, top ↔ W loop | "or they exchange a photon instead" |
| `boost` | on a `kinematics` scene: speed the last frame up continuously (`- action: boost`, `to: lab`, `rest` or a β such as 0.99): a decay's products swing forward and close up, Σp grows, β and γ count up, the invariant mass stays | "speed the pion up" |
| `switch_view` | on a `detector` scene: turn the transverse view (x–y, across the beam) into the longitudinal one (r–z, along it) or back (`- action: switch_view`, `to: rz` / `xy`); rings, tracks, towers and hits morph | "seen from the side" |
| `trace` | on a `function_plot`: move a dot along its curve (`- trace: dot1`, `to: 2`; its value label and tangent follow), an area's right end, a point (`to: [x, y]`) or a vector's tip (`to: [x, y]`, or `scale: 2`), everything drawn from them following; on a `number_line`: a point (`to: 4`); on a `line_chart`: a cursor dot along a series (`- trace: series1`, `to: 4`, the line's value over it) | one movement per beat, timed to the word that says it |
| `sfx` | a sound at that moment (`vidgen guide audio`) | the important moments only |
| `particles` | rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves or streaks (wind lines) over any scene (`- particles: confetti`; `density`, `area`, `glow: true` to make them shine, `keep: true` for the rest of the scene) | a mood or a celebration, not on dense text |
| `wind` | on a `stage`: fade the wind to `0.8` or `calm`, `breeze`, `windy`, `gale` (`- wind: gale`; `run_time` = the fade, 2 s) | a storm coming, a gust in the story |
| `blow_away` | on a `stage`: the wind blows a light prop away, tumbling, out of a hand too (`- blow_away: napkin`; `to:` a mark to land there, else off the stage) | a gust in the story; napkin, umbrella, ball, cup, basket, box, letter, balloons only |
| `light` | on a `stage`: fade the light to `morning`, `sunset`, `night`, `indoor` or `day` (`- light: night`; `run_time` = the fade, 2 s; `move_sun: true` moves a `sun` / `moon` prop across the sky, shadows turning) | when time passes in the story |
| `time_of_day` | on a `stage`: a day passing (`- {time_of_day: night, run_time: 6}`, 6 s): the light and a sky of the time of day fade (day to night through a sunset), stars come out, and at dusk lamps, windows, lit objects and cars' headlights switch on by themselves one after another (off at dawn); `auto_lights: false`, or `auto_light: false` on an object, opts out; a `sun` / `moon` prop moves | evening falls or morning comes during a scene |
| `lightning` | on a `stage`: the set flashes and a bolt strikes (`- lightning: right`; `distance: 2`: its thunder ~6 s later; in a room the windows flash) | a storm, a scare; rain with `lightning: true` strikes on its own |
| `rainbow` | on a `stage` outdoors: a rainbow fades into the sky and stays (`- rainbow: centre`; `hide: true` fades it out) | after the rain |
| `switch_on` | on a `stage`: a `tv`, `lamp`, `kettle` goes on, a `fireplace` burns, a `phone` rings (`- switch_on: tv`; a click with foley); on an iso place a `lamp` lights, a `house`'s windows glow (they stay bright at `light: sunset` / `night`) | when someone in the story switches it on or lights the fire; when a call comes |
| `switch_off` | on a `stage`: a `tv`, `lamp`, `kettle` or `fireplace` goes off, a `phone` stops ringing (`- switch_off: lamp`) | when someone in the story switches it off or answers |
| `knock` | on a `stage`: someone knocks three times on a door (`- knock: front`; a room's door or a `door` prop; nobody needs to stand there) | a visitor in the story; the door then `open`s with a creak |
| `alarm` | on a `stage`: an alarm goes off (`- alarm: start`) or stops (`- alarm: stop`): the set darkens under a red light pulsing like a beacon, a siren plays; portals, holograms and screens keep shining (`color`, `period`) | a security system, a red alert |
| `shutters` | on an indoor iso place: steel shutters slam down over its windows (`- shutters: close`, a slam) or roll up (`- shutters: open`) | with an alarm; a lockdown |
| `materialise` | on a `stage`: a character appears as a hologram does, a flickering wireframe, then solid (`- materialise: guide`; it waits unseen until then) | a projection switched on, another self appearing; best on `hologram: true` or `echo: true` |
| `dematerialise` | on a `stage`: a character vanishes the same way backwards (`- dematerialise: guide`) | a projection switched off |
| `hold_hands` | on a `stage`: a character takes another's hand (`- {hold_hands: ana, with: ben}`); they hold hands wherever they stand or walk | walk both in the same beat to places side by side to go hand in hand |
| `let_go_hands` | on a `stage`: a character lets go of the hand it holds (`- let_go_hands: ana`; the other too) | before an arm gestures again |
| `kiss` | on a `stage`: two characters kiss (`- {kiss: ana, with: ben}`, 3 s): they turn, lean in until their faces touch, eyes closed, a small burst of hearts and sparkles, then lean back (`hearts`, `color`) | stand them a step apart; a `two_shot` |
| `let_go` | on a `stage`: a character lets go of the balloons it holds; they float away (`- let_go: pip`) | gone for the scene |
| `pour` | on a `stage`: a character pours with the watering can it holds (`- pour: kit`, 2 s) | watering a plant |
| `drop_fruit` | on a `stage`: a fruit falls from a tree with `fruit: true`, bounces, thuds (`- drop_fruit: tree`; `to: pip`: on pip's head, stars) | a comic moment; the character stands under the tree |
| `birds` | on a `stage` outdoors: a flock crosses the sky (`- birds: 5`; `direction: left`) | a calm outdoor moment, time passing |
| `say` | on a `stage`: pick who speaks the beat (`- say: kit`; `bubble: true` or a short text for a speech bubble) | without it the characters whose `voice` is the beat's voice speak; bubbles for short lines |
| `look_at` | on a `stage`: a character looks at another, a prop, a mark or `camera` (`to:`) | when attention moves |
| `turn` | on a `stage`: a character faces the other way (`to: left` / `right`), or the viewer (`to: front`: its front view) | an SVG character has no front view |
| `emote` | on a `stage`: change a character's expression (`to: happy`) | on the word that causes it (`at`) |
| `pose` | on a `stage`: change a character's pose (`to: pointing`) | one pose change per beat |
| `react` | on a `stage`: a listener's `expression` / `pose` for this beat only | the listener, not the speaker |
| `effect` | on a `stage`: a symbol over a character's head for this beat (`to: idea`, `question`, `exclaim`, `sweat`, `anger`, `sleep`, `hearts`, `stars`, `sparkle`, `tear`) | a feeling that should read at a glance; one per line |
| `walk_to` | on a `stage`: a character walks to a mark or x (`to:`; `speed`), also towards or away from the camera (`depth: 0.4`, or `to: {mark: right, depth: 0.4}`); on an iso place to a spot or `{column, row}` round what is in the way, or `after: kit` (follows it) | with `follow` on a wide stage; the walk takes its distance's time |
| `run_to` | on a `stage`: a character runs to a mark or x (`to:`; `speed`): longer strides, leaning forward, dust and speed lines | a hurry, a chase, an escape |
| `enter` | on a `stage`: a character walks in from an edge (`side:`) or through a room's door (`door: door`) to its mark (or `to:`); on an iso place over the place's edge, or out of a spot (`door: front_door`) | it waits off stage until then |
| `exit` | on a `stage`: a character walks out by an edge (`to: left` / `right`) or through a room's door (`door: door`) | an `enter` brings it back |
| `gesture` | on a `stage`: `to: point`, `wave`, `shrug`, `nod`, `shake_head`; `big: true` adds a whoosh arc | on the word it goes with (`at`) |
| `jump` | on a `stage`: a character jumps (`height`); on a platform `level`, `to:` a spot, mark or tile jumps it there on a planned arc, picking up coins and stars on the way (`react: {when: land, expression: happy}`) | joy or surprise; getting onto a platform |
| `step_aside` | on a platform `level`: a blocker (`level.blockers`) moves out of the way (`- step_aside: tobble`; `to:` a place to walk to) | after the line that asks it nicely |
| `wander` | on an iso place (`iso:`): a character strolls to a few cells near it, round what is in the way (`around:` a spot, `radius`, `stops`; `seed` for another stroll) | waiting, looking about, time passing |
| `meet` | on an iso place: a character and another (`with: kit`) walk to each other and stop side by side, facing each other | before the two talk |
| `keyframes` | on a `stage`: move a character, prop or part (`kit.arm_left`) through `keys: [{t, x, y, rotate, scale, ease}]` (`t` seconds or `"40%"` of the beat) | motion no other action has; keep it short |
| `move_along` | on a `stage`: move a character, prop or part along `path: [[x, y], ...]` (smooth curve; `speed`) | flying, floating |
| `pick_up` | on a `stage`: a character reaches for a prop and holds it (`to: ball`; `hand`); it goes along with the hand | `walk_to` next to the prop first (`vidgen validate` says where) |
| `hold` | on a `stage`: a character holds a prop from now on, without picking it up (`to: cup`) | a prop it has from the start (`at: 0`) |
| `put_down` | on a `stage`: the held prop goes on the ground (`to:` a mark or x, default in front); on an iso place beside it, or `to:` a spot next to it (on the table there) | within reach |
| `give` | on a `stage`: the held prop goes to another character (`to: kit`) | the two stand next to each other |
| `throw` | on a `stage`: the held prop flies to a mark or x (`to:`; `spin`, `height`) and lands with a thud | |
| `open` | on a `stage`: an `umbrella` or `door` prop opens (`- open: umbrella`); a held umbrella goes up over its holder's head; `by: pip` reaches for it (a locked door on a `level` opens only by whoever holds its key); on an iso place a `house`'s door, a room's `door_1`, `flowers` (they bloom) | `open: true` in `props` starts it open |
| `close` | on a `stage`: an open `umbrella` or `door` closes (`- close: door`); a held umbrella comes down to the hand; on an iso place a house's or a room's door, flowers back to buds | |
| `sit_on` | on a `stage`: a character sits on a `chair`, `rock`, `box`, `sofa`, `armchair`, `bed` or `desk` (`to: chair`); its hips and knees bend; on an iso place on an object with seats (`armchair`, `bench`, `cafe_table`...) | next to the prop; `stand_up` before it walks |
| `lean_on` | on a `stage`: a character leans its back on a `tree`, `door`, `sign`, `lamp`, `house`, `bookshelf`, `counter` or `fridge` (`to: tree`) | next to the prop; `stand_up` before it walks |
| `stand_up` | on a `stage`: a character gets up from where it sits, leans or lies | |
| `lie_on` | on an iso place: a character lies in a `bed` (`to: bed`), the blanket over it | next to the bed; `stand_up` before it walks |
| `use` | on an iso place: a character types at a `laptop` / `desk_with_pc` / `console`, warms its hands at a `campfire` / `fireplace`, takes a book, presses at a machine (`to: laptop`, `run_time`) | next to the object, or seated next to it |
| `get_in` | on a `stage`: characters get in a `car`, a `bus`, a `boat` or a `hot_air_balloon` or on a `bicycle` (`to: car`); they ride with it until `get_out` | next to the vehicle; a bicycle seats 1, a car, a boat and a balloon 2, a bus 4 |
| `ride_to` | on a `stage`: a vehicle (or a rider: its vehicle) rides to a mark, an x or `{mark, depth}` with its riders, wheels turning; a boat along the water, a balloon or a `toy_rocket` flies there (`land: false`: away) | `get_in` first (a toy rocket: none) |
| `get_out` | on a `stage`: riders get out of their vehicle where it is | |
| `drive_to` | on an iso place: a `car` drives along the path cells to `to` (a spot or `{column, row}`, `via` on the way); a `train_car` rolls along its track | a car arriving, leaving, passing by |
| `sail_to` | on an iso place: a `boat` sails across the water to `to` (`via` on the way) | a boat setting off or coming in |
| `lift_off` | on an iso place: a `rocket` fires and rises out of the view | a launch |
| `shot` | on a `stage`: the camera frames characters for the beat; write it as the beat's key `shot: closeup kit` (`wide`, `two_shot`, `medium`, `over_shoulder kit pip`; `closeup ana ben`: two or three faces together; `{kind: closeup, of: kit, clear: true}` hides the others for the beat); the next beat without one cuts back; on an iso place `wide` is the place's wide view and the others make its small characters large | a beat's dialogue line or reaction (on an iso place every longer spoken line: in a wide view a speaker gets a name tag, enough for a short line); not with a walk out of the framing |
| `host_point` | with a `host:`: the host's arm reaches towards a target of the scene and it looks there (`- host_point: item2`; `line: true`: a thin pointer line) | one per beat; a line only when nothing lies between the host and the target |
| `host_look` | with a `host:`: the host looks at a target of the scene (`- host_look: bar3`) | when attention moves |
| `host_react` | with a `host:`: the host's expression for this beat (`- host_react: happy`; `effect: sparkle` adds a symbol) | on a result or a surprise |
| `host_move` | with a `host:`: the host walks to the other side and the content slides over with it (`- host_move: other_side`, `left`, `right`) | one move per beat; rarely, between topics |
| `host_enter` | with a `host:`: the host walks in from an edge (`{action: host_enter}`, or `- host_enter: left`); the scene starts without it | at the start of the video |
| `host_exit` | with a `host:`: the host walks out by an edge (`- host_exit: left`); its room stays free | at the end |
| `build` | on an `iso_diagram`: blocks, a stack (layer by layer), a group or a connector come in on the word (`- build: "block:db"`; `style: grow`, `drop`, `fade`); the scene leaves them to it | one part per idea, as the voice names it |
| `raise` | on an `iso_diagram`: lift blocks, a layer (with the layers above) or a group off the floor (`by: 0.5`), a shadow under them; `lower` sets them down | to single out a part; undo with `until` |
| `lower` | on an `iso_diagram`: set raised blocks down (`by`, default to the ground) | |
| `explode` | on an `iso_diagram`: pull a stack's layers apart (`- explode: "stack:app"`, `gap: 0.6`), labels going along; `collapse` puts them back | to show what a stack is made of |
| `collapse` | on an `iso_diagram`: an exploded stack's layers back together | |
| `flow` | on an `iso_diagram`: dots (`style: packets`: small cubes) run along connectors (`- flow: "edge:*"`, `chain: true` one after another, `back`, `count`) | when the voice follows data or a request |
| `focus` | on an `iso_diagram`: the camera moves onto a block, stack or group and stays (`- focus: "group:web"`), clear of the captions; labels it would cut fade out; `focus: diagram` goes back to the whole frame; on a `pathway`: onto nodes (`focus: ras`; `focus: pathway` goes back) | at most one or two per scene |
| `relabel` | on an `iso_diagram`: a label or value changes in place (`- relabel: "block:cache"`, `text: "Cache: hit"`) | a new value, a state change |
| `zoom_to` | on a `cell`: the camera moves in µm to a level on an object and stays (`- zoom_to: mitochondria`; `level: tissue`, `cell`, `organelle`, `complex`; `width: "2 um"`; `labels: false` or a list of the parts to name); details appear as they grow, the scale bar follows; `zoom_to: cell` goes back | one level change per idea, on the word that names the target |
| `motor_walk` | on a `cell`: motors walk hand over hand along their filament with their cargo (`{motor_walk: kin, distance: 500 nm}`; kinesin to the + end, dynein to the − end; `toward` checked) | at a view of a few hundred nm to see the steps |
| `endocytosis` | on a `cell`: a clathrin-coated pit buds in and is pinched off by dynamin (`endocytosis: cell`, `site: [x, y]`); captioned steps | at a 300–500 nm view of the plasma membrane, `labels: false` on it |
| `exocytosis` | on a `cell`: a vesicle docks with SNAREs, fuses and releases its cargo (`exocytosis: <vesicle id>`, uncoated, in the cytosol) | likewise |
| `set_state` | on a `molecule`: a molecule morphs to another state (`{set_state: kv, state: open}`; `until` turns it back) | before `transport` on a channel (ions pass only an open one) |
| `transport` | on a `molecule`: a channel passes ions down their gradient (`count`), a carrier or pump runs its cycle (`cycles`: alternating access; the Na⁺/K⁺ pump's E1 → E1P → E2P → E2 with ATP → ADP + Pᵢ), each step captioned | one cycle per idea |
| `diffuse` | on a `molecule`: a solute's particles random-walk with net flux down the gradient (`diffuse: oxygen`; across a bilayer only O₂, CO₂, water) | on the word that names the process |
| `osmosis` | on a `molecule`: water moves to the side with more solute (`osmosis: membrane`), through aquaporins if any | |
| `action_potential` | on a `molecule`: voltage-gated Na⁺ and K⁺ channels open, inactivate and close with a live Vₘ readout and an inset trace (`action_potential: membrane`) | |
| `transcribe` | on a `molecule` with a `gene`: TBP on the TATA box, the general factors and RNA polymerase II assemble, a ~13 bp bubble opens, the template strand is read 3′→5′ and RNA made 5′→3′ (capped at ~25 nt); on a `cell`: mRNAs made at the gene | first step of a gene; then the others in order (validated) |
| `cap` | on a `molecule` with a `gene`: the three enzymes of the 5′ cap (m⁷GpppN) as their own step (else `transcribe` caps) | after `transcribe` |
| `splice` | on a `molecule` with a `gene`: snRNPs on GU / branch A / AG, the lariat, the exons joined, an EJC | the gene needs `introns` |
| `polyadenylate` | on a `molecule` with a `gene`: CPSF / CstF, cleavage, Xrn2 termination, the poly(A) tail | before `export` |
| `export` | on a `molecule` or `cell` with a `gene`: the mRNP through a nuclear pore, 5′ end first | only a capped, spliced, polyadenylated mRNA |
| `translate` | on a `molecule` or `cell` with a `gene`: scanning to the AUG, the 80S ribosome, tRNAs pairing with codons, the chain growing N→C with its amino acids written out, the stop codon and release (`codons: n` stops after n) | only after `export` (refused in the nucleus) |
| `target_er` | on a `molecule` with a `gene` (`signal_peptide: true`): SRP, its receptor, Sec61, the signal in the lateral gate, signal peptidase | while translating (`translate: g, codons: 3` before it) |
| `glycosylate` | on a `molecule` with a `gene` (`glycosylation: true`): OST puts Glc₃Man₉GlcNAc₂ on the sequon's Asn | in the ER, after `target_er` |
| `fold` | on a `molecule` with a `gene`: Hsp70, the chaperonin, BiP or calnexin (`chaperone`, checked against the compartment); the chain packs its hydrophobic residues inside | after the stop codon |
| `to_golgi` | on a `cell` with a `gene`: a COPII vesicle from an ER exit site to the cis-Golgi, then cis → trans | a folded protein made into the ER |
| `secrete` | on a `cell` with a `gene`: from the trans-Golgi network `to: outside` (exocytosis), `membrane` or `lysosome` | after `to_golgi` |
| `signal` | on a `pathway`: the signal runs from a node along the arcs, wave by wave: arcs light, nodes light, GDP → GTP, phosphorylated sites appear (pS133); an inhibitor of an inhibitor turns its target on (`signal: egf`; `to: creb` only the shortest path; `signal: [gcgr, gas, ac]` a path; `feedback: false`); it stops at a knocked-out, drugged or held node | about 0.75 s per step: give it a long beat, or `to:` |
| `inhibit` | on a `pathway`: an inhibitor engages (`inhibit: pten`; `on: [pip3]`): its T-bars flash, its targets are held, the nodes downstream that change get ↑ / ↓ | the node needs an inhibitory arc |
| `knockout` | on a `pathway`: a node is crossed out (`knockout: pten`) and every node downstream that changes gets ↑ / ↓, computed from the graph (`effects: false` leaves them out) | `until` brings it back |
| `drug` | on a `pathway`: a pill with the drug's name blocks a protein (`{drug: mek, name: trametinib}`; a known drug on another target is refused), with the effects downstream | not on genes, messengers or outcomes |
| `amplify` | on a `pathway`: many copies of a node stream out of the node that makes it (`{amplify: camp, factor: "×100"}`; `from`, `count`) | after the `signal` reached it |
| `advance` | on a `cell_cycle`: the cell moves round the cycle (`advance: cycle, to: s`; `into: 0.5`; `to: g0` only before the restriction point) or a division runs to a stage (`advance: cell, to: anaphase_i`; `expect: {chromosomes: 2, chromatids: 4}` is checked); on a `metabolism`: the token runs to a metabolite or enzyme (`advance: glycolysis, to: pyruvate`), electrons run along the chain pumping protons (`advance: etc, to: complex_iv`; `from: fadh2`), or the gradient drives ATP synthase (`to: atp_synthase`) | one stage or a few steps per beat: its length follows what it shows (up to ~8 s) |
| `checkpoint` | on a `cell_cycle` (`mode: cycle`): a checkpoint's regulators light in a panel — `checkpoint: g1_s` passes (cyclin D–CDK4/6 ⊣ Rb ⊣ E2F → cyclin E–CDK2), `{checkpoint: g2_m, outcome: arrest, cause: dna_damage}` holds the cell (`advance` cannot pass it until the action's `until`); `spindle` (SAC: MCC ⊣ APC/C–Cdc20) | one checkpoint per beat |
| `form_gametes` | on a `cross`: a parent's homologues part and its gametes fly out to the square's headers (`form_gametes: both`, `parent1`, `mother`…), each allele in its homologue's colour, recombinants ringed | once per parent |
| `fill` | on a `cross`: Punnett cells fill in, the row's and column's gametes moving in (`fill: square`, `row2`, `col1`, `cell2.3`, `"cells:wrinkled, green"`; `by: row` / `column` / `cell`); `fill: tree` grows a branch diagram | a row or the square per beat (~0.2 s a cell) |
| `count` | on a `cross`: the offspring counted into classes (`count: phenotypes` or `genotypes`): rows appear as their cells flash, fractions in lowest terms, percentages, the lethal class dying | one table per beat |
| `ratio` | on a `cross`: the whole-number ratio of a table (`ratio: phenotypes` → 9 : 3 : 3 : 1) | on the word that says it |
| `chi_square` | on a `cross` with `observed` counts: the goodness-of-fit table, χ², df, p, the verdict (`chi_square: test`) | give it its own beat |
| `deduce` | on a `pedigree`: the genotypes under the symbols, forced ones or the most telling with its exact probability (`deduce: genotypes`, `carriers`, `generation:II`, `person:II-3`), obligate carriers marked | on the word that says carriers |
| `analyse` | on a `pedigree`: the modes of inheritance tried one by one, each fits or is excluded with its reason, the people it names ringed (`analyse: modes`; `mode:XR` for one) | ~1 s a mode: a beat for all six, or one mode per beat |
| `risk` | on a `pedigree` with a `proposed` child: the child appears and the risk card with the factors of the product (`risk: risk`) | on the word that says the risk |
| `cross_over` | on a `linkage_map`: non-sister chromatids meet at a chiasma in an interval and swap the segments beyond it (`cross_over: "interval:v-ct"`, or `double`); the recombinant chromatids are labelled | ~2.4 s, on the word that says crossing over |
| `measure` | on a `linkage_map`: a distance on the map with the RF its map function gives (`measure: "interval:w-v"`) | ~1.6 s |
| `rearrange` | on a `karyotype`: a change of the notation (`rearrange: change:1`, or `changes`): a structural change as an edit in an ideogram, else its highlight | ~2.6 s an edit |
| `mutate` | on a `mutation`: the variant row is made from the reference and the card gives the HGVS notation (`mutate: variant`, `variant:2`, `variants`) | ~3 s, on the word that names the change |
| `scan` | on a `crispr`: the enzyme searches the PAMs, binds the protospacer and the R-loop forms (`scan: dna`) | ~3 s |
| `cleave` | on a `crispr`: the blunt double-strand break 3 bp from the PAM (`cleave: dna`) | ~1.6 s, on the word that says cut |
| `repair` | on a `crispr`: NHEJ or HDR, with the repaired allele and its HGVS change (`repair: repair`) | ~2.8 s |
| `run` | on a `dna_lab`: a step of its method (`run: trace`, `counts`, `ladder`, `sizes`, `fragments`, `chromatogram`, `reads`, `call`); the steps before it play first | ~2.2 s each |
| `simulate` | on a `population` simulation: the lines grow to a generation (`simulate: "generation:40"`, or `lines` to the end); fixation and loss marked, the dots follow | ~1–3.2 s by the generations covered |
| `resample` | on a `population`: the next generation's individuals (a simulation), or a new random sample at the Hardy–Weinberg frequencies (`resample: population`) | ~1.4 s |
| `regional` | on a `gwas`: zoom into a peak, its variants coloured by r² with the lead (`regional: "peak:FTO"`; one per scene) | ~2.6 s |

```yaml
- id: speeds
  type: bar_chart
  params: {title: "Render time", labels: ["Preview", "1080p", "4K"], values: [0.4, 2.6, 9.8], unit: " min"}
  beats:
    - text: "Render time grows with the resolution."
    - text: "Four K is the slow one."
      actions:
        - {highlight: "bar:4K", style: box, until: speeds_b3}
    - text: "Previews are how you iterate."
      actions:
        - dim: ["bar:1080p", "bar:4K"]
        - callout: "bar:Preview"
          kind: arrow
          label: "Use this while editing"
          at: "@iterate"           # on that word (or a fraction of the beat: 0.3)
```

- `at` times the action to the word it belongs to: name the word, `at: "@gradient"` (quoted;
  `"@gradient#2"` its second time in the beat, `"@gradient-0.2s"` a moment before it,
  `"@learning rate"` a phrase), or give a fraction of the beat (0–1). A word is timed by the
  beat's audio once `vidgen tts` made it, by an estimate from the text before; a word the beat
  does not say is a `vidgen validate` error that lists the words like it. Every action takes it
  (`callout`, `sfx`, the stage's moves and acting too), and so does `lower_third`'s `at`
  (`"@Ada"`). Actions never make a beat longer. Show a label when the narration names it:
  lint's `said_before_shown` warns when a node, callout or stage is named seconds before it
  appears. A whole explainer timed this way: `examples/gradient-descent`.
- The `stage` actions (`say` to `throw`) take the character as the target and the new
  state as `to:` (`- emote: kit` + `to: happy`). How to use them together for a cartoon:
  `vidgen guide cartoons`.
- `until: <later beat id>` keeps a highlight / dim / callout on screen; without it a callout
  disappears at the next beat and a zoom comes back by the beat's end.
- A callout without a target points at an `area: [x, y, w, h]` of the frame (fractions).
- Check actions mid-beat with `vidgen storyboard --scene ID --per-beat 3`.

