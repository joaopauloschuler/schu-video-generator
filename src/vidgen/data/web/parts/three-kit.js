// The ready-made parts of vidgen/three-kit and vidgen/three-finish (DESIGN.md §121.1, §120.11) for
// the registry vidgen/parts (§122.5): what `vidgen parts` draws on its contact sheet. Each make()
// sets the kit's stage for the scene it is given (setStage) and builds the part as the films do.
// Music the parts react to (hits, notes, bands) is made up here: a page gives its own (ctx.music).
import * as THREE from "three";
import {definePart} from "vidgen/parts";
import * as K from "vidgen/three-kit";
import {nebulaSky, studioEnvironment} from "vidgen/three-finish";

const kit = (s) => K.setStage({renderer: s.renderer, scene: s.scene, camera: s.camera, width: s.width, height: s.height});
const hex = (text, m = 1) => new THREE.Color(text).multiplyScalar(m);
const aim = (s, x, y, z, lx, ly, lz, fov = 40) => {
  s.camera.position.set(x, y, z); s.camera.lookAt(lx, ly, lz);
  s.camera.fov = fov; s.camera.updateProjectionMatrix(); s.camera.updateMatrixWorld();
};
const PALETTE = ["#35e8ff", "#9b5cff", "#ff4fd8", "#ffb347", "#9fdcff"];
const hits = (times) => ({t: Float32Array.from(times), g: Float32Array.from(times, () => 1)});
const notes = (times, pitches, length = 0.25) => ({t: Float32Array.from(times), d: Float32Array.from(times, () => length), p: Float32Array.from(pitches)});

// ---------- skies ----------
definePart({"name": "nebula-dome", "kind": "sky", "module": "vidgen/three-kit",
  "label": "nebula with stars all round, baked once, coloured and lit live",
  "use": "const sky = new SkyDome(seed); sky.colors(a, b, c); sky.turn(t); sky.follow(camera)",
  "options": {"deep": "#010308", "mid": "#06203a", "bright": "#2a7fa0", "light": "#6a3cff", "gain": 1.4}, "seed": 3, "at": 20},
(s) => {
  kit(s);
  const o = s.options, sky = new K.SkyDome(s.seed);
  sky.colors(hex(o.deep), hex(o.mid), hex(o.bright), o.gain);
  sky.light(1, new THREE.Vector3(0.4, 0.3, -1), hex(o.light), 0.7, 4);
  aim(s, 0, 0, 0, 0.2, 0.1, -1, 60);
  return {frame(t) { sky.turn(t); sky.follow(s.camera); }};
});

definePart({"name": "nebula-sky", "kind": "sky", "module": "vidgen/three-finish",
  "label": "nebula and stars as scene.background (and an environment)",
  "use": "scene.background = nebulaSky(renderer, {seed, mid, bright, glow}).background",
  "options": {"mid": "#2a1040", "bright": "#c0508a", "glow": "#ff9a50", "density": 0.6}, "seed": 4},
(s) => {
  const o = s.options;
  s.scene.background = nebulaSky(s.renderer, {seed: s.seed, size: 256, mid: new THREE.Color(o.mid).getHex(), bright: new THREE.Color(o.bright).getHex(),
    glow: new THREE.Color(o.glow).getHex(), density: o.density}).background;
  aim(s, 0, 0, 0, 0.3, 0.15, -1, 60);
});

definePart({"name": "star-field", "kind": "sky", "module": "vidgen/three-kit",
  "label": "stars in a tube along the flight axis, flown through",
  "use": "const st = makeStarField(n, [r0, r1], depth, seed); updateStarField(st, t, distance, streak)",
  "options": {"count": 1400, "speed": 20, "streak": 0}, "seed": 5},
(s) => {
  kit(s);
  const o = s.options, st = K.makeStarField(o.count, [3, 40], 220, s.seed);
  aim(s, 0, 0, 0, 0, 0, -1, 55);
  return {frame(t) { K.updateStarField(st, t, t * o.speed, o.streak, 0); }};
});

definePart({"name": "star-shell", "kind": "sky", "module": "vidgen/three-kit",
  "label": "still stars all round a centre, for a camera circling it",
  "use": "makeStarShell(n, r0, r1, seed, {flat})",
  "options": {"count": 1500}, "seed": 6},
(s) => {
  kit(s);
  K.makeStarShell(s.options.count, 40, 120, s.seed);
  aim(s, 8, 2, 8, 0, 0, 0, 55);
});

// ---------- structures ----------
definePart({"name": "crystals", "kind": "structure", "module": "vidgen/three-kit",
  "label": "glass polyhedra with glowing edges: octa, tetra, ico, dodeca, cube",
  "use": "const g = makeCrystal(\"ico\", lineColour, faceColour); lightCrystal(g, kick)",
  "options": {"line": "#35e8ff", "face": "#9b5cff", "kick": 0.3}},
(s) => {
  kit(s);
  const o = s.options;
  const list = K.POLYHEDRA.map((kind, i) => { const g = K.makeCrystal(kind, hex(o.line), hex(o.face)); g.position.set(-4 + i * 2, 0, 0); g.scale.setScalar(0.75); return g; });
  aim(s, 0, 0.6, 8.5, 0, 0, 0, 40);
  return {frame(t) { list.forEach((g, i) => { g.rotation.set(t * 0.3 + i, t * 0.4, 0.2 * i); K.lightCrystal(g, o.kick); }); }};
});

definePart({"name": "tesseract", "kind": "structure", "module": "vidgen/three-kit",
  "label": "a 4D cube of glowing edges, turning in four dimensions",
  "use": "const tes = makeTesseract(); updateTesseract(tes, tesseractAngles(t), colour)",
  "options": {"colour": "#35e8ff"}},
(s) => {
  kit(s);
  const tes = K.makeTesseract();
  aim(s, 0, 0.5, 7, 0, 0, 0, 40);
  return {frame(t) { K.updateTesseract(tes, K.tesseractAngles(t), hex(s.options.colour)); }};
});

definePart({"name": "portal", "kind": "structure", "module": "vidgen/three-kit",
  "label": "a ring of light whose window shows another sky (renderer with stencil: true)",
  "use": "const p = makePortal(radius, sky); lightPortal(p, ringColour, 2); lightDial(p, c, 0.3, step, 1)",
  "options": {"ring": "#ffb347"}, "seed": 7},
(s) => {
  kit(s);
  const sky = new K.SkyDome(s.seed);
  sky.colors(hex("#08020a"), hex("#3a0a30"), hex("#ff6a3c"), 1.6); sky.mesh.visible = false;
  const p = K.makePortal(2.2, sky);
  aim(s, 0, 0, 7, 0, 0, 0, 40);
  return {frame(t) { sky.turn(t); K.lightPortal(p, hex(s.options.ring), 2.2); K.lightDial(p, hex(s.options.ring), 0.3, Math.floor(t * 8), 1); }};
});

definePart({"name": "ring-structure", "kind": "structure", "module": "vidgen/three-kit",
  "label": "great rings with scale marks turning slowly about one centre",
  "use": "const m = makeRingStructure(); updateRingStructure(m, t, colour, gain)",
  "options": {"colour": "#ffb347", "gain": 1.6}},
(s) => {
  kit(s);
  const m = K.makeRingStructure();
  aim(s, 0, 80, 430, 0, 0, 0, 55);
  return {frame(t) { K.updateRingStructure(m, t, hex(s.options.colour), s.options.gain); }};
});

definePart({"name": "lattice", "kind": "structure", "module": "vidgen/three-kit",
  "label": "a twisting corridor of hexagons, flown down",
  "use": "const lat = makeLattice(); updateLattice(lat, t, distance, cameraZ, colour, (i, ahead) => gain)",
  "options": {"colour": "#35e8ff", "speed": 18}},
(s) => {
  kit(s);
  const lat = K.makeLattice();
  aim(s, 0, 0, 0, 0, 0, -1, 60);
  return {frame(t) { K.updateLattice(lat, t, t * s.options.speed, 0, hex(s.options.colour), (i, ahead) => 1.4 + Math.max(0, 1 - Math.abs(ahead - 60) / 30)); }};
});

definePart({"name": "crystal-field", "kind": "structure", "module": "vidgen/three-kit",
  "label": "crystals along the flight axis, lit by the kick and the bands",
  "use": "const f = makeCrystalField(n, [r0, r1], depth, seed, palette); updateCrystalField(f, t, distance, kick, band, camZ, gain, near)",
  "options": {"count": 24, "speed": 6}, "seed": 8},
(s) => {
  kit(s);
  const f = K.makeCrystalField(s.options.count, [1.5, 5], 45, s.seed, PALETTE.map((c) => hex(c)));
  aim(s, 9, 3, 2, 0, 0, -22, 50);   // from beside the flight axis: the field seen along its length
  return {frame(t) { K.updateCrystalField(f, t, t * s.options.speed, 0.4, (b) => 0.5 + 0.4 * Math.sin(b + t), 0, 1, 4); }};
});

definePart({"name": "crystal-swarm", "kind": "structure", "module": "vidgen/three-kit",
  "label": "crystals on slow orbits about a centre",
  "use": "const list = makeCrystalSwarm(n, [r0, r1], seed, palette); updateCrystalSwarm(list, t, kick, band)",
  "options": {"count": 30}, "seed": 9},
(s) => {
  kit(s);
  const list = K.makeCrystalSwarm(s.options.count, [6, 26], s.seed, PALETTE.map((c) => hex(c)));
  aim(s, 0, 12, 58, 0, 0, 0, 45);
  return {frame(t) { K.updateCrystalSwarm(list, t, 0.4, (b) => 0.5 + 0.4 * Math.sin(b + t)); }};
});

// ---------- effects ----------
definePart({"name": "glow-lines", "kind": "effect", "module": "vidgen/three-kit",
  "label": "glowing strokes, a bright core and a soft halo, for bloom",
  "use": "const g = Glow.from(segments, {px: 1.5, world: 0.03}); g.tint(colour, 2)",
  "options": {"colour": "#35e8ff"}},
(s) => {
  kit(s);
  const seg = [];
  for (let i = 0; i < 7; i++) { const a = (i / 7) * Math.PI * 2, b = ((i + 3) / 7) * Math.PI * 2; seg.push(Math.cos(a) * 2, Math.sin(a) * 2, 0, Math.cos(b) * 2, Math.sin(b) * 2, 0); }
  seg.push(...K.circleSegments(64, 2.3));
  K.Glow.from(seg, {px: 1.5, world: 0.03}).tint(hex(s.options.colour), 2);
  aim(s, 0, 0, 7, 0, 0, 0, 40);
});

definePart({"name": "flare", "kind": "effect", "module": "vidgen/three-kit",
  "label": "a flare facing the camera: glow, a streak, slow rays",
  "use": "const f = makeFlare(size); setFlare(f, colour, intensity, turn)",
  "options": {"colour": "#ffd9a0", "intensity": 1.4}},
(s) => {
  kit(s);
  const f = K.makeFlare(5);
  aim(s, 0, 0, 6, 0, 0, 0, 40);
  return {frame(t) { K.setFlare(f, hex(s.options.colour), s.options.intensity, t * 0.1); }};
});

definePart({"name": "shock-rings", "kind": "effect", "module": "vidgen/three-kit",
  "label": "rings of light spreading from each drum hit",
  "use": "const rings = makeShockRings(4); updateShockRings(rings, hits, t, colour, {r0, r1, life, face: true})",
  "options": {"colour": "#35e8ff"}},
(s) => {
  kit(s);
  const rings = K.makeShockRings(4), h = hits([0.2, 0.8, 1.4, 1.9]);
  aim(s, 0, 0, 9, 0, 0, 0, 40);
  return {frame(t) { K.updateShockRings(rings, h, t, hex(s.options.colour), {r0: 0.4, r1: 4.5, life: 2.4, face: true}); }};
});

definePart({"name": "glints", "kind": "effect", "module": "vidgen/three-kit",
  "label": "a four-pointed star for each note, rising and fading",
  "use": "const gl = new Glow(60); updateGlints(gl, notes, t, {n: 12, place: (i, pitch) => [x, y, z]})",
  "options": {"size": 0.22}},
(s) => {
  kit(s);
  const gl = new K.Glow(60), n = notes([0.6, 0.85, 1.1, 1.35, 1.5, 1.65, 1.8, 1.95], [60, 64, 67, 72, 71, 67, 64, 62]);
  aim(s, 0, 0, 7, 0, 0, 0, 40);
  return {frame(t) { K.updateGlints(gl, n, t, {n: 8, size: s.options.size, place: (j, p) => [-3 + j * 0.85, (p - 66) * 0.18, 0]}); }};
});

definePart({"name": "ribbon", "kind": "effect", "module": "vidgen/three-kit",
  "label": "the melody drawn as a line of light, its head bright",
  "use": "const gl = makeRibbon(120); updateRibbon(gl, notes, t, span, (time, pitch, age, out) => ..., colourNow, colourOld)",
  "options": {"now": "#ff4fd8", "old": "#35e8ff"}},
(s) => {
  kit(s);
  const gl = K.makeRibbon(120, {world: 0.05}), n = notes([0, 0.4, 0.8, 1.2, 1.6, 2.0, 2.4], [60, 67, 64, 72, 69, 65, 71], 0.38);
  aim(s, 0, 0, 7, 0, 0, 0, 40);
  return {frame(t) { K.updateRibbon(gl, n, t, 2.4, (time, p, age, out) => { out[0] = 2.6 - age * 2.2; out[1] = (p - 66) * 0.16; out[2] = 0; }, hex(s.options.now), hex(s.options.old)); }};
});

definePart({"name": "spectrum-rays", "kind": "effect", "module": "vidgen/three-kit",
  "label": "96 rays round a centre, their lengths the 16 bands of the music",
  "use": "const gl = makeSpectrumRays(group); updateSpectrumRays(gl, ctx.music.band, r0, length, colourA, colourB)",
  "options": {"a": "#35e8ff", "b": "#ff4fd8"}},
(s) => {
  kit(s);
  const group = new THREE.Group(); s.scene.add(group);
  const gl = K.makeSpectrumRays(group, {world: 0.03});
  aim(s, 0, 0, 8, 0, 0, 0, 40);
  return {frame(t) { K.updateSpectrumRays(gl, (b) => 0.25 + 0.6 * Math.abs(Math.sin(b * 0.7 + t * 2)), 1.0, 2.2, hex(s.options.a), hex(s.options.b)); }};
});

definePart({"name": "tunnel", "kind": "effect", "module": "vidgen/three-kit",
  "label": "polygon rings flying past on the beat",
  "use": "updateTunnel(new Glow(8 * rings), t, secondsPerRing, time => z, far, radius, (i, time) => [colour, gain, sides])",
  "options": {"speed": 30}},
(s) => {
  kit(s);
  const gl = new K.Glow(8 * 24, {px: 1.6, world: 0.05});
  const look = (i) => [hex(PALETTE[i % PALETTE.length]), 2.2, 3 + (i % 4)];
  aim(s, 0, 0, 0, 0, 0, -1, 60);
  return {frame(t) { K.updateTunnel(gl, t, 0.25, (tk) => -(tk - t) * s.options.speed, 160, 5, look); }};
});

definePart({"name": "dust", "kind": "effect", "module": "vidgen/three-kit",
  "label": "soft motes drifting in a box of light",
  "use": "const d = makeDustCloud(n, [w, h, d, cx, cy, cz], size, seed); updateDustCloud(d, t, colour, amount)",
  "options": {"count": 300, "colour": "#ffd9a0"}, "seed": 2},
(s) => {
  kit(s);
  const d = K.makeDustCloud(s.options.count, [10, 6, 6, 0, 0, 0], 0.3, s.seed);
  aim(s, 0, 0, 6, 0, 0, 0, 45);
  return {frame(t) { K.updateDustCloud(d, t, hex(s.options.colour), 1.6); }};
});

// ---------- environments ----------
definePart({"name": "studio-environment", "kind": "environment", "module": "vidgen/three-finish",
  "label": "soft boxes on a dark dome for metal to reflect (studio, cool, soft)",
  "use": "scene.environment = studioEnvironment(renderer, {preset: \"studio\"})",
  "options": {"preset": "studio"}},
(s) => {
  s.scene.environment = studioEnvironment(s.renderer, {preset: s.options.preset});
  s.scene.background = new THREE.Color(0x0b0c0e);
  s.key.intensity = 0; s.fill.intensity = 0;
  [0.08, 0.3, 0.6].forEach((roughness, i) => {
    const ball = new THREE.Mesh(new THREE.SphereGeometry(0.8, 48, 24), new THREE.MeshStandardMaterial({color: [0xd9a441, 0xc8ccd2, 0xb87333][i], metalness: 1, roughness}));
    ball.position.set(-1.9 + i * 1.9, 0, 0); s.scene.add(ball);
  });
  aim(s, 0, 0.6, 6.5, 0, 0, 0, 40);
});
