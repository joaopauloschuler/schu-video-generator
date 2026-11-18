// The ready-made seas of vidgen/space-sea (DESIGN.md §123.4) for the registry vidgen/parts (§122.5):
// what `vidgen parts` draws on its contact sheet. Drawn straight to the canvas ({finish: false}: the
// dome and the sea apply the tone curve themselves).
import {definePart} from "vidgen/parts";
import {air, sunDirection} from "vidgen/space-air";
import {sea} from "vidgen/space-sea";
import {spaceSky} from "vidgen/space-sky";

// a camera `height` metres over the sea, looking `pitch` degrees up towards -z; the air and the sea under it
function show(s, what, options, {stars = false} = {}) {
  const o = s.options, a = o.pitch * Math.PI / 180, sky = stars ? spaceSky(s.renderer, {seed: s.seed, size: 256}) : null;
  if (sky) s.scene.add(sky.object);
  s.scene.remove(s.key, s.fill);
  s.camera.position.set(0, o.height, 0); s.camera.up.set(0, 1, 0); s.camera.near = 1; s.camera.far = 1e8; s.camera.fov = o.fov;
  s.camera.lookAt(0, o.height + Math.sin(a) * 1000, -Math.cos(a) * 1000); s.camera.updateProjectionMatrix(); s.camera.updateMatrixWorld();
  const dome = air(s.renderer, what, {sun: sunDirection(o.elevation, o.azimuth), stars: sky});
  const water = sea(s.renderer, dome, {seed: s.seed, ...options});
  s.scene.add(dome.object, water.object);
  dome.update(0, {camera: s.camera}); water.update(2, {camera: s.camera});
  return {finish: false};
}

definePart({"name": "sea-calm", "kind": "sea", "module": "vidgen/space-sea",
  "label": "a calm sea by day from 50 m: a low swell, ripples in patches, the sun's mirror image a soft blot",
  "use": "const water = sea(renderer, sky, {state: \"calm\", seed}); scene.add(water.object); water.update(t, {camera})",
  "options": {"height": 50, "pitch": -8, "fov": 55, "elevation": 50, "azimuth": 35}, "seed": 3},
(s) => show(s, "earth", {state: "calm"}));

definePart({"name": "sea-breeze", "kind": "sea", "module": "vidgen/space-sea",
  "label": "the default sea, a breeze of 6 m/s: the glitter path towards a sun 22 degrees up",
  "use": "sea(renderer, sky, {state: \"breeze\", seed})",
  "options": {"height": 50, "pitch": -6, "fov": 55, "elevation": 22, "azimuth": 28}, "seed": 3},
(s) => show(s, "earth", {state: "breeze"}));

definePart({"name": "sea-rough", "kind": "sea", "module": "vidgen/space-sea",
  "label": "a rough sea, 13 m/s: steep waves 3 m high, whitecaps on the crests",
  "use": "sea(renderer, sky, {state: \"rough\", seed})",
  "options": {"height": 30, "pitch": -9, "fov": 55, "elevation": 40, "azimuth": 100}, "seed": 3},
(s) => show(s, "earth", {state: "rough"}));

definePart({"name": "sea-storm", "kind": "sea", "module": "vidgen/space-sea",
  "label": "a storm sea, 22 m/s: waves 8 m high, breaking crests and the lace they leave",
  "use": "sea(renderer, sky, {state: \"storm\", seed})",
  "options": {"height": 20, "pitch": -6, "fov": 55, "elevation": 40, "azimuth": 100}, "seed": 3},
(s) => show(s, "earth", {state: "storm"}));

definePart({"name": "sea-sunset", "kind": "sea", "module": "vidgen/space-sea",
  "label": "sunset from 12 m: the glitter path narrow and orange under a sun 1.2 degrees up",
  "use": "air(renderer, \"earth\", {sun: sunDirection(1.2, 4)}); sea(renderer, sky, {seed})",
  "options": {"height": 12, "pitch": -3, "fov": 30, "elevation": 1.2, "azimuth": 4}, "seed": 3},
(s) => show(s, "earth", {state: "breeze"}));

definePart({"name": "sea-dusk", "kind": "sea", "module": "vidgen/space-sea",
  "label": "dusk, the sun 5 degrees down: the sea mirrors the twilight arch (film exposure)",
  "use": "air(renderer, \"earth\", {sun: sunDirection(-5, 15), stars}); sea(renderer, sky, {seed})",
  "options": {"height": 30, "pitch": -2, "fov": 55, "elevation": -5, "azimuth": 15}, "seed": 5},
(s) => show(s, "earth", {state: "breeze"}, {stars: true}));

definePart({"name": "sea-from-20-km", "kind": "sea", "module": "vidgen/space-sea",
  "label": "the same sea from 20 km: the horizon 4.5 degrees under the level, the glitter a broad column",
  "use": "water.update(t, {camera}); water.horizon  // {distance, dip, height}",
  "options": {"height": 20000, "pitch": -8, "fov": 55, "elevation": 30, "azimuth": 30}, "seed": 3},
(s) => show(s, "earth", {state: "breeze"}));

definePart({"name": "sea-methane", "kind": "sea", "module": "vidgen/space-sea",
  "label": "an invented world: the dark water \"methane\" under the thick air (a look)",
  "use": "sea(renderer, air(renderer, \"thick\"), {water: \"methane\", state: \"swell\"})",
  "options": {"height": 40, "pitch": -5, "fov": 55, "elevation": 14, "azimuth": 20}, "seed": 3},
(s) => show(s, "thick", {state: "swell", water: "methane"}));
