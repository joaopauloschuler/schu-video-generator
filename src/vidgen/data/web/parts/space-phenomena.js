// The ready-made phenomena of vidgen/space-phenomena for the registry vidgen/parts:
// what `vidgen parts` draws on its contact sheet. Drawn straight to the canvas (each
// phenomenon, like the sky, applies the tone curve itself); a small tile bakes small maps. The labels
// carry each part's measured cost: seconds a frame at 1280x720 in software GL on 2 cores, on top of the
// sky and vidgen/three-finish.
import * as THREE from "three";
import {definePart} from "vidgen/parts";
import {planet} from "vidgen/space-bodies";
import {spaceSky} from "vidgen/space-sky";
import {blackHole, wormhole, warp, asteroids, asteroid, comet, aurora} from "vidgen/space-phenomena";

const small = (s) => (s.height < 300 ? {size: 256} : {});
function aim(s, from, to, fov = 40, up = [0, 1, 0]) {
  s.camera.position.set(...from); s.camera.up.set(...up); s.camera.lookAt(...to);
  s.camera.fov = fov; s.camera.updateProjectionMatrix(); s.camera.updateMatrixWorld();
}
function sky(s, options = {}) {
  const made = spaceSky(s.renderer, {seed: s.seed, ...small(s), ...options});
  s.scene.add(made.object);
  return made;
}
// a camera `distance` away from the origin with the sky's galactic centre behind the origin, lifted by `lift`
function before(s, made, distance, lift, fov = 40) {
  const d = made.direction("center"), up = new THREE.Vector3(0, 1, 0), side = new THREE.Vector3().crossVectors(d, up).normalize();
  const from = d.clone().multiplyScalar(-distance).addScaledVector(up, lift[1]).addScaledVector(side, lift[0]);
  aim(s, from.toArray(), [0, 0, 0], fov);
}

definePart({"name": "black-hole", "kind": "phenomenon", "module": "vidgen/space-phenomena",
  "label": "a black hole: bent sky, the disc's far side over and under the shadow (+0.7 to 0.9 s a frame)",
  "use": "const hole = blackHole(renderer, {sky}); scene.add(hole.object); hole.update(t)",
  "options": {"tilt": 0, "temperature": 5400}, "seed": 4},
(s) => {
  const made = sky(s), hole = blackHole(s.renderer, {sky: made, seed: s.seed, ...s.options});
  s.scene.add(hole.object);
  aim(s, [30, 4.5, -24], [1, 0.3, 0], 34);
  return {finish: false, frame(t) { hole.update(t); }};
});

definePart({"name": "black-hole-from-above", "kind": "phenomenon", "module": "vidgen/space-phenomena",
  "label": "the hole from above its disc: gas that turns faster inside, brighter where it comes toward us",
  "use": "blackHole(renderer, {sky, tilt: 0, doppler: 0.7, speed: 0.5})",
  "options": {"doppler": 0.7}, "seed": 4},
(s) => {
  const made = sky(s), hole = blackHole(s.renderer, {sky: made, seed: s.seed, ...s.options});
  s.scene.add(hole.object);
  aim(s, [10, 24, 24], [0, 0, 0], 40);
  return {finish: false, frame(t) { hole.update(t); }};
});

definePart({"name": "einstein-ring", "kind": "phenomenon", "module": "vidgen/space-phenomena",
  "label": "a black hole without a disc before the Milky Way: the band drawn out into a ring (+0.3 s a frame)",
  "use": "blackHole(renderer, {sky, disc: false})",
  "options": {"disc": false}, "seed": 4},
(s) => {
  const made = sky(s), hole = blackHole(s.renderer, {sky: made, ...s.options});
  s.scene.add(hole.object);
  before(s, made, 30, [6, 2]);
  return {finish: false};
});

definePart({"name": "wormhole", "kind": "phenomenon", "module": "vidgen/space-phenomena",
  "label": "a wormhole: a ball that shows another sky, ours bent round its rim (+0.45 s a frame)",
  "use": "const hole = wormhole(renderer, {sky, other: spaceSky(renderer, {seed: 11})}); scene.add(hole.object)",
  "options": {"otherGain": 3, "rim": 0.1}, "seed": 4},
(s) => {
  const made = sky(s), other = spaceSky(s.renderer, {seed: 11, look: "rich", ...small(s)}), hole = wormhole(s.renderer, {sky: made, other, ...s.options});
  s.scene.add(hole.object);
  aim(s, [-4.6, 1.6, 5.2], [-0.4, 0.1, 0], 34);
  return {finish: false};
});

definePart({"name": "wormhole-tunnel", "kind": "phenomenon", "module": "vidgen/space-phenomena",
  "label": "inside a long wormhole: the far sky wound into rings round the way out (+0.45 s a frame)",
  "use": "const state = hole.passage(camera, progress); sky.object.visible = state.side > 0",
  "options": {"length": 30, "progress": 0.45}, "seed": 4},
(s) => {
  const other = spaceSky(s.renderer, {seed: 11, look: "rich", ...small(s)}), made = spaceSky(s.renderer, {seed: s.seed, ...small(s)});
  const hole = wormhole(s.renderer, {sky: made, other, length: s.options.length});
  s.scene.add(hole.object);
  hole.passage(s.camera, s.options.progress, {from: [3.2, 1.2, 7.5]});
  return {finish: false};
});

function jump(s, progress) {
  const made = sky(s), w = warp(s.renderer, {seed: s.seed, fps: s.ctx.fps, ...s.options});
  s.scene.add(w.object);
  aim(s, [0, 0, 0], [0.3, 0.1, -5], 50);
  made.set({brightness: w.update(0, {progress, camera: s.camera}).sky});
  return {finish: false};
}
definePart({"name": "warp-streaks", "kind": "phenomenon", "module": "vidgen/space-phenomena",
  "label": "a jump to warp begins: stars stretch from the point flown at, a burst of light (+0.1 s a frame)",
  "use": "const w = warp(renderer, {seconds: 4, fps: ctx.fps}); scene.add(w.object); w.update(t, {progress, camera})",
  "options": {"seconds": 4}, "seed": 3},
(s) => jump(s, 0.12));

definePart({"name": "warp-tunnel", "kind": "phenomenon", "module": "vidgen/space-phenomena",
  "label": "in the jump: long streaks, soft bands along the tunnel, the light ahead (+0.1 s a frame)",
  "use": "w.update(t, {progress: bars / 8, camera, intensity: 1 + 0.5 * kick})",
  "options": {"seconds": 4}, "seed": 3},
(s) => jump(s, 0.5));

definePart({"name": "asteroid-field", "kind": "phenomenon", "module": "vidgen/space-phenomena",
  "label": "3,000 tumbling rocks to fly through: near ones meshes, far ones points (+0.05 s a frame)",
  "use": "const rocks = asteroids(renderer, {seed, light}); scene.add(rocks.object); rocks.update(t, {camera})",
  "options": {"count": 3000, "size": 120}, "seed": 5},
(s) => {
  sky(s, {seed: 4});
  s.key.position.set(8, 3.5, 4.5); s.key.intensity = 3.1; s.fill.intensity = 0;
  const rocks = asteroids(s.renderer, {seed: s.seed, sun: [0.8, 0.35, 0.45], ...s.options});
  s.scene.add(rocks.object);
  aim(s, [0, 0, 0], [0.2, 0.05, -5], 45);
  return {finish: false, frame(t) { rocks.update(t, {camera: s.camera}); }};
});

definePart({"name": "asteroid-belt", "kind": "phenomenon", "module": "vidgen/space-phenomena",
  "label": "a belt of 16,000 rocks round a world, from afar points and a band of dust (+0.05 s a frame)",
  "use": "asteroids(renderer, {layout: \"belt\", inner: 42, outer: 90, light})",
  "options": {"inner": 42, "outer": 90, "thickness": 4}, "seed": 3},
(s) => {
  sky(s, {look: "sparse"});
  const sun = [0.7, 0.3, 0.65], world = planet(s.renderer, "jupiter", {...small(s), sun});
  world.object.scale.setScalar(16); s.scene.add(world.object);
  const rocks = asteroids(s.renderer, {layout: "belt", seed: s.seed, sun, ...s.options});
  s.scene.add(rocks.object);
  s.key.position.set(...sun); s.fill.intensity = 0;
  aim(s, [0, 40, 190], [6, -6, 0], 40);
  return {finish: false, frame(t) { world.update(t); rocks.update(t, {camera: s.camera}); }};
});

definePart({"name": "asteroid", "kind": "phenomenon", "module": "vidgen/space-phenomena",
  "label": "one asteroid for a close-up: craters, facets, shadows on itself (+0.1 s a frame, 2 s to make)",
  "use": "const rock = asteroid({seed}); scene.add(rock.object); rock.update(t)",
  "options": {"detail": 64, "craters": 40}, "seed": 7},
(s) => {
  sky(s, {look: "sparse"});
  s.key.position.set(9.5, 3, 1); s.key.intensity = 3.1; s.fill.intensity = 0;
  const rock = asteroid({seed: s.seed, ...s.options, ...(s.height < 300 ? {detail: 32} : {})});
  s.scene.add(rock.object);
  aim(s, [0.4, 0.5, 3.6], [0, 0, 0], 40);
  return {finish: false, frame(t) { rock.update(t); }};
});

definePart({"name": "comet", "kind": "phenomenon", "module": "vidgen/space-phenomena",
  "label": "a comet: a curved yellowish dust tail and a straight blue ion tail away from the sun (+0.05 s a frame)",
  "use": "const c = comet(renderer); scene.add(c.object); c.update(t, {sun, velocity, activity: 1})",
  "options": {"length": 30, "ionLength": 52}, "seed": 2},
(s) => {
  sky(s, {look: "sparse"});
  const c = comet(s.renderer, {seed: s.seed, ...s.options});
  s.scene.add(c.object);
  aim(s, [6, 2, 62], [12, 6, 0], 40);
  return {finish: false, frame(t) { c.update(t, {sun: [-0.85, -0.45, 0.3], velocity: [-0.3, 0.9, 0.3], activity: 1}); }};
});

definePart({"name": "aurora", "kind": "phenomenon", "module": "vidgen/space-phenomena",
  "label": "an aurora: green curtains with red tops round a world's magnetic pole (+0.1 to 0.2 s a frame)",
  "use": "const lights = aurora(world, {latitude: 68}); lights.update(t)",
  "options": {"latitude": 68, "brightness": 1}, "seed": 1},
(s) => {
  sky(s, {look: "sparse"});
  const world = planet(s.renderer, "earth", {...small(s), spin: 0, tilt: 0, sun: [0.5, -0.12, -1]});
  s.scene.add(world.object);
  const lights = aurora(world, {seed: s.seed, ...s.options});
  aim(s, [-0.45, 2.3, 1.35], [0.05, 0.85, 0], 40);
  return {finish: false, frame(t) { world.update(t); lights.update(t); }};
});
