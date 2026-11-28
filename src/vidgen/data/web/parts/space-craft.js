// The spacecraft of vidgen/space-craft for the registry vidgen/parts: what
// `vidgen parts` draws on its contact sheet: every ready-made craft (kind "craft"), the kit's parts, its
// surfaces on test shapes and its plumes (kind "craft-part"). Each tile: one hard sun with its shadows, a
// faint planet-shine from below, a painted environment (a blue-white world under the craft) for the metal;
// a small tile draws the craft at its "far" detail. Measured at 1280x720 in software GL on 2 cores: a craft
// close up adds 0.15 to 0.6 s a frame to the sky and vidgen/three-finish (its shadows 0.05 to 0.1 s of that),
// far away 0.05 to 0.1 s.
import * as THREE from "three";
import {definePart} from "vidgen/parts";
import {craft, craftKit, attach, around, fleet, paintedEnvironment} from "vidgen/space-craft";

const SUN = new THREE.Vector3(5, 4.5, 4).normalize();
const detail = (s) => (s.height < 300 ? "far" : "near");
// the tile's light and camera for `object` of `radius` metres: scaled to fill the tile, seen from `view`
function show(s, object, radius, view = [0.55, 0.3, 1], fill = 3.1) {
  const k = fill / radius, d = new THREE.Vector3(...view).normalize().multiplyScalar(7.6);
  object.scale.setScalar(k); s.scene.add(object);
  s.key.color.set(0xffffff); s.key.intensity = Math.PI; s.key.position.copy(SUN).multiplyScalar(12); s.fill.intensity = 0;
  s.key.castShadow = true; s.key.shadow.mapSize.set(1024, 1024); s.key.shadow.bias = -0.0005;
  const c = s.key.shadow.camera; c.left = c.bottom = -2.8; c.right = c.top = 2.8; c.near = 2; c.far = 24; c.updateProjectionMatrix();
  s.renderer.shadowMap.enabled = true;
  const shine = new THREE.DirectionalLight(0x9fc0ff, 0.5); shine.position.set(-0.4, -1, 0.3); s.scene.add(shine);
  s.scene.environment = paintedEnvironment(s.renderer).texture;
  s.camera.position.copy(d); s.camera.lookAt(0, 0, 0); s.camera.fov = 34; s.camera.updateProjectionMatrix(); s.camera.updateMatrixWorld();
}
// a ready-made craft, turned a little, its wings to the sun
function ready(s, kind, options = {}, turn = [0.25, -0.95, 0.12], view, extra = {}, fill = 3.1) {
  const c = craft(kind, {seed: s.seed, detail: detail(s), ...options, ...s.options});
  c.object.rotation.set(...turn);
  show(s, c.object, c.size.radius, view, fill);
  return {frame(t) { c.update(t, {sun: SUN, ...extra}); }};
}
// parts side by side: `make(kit)` returns [[part, the point that becomes its nose], ...]
function parts(s, make, {turn = [0.35, -0.6, 0.1], gap = 1.25, view, extra = {}, fill = 3.1} = {}) {
  const kit = craftKit({seed: s.seed, detail: detail(s), ...s.options}), list = make(kit).map(([p, fore]) => kit.craft(p, {fore})), group = new THREE.Group();
  const width = list.reduce((w, c) => w + 2 * c.size.radius * gap, 0);
  let x = -width / 2;
  for (const c of list) { c.object.position.x = x + c.size.radius * gap; x += 2 * c.size.radius * gap; c.object.rotation.set(...turn); group.add(c.object); }
  show(s, group, list.length === 1 ? list[0].size.radius : width / 2, view, fill);
  return {frame(t) { for (const c of list) c.update(t, {sun: SUN, ...extra}); }};
}

definePart({"name": "craft-probe", "kind": "craft", "module": "vidgen/space-craft",
  "label": "a deep-space probe: foil bus, high-gain dish, power boom, magnetometer boom (dish 3 m, 11 to 17 m across)",
  "use": "const probe = craft(\"probe\", {seed: 1}); scene.add(probe.object); probe.update(t, {sun})",
  "options": {}, "seed": 1},
(s) => ready(s, "probe", {}, [-0.35, 0.55, 0.25], undefined, {}, 3.6));

definePart({"name": "craft-satellite", "kind": "craft", "module": "vidgen/space-craft",
  "label": "a communications satellite: foil box bus, wings that track the sun, reflectors (16 to 28 m across)",
  "use": "craft(\"satellite\", {seed: 1})",
  "options": {}, "seed": 1},
(s) => ready(s, "satellite", {}, [-0.5, 0.5, 0.25]));

definePart({"name": "craft-station", "kind": "craft", "module": "vidgen/space-craft",
  "label": "a modular station: modules, node, cupola, airlock, truss, wings, radiators (truss 46 to 64 m)",
  "use": "craft(\"station\", {seed: 1})",
  "options": {}, "seed": 1},
(s) => ready(s, "station", {}, [0.45, -0.6, 0.1]));

definePart({"name": "craft-station-ring", "kind": "craft", "module": "vidgen/space-craft",
  "label": "the station with a ring habitat that turns (0.3 g at its rim: one turn in about 15 s)",
  "use": "craft(\"station\", {seed: 2, ring: true})",
  "options": {"ring": true}, "seed": 2},
(s) => ready(s, "station", {}, [0.5, -0.75, 0.1]));

definePart({"name": "craft-ship", "kind": "craft", "module": "vidgen/space-craft",
  "label": "a crewed ship: habitat, truss spine, propellant tanks, radiators, a ring of engines (42 to 58 m)",
  "use": "craft(\"ship\", {seed: 1})",
  "options": {}, "seed": 1},
(s) => ready(s, "ship", {}, [0.2, -1.05, 0.08]));

definePart({"name": "craft-ship-burn", "kind": "craft", "module": "vidgen/space-craft",
  "label": "the ship under thrust: plumes that widen into the vacuum (+0.05 to 0.65 s a frame)",
  "use": "ship.update(t, {throttle: 1})   // or craft(\"ship\").fly(space, {body: \"Ship\"}): the data's burns",
  "options": {}, "seed": 3},
(s) => ready(s, "ship", {}, [0.15, -2.2, 0.05], [0.5, 0.25, 1], {throttle: 1}));

definePart({"name": "craft-lander", "kind": "craft", "module": "vidgen/space-craft",
  "label": "a lander (nose up): foil descent stage, four legs, tanks, an ascent cabin (8 m across the pads)",
  "use": "craft(\"lander\", {seed: 1})",
  "options": {}, "seed": 1},
(s) => ready(s, "lander", {}, [-1.25, 0.5, 0.0], [0.4, 0.2, 1], {}, 2.3));

definePart({"name": "craft-tug", "kind": "craft", "module": "vidgen/space-craft",
  "label": "a cargo tug: crew pod, truss spine, rows of cargo boxes, tank cluster, two engines (19 to 32 m)",
  "use": "craft(\"tug\", {seed: 1})",
  "options": {}, "seed": 1},
(s) => ready(s, "tug", {}, [0.25, -1.0, 0.1]));

definePart({"name": "craft-fleet", "kind": "craft", "module": "vidgen/space-craft",
  "label": "a fleet from seeds: five ships, each its own design, at the \"far\" detail (20,000 triangles each)",
  "use": "const ships = fleet(\"ship\", {count: 5, seed: 3}); scene.add(ships.object); ships.update(t, {sun})",
  "options": {"count": 5}, "seed": 3},
(s) => {
  const f = fleet("ship", {seed: s.seed, ...s.options});
  f.object.rotation.set(0.15, -0.8, 0.05);
  const box = new THREE.Box3().setFromObject(f.object), mid = box.getCenter(new THREE.Vector3()), holder = new THREE.Group();
  f.object.position.sub(mid); holder.add(f.object);
  show(s, holder, 0.5 * box.getSize(new THREE.Vector3()).length(), [0.45, 0.35, 1], 4.2);
  return {frame(t) { f.update(t, {sun: SUN, throttle: 0.7}); }};
});

definePart({"name": "craft-seeds", "kind": "craft", "module": "vidgen/space-craft",
  "label": "one kind, three seeds: proportions, booms, tanks, instruments and accents differ; a seed is a ship",
  "use": "craft(\"probe\", {seed: 5})   // the same seed is always the same craft",
  "options": {}, "seed": 4},
(s) => {
  const list = [0, 1, 2].map((i) => craft("probe", {seed: s.seed + i, detail: detail(s)})), group = new THREE.Group();
  list.forEach((c, i) => { c.object.position.set((i - 1) * 10.5, (i - 1) * -1.2, 0); c.object.rotation.set(-0.35, 0.55 + 0.2 * i, 0.25); group.add(c.object); });
  show(s, group, 15, undefined, 3.9);
  return {frame(t) { for (const c of list) c.update(t, {sun: SUN}); }};
});

definePart({"name": "part-hulls", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "hull sections: cylinder with windows and rails, prism in foil, nose, taper, sphere, box",
  "use": "const kit = craftKit({seed: 1}); kit.hull({shape: \"prism\", sides: 8, radius: 1, length: 1.4, skin: \"foil\"})",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => [
  [kit.hull({radius: 1, length: 2.6, windows: {count: 6, rows: 2}, rails: 5, bands: 1, greebles: 0.6, stripe: 0.85}), "fore"],
  [kit.hull({shape: "prism", sides: 8, radius: 1, length: 1.5, skin: "foil", greebles: 0.6}), "fore"],
  [kit.hull({shape: "nose", radius: 1, radius2: 0.3, length: 1.5, windows: {count: 5, from: 0.4}}), "fore"],
  [kit.hull({shape: "taper", radius: 1, radius2: 0.5, length: 1.4, skin: "aluminium", bands: 1}), "fore"],
  [kit.hull({shape: "box", size: [1.6, 1.6], length: 1.8, skin: "tiles"}), "fore"]], {turn: [-1.2, 0, 0.5], gap: 0.72, fill: 3.9}));

definePart({"name": "part-tanks", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "tanks: a sphere in silver foil, a capsule in gold foil with straps, a cluster round a spine",
  "use": "kit.tank({shape: \"capsule\", radius: 0.6, length: 2.4, skin: \"foil\"}); kit.tankCluster({count: 4})",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => [[kit.tank({shape: "sphere", radius: 0.8, skin: "foil-silver"}), "top"], [kit.tank({shape: "capsule", radius: 0.6, length: 2.6}), "top"], [kit.tankCluster({count: 4, radius: 0.5, length: 2.2, skin: "paint"}), "fore"]], {turn: [-1.2, 0, 0.5], gap: 0.9, fill: 3.4}));

definePart({"name": "part-truss", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "a lattice truss: longerons, a frame every bay, diagonals, a node at every joint; a boom of three",
  "use": "kit.truss({length: 10, width: 1}); kit.boom({length: 4, lattice: true})",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => [[kit.truss({length: 7, width: 1.1}), "fore"]], {turn: [0.25, -1.0, 0.12]}));

definePart({"name": "part-solar-wing", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "a solar wing: cells with a grid and bus bars, frames, hinges, a yoke; it turns to face the sun",
  "use": "attach(bus, {angle: 0, along: 0.5}, kit.solarWing({panels: 3, size: [1.8, 2.4]}))",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => { const bus = kit.hull({shape: "box", size: [1.2, 1.2], length: 1.4, skin: "foil"}); attach(bus, {angle: 0, along: 0.5}, kit.solarWing({panels: 3, size: [1.5, 1.8], yoke: 0.8})); return [[bus, "fore"]]; }, {turn: [-0.75, 0.55, 0.15]}));

definePart({"name": "part-solar-wing-folding", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "the wing half unfolded: deployable panels that open with craft.update(t, {deploy: 0..1})",
  "use": "kit.solarWing({panels: 4, deployable: true})   // craft.update(t, {deploy: t / 6})",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => { const bus = kit.hull({shape: "box", size: [1.2, 1.2], length: 1.4, skin: "foil"}); attach(bus, {angle: 0, along: 0.5}, kit.solarWing({panels: 4, size: [1.2, 1.8], yoke: 0.8, deployable: true, track: false})); return [[bus, "fore"]]; },
  {turn: [-0.75, 0.55, 0.15], extra: {deploy: 0.6}}));

definePart({"name": "part-radiator", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "a radiator: white panels with coolant pipes on both faces, a header, hinges",
  "use": "kit.radiator({panels: 3, size: [2, 1.4]})",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => [[kit.radiator({panels: 3, size: [1.6, 1.3]}), "tip"]], {turn: [0.3, -1.2, 1.0]}));

definePart({"name": "part-dish", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "a high-gain dish: a true parabola, rim, ribs, a feed on three struts, a two-axis gimbal",
  "use": "kit.dish({diameter: 3})   // craft.update(t, {target}) points a gimballed dish",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => [[kit.dish({diameter: 3}), "feed"]], {turn: [-0.55, 0.5, 0.2]}));

definePart({"name": "part-antennas", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "antennas and booms: whip, helix, horn, omni, patch; a tube boom with a sensor head",
  "use": "kit.antenna({kind: \"helix\"}); attach(kit.boom({length: 4}), \"tip\", kit.instrument({kind: \"magnetometer\"}))",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => [...["whip", "helix", "horn", "omni", "patch"].map((kind) => [kit.antenna({kind, length: kind === "whip" ? 1.2 : 0.8}), "tip"]),
  (() => { const b = kit.boom({length: 1.6, radius: 0.03}); attach(b, "tip", kit.instrument({kind: "magnetometer", size: 0.3})); return [b, "tip"]; })()], {turn: [-1.2, 0, 0.5], gap: 0.8, fill: 3.8}));

definePart({"name": "part-instruments", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "instruments: camera, spectrometer, star tracker, a scan platform; a finned power unit",
  "use": "kit.instrument({kind: \"platform\", size: 0.4}); kit.powerUnit({length: 1.1})",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => [[kit.instrument({kind: "camera", size: 0.5}), "top"], [kit.instrument({kind: "spectrometer", size: 0.5}), "top"], [kit.instrument({kind: "platform", size: 0.45}), "top"], [kit.powerUnit({length: 1.1}), "tip"]],
  {turn: [-1.2, 0, 0.5], gap: 0.85, fill: 3.6}));

definePart({"name": "part-docking", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "a docking port, a cupola with lit windows, an airlock with its hatch and rails",
  "use": "attach(node, \"fore\", kit.dockingPort({radius: 0.8})); kit.cupola({radius: 1}); kit.airlock()",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => [[kit.dockingPort({radius: 0.8}), "dock"], [kit.cupola({radius: 0.9}), "top"], [kit.airlock({radius: 0.8, length: 1.8}), "dock"]], {turn: [-1.0, 0, 0.5], gap: 0.85, fill: 3.6}));

definePart({"name": "part-engine", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "an engine: chamber, a bell of a true bell curve with cooling channels and hoops, manifold, pumps",
  "use": "attach(hull, \"aft\", kit.engine({exit: 0.5, kind: \"chemical\"}))",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => [[kit.engine({exit: 0.6, kind: "chemical"}), "mount"], [kit.engine({exit: 0.6, kind: "vacuum"}), "mount"], [kit.engine({exit: 0.6, kind: "ion"}), "mount"]], {turn: [-1.75, 0, 0.5], gap: 0.85, fill: 3.4}));

definePart({"name": "part-thrusters-leg", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "a block of four attitude thrusters (puffing); a landing leg: two-stage strut, side struts, a pad",
  "use": "around(hull, () => kit.thrusters(), {count: 4, angle: 45}); kit.leg({length: 3, ladder: true})",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => [[kit.thrusters({size: 0.4}), "top"], [kit.leg({length: 2.4, ladder: true}), {p: new THREE.Vector3(0, 0, 0), n: new THREE.Vector3(0, 1, 0), u: new THREE.Vector3(1, 0, 0)}]], {turn: [-1.2, 0, 0.9], gap: 0.9, extra: {rcs: 1}}));

definePart({"name": "part-ring-habitat", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "a ring habitat that turns about its hub: spokes, hoops, windows on both sides",
  "use": "attach(hull, \"aft\", kit.ringHabitat({radius: 12, gravity: 0.3}), \"fore\")",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => [[kit.ringHabitat({radius: 10, tube: 1.3}), "fore"]], {turn: [0.5, -0.5, 0.1]}));

definePart({"name": "part-cargo-lights", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "a cargo box; lights: port red, starboard green, white, strobe, beacon (they blink by the clock)",
  "use": "kit.container({size: [2.4, 2.4, 5]}); attach(hull, {angle: 90, along: 0.9}, kit.light({kind: \"strobe\"}))",
  "options": {}, "seed": 1, "at": 0.03},
(s) => parts(s, (kit) => { const box = kit.container({size: [1.6, 1.6, 3]}); ["port", "starboard", "white", "strobe", "beacon"].forEach((kind, i) => attach(box, {p: new THREE.Vector3(0.5 - i * 0.25, 0.8, 1.2 - i * 0.6), n: new THREE.Vector3(0, 1, 0)}, kit.light({kind, size: 0.06, phase: 0}))); return [[box, "top"]]; },
  {turn: [0.5, 0.9, 0.1], fill: 2.6}));

definePart({"name": "surface-foil", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "thermal blankets that crinkle: gold, silver and black foil (skins \"foil\", \"foil-silver\", \"foil-black\")",
  "use": "kit.hull({skin: \"foil\"}); craftKit({foil: \"amber\"})   // gold | amber | pale",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => ["foil", "foil-silver", "foil-black"].map((skin) => [kit.hull({shape: "prism", sides: 6, radius: 1, length: 1.7, skin, caps: skin, frames: false}), "fore"]), {turn: [-1.2, 0, 0.5], gap: 0.8, fill: 3.6}));

definePart({"name": "surface-plating", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "plating with panel lines and rivets: white paint, an accent colour, bare aluminium, black tiles",
  "use": "kit.hull({skin: \"paint\"})   // paint | accent | aluminium | tiles | radiator",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => ["paint", "accent", "aluminium", "tiles"].map((skin) => [kit.hull({radius: 1, length: 1.7, skin, caps: skin, frames: false}), "fore"]), {turn: [-1.2, 0, 0.5], gap: 0.8, fill: 3.8}));

definePart({"name": "surface-cells-glass", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "solar cells with a bluish sheen and a grid; lit windows (warm) beside dark glass",
  "use": "kit.hull({windows: {count: 8, rows: 2, lit: 0.6}}); kit.hull({skin: \"cells\"})",
  "options": {}, "seed": 1},
(s) => parts(s, (kit) => [[kit.hull({shape: "box", size: [1.5, 0.08], length: 1.5, skin: "cells", caps: "back"}), "fore"], [kit.hull({radius: 0.8, length: 1.5, windows: {count: 7, rows: 3, lit: 0.6, from: 0.2, to: 0.8}}), "fore"]], {turn: [-1.2, 0, 0.9], gap: 0.9}));

// an engine at full throttle on a plate, seen from the side
function burning(s, kind) {
  return parts(s, (kit) => { const base = kit.hull({radius: 0.9, length: 0.6, skin: "aluminium"}); attach(base, "aft", kit.engine({exit: 0.5, kind})); return [[base, "fore"]]; },
    {turn: [0.2, -1.95, 0.05], extra: {throttle: 1}, fill: 1.1, view: [0.3, 0.2, 1]});
}

definePart({"name": "plume-chemical", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "a chemical engine in vacuum: a white-hot core, an amber flare that widens (no shock diamonds)",
  "use": "kit.engine({kind: \"chemical\"}); craft.update(t, {throttle: 1})   // 0..1; it flickers by the clock",
  "options": {}, "seed": 1},
(s) => burning(s, "chemical"));

definePart({"name": "plume-vacuum", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "a hydrogen engine in vacuum: a pale blue plume, wide and faint",
  "use": "kit.engine({kind: \"vacuum\"}); craft.update(t, {throttle: 1})   // 0..1; it flickers by the clock",
  "options": {}, "seed": 1},
(s) => burning(s, "vacuum"));

definePart({"name": "plume-ion", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "an ion engine: a narrow blue beam from a glowing grid",
  "use": "kit.engine({kind: \"ion\"}); craft.update(t, {throttle: 1})   // 0..1; it flickers by the clock",
  "options": {}, "seed": 1},
(s) => burning(s, "ion"));

definePart({"name": "plume-air", "kind": "craft-part", "module": "vidgen/space-craft",
  "label": "an engine firing in air (a lander near the ground): a narrow jet with shock diamonds",
  "use": "kit.engine({kind: \"air\"}); craft.update(t, {throttle: 1})   // 0..1; it flickers by the clock",
  "options": {}, "seed": 1},
(s) => burning(s, "air"));
