// The ready-made skies of vidgen/space-clouds for the registry vidgen/parts:
// what `vidgen parts` draws on its contact sheet. Drawn straight to the canvas ({finish: false}: the
// dome, the sea and the clouds apply the tone curve themselves).
import {definePart} from "vidgen/parts";
import {air, sunDirection} from "vidgen/space-air";
import {sea} from "vidgen/space-sea";
import {clouds, giantSky, giantAir} from "vidgen/space-clouds";
import {spaceSky} from "vidgen/space-sky";

// a camera `height` metres up, looking `pitch` degrees up towards -z; the air, the clouds, and a sea under them when asked
function show(s, what, options, {stars = false, water = false, at = 0} = {}) {
  const o = s.options, a = o.pitch * Math.PI / 180, sky = stars ? spaceSky(s.renderer, {seed: s.seed, size: 256}) : null;
  if (sky) s.scene.add(sky.object);
  s.scene.remove(s.key, s.fill);
  s.camera.position.set(0, o.height, 0); s.camera.up.set(0, 1, 0); s.camera.near = 1; s.camera.far = 1e8; s.camera.fov = o.fov;
  s.camera.lookAt(0, o.height + Math.sin(a) * 1000, -Math.cos(a) * 1000); s.camera.updateProjectionMatrix(); s.camera.updateMatrixWorld();
  const dome = air(s.renderer, what, {sun: sunDirection(o.elevation, o.azimuth), stars: sky});
  dome.update(0, {camera: s.camera});
  const weather = clouds(s.renderer, dome, typeof options === "function" ? options(dome) : {seed: s.seed, ...options});
  const below = water ? sea(s.renderer, dome, {seed: s.seed, shade: weather.shade}) : null;
  s.scene.add(dome.object);
  if (below) { s.scene.add(below.object); below.update(2, {camera: s.camera}); }
  s.scene.add(weather.object);
  weather.update(at, {camera: s.camera});
  return {finish: false};
}

definePart({"name": "clouds-fair", "kind": "cloud", "module": "vidgen/space-clouds",
  "label": "the sky \"fair\" from 150 m at noon: a field of cumulus with flat grey bases, cirrus high over it",
  "use": "const weather = clouds(renderer, sky, {sky: \"fair\", seed}); scene.add(weather.object); weather.update(t, {camera})",
  "options": {"height": 150, "pitch": 20, "fov": 60, "elevation": 55, "azimuth": 140}, "seed": 11},
(s) => show(s, "earth", {sky: "fair"}));

definePart({"name": "clouds-sea-of-cloud", "kind": "cloud", "module": "vidgen/space-clouds",
  "label": "the sky \"overcast\" from 10 km: a closed deck with a rolling top to its own horizon",
  "use": "clouds(renderer, sky, {sky: \"overcast\", seed})  // or decks: [{type: \"stratus\", base: 1800, top: 3000}]",
  "options": {"height": 10000, "pitch": -9, "fov": 55, "elevation": 35, "azimuth": 40}, "seed": 4},
(s) => show(s, "earth", {sky: "overcast"}));

definePart({"name": "clouds-sunset", "kind": "cloud", "module": "vidgen/space-clouds",
  "label": "sunset over a cloud sea from 6 km: the sun 2.5 degrees up, every swell of the deck lit from the side",
  "use": "air(renderer, \"earth\", {sun: sunDirection(2.5, 12)}); clouds(renderer, sky, {sky: \"overcast\"})",
  "options": {"height": 6000, "pitch": -5, "fov": 50, "elevation": 2.5, "azimuth": 12}, "seed": 4},
(s) => show(s, "earth", {sky: "overcast"}));

definePart({"name": "clouds-towers", "kind": "cloud", "module": "vidgen/space-clouds",
  "label": "the sky \"towers\" from 4 km: cloud towers 11 km high with anvils, rising through a broken deck",
  "use": "clouds(renderer, sky, {sky: \"towers\", seed})  // or towers: {count, radius, top, at: [[x, z], ...]}",
  "options": {"height": 4000, "pitch": 3, "fov": 55, "elevation": 30, "azimuth": 60}, "seed": 4},
(s) => show(s, "earth", {sky: "towers"}));

definePart({"name": "clouds-between-decks", "kind": "cloud", "module": "vidgen/space-clouds",
  "label": "the sky \"layers\" from 4.6 km: between a cloud sea and a broken deck, whose shadows lie on the sea",
  "use": "clouds(renderer, sky, {sky: \"layers\", seed})",
  "options": {"height": 4600, "pitch": -1, "fov": 60, "elevation": 22, "azimuth": 50}, "seed": 4},
(s) => show(s, "earth", {sky: "layers"}));

definePart({"name": "clouds-lightning", "kind": "cloud", "module": "vidgen/space-clouds",
  "label": "lightning inside a tower at dusk: a flash at a stated time (film exposure; a flash's strength is a look)",
  "use": "clouds(renderer, sky, {sky: \"towers\", lightning: {times: trackArrays(ctx.music, {hits: [\"kick\"]}).hits.kick}})",
  "options": {"height": 3200, "pitch": 4, "fov": 55, "elevation": -4, "azimuth": 20}, "seed": 4, "at": 1.03},
(s) => show(s, "earth", {sky: "towers", lightning: {times: [1, 1.01, 1.02], power: 1.5}}, {stars: true, at: 1.03}));

definePart({"name": "clouds-over-sea", "kind": "cloud", "module": "vidgen/space-clouds",
  "label": "cumulus over the sea of vidgen/space-sea from 3.5 km: the clouds' shadows on the water",
  "use": "const weather = clouds(renderer, sky, {sky: \"fair\"}); sea(renderer, sky, {shade: weather.shade})",
  "options": {"height": 3500, "pitch": -35, "fov": 60, "elevation": 50, "azimuth": 30}, "seed": 4},
(s) => show(s, "earth", {sky: "fair"}, {water: true}));

definePart({"name": "clouds-giant", "kind": "cloud", "module": "vidgen/space-clouds",
  "label": "a giant of gas from inside: the decks of the \"jupiter\" of vidgen/space-bodies in its bands' colours (drawn 40 times narrower than true), a haze, the dark below (heights, air and band width: a look)",
  "use": "const sky = air(renderer, giantAir(\"jupiter\")); clouds(renderer, sky, giantSky(\"jupiter\", {scale: sky.model.H}))",
  "options": {"height": 125000, "pitch": -7, "fov": 60, "elevation": 35, "azimuth": 60, "world": "jupiter"}, "seed": 4},
(s) => show(s, giantAir(s.options.world), (dome) => ({...giantSky(s.options.world, {scale: dome.model.H}), seed: s.seed})));

definePart({"name": "clouds-ice-giant", "kind": "cloud", "module": "vidgen/space-clouds",
  "label": "the same for the \"neptune\" of vidgen/space-bodies: blue decks under a teal sky (a look)",
  "use": "const sky = air(renderer, giantAir(\"neptune\")); clouds(renderer, sky, giantSky(\"neptune\", {scale: sky.model.H}))",
  "options": {"height": 60000, "pitch": -5, "fov": 60, "elevation": 25, "azimuth": 40, "world": "neptune"}, "seed": 4},
(s) => show(s, giantAir(s.options.world), (dome) => ({...giantSky(s.options.world, {scale: dome.model.H}), seed: s.seed})));
