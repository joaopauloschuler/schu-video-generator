// The giant hulls of vidgen/space-hull (DESIGN.md §123.10) for the registry vidgen/parts (§122.5): what
// `vidgen parts` draws on its contact sheet: every family of hull, a fleet and a hull with a 50 m craft beside
// it (kind "craft"), and the kit's shapes, surfaces and atlas (kind "craft-part"), under the light of the
// craft of vidgen/space-craft: one hard sun with its shadows, a faint planet-shine from below; a small tile
// draws a hull at its "far" detail. A hull is kilometres long: the tile scales it to fit. Measured at
// 1280x720 in software GL on 2 cores: a hull that fills the frame adds about 0.3 s a frame.
import * as THREE from "three";
import {definePart} from "vidgen/parts";
import {paintedEnvironment} from "vidgen/space-craft";
import {hull, hullKit, hullFleet, bankPlan, sectionOf, PALETTES} from "vidgen/space-hull";

const SUN = new THREE.Vector3(5, 5.5, 4).normalize();
const detail = (s) => (s.height < 300 ? "far" : "near");
// the tile's light and camera for `object` of `radius` metres: scaled to fill the tile, seen from `view`
function show(s, object, radius, view = [0.62, 0.42, 0.66], fill = 3.3) {
  const k = fill / radius, d = new THREE.Vector3(...view).normalize().multiplyScalar(7.6);
  object.scale.setScalar(k); s.scene.add(object);
  s.key.color.set(0xffffff); s.key.intensity = Math.PI; s.key.position.copy(SUN).multiplyScalar(12); s.fill.intensity = 0;
  s.key.castShadow = true; s.key.shadow.mapSize.set(2048, 2048); s.key.shadow.bias = -0.0006; s.key.shadow.normalBias = 0.01;
  const c = s.key.shadow.camera; c.left = c.bottom = -3.6; c.right = c.top = 3.6; c.near = 2; c.far = 24; c.updateProjectionMatrix();
  s.renderer.shadowMap.enabled = true;
  const shine = new THREE.DirectionalLight(0x9fc0ff, 0.4); shine.position.set(-0.4, -1, 0.3); s.scene.add(shine);
  s.scene.environment = paintedEnvironment(s.renderer).texture;
  s.camera.position.copy(d); s.camera.lookAt(0, 0, 0); s.camera.fov = 34; s.camera.updateProjectionMatrix(); s.camera.updateMatrixWorld();
}
// a ready-made hull from three quarters ahead
function ready(s, family, options = {}, {view, fill = 3.5, state = {}} = {}) {
  const h = hull(family, {seed: s.seed, detail: detail(s), ...options, ...s.options});
  show(s, h.object, h.size.radius, view, fill);
  return {frame(t) { h.update(t, {sun: SUN, ...state}); }};
}
// a hull of your own from a shell: `make(shell, kit)` builds it
function own(s, make, {view, fill = 3.3, kit = {}} = {}) {
  const k = hullKit({seed: s.seed, detail: detail(s), ...kit, ...s.options}), sh = k.shell(), anchors = make(sh, k) ?? {}, h = k.hull(sh.finish(), {anchors});
  show(s, h.object, h.size.radius, view, fill);
  return {frame(t) { h.update(t, {sun: SUN, throttle: 0.7}); }};
}

definePart({"name": "hull-spine", "kind": "craft", "module": "vidgen/space-hull",
  "label": "a long truss: drive behind a shadow disc, radiators in one plane, tanks, crew drums (1.2 to 2.8 km)",
  "use": "const ship = hull(\"spine\", {seed: 1}); scene.add(ship.object); ship.update(t, {sun})",
  "options": {}, "seed": 1},
(s) => ready(s, "spine"));

definePart({"name": "hull-carrier", "kind": "craft", "module": "vidgen/space-hull",
  "label": "a thick block: a deck trench into a gulf between two prongs, hangar slots, terraces (1.8 to 4.2 km)",
  "use": "hull(\"carrier\", {seed: 1, length: 3000})   // ship.anchor(\"hangar-1\"), ship.region(\"trench\")",
  "options": {}, "seed": 1},
(s) => ready(s, "carrier"));

definePart({"name": "hull-cluster", "kind": "craft", "module": "vidgen/space-hull",
  "label": "an open frame with its load in plain sight: pressure balls, tanks, container stacks (0.7 to 1.7 km)",
  "use": "hull(\"cluster\", {seed: 1})   // cells: [\"ball\", \"cargo\", \"pair\", \"cross\", \"gap\", ...]",
  "options": {}, "seed": 1},
(s) => ready(s, "cluster"));

definePart({"name": "hull-lance", "kind": "craft", "module": "vidgen/space-hull",
  "label": "a very long thin hull behind a faceted shield, the drive far aft among narrow radiators (2.5 to 6 km)",
  "use": "hull(\"lance\", {seed: 1})   // shieldShape: \"cone\" | \"disc\", vanes: 3 | 4",
  "options": {}, "seed": 1},
(s) => ready(s, "lance", {}, {fill: 3.9}));

definePart({"name": "hull-wheel", "kind": "craft", "module": "vidgen/space-hull",
  "label": "a hub with two polygonal crew rings of unequal size turning against each other (0.9 to 2.4 km)",
  "use": "hull(\"wheel\", {seed: 1})   // the rings turn with update(t); spin: radians a second",
  "options": {}, "seed": 1},
(s) => ready(s, "wheel"));

definePart({"name": "hull-ark", "kind": "craft", "module": "vidgen/space-hull",
  "label": "a worked asteroid: cut faces, a hangar portal, a collar with radiators, terraces on a mesa (3 to 8 km)",
  "use": "hull(\"ark\", {seed: 1})   // rough: 0.15 to 0.6, girth: its width over its length",
  "options": {}, "seed": 1},
(s) => ready(s, "ark", {}, {fill: 3.1}));

definePart({"name": "hull-twin", "kind": "craft", "module": "vidgen/space-hull",
  "label": "two unequal hulls, one set back and higher: bridges, a hangar pod, cargo racks (1.2 to 3.2 km)",
  "use": "hull(\"twin\", {seed: 1})   // stagger, rise, gap, bridges",
  "options": {}, "seed": 1},
(s) => ready(s, "twin"));

definePart({"name": "hull-burn", "kind": "craft", "module": "vidgen/space-hull",
  "label": "the drive from astern: a bank of the craft kit's bells firing, each with its plume",
  "use": "ship.update(t, {throttle: 0.8})   // ship.anchors.bells: [{name, p, n, radius, bank}]",
  "options": {}, "seed": 1},
(s) => ready(s, "carrier", {}, {view: [0.5, 0.3, -0.8], state: {throttle: 0.8}}));

definePart({"name": "hull-scale", "kind": "craft", "module": "vidgen/space-hull",
  "label": "a sense of size: a 50 m ship of the craft kit before a hangar slot of a 3 km carrier",
  "use": "const small = ship.scaleRef(\"ship\", {at: \"hangar-1\", gap: 120}); small.update(t, {sun})",
  "options": {}, "seed": 1},
(s) => {
  const h = hull("carrier", {seed: s.seed, detail: detail(s), length: 3000, ...s.options}), small = h.scaleRef("ship", {at: "hangar-1", gap: 110, detail: detail(s)}), a = h.anchor("hangar-1");
  const holder = new THREE.Group(), inner = new THREE.Group(); h.object.position.set(-a.p[0] - a.n[0] * 60, -a.p[1], -a.p[2]); inner.add(h.object); inner.rotation.y = a.n[0] < 0 ? Math.PI : 0; holder.add(inner);
  show(s, holder, 330, [0.75, 0.2, 0.55], 3.3);
  return {frame(t) { h.update(t, {sun: SUN}); small.update(t, {sun: SUN}); }};
});

definePart({"name": "hull-fleet", "kind": "craft", "module": "vidgen/space-hull",
  "label": "a fleet from seeds: five hulls of five families at \"far\" detail, in a loose formation",
  "use": "const fleet = hullFleet([\"carrier\", \"spine\", \"twin\", \"lance\", \"cluster\"], {count: 5, seed: 3}); fleet.update(t, {sun})",
  "options": {"count": 5}, "seed": 3},
(s) => {
  const f = hullFleet(["carrier", "spine", "twin", "lance", "cluster"], {seed: s.seed, spacing: 2600, ...s.options}), box = new THREE.Box3().setFromObject(f.object), mid = box.getCenter(new THREE.Vector3()), holder = new THREE.Group();
  f.object.position.sub(mid); holder.add(f.object);
  show(s, holder, 0.5 * box.getSize(new THREE.Vector3()).length(), [0.45, 0.6, 0.66], 4.2);
  return {frame(t) { f.update(t, {sun: SUN}); }};
});

definePart({"name": "hull-part-shapes", "kind": "craft-part", "module": "vidgen/space-hull",
  "label": "the kit's shapes: a section with a trench and a side slot, a hangar mouth, a drum, tanks, a truss",
  "use": "const kit = hullKit({seed: 1}), sh = kit.shell(); sh.part(\"core\").region(\"midship\").block(\"hull-a\", [300, 160, 800]); kit.hull(sh.finish())",
  "options": {}, "seed": 1},
(s) => own(s, (sh) => {
  const sec = sectionOf(320, 170, 6, {trench: {w: 44, d: 56}, slots: [{side: 1, y0: -50, y1: 20, d: 60}]});
  sh.part("core").region("midship").loft("hull-a", sec.poly, [{z: -420, s: [1, 1], o: [0, 0]}, {z: 120, s: [1, 1], o: [0, 0]}], {edge: (e) => (["wall", "floor", "slot"].includes(sec.tags[e]) ? {skin: "hull-c"} : sec.tags[e] === "back" ? {skin: "hull-void"} : null)});
  sh.part("fore").region("bow", "dock").block("hull-b", [260, 150, 160], [0, 0, 200], {chamfer: 8, bevel: 10}).mouth("hangar-1", [0, 0, 330], [0, 0, 1], [120, 60, 50]);
  sh.part("drum").region("habitat-1", "windows").drum("hull-a", 130, [-560, -470], {sides: 16, facet: true, bevel: 14});
  sh.part("tanks").region("tank-1", "tank");
  for (const x of [-1, 1]) sh.capsule("hull-tank", [x * 215, 0, -380], [x * 215, 0, -40], 48);
  sh.part("truss", {sparse: true}).region("truss", "truss").truss([0, 0, -900], [0, 0, -560], 60);
  sh.part("deck works", {sparse: true}).region("midship").scatter(new THREE.Vector3(40, 85, -400), new THREE.Vector3(110, 0, 0), new THREE.Vector3(0, 0, 500), new THREE.Vector3(0, 1, 0), {count: 7, size: [20, 80], height: [5, 16]});
}, {view: [0.6, 0.45, 0.66]}));

definePart({"name": "hull-part-drive", "kind": "craft-part", "module": "vidgen/space-hull",
  "label": "the drive's parts: radiator vanes warm at the root, a bank of bells from a plan (grid, ring, row), a dish",
  "use": "sh.vane([0, 0, 0], [1, 0, 0], 400, 300); const plan = bankPlan({w: 300, h: 160, count: 6}); kit.bells(sh, plan, [0, 0, -500])",
  "options": {}, "seed": 2},
(s) => own(s, (sh, kit) => {
  const plan = bankPlan({w: 300, h: 150, count: 6, rows: 2});
  sh.part("engine-block").region("engine-block", "engine").block("hull-c", [320, 170, 120], [0, 0, -240], {chamfer: 12, bevel: 12});
  const bells = kit.bells(sh, plan, [0, 0, -300]);
  sh.part("truss", {sparse: true}).region("truss", "truss").truss([0, 0, -180], [0, 0, 420], 50);
  [1, -1].forEach((q, k) => sh.part(`radiator ${k + 1}`).region(`radiator-${k + 1}`, "radiator").vane([q * 25, 0, 140], [q, 0, 0], 330, 380, {taper: 0.8}));
  sh.part("array", {sparse: true}).region("midship").dish([0, 25, 400], [0.3, 1, 0.3], 70, {mast: 80});
  return {bells};
}, {view: [0.55, 0.5, -0.67], fill: 3.6}));

definePart({"name": "hull-surfaces", "kind": "craft-part", "module": "vidgen/space-hull",
  "label": "the palettes: bone, slate, iron, sand, frost: two hull tones and a dark metal each, one accent, big plates",
  "use": "hull(\"carrier\", {palette: \"slate\", accent: 0xc8542a, age: 0.5})   // or hullKit({palette, accent, tile, plate})",
  "options": {}, "seed": 1},
(s) => {
  const group = new THREE.Group(), list = Object.keys(PALETTES).map((palette, i) => {
    const k = hullKit({seed: s.seed + i, detail: detail(s), palette, ...s.options}), sh = k.shell();
    sh.part("a").region("midship").block("hull-a", [200, 200, 420], [0, 0, 0], {chamfer: 10, bevel: 10}).block("hull-b", [214, 120, 150], [0, -30, -60], {chamfer: 8, bevel: 8}).block("hull-c", [150, 150, 60], [0, 0, -240], {chamfer: 8}).block("hull-accent", [204, 16, 300], [0, 70, 30]);
    const h = k.hull(sh.finish());
    h.object.position.set((i - 2) * 330, 0, 0); h.object.rotation.set(0, 0.5, 0); group.add(h.object);
    return h;
  });
  show(s, group, 900, [0.15, 0.5, 0.85], 4.2);
  return {frame(t) { for (const h of list) h.update(t, {sun: SUN}); }};
});

definePart({"name": "hull-charts", "kind": "craft-part", "module": "vidgen/space-hull",
  "label": "the atlas for fine detail: every large face is a chart of its own (uv1), each drawn in its own colour",
  "use": "ship.charts   // [{id, name, region, size: [w, h] m, rect: [u0, v0, u1, v1], ...}]; ship.texel(chart, 4096) metres",
  "options": {}, "seed": 1},
(s) => {
  const h = hull("carrier", {seed: s.seed, detail: detail(s), ...s.options}), n = 1024, data = new Uint8Array(n * n * 4).fill(40);
  for (const c of h.charts) {
    const k = c.id * 2654435761 >>> 0, rgb = [90 + (k & 127), 90 + ((k >> 8) & 127), 90 + ((k >> 16) & 127)];
    for (let y = Math.floor(c.rect[1] * n); y < Math.ceil(c.rect[3] * n); y++) for (let x = Math.floor(c.rect[0] * n); x < Math.ceil(c.rect[2] * n); x++) data.set([...rgb, 255], 4 * (y * n + x));
  }
  const map = new THREE.DataTexture(data, n, n, THREE.RGBAFormat); map.channel = 1; map.colorSpace = THREE.SRGBColorSpace; map.needsUpdate = true;
  const flat = new THREE.MeshLambertMaterial({map});
  h.object.traverse((m) => { if (m.isMesh && !m.userData.keep && m.geometry.attributes.uv1) m.material = flat; });
  show(s, h.object, h.size.radius, [0.62, 0.42, 0.66], 3.5);
  return {frame(t) { h.update(t, {sun: SUN}); }};
});
