// The moves of vidgen/space-camera-air for the registry vidgen/parts: each tile
// is one move at a telling moment, so `vidgen parts 'camera-*'` shows what its frame looks like before a
// page is written. Air moves: an Earth-like air over a breeze sea (a plane on a flight made by hand: a
// steady banked turn); ship moves: a dressed carrier of seed 1 scaled to the tile, under one hard sun.
// Drawn straight to the canvas. Measured at 1280x720 in software GL on 2 cores: 0.8 to 2.1 s a frame.
import * as THREE from "three";
import {definePart} from "vidgen/parts";
import {air, sunDirection} from "vidgen/space-air";
import {sea} from "vidgen/space-sea";
import {clouds} from "vidgen/space-clouds";
import {plane} from "vidgen/space-plane";
import {paintedEnvironment} from "vidgen/space-craft";
import {hull} from "vidgen/space-hull";
import {dress} from "vidgen/space-hull-detail";
import {airCamera} from "vidgen/space-camera-air";

const RAD = Math.PI / 180;
// a flight by hand: a steady turn to the right at `speed` m/s, `rate` degrees a second, banked `bank` degrees
function turning({at = [0, 320, 0], heading = 60, speed = 150, rate = 3.2, bank = 28} = {}) {
  const w = rate * RAD, state = (t) => {
    const h = heading * RAD + w * t, o = new THREE.Object3D();
    o.rotation.set(0, Math.atan2(Math.sin(h), -Math.cos(h)), 0); o.rotateZ(bank * RAD);
    return {position: [at[0] - (speed / w) * (Math.cos(h) - Math.cos(heading * RAD)), at[1], at[2] - (speed / w) * (Math.sin(h) - Math.sin(heading * RAD))],
      velocity: [speed * Math.sin(h), 0, -speed * Math.cos(h)], quaternion: o.quaternion.toArray()};
  };
  return {name: "Plane", position: (t) => state(t).position, velocity: (t) => state(t).velocity, quaternion: (t) => state(t).quaternion, bank: () => bank};
}
// the air, a sea, clouds when asked and a plane on the turn when asked; `view(cam, t, flight)` gives the shot
function inAir(s, view, {sun = [16, 250], weather = null, craft = false} = {}) {
  s.scene.remove(s.key, s.fill);
  s.camera.near = craft ? 0.4 : 2; s.camera.far = 4e6; s.camera.updateProjectionMatrix();
  const sky = air(s.renderer, "earth", {sun: sunDirection(...sun), scene: s.scene}), water = sea(s.renderer, sky, {state: "breeze", seed: s.seed});
  s.scene.add(sky.object, water.object);
  const decks = weather ? clouds(s.renderer, sky, {seed: s.seed, ...weather}) : null;
  if (decks) s.scene.add(decks.object);
  const flight = craft ? turning() : null, ship = craft ? plane("glider", {seed: 2, detail: s.height < 300 ? "far" : "near"}) : null;
  if (ship) { s.scene.add(ship.object); for (const m of Object.values(ship.materials)) sky.haze(m); }
  const cam = airCamera({camera: s.camera, sky, water, clouds: decks, crafts: ship ? {Plane: ship} : {}});
  return {finish: false, frame(t) {
    if (ship) { ship.object.position.set(...flight.position(t)); ship.object.quaternion.set(...flight.quaternion(t)); ship.update(t); }
    cam.apply(t, view(cam, t, flight));
    sky.update(t, {camera: s.camera}); water.update(t, {camera: s.camera});
    if (decks) decks.update(t, {camera: s.camera});
  }};
}
// a dressed carrier scaled to the tile; `view(cam, t)` gives the shot, `state(shot)` what the ship does
function beside(s, view, {sun = [5, 5.5, 4], throttle = null} = {}) {
  const h = hull("carrier", {seed: 1, detail: s.height < 300 ? "far" : "near"}), d = dress(h, s.renderer, {}), k = 3.5 / h.size.radius, light = new THREE.Vector3(...sun).normalize();
  h.object.scale.setScalar(k); s.scene.add(h.object);
  s.key.color.set(0xffffff); s.key.intensity = Math.PI; s.key.position.copy(light).multiplyScalar(12); s.fill.intensity = 0;
  const shine = new THREE.DirectionalLight(0x9fc0ff, 0.25); shine.position.set(-0.4, -1, 0.3); s.scene.add(shine);
  s.scene.environment = paintedEnvironment(s.renderer).texture;
  s.camera.near = 0.004; s.camera.far = 400; s.camera.updateProjectionMatrix();
  const cam = airCamera({camera: s.camera, ships: {Ship: h}});
  return {frame(t) { const shot = cam.apply(t, view(cam, t)); h.update(t, {sun: light, throttle: throttle ? throttle(shot) : 0}); d.update(t, {lights: 1}); }};
}

definePart({"name": "camera-skim", "kind": "camera", "module": "vidgen/space-camera-air",
  "label": "skim: a low pass over the sea at a stated clearance, banking into a turn towards the sun",
  "use": "const cam = airCamera({camera, sky, ground, water}); cam.apply(t, cam.skim(t, {over: [0, 8], heading: 284, speed: 90, clearance: 14, turn: 14}))",
  "options": {"progress": 0.5}, "seed": 3},
(s) => inAir(s, (cam) => cam.skim(0, {progress: s.options.progress, seconds: 4, heading: 240, speed: 90, clearance: 14, turn: 14, lens: "wide"}), {sun: [5, 252]}));

definePart({"name": "camera-climb-through", "kind": "camera", "module": "vidgen/space-camera-air",
  "label": "climbThrough: up through a cloud deck's fog and out over its top into the sun (descendThrough: back down)",
  "use": "cam.climbThrough(t, {over: [0, 14], deck: 0, heading: 40, adapt: 1})   // air(..., {ev: (t) => shotNow.ev}): no white flash",
  "options": {"progress": 0.72}, "seed": 4},
(s) => inAir(s, (cam) => cam.climbThrough(0, {progress: s.options.progress, seconds: 14, heading: 40, below: 300, above: 500, lens: "wide"}),
  {sun: [14, 40], weather: {decks: [{type: "stratus", base: 1500, top: 2300}, {type: "cirrus", base: 11000}]}}));

definePart({"name": "camera-chase", "kind": "camera", "module": "vidgen/space-camera-air",
  "label": "chase: behind and above a plane on its flight, following with a lag and rolling with half its bank",
  "use": "const cam = airCamera({camera, sky, ground, flight: ctx.flight, crafts: {Plane: ship}}); cam.apply(t, cam.chase(t, {flight: \"Plane\"}))",
  "options": {}, "seed": 3, "at": 3},
(s) => inAir(s, (cam, t, flight) => cam.chase(t, {flight, lens: "wide-normal"}), {sun: [30, 200], craft: true}));

definePart({"name": "camera-wing", "kind": "camera", "module": "vidgen/space-camera-air",
  "label": "wing: locked to the plane's own frame: its wing tip, the world tilting as it banks (also tail, belly, nose)",
  "use": "cam.wing(t, {flight: \"Plane\", view: \"wingtip\", side: \"right\"})   // view: \"belly\" looks back up at the tiles on a re-entry",
  "options": {"view": "wingtip"}, "seed": 3, "at": 3},
(s) => inAir(s, (cam, t, flight) => cam.wing(t, {flight, view: s.options.view, side: "right"}), {sun: [30, 200], craft: true}));

definePart({"name": "camera-fly-past", "kind": "camera", "module": "vidgen/space-camera-air",
  "label": "flyPast: a camera standing over the water turns with the plane as it passes (a whip-pan at the pass)",
  "use": "cam.flyPast(t, {flight: \"Plane\", at: {bar: 9}, closest: 100, side: \"right\", stand: \"ground\", eye: 3})",
  "options": {"before": 0.35}, "seed": 3, "at": 3},
(s) => inAir(s, (cam, t, flight) => cam.flyPast(t, {flight, at: t + s.options.before, closest: 100, side: "right", rise: -40, lens: "wide-normal"}), {sun: [30, 200], craft: true}));

definePart({"name": "camera-orbit-peak", "kind": "camera", "module": "vidgen/space-camera-air",
  "label": "orbitPeak: circling a tower of cloud (or a mountain: around: {near: [x, z]}) and keeping it in the frame",
  "use": "cam.orbitPeak(t, {over: [0, 12], around: {tower: 0}, sweep: 40})   // or around: {near: [0, 0], reach: 20000}, radius: 9000",
  "options": {"progress": 0.5}, "seed": 4},
(s) => inAir(s, (cam) => cam.orbitPeak(0, {progress: s.options.progress, seconds: 12, around: {tower: 0}, sweep: 40, height: -2500}), {sun: [24, 120], weather: {sky: "towers"}}));

definePart({"name": "camera-rise", "kind": "camera", "module": "vidgen/space-camera-air",
  "label": "rise: a crane up from the surface to 60 km, the lens widening, the horizon held as the curve appears",
  "use": "cam.rise(t, {over: [0, 10], at: [0, 0], from: 15, to: 60000, heading: 300, lens: [\"normal\", \"ultra-wide\"]})   // down: true: the same move back",
  "options": {"progress": 0.86}, "seed": 3},
(s) => inAir(s, (cam) => cam.rise(0, {progress: s.options.progress, seconds: 8, from: 15, to: 60000, heading: 300, lens: ["normal", "ultra-wide"]}), {sun: [22, 250], weather: {sky: "fair"}}));

definePart({"name": "camera-hull-pass", "kind": "camera", "module": "vidgen/space-camera-air",
  "label": "hullPass: a slow pass 60 m off a hull's wall with a wide lens, the path made from the hull's regions",
  "use": "const cam = airCamera({space, camera, ships: {Ship: ship}}); cam.apply(t, cam.hullPass(t, {ship: \"Ship\", over: [0, 20], side: \"port\", standoff: 60, speed: 40}))",
  "options": {"progress": 0.5}, "seed": 1},
(s) => beside(s, (cam) => cam.hullPass(0, {progress: s.options.progress, seconds: 20, from: 0.3, speed: 40}), {sun: [0.3, 0.25, 0.9]}));

definePart({"name": "camera-hull-reveal", "kind": "camera", "module": "vidgen/space-camera-air",
  "label": "hullReveal: the bow slides in over the camera and the hull keeps coming (mode \"limb\": from behind a world)",
  "use": "cam.hullReveal(t, {ship: \"Ship\", at: {bar: 5}, lane: 200})   // shot.escort: where a small craft enters last, for scale",
  "options": {"after": 9}, "seed": 1},
(s) => beside(s, (cam) => cam.hullReveal(s.options.after, {at: 0, lane: 200}), {sun: [0.5, -0.2, 0.75]}));

definePart({"name": "camera-into-bay", "kind": "camera", "module": "vidgen/space-camera-air",
  "label": "intoBay: an approach to a hangar's mouth at an angle, then inside (out: true pulls out of it)",
  "use": "cam.intoBay(t, {ship: \"Ship\", hangar: \"hangar-2\", over: [0, 10]})",
  "options": {"progress": 0.66}, "seed": 1},
(s) => beside(s, (cam) => cam.intoBay(0, {progress: s.options.progress, hangar: "hangar-2"}), {sun: [0.2, 0.75, 0.6]}));

definePart({"name": "camera-stern-burn", "kind": "camera", "module": "vidgen/space-camera-air",
  "label": "sternBurn: behind the engine bank as it lights on a bar; the camera is pushed back (a shake on request)",
  "use": "const shot = cam.sternBurn(t, {ship: \"Ship\", over: [0, 8], light: {bar: 3}, shake: {amount: 0.3}}); ship.update(t, {sun, throttle: shot.throttle})",
  "options": {"after": 1.2}, "seed": 1},
(s) => beside(s, (cam) => cam.sternBurn(s.options.after, {light: 0, over: [-2, 4]}), {sun: [0.5, 0.6, -0.35], throttle: (shot) => shot.throttle}));

definePart({"name": "camera-scale-zoom", "kind": "camera", "module": "vidgen/space-camera-air",
  "label": "scaleZoom: powers of ten from a place on the hull to the whole ship (with world: on to a speck by it)",
  "use": "cam.scaleZoom(t, {ship: \"Ship\", window: \"hangar-2\", close: 80, world: \"Earth\", over: [0, 8]})",
  "options": {"seconds": 1.6}, "seed": 1},
(s) => beside(s, (cam) => cam.scaleZoom(s.options.seconds, {window: "hangar-2", close: 80, over: [0, 3]})));
