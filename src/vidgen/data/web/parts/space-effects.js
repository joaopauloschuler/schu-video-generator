// The effects of vidgen/space-effects (DESIGN.md §123.9) for the registry vidgen/parts (§122.5): what
// `vidgen parts --kind effect` draws: a re-entry's glow on a plane and on a lander, a far head with its
// train, a vapour trail, exhaust in dense and in thin air, a vapour cone, the vapour of a hard turn. Each
// tile sets the numbers by hand (heating, Mach number, load, the air's density); in a film they come from
// `ctx.flight`. Measured at 1280x720 in software GL on 2 cores: a re-entry adds 0.3 to 0.4 s a frame to a
// plane a third of the frame wide (0.7 s filling it), exhaust, vapour and trails under 0.05 s together.
import * as THREE from "three";
import {definePart} from "vidgen/parts";
import {craft, paintedEnvironment} from "vidgen/space-craft";
import {plane} from "vidgen/space-plane";
import {effects} from "vidgen/space-effects";

const SUN = new THREE.Vector3(5, 4.5, 4).normalize();
const detail = (s) => (s.height < 300 ? "far" : "near");
// the tile: `ship` flying along `velocity` (metres a second, the scene's axes), seen from `view` at `fill` radii
function show(s, ship, {view = [0.8, 0.25, 0.55], fill = 3.0, look = [0, 0, 0], turn = [0, 0, 0], velocity = [0, 0, 240], fx = {}, state = {}, craftState = {}} = {}) {
  const R = ship.size.radius, d = new THREE.Vector3(...view).normalize().multiplyScalar(R * fill);
  ship.object.rotation.set(...turn); s.scene.add(ship.object);
  s.key.color.set(0xffffff); s.key.intensity = Math.PI; s.key.position.copy(SUN).multiplyScalar(R * 12); s.fill.intensity = 0.25;
  s.scene.environment = paintedEnvironment(s.renderer).texture;
  s.camera.near = R * 0.05; s.camera.far = R * Math.max(400, fill * 3); s.camera.fov = 34; s.camera.position.copy(d); s.camera.lookAt(...look.map((v) => v * R)); s.camera.updateProjectionMatrix(); s.camera.updateMatrixWorld();
  const made = effects(ship, {seed: s.seed, sun: SUN.toArray(), quality: s.height < 300 ? "fast" : "standard", ...fx, ...s.options});
  s.scene.add(made.object);
  return {frame(t) { ship.update(t, {sun: SUN, ...craftState}); made.update(t, {velocity, ...state}); }};
}
const glider = (s, options = {}) => plane("glider", {seed: s.seed, detail: detail(s), scheme: "tiles", scorch: 0.5, ...options});

definePart({"name": "effect-reentry", "kind": "effect", "module": "vidgen/space-effects",
  "label": "a re-entry at its peak: the shock layer on the windward side, hot tiles, the wake, sparks",
  "use": "const fx = effects(ship, {flight: ctx.flight, sky, reentry: true}); scene.add(fx.object); fx.update(t)   // after ship.update(t)",
  "options": {}, "seed": 1},
(s) => show(s, glider(s), {view: [-0.75, -0.12, 0.6], fill: 3.2, look: [0, 0, -0.5], turn: [-0.6, 0, 0], velocity: [0, 0, 6600], fx: {reentry: true}, state: {heating: 1, height: 75000}}));

definePart({"name": "effect-reentry-early", "kind": "effect", "module": "vidgen/space-effects",
  "label": "the same at heating 0.45: a dull red layer and wake (heating 0..1 by hand or from the flight)",
  "use": "fx.update(t, {heating: 0.45})",
  "options": {}, "seed": 1},
(s) => show(s, glider(s), {view: [-0.75, -0.12, 0.6], fill: 3.2, look: [0, 0, -0.5], turn: [-0.6, 0, 0], velocity: [0, 0, 6600], fx: {reentry: true}, state: {heating: 0.45, height: 85000}}));

definePart({"name": "effect-reentry-lander", "kind": "effect", "module": "vidgen/space-effects",
  "label": "the glow on any craft: a lander of vidgen/space-craft coming in base first",
  "use": "effects(craft(\"lander\"), {reentry: true}).update(t, {heating: 0.85, velocity: [vx, vy, vz]})",
  "options": {}, "seed": 1},
(s) => show(s, craft("lander", {seed: s.seed, detail: detail(s)}), {view: [0.9, 0.1, 0.45], fill: 3.6, look: [0, 0, 0.6], velocity: [0, 0, -5200], fx: {reentry: true}, state: {heating: 0.85, height: 62000}}));

definePart({"name": "effect-reentry-far", "kind": "effect", "module": "vidgen/space-effects",
  "label": "seen from 40 km: a bright head and the train of light it leaves along its path (14 s long here)",
  "use": "effects(ship, {flight: ctx.flight, reentry: {persist: 14}})   // persist: seconds the train glows (default 5)",
  "options": {}, "seed": 1},
(s) => show(s, glider(s), {view: [0.9, 0.3, -0.5], fill: 2600, look: [0, 0, -600], velocity: [0, 0, 7000], fx: {reentry: {persist: 14}}, state: {heating: 1, height: 76000}}));

definePart({"name": "effect-contrails", "kind": "effect", "module": "vidgen/space-effects",
  "label": "vapour trails behind the engines: laid in the world, spreading and breaking up with age, lit by the sun",
  "use": "effects(ship, {flight: ctx.flight, sky, contrails: true})   // above 8 to 9 km; {always: true} anywhere",
  "options": {}, "seed": 1},
(s) => show(s, glider(s), {view: [0.75, 0.35, 0.55], fill: 7, look: [0, 0, -5], velocity: [0, 0, 240], fx: {contrails: {always: true}}, state: {height: 10500}}));

definePart({"name": "effect-exhaust-air", "kind": "effect", "module": "vidgen/space-effects",
  "label": "exhaust in dense air: a sharp core from each bell, a row of shock diamonds, the afterburner on",
  "use": "effects(ship, {flight: ctx.flight, sky, exhaust: true}); ship.update(t, {throttle: 1}); fx.update(t, {boost: 1})",
  "options": {}, "seed": 1},
(s) => show(s, glider(s), {view: [0.85, 0.2, -0.6], fill: 2.6, look: [0, 0, -1.3], fx: {exhaust: true}, craftState: {throttle: 1}, state: {height: 500, boost: 1}}));

definePart({"name": "effect-exhaust-thin", "kind": "effect", "module": "vidgen/space-effects",
  "label": "the same engines 45 km up: the plume widens and pales as the air's pressure falls",
  "use": "fx.update(t)   // the air's density from the flight's height; or {air: 0.004} by hand",
  "options": {}, "seed": 1},
(s) => show(s, glider(s), {view: [0.85, 0.2, -0.6], fill: 2.6, look: [0, 0, -1.3], fx: {exhaust: true}, craftState: {throttle: 1}, state: {height: 45000}}));

definePart({"name": "effect-vapour-cone", "kind": "effect", "module": "vidgen/space-effects",
  "label": "a vapour cone at Mach 0.97 in dense air: a soft disc of mist, there only within about 0.04 of that",
  "use": "effects(ship, {flight: ctx.flight, sky, vapour: true})   // from the flight's Mach number and load",
  "options": {}, "seed": 1},
(s) => show(s, glider(s), {view: [0.9, 0.2, 0.5], fill: 3.0, velocity: [0, 0, 335], fx: {vapour: true}, state: {mach: 0.97, height: 100}}));

definePart({"name": "effect-wing-vapour", "kind": "effect", "module": "vidgen/space-effects",
  "label": "a hard turn (5 g) in dense air: mist over the wings, a thread of vapour from each wing tip",
  "use": "fx.update(t)   // or {load: 5} by hand",
  "options": {}, "seed": 1},
(s) => show(s, glider(s), {view: [0.35, 0.75, -0.6], fill: 3.2, turn: [0, 0, -0.5], velocity: [0, 0, 190], fx: {vapour: true}, state: {load: 5, height: 300}}));
