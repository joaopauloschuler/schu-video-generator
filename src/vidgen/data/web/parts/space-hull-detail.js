// The fine detail of giant hulls, vidgen/space-hull-detail (DESIGN.md §123.11), for the registry vidgen/parts
// (§122.5): what `vidgen parts` draws on its contact sheet: a dressed hull by day and by night, a hangar bay
// seen from outside, a bank of bells with its long plume, a dressed fleet (kind "craft") and the tiling maps
// (kind "craft-part"), under one hard sun with a faint planet-shine. A hull is kilometres long: the tile scales
// it to fit. Measured at 1280x720 in software GL on 2 cores: a dressed hull that fills the frame from two
// kilometres off costs about 1.0 s a frame (0.7 s bare).
import * as THREE from "three";
import {definePart} from "vidgen/parts";
import {paintedEnvironment} from "vidgen/space-craft";
import {hull, hullFleet} from "vidgen/space-hull";
import {dress, dressFleet, detailMap, KINDS} from "vidgen/space-hull-detail";

const detail = (s) => (s.height < 300 ? "far" : "near");
// the tile's light and camera: `object` of `radius` metres scaled to fill the tile; the camera at `from` looking
// at `to` (metres in the hull's axes) or, without them, from the direction `view`
function show(s, object, radius, {view = [0.62, 0.42, 0.66], fill = 3.5, from = null, to = [0, 0, 0], sun = [5, 5.5, 4], fov = 34} = {}) {
  const k = fill / radius, light = new THREE.Vector3(...sun).normalize();
  object.scale.setScalar(k); s.scene.add(object);
  s.key.color.set(0xffffff); s.key.intensity = Math.PI; s.key.position.copy(light).multiplyScalar(12); s.fill.intensity = 0;
  s.key.castShadow = true; s.key.shadow.mapSize.set(2048, 2048); s.key.shadow.bias = -0.0006; s.key.shadow.normalBias = 0.01;
  const c = s.key.shadow.camera; c.left = c.bottom = -3.6; c.right = c.top = 3.6; c.near = 2; c.far = 24; c.updateProjectionMatrix();
  s.renderer.shadowMap.enabled = true;
  const shine = new THREE.DirectionalLight(0x9fc0ff, 0.25); shine.position.set(-0.4, -1, 0.3); s.scene.add(shine);
  s.scene.environment = paintedEnvironment(s.renderer).texture;
  if (from) s.camera.position.set(...from).multiplyScalar(k); else s.camera.position.set(...view).normalize().multiplyScalar(7.6);
  s.camera.lookAt(new THREE.Vector3(...to).multiplyScalar(k)); s.camera.fov = fov; s.camera.near = 0.01; s.camera.updateProjectionMatrix(); s.camera.updateMatrixWorld();
  return light;
}
function dressed(s, family, options, look, state = {}, own = {}) {
  const h = hull(family, {seed: s.seed, detail: detail(s), ...own}), d = dress(h, s.renderer, {...options, ...s.options}), sun = show(s, h.object, h.size.radius, look);
  return {frame(t) { h.update(t, {sun, throttle: state.throttle ?? 0}); d.update(t, {lights: state.lights ? state.lights(t) : 1}); }};
}

definePart({"name": "hull-dressed", "kind": "craft", "module": "vidgen/space-hull-detail",
  "label": "a hull with its fine detail: seams, hatches, pipe runs, deck clutter, marks, lit bays, lamps",
  "use": "const ship = hull(\"carrier\", {seed: 1}); const detail = dress(ship, renderer); ship.update(t, {sun}); detail.update(t)",
  "options": {}, "seed": 1},
(s) => dressed(s, "carrier", {}, {}));

definePart({"name": "hull-windows", "kind": "craft", "module": "vidgen/space-hull-detail",
  "label": "the night side: windows by the thousand in rows along the decks, banks coming on with `lights`",
  "use": "detail.update(t, {lights: 0.4 + 0.6 * ctx.music.level(t), light})   // light: the spaceLight, for an honest exposure",
  "options": {}, "seed": 1},
(s) => dressed(s, "carrier", {}, {from: [1300, 300, 900], to: [400, 50, 0], sun: [-0.7, 0.3, -0.6], fov: 40}, {lights: (t) => 0.5 + 0.5 * Math.sin(t * 1.3)}));

definePart({"name": "hull-bay", "kind": "craft", "module": "vidgen/space-hull-detail",
  "label": "a hangar bay from outside: lit floor with marks, ribbed wall, parked craft, cargo, guide lamps",
  "use": "dress(ship, renderer, {hangars: {craft: 1, cargo: 1, curtain: 0.25}})   // detail.fly(ship.scaleRef(\"ship\", {at: \"hangar-2\"}), \"hangar-2\", u)",
  "options": {}, "seed": 1},
(s) => dressed(s, "carrier", {}, {from: [960, 20, 470], to: [518, -55, 150], sun: [0.2, 0.75, 0.6], fov: 32}, {}, {detail: "near"}));

definePart({"name": "hull-torch", "kind": "craft", "module": "vidgen/space-hull-detail",
  "label": "a bank of bells dressed (frames, gimbal rings, shrouds) and one long plume a bank that lights the stern",
  "use": "dress(ship, renderer, {plumes: \"bank\"}); ship.update(t, {sun, throttle}); detail.update(t)   // \"both\": the kit's plumes too",
  "options": {}, "seed": 1},
(s) => dressed(s, "carrier", {plumes: "bank"}, {view: [0.55, 0.3, -0.78]}, {throttle: 1}));

definePart({"name": "hull-fleet-dressed", "kind": "craft", "module": "vidgen/space-hull-detail",
  "label": "a fleet one maker built (one palette, one accent), every hull dressed at \"far\" detail",
  "use": "const fleet = hullFleet([\"carrier\", \"spine\", \"twin\"], {count: 5, seed: 3}); const details = dressFleet(fleet, renderer)",
  "options": {}, "seed": 3},
(s) => {
  const fleet = hullFleet(["carrier", "spine", "twin", "lance", "cluster"], {count: 5, seed: s.seed, spacing: 2600}), d = dressFleet(fleet, s.renderer, s.options);
  const sun = show(s, fleet.object, 5200, {view: [0.5, 0.7, 0.6]});
  return {frame(t) { fleet.update(t, {sun}); d.update(t); }};
});

definePart({"name": "hull-detail-maps", "kind": "craft-part", "module": "vidgen/space-hull-detail",
  "label": "the tiling maps (plating, metal, radiator, tank; 5 to 20 m above, 1 to 5 m below) as light falls on them",
  "use": "detailMap(\"plating\", \"mid\", 1024)   // {data, size, tile}: normal x and y, tone, gloss; baked once by vidgen/baked",
  "options": {}, "seed": 1},
(s) => {
  const size = s.height < 300 ? 128 : 256, group = new THREE.Group();
  KINDS.forEach((kind, i) => ["mid", "fine"].forEach((scale, j) => {
    const m = detailMap(kind, scale, size), normal = new Uint8Array(m.data.length), tone = new Uint8Array(m.data.length);
    for (let q = 0; q < m.data.length; q += 4) { normal.set([m.data[q], m.data[q + 1], 255, 255], q); const v = Math.min(255, m.data[q + 2] * 1.5); tone.set([v, v, v, 255], q); }
    const tex = (d, srgb) => { const t = new THREE.DataTexture(d, size, size, THREE.RGBAFormat); if (srgb) t.colorSpace = THREE.SRGBColorSpace; t.magFilter = THREE.LinearFilter; t.needsUpdate = true; return t; };
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 1.5), new THREE.MeshStandardMaterial({map: tex(tone, true), normalMap: tex(normal, false), roughness: 0.8, color: [0xcfcbc2, 0x5a5d62, 0xdcdcd8, 0xbfc2c6][i]}));
    mesh.position.set((i - 1.5) * 1.6, (0.5 - j) * 1.6, 0); group.add(mesh);
  }));
  s.scene.add(group);
  s.key.color.set(0xffffff); s.key.intensity = Math.PI; s.key.position.set(-4, 5, 6); s.fill.intensity = 0.3;
  s.camera.position.set(0, 0, 7.6); s.camera.lookAt(0, 0, 0); s.camera.fov = 34; s.camera.updateProjectionMatrix();
  return {frame() {}};
});
