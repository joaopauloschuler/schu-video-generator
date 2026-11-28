// The space planes of vidgen/space-plane for the registry vidgen/parts: what
// `vidgen parts` draws on its contact sheet: every ready-made plane (kind "craft") and the plane kit's parts
// and surfaces (kind "craft-part"), under the same light as the craft of vidgen/space-craft: one hard sun
// with its shadows, a faint planet-shine from below, a painted environment for the metal; a small tile
// draws the plane at its "far" detail. Measured at 1280x720 in software GL on 2 cores: a plane that fills
// the frame adds 0.12 to 0.2 s a frame (its shadows 0.03 to 0.05 s of that), 0.02 to 0.07 s at 320x180.
import * as THREE from "three";
import {definePart} from "vidgen/parts";
import {paintedEnvironment} from "vidgen/space-craft";
import {plane, planeKit, planeFleet, WINGS} from "vidgen/space-plane";

const SUN = new THREE.Vector3(5, 4.5, 4).normalize();
const detail = (s) => (s.height < 300 ? "far" : "near");
// the tile's light and camera for `object` of `radius` metres: scaled to fill the tile, seen from `view`
function show(s, object, radius, view = [0.62, 0.4, 0.7], fill = 3.1) {
  const k = fill / radius, d = new THREE.Vector3(...view).normalize().multiplyScalar(7.6);
  object.scale.setScalar(k); s.scene.add(object);
  s.key.color.set(0xffffff); s.key.intensity = Math.PI; s.key.position.copy(SUN).multiplyScalar(12); s.fill.intensity = 0;
  s.key.castShadow = true; s.key.shadow.mapSize.set(1024, 1024); s.key.shadow.bias = -0.0005; s.key.shadow.normalBias = 0.01;
  const c = s.key.shadow.camera; c.left = c.bottom = -3.4; c.right = c.top = 3.4; c.near = 2; c.far = 24; c.updateProjectionMatrix();
  s.renderer.shadowMap.enabled = true;
  const shine = new THREE.DirectionalLight(0x9fc0ff, 0.5); shine.position.set(-0.4, -1, 0.3); s.scene.add(shine);
  s.scene.environment = paintedEnvironment(s.renderer).texture;
  s.camera.position.copy(d); s.camera.lookAt(0, 0, 0); s.camera.fov = 34; s.camera.updateProjectionMatrix(); s.camera.updateMatrixWorld();
}
// a ready-made plane from three quarters ahead
function ready(s, kind, options = {}, {view, fill = 3.3, state = {}, turn = [0, 0, 0]} = {}) {
  const p = plane(kind, {seed: s.seed, detail: detail(s), ...options, ...s.options});
  p.object.rotation.set(...turn);
  show(s, p.object, p.size.radius, view, fill);
  return {frame(t) { p.update(t, {sun: SUN, ...state}); }};
}
// things side by side: `make(kit)` returns [[an Object3D, its radius], ...]
function row(s, make, {kit = {}, view, fill = 3.6, gap = 1.1, turn = [0, 0, 0], radius = null} = {}) {
  const k = planeKit({seed: s.seed, detail: detail(s), ...kit, ...s.options}), list = make(k), group = new THREE.Group();
  const width = list.reduce((w, [, r]) => w + 2 * r * gap, 0);
  let x = -width / 2;
  for (const [object, r] of list) { object.position.x += x + r * gap; x += 2 * r * gap; group.add(object); }
  group.rotation.set(...turn);
  show(s, group, radius ?? width / 2, view, fill);
  return {frame(t) { for (const [object] of list) if (object.userData.craft) object.userData.craft.update(t, {sun: SUN}); }};
}

definePart({"name": "plane-glider", "kind": "craft", "module": "vidgen/space-plane",
  "label": "a small crewed orbital glider: chined nose, a delta low on a flat belly, two fins, a bay (22 to 30 m)",
  "use": "const ship = plane(\"glider\", {seed: 1}); scene.add(ship.object); ship.update(t, {sun})",
  "options": {}, "seed": 1},
(s) => ready(s, "glider"));

definePart({"name": "plane-freighter", "kind": "craft", "module": "vidgen/space-plane",
  "label": "a large cargo spaceplane: wide low body, cabin hump, drooping wings, pods, a long bay (56 to 74 m)",
  "use": "plane(\"freighter\", {seed: 2})",
  "options": {}, "seed": 2},
(s) => ready(s, "freighter"));

definePart({"name": "plane-needle", "kind": "craft", "module": "vidgen/space-plane",
  "label": "a single-stage needle: engines inside behind a belly intake, cranked wing, vee tail (60 to 78 m)",
  "use": "plane(\"needle\", {seed: 1})",
  "options": {}, "seed": 1},
(s) => ready(s, "needle"));

definePart({"name": "plane-lifter", "kind": "craft", "module": "vidgen/space-plane",
  "label": "a lifting-body shuttle: wide flat-bellied body, blended wings with tall tip fins (16 to 22 m)",
  "use": "plane(\"lifter\", {seed: 1})",
  "options": {}, "seed": 1},
(s) => ready(s, "lifter"));

definePart({"name": "plane-scout", "kind": "craft", "module": "vidgen/space-plane",
  "label": "a scout for other worlds, no crew: long thin wings for thin air, a vee tail (span 17 to 32 m)",
  "use": "plane(\"scout\", {seed: 1})",
  "options": {}, "seed": 1},
(s) => ready(s, "scout", {}, {fill: 3.9}));

definePart({"name": "plane-skiff", "kind": "craft", "module": "vidgen/space-plane",
  "label": "a small air-launched skiff: swept wings with winglets, canards, two fins, one bell (12 to 17 m)",
  "use": "plane(\"skiff\", {seed: 3})",
  "options": {}, "seed": 3},
(s) => ready(s, "skiff"));

definePart({"name": "plane-open", "kind": "craft", "module": "vidgen/space-plane",
  "label": "the glider in orbit trim: bay doors open on their radiators, the engines firing, thrusters",
  "use": "ship.update(t, {bay: 1, throttle: 1})   // bay 0..1: the doors' opening",
  "options": {}, "seed": 3},
(s) => ready(s, "glider", {}, {view: [0.45, 0.75, 0.5], fill: 2.9, state: {bay: 1, throttle: 0.8}}));

definePart({"name": "plane-landing", "kind": "craft", "module": "vidgen/space-plane",
  "label": "gear down, flaps and body flap down, brakes open: every moving surface set by hand",
  "use": "ship.update(t, {gear: 1, controls: {flap: 25, elevon: -8, bodyFlap: 12, brake: 40, rudder: 6}})",
  "options": {}, "seed": 2},
(s) => ready(s, "glider", {}, {view: [0.8, -0.1, 0.55], state: {gear: 1, controls: {flap: 25, elevon: -8, bodyFlap: 12, brake: 40, rudder: 6}}}));

definePart({"name": "plane-fleet", "kind": "craft", "module": "vidgen/space-plane",
  "label": "a formation from seeds: six gliders, each its own proportions, scheme and stripes, at \"far\" detail",
  "use": "const team = planeFleet(\"glider\", {count: 6, seed: 1}); scene.add(team.object); team.update(t, {sun})",
  "options": {"count": 6}, "seed": 1},
(s) => {
  const f = planeFleet("glider", {seed: s.seed, ...s.options}), box = new THREE.Box3().setFromObject(f.object), mid = box.getCenter(new THREE.Vector3()), holder = new THREE.Group();
  f.object.position.sub(mid); holder.add(f.object);
  show(s, holder, 0.5 * box.getSize(new THREE.Vector3()).length(), [0.5, 0.55, 0.7], 4.4);
  return {frame(t) { f.update(t, {sun: SUN}); }};
});

definePart({"name": "plane-part-bodies", "kind": "craft-part", "module": "vidgen/space-plane",
  "label": "bodies: ogive and round, blunt with a flat belly and a hump, chined and flat, a needle; nose caps",
  "use": "const kit = planeKit({seed: 1}); kit.body({length: 24, width: 3.6, nose: \"chined\", belly: 0.8})",
  "options": {}, "seed": 1},
(s) => row(s, (kit) => [
  kit.body({length: 20, width: 3.2, nose: "ogive", belly: 0.2, waterline: 16}),
  kit.body({length: 20, width: 4.6, height: 3, nose: "blunt", belly: 0.9, droop: 0.22, hump: {from: 0.08, to: 0.4, height: 0.28}, tail: 0.9, upsweep: 0.9}),
  kit.body({length: 20, width: 3.8, height: 2.8, nose: "chined", noseLength: 0.4, belly: 0.8}),
  kit.body({length: 20, width: 2, nose: "needle", noseLength: 0.5, belly: 0.3, tail: 0.5})].map((b) => [kit.plane(b).object, 3]), {radius: 17, view: [0.75, 0.5, 0.6], fill: 3.9}));

definePart({"name": "plane-part-wings", "kind": "craft-part", "module": "vidgen/space-plane",
  "label": "one wing, nine presets: delta, double-delta, cranked-arrow, swept, straight, ogival, stub, blended, long",
  "use": "const wing = kit.wing({preset: \"double-delta\", span: 15, dihedral: 3}); wing.position.set(0, -0.9, 2); body.add(wing)",
  "options": {}, "seed": 3},
(s) => row(s, (kit) => Object.keys(WINGS).map((preset) => {
  const span = preset === "long" ? 20 : preset === "stub" || preset === "blended" ? 9 : 14, w = kit.wing({preset, span});
  w.position.z = 0.5 * w.userData.wing.options.rootChord;
  return [w, span / 2];
}), {view: [0, 1, 0.12], gap: 1.08, fill: 4.2}));

definePart({"name": "plane-part-tails", "kind": "craft-part", "module": "vidgen/space-plane",
  "label": "tails with rudders: one fin, two fins leaning out, a vee; winglets and tip fins belong to the wing",
  "use": "kit.fin({type: \"twin\", height: 4, rootChord: 5, cant: 20, spacing: 3})   // or wing({tip: {height: 3, cant: 65}})",
  "options": {}, "seed": 1},
(s) => row(s, (kit) => [
  [kit.fin({type: "single", height: 4.5, rootChord: 5, sink: 0}), 3],
  [kit.fin({type: "twin", height: 4, rootChord: 4.5, cant: 20, spacing: 3, sink: 0}), 3.6],
  [kit.fin({type: "vee", height: 4, rootChord: 4, spacing: 1.2, sink: 0}), 3.8],
  [kit.wing({preset: "swept", span: 9, tip: {height: 2.2, cant: 65}}), 4.6]].map(([p, r]) => { p.position.y = -1.5; return [p, r]; }), {view: [0.7, 0.3, 0.65]}));

definePart({"name": "plane-part-engines", "kind": "craft-part", "module": "vidgen/space-plane",
  "label": "engines: a row and a block of bells for the tail, an air-breathing pod on its pylon, a belly intake",
  "use": "kit.nozzles({count: 3, exit: 0.6, layout: \"row\"}); kit.nacelle({length: 6, radius: 0.8}); kit.intake({width: 3, height: 0.8})",
  "options": {}, "seed": 1},
(s) => row(s, (kit) => [
  [kit.nozzles({count: 3, exit: 0.6}), 2.2], [kit.nozzles({count: 4, exit: 0.5, layout: "block"}), 1.6],
  [kit.nacelle({length: 6, radius: 0.8, pylon: 0.5}), 3.1], [kit.intake({width: 3, height: 0.8, length: 5}), 2.6]], {view: [0.75, 0.35, 0.56]}));

definePart({"name": "plane-part-gear", "kind": "craft-part", "module": "vidgen/space-plane",
  "label": "landing gear on a body: legs that fold into wells behind doors (gear 0..1), and a problems() check",
  "use": "ship.gear(1)   // or update(t, {gear}); ship.problems() names gear that does not reach below the belly",
  "options": {}, "seed": 4},
(s) => ready(s, "lifter", {}, {view: [0.7, -0.1, 0.7], state: {gear: 1}}));

definePart({"name": "plane-surfaces", "kind": "craft-part", "module": "vidgen/space-plane",
  "label": "schemes: tiles (white blankets over black tiles), grey, metal, paint, plain; scorch 0.8 behind the caps",
  "use": "planeKit({scheme: \"metal\", scorch: 0.8, accent: 0x2f5fa8})   // or plane(kind, {scheme, scorch, color, belly})",
  "options": {}, "seed": 2},
(s) => {
  const list = ["tiles", "grey", "metal", "paint", "plain"].map((scheme) => plane("skiff", {seed: s.seed, detail: detail(s), scheme, scorch: 0.8, ...s.options})), group = new THREE.Group();
  list.forEach((p, i) => { p.object.position.set((i - 2) * 11.5, 0, 0); p.object.rotation.set(0.2, 0.5, 0); group.add(p.object); });
  show(s, group, 32, [0.2, 0.5, 0.85], 4.3);
  return {frame(t) { for (const p of list) p.update(t, {sun: SUN}); }};
});
