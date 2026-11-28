// The ready-made airs of vidgen/space-air for the registry vidgen/parts:
// what `vidgen parts` draws on its contact sheet. Drawn straight to the canvas ({finish: false}: the
// dome applies the tone curve itself; the meshes of the haze tile get the renderer's ACES curve while they are drawn).
import * as THREE from "three";
import {definePart} from "vidgen/parts";
import {air, sunDirection} from "vidgen/space-air";
import {spaceSky} from "vidgen/space-sky";

// a camera `height` metres over the ground, looking `pitch` degrees up towards -z
function stand(s, height, pitch, fov) {
  const a = pitch * Math.PI / 180;
  s.camera.position.set(0, height, 0); s.camera.up.set(0, 1, 0); s.camera.near = 1; s.camera.far = 1e7; s.camera.fov = fov;
  s.camera.lookAt(0, height + Math.sin(a) * 1000, -Math.cos(a) * 1000); s.camera.updateProjectionMatrix(); s.camera.updateMatrixWorld();
}
function show(s, what, {stars = false, extra = {}} = {}) {
  const o = s.options, sky = stars ? spaceSky(s.renderer, {seed: s.seed, size: 256}) : null;
  if (sky) s.scene.add(sky.object);
  stand(s, o.height ?? 2, o.pitch, o.fov);
  const dome = air(s.renderer, what, {sun: sunDirection(o.elevation, o.azimuth), stars: sky, ...extra});
  s.scene.add(dome.object);
  dome.update(0, {camera: s.camera});
  return dome;
}

definePart({"name": "air-earth-noon", "kind": "air", "module": "vidgen/space-air",
  "label": "Earth-like air by day: a blue zenith over a paler, brighter horizon",
  "use": "const sky = air(renderer, \"earth\", {sun: sunDirection(55, 40)}); scene.add(sky.object); sky.update(t, {camera})",
  "options": {"elevation": 55, "azimuth": 40, "pitch": 14, "fov": 75}},
(s) => { show(s, "earth"); return {finish: false}; });

definePart({"name": "air-earth-golden-hour", "kind": "air", "module": "vidgen/space-air",
  "label": "a low sun: a warm glow round it, the sky still blue above",
  "use": "air(renderer, \"earth\", {sun: sunDirection(7, 18)})",
  "options": {"elevation": 7, "azimuth": 18, "pitch": 8, "fov": 60}},
(s) => { show(s, "earth"); return {finish: false}; });

definePart({"name": "air-earth-sunset", "kind": "air", "module": "vidgen/space-air",
  "label": "sunset: red at the horizon, orange, then the dusk above; the disc reddened and darker at its limb",
  "use": "air(renderer, \"earth\", {sun: sunDirection(0.6, 0)})",
  "options": {"elevation": 0.6, "azimuth": 0, "pitch": 5, "fov": 40}},
(s) => { show(s, "earth"); return {finish: false}; });

definePart({"name": "air-earth-twilight", "kind": "air", "module": "vidgen/space-air",
  "label": "twilight, the sun 6 degrees down: the arch over where it set, the first stars (film exposure)",
  "use": "air(renderer, \"earth\", {sun: sunDirection(-6, 0), stars: spaceSky(renderer, {seed})})",
  "options": {"elevation": -6, "azimuth": 0, "pitch": 18, "fov": 70}, "seed": 7},
(s) => { show(s, "earth", {stars: true}); return {finish: false}; });

definePart({"name": "air-mars-day", "kind": "air", "module": "vidgen/space-air",
  "label": "Mars-like dusty air by day: a butterscotch sky, paler towards the sun",
  "use": "air(renderer, \"mars\", {sun: sunDirection(40, 75)})",
  "options": {"elevation": 40, "azimuth": 75, "pitch": 12, "fov": 75}},
(s) => { show(s, "mars"); return {finish: false}; });

definePart({"name": "air-mars-sunset", "kind": "air", "module": "vidgen/space-air",
  "label": "Mars-like sunset: a blue glow round the sun in a tawny sky",
  "use": "air(renderer, \"mars\", {sun: sunDirection(3, 0)})",
  "options": {"elevation": 3, "azimuth": 0, "pitch": 6, "fov": 50}},
(s) => { show(s, "mars"); return {finish: false}; });

definePart({"name": "air-thin", "kind": "air", "module": "vidgen/space-air",
  "label": "thin air (invented world): a dark sky by day, stars in it, a hard bright sun",
  "use": "air(renderer, \"thin\", {sun: sunDirection(25, 30), stars})",
  "options": {"elevation": 25, "azimuth": 30, "pitch": 12, "fov": 75}, "seed": 7},
(s) => { show(s, "thin", {stars: true}); return {finish: false}; });

definePart({"name": "air-thick", "kind": "air", "module": "vidgen/space-air",
  "label": "thick air (invented world): a pale bright sky, a yellowed sun in a wide glow",
  "use": "air(renderer, \"thick\", {sun: sunDirection(25, 30)})",
  "options": {"elevation": 25, "azimuth": 30, "pitch": 12, "fov": 75}},
(s) => { show(s, "thick"); return {finish: false}; });

definePart({"name": "air-from-30-km", "kind": "air", "module": "vidgen/space-air",
  "label": "the same air from 30 km up: a curved horizon, the air a band, black above",
  "use": "sky.update(t, {camera})  // the camera's height is read from where it stands",
  "options": {"elevation": 20, "azimuth": 60, "pitch": -4, "fov": 60, "height": 30000}, "seed": 7},
(s) => { show(s, "earth", {stars: true}); return {finish: false}; });

definePart({"name": "air-haze", "kind": "air", "module": "vidgen/space-air",
  "label": "aerial perspective: hills 1.5 to 100 km away take the sky's colour and lose contrast",
  "use": "sky.haze(mesh.material); scene.add(sky.light.sun, sky.light.sky)",
  "options": {"elevation": 30, "azimuth": 70, "pitch": 3, "fov": 55, "height": 300}},
(s) => {
  s.scene.remove(s.key, s.fill);
  const dome = show(s, "earth", {extra: {scene: s.scene}});
  const dark = dome.haze(new THREE.MeshStandardMaterial({color: 0x3a3f36, roughness: 1})), pale = dome.haze(new THREE.MeshStandardMaterial({color: 0xe8e8e8, roughness: 1}));
  [1.5, 4, 9, 18, 35, 60, 100].forEach((km, i) => {
    const d = km * 1000, h = d * 0.13, hill = new THREE.Mesh(new THREE.ConeGeometry(h * 1.1, h, 5), i % 3 === 2 ? pale : dark), bearing = (-24 + 8 * i) * Math.PI / 180;
    hill.position.set(Math.sin(bearing) * d, h / 2 - d * d / 2 / 6.371e6, -Math.cos(bearing) * d); hill.rotation.y = i; s.scene.add(hill);
    // straight to the canvas a mesh needs the curve the dome applies itself: only while this hill is drawn
    hill.onBeforeRender = (r) => { r.toneMapping = THREE.ACESFilmicToneMapping; }; hill.onAfterRender = (r) => { r.toneMapping = THREE.NoToneMapping; };
  });
  return {finish: false};
});
