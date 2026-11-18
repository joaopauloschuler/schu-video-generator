// The joined world of vidgen/space-descent (DESIGN.md §123.13) for the registry vidgen/parts (§122.5): the
// same world from orbit, in the handover and near the ground, and the camera's `descend` at a telling
// moment. An ocean world with fair clouds and a Mars-like desert, each at its own place and sun. Drawn
// straight to the canvas. Measured at 1280x720 in software GL on 2 cores: 0.75 s a frame from orbit (the
// globe and the air), about 3 s in the handover (everything), 1.5 to 1.8 s near the surface.
import * as THREE from "three";
import {definePart} from "vidgen/parts";
import {world} from "vidgen/space-descent";
import {airCamera} from "vidgen/space-camera-air";

const OCEAN = {planet: "earth", at: [8, -150], sun: [38, 250], sea: {state: "breeze"}, clouds: {sky: "fair"}};
const DESERT = {land: "mars", sun: [30, 120]};
// the world and a rig; `view(cam, t)` gives the shot
function joined(s, options, view) {
  s.scene.remove(s.key, s.fill);
  s.camera.near = 2; s.camera.far = 4e7; s.camera.updateProjectionMatrix();
  const w = world(s.renderer, {...options, quality: s.height < 300 ? "fast" : "standard", scene: s.scene, ...(options.sea ? {sea: {...options.sea, seed: s.seed}} : {}), ...(options.clouds ? {clouds: {...options.clouds, seed: s.seed}} : {})});
  s.scene.add(w.object);
  const cam = airCamera({camera: s.camera, ...w.rig});
  return {finish: false, frame(t) { cam.apply(t, view(cam, t)); w.update(t, {camera: s.camera}); }};
}
const fall = (heading, to = 300) => ({seconds: 10, from: 400e3, to, heading, turn: 30, lens: ["normal", "wide"]});

definePart({"name": "joined-ocean-orbit", "kind": "air", "module": "vidgen/space-descent",
  "label": "one world from orbit to the sea: from 400 km only the globe is drawn, seen through the world's own air",
  "use": "const w = world(renderer, {planet: \"earth\", at: [8, -150], sun: [38, 250], sea: {state: \"breeze\"}, clouds: {sky: \"fair\"}, scene}); scene.add(w.object); w.update(t, {camera})",
  "options": {"progress": 0}, "seed": 3},
(s) => joined(s, OCEAN, (cam) => cam.descend(0, {...fall(300), progress: s.options.progress})));

definePart({"name": "joined-ocean-handover", "kind": "air", "module": "vidgen/space-descent",
  "label": "the same world from 12 km: decks and sea near the camera, the globe's picture far off (HANDOVERS.low)",
  "use": "w.stage(12e3)   // {name: \"handover\", globe: true, local: true, below: 0, far: 0.97}; w.state after an update",
  "options": {"progress": 0.5}, "seed": 3},
(s) => joined(s, OCEAN, (cam) => cam.descend(0, {...fall(300), progress: s.options.progress})));

definePart({"name": "joined-desert", "kind": "air", "module": "vidgen/space-descent",
  "label": "a Mars-like desert from 60 km: bare ground holds from orbit, so the globe hands over high (HANDOVERS.high)",
  "use": "const w = world(renderer, {land: \"mars\", sun: [30, 120], scene})   // the planet, the place and the air are the ground's own",
  "options": {"progress": 0.3}, "seed": 3},
(s) => joined(s, DESERT, (cam) => cam.descend(0, {...fall(60, 500), progress: s.options.progress})));

definePart({"name": "camera-descend", "kind": "camera", "module": "vidgen/space-camera-air",
  "label": "descend: from orbit to 300 m in one move, ending level and moving so a skim follows (ascend: back up); a camera's fall, a look",
  "use": "const cam = airCamera({camera, ...w.rig}); const shot = cam.descend(t, {over: [0, 10], from: 400e3, to: 300, heading: 300, turn: 30}); cam.apply(t, shot)   // then cam.skim(t, {over: [10, 14], ...shot.end, follow: 0})",
  "options": {"progress": 0.72}, "seed": 3},
(s) => joined(s, OCEAN, (cam) => cam.descend(0, {...fall(300), progress: s.options.progress})));
