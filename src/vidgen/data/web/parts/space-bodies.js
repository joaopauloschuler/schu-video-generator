// The ready-made worlds of vidgen/space-bodies for the registry vidgen/parts:
// what `vidgen parts` draws on its contact sheet. Every tile is one body of radius 1.5 at
// the origin under one hard sun, drawn straight to the canvas; a small tile bakes small maps.
import {definePart} from "vidgen/parts";
import {planet} from "vidgen/space-bodies";

const SUN = [1, 0.35, 0.6];
// one body in the stage: turned so that its best side faces the camera, the camera moved for a view
function show(s, what, options = {}, {radius = 1.5, sun = SUN, turn = 0, from = null, to = [0, 0, 0], fov = null, lean = 0} = {}) {
  const given = {seed: s.seed, ...(s.height < 300 ? {size: 256} : {}), ...options};
  if (given.seed === undefined) delete given.seed;                      // a ready-made world keeps its own seed
  const body = planet(s.renderer, what, given);
  body.object.scale.setScalar(radius);
  s.scene.add(body.object);
  if (from) { s.camera.position.set(...from); s.camera.lookAt(...to); }
  if (fov) { s.camera.fov = fov; s.camera.updateProjectionMatrix(); }
  s.camera.updateMatrixWorld();
  // straight to the canvas: a body draws its own anti-aliased edge and tone curve, and FXAA would break thin rings into dots
  return {finish: false, frame(t) { body.update(t, {sun}); body.spinner.rotation.y += turn * Math.PI / 180; body.object.rotation.x = lean * Math.PI / 180; }};
}

definePart({"name": "body-rocky", "kind": "body", "module": "vidgen/space-bodies",
  "label": "type rocky: an airless, cratered world with dark plains and rayed craters",
  "use": "const b = planet(renderer, {type: \"rocky\", seed}); scene.add(b.object); b.update(t, {sun: [1, 0.3, 0.6]})",
  "options": {"maria": 0.3, "craters": 1, "rays": 1}, "seed": 5},
(s) => show(s, {type: "rocky", ...s.options}, {}, {sun: [1, 0.2, 0.25]}));

definePart({"name": "body-icy", "kind": "body", "module": "vidgen/space-bodies",
  "label": "type icy: a bright ice shell crossed by long dark cracks",
  "use": "planet(renderer, {type: \"icy\", seed, cracks: 1, dark: 0.3})",
  "options": {"cracks": 1, "dark": 0.3, "craters": 0.4}, "seed": 5},
(s) => show(s, {type: "icy", ...s.options}));

definePart({"name": "body-desert", "kind": "body", "module": "vidgen/space-bodies",
  "label": "type desert: dust and dark ground, a canyon, volcanoes, polar caps, thin air",
  "use": "planet(renderer, {type: \"desert\", seed, canyons: 1, caps: 1})",
  "options": {"dark": 0.35, "caps": 1, "canyons": 1}, "seed": 5},
(s) => show(s, {type: "desert", ...s.options}));

definePart({"name": "body-ocean", "kind": "body", "module": "vidgen/space-bodies",
  "label": "type ocean: seas with sun glint, continents, ice caps, clouds, air, city lights",
  "use": "planet(renderer, {type: \"ocean\", seed, land: 0.3, clouds: 0.5})",
  "options": {"land": 0.3, "clouds": 0.5}, "seed": 5},
(s) => show(s, {type: "ocean", ...s.options}));

definePart({"name": "body-lava", "kind": "body", "module": "vidgen/space-bodies",
  "label": "type lava: a dark crust broken into plates, glowing where it parts",
  "use": "planet(renderer, {type: \"lava\", seed, heat: 0.6})",
  "options": {"heat": 0.6}, "seed": 5},
(s) => show(s, {type: "lava", ...s.options}));

definePart({"name": "body-gas", "kind": "body", "module": "vidgen/space-bodies",
  "label": "type gas: belts and zones, stirred edges, a great storm and white ovals",
  "use": "planet(renderer, {type: \"gas\", seed, bands: 17, drift: 2}); b.update(t) drifts the bands",
  "options": {"bands": 17, "turbulence": 1, "storms": 6}, "seed": 5},
(s) => show(s, {type: "gas", ...s.options}, {}, {turn: -60}));

definePart({"name": "body-ice-giant", "kind": "body", "module": "vidgen/space-bodies",
  "label": "type ice-giant: smooth, faint bands, haze, a dark storm",
  "use": "planet(renderer, {type: \"ice-giant\", seed, palette: \"neptune\"})",
  "options": {"palette": "neptune", "spot": 1}, "seed": 5},
(s) => show(s, {type: "ice-giant", ...s.options}, {}, {turn: -60}));

// the ready-made worlds (PRESETS): the Solar System's lookalikes, then the invented ones
definePart({"name": "world-mercury", "kind": "body", "module": "vidgen/space-bodies", "label": "Mercury-like: grey-brown, heavily cratered, rayed", "use": "const b = planet(renderer, \"mercury\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"mercury\", {space})"},
(s) => show(s, "mercury", {seed: undefined}, {turn: 0}));

definePart({"name": "world-venus", "kind": "body", "module": "vidgen/space-bodies", "label": "Venus-like: a cream cloud deck under thick air", "use": "const b = planet(renderer, \"venus\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"venus\", {space})"},
(s) => show(s, "venus", {seed: undefined}, {turn: 0}));

definePart({"name": "world-earth", "kind": "body", "module": "vidgen/space-bodies", "label": "Earth-like: oceans, continents, weather, ice caps", "use": "const b = planet(renderer, \"earth\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"earth\", {space})"},
(s) => show(s, "earth", {seed: undefined}, {turn: 0}));

definePart({"name": "world-moon", "kind": "body", "module": "vidgen/space-bodies", "label": "Moon-like: highlands, maria, rayed craters", "use": "const b = planet(renderer, \"moon\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"moon\", {space})"},
(s) => show(s, "moon", {seed: undefined}, {turn: 0}));

definePart({"name": "world-mars", "kind": "body", "module": "vidgen/space-bodies", "label": "Mars-like: rust dust, dark ground, a canyon, caps, thin haze", "use": "const b = planet(renderer, \"mars\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"mars\", {space})"},
(s) => show(s, "mars", {seed: undefined}, {turn: 0}));

definePart({"name": "world-jupiter", "kind": "body", "module": "vidgen/space-bodies", "label": "Jupiter-like: brown belts, cream zones, a red storm", "use": "const b = planet(renderer, \"jupiter\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"jupiter\", {space})"},
(s) => show(s, "jupiter", {seed: undefined}, {turn: -60}));

definePart({"name": "world-saturn", "kind": "body", "module": "vidgen/space-bodies", "label": "Saturn-like: butterscotch bands, flattened, broad rings", "use": "const b = planet(renderer, \"saturn\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"saturn\", {space})"},
(s) => show(s, "saturn", {seed: undefined}, {radius: 1.0, turn: 0, lean: 18}));

definePart({"name": "world-uranus", "kind": "body", "module": "vidgen/space-bodies", "label": "Uranus-like: pale cyan, almost blank, on its side, thin rings", "use": "const b = planet(renderer, \"uranus\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"uranus\", {space})"},
(s) => show(s, "uranus", {seed: undefined}, {radius: 1.0, turn: 0, lean: 25}));

definePart({"name": "world-neptune", "kind": "body", "module": "vidgen/space-bodies", "label": "Neptune-like: deep blue, streaks, a dark storm", "use": "const b = planet(renderer, \"neptune\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"neptune\", {space})"},
(s) => show(s, "neptune", {seed: undefined}, {turn: -60}));

definePart({"name": "world-io", "kind": "body", "module": "vidgen/space-bodies", "label": "Io-like: sulphur yellows, dark vents, red fallout", "use": "const b = planet(renderer, \"io\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"io\", {space})"},
(s) => show(s, "io", {seed: undefined}, {turn: 0}));

definePart({"name": "world-europa", "kind": "body", "module": "vidgen/space-bodies", "label": "Europa-like: bright ice, brown lineae", "use": "const b = planet(renderer, \"europa\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"europa\", {space})"},
(s) => show(s, "europa", {seed: undefined}, {turn: 0}));

definePart({"name": "world-ganymede", "kind": "body", "module": "vidgen/space-bodies", "label": "Ganymede-like: dark old ground and bright grooved ice", "use": "const b = planet(renderer, \"ganymede\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"ganymede\", {space})"},
(s) => show(s, "ganymede", {seed: undefined}, {turn: 0}));

definePart({"name": "world-callisto", "kind": "body", "module": "vidgen/space-bodies", "label": "Callisto-like: dark, saturated with bright craters", "use": "const b = planet(renderer, \"callisto\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"callisto\", {space})"},
(s) => show(s, "callisto", {seed: undefined}, {turn: 0}));

definePart({"name": "world-titan", "kind": "body", "module": "vidgen/space-bodies", "label": "Titan-like: an orange haze ball with a deep fuzzy limb", "use": "const b = planet(renderer, \"titan\"); scene.add(b.object); b.update(t, {sun})  // with ctx.orbits: planet(renderer, \"titan\", {space})"},
(s) => show(s, "titan", {seed: undefined}, {turn: 0}));

definePart({"name": "world-ember", "kind": "body", "module": "vidgen/space-bodies", "label": "invented: a lava world with seas of fire and smoke", "use": "const b = planet(renderer, \"ember\"); scene.add(b.object); b.update(t, {sun})"},
(s) => show(s, "ember", {seed: undefined}, {turn: 0}));

definePart({"name": "world-boreas", "kind": "body", "module": "vidgen/space-bodies", "label": "invented: a blue ice world with thin rings", "use": "const b = planet(renderer, \"boreas\"); scene.add(b.object); b.update(t, {sun})"},
(s) => show(s, "boreas", {seed: undefined}, {radius: 1.0, turn: 0, lean: 18}));

definePart({"name": "world-ochre", "kind": "body", "module": "vidgen/space-bodies", "label": "invented: a desert of ochre dust and teal-grey ground", "use": "const b = planet(renderer, \"ochre\"); scene.add(b.object); b.update(t, {sun})"},
(s) => show(s, "ochre", {seed: undefined}, {turn: 0}));

definePart({"name": "world-tempest", "kind": "body", "module": "vidgen/space-bodies", "label": "invented: a violet giant with storms and rings", "use": "const b = planet(renderer, \"tempest\"); scene.add(b.object); b.update(t, {sun})"},
(s) => show(s, "tempest", {seed: undefined}, {radius: 1.0, turn: -60, lean: 18}));

definePart({"name": "world-verdant", "kind": "body", "module": "vidgen/space-bodies", "label": "invented: a warm, wet, cloudy ocean world", "use": "const b = planet(renderer, \"verdant\"); scene.add(b.object); b.update(t, {sun})"},
(s) => show(s, "verdant", {seed: undefined}, {turn: 0}));

definePart({"name": "world-cinder", "kind": "body", "module": "vidgen/space-bodies", "label": "invented: a dark red cratered rock", "use": "const b = planet(renderer, \"cinder\"); scene.add(b.object); b.update(t, {sun})"},
(s) => show(s, "cinder", {seed: undefined}, {turn: 0}));

definePart({"name": "world-azure", "kind": "body", "module": "vidgen/space-bodies", "label": "invented: a blue ice giant with pale rings", "use": "const b = planet(renderer, \"azure\"); scene.add(b.object); b.update(t, {sun})"},
(s) => show(s, "azure", {seed: undefined}, {radius: 1.0, turn: -60, lean: 18}));

definePart({"name": "rings-broad", "kind": "body", "module": "vidgen/space-bodies",
  "label": "rings, style broad: provinces, a main gap, ringlets; they shadow the globe and it them",
  "use": "planet(renderer, {type: \"gas\", palette: \"saturn\", rings: {seed, inner: 1.25, outer: 2.3, gaps: 7}})",
  "options": {"inner": 1.25, "outer": 2.3, "gaps": 7}, "seed": 3},
(s) => show(s, {type: "gas", palette: "saturn", contrast: 0.55, spot: 0, oblateness: 0.09, rings: {seed: s.seed, ...s.options}}, {}, {radius: 1.0, lean: 24, sun: [-0.7, 0.45, 0.6]}));

definePart({"name": "rings-narrow", "kind": "body", "module": "vidgen/space-bodies",
  "label": "rings, style narrow: a few thin rings and a little dust",
  "use": "planet(renderer, {type: \"ice-giant\", rings: {style: \"narrow\", seed, inner: 1.5, outer: 2.1, gaps: 8}})",
  "options": {"inner": 1.5, "outer": 2.1, "gaps": 8}, "seed": 3},
(s) => show(s, {type: "ice-giant", palette: "azure", rings: {style: "narrow", seed: s.seed, color: 0xd8e0e8, ...s.options}}, {}, {radius: 1.0, lean: 28}));

definePart({"name": "rings-far-side", "kind": "body", "module": "vidgen/space-bodies",
  "label": "rings from their unlit side: the thin parts glow, the dense ones are dark",
  "use": "the same rings; the camera on the other side of their plane from the sun",
  "seed": 3},
(s) => show(s, {type: "gas", palette: "saturn", contrast: 0.55, spot: 0, oblateness: 0.09, rings: {seed: s.seed}}, {}, {radius: 1.0, lean: -22, sun: [-0.7, 0.45, 0.6]}));

definePart({"name": "body-crescent", "kind": "body", "module": "vidgen/space-bodies",
  "label": "a crescent: the lit rim of air round the night side, towns in the dark",
  "use": "any body with air, the sun behind it: b.update(t, {sun: [0.7, 0.2, -1]})",
  "seed": 13},
(s) => show(s, "earth", {}, {sun: [0.7, 0.2, -1]}));

definePart({"name": "body-limb", "kind": "body", "module": "vidgen/space-bodies",
  "label": "a close limb: the air as a blue shell over the horizon (size: 1024 for a sharp ground)",
  "use": "camera a tenth of a radius up, looking along the horizon; planet(renderer, \"earth\", {size: 1024})",
  "seed": 13},
(s) => show(s, "earth", {}, {radius: 1, from: [0, 0.35, 1.09], to: [0.5, 1.1, 0.2], fov: 40, sun: [0.7, 0.6, -0.25]}));
