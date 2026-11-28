// The framings of vidgen/space-camera for the registry vidgen/parts: each
// tile is one move at its key moment, in a plain three.js scene (an Earth-like world of radius 1, a far
// sun, the sky), so `vidgen parts --kind camera` shows what a move's frame looks like before a page is
// written. Drawn straight to the canvas; a small tile bakes small maps.
import {definePart} from "vidgen/parts";
import {planet} from "vidgen/space-bodies";
import {spaceSky} from "vidgen/space-sky";
import {star, spaceLight} from "vidgen/space-light";
import {spaceCamera} from "vidgen/space-camera";

const SUN = [0.8, 0.2, -0.5];
// the world, the sun and the sky; `view(cam, earth, t)` gives the shot
function shot(s, view) {
  const sky = spaceSky(s.renderer, {seed: 4}), earth = planet(s.renderer, "earth", {spin: 0, ...(s.height < 300 ? {size: 256} : {})});
  const sun = star(s.renderer, "sun", {direction: SUN, flare: 0.6});
  s.scene.add(sky.object, earth.object, sun.object);
  const cam = spaceCamera({camera: s.camera, sun: SUN, bodies: [earth]}), light = spaceLight({scene: s.scene, camera: s.camera, sun, bodies: [earth], sky});
  return {finish: false, frame(t) { cam.apply(t, view(cam, earth, t)); earth.update(t); sun.update(t); light.update(t); }};
}

definePart({"name": "camera-three-quarter", "kind": "camera", "module": "vidgen/space-camera",
  "label": "arc: a world three-quarter lit, on the third away from the sun",
  "use": "const cam = spaceCamera({space, camera}); cam.apply(t, cam.arc(t, {subject: \"Earth\", phase: \"three-quarter\", distance: {radii: 5}}))",
  "options": {"phase": "three-quarter", "radii": 5}},
(s) => shot(s, (cam, earth, t) => cam.arc(t, {subject: earth, phase: s.options.phase, distance: {radii: s.options.radii}})));

definePart({"name": "camera-crescent", "kind": "camera", "module": "vidgen/space-camera",
  "label": "arc: a thin crescent with the sun just off the limb, in one line",
  "use": "cam.arc(t, {subject: \"Earth\", phase: {limb: 0.12}, distance: {radii: 5}})  // or phase: \"crescent\"; [from, to] with over: [a, b] moves",
  "options": {"limb": 0.12, "radii": 5}},
(s) => shot(s, (cam, earth, t) => cam.arc(t, {subject: earth, phase: {limb: s.options.limb}, distance: {radii: s.options.radii}})));

definePart({"name": "camera-fly-by", "kind": "camera", "module": "vidgen/space-camera",
  "label": "fly-by: just before the closest pass, the world gliding across the frame, a slight bank",
  "use": "cam.flyBy(t, {subject: \"Earth\", over: [0, 8], closest: {radii: 2.4}, side: \"left\", roll: 8})",
  "options": {"progress": 0.4, "closest": 2.4, "roll": 8}},
(s) => shot(s, (cam, earth, t) => cam.flyBy(t, {subject: earth, progress: s.options.progress, closest: {radii: s.options.closest}, side: "left", roll: s.options.roll})));

definePart({"name": "camera-arrival", "kind": "camera", "module": "vidgen/space-camera",
  "label": "arrival: the end of the sweep into a low orbit, the limb level across the bottom",
  "use": "cam.arrive(t, {subject: \"Earth\", over: [0, 8], lens: \"wide\"})  // sunAhead: 9 arrives at a sunrise",
  "options": {"progress": 1, "sunAhead": 140}},
(s) => shot(s, (cam, earth, t) => cam.arrive(t, {subject: earth, progress: s.options.progress, sunAhead: s.options.sunAhead, lens: "wide"})));

definePart({"name": "camera-sunrise", "kind": "camera", "module": "vidgen/space-camera",
  "label": "reveal: the sun over a world's limb, its first light timed to the second (here 1.2 s after it)",
  "use": "cam.reveal(t, {behind: \"Earth\", at: 4 * bar, rate: 0.5, air: 0.1, lens: \"wide-normal\"})  // of: \"Moon\" for a moonrise",
  "options": {"after": 1.2, "rate": 0.5}},
(s) => shot(s, (cam, earth, t) => cam.reveal(s.options.after, {behind: earth, at: 0, rate: s.options.rate, lens: "wide-normal"})));
