// The ready-made grounds of vidgen/space-land for the registry vidgen/parts:
// what `vidgen parts` draws on its contact sheet. Drawn straight to the canvas ({finish: false}: the
// dome and the ground apply the tone curve themselves), at the quality "fast" (the sheet's tiles are small).
import {definePart} from "vidgen/parts";
import {air, sunDirection} from "vidgen/space-air";
import {sea} from "vidgen/space-sea";
import {spaceSky} from "vidgen/space-sky";
import {land, vacuum, PRESETS, RADII} from "vidgen/space-land";

// a camera `over` metres over the ground under it (or `height` metres over the world's sphere) at (x, z), looking
// `pitch` degrees up towards `heading` (0: -z, north); the air the preset names (none: a black sky with stars), the ground, a sea where asked
function show(s, options, {water = false} = {}) {
  const o = s.options, a = o.pitch * Math.PI / 180, b = o.heading * Math.PI / 180, preset = PRESETS[options.preset] ?? {air: "earth", world: options.world};
  let stars = null, what = preset.air;
  if (what === null) { stars = spaceSky(s.renderer, {seed: s.seed, size: 256}); s.scene.add(stars.object); what = vacuum(RADII[preset.world]); }
  s.scene.remove(s.key, s.fill);
  const dome = air(s.renderer, what, {sun: sunDirection(o.elevation, o.azimuth), stars, ...(preset.air === null ? {exposure: "camera", ev: 1.3} : {})});
  const ground = land(s.renderer, dome, {quality: "fast", ...options});
  let x = o.x ?? 0, z = o.z ?? 0;
  if (o.towards) {            // stand `back` metres before the highest ("peak") or the lowest ("floor") ground within 30 km, looking at it
    let best = null;
    for (let i = -20; i <= 20; i++) for (let j = -20; j <= 20; j++) { const v = ground.heightAt(i * 1500, j * 1500) * (o.towards === "floor" ? -1 : 1); if (!best || v > best[0]) best = [v, i * 1500, j * 1500]; }
    x = best[1] - Math.sin(b) * o.back; z = best[2] + Math.cos(b) * o.back;
  }
  const h = o.height ?? ground.heightAt(x, z) + o.over;
  s.camera.position.set(x, h, z); s.camera.up.set(0, 1, 0); s.camera.near = 1; s.camera.far = 1e8; s.camera.fov = o.fov;
  s.camera.lookAt(x + Math.sin(b) * Math.cos(a) * 1000, h + Math.sin(a) * 1000, z - Math.cos(b) * Math.cos(a) * 1000); s.camera.updateProjectionMatrix(); s.camera.updateMatrixWorld();
  s.scene.add(dome.object, ground.object);
  dome.update(0, {camera: s.camera}); ground.update(0, {camera: s.camera});
  if (water) { const w = sea(s.renderer, dome, {seed: s.seed, depth: ground.depth}); s.scene.add(w.object); w.update(2, {camera: s.camera}); }
  return {finish: false};
}

definePart({"name": "land-alpine", "kind": "land", "module": "vidgen/space-land",
  "label": "an Earth-like range at low sun from 2.5 km over the valley: snow above a line and off the steep faces, long shadows",
  "use": "const ground = land(renderer, sky, {preset: \"alpine\"}); scene.add(ground.object); ground.update(t, {camera}); ground.heightAt(x, z)",
  "options": {"over": 2500, "pitch": -9, "heading": 80, "fov": 55, "elevation": 9, "azimuth": 150}, "seed": 3},
(s) => show(s, {preset: "alpine"}));

definePart({"name": "land-alpine-from-30-km", "kind": "land", "module": "vidgen/space-land",
  "label": "the same range from 30 km: ranges and valleys under the air's blue line",
  "use": "land(renderer, sky, {preset: \"alpine\"})  // ground.horizon: {distance, dip, height, over}",
  "options": {"height": 30000, "pitch": -18, "heading": 80, "fov": 55, "elevation": 12, "azimuth": 150}, "seed": 3},
(s) => show(s, {preset: "alpine"}));

definePart({"name": "land-mars", "kind": "land", "module": "vidgen/space-land",
  "label": "a Mars-like desert under the Mars-like air: dust, craters of every size, low scarps",
  "use": "land(air(renderer, \"mars\"), {preset: \"mars\"})  // the world \"mars\" of vidgen/space-bodies at [-8, 40]",
  "options": {"over": 800, "pitch": -7, "heading": 20, "fov": 55, "elevation": 18, "azimuth": 100}, "seed": 3},
(s) => show(s, {preset: "mars"}));

definePart({"name": "land-canyon", "kind": "land", "module": "vidgen/space-land",
  "label": "canyon land on the invented world \"ochre\": winding canyons 1,100 m deep with stepped, banded walls, mesas between (a look)",
  "use": "land(renderer, sky, {preset: \"canyon\"})  // canyons: {depth, width, length, floor, steps, branches}",
  "options": {"towards": "floor", "back": 6000, "over": 3000, "pitch": -20, "heading": 100, "fov": 55, "elevation": 22, "azimuth": 200}, "seed": 3},
(s) => show(s, {preset: "canyon"}));

definePart({"name": "land-dunes", "kind": "land", "module": "vidgen/space-land",
  "label": "a sand sea at sunset: dunes 90 m high across the wind, the Mars-like air's blue glow round the sun",
  "use": "land(renderer, sky, {preset: \"dunes\"})  // dunes: {height, length, direction, field}",
  "options": {"over": 150, "pitch": -6, "heading": 230, "fov": 55, "elevation": 6, "azimuth": 255}, "seed": 3},
(s) => show(s, {preset: "dunes"}));

definePart({"name": "land-snow", "kind": "land", "module": "vidgen/space-land",
  "label": "the ice world \"boreas\": snow hills and a few craters under a thin air (invented)",
  "use": "land(air(renderer, \"thin\"), {preset: \"snow\"})",
  "options": {"over": 1200, "pitch": -8, "heading": 0, "fov": 55, "elevation": 14, "azimuth": 80}, "seed": 3},
(s) => show(s, {preset: "snow"}));

definePart({"name": "land-volcanic", "kind": "land", "module": "vidgen/space-land",
  "label": "a volcano of the lava world \"ember\" after sunset: a cone 3 km high, the lake in its crater and the channels down its flanks glowing (invented; a look)",
  "use": "land(renderer, sky, {preset: \"volcanic\"})  // volcanoes: {height, radius, spacing, density}; ground.setGlow(level)",
  "options": {"towards": "peak", "back": 14000, "over": 1200, "pitch": 3, "heading": 0, "fov": 50, "elevation": -4, "azimuth": 20}, "seed": 3},
(s) => show(s, {preset: "volcanic"}));

definePart({"name": "land-airless", "kind": "land", "module": "vidgen/space-land",
  "label": "an airless crater field: the grey \"moon\", a black sky, hard shadows (camera exposure, 1.3 stops up)",
  "use": "const sky = air(renderer, vacuum(RADII.moon), {exposure: \"camera\", ev: 1.3}); land(renderer, sky, {preset: \"airless\"})",
  "options": {"over": 800, "pitch": -8, "heading": 40, "fov": 55, "elevation": 10, "azimuth": 110}, "seed": 5},
(s) => show(s, {preset: "airless"}));

definePart({"name": "land-coast", "kind": "land", "module": "vidgen/space-land",
  "label": "a coast: the same Earth-like world's hills rising out of the sea of vidgen/space-sea, the shallows paler",
  "use": "const ground = land(renderer, sky, {world: \"earth\", at: [-11.5, -15.2], mountains: {from: -300, to: 500, base: 0.35, height: 2600, length: 9000}}); sea(renderer, sky, {depth: ground.depth})",
  "options": {"x": 6000, "z": 6000, "height": 900, "pitch": -7, "heading": 320, "fov": 60, "elevation": 26, "azimuth": 215}, "seed": 3},
(s) => show(s, {world: "earth", at: [-11.5, -15.2], mountains: {from: -300, to: 500, base: 0.35, height: 2600, length: 9000}}, {water: true}));
