// The ready-made stars and lights of vidgen/space-light (DESIGN.md §122.8) for the registry
// vidgen/parts (§122.5): what `vidgen parts` draws on its contact sheet. Drawn straight to the canvas
// (a star, a body and the sky each apply the tone curve themselves); a small tile bakes small maps.
import {definePart} from "vidgen/parts";
import {planet} from "vidgen/space-bodies";
import {spaceSky} from "vidgen/space-sky";
import {star, spaceLight} from "vidgen/space-light";

const small = (s) => (s.height < 300 ? {size: 256} : {});
function aim(s, from, to, fov = 40, up = [0, 1, 0]) {
  s.camera.position.set(...from); s.camera.up.set(...up); s.camera.lookAt(...to);
  s.camera.fov = fov; s.camera.updateProjectionMatrix(); s.camera.updateMatrixWorld();
}
// one star close up, its corona round it
function close(s, what) {
  const sun = star(s.renderer, what, {seed: s.seed, ...s.options});
  s.scene.add(sun.object);
  aim(s, [0, 0, 7.2], [0, 0, 0], 30);
  return {finish: false, frame(t) { sun.update(t); }};
}

definePart({"name": "sun-yellow", "kind": "light", "module": "vidgen/space-light",
  "label": "a sun-like star (5,772 K): boiling cells, spots, faculae, corona, loops at the limb",
  "use": "const sun = star(renderer, \"sun\"); scene.add(sun.object); sun.update(t)",
  "options": {"spots": 5, "prominences": 4, "corona": 1}, "seed": 13},
(s) => close(s, "sun"));

definePart({"name": "sun-red-dwarf", "kind": "light", "module": "vidgen/space-light",
  "label": "a red dwarf (3,200 K): large cells, great spots, a dark red limb",
  "use": "star(renderer, \"red-dwarf\")",
  "options": {"spots": 3}, "seed": 11},
(s) => close(s, "red-dwarf"));

definePart({"name": "sun-orange", "kind": "light", "module": "vidgen/space-light",
  "label": "an orange star (4,600 K): spotted, a little cooler than the Sun",
  "use": "star(renderer, \"orange\")",
  "options": {"spots": 6}, "seed": 12},
(s) => close(s, "orange"));

definePart({"name": "sun-white", "kind": "light", "module": "vidgen/space-light",
  "label": "a white star (8,500 K): smooth and brilliant, no spots",
  "use": "star(renderer, \"white\")",
  "seed": 14},
(s) => close(s, "white"));

definePart({"name": "sun-blue-giant", "kind": "light", "module": "vidgen/space-light",
  "label": "a blue giant (22,000 K): white-hot with a blue limb and a wide pale halo",
  "use": "star(renderer, \"blue-giant\")  // or star(renderer, {temperature: 12000, seed})",
  "seed": 15},
(s) => close(s, "blue-giant"));

definePart({"name": "sun-far", "kind": "light", "module": "vidgen/space-light",
  "label": "a far sun: a brilliant point with a soft glow, six thin spikes and faint lens ghosts",
  "use": "const sun = star(renderer, \"sun\", {direction: [x, y, z], spikes: 6, flare: 0.5}); scene.add(sun.object)",
  "options": {"spikes": 6, "flare": 1, "glare": 1}, "seed": 4},
(s) => {
  const sky = spaceSky(s.renderer, {seed: s.seed});
  s.scene.add(sky.object);
  const sun = star(s.renderer, "sun", {direction: [0.3, 0.1, -1], ...s.options});
  s.scene.add(sun.object);
  aim(s, [0, 0, 0], [0.62, 0.0, -1.6], 40);
  return {finish: false};
});

// the Earth-like world's limb from 0.25 radii up, the sun `alt` degrees over it
function limb(s, alt, options = {}) {
  const sky = spaceSky(s.renderer, {seed: 4});
  const earth = planet(s.renderer, "earth", {spin: 0, ...small(s)});
  const r = 1.25, horizon = Math.asin(1 / r), rad = Math.PI / 180;
  const d = (phi, az) => [Math.sin(phi) * Math.cos(az * rad), Math.sin(phi) * Math.sin(az * rad), -Math.cos(phi)];
  const sun = star(s.renderer, "sun", {direction: d(horizon + alt * rad, 25), ...options});
  s.scene.add(sky.object, earth.object, sun.object);
  const v = d(horizon + 6.5 * rad, 16);
  aim(s, [0, 0, r], [v[0], v[1], r + v[2]], 40, [0, 0, 1]);
  const light = spaceLight({scene: s.scene, camera: s.camera, sun, bodies: [earth], sky});
  return {finish: false, frame(t) { earth.update(t); sun.update(t); light.update(t); }};
}

definePart({"name": "sunrise-limb", "kind": "light", "module": "vidgen/space-light",
  "label": "sunrise over a world's limb: the glare over the dark ground, the lit line of air",
  "use": "const light = spaceLight({scene, camera, sun, bodies: [earth], sky}); light.update(t)  // the bodies hide and redden the glare",
  "options": {"altitude": 0.6}},
(s) => limb(s, s.options.altitude, {flare: 1}));

definePart({"name": "sunrise-diamond", "kind": "light", "module": "vidgen/space-light",
  "label": "the same a moment earlier: a red spark where the first sliver of sun clears the air",
  "use": "the same scene with the sun's middle 0.15 degrees over the limb (its radius is 0.27)",
  "options": {"altitude": 0.15}},
(s) => limb(s, s.options.altitude));

// a moon and the Earth-like world at true sizes and distance (3.67 moon radii at 221), the world behind the camera
function moonAndWorld(s, sunDirection, lightOptions = {}, turn = 70) {
  const moon = planet(s.renderer, "moon", {spin: 100, ...small(s)}), earth = planet(s.renderer, "earth", {size: 256});
  earth.object.position.set(-150, 45, 150); earth.object.scale.setScalar(3.67);
  s.scene.add(moon.object, earth.object);
  aim(s, [0.5, 0.1, 5.6], [-0.35, 0, 0], 26);
  const light = spaceLight({scene: s.scene, camera: s.camera, sun: sunDirection, bodies: [moon, earth], ...lightOptions});
  return {finish: false, frame(t) { moon.update(t + turn); earth.update(t); light.update(t); }};
}

definePart({"name": "planet-shine", "kind": "light", "module": "vidgen/space-light",
  "label": "planet-shine: a crescent moon whose dark side is lit by the world behind the camera",
  "use": "spaceLight({scene, camera, sun, bodies: [moon, earth], shine: 1})  // shine: 0 leaves the night side black",
  "options": {"shine": 1}},
(s) => moonAndWorld(s, [0.9, 0.12, -0.72], {shine: s.options.shine}));

definePart({"name": "eclipse-shadow", "kind": "light", "module": "vidgen/space-light",
  "label": "an eclipse: a moon's shadow on its world, dark middle and soft edge",
  "use": "spaceLight({scene, camera, sun, bodies: [earth, moon], eclipses: true})",
  "options": {"eclipses": true}},
(s) => {
  const earth = planet(s.renderer, "earth", {spin: 0, ...small(s)}), moon = planet(s.renderer, "moon", {size: 256});
  const sun = [0.8, 0.25, 0.55], n = Math.hypot(...sun);
  moon.object.position.set(58 * sun[0] / n + 0.25, 58 * sun[1] / n + 0.18, 58 * sun[2] / n); moon.object.scale.setScalar(0.2725);
  earth.object.scale.setScalar(1.5);
  moon.object.position.multiplyScalar(1.5); moon.object.scale.multiplyScalar(1.5);
  s.scene.add(earth.object, moon.object);
  aim(s, [2.6, 1.1, 5.3], [0, 0, 0], 40);
  const light = spaceLight({scene: s.scene, camera: s.camera, sun, bodies: [earth, moon], eclipses: s.options.eclipses});
  return {finish: false, frame(t) { earth.update(t); moon.update(t); light.update(t); }};
});

definePart({"name": "eclipse-moon", "kind": "light", "module": "vidgen/space-light",
  "label": "a moon entering its world's shadow: the copper light the world's air bends into it",
  "use": "the same option; a world with air leaves a faint red light in its shadow",
  "options": {"eclipses": true}},
(s) => {
  const moon = planet(s.renderer, "moon", {spin: 0, ...small(s)}), earth = planet(s.renderer, "earth", {size: 256});
  const sun = [0.6, 0.1, 0.79];
  earth.object.position.set(221 * sun[0] + 2.7, 221 * sun[1] + 1.9, 221 * sun[2]); earth.object.scale.setScalar(3.67);
  s.scene.add(moon.object, earth.object);
  aim(s, [0.6, 0.2, 5.6], [0, 0, 0], 26);
  const light = spaceLight({scene: s.scene, camera: s.camera, sun, bodies: [moon, earth], eclipses: s.options.eclipses});
  return {finish: false, frame(t) { moon.update(t); earth.update(t); light.update(t); }};
});

// the exposure modes on one scene: a half-lit world before the Milky Way
function exposure(s, lightOptions, sunDirection = [1, 0.25, 0.1]) {
  const sky = spaceSky(s.renderer, {seed: 4});
  const earth = planet(s.renderer, "earth", {spin: 0, ...small(s)});
  earth.object.position.set(1.1, 0, 0); earth.object.scale.setScalar(1.35);
  s.scene.add(sky.object, earth.object);
  aim(s, [0, 0, 6], [0, 0, 0], 40);
  const light = spaceLight({scene: s.scene, camera: s.camera, sun: sunDirection, bodies: [earth], sky, ...lightOptions});
  return {finish: false, frame(t) { earth.update(t); light.update(t); }};
}

definePart({"name": "exposure-film", "kind": "light", "module": "vidgen/space-light",
  "label": "exposure \"film\" (the default, a convention): the stars stay beside a sunlit world",
  "use": "spaceLight({scene, camera, sun, bodies, sky, exposure: \"film\"})",
  "options": {"exposure": "film"}},
(s) => exposure(s, s.options));

definePart({"name": "exposure-camera", "kind": "light", "module": "vidgen/space-light",
  "label": "exposure \"camera\", ev 0 (honest): exposed for the day side, the stars are gone",
  "use": "spaceLight({..., sky, exposure: \"camera\", ev: 0})",
  "options": {"exposure": "camera", "ev": 0}},
(s) => exposure(s, s.options));

definePart({"name": "exposure-camera-stars", "kind": "light", "module": "vidgen/space-light",
  "label": "exposure \"camera\", ev 20 (honest): exposed for the stars, the world burns out",
  "use": "spaceLight({..., sky, exposure: \"camera\", ev: 20})  // ev may be a function of t",
  "options": {"exposure": "camera", "ev": 20}},
(s) => exposure(s, s.options));

definePart({"name": "exposure-auto", "kind": "light", "module": "vidgen/space-light",
  "label": "exposure \"auto\" (honest): only a thin crescent is lit, so the exposure opens: stars, a burnt rim",
  "use": "spaceLight({..., sky, exposure: \"auto\"})  // from what is in the frame at t; no state between frames",
  "options": {"exposure": "auto"}},
(s) => exposure(s, s.options, [0.45, 0.1, -1]));
