// vidgen/space-craft: a spacecraft kit (DESIGN.md §122.10). Part of schu-video-generator (MIT licence);
// imported by a page as "vidgen/space-craft".
//
//   import {craft, craftKit, attach, around, craftEnvironment} from "vidgen/space-craft";
//   const probe = craft("probe", {seed: 7});                 // a ready-made craft (CRAFT), another design per seed
//   scene.add(probe.object);                                 // metres; +z the nose, +y up, engines fire toward -z
//   probe.update(t, {sun: [3, 1, 2], camera});               // wings track the sun, lights blink, far away: a glint
//   const ship = craft("ship", {seed: 2}).fly(space, {body: "Ship", attitude: "prograde", burn: {seconds: 2}});
//   function frame(t) { space.update(t, view); ship.update(t); light.update(t); finish.render(t); }
//   const env = craftEnvironment(renderer, scene, {at: probe.object}); scene.environment = env.texture;
//   sun.occluders = [...sun.occluders, ...probe.occluders];  // the craft hides the sun's glare (vidgen/space-light)
//
// A craft of your own, from the same parts:
//   const kit = craftKit({seed: 3});
//   const bus = kit.hull({shape: "prism", sides: 8, radius: 1, length: 1.4, skin: "foil"});
//   attach(bus, "fore", kit.dish({diameter: 3}));
//   around(bus, () => kit.solarWing({panels: 3}), {count: 2, along: 0.5});
//   const mine = kit.craft(bus);
//
// Everything is made here, from numbers: the designs are invented (no real or film spacecraft, no
// markings), the surfaces are computed (foil that crinkles, plating with panel lines and rivets, solar
// cells, tiles). Units are metres. Nothing is random at draw time and nothing is kept between frames:
// what a craft shows at t is a function of t, its seed and what update is given. The light is the
// scene's: one hard sun and planet-shine from vidgen/space-light (its `shadows` for the craft's own
// shadows), reflections from `scene.environment` (craftEnvironment: the sky and the worlds near the craft).
import * as THREE from "three";
import {mergeGeometries} from "three/addons/utils/BufferGeometryUtils.js";
import {rng} from "vidgen/music-time";

export const VERSION = 1;
const PREFIX = "vidgen/space-craft";
const TAU = Math.PI * 2, RAD = Math.PI / 180;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const mix = (a, b, u) => a + (b - a) * u;
const smooth = (a, b, x) => { const u = clamp((x - a) / (b - a)); return u * u * (3 - 2 * u); };
const smoother = (u) => { u = clamp(u); return u * u * u * (u * (u * 6 - 15) + 10); };
const V3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const isVec = (v) => Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === "number" && Number.isFinite(x));
const fail = (message) => new Error(`${PREFIX}: ${message}`);
function distance(a, b) {
  const d = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = d[0]; d[0] = i;
    for (let j = 1; j <= b.length; j++) { const cur = d[j]; d[j] = Math.min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = cur; }
  }
  return d[b.length];
}
function hint(key, known) {
  const best = known.map((k) => [distance(String(key).toLowerCase(), k.toLowerCase()), k]).sort((x, y) => x[0] - y[0])[0];
  return best && best[0] <= Math.max(2, String(key).length / 3) ? ` (did you mean "${best[1]}"?)` : "";
}
function known(where, object, keys) {
  if (object === null || typeof object !== "object" || Array.isArray(object)) throw fail(`${where} must be an object, got ${JSON.stringify(object)}`);
  for (const k of Object.keys(object)) if (!keys.includes(k)) throw fail(`${where}: unknown option "${k}"${hint(k, keys)}; options: ${keys.join(", ")}`);
}
function choice(where, value, choices) {
  if (!choices.includes(value)) throw fail(`${where}: "${value}"${hint(value, choices)}; one of: ${choices.join(", ")}`);
  return value;
}
// whole-number hash -> [0, 1): the same on every machine
const hash2 = (x, y, k = 0) => { let h = Math.imul(x | 0, 374761393) ^ Math.imul(y | 0, 668265263) ^ Math.imul(k | 0, 1274126177); h = Math.imul(h ^ (h >>> 13), 1103515245); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
const pick = (r, list) => list[Math.min(list.length - 1, Math.floor(r() * list.length))];
const range = (r, a, b) => a + (b - a) * r();
const whole = (r, a, b) => a + Math.min(b - a, Math.floor(r() * (b - a + 1)));

// ---------- surfaces: maps computed once (the same for every craft; a craft's seed changes colours and shapes) ----------
const TEXTURES = new Map(), ANISOTROPY = 2;      // measured: 4 costs a frame-filling craft 0.18 s a frame more than 1 in software GL
function texture(name, make) {
  if (!TEXTURES.has(name)) TEXTURES.set(name, make());
  return TEXTURES.get(name);
}
// a tiling map of `size` texels standing for `tile` metres
function dataTexture(data, size, tile, srgb = false) {
  const t = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.magFilter = THREE.LinearFilter; t.minFilter = THREE.LinearMipmapLinearFilter;
  t.generateMipmaps = true; t.anisotropy = ANISOTROPY; t.repeat.set(1 / tile, 1 / tile);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.needsUpdate = true;
  return t;
}
// a normal map from a height field (texels of height per texel of width times `strength`), wrapping
function normalsOf(h, size, strength) {
  const d = new Uint8Array(size * size * 4), at = (x, y) => h[((y + size) % size) * size + ((x + size) % size)];
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const dx = (at(x + 1, y) - at(x - 1, y)) * strength, dy = (at(x, y + 1) - at(x, y - 1)) * strength, l = 1 / Math.hypot(dx, dy, 1), k = (y * size + x) * 4;
    d[k] = 127.5 - dx * l * 127.5; d[k + 1] = 127.5 - dy * l * 127.5; d[k + 2] = 127.5 + l * 127.5; d[k + 3] = 255;
  }
  return d;
}
/** The crinkled foil of a thermal blanket, as numbers: {normal, orm, albedo} (Uint8Array RGBA, `size` square,
 * tiling). A crumpled sheet: at three scales the lowest (or highest) of slightly bowed facets, one for every
 * scattered point, so the creases between them are sharp, straight and of every length; a slow billow over
 * all. Creases are duller, and each large facet has its own gloss and a slightly different tone. */
export function foilMaps(size = 512, seed = 1) {
  const h = new Float32Array(size * size), cell = new Int32Array(size * size);
  const levels = [[4, 1.0, 1, 2.6], [11, 0.95, -1, 3.2], [29, 0.9, 1, 3.0], [71, 0.9, -1, 2.4]];       // grid, slope, valleys (1) or ridges (-1), height in texels x size / 512
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const u = x / size, v = y / size;
    let sum = 2.2 * Math.sin(TAU * (u + 0.3 * Math.sin(TAU * v))) + 1.6 * Math.sin(TAU * (2 * v + u) + 1.3) + 1.2 * Math.sin(TAU * (3 * u - 2 * v) + 0.4);
    for (let L = 0; L < levels.length; L++) {
      const [g, slope, sign, height] = levels[L], cx = u * g, cy = v * g, ix = Math.floor(cx), iy = Math.floor(cy), k = seed * 16 + L;
      let best = 1e9, id = 0;
      for (let j = -1; j <= 1; j++) for (let i = -1; i <= 1; i++) {
        const qx = ((ix + i) % g + g) % g, qy = ((iy + j) % g + g) % g, dx = cx - (ix + i + hash2(qx, qy, k)), dy = cy - (iy + j + hash2(qx, qy, k + 100));
        const a = hash2(qx, qy, k + 200) * TAU, m = slope * (0.35 + 0.65 * hash2(qx, qy, k + 300));
        const f = 0.5 * hash2(qx, qy, k + 400) + m * (Math.cos(a) * dx + Math.sin(a) * dy) + 0.75 * (dx * dx + dy * dy);
        if (f < best) { best = f; id = qx + qy * g; }
      }
      sum += sign * best * height * 512 / g * 0.09;
      if (L === 0) cell[y * size + x] = id;
    }
    h[y * size + x] = sum * size / 512;
  }
  const normal = normalsOf(h, size, 0.5), orm = new Uint8Array(size * size * 4), albedo = new Uint8Array(size * size * 4), at = (x, y) => h[((y + size) % size) * size + ((x + size) % size)];
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const k = (y * size + x) * 4, bend = Math.abs(at(x + 1, y) + at(x - 1, y) + at(x, y + 1) + at(x, y - 1) - 4 * at(x, y)), crease = clamp(bend * 0.9);
    const q = hash2(cell[y * size + x], 3, seed), tone = hash2(cell[y * size + x], 5, seed);
    orm[k] = 255; orm[k + 1] = clamp(0.3 + 0.3 * q + 0.3 * crease) * 255; orm[k + 2] = 255; orm[k + 3] = 255;
    const dark = 1 - 0.14 * tone - 0.2 * crease;                                // some facets show the deeper amber of the layers under
    albedo[k] = 255 * dark; albedo[k + 1] = 255 * (dark - 0.05 * tone); albedo[k + 2] = 255 * (dark - 0.1 * tone); albedo[k + 3] = 255;
  }
  return {normal, orm, albedo};
}
/** Plating, as numbers: {albedo (grey), normal, orm}. Panels from a seeded splitting of the square (or a grid of
 * `tiles` with every other row moved half a tile), each a little pillowed and of its own tone and gloss, a groove
 * between them, rivets along the grooves (`rivets`), a few specks where dust has hit, a faint cloud of grime. */
export function platingMaps(size = 512, {seed = 1, depth = 5, tiles = 0, rivets = true, pillow = 1, tone = 0.05, specks = 30, groove = 1} = {}) {
  const r = rng(seed * 977 + 5), rects = [];
  if (tiles > 0) { const s = size / tiles; for (let j = 0; j < tiles; j++) for (let i = 0; i < tiles; i++) rects.push([Math.round((i + (j % 2) * 0.5) * s), Math.round(j * s), Math.round(s), Math.round(s)]); }
  else {
    const split = (x, y, w, h, d) => {
      const stop = d <= 0 || (d < depth - 1 && r() < 0.18) || Math.max(w, h) < size / 12;
      if (stop) { rects.push([x, y, w, h]); return; }
      const wide = w * (0.75 + 0.5 * r()) > h, cut = Math.round((wide ? w : h) * pick(r, [1 / 3, 0.5, 0.5, 2 / 3]));
      if (wide) { split(x, y, cut, h, d - 1); split(x + cut, y, w - cut, h, d - 1); } else { split(x, y, w, cut, d - 1); split(x, y + cut, w, h - cut, d - 1); }
    };
    split(0, 0, size, size, depth);
  }
  const h = new Float32Array(size * size), albedo = new Uint8Array(size * size * 4), orm = new Uint8Array(size * size * 4), shade = new Float32Array(size * size).fill(1), rough = new Float32Array(size * size);
  rects.forEach(([x0, y0, w, hh], n) => {
    const t = 1 + tone * (hash2(n, 3, seed) * 2 - 1) * (hash2(n, 9, seed) < 0.12 ? 2.4 : 1), g = 0.62 + 0.2 * hash2(n, 5, seed);
    for (let j = 0; j < hh; j++) for (let i = 0; i < w; i++) {
      const k = ((y0 + j) % size) * size + (x0 + i) % size, edge = Math.min(i, j, w - 1 - i, hh - 1 - j);
      const a = (2 * (i + 0.5) / w - 1), b = (2 * (j + 0.5) / hh - 1), cut = edge < 1 ? 1 : edge < 2 ? 0.35 : 0;
      h[k] = pillow * 0.9 * (1 - a * a * a * a) * (1 - b * b * b * b) * Math.min(w, hh) / 64 - groove * 1.6 * cut;
      shade[k] = t * (1 - 0.5 * cut * groove) * (1 - 0.05 * smooth(7, 2, edge) * groove); rough[k] = cut ? 0.95 : g;
    }
    if (rivets && Math.min(w, hh) > size / 10) {
      const step = size / 40, inset = Math.max(3, size / 128), stamp = (cx, cy) => {
        for (let j = -2; j <= 2; j++) for (let i = -2; i <= 2; i++) {
          const d = Math.hypot(i, j), k = (((Math.round(cy) + j) % size + size) % size) * size + ((Math.round(cx) + i) % size + size) % size;
          if (d < 1.6) { h[k] += 0.9 * (1 - d / 1.6); shade[k] *= 0.9 + 0.05 * (1 - d / 1.6); } else if (d < 2.4) shade[k] *= 0.95;
        }
      };
      for (let s = inset + step / 2; s < w - inset; s += step) { stamp(x0 + s, y0 + inset); stamp(x0 + s, y0 + hh - 1 - inset); }
      for (let s = inset + step * 1.5; s < hh - inset - step; s += step) { stamp(x0 + inset, y0 + s); stamp(x0 + w - 1 - inset, y0 + s); }
    }
  });
  for (let n = 0; n < specks; n++) {
    const cx = Math.floor(r() * size), cy = Math.floor(r() * size), big = r() < 0.2 ? 1.6 : 0.9;
    for (let j = -3; j <= 3; j++) for (let i = -3; i <= 3; i++) {
      const d = Math.hypot(i, j) / big, k = ((cy + j + size) % size) * size + (cx + i + size) % size;
      if (d < 1) { shade[k] *= 0.62; h[k] -= 0.5; } else if (d < 2.2) shade[k] *= 1.035;
    }
  }
  const cloud = (u, v) => 0.5 + 0.25 * Math.sin(TAU * (u + 0.4 * Math.sin(TAU * v))) * Math.sin(TAU * (v * 2 + 0.3)) + 0.25 * Math.sin(TAU * (3 * u - v) + 2) * Math.sin(TAU * (2 * v + u));
  for (let k = 0, y = 0; y < size; y++) for (let x = 0; x < size; x++, k++) {
    const c = clamp(shade[k] * (0.955 + 0.045 * cloud(x / size, y / size))) * 255;
    albedo[4 * k] = albedo[4 * k + 1] = albedo[4 * k + 2] = c; albedo[4 * k + 3] = 255;
    orm[4 * k] = 255; orm[4 * k + 1] = clamp(rough[k] + 0.06 * (cloud(y / size, x / size) - 0.5)) * 255; orm[4 * k + 2] = 255; orm[4 * k + 3] = 255;
  }
  return {albedo, normal: normalsOf(h, size, 0.5), orm, panels: rects.length};
}
/** Solar cells, as numbers: {albedo, normal, orm}: `cells` x `cells` dark blue cells with cut corners, thin
 * collecting lines, two bus bars each, the pale sheet between them. */
export function cellMaps(size = 512, cells = 4, seed = 1) {
  const albedo = new Uint8Array(size * size * 4), orm = new Uint8Array(size * size * 4), h = new Float32Array(size * size), s = size / cells;
  for (let k = 0, y = 0; y < size; y++) for (let x = 0; x < size; x++, k++) {
    const i = Math.floor(x / s), j = Math.floor(y / s), a = x - i * s, b = y - j * s, e = Math.min(a, b, s - 1 - a, s - 1 - b), corner = Math.min(a, s - 1 - a) + Math.min(b, s - 1 - b);
    const gap = e < 1.5 || corner < s * 0.14, bar = Math.abs(a - s * 0.27) < 1.2 || Math.abs(a - s * 0.73) < 1.2, line = Math.floor(b) % 4 === 0;
    const q = hash2(i, j, seed), q2 = hash2(i, j, seed + 7);
    let c = [0.012 + 0.012 * q, 0.022 + 0.02 * q2, 0.085 + 0.05 * q], rough = 0.27 + 0.07 * q2, metal = 0.7;
    if (line) { c = c.map((v) => v + 0.02); rough += 0.05; }
    if (bar) { c = [0.5, 0.52, 0.56]; rough = 0.34; metal = 1; }
    if (gap) { c = [0.2, 0.2, 0.22]; rough = 0.6; metal = 0.3; }
    h[k] = gap ? -1 : 0;
    for (let n = 0; n < 3; n++) albedo[4 * k + n] = 255 * Math.pow(c[n], 1 / 2.2);
    albedo[4 * k + 3] = 255; orm[4 * k] = 255; orm[4 * k + 1] = rough * 255; orm[4 * k + 2] = metal * 255; orm[4 * k + 3] = 255;
  }
  return {albedo, normal: normalsOf(h, size, 0.6), orm};
}
// lengthwise ribs (an engine bell's cooling channels): u runs round the bell
function ribMaps(size = 64) {
  const h = new Float32Array(size * size);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) h[y * size + x] = Math.pow(0.5 + 0.5 * Math.cos(TAU * x / 8), 0.6) * 1.6;
  return normalsOf(h, size, 0.7);
}
const MAPS = {
  foil: () => { const m = foilMaps(512, 1); return {map: dataTexture(m.albedo, 512, 1.1, true), normalMap: dataTexture(m.normal, 512, 1.1), orm: dataTexture(m.orm, 512, 1.1)}; },
  plating: () => { const m = platingMaps(512, {seed: 1, pillow: 0.4}); return {map: dataTexture(m.albedo, 512, 2.4, true), normalMap: dataTexture(m.normal, 512, 2.4), orm: dataTexture(m.orm, 512, 2.4)}; },
  tiles: () => { const m = platingMaps(256, {seed: 2, tiles: 8, rivets: false, pillow: 0.6, tone: 0.2, specks: 12}); return {map: dataTexture(m.albedo, 256, 1.2, true), normalMap: dataTexture(m.normal, 256, 1.2), orm: dataTexture(m.orm, 256, 1.2)}; },
  cells: () => { const m = cellMaps(512, 4, 1); return {map: dataTexture(m.albedo, 512, 0.6, true), normalMap: dataTexture(m.normal, 512, 0.6), orm: dataTexture(m.orm, 512, 0.6)}; },
  ribs: () => { const t = dataTexture(ribMaps(64), 64, 1); t.repeat.set(1, 1); return {normalMap: t}; },
};
const maps = (name) => texture(name, MAPS[name]);

/** The named surfaces of a craft (`kit.materials[name]`, a part's `skin`). */
export const SKINS = Object.freeze(["paint", "accent", "aluminium", "foil", "foil-silver", "foil-black", "tiles", "cells", "back", "dark", "steel", "radiator", "dish", "glass", "window", "nozzle", "rubber"]);
/** Accent colours a seed chooses from (muted: a stripe, a hatch, a cargo box). */
export const ACCENTS = Object.freeze([0xc8542a, 0x2f5fa8, 0xa8322e, 0x1f8079, 0xd0a22a, 0x56606e, 0x7a4a9a]);
/** The warm light of a window lit from inside (linear), and how bright it is drawn. */
export const WINDOW_LIGHT = Object.freeze({color: 0xffc98a, intensity: 1.25});

/** The most the sun's own mirror image on a surface may shine (in units of a white surface facing the sun): a
 * flat panel at the mirror angle is a bright glint that blooms, not a white hole in the picture. */
export const GLARE = {value: 5};
function capGlare(shader) {
  shader.uniforms.uGlareCap = GLARE;
  shader.fragmentShader = shader.fragmentShader.replace("void main() {", "uniform float uGlareCap;\nvoid main() {")
    .replace("#include <lights_fragment_end>", "#include <lights_fragment_end>\nreflectedLight.directSpecular = min(reflectedLight.directSpecular, vec3(uGlareCap));");
}
function makeMaterials({accent, foil, wear}) {
  const std = (o, m, {scale = 1, rough = 1, metal = 1} = {}) => {
    const t = m ? maps(m) : {};
    const mat = new THREE.MeshStandardMaterial({vertexColors: true, ...o, roughness: (o.roughness ?? 1) * rough, metalness: (o.metalness ?? 1) * metal});
    if (t.map) mat.map = t.map;
    if (t.normalMap) { mat.normalMap = t.normalMap; mat.normalScale = new THREE.Vector2(scale, scale); }
    if (t.orm) { mat.roughnessMap = t.orm; if (m === "cells") mat.metalnessMap = t.orm; }
    mat.onBeforeCompile = capGlare; mat.customProgramCacheKey = () => "vidgen-craft";
    return mat;
  };
  const gold = {gold: 0xe0a13c, amber: 0xd98a2b, pale: 0xe6bd62}[foil] ?? 0xe0a13c;
  const M = {
    paint: std({color: 0xd6d4cf, roughness: 0.8, metalness: 0.04}, "plating", {scale: 0.7 * wear}),
    accent: std({color: accent, roughness: 0.75, metalness: 0.05}, "plating", {scale: 0.7 * wear}),
    aluminium: std({color: 0xc3c6ca, roughness: 0.82, metalness: 0.92}, "plating", {scale: 0.7 * wear}),
    foil: std({color: gold, roughness: 1, metalness: 0.9}, "foil", {scale: 1}),
    "foil-silver": std({color: 0xd9dbde, roughness: 0.9, metalness: 0.95}, "foil", {scale: 0.9}),
    "foil-black": std({color: 0x2b2826, roughness: 1, metalness: 0.5}, "foil", {scale: 0.8}),
    tiles: std({color: 0x1b1c20, roughness: 1.15, metalness: 0.05}, "tiles", {scale: 1}),
    cells: std({color: 0xffffff, roughness: 1, metalness: 1}, "cells", {scale: 0.8}),
    back: std({color: 0x1d1f23, roughness: 0.55, metalness: 0.6}),
    dark: std({color: 0x34373c, roughness: 0.55, metalness: 0.8}),
    steel: std({color: 0xb4b8bd, roughness: 0.5, metalness: 0.95}),
    radiator: std({color: 0xcfd0d2, roughness: 0.7, metalness: 0.1}, "plating", {scale: 0.4}),
    dish: std({color: 0xdddcd7, roughness: 0.78, metalness: 0.02}, "plating", {scale: 0.35}),
    glass: std({color: 0x0a0d12, roughness: 0.04, metalness: 1}),
    window: std({color: 0x1a130b, roughness: 0.2, metalness: 0.2, emissive: WINDOW_LIGHT.color, emissiveIntensity: WINDOW_LIGHT.intensity}),
    nozzle: std({color: 0x8d8780, roughness: 0.5, metalness: 1}, "ribs", {scale: 0.9}),
    rubber: std({color: 0x121314, roughness: 0.9, metalness: 0}),
  };
  for (const [name, m] of Object.entries(M)) { m.name = name; m.envMapIntensity = 1; }
  return M;
}

// ---------- geometry: everything a part draws goes into bins, one mesh per surface ----------
const X = V3(1, 0, 0), Y = V3(0, 1, 0), Z = V3(0, 0, 1);
// an orthonormal frame whose y is `n` and whose x is as near `u` as it can be
function frameOf(n, u) {
  const y = n.clone().normalize(), x = u.clone().addScaledVector(y, -u.dot(y));
  if (x.lengthSq() < 1e-10) x.copy(Math.abs(y.x) < 0.9 ? X : Z).addScaledVector(y, -(Math.abs(y.x) < 0.9 ? y.x : y.z));
  x.normalize();
  return new THREE.Matrix4().makeBasis(x, y, V3().crossVectors(x, y));
}
// the matrix that stands a shape made along +y on `p`, its +y along `n`, its +x toward `u`
const stand = (p, n, u = Z) => frameOf(n, u).setPosition(p);
// a rod's matrix: a cylinder of length |b - a| made along +y, from a to b
const between = (a, b) => stand(a.clone().add(b).multiplyScalar(0.5), b.clone().sub(a), X);
const flat = (g) => { const f = g.toNonIndexed(); f.computeVertexNormals(); return f; };
const lathe = (profile, sides) => new THREE.LatheGeometry(profile.map(([r, y]) => new THREE.Vector2(Math.max(r, 1e-4), y)), sides);
const profileLength = (profile) => profile.slice(1).reduce((s, p, i) => s + Math.hypot(p[0] - profile[i][0], p[1] - profile[i][1]), 0);

class Bins {
  constructor(kit) { this.kit = kit; this.map = new Map(); }
  /** Add `geometry` with surface `skin`. `uv`: "box" (metres, from its faces), [su, sv] (its own 0..1 times
   * these metres) or "keep"; `at`: a Matrix4; `tint`: [r, g, b] or (x, y, z) => [r, g, b] in the shape's own axes. */
  add(skin, geometry, {at = null, uv = "box", tint = null} = {}) {
    if (!this.kit.materials[skin]) throw fail(`no surface "${skin}"${hint(skin, SKINS)}; surfaces: ${SKINS.join(", ")}`);
    let g = geometry;
    if (!g.index) g.setIndex(Array.from({length: g.attributes.position.count}, (_, i) => i));
    const pos = g.attributes.position, nor = g.attributes.normal, n = pos.count, k = this.kit.count++;
    const ou = skin === "cells" ? 0 : hash2(k, 1, this.kit.seed) * 7, ov = skin === "cells" ? 0 : hash2(k, 2, this.kit.seed) * 7;
    const uvs = new Float32Array(n * 2), old = g.attributes.uv;
    for (let i = 0; i < n; i++) {
      let a = 0, b = 0;
      if (uv === "box") {
        const ax = Math.abs(nor.getX(i)), ay = Math.abs(nor.getY(i)), az = Math.abs(nor.getZ(i));
        if (az >= ax && az >= ay) { a = pos.getX(i); b = pos.getY(i); } else if (ax >= ay) { a = pos.getZ(i); b = pos.getY(i); } else { a = pos.getX(i); b = pos.getZ(i); }
      } else if (old) { a = old.getX(i) * (uv === "keep" ? 1 : uv[0]); b = old.getY(i) * (uv === "keep" ? 1 : uv[1]); }
      uvs[2 * i] = a + (uv === "keep" ? 0 : ou); uvs[2 * i + 1] = b + (uv === "keep" ? 0 : ov);
    }
    const colors = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) { const c = typeof tint === "function" ? tint(pos.getX(i), pos.getY(i), pos.getZ(i)) : (tint ?? [1, 1, 1]); colors[3 * i] = c[0]; colors[3 * i + 1] = c[1]; colors[3 * i + 2] = c[2]; }
    const out = new THREE.BufferGeometry();
    out.setIndex(g.index); out.setAttribute("position", pos); out.setAttribute("normal", nor);
    out.setAttribute("uv", new THREE.BufferAttribute(uvs, 2)); out.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    if (at) out.applyMatrix4(at);
    if (!this.map.has(skin)) this.map.set(skin, []);
    this.map.get(skin).push(out);
    return this;
  }
  box(skin, w, h, d, at, options) { return this.add(skin, new THREE.BoxGeometry(w, h, d), {at, ...options}); }
  /** A rod from a to b (Vector3) of radius r. */
  rod(skin, a, b, r, sides = 6, options) { return this.add(skin, new THREE.CylinderGeometry(r, r, a.distanceTo(b), this.kit.far ? Math.min(sides, 4) : sides, 1, true), {at: between(a, b), uv: [TAU * r, a.distanceTo(b)], ...options}); }
  /** A tube through `points` (a bent pipe). */
  pipe(skin, points, r, sides = 6) { return this.add(skin, new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), this.kit.far ? points.length * 2 : points.length * 5, r, this.kit.far ? 4 : sides, false), {uv: "keep"}); }
  group(name) {
    const g = new THREE.Group(); g.name = name;
    for (const [skin, list] of this.map) {
      const mesh = new THREE.Mesh(list.length === 1 ? list[0] : mergeGeometries(list, false), this.kit.materials[skin]);
      mesh.castShadow = skin !== "window"; mesh.receiveShadow = true;
      g.add(mesh);
    }
    g.userData.points = {}; g.userData.part = name;
    return g;
  }
}
const point = (p, n, u = Z) => ({p, n: n.clone().normalize(), u});

/** A part's point: a name of its `userData.points`, {angle (degrees round its axis), along (0..1), out (metres)}
 * on a hull, truss or boom, or {p, n, u} (Vector3: place, outward direction, the direction a child's "up" follows). */
export function pointOf(part, at = "mount") {
  const P = (part && part.userData && part.userData.points) || null;
  if (!P) throw fail("not a part of this kit (no points): attach parts made by craftKit()");
  if (typeof at === "string") { if (!P[at]) throw fail(`${part.userData.part} has no point "${at}"${hint(at, Object.keys(P))}; points: ${Object.keys(P).join(", ")}`); return P[at]; }
  if (at && at.p && at.n) return {u: Z, ...at};
  known("a point", at, ["angle", "along", "out", "across"]);
  if (!part.userData.surface) throw fail(`${part.userData.part} has no surface to stand things on; use one of its points: ${Object.keys(P).join(", ")}`);
  return part.userData.surface(at.angle ?? 0, at.along ?? 0.5, at.out ?? 0, at.across ?? 0);
}
/** Fix `child` to `parent`: the child's point `mount` on the parent's point `at`, facing away from it; `roll`
 * (degrees) turns the child round that direction, `gap` (metres) lifts it off. Returns the child. */
export function attach(parent, at, child, mount = "mount", options = {}) {
  known("attach options", options, ["roll", "gap"]);
  const a = pointOf(parent, at), b = pointOf(child, mount), roll = options.roll ?? 0, gap = options.gap ?? 0;
  const R = frameOf(a.n.clone().negate(), a.u).multiply(frameOf(b.n, b.u).transpose());
  if (roll) R.premultiply(new THREE.Matrix4().makeRotationAxis(a.n.clone().normalize(), roll * RAD));
  child.quaternion.setFromRotationMatrix(R);
  child.position.copy(a.p).addScaledVector(a.n, gap).sub(b.p.clone().applyMatrix4(R));
  parent.add(child);
  return child;
}
/** Repeat round a hull's axis: `make(i)` gives the i-th part, fixed at angle + i * span / count. Options: count,
 * angle, span (360), along, out, mount, roll, gap. Returns the parts. */
export function around(parent, make, options = {}) {
  known("around options", options, ["count", "angle", "span", "along", "out", "mount", "roll", "gap"]);
  const count = options.count ?? 2, span = options.span ?? 360, out = [];
  for (let i = 0; i < count; i++) out.push(attach(parent, {angle: (options.angle ?? 0) + i * span / count, along: options.along ?? 0.5, out: options.out ?? 0}, make(i), options.mount ?? "mount", {roll: options.roll ?? 0, gap: options.gap ?? 0}));
  return out;
}
/** A pair, one each side: around() with count 2. */
export const mirror = (parent, make, options = {}) => around(parent, make, {...options, count: 2});

// ---------- engine plumes: light summed along the view ray through an exhaust that widens into the vacuum ----------
/** The kinds of exhaust: `spread` (how fast it widens: the tangent of its half angle), `length` (exit radii to
 * 1/e), `core` and `edge` colours (linear), `gain`, `diamonds` (shock diamonds: only for an engine firing in air). */
export const PLUMES = Object.freeze({
  chemical: Object.freeze({spread: 0.34, length: 9, core: [1.0, 0.5, 0.14], edge: [1.0, 0.2, 0.03], gain: 0.6, diamonds: 0, spike: 1.3, haze: 0.4}),
  vacuum: Object.freeze({spread: 0.62, length: 11, core: [0.82, 0.9, 1.0], edge: [0.3, 0.45, 1.0], gain: 0.46, diamonds: 0, spike: 0.36}),
  air: Object.freeze({spread: 0.045, length: 12, core: [1.0, 0.85, 0.6], edge: [1.0, 0.4, 0.08], gain: 0.9, diamonds: 1, spike: 0.12, haze: 1.5}),
  ion: Object.freeze({spread: 0.07, length: 26, core: [0.35, 0.75, 1.0], edge: [0.03, 0.25, 1.0], gain: 0.42, diamonds: 0, spike: 0.22}),
  rcs: Object.freeze({spread: 0.5, length: 7, core: [1.0, 0.98, 0.95], edge: [0.75, 0.85, 1.0], gain: 0.3, diamonds: 0, spike: 0.25}),
});
// how many samples a view ray takes through a plume, and how far (in lengths to 1/e) a plume is drawn: measured,
// five engines filling a 720p frame cost 2 s a frame with 18 even samples over 3.2 lengths, 0.65 s as it is
const PLUME_STEPS = 10, PLUME_REACH = 2.4;
const PLUME_VERT = /* glsl */`
varying vec3 vPos; varying vec3 vCam;
void main() { vPos = position; vCam = (inverse(modelMatrix) * vec4(cameraPosition, 1.0)).xyz; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const PLUME_FRAG = /* glsl */`
precision highp float;
varying vec3 vPos; varying vec3 vCam;
uniform vec3 uCore, uEdge; uniform vec4 uShape; uniform vec4 uNow; uniform float uHaze;   // uShape: exit radius, spread, length, bound radius; uNow: power, time, diamonds, spike
void main() {
  vec3 rd = normalize(vPos - vCam);
  float tB = length(vPos - vCam), t0 = 0.0, Re = uShape.x;
  float a = dot(rd.xz, rd.xz), b = dot(vCam.xz, rd.xz), c = dot(vCam.xz, vCam.xz) - uShape.w * uShape.w;
  if (a > 1e-9) { float h = b * b - a * c; if (h > 0.0) t0 = max(t0, (-b - sqrt(h)) / a); }
  if (abs(rd.y) > 1e-6) { float y0 = (-uShape.z * REACH * Re - vCam.y) / rd.y, y1 = (1.3 * Re - vCam.y) / rd.y; t0 = max(t0, min(y0, y1)); }
  if (tB <= t0) discard;
  // the samples crowd where the ray passes nearest the plume's axis (t = tc + h tan u, u in equal steps): the
  // bright narrow core is met by several of them however long the ray's way through the faint outer plume is
  float tc = a > 1e-9 ? clamp(-b / a, t0, tB) : t0;
  vec3 pc = vCam + rd * tc;
  float sc = -pc.y / Re, wc = sc > 0.0 ? 1.0 + sc * uShape.y : 1.0;
  float h = sqrt(dot(pc.xz, pc.xz) + 0.3 * wc * wc * Re * Re) / sqrt(max(a, 1e-4));
  float u0 = atan((t0 - tc) / h), du = (atan((tB - tc) / h) - u0) / float(STEPS);
  vec3 sum = vec3(0.0);
  float power = uNow.x, reach = uShape.z * (0.35 + 0.65 * power);
  for (int i = 0; i < STEPS; i++) {
    float tn = tan(u0 + (float(i) + 0.5) * du), dt = h * (1.0 + tn * tn) * du;
    vec3 p = (vCam + rd * (tc + h * tn)) / Re;
    float s = -p.y, r2 = dot(p.xz, p.xz), sp = max(s, 0.0);
    float w = s > 0.0 ? 1.0 + s * uShape.y : max(0.3, 1.0 + s * 0.55), q2 = r2 / (w * w);
    float body = exp(-q2 * 2.3 - sp / reach) / (w * w) * smoothstep(-1.3, -0.2, s);
    float w2 = 0.34 * (1.0 + sp * 0.12);
    float spike = uNow.w * exp(-r2 / (w2 * w2) - sp / (reach * 0.3)) * smoothstep(-1.3, -0.5, s);
    float flow = 1.0 + 0.09 * sin(s * 2.7 - uNow.y * 31.0) / (1.0 + s * 0.2);
    vec3 light = uEdge * (body * flow * 0.32 * uHaze) + uCore * (spike * 4.0 + body * body * w * w * 0.14 * uHaze) + vec3(spike * spike * 2.5 / max(uNow.w, 0.05));
    #ifdef DIAMONDS
      float k = max(cos(s * 2.0 - 1.0), 0.0); k *= k;
      light *= 1.0 + 5.0 * k * k * exp(-s * 0.14 - q2 * 3.0) - 0.55;
    #endif
    sum += light * (s < 0.0 ? 0.45 : 1.0) * dt;
  }
  gl_FragColor = vec4(sum / Re * power, 1.0);
}`;
/** How an engine's light flickers at t (a sum of fixed sines round 1; `i` tells engines apart). */
export const flicker = (t, i = 0) => 1 + 0.045 * Math.sin(TAU * 17.3 * t + i * 2.1) + 0.03 * Math.sin(TAU * 41.7 * t + i * 4.3) + 0.035 * Math.sin(TAU * 6.1 * t + i);
function makePlume(kind, exit, options = {}) {
  const k = {...PLUMES[kind], ...options}, L = k.length * PLUME_REACH * exit, bound = exit * (1 + k.spread * k.length * PLUME_REACH) * 1.1;
  const geometry = new THREE.CylinderGeometry(exit * 1.15, bound, L + 1.3 * exit, 20, 1, false);
  geometry.translate(0, 1.3 * exit - (L + 1.3 * exit) / 2, 0);
  const material = new THREE.ShaderMaterial({vertexShader: PLUME_VERT, fragmentShader: PLUME_FRAG, defines: {STEPS: PLUME_STEPS, REACH: PLUME_REACH.toFixed(1), ...(k.diamonds ? {DIAMONDS: 1} : {})}, side: THREE.BackSide, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false,
    uniforms: {uCore: {value: V3(...k.core).multiplyScalar(k.gain)}, uEdge: {value: V3(...k.edge).multiplyScalar(k.gain)}, uShape: {value: new THREE.Vector4(exit, k.spread, k.length, bound)}, uNow: {value: new THREE.Vector4(0, 0, 0, k.spike)}, uHaze: {value: k.haze ?? 1}}});
  const mesh = new THREE.Mesh(geometry, material);
  mesh.userData.keep = true; mesh.userData.plume = {kind, exit, color: k.edge.map((c, i) => 0.6 * c + 0.4 * k.core[i])}; mesh.visible = false; mesh.renderOrder = 5; mesh.name = `plume ${kind}`;
  return mesh;
}
// a light seen as a soft point: at least `uSize.y` pixels wide however far (its light kept), drawn over the craft
const GLOW_VERT = /* glsl */`
uniform vec2 uSize; uniform vec2 uView; uniform float uFloor; varying vec2 vUv; varying float vGain;
void main() {
  vec4 mv = modelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0); vec4 clip = projectionMatrix * mv;
  float px = uSize.x * length(modelMatrix[0].xyz) * uView.y * 0.5 * projectionMatrix[1][1] / max(-mv.z, 1e-6), shown = max(px, uSize.y);
  vGain = min(1.0, (px * px) / (shown * shown)); vUv = position.xy * 2.0;
  clip.xy += position.xy * 2.0 * shown * 2.0 / uView * clip.w; gl_Position = clip; }`;
const GLOW_FRAG = /* glsl */`
precision highp float; uniform vec3 uColor; uniform float uLevel, uFloor; varying vec2 vUv; varying float vGain;
void main() { float r2 = dot(vUv, vUv); if (r2 > 1.0) discard; float g = exp(-r2 * 5.5) - 0.0041; gl_FragColor = vec4(uColor * (max(uLevel * vGain, uFloor) * max(g, 0.0)), 1.0); }`;
const GLOW_GEOMETRY = new THREE.PlaneGeometry(1, 1);
// the least radius (pixels) a point of light is drawn with: its gaussian is then 0.7 px wide, so it neither
// flickers between pixels nor vanishes; what it loses in size it keeps in brightness
const GLOW_PIXELS = 2.3;
function makeGlow(color, radius, minPixels) {
  const material = new THREE.ShaderMaterial({vertexShader: GLOW_VERT, fragmentShader: GLOW_FRAG, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false,
    uniforms: {uColor: {value: new THREE.Color(color)}, uLevel: {value: 1}, uSize: {value: new THREE.Vector2(radius, minPixels)}, uView: {value: new THREE.Vector2(1280, 720)}, uFloor: {value: 0}}});
  const mesh = new THREE.Mesh(GLOW_GEOMETRY, material);
  mesh.userData.keep = true; mesh.renderOrder = 6;
  mesh.onBeforeRender = (renderer) => { const v = renderer.getCurrentViewport(VIEW); material.uniforms.uView.value.set(v.z, v.w); };
  return mesh;
}
const VIEW = new THREE.Vector4();
/** How bright a light of `kind` is at t (0..1): "steady", "strobe" (two short flashes every 1.6 s), "beacon" (one
 * soft flash a second), "pulse" (a slow breath). `phase` (0..1) shifts it. */
export function blink(kind, t, phase = 0) {
  const u = (x) => x - Math.floor(x);
  if (kind === "strobe") { const p = u(t / 1.6 + phase) * 1.6; return p < 0.07 || (p > 0.2 && p < 0.27) ? 1 : 0; }
  if (kind === "beacon") { const p = u(t + phase); return p < 0.3 ? Math.pow(Math.sin(Math.PI * p / 0.3), 2) : 0; }
  if (kind === "pulse") return 0.55 + 0.45 * Math.sin(TAU * (t / 3 + phase));
  return 1;
}
export const LIGHTS = Object.freeze({port: {color: 0xff2a1c, kind: "steady"}, starboard: {color: 0x22ff5a, kind: "steady"}, white: {color: 0xfff4e0, kind: "steady"},
  strobe: {color: 0xffffff, kind: "strobe"}, beacon: {color: 0xff3a22, kind: "beacon"}, dock: {color: 0x9fd0ff, kind: "pulse"}});

// ---------- the kit: parts in metres, each a THREE.Group with named points ----------
export const DETAILS = Object.freeze(["near", "far"]);
export const HULL_SHAPES = Object.freeze(["cylinder", "taper", "cone", "nose", "sphere", "box", "prism"]);
export const FOILS = Object.freeze(["gold", "amber", "pale"]);
const KIT_DEFAULTS = Object.freeze({seed: 1, accent: null, foil: null, detail: "near", wear: 1, lit: 0.6});

/** The parts of a craft, sharing one set of surfaces. Options: `seed`; `accent` (a colour; default one of
 * ACCENTS by the seed); `foil` ("gold" | "amber" | "pale"); `detail` ("near": everything; "far": fewer sides, no
 * rails, rivet heads or small boxes: a craft for a fleet or the distance); `wear` (0..2: how deep the plating's
 * lines are drawn); `lit` (0..1: the share of windows lit from inside). */
export class CraftKit {
  constructor(options = {}) {
    known("craftKit options", options, Object.keys(KIT_DEFAULTS));
    const o = this.options = {...KIT_DEFAULTS, ...options};
    choice("detail", o.detail, DETAILS);
    this.seed = o.seed; this.far = o.detail === "far"; this.count = 0;
    const r = rng(o.seed * 7919 + 11);
    this.accent = o.accent ?? pick(r, ACCENTS); this.foil = o.foil ?? pick(r, FOILS);
    if (o.foil !== null) choice("foil", o.foil, FOILS);
    this.materials = makeMaterials({accent: this.accent, foil: this.foil, wear: o.wear});
    this.r = rng(o.seed * 104729 + 3);
  }
  bins() { return new Bins(this); }
  sides(n) { return this.far ? Math.max(6, Math.round(n / 2.5)) : n; }

  /** A hull section along +y. `shape`: cylinder | taper | cone (to `radius2` at the fore end) | nose (a rounded
   * end) | sphere | box (`size`: [width, depth]) | prism (`sides` flat faces). `radius`, `length`; `skin`, `caps`
   * (surfaces); `frames` (ring frames at the ends and `bands` between); `windows`: {count, rows, lit, size, from,
   * to}; `rails` (handrails), `greebles` (0..1: small boxes and conduits), `stripe` (an accent band).
   * Points: fore, aft, port, starboard, zenith, nadir, and {angle, along, out} anywhere on its side. */
  hull(o = {}) {
    known("hull options", o, ["shape", "radius", "radius2", "length", "size", "sides", "skin", "caps", "frames", "bands", "windows", "rails", "greebles", "stripe"]);
    const shape = choice("hull shape", o.shape ?? "cylinder", HULL_SHAPES), b = this.bins(), far = this.far;
    const r1 = o.radius ?? 1, L = shape === "sphere" ? 2 * r1 : (o.length ?? 3), skin = o.skin ?? "paint", caps = o.caps ?? "aluminium";
    const r2 = shape === "taper" || shape === "cone" ? (o.radius2 ?? r1 * (shape === "cone" ? 0.25 : 0.6)) : shape === "nose" ? (o.radius2 ?? 0) : r1;
    const sides = shape === "prism" ? (o.sides ?? 8) : this.sides(48), step = 360 / sides;
    const [bw, bd] = o.size ?? [2 * r1, 2 * r1];
    let radiusAt = (a) => mix(r1, r2, a);
    if (shape === "nose") radiusAt = (a) => Math.max(r2, r1 * Math.sqrt(Math.max(0, 1 - a * a)));
    if (shape === "sphere") radiusAt = (a) => r1 * Math.sin(Math.PI * clamp(a, 0.02, 0.98));
    const apothem = shape === "prism" ? Math.cos(Math.PI / sides) : 1;
    const surface = (angle, along, out = 0, across = 0) => {
      const y = (along - 0.5) * L;
      if (shape === "box") {
        const k = ((Math.round(angle / 90) % 4) + 4) % 4, n = [X, Z, X.clone().negate(), Z.clone().negate()][k].clone(), half = k % 2 === 0 ? bw / 2 : bd / 2, side = V3().crossVectors(Y, n);
        return point(n.clone().multiplyScalar(half + out).addScaledVector(Y, y).addScaledVector(side, across * (k % 2 === 0 ? bd / 2 : bw / 2)), n, Y);
      }
      const face = shape === "prism" ? Math.round(angle / step) * step : angle, n = V3(Math.cos(face * RAD), 0, Math.sin(face * RAD));
      const rr = radiusAt(along) * apothem / (shape === "prism" ? Math.cos((angle - face) * RAD) : 1) + out;
      return point(V3(Math.cos(angle * RAD) * rr, y, Math.sin(angle * RAD) * rr), n, Y);
    };
    const rmax = Math.max(r1, r2);
    if (shape === "box") b.box(skin, bw, L, bd);
    else if (shape === "sphere") b.add(skin, new THREE.SphereGeometry(r1, this.sides(48), this.sides(28)), {uv: [TAU * r1, Math.PI * r1]});
    else if (shape === "nose") {
      const n = far ? 6 : 14, profile = Array.from({length: n + 1}, (_, i) => [radiusAt(i / n), (i / n - 0.5) * L]);
      b.add(skin, lathe(profile, sides), {uv: [TAU * r1, profileLength(profile)]});
      b.add(caps, new THREE.CircleGeometry(r1, sides).rotateX(Math.PI / 2).translate(0, -L / 2, 0));
      if (r2 > 0.01) b.add(caps, new THREE.CircleGeometry(r2, sides).rotateX(-Math.PI / 2).translate(0, L / 2, 0));
    } else {
      let g = new THREE.CylinderGeometry(r2, r1, L, sides, 1, true);
      if (shape === "prism") g = flat(g).rotateY(((((90 - step / 2) % step) + step) % step) * RAD);
      b.add(skin, g, {uv: shape === "prism" ? "box" : [TAU * rmax, L]});
      const turn = shape === "prism" ? ((((90 - step / 2) % step) + step) % step) * RAD : 0;
      b.add(caps, new THREE.CircleGeometry(r1, sides).rotateX(Math.PI / 2).rotateY(turn).translate(0, -L / 2, 0));
      b.add(caps, new THREE.CircleGeometry(r2, sides).rotateX(-Math.PI / 2).rotateY(turn).translate(0, L / 2, 0));
    }
    const round = shape !== "box" && shape !== "sphere";
    if (round && (o.frames ?? true)) {
      const bands = o.bands ?? 0, list = [0, 1, ...Array.from({length: bands}, (_, i) => (i + 1) / (bands + 1))];
      for (const a of list) {
        const r = radiusAt(a), h = Math.min(0.12, 0.05 * rmax + 0.01), e = Math.min(0.05, 0.022 * rmax + 0.006), y = clamp((a - 0.5) * L, -L / 2 + h / 2, L / 2 - h / 2);
        if (r < 0.03) continue;
        let g = lathe([[r, -h / 2], [r + e, -h / 2 + e * 0.5], [r + e, h / 2 - e * 0.5], [r, h / 2]], sides);
        if (shape === "prism") g = flat(g).rotateY(((((90 - step / 2) % step) + step) % step) * RAD);
        b.add(shape === "prism" ? "aluminium" : (a > 0 && a < 1 ? skin : "aluminium"), g.translate(0, y, 0), {uv: shape === "prism" ? "box" : [TAU * r, 4 * h]});
      }
    }
    if (o.stripe && round && shape !== "prism") { const a = typeof o.stripe === "number" ? o.stripe : 0.82, h = Math.min(0.5, L * 0.08); b.add("accent", new THREE.CylinderGeometry(radiusAt(a + h / L / 2) + 0.006, radiusAt(a - h / L / 2) + 0.006, h, sides, 1, true).translate(0, (a - 0.5) * L, 0), {uv: [TAU * rmax, h]}); }
    if (o.windows) {
      known("windows", o.windows, ["count", "rows", "lit", "size", "from", "to", "angle"]);
      const w = o.windows, rows = w.rows ?? 1, count = w.count ?? 6, [ww, wh] = w.size ?? [0.34, 0.46], lit = w.lit ?? this.options.lit;
      for (let j = 0; j < rows; j++) for (let i = 0; i < count; i++) {
        const along = rows === 1 ? (w.from ?? 0.5) : mix(w.from ?? 0.25, w.to ?? 0.75, j / (rows - 1)), at = surface((w.angle ?? 0) + (i + (j % 2) * 0.5) * 360 / count, along, 0);
        const m = stand(at.p, at.n, at.u), on = hash2(i, j, this.seed * 13 + this.count) < lit;
        b.box("aluminium", wh + 0.1, 0.05, ww + 0.1, m); b.box(on ? "window" : "glass", wh, 0.065, ww, m, on ? {tint: [0.75 + 0.25 * hash2(i, j, 5), 0.8 + 0.2 * hash2(i, j, 6), 0.7 + 0.3 * hash2(i, j, 7)]} : {});
      }
    }
    if (o.rails && !far) for (let i = 0; i < o.rails; i++) {
      const a = (i + 0.5) * 360 / o.rails + 17, a0 = 0.12 + 0.5 * hash2(i, 1, this.seed), a1 = Math.min(0.92, a0 + Math.min(0.9, 0.8 / L) + 0.25 * hash2(i, 2, this.seed));
      const p0 = surface(a, a0, 0.075).p, p1 = surface(a, a1, 0.075).p;
      b.rod("steel", p0, p1, 0.014, 5); b.rod("steel", surface(a, a0, 0).p, p0, 0.012, 5); b.rod("steel", surface(a, a1, 0).p, p1, 0.012, 5);
      b.rod("steel", surface(a, (a0 + a1) / 2, 0).p, surface(a, (a0 + a1) / 2, 0.075).p, 0.012, 5);
    }
    if (o.greebles && !far && shape !== "sphere") {
      const r = this.r, n = Math.round(o.greebles * (4 + L * rmax * 2.2));
      for (let i = 0; i < n; i++) {
        const t = range(r, 0.05, 0.16), at = surface(r() * 360, range(r, 0.1, 0.9), t / 2 - 0.004), s = pick(r, ["aluminium", "aluminium", "dark", "foil-silver", "paint"]);
        b.box(s, range(r, 0.14, 0.42) * Math.min(1, rmax * 0.8), t * Math.min(1, rmax), range(r, 0.12, 0.34) * Math.min(1, rmax * 0.8), stand(at.p, at.n, at.u));
      }
      for (let i = 0; i < Math.ceil(o.greebles * 3); i++) {
        const a = r() * 360, a0 = range(r, 0.04, 0.3), a1 = range(r, 0.7, 0.96), rr = range(r, 0.014, 0.03), s = pick(r, ["dark", "steel", "aluminium"]);
        const pts = Array.from({length: 5}, (_, q) => surface(a, mix(a0, a1, q / 4), rr * 1.5));
        for (let q = 0; q < 4; q++) b.rod(s, pts[q].p, pts[q + 1].p, rr, 6);
        for (let q = 0; q < 5; q++) b.box("aluminium", rr * 1.3, rr * 2.8, rr * 3.4, stand(surface(a, mix(a0, a1, q / 4), rr * 1.2).p, pts[q].n, pts[q].u));
      }
    }
    const g = b.group(`hull (${shape})`);
    g.userData.points = {fore: point(V3(0, L / 2, 0), Y, Z), aft: point(V3(0, -L / 2, 0), Y.clone().negate(), Z), starboard: surface(0, 0.5), zenith: surface(90, 0.5), port: surface(180, 0.5), nadir: surface(270, 0.5)};
    g.userData.surface = surface; g.userData.size = {radius: rmax, length: L};
    const gloss = skin.startsWith("foil") ? 0.45 : skin === "cells" ? 1 : 0.12;                       // flat faces mirror the sun for a moment as the craft turns
    if (shape === "box") g.userData.facets = [0, 90, 180, 270].map((a) => ({normal: surface(a, 0.5).n, area: L * (a % 180 ? bw : bd), gloss}));
    if (shape === "prism") g.userData.facets = Array.from({length: sides}, (_, i) => ({normal: surface(i * step, 0.5).n, area: L * 2 * r1 * Math.sin(Math.PI / sides), gloss}));
    return g;
  }

  /** A tank: `shape` sphere | capsule, `radius`, `length` (a capsule's whole length), `skin`, `straps`.
   * Points: mount (its side), top, bottom. */
  tank(o = {}) {
    known("tank options", o, ["shape", "radius", "length", "skin", "straps"]);
    const shape = choice("tank shape", o.shape ?? "sphere", ["sphere", "capsule"]), r = o.radius ?? 0.6, L = shape === "sphere" ? 2 * r : Math.max(o.length ?? 3 * r, 2 * r), b = this.bins(), n = this.far ? 5 : 10, sides = this.sides(36);
    const profile = [];
    for (let i = 0; i <= n; i++) { const a = (i / n) * Math.PI / 2; profile.push([r * Math.sin(a), -L / 2 + r - r * Math.cos(a)]); }
    for (let i = n; i >= 0; i--) { const a = (i / n) * Math.PI / 2; profile.push([r * Math.sin(a), L / 2 - r + r * Math.cos(a)]); }
    const skin = o.skin ?? "foil";
    b.add(skin, lathe(profile, sides), {uv: [TAU * r, profileLength(profile)]});
    if (o.straps ?? true) for (const y of shape === "sphere" ? [0] : [-(L / 2 - r) * 0.8, (L / 2 - r) * 0.8]) b.add("steel", lathe([[r + 0.002, y - 0.035 * r - 0.01], [r + 0.012, y - 0.02 * r], [r + 0.012, y + 0.02 * r], [r + 0.002, y + 0.035 * r + 0.01]], sides), {uv: [TAU * r, 0.2]});
    for (const s of [1, -1]) b.add("aluminium", new THREE.CylinderGeometry(r * 0.16, r * 0.2, r * 0.12, this.sides(16)).translate(0, s * (L / 2 + r * 0.03), 0), {uv: [r, r * 0.12]});
    const g = b.group(`tank (${shape})`);
    g.userData.points = {mount: point(V3(-r, 0, 0), X.clone().negate(), Y), top: point(V3(0, L / 2 + r * 0.09, 0), Y, Z), bottom: point(V3(0, -L / 2 - r * 0.09, 0), Y.clone().negate(), Z)};
    g.userData.size = {radius: r, length: L};
    return g;
  }

  /** Tanks round an axis, held by struts: `count`, `radius`, `length`, `ring` (their distance from the axis),
   * `shape`, `skin`. Points: fore, aft (on the axis), and {angle, along} round it. */
  tankCluster(o = {}) {
    known("tankCluster options", o, ["count", "radius", "length", "ring", "shape", "skin", "spine"]);
    const count = o.count ?? 4, r = o.radius ?? 0.6, shape = o.shape ?? "capsule", L = shape === "sphere" ? 2 * r : (o.length ?? 4 * r), ring = o.ring ?? r / Math.sin(Math.PI / Math.max(count, 3)) * 1.08 + 0.05, b = this.bins();
    const spine = o.spine ?? Math.min(0.25, r * 0.35);
    b.add("aluminium", new THREE.CylinderGeometry(spine, spine, L * 1.04, this.sides(16), 1, false), {uv: [TAU * spine, L]});
    const g = b.group("tank cluster"), s = this.bins();
    for (let i = 0; i < count; i++) {
      const a = i * TAU / count, d = V3(Math.cos(a), 0, Math.sin(a)), tank = this.tank({shape, radius: r, length: L, skin: o.skin ?? (i % 2 ? "foil" : "foil")});
      tank.position.copy(d).multiplyScalar(ring); tank.rotation.y = -a; g.add(tank);
      for (const y of shape === "sphere" ? [0] : [-(L / 2 - r) * 0.8, (L / 2 - r) * 0.8]) { s.rod("steel", V3(0, y, 0).addScaledVector(d, spine * 0.8), V3(0, y, 0).addScaledVector(d, ring - r * 0.98), 0.03 + r * 0.02, 6); s.rod("steel", V3(0, y + r * 0.7, 0).addScaledVector(d, spine * 0.8), V3(0, y, 0).addScaledVector(d, ring - r * 0.98), 0.02 + r * 0.012, 6); }
    }
    g.add(...s.group("struts").children);
    g.userData.points = {fore: point(V3(0, L * 0.52, 0), Y, Z), aft: point(V3(0, -L * 0.52, 0), Y.clone().negate(), Z)};
    g.userData.surface = (angle, along, out = 0) => { const n = V3(Math.cos(angle * RAD), 0, Math.sin(angle * RAD)); return point(n.clone().multiplyScalar(ring + r + out).setY((along - 0.5) * L), n, Y); };
    g.userData.size = {radius: ring + r, length: L};
    return g;
  }

  /** A lattice truss along +y: `length`, `width`, `section` (4 or 3 longerons), `skin`. Longerons, a frame every
   * bay, a diagonal on every face, a node at every joint. Points: fore, aft, {angle, along, out}. */
  truss(o = {}) {
    known("truss options", o, ["length", "width", "section", "skin", "bays"]);
    const L = o.length ?? 10, w = o.width ?? 1, n = o.section ?? 4, skin = o.skin ?? "aluminium", bays = o.bays ?? Math.max(1, Math.round(L / w)), b = this.bins();
    const R = w / (2 * Math.sin(Math.PI / n)), rod = Math.max(0.012, w * 0.028), corner = (i, y) => V3(R * Math.cos((i + 0.5) * TAU / n), y, R * Math.sin((i + 0.5) * TAU / n));
    for (let i = 0; i < n; i++) b.rod(skin, corner(i, -L / 2), corner(i, L / 2), rod * 1.25, 8);
    for (let k = 0; k <= bays; k++) {
      const y = -L / 2 + k * L / bays;
      for (let i = 0; i < n; i++) {
        b.rod(skin, corner(i, y), corner(i + 1, y), rod, 6);
        if (k < bays) { const y1 = y + L / bays, up = (k + i) % 2 === 0; b.rod(skin, corner(i, up ? y : y1), corner(i + 1, up ? y1 : y), rod * 0.8, 6); }
        if (!this.far) b.add("steel", new THREE.SphereGeometry(rod * 2.1, 8, 6).translate(...corner(i, y).toArray()), {uv: "keep"});
      }
      if (n === 4 && k % 2 === 0 && !this.far) b.rod(skin, corner(0, y), corner(2, y), rod * 0.7, 5);
    }
    const g = b.group("truss"), apothem = R * Math.cos(Math.PI / n), step = 360 / n;
    g.userData.points = {fore: point(V3(0, L / 2, 0), Y, Z), aft: point(V3(0, -L / 2, 0), Y.clone().negate(), Z)};
    g.userData.surface = (angle, along, out = 0) => { const f = Math.round(angle / step) * step, nn = V3(Math.cos(f * RAD), 0, Math.sin(f * RAD)); return point(nn.clone().multiplyScalar(apothem + out).setY((along - 0.5) * L), nn, Y); };
    g.userData.size = {radius: R, length: L}; g.userData.sparse = true;
    return g;
  }

  /** A solar wing along +x from its root: `panels`, `size` ([along the wing, across] metres per panel), `yoke`
   * (metres of yoke before the first panel), `deploy` (1 flat .. 0 folded), `deployable` (true: the panels stay
   * separate so craft.update(t, {deploy}) can fold them), `track` (true: the wing turns about its length to face
   * the sun). Cells on +z, a ribbed back, a frame, hinges. Points: mount, tip. */
  solarWing(o = {}) {
    known("solarWing options", o, ["panels", "size", "yoke", "deploy", "deployable", "track", "gap"]);
    const panels = o.panels ?? 3, snap = (v) => Math.max(0.3, Math.round(v / 0.15) * 0.15), w = snap((o.size ?? [1.8, 2.4])[0]), h = snap((o.size ?? [1.8, 2.4])[1]);
    const yoke = o.yoke ?? Math.max(0.5, h * 0.45), gap = o.gap ?? 0.06, T = Math.max(0.02, Math.min(0.05, h * 0.012)), deploy = clamp(o.deploy ?? 1), jointed = !!o.deployable || deploy < 1, far = this.far;
    const root = this.bins(), jr = Math.max(0.05, h * 0.035);
    root.add("aluminium", new THREE.CylinderGeometry(jr * 1.5, jr * 1.8, jr * 1.6, this.sides(20)).rotateZ(-Math.PI / 2).translate(jr * 0.8, 0, 0), {uv: [jr * 9, jr * 1.6]});
    const g = root.group("solar wing"), arm = new THREE.Group(); arm.name = "wing arm";
    const yb = this.bins();
    yb.add("dark", new THREE.CylinderGeometry(jr, jr, jr * 1.4, this.sides(16)).rotateZ(-Math.PI / 2).translate(jr * 2.2, 0, 0), {uv: [jr * 6, jr]});
    for (const s of [1, -1]) yb.rod("aluminium", V3(jr * 2.4, 0, 0), V3(yoke, s * h * 0.32, 0), jr * 0.42, 8);
    yb.rod("aluminium", V3(yoke - jr, -h * 0.34, 0), V3(yoke - jr, h * 0.34, 0), jr * 0.4, 8);
    arm.add(...yb.group("yoke").children);
    const panel = (k) => {
      const b = this.bins(), mid = new THREE.Matrix4().makeTranslation(w / 2, 0, 0);
      b.add("cells", new THREE.PlaneGeometry(w - 0.04, h - 0.04).translate((w - 0.04) / 2, (h - 0.04) / 2, 0), {at: new THREE.Matrix4().makeTranslation(0.02, -h / 2 + 0.02, T / 2 + 0.001)});
      b.box("back", w, h, T, mid);
      for (const s of [1, -1]) { b.box("aluminium", w, 0.025, T * 1.5, new THREE.Matrix4().makeTranslation(w / 2, s * (h / 2 - 0.0125), 0)); b.box("aluminium", 0.025, h, T * 1.5, new THREE.Matrix4().makeTranslation(w / 2 + s * (w / 2 - 0.0125), 0, 0)); }
      if (!far) {
        for (const y of [-h * 0.3, 0, h * 0.3]) b.box("back", w - 0.06, 0.03, 0.03, new THREE.Matrix4().makeTranslation(w / 2, y, -T / 2 - 0.015));
        for (const x of [w * 0.25, w * 0.75]) b.box("back", 0.03, h - 0.06, 0.02, new THREE.Matrix4().makeTranslation(x, 0, -T / 2 - 0.01));
        for (const y of [-h * 0.3, h * 0.3]) b.add("steel", new THREE.CylinderGeometry(gap * 0.42, gap * 0.42, 0.14, 8).translate(-gap / 2, y, 0), {uv: [0.2, 0.14]});
      }
      const pg = b.group(`panel ${k}`); delete pg.userData.points;
      return pg;
    };
    const fold = (d) => (1 - d) * 88 * RAD, hinges = [];
    let parent = arm, x = yoke;
    for (let k = 0; k < panels; k++) {
      const pg = panel(k);
      if (jointed) { const hinge = new THREE.Group(); hinge.position.set(x, 0, 0); hinge.rotation.y = (k === 0 ? 1 : k % 2 ? -2 : 2) * fold(deploy); hinge.add(pg); if (o.deployable) hinge.userData.moving = true; parent.add(hinge); parent = hinge; hinges.push(hinge); x = w + gap; }
      else { pg.position.set(x, 0, 0); arm.add(pg); x += w + gap; }
    }
    g.add(arm);
    const span = yoke + panels * (w + gap);
    if (o.track ?? true) { arm.userData.moving = true; arm.userData.track = true; }
    if (o.deployable) g.userData.deploy = (d) => hinges.forEach((hh, k) => { hh.rotation.y = (k === 0 ? 1 : k % 2 ? -2 : 2) * fold(clamp(d)); });
    arm.userData.facet = {normal: Z.clone(), area: panels * w * h, gloss: 1};
    g.userData.points = {mount: point(V3(0, 0, 0), X.clone().negate(), Y), tip: point(V3(span, 0, 0), X, Y)};
    g.userData.size = {radius: h / 2, length: span};
    return g;
  }

  /** A radiator along +x: `panels`, `size` ([along, across] per panel), `yoke`. White panels with coolant pipes on
   * both faces and a header at the root. Points: mount, tip. */
  radiator(o = {}) {
    known("radiator options", o, ["panels", "size", "yoke", "skin"]);
    const panels = o.panels ?? 2, [w, h] = o.size ?? [2, 1.4], yoke = o.yoke ?? 0.3, T = 0.035, b = this.bins(), skin = o.skin ?? "radiator", gap = 0.05;
    b.rod("aluminium", V3(0, 0, 0), V3(yoke, 0, 0), 0.05 + h * 0.01, 8);
    b.rod("steel", V3(yoke - 0.03, -h / 2, 0), V3(yoke - 0.03, h / 2, 0), 0.03 + h * 0.006, 8);
    for (let k = 0; k < panels; k++) {
      const x0 = yoke + k * (w + gap);
      b.box(skin, w, h, T, new THREE.Matrix4().makeTranslation(x0 + w / 2, 0, 0));
      for (const s of [1, -1]) b.box("aluminium", w, 0.03, T * 1.4, new THREE.Matrix4().makeTranslation(x0 + w / 2, s * (h / 2 - 0.015), 0));
      const n = this.far ? 0 : Math.max(3, Math.round(h / 0.22));
      for (let i = 0; i < n; i++) for (const s of [1, -1]) { const y = (i + 0.5) / n * h - h / 2; b.rod("steel", V3(x0 + 0.03, y, s * (T / 2 + 0.006)), V3(x0 + w - 0.03, y, s * (T / 2 + 0.006)), 0.011, 5); }
      if (k > 0 && !this.far) for (const y of [-h * 0.3, h * 0.3]) b.add("steel", new THREE.CylinderGeometry(0.025, 0.025, 0.12, 8).translate(x0 - gap / 2, y, 0), {uv: [0.15, 0.12]});
    }
    const g = b.group("radiator"), span = yoke + panels * (w + gap);
    g.userData.points = {mount: point(V3(0, 0, 0), X.clone().negate(), Y), tip: point(V3(span, 0, 0), X, Y)};
    g.userData.size = {radius: h / 2, length: span};
    return g;
  }

  /** A high-gain dish looking along +y: `diameter`; `focal` (focal length over diameter, 0.4); `feed`: "tripod" |
   * "none"; `gimbal` (true: craft.update(t, {target}) points it; false: fixed); `skin`. A true parabola with a
   * rim, ribs and a ring on its back, a feed horn at the focus on three struts. Points: mount, feed. */
  dish(o = {}) {
    known("dish options", o, ["diameter", "focal", "feed", "gimbal", "skin", "neck"]);
    const D = o.diameter ?? 3, R = D / 2, f = (o.focal ?? 0.4) * D, n = this.far ? 6 : 16, sides = this.sides(64), t = Math.max(0.012, D * 0.006), neck = o.neck ?? D * 0.14, skin = o.skin ?? "dish";
    const z = (r) => r * r / (4 * f), b = this.bins(), base = this.bins();
    const front = Array.from({length: n + 1}, (_, i) => [R * (1 - i / n), z(R * (1 - i / n)) + t]), back = Array.from({length: n + 1}, (_, i) => [R * i / n, z(R * i / n)]);
    b.add(skin, lathe(front, sides), {uv: [TAU * R, profileLength(front)]});
    b.add("aluminium", lathe(back, sides), {uv: [TAU * R, profileLength(back)]});
    b.add("aluminium", new THREE.TorusGeometry(R, t * 1.3, 6, sides).rotateX(Math.PI / 2).translate(0, z(R) + t / 2, 0), {uv: [TAU * R, 0.2]});
    const ribs = this.far ? 6 : 12;
    for (let i = 0; i < ribs; i++) { const a = i * TAU / ribs, d = V3(Math.cos(a), 0, Math.sin(a)), at = (r) => d.clone().multiplyScalar(r).setY(z(r) - D * 0.012); for (const [r0, r1] of [[0.12 * R, 0.45 * R], [0.45 * R, 0.75 * R], [0.75 * R, 0.985 * R]]) b.rod("aluminium", at(r0), at(r1), D * 0.008, 4); }
    b.add("aluminium", new THREE.TorusGeometry(0.55 * R, D * 0.011, 5, sides).rotateX(Math.PI / 2).translate(0, z(0.55 * R) - D * 0.014, 0), {uv: [TAU * R, 0.2]});
    b.add("dark", new THREE.CylinderGeometry(0.14 * R, 0.11 * R, D * 0.07, this.sides(20)).translate(0, -D * 0.035, 0), {uv: [R, D * 0.07]});
    const feedY = f * 0.94;
    if ((o.feed ?? "tripod") === "tripod") {
      for (let i = 0; i < 3; i++) { const a = i * TAU / 3 + 0.5, d = V3(Math.cos(a), 0, Math.sin(a)); b.rod("aluminium", d.clone().multiplyScalar(0.8 * R).setY(z(0.8 * R) + t), d.clone().multiplyScalar(0.07 * R).setY(feedY), Math.max(0.01, D * 0.006), 6); }
      b.add("aluminium", new THREE.CylinderGeometry(0.075 * R, 0.035 * R, D * 0.07, this.sides(20)).translate(0, feedY - D * 0.01, 0), {uv: [R * 0.4, D * 0.07]});
      b.add("dark", new THREE.CylinderGeometry(0.1 * R, 0.1 * R, D * 0.012, this.sides(20)).translate(0, feedY + D * 0.03, 0), {uv: [R * 0.4, D * 0.02]});
      b.rod("steel", V3(0, feedY + D * 0.03, 0), V3(0, feedY + D * 0.16, 0), Math.max(0.006, D * 0.004), 5);
    }
    base.add("aluminium", new THREE.CylinderGeometry(0.07 * R, 0.1 * R, neck * 0.8, this.sides(16)).translate(0, neck * 0.4, 0), {uv: [R * 0.5, neck]});
    base.add("dark", new THREE.SphereGeometry(0.1 * R, this.sides(16), 8).translate(0, neck * 0.82, 0), {uv: [R * 0.6, R * 0.3]});
    const g = base.group("dish"), az = new THREE.Group(), el = new THREE.Group(), bowl = b.group("reflector");
    az.name = "dish azimuth"; el.name = "dish elevation"; az.position.y = neck * 0.82; bowl.position.y = D * 0.07 + 0.1 * R;
    delete bowl.userData.points; el.add(bowl); az.add(el); g.add(az);
    if (o.gimbal ?? true) { az.userData.moving = true; el.userData.moving = true; g.userData.aim = {az, el}; }
    az.userData.facet = {normal: Y.clone(), area: Math.PI * R * R * 0.3, gloss: 0.15};
    g.userData.points = {mount: point(V3(0, 0, 0), Y.clone().negate(), Z), feed: point(V3(0, az.position.y + bowl.position.y + feedY + D * 0.16, 0), Y, Z)};
    g.userData.size = {radius: R, length: neck + f};
    return g;
  }

  /** An antenna standing along +y: `kind` whip | helix | horn | omni | patch; `length`. Point: mount. */
  antenna(o = {}) {
    known("antenna options", o, ["kind", "length"]);
    const kind = choice("antenna kind", o.kind ?? "whip", ["whip", "helix", "horn", "omni", "patch"]), L = o.length ?? {whip: 1.6, helix: 0.9, horn: 0.4, omni: 0.5, patch: 0.5}[kind], b = this.bins();
    b.add("aluminium", new THREE.CylinderGeometry(L * 0.05 + 0.02, L * 0.06 + 0.03, 0.06, this.sides(12)).translate(0, 0.03, 0), {uv: [0.3, 0.06]});
    if (kind === "whip") { b.rod("steel", V3(0, 0.05, 0), V3(0, L, 0), 0.008 + L * 0.002, 5); b.add("dark", new THREE.SphereGeometry(0.02 + L * 0.004, 8, 6).translate(0, L, 0), {uv: "keep"}); }
    if (kind === "helix") { const turns = 7, pts = Array.from({length: turns * 10 + 1}, (_, i) => V3(L * 0.13 * Math.cos(i * TAU / 10), 0.1 + (L - 0.1) * i / (turns * 10), L * 0.13 * Math.sin(i * TAU / 10))); b.pipe("steel", pts, L * 0.012, 5); b.rod("dark", V3(0, 0.05, 0), V3(0, L, 0), L * 0.02, 6); b.add("aluminium", new THREE.CylinderGeometry(L * 0.22, L * 0.22, 0.02, this.sides(20)).translate(0, 0.07, 0), {uv: [L, 0.02]}); }
    if (kind === "horn") { b.add("aluminium", new THREE.CylinderGeometry(L * 0.38, L * 0.12, L, this.sides(20), 1, true).translate(0, L / 2 + 0.05, 0), {uv: [L * 2, L]}); b.add("dark", new THREE.CircleGeometry(L * 0.37, this.sides(20)).rotateX(-Math.PI / 2).translate(0, L * 0.9, 0)); }
    if (kind === "omni") { b.rod("aluminium", V3(0, 0.05, 0), V3(0, L * 0.7, 0), L * 0.04, 6); b.add("dish", new THREE.CylinderGeometry(L * 0.08, L * 0.3, L * 0.3, this.sides(20)).translate(0, L * 0.85, 0), {uv: [L, L * 0.3]}); }
    if (kind === "patch") { b.rod("aluminium", V3(0, 0.05, 0), V3(0, L * 0.3, 0), 0.03, 6); b.box("dish", L, 0.03, L * 0.7, new THREE.Matrix4().makeTranslation(0, L * 0.3, 0)); b.box("dark", L * 0.9, 0.012, L * 0.6, new THREE.Matrix4().makeTranslation(0, L * 0.3 + 0.02, 0)); }
    const g = b.group(`antenna (${kind})`);
    g.userData.points = {mount: point(V3(0, 0, 0), Y.clone().negate(), Z), tip: point(V3(0, L, 0), Y, Z)}; g.userData.sparse = true; g.userData.size = {radius: 0.1, length: L};
    return g;
  }

  /** A boom along +y: `length`, `radius`, `skin`, `lattice` (true: a three-sided truss). Collars along a tube.
   * Points: mount, tip, {angle, along, out}. */
  boom(o = {}) {
    known("boom options", o, ["length", "radius", "skin", "lattice"]);
    const L = o.length ?? 4, r = o.radius ?? Math.max(0.02, L * 0.008);
    if (o.lattice) { const tr = this.truss({length: L, width: Math.max(0.16, r * 9), section: 3, skin: o.skin ?? "aluminium"}); tr.userData.points.mount = tr.userData.points.aft; tr.userData.points.tip = tr.userData.points.fore; return tr; }
    const b = this.bins(), skin = o.skin ?? "aluminium", n = Math.max(2, Math.round(L / 1.2));
    b.add(skin, new THREE.CylinderGeometry(r, r, L, this.sides(12), 1, true).translate(0, L / 2, 0), {uv: [TAU * r, L]});
    for (let i = 0; i <= n; i++) b.add("steel", new THREE.CylinderGeometry(r * 1.5, r * 1.5, r * 2.2, this.sides(12)).translate(0, clamp(i * L / n, r * 1.1, L - r * 1.1), 0), {uv: [r * 6, r * 2]});
    const g = b.group("boom");
    g.userData.points = {mount: point(V3(0, 0, 0), Y.clone().negate(), Z), tip: point(V3(0, L, 0), Y, Z)};
    g.userData.surface = (angle, along, out = 0) => { const nn = V3(Math.cos(angle * RAD), 0, Math.sin(angle * RAD)); return point(nn.clone().multiplyScalar(r + out).setY(along * L), nn, Y); };
    g.userData.sparse = true; g.userData.size = {radius: r, length: L};
    return g;
  }

  /** An instrument looking along +y: `kind` camera | spectrometer | magnetometer | tracker | platform (three on
   * a plate); `size`. Point: mount. */
  instrument(o = {}) {
    known("instrument options", o, ["kind", "size"]);
    const kind = choice("instrument kind", o.kind ?? "camera", ["camera", "spectrometer", "magnetometer", "tracker", "platform"]), s = o.size ?? 0.4, b = this.bins(), T = (x, y, z) => new THREE.Matrix4().makeTranslation(x, y, z);
    const camera = (x, z, k) => {
      b.box("foil-black", 0.7 * k, 0.9 * k, 0.7 * k, T(x, 0.45 * k, z));
      b.add("dark", new THREE.CylinderGeometry(0.3 * k, 0.26 * k, 0.8 * k, this.sides(24), 1, true).translate(x, 1.25 * k, z), {uv: [k * 2, k]});
      b.add("aluminium", new THREE.TorusGeometry(0.3 * k, 0.03 * k, 6, this.sides(24)).rotateX(Math.PI / 2).translate(x, 1.65 * k, z), {uv: "keep"});
      b.add("glass", new THREE.SphereGeometry(0.4 * k, this.sides(20), 6, 0, TAU, 0, 0.7).translate(x, 1.1 * k, z), {uv: "keep"});
    };
    const spectro = (x, z, k) => {
      b.box("foil", 1.1 * k, 0.8 * k, 0.8 * k, T(x, 0.4 * k, z)); b.box("dark", 0.8 * k, 0.5 * k, 0.5 * k, T(x, 1.0 * k, z)); b.box("glass", 0.62 * k, 0.03 * k, 0.34 * k, T(x, 1.25 * k, z));
      b.box("radiator", 0.04 * k, 1.1 * k, 1.0 * k, T(x + 0.62 * k, 0.6 * k, z));
    };
    const tracker = (x, z, k) => { b.box("aluminium", 0.5 * k, 0.4 * k, 0.5 * k, T(x, 0.2 * k, z)); b.add("dark", new THREE.CylinderGeometry(0.3 * k, 0.17 * k, 0.7 * k, this.sides(20), 1, true).translate(x, 0.75 * k, z), {uv: [k * 2, k]}); b.add("glass", new THREE.CircleGeometry(0.17 * k, this.sides(16)).rotateX(-Math.PI / 2).translate(x, 0.45 * k, z)); };
    if (kind === "camera") camera(0, 0, s);
    if (kind === "spectrometer") spectro(0, 0, s);
    if (kind === "tracker") tracker(0, 0, s);
    if (kind === "magnetometer") { b.add("foil-silver", new THREE.CylinderGeometry(0.22 * s, 0.22 * s, 0.7 * s, this.sides(16)).translate(0, 0.35 * s, 0), {uv: [s, s]}); b.add("dark", new THREE.SphereGeometry(0.2 * s, 12, 8).translate(0, 0.85 * s, 0), {uv: "keep"}); }
    if (kind === "platform") { b.box("aluminium", 2.6 * s, 0.12 * s, 1.6 * s, T(0, 0.06 * s, 0)); camera(-0.8 * s, 0.2 * s, s * 0.8); spectro(0.3 * s, -0.2 * s, s * 0.75); tracker(1.0 * s, 0.4 * s, s * 0.7); b.box("foil", 0.9 * s, 0.5 * s, 0.5 * s, T(-0.6 * s, 0.37 * s, -0.5 * s)); }
    const g = b.group(`instrument (${kind})`);
    g.userData.points = {mount: point(V3(0, 0, 0), Y.clone().negate(), Z), top: point(V3(0, s * 1.7, 0), Y, Z)}; g.userData.size = {radius: s, length: s * 1.7};
    return g;
  }

  /** A radioisotope power unit: a dark finned cylinder along +y (`length`, `radius`, `fins`). Points: mount, tip. */
  powerUnit(o = {}) {
    known("powerUnit options", o, ["length", "radius", "fins"]);
    const L = o.length ?? 1.1, r = o.radius ?? 0.14, fins = o.fins ?? 8, b = this.bins();
    b.add("dark", new THREE.CylinderGeometry(r, r, L, this.sides(20)).translate(0, L / 2, 0), {uv: [TAU * r, L]});
    for (let i = 0; i < fins; i++) { const a = i * TAU / fins; b.box("back", r * 1.5, L * 0.86, 0.012, new THREE.Matrix4().makeRotationY(-a).multiply(new THREE.Matrix4().makeTranslation(r * 1.7, L / 2, 0))); }
    for (const y of [0.04, L - 0.04]) b.add("aluminium", new THREE.CylinderGeometry(r * 1.25, r * 1.25, 0.06, this.sides(20)).translate(0, y, 0), {uv: [TAU * r, 0.06]});
    const g = b.group("power unit");
    g.userData.points = {mount: point(V3(0, 0, 0), Y.clone().negate(), Z), tip: point(V3(0, L, 0), Y, Z)}; g.userData.size = {radius: r * 2.5, length: L};
    return g;
  }

  /** A docking port facing +y: `radius`. A collar, a ring, three guide petals, latches, a hatch with a small
   * window. Points: mount, dock. */
  dockingPort(o = {}) {
    known("dockingPort options", o, ["radius", "light"]);
    const r = o.radius ?? 0.7, h = r * 0.42, b = this.bins(), sides = this.sides(40);
    b.add("aluminium", lathe([[r * 1.12, 0], [r * 1.12, h * 0.5], [r, h * 0.62], [r, h], [r * 0.86, h], [r * 0.86, h * 0.45]], sides), {uv: [TAU * r, h * 2]});
    b.add("steel", new THREE.TorusGeometry(r * 0.93, r * 0.035, 6, sides).rotateX(Math.PI / 2).translate(0, h, 0), {uv: "keep"});
    b.add("paint", new THREE.CircleGeometry(r * 0.86, sides).rotateX(-Math.PI / 2).translate(0, h * 0.45, 0));
    b.add("glass", new THREE.CircleGeometry(r * 0.2, this.sides(20)).rotateX(-Math.PI / 2).translate(0, h * 0.46, 0));
    b.add("aluminium", new THREE.TorusGeometry(r * 0.22, r * 0.03, 6, this.sides(20)).rotateX(Math.PI / 2).translate(0, h * 0.46, 0), {uv: "keep"});
    for (let i = 0; i < 3; i++) { const a = i * TAU / 3, m = new THREE.Matrix4().makeRotationY(-a).multiply(new THREE.Matrix4().makeTranslation(r * 0.8, h * 1.22, 0)).multiply(new THREE.Matrix4().makeRotationZ(0.5)); b.box("aluminium", r * 0.05, h * 0.75, r * 0.5, m); }
    if (!this.far) for (let i = 0; i < 12; i++) { const a = (i + 0.5) * TAU / 12; b.box("dark", r * 0.1, h * 0.3, r * 0.08, new THREE.Matrix4().makeRotationY(-a).multiply(new THREE.Matrix4().makeTranslation(r * 1.14, h * 0.3, 0))); }
    const g = b.group("docking port");
    g.userData.points = {mount: point(V3(0, 0, 0), Y.clone().negate(), Z), dock: point(V3(0, h, 0), Y, Z)}; g.userData.size = {radius: r * 1.15, length: h};
    return g;
  }

  /** A cupola looking along +y: `radius`. Six trapezoid windows round a round one, in frames. Point: mount. */
  cupola(o = {}) {
    known("cupola options", o, ["radius", "lit"]);
    const r = o.radius ?? 1, h = r * 0.62, rt = r * 0.52, b = this.bins(), lit = o.lit ?? true, pane = lit ? "window" : "glass", shift = Math.PI / 6;
    b.add("aluminium", new THREE.CylinderGeometry(r, r * 1.04, r * 0.16, this.sides(36)).translate(0, r * 0.08, 0), {uv: [TAU * r, r * 0.16]});
    b.add("aluminium", flat(new THREE.CylinderGeometry(rt, r * 0.97, h, 6, 1, false)).rotateY(shift).translate(0, r * 0.16 + h / 2, 0));
    for (let i = 0; i < 6; i++) {
      const a0 = i * TAU / 6 + 0.1, a1 = (i + 1) * TAU / 6 - 0.1, e = 0.012 * r, y0 = r * 0.16 + h * 0.1, y1 = r * 0.16 + h * 0.9, ra = mix(r * 0.97, rt, 0.1), rb = mix(r * 0.97, rt, 0.9), cs = Math.cos(Math.PI / 6);
      const at = (rr, a, y) => { const mid = (a0 + a1) / 2, k = rr * cs / Math.cos(a - mid) + e; return [k * Math.sin(a), y, k * Math.cos(a)]; };
      const quad = new THREE.BufferGeometry(); quad.setAttribute("position", new THREE.Float32BufferAttribute([...at(ra, a0, y0), ...at(ra, a1, y0), ...at(rb, a1, y1), ...at(rb, a0, y1)], 3));
      quad.setIndex([0, 1, 2, 0, 2, 3]); quad.computeVertexNormals(); quad.setAttribute("uv", new THREE.Float32BufferAttribute([0, 0, 1, 0, 1, 1, 0, 1], 2));
      b.add(pane, quad, {uv: "keep", tint: lit ? [0.85, 0.9, 0.8] : null});
    }
    b.add(pane, new THREE.CircleGeometry(rt * 0.72, this.sides(24)).rotateX(-Math.PI / 2).translate(0, r * 0.16 + h + 0.012 * r, 0), {uv: "keep"});
    b.add("aluminium", new THREE.TorusGeometry(rt * 0.76, r * 0.035, 6, this.sides(24)).rotateX(Math.PI / 2).translate(0, r * 0.16 + h + 0.01 * r, 0), {uv: "keep"});
    const g = b.group("cupola");
    g.userData.points = {mount: point(V3(0, 0, 0), Y.clone().negate(), Z), top: point(V3(0, h + r * 0.17, 0), Y, Z)}; g.userData.size = {radius: r, length: h + r * 0.16};
    return g;
  }

  /** An airlock along +y: `radius`, `length`. A short section with a square outer hatch, rails and a docking
   * port at its end. Points: mount (aft), fore, dock. */
  airlock(o = {}) {
    known("airlock options", o, ["radius", "length"]);
    const r = o.radius ?? 1, L = o.length ?? 2.2, g = this.hull({radius: r, length: L, rails: 5, bands: 1, greebles: 0.4}), b = this.bins();
    const at = g.userData.surface(90, 0.5, 0.02), m = stand(at.p, at.n, at.u), s = Math.min(1.1, r * 1.1);
    b.box("accent", s + 0.14, 0.05, s + 0.14, m); b.box("paint", s, 0.07, s, m); b.box("glass", 0.22, 0.08, 0.22, m);
    for (const k of [1, -1]) b.box("steel", 0.06, 0.12, s * 0.5, stand(g.userData.surface(90, 0.5 + k * (s * 0.42) / L, 0.03).p, at.n, at.u));
    g.add(...b.group("hatch").children);
    const port = attach(g, "fore", this.dockingPort({radius: r * 0.62}));
    g.userData.points.mount = g.userData.points.aft; g.userData.points.dock = point(V3(0, L / 2 + r * 0.62 * 0.42, 0), Y, Z); g.userData.part = "airlock"; port.name = "port";
    return g;
  }

  /** An engine hanging from its mount, firing toward -y: `exit` (the bell's exit radius), `length`, `kind`
   * (a key of PLUMES: chemical | vacuum | air | ion), `plume` (false: none). A chamber, a bell of a true bell
   * curve with cooling channels and hoops, a manifold, feed pipes, pumps, two gimbal struts; an ion engine is a
   * short can with a glowing grid. Points: mount, exit. */
  engine(o = {}) {
    known("engine options", o, ["exit", "length", "kind", "plume"]);
    const kind = choice("engine kind", o.kind ?? "chemical", ["chemical", "vacuum", "air", "ion"]), re = o.exit ?? 0.5, b = this.bins(), sides = this.sides(40), far = this.far;
    const glow = new THREE.MeshBasicMaterial({vertexColors: true, toneMapped: false, side: THREE.DoubleSide, color: 0x050505}); glow.name = "glow";
    const inner = [];
    let L;
    if (kind === "ion") {
      L = o.length ?? re * 1.3;
      b.add("aluminium", lathe([[re * 0.5, 0], [re * 1.02, -L * 0.25], [re * 1.02, -L * 0.92], [re * 0.95, -L]].reverse(), sides), {uv: [TAU * re, L]});
      b.add("dark", new THREE.TorusGeometry(re * 0.98, re * 0.05, 6, sides).rotateX(Math.PI / 2).translate(0, -L, 0), {uv: "keep"});
      inner.push(new THREE.SphereGeometry(re * 1.6, sides, 6, 0, TAU, Math.PI - 0.62, 0.62).translate(0, -L + re * 1.6 - re * 0.3, 0));
      b.rod("steel", V3(re * 1.08, -L * 0.5, 0), V3(re * 1.08, -L * 1.02, 0), re * 0.05, 6); b.box("dark", re * 0.2, re * 0.2, re * 0.2, new THREE.Matrix4().makeTranslation(re * 1.08, -L * 0.45, 0));
      for (let i = 0; i < 3; i++) { const a = i * TAU / 3 + 0.6; b.rod("steel", V3(re * 0.3 * Math.cos(a), 0, re * 0.3 * Math.sin(a)), V3(re * 0.9 * Math.cos(a), -L * 0.25, re * 0.9 * Math.sin(a)), re * 0.04, 5); }
    } else {
      L = o.length ?? re * (kind === "vacuum" ? 3.4 : 2.8);
      const rt = re * (kind === "vacuum" ? 0.16 : 0.22), rc = rt * 1.9, yc = -L * 0.07, yt = -L * 0.3, n = far ? 8 : 20, wall = Math.max(0.006, re * 0.02);
      const bell = Array.from({length: n + 1}, (_, i) => { const s = i / n; return [rt + (re - rt) * Math.pow(Math.sin(s * Math.PI / 2), 0.72), yt - (L + yt) * s]; });
      const outer = [[rc * 0.7, 0], [rc, yc], [rc, yt * 0.62], ...bell.map(([r, y]) => [r + wall, y])].reverse();
      const heat = (x, y) => { const s = clamp((yt - y) / (L + yt)); return [mix(0.5, 1, s) * mix(0.82, 1, s), mix(0.42, 1, s), mix(0.5, 1, Math.pow(s, 0.6))]; };
      b.add("nozzle", lathe(outer, sides), {uv: "keep", tint: heat});
      b.add("dark", new THREE.RingGeometry(re, re + wall, sides).rotateX(Math.PI / 2).translate(0, -L, 0));
      inner.push(lathe(bell, sides));
      for (const s of far ? [0.98] : [0.3, 0.62, 0.98]) { const r = rt + (re - rt) * Math.pow(Math.sin(s * Math.PI / 2), 0.72) + wall; b.add("steel", new THREE.TorusGeometry(r, re * 0.022, 6, sides).rotateX(Math.PI / 2).translate(0, yt - (L + yt) * s, 0), {uv: "keep"}); }
      const ym = yt - (L + yt) * 0.16, rm = rt + (re - rt) * Math.pow(Math.sin(0.16 * Math.PI / 2), 0.72) + wall + re * 0.05;
      b.add("aluminium", new THREE.TorusGeometry(rm, re * 0.05, 8, sides).rotateX(Math.PI / 2).translate(0, ym, 0), {uv: "keep"});
      if (!far) {
        for (const s of [1, -1]) {
          b.pipe("steel", [V3(s * rc * 0.5, yc * 0.3, 0), V3(s * rc * 1.7, yc * 1.6, s * rc * 0.3), V3(s * rm * 1.02, mix(yc, ym, 0.6), s * rc * 0.5), V3(s * rm, ym, 0)], re * 0.035, 6);
          b.add("aluminium", new THREE.CylinderGeometry(rc * 0.55, rc * 0.55, rc * 1.5, this.sides(16)).translate(0, yc * 2.2, s * rc * 1.7), {uv: [rc * 3, rc * 1.5]});
          b.add("dark", new THREE.SphereGeometry(rc * 0.55, this.sides(16), 8).translate(0, yc * 2.2 - rc * 0.75, s * rc * 1.7), {uv: "keep"});
          b.rod("steel", V3(s * re * 0.62, 0, s * re * 0.2), V3(s * rm * 0.95, ym + re * 0.08, s * rc * 0.2), re * 0.03, 6);
        }
        b.pipe("steel", [V3(0, yc * 2.2, rc * 1.7), V3(0, yc * 3.2, rc * 2.1), V3(0, mix(yc, ym, 0.7), rm * 0.9), V3(0, ym, rm)], re * 0.028, 6);
      }
      b.add("aluminium", new THREE.CylinderGeometry(re * 0.7, re * 0.7, re * 0.05, this.sides(24)).translate(0, -re * 0.025, 0), {uv: [re * 4, re * 0.05]});
    }
    const g = b.group(`engine (${kind})`);
    for (const geo of inner) {
      const pos = geo.attributes.position, col = new Float32Array(pos.count * 3);                   // hottest at the throat (or the grid's middle), cooler toward the lip
      for (let i = 0; i < pos.count; i++) { const rr = Math.hypot(pos.getX(i), pos.getZ(i)) / re, k = kind === "ion" ? 1 - 0.55 * rr * rr : 0.16 + 0.84 * Math.pow(1 - clamp(rr), 1.6); col.set([k, k, k], 3 * i); }
      geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
      const m = new THREE.Mesh(geo, glow); m.userData.keep = true; m.receiveShadow = true; m.name = "bell inside"; g.add(m); }
    const plume = (o.plume ?? true) ? makePlume(kind, re) : null;
    if (plume) { plume.position.y = -L; g.add(plume); }
    g.userData.engine = {kind, plume, glow, exit: re};
    g.userData.points = {mount: point(V3(0, 0, 0), Y, Z), exit: point(V3(0, -L, 0), Y.clone().negate(), Z)}; g.userData.size = {radius: re, length: L};
    return g;
  }

  /** A block of four small thrusters (attitude control) standing on its mount: `size`. Its puffs fire when
   * the craft turns (or with craft.update(t, {rcs})). Point: mount. */
  thrusters(o = {}) {
    known("thrusters options", o, ["size"]);
    const s = o.size ?? 0.16, b = this.bins(), g0 = [];
    b.box("aluminium", s * 1.3, s * 1.2, s * 1.3, new THREE.Matrix4().makeTranslation(0, s * 0.6, 0));
    b.box("foil-silver", s * 1.5, s * 0.5, s * 1.5, new THREE.Matrix4().makeTranslation(0, s * 0.25, 0));
    const dirs = [V3(1, 0.25, 0), V3(-1, 0.25, 0), V3(0, 0.25, 1), V3(0, 0.25, -1)].map((d) => d.normalize());
    for (const d of dirs) {
      const p = V3(0, s * 0.75, 0).addScaledVector(d, s * 0.6), q = p.clone().addScaledVector(d, s * 0.75);
      b.add("nozzle", new THREE.CylinderGeometry(s * 0.34, s * 0.12, s * 0.75, this.sides(14), 1, true), {at: between(p, q), uv: "keep", tint: [0.8, 0.75, 0.7]});
      const plume = makePlume("rcs", s * 0.34); plume.applyMatrix4(stand(q, d.clone().negate(), X)); g0.push(plume);
    }
    const g = b.group("thrusters"); g.add(...g0);
    g.userData.rcs = g0; g.userData.points = {mount: point(V3(0, 0, 0), Y.clone().negate(), Z), top: point(V3(0, s * 1.2, 0), Y, Z)}; g.userData.size = {radius: s * 1.5, length: s * 1.2};
    return g;
  }

  /** A landing leg reaching out along +x and down -y from its hip: `length` (the main strut), `angle` (degrees
   * from straight down), `pad` (radius), `ladder`. A two-stage main strut in foil, two side struts, a dished
   * pad on a ball. Points: mount, foot. */
  leg(o = {}) {
    known("leg options", o, ["length", "angle", "pad", "ladder", "skin"]);
    const L = o.length ?? 3, a = (o.angle ?? 32) * RAD, pad = o.pad ?? L * 0.14, b = this.bins(), r = L * 0.03;
    const hip = V3(0, 0, 0), foot = V3(L * Math.sin(a), -L * Math.cos(a), 0), knee = hip.clone().lerp(foot, 0.56);
    b.rod(o.skin ?? "foil", hip, knee, r * 1.25, 12); b.rod("steel", knee, foot, r * 0.8, 10);
    b.add("aluminium", new THREE.CylinderGeometry(r * 1.5, r * 1.5, r * 1.6, this.sides(12)), {at: between(knee.clone().lerp(hip, 0.03), knee.clone().lerp(foot, 0.03)), uv: [r * 8, r]});
    for (const s of [1, -1]) { const root = V3(0, -L * 0.42, s * L * 0.24); b.rod("aluminium", root, knee, r * 0.6, 8); b.rod("aluminium", V3(0, 0, s * L * 0.2), knee.clone().lerp(hip, 0.5), r * 0.45, 6); }
    b.add("steel", new THREE.SphereGeometry(r * 1.3, 10, 8).translate(...foot.toArray()), {uv: "keep"});
    const dishP = [[0, 0], [pad * 0.6, -pad * 0.03], [pad, pad * 0.12], [pad * 1.02, pad * 0.2]];
    b.add("foil", lathe(dishP, this.sides(28)).translate(foot.x, foot.y - r * 1.2 - pad * 0.0, 0), {uv: [TAU * pad, pad]});
    b.add("aluminium", lathe(dishP.map(([x, y]) => [x * 0.97, y + pad * 0.03]).reverse(), this.sides(28)).translate(foot.x, foot.y - r * 1.2, 0), {uv: [TAU * pad, pad]});
    if (o.ladder && !this.far) { const n = Math.round(L * 0.56 / 0.25), side = V3(0, 0, 0.16); for (const s of [1, -1]) b.rod("steel", hip.clone().addScaledVector(side, s).add(V3(r * 2, 0, 0)), knee.clone().addScaledVector(side, s).add(V3(r * 2, 0, 0)), 0.012, 5); for (let i = 1; i < n; i++) { const p = hip.clone().lerp(knee, i / n).add(V3(r * 2, 0, 0)); b.rod("steel", p.clone().addScaledVector(side, 1), p.clone().addScaledVector(side, -1), 0.011, 5); } }
    const g = b.group("leg");
    g.userData.points = {mount: point(V3(0, 0, 0), X.clone().negate(), Y), foot: point(V3(foot.x, foot.y - r * 1.2, 0), Y.clone().negate(), X)}; g.userData.size = {radius: L * 0.3, length: L}; g.userData.sparse = true;
    return g;
  }

  /** A ring habitat turning about +y: `radius`, `tube` (the ring's own radius), `spokes`, `rate` (radians a
   * second; default what gives `gravity` (0.3 g) at the rim), `windows`. Points: aft, fore (the hub's ends). */
  ringHabitat(o = {}) {
    known("ringHabitat options", o, ["radius", "tube", "spokes", "rate", "gravity", "windows", "hub"]);
    const R = o.radius ?? 12, tube = o.tube ?? Math.max(0.9, R * 0.12), spokes = o.spokes ?? 4, hub = o.hub ?? tube * 1.1, H = tube * 2.6, b = this.bins(), sb = this.bins();
    const rate = o.rate ?? Math.sqrt((o.gravity ?? 0.3) * 9.81 / R), far = this.far;
    sb.add("aluminium", new THREE.CylinderGeometry(hub * 0.8, hub * 0.8, H, this.sides(32), 1, false), {uv: [TAU * hub, H]});
    b.add("paint", new THREE.TorusGeometry(R, tube, this.sides(20), this.sides(96)).rotateX(Math.PI / 2), {uv: [TAU * R, TAU * tube]});
    b.add("paint", new THREE.CylinderGeometry(hub, hub, H * 0.7, this.sides(32), 1, false), {uv: [TAU * hub, H * 0.7]});
    const count = spokes * 6;
    for (let i = 0; i < count; i++) { const a = i * TAU / count; b.add("aluminium", new THREE.TorusGeometry(tube * 1.025, tube * 0.05, 5, this.sides(20)).rotateY(Math.PI / 2 - a).translate(R * Math.cos(a), 0, R * Math.sin(a)), {uv: "keep"}); }
    for (let i = 0; i < spokes; i++) {
      const a = (i + 0.5) * TAU / spokes, d = V3(Math.cos(a), 0, Math.sin(a));
      b.rod("paint", d.clone().multiplyScalar(hub * 0.95), d.clone().multiplyScalar(R - tube * 0.9), tube * 0.3, 14);
      if (!far) for (const s of [1, -1]) b.rod("steel", d.clone().multiplyScalar(hub).setY(s * H * 0.3), d.clone().multiplyScalar(R * 0.72), tube * 0.04, 5);
    }
    if (o.windows ?? true) {
      const n = Math.round(TAU * R / 1.4);
      for (let i = 0; i < n; i++) for (const s of [1, -1]) {
        if (hash2(i, s, this.seed) < 0.25) continue;
        const a = i * TAU / n, on = hash2(i, s + 3, this.seed) < this.options.lit;
        const m = new THREE.Matrix4().makeRotationY(-a).multiply(new THREE.Matrix4().makeTranslation(R, s * tube * 1.0, 0)).multiply(new THREE.Matrix4().makeRotationX(s > 0 ? 0 : Math.PI));
        b.box("aluminium", 0.5, 0.05, 0.42, m); b.box(on ? "window" : "glass", 0.4, 0.065, 0.32, m);
      }
    }
    const g = sb.group("ring habitat"), spin = b.group("ring");
    delete spin.userData.points; spin.userData.moving = true; spin.userData.spin = {rate}; g.add(spin);
    g.userData.points = {aft: point(V3(0, -H / 2, 0), Y.clone().negate(), Z), fore: point(V3(0, H / 2, 0), Y, Z), mount: point(V3(0, -H / 2, 0), Y.clone().negate(), Z)};
    g.userData.size = {radius: R + tube, length: H}; g.userData.ring = true;
    return g;
  }

  /** A cargo box: `size` [x, y, z]. Ribbed plating, corner blocks, an accent door. Points: mount (under), top, side. */
  container(o = {}) {
    known("container options", o, ["size", "skin"]);
    const [w, h, d] = o.size ?? [2.4, 2.4, 5], b = this.bins(), skin = o.skin ?? "paint";
    b.box(skin, w, h, d);
    for (const sx of [1, -1]) for (const sy of [1, -1]) { b.box("aluminium", 0.09, 0.09, d + 0.04, new THREE.Matrix4().makeTranslation(sx * w / 2, sy * h / 2, 0)); for (const sz of [1, -1]) b.box("dark", 0.2, 0.2, 0.2, new THREE.Matrix4().makeTranslation(sx * (w / 2 - 0.02), sy * (h / 2 - 0.02), sz * (d / 2 - 0.02))); }
    if (!this.far) { const n = Math.round(d / 0.45); for (let i = 1; i < n; i++) for (const sx of [1, -1]) b.box(skin, 0.035, h - 0.2, 0.09, new THREE.Matrix4().makeTranslation(sx * (w / 2 + 0.015), 0, -d / 2 + i * d / n)); }
    b.box("accent", w * 0.8, h * 0.8, 0.03, new THREE.Matrix4().makeTranslation(0, 0, d / 2 + 0.012));
    const g = b.group("container");
    g.userData.points = {mount: point(V3(0, -h / 2, 0), Y.clone().negate(), Z), top: point(V3(0, h / 2, 0), Y, Z), side: point(V3(-w / 2, 0, 0), X.clone().negate(), Z)}; g.userData.size = {radius: Math.max(w, h) / 2, length: d};
    return g;
  }

  /** A light on a small housing: `kind` (a key of LIGHTS: port | starboard | white | strobe | beacon | dock) or
   * {color, kind}; `size` (the lamp's radius). Point: mount. */
  light(o = {}) {
    known("light options", o, ["kind", "size", "color", "phase"]);
    const spec = typeof (o.kind ?? "white") === "string" ? LIGHTS[choice("light kind", o.kind ?? "white", Object.keys(LIGHTS))] : o.kind, s = o.size ?? 0.05, b = this.bins();
    b.add("dark", new THREE.CylinderGeometry(s * 0.9, s * 1.2, s * 1.2, 10).translate(0, s * 0.6, 0), {uv: "keep"});
    const g = b.group("light"), color = new THREE.Color(o.color ?? spec.color);
    const lamp = new THREE.Mesh(new THREE.SphereGeometry(s, 10, 8), new THREE.MeshBasicMaterial({color: color.clone(), toneMapped: false}));
    lamp.position.y = s * 1.4; lamp.userData.keep = true;
    const glow = makeGlow(color, s * 3.2, GLOW_PIXELS); glow.position.y = s * 1.4;
    g.add(lamp, glow);
    g.userData.light = {kind: spec.kind, color, lamp, glow, phase: o.phase ?? hash2(this.count++, 7, this.seed)};
    g.userData.points = {mount: point(V3(0, 0, 0), Y.clone().negate(), Z)}; g.userData.size = {radius: s, length: s * 2}; g.userData.sparse = true;
    return g;
  }

  /** Finish a craft from its root part: see Craft. `fore`: the root's point that becomes the nose (+z). */
  craft(root, options = {}) { return new Craft(root, this, options); }
}
/** The parts of a craft: craftKit({seed, accent, foil, detail, wear, lit}). */
export const craftKit = (options = {}) => new CraftKit(options);

// ---------- attitude: where a craft points, a function of t ----------
/** The attitude modes. A craft's +z is its nose (engines push it that way), +y its top.
 * prograde / retrograde: the nose along / against its velocity (relative to the body it orbits), the top away
 * from that body; radial: the nose away from the body; nadir: the belly to the body, the nose forward (a station);
 * sun: `axis` (default the top) to the sun; target: `axis` (default the nose) to the target, the top toward the
 * sun; thrust: the nose along a burn's change of velocity; inertial: {forward, up} fixed in the scene. */
export const ATTITUDES = Object.freeze(["prograde", "retrograde", "radial", "nadir", "sun", "target", "thrust", "inertial"]);
const AXES = {x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1], "-x": [-1, 0, 0], "-y": [0, -1, 0], "-z": [0, 0, -1]};
const vec = (v, fallback) => (v && v.isVector3 ? v : isVec(v) ? V3(...v) : fallback);
// the turn taking the craft's own unit axes a, b (at right angles) to A and, as nearly as can be, B
function alignQ(a, A, b, B, out = new THREE.Quaternion()) {
  const local = new THREE.Matrix4().makeBasis(a, b, V3().crossVectors(a, b));
  const y = B.clone().addScaledVector(A, -B.dot(A) / Math.max(A.lengthSq(), 1e-30));
  const world = frameOf(A, y.lengthSq() > 1e-12 ? y : (Math.abs(A.clone().normalize().y) < 0.9 ? Y : X));    // frameOf: y = A, x = B
  const W = new THREE.Matrix4().makeBasis(V3().setFromMatrixColumn(world, 1), V3().setFromMatrixColumn(world, 0), V3().crossVectors(V3().setFromMatrixColumn(world, 1), V3().setFromMatrixColumn(world, 0)));
  return out.setFromRotationMatrix(W.multiply(local.transpose()));
}
/** The quaternion of one attitude. `spec`: a mode's name or {mode, axis, forward, up}; `state`: {velocity,
 * radial (from the body it orbits to the craft), sun, target, thrust}: directions in the scene's axes (Vector3
 * or [x, y, z]; any length). */
export function attitudeQuaternion(spec, state = {}, out = new THREE.Quaternion()) {
  const e = typeof spec === "string" ? {mode: spec} : spec;
  choice("attitude", e.mode, ATTITUDES);
  const v = vec(state.velocity, Z), r = vec(state.radial, Y), need = (name) => { const x = vec(state[name], null); if (!x || x.lengthSq() === 0) throw fail(`attitude "${e.mode}" needs ${name}: give update(t, {${name}}) or fly(space, {${name}})`); return x; };
  const axis = (fallback) => { const a = e.axis ?? fallback; if (!AXES[a]) throw fail(`attitude axis "${a}"${hint(a, Object.keys(AXES))}; one of: ${Object.keys(AXES).join(", ")}`); return V3(...AXES[a]); };
  const other = (a) => (Math.abs(a.z) > 0.5 ? Y : Z);
  if (e.mode === "prograde") return alignQ(Z, v, Y, r, out);
  if (e.mode === "retrograde") return alignQ(Z, v.clone().negate(), Y, r, out);
  if (e.mode === "radial") return alignQ(Z, r, Y, v, out);
  if (e.mode === "nadir") return alignQ(Y, r, Z, v, out);
  if (e.mode === "sun") { const a = axis("y"); return alignQ(a, need("sun"), other(a), v, out); }
  if (e.mode === "target") { const a = axis("z"); return alignQ(a, need("target"), other(a), vec(state.sun, r), out); }
  if (e.mode === "thrust") return alignQ(Z, need("thrust"), Y, r, out);
  return alignQ(Z, vec(e.forward, Z), Y, vec(e.up, Y), out);
}
const schedule = (spec) => (Array.isArray(spec) ? spec.map((e, i) => ({at: i === 0 ? -Infinity : 0, turn: 3, ...(typeof e === "string" ? {mode: e} : e)})) : [{at: -Infinity, turn: 3, ...(typeof spec === "string" ? {mode: spec} : spec)}]);
/** The attitude at t: `spec` is one attitude, or a list [{mode, ...}, {at: seconds, turn: seconds (3), mode,
 * ...}, ...]: from `at` the craft turns to the next one over `turn` seconds, eased at both ends. Each mode is
 * worked out for t itself, so the answer is a function of t and `state` only. */
export function attitudeAt(t, spec, state = {}, out = new THREE.Quaternion()) {
  const list = schedule(spec);
  attitudeQuaternion(list[0], state, out);
  for (let i = 1; i < list.length; i++) { const u = smoother((t - list[i].at) / Math.max(list[i].turn, 1e-6)); if (u > 0) out.slerp(attitudeQuaternion(list[i], state, Q1), u); }
  return out;
}
const Q1 = new THREE.Quaternion(), Q2 = new THREE.Quaternion();
/** The burns of ctx.orbits as stretches of scene time. A burn of the orbit model happens in an instant; a film
 * shows it as `seconds` of thrust centred on that instant (a stated convention). Returns [{start, end, at,
 * direction: [x, y, z] (the change of velocity, three.js axes), magnitude, label}]. */
export function burnWindows(burns, fps, {seconds = 2} = {}) {
  return burns.filter((b) => b.frame !== null && b.frame !== undefined && b.magnitude > 0).map((b) => {
    const at = b.frame / fps, m = Math.hypot(...b.dv) || 1;
    return {start: at - seconds / 2, end: at + seconds / 2, at, direction: [b.dv[0] / m, b.dv[2] / m, -b.dv[1] / m], magnitude: b.magnitude, label: b.label ?? null};
  });
}
/** The throttle (0..1) at t for those stretches: up in `rise` seconds, down in `fall`. */
export function throttleAt(t, windows, {rise = 0.25, fall = 0.4} = {}) {
  let k = 0;
  for (const w of windows) k = Math.max(k, smooth(w.start, w.start + rise, t) * (1 - smooth(w.end - fall, w.end, t)));
  return k;
}
/** How far a craft has turned toward a burn's direction at t (0..1): there `turn` seconds before the burn,
 * held through it, back over `turn` seconds after. */
export const burnWeight = (t, w, turn = 3) => Math.min(smoother((t - (w.start - turn * 1.15)) / turn), 1 - smoother((t - w.end - turn * 0.15) / turn));
/** The angle (radians) a wing turns about its length (+x) so that its face (+z) is as near `sun` as it can be;
 * `sun`: the direction in the axes the wing hangs in. */
export const trackAngle = (sun) => (Math.hypot(sun.y, sun.z) < 1e-6 ? 0 : Math.atan2(-sun.y, sun.z));
/** A dish's two angles (radians) for `target` in the axes it stands in (+y its rest direction): [azimuth about
 * y, elevation from y], the elevation held within `limit`. */
export const aimAngles = (target, limit = 1.75) => { const d = target.clone().normalize(); return [Math.hypot(d.x, d.z) < 1e-6 ? 0 : Math.atan2(d.x, d.z), Math.min(limit, Math.acos(clamp(d.y, -1, 1)))]; };

// ---------- a finished craft ----------
/** The flash of a far craft whose flat face mirrors the sun to the camera: how narrow the mirror angle is (the
 * power of the cosine between the face and the half-way direction) and how bright against the craft's own light. */
export const GLINT = Object.freeze({sharpness: 500, gain: 300});
const CRAFT_DEFAULTS = Object.freeze({fore: "fore", name: "craft", occlusion: 0.55, camera: null, height: 720, sun: null, target: null, lights: 1, marker: 0, kind: null, seed: null});
const UPDATE_KEYS = ["sun", "target", "velocity", "radial", "thrust", "attitude", "throttle", "rcs", "lights", "camera", "height", "deploy", "spin"];
const FLY_KEYS = ["body", "attitude", "burn", "target", "sun", "parent", "camera", "height", "throttle", "marker"];
const W1 = V3(), W2 = V3(), W3 = V3(), WQ = new THREE.Quaternion();

/** A craft: `object` (a THREE.Group in metres: +z the nose, +y the top, its middle at the origin), update(t,
 * {...}), fly(space, {...}), `occluders` (for a Star's `occluders`: balls along its hull), `shadows` (options for
 * spaceLight's `shadows`), `size` ({radius, length, width, height} metres), `info` ({kind, seed, triangles,
 * meshes, parts}), `engines`, `thrusters`, `lights`, `wings`, `dishes`, `materials`, dispose(). */
export class Craft {
  constructor(root, kit, options = {}) {
    known("craft options", options, Object.keys(CRAFT_DEFAULTS));
    const o = this.options = {...CRAFT_DEFAULTS, ...options};
    this.kit = kit; this.materials = kit.materials;
    this.object = new THREE.Group(); this.object.name = o.name; this.object.userData.craft = this;
    const f = pointOf(root, o.fore);
    root.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(Y, Z, X).multiply(frameOf(f.n, f.u).transpose()));
    this.object.add(root); this.object.updateMatrixWorld(true);
    const box = new THREE.Box3(), mid = V3();
    root.traverse((n) => { if (n.isMesh && !n.userData.keep) { if (!n.geometry.boundingBox) n.geometry.computeBoundingBox(); box.union(W_B.copy(n.geometry.boundingBox).applyMatrix4(n.matrixWorld)); } });
    box.getCenter(mid); root.position.sub(mid); this.object.updateMatrixWorld(true);
    const dim = box.getSize(V3());
    this.size = {radius: 0.5 * dim.length(), length: dim.z, width: dim.x, height: dim.y};
    this.wings = []; this.dishes = []; this.spinners = []; this.engines = []; this.thrusters = []; this.lights = []; this.folds = []; this.facets = [];
    let parts = 0;
    root.traverse((n) => {
      const u = n.userData;
      if (u.part) parts++;
      if (u.track) this.wings.push(n);
      if (u.aim) this.dishes.push(u.aim);
      if (u.spin) this.spinners.push(n);
      if (u.engine) this.engines.push(u.engine);
      if (u.rcs) this.thrusters.push(u.rcs);
      if (u.light) this.lights.push(u.light);
      if (u.deploy) this.folds.push(u.deploy);
      if (u.facet) this.facets.push({node: n, ...u.facet});
      if (u.facets) for (const f of u.facets) this.facets.push({node: n, ...f});
    });
    this._balls(root);
    if (o.occlusion > 0) this._occlude(root, o.occlusion);
    this._compile(root);
    let triangles = 0, meshes = 0;
    this.object.traverse((n) => { if (n.isMesh) { meshes++; triangles += n.geometry.index ? n.geometry.index.count / 3 : n.geometry.attributes.position.count / 3; } });
    /** A point of light for the craft far away (under a few pixels): steady, with a flash when a wing mirrors the sun. */
    this.glint = makeGlow(0xffffff, 1, GLOW_PIXELS); this.glint.visible = false; this.object.add(this.glint);
    this.root = root;
    this.shadows = {size: Math.max(1, this.size.radius * 1.08), mapSize: 2048, bias: -0.0004};
    this.flight = null; this.burns = []; this.state = null;
    this.info = {kind: o.kind, seed: o.seed, triangles: Math.round(triangles), meshes, parts};
  }

  // balls that stand for the solid parts (the sun's glare is hidden by them; the baked shading reads them)
  _balls(root) {
    this.occluders = []; this._ballList = [];
    const inv = this.object.matrixWorld.clone().invert(), bb = new THREE.Box3(), groups = [];
    root.traverse((n) => { if (n.userData.part && !n.userData.sparse && n.children.some((c) => c.isMesh && !c.userData.keep)) groups.push(n); });
    for (const g of groups) {
      bb.makeEmpty();
      for (const c of g.children) if (c.isMesh && !c.userData.keep) { if (!c.geometry.boundingBox) c.geometry.computeBoundingBox(); bb.union(c.geometry.boundingBox); }
      const d = bb.getSize(V3()), sorted = [d.x, d.y, d.z].sort((a, b) => a - b), s = Math.max(sorted[0], sorted[1] / 2, sorted[2] / 6, 1e-3), r = s * (sorted[0] < 0.5 * s ? 0.64 : 0.6);
      const n = [d.x, d.y, d.z].map((v) => Math.max(1, Math.ceil(v / s - 0.25)));
      for (let i = 0; i < n[0]; i++) for (let j = 0; j < n[1]; j++) for (let k = 0; k < n[2]; k++) {
        const ball = new THREE.Object3D();
        ball.position.set(bb.min.x + (i + 0.5) * d.x / n[0], bb.min.y + (j + 0.5) * d.y / n[1], bb.min.z + (k + 0.5) * d.z / n[2]); ball.scale.setScalar(r);
        g.add(ball); ball.updateMatrixWorld(true);
        this.occluders.push({object: ball});
        this._ballList.push({c: ball.getWorldPosition(V3()).applyMatrix4(inv), r, part: g});
      }
    }
  }

  // shading baked into the vertices' colours: how much of the open sky each vertex loses to the other parts
  _occlude(root, strength) {
    const balls = this._ballList, p = V3(), n = V3(), nm = new THREE.Matrix3();
    root.traverse((mesh) => {
      if (!mesh.isMesh || mesh.userData.keep) return;
      let own = mesh.parent;
      while (own && !own.userData.part) own = own.parent;
      const near = balls.filter((b) => b.part !== own);
      if (!near.length) return;
      const pos = mesh.geometry.attributes.position, nor = mesh.geometry.attributes.normal, col = mesh.geometry.attributes.color;
      nm.getNormalMatrix(mesh.matrixWorld);
      for (let i = 0; i < pos.count; i++) {
        p.fromBufferAttribute(pos, i).applyMatrix4(mesh.matrixWorld); n.fromBufferAttribute(nor, i).applyMatrix3(nm).normalize();
        let lost = 0;
        for (const b of near) {
          const dx = b.c.x - p.x, dy = b.c.y - p.y, dz = b.c.z - p.z, d2 = dx * dx + dy * dy + dz * dz, r2 = b.r * b.r;
          if (d2 > r2 * 16) continue;
          const d = Math.sqrt(d2), cos = (dx * n.x + dy * n.y + dz * n.z) / Math.max(d, 1e-6);
          lost += Math.max(0, cos * 0.75 + 0.25) * Math.min(1, r2 / Math.max(d2, r2 * 0.6)) * (1 - smooth(r2 * 6, r2 * 16, d2));
        }
        const k = 1 - strength * (1 - Math.exp(-0.9 * lost));
        col.setXYZ(i, col.getX(i) * k, col.getY(i) * k, col.getZ(i) * k);
      }
    });
  }

  // one mesh per surface for the craft and for each part that moves
  _compile(root) {
    const islands = [root];
    root.traverse((n) => { if (n !== root && n.userData.moving) islands.push(n); });
    for (const island of islands) {
      const inv = island.matrixWorld.clone().invert(), by = new Map(), gone = [];
      const walk = (n) => { for (const c of n.children) { if (c.userData.moving) continue; if (c.isMesh && !c.userData.keep) { c.geometry.applyMatrix4(W_M.multiplyMatrices(inv, c.matrixWorld)); if (!by.has(c.material)) by.set(c.material, []); by.get(c.material).push(c.geometry); gone.push(c); } walk(c); } };
      walk(island);
      for (const c of gone) c.removeFromParent();
      for (const [material, list] of by) {
        const mesh = new THREE.Mesh(list.length === 1 ? list[0] : mergeGeometries(list, false), material);
        if (list.length > 1) for (const g of list) g.dispose();
        mesh.castShadow = material.name !== "window"; mesh.receiveShadow = true; mesh.name = material.name;
        island.add(mesh);
      }
    }
  }

  /** Fly a body of ctx.orbits: `space` (a vidgen/space-scale SpaceView), {body (its name), attitude (a mode, or a
   * list with times; default "prograde"), burn ({seconds: 2, turn: 3, attitude: "thrust"} or false: how the
   * data's burns are shown: the craft turns its nose along each burn, the engines fire for `seconds` centred on
   * it, and it turns back), target (a body's name: for "target" and the dishes), sun (default the data's Sun),
   * parent (the body its velocity is measured against; default the data's), camera, height}. Returns the craft. */
  fly(space, options = {}) {
    known("fly options", options, FLY_KEYS);
    if (!space || !space.orbits || typeof space.add !== "function") throw fail("fly needs a SpaceView of vidgen/space-scale with orbit data (ctx.orbits)");
    const orbits = space.orbits, names = orbits.names, name = (key, v) => { if (!names.includes(v)) throw fail(`fly: ${key} "${v}"${hint(v, names)}; bodies of the data: ${names.join(", ")}`); return v; };
    if (typeof options.body !== "string") throw fail(`fly needs {body}: a name of the orbit data (${names.join(", ")})`);
    const body = name("body", options.body), burn = options.burn === false ? null : {seconds: 2, turn: 3, attitude: "thrust", ...(options.burn ?? {})};
    if (burn) known("fly burn", burn, ["seconds", "turn", "attitude"]);
    space.add(this.object, {body});
    const parent = options.parent ?? orbits.bodies[body].parent ?? names[0];
    this.flight = {space, orbits, body, parent: parent && parent !== body && names.includes(parent) ? parent : null, attitude: options.attitude ?? "prograde", burn,
      target: typeof options.target === "string" ? name("target", options.target) : null, sun: options.sun ?? (names.includes("Sun") && body !== "Sun" ? "Sun" : null)};
    this.burns = burn ? burnWindows(orbits.burns(body), orbits.fps, burn) : [];
    for (const k of ["camera", "height", "throttle", "marker"]) if (options[k] !== undefined) this.options[k] = options[k];
    return this;
  }

  // a burn's direction at t: the burn's Δv kept in the flight's own axes (along the velocity, out from the parent,
  // across the plane) as they were at its instant, so a turn and a burn shown for seconds of a sped-up scene
  // still point the way the burn does there (a prograde burn stays prograde), not along the instant's fixed line
  _thrustAt(w, state) {
    const y = (a, b) => V3(a[0] - b[0], a[2] - b[2], -(a[1] - b[1]));
    const fl = this.flight, ob = fl.orbits, axes = (v, r) => { const e1 = v.clone().normalize(), e3 = r.clone().cross(v).normalize(); return [e1, e3.clone().cross(e1), e3]; };
    const d = V3(...w.direction);
    if (!fl.parent || !(state.velocity.lengthSq() > 0) || !(state.radial.lengthSq() > 0)) return d;
    const zero = [0, 0, 0], pv = ob.velocity(fl.parent, w.at), pp = ob.position(fl.parent, w.at);
    const then = axes(y(ob.velocity(fl.body, w.at), pv ?? zero), y(ob.position(fl.body, w.at), pp ?? zero)), now = axes(state.velocity, state.radial);
    if (then.some((e) => !Number.isFinite(e.x)) || now.some((e) => !Number.isFinite(e.x))) return d;
    return now[0].multiplyScalar(d.dot(then[0])).add(now[1].multiplyScalar(d.dot(then[1]))).add(now[2].multiplyScalar(d.dot(then[2]))).normalize();
  }

  // towards the sun from the craft, from whatever was given: a direction, an Object3D, a Star or a SpaceLight
  _toward(what, out) {
    if (!what) return null;
    if (isVec(what)) return out.set(...what).normalize();
    if (what.isVector3) return out.copy(what).normalize();
    if (what.star || what.sunObject || what.direction) what = what.star ?? what.sunObject ?? what.direction;   // a SpaceLight
    if (what.isVector3) return out.copy(what).normalize();
    if (what.infinite && what.direction) return out.copy(what.direction).normalize();
    const object = what.isObject3D ? what : what.object;
    if (!object || !object.isObject3D) throw fail("sun / target: a direction [x, y, z], a THREE.Vector3, an Object3D standing there, a star or the spaceLight of vidgen/space-light");
    return out.setFromMatrixPosition(object.matrixWorld).sub(W3.setFromMatrixPosition(this.object.matrixWorld)).normalize();
  }

  /** Set the craft to scene time `t`. Options (each also a default from craft(...) or fly(...)): `sun`, `target`
   * (where they are: a direction, an object, a star, the spaceLight): the wings track the sun, gimballed dishes
   * point at the target; `attitude` with `velocity`, `radial`, `thrust` (directions) for a craft that is not
   * flown from ctx.orbits; `throttle` (0..1, a list per engine, or a function of t; default the burns of fly());
   * `rcs` (0..1 or a function of (t, i); default puffs at the start and end of each turn); `lights` (0..1 or a
   * function of (t, i): multiplies each light's own blinking); `deploy` (0..1 for deployable wings); `camera`,
   * `height` (the frame's, in pixels): under a few pixels the craft becomes a point of light. Returns the craft. */
  update(t = 0, options = {}) {
    known("update options", options, UPDATE_KEYS);
    const o = {...this.options, ...options}, fl = this.flight, state = {velocity: options.velocity, radial: options.radial, thrust: options.thrust};
    let spec = options.attitude ?? null, turning = 0;
    this.object.updateMatrixWorld(true);
    if (fl) {
      const ob = fl.orbits, p = ob.position(fl.body, t), v = ob.velocity(fl.body, t), pp = fl.parent ? ob.position(fl.parent, t) : [0, 0, 0], pv = fl.parent ? ob.velocity(fl.parent, t) : [0, 0, 0];
      const y = (a, b) => V3(a[0] - b[0], a[2] - b[2], -(a[1] - b[1]));
      state.velocity = y(v, pv); state.radial = y(p, pp);
      if (typeof fl.sun === "string") state.sun = y(ob.position(fl.sun, t), p).normalize();
      if (fl.target) state.target = y(ob.position(fl.target, t), p).normalize();
      spec = spec ?? fl.attitude;
    }
    const sun = state.sun ?? this._toward(options.sun ?? (fl && typeof fl.sun !== "string" ? fl.sun : null) ?? this.options.sun, W1);
    const target = state.target ?? this._toward(options.target ?? this.options.target, W2);
    state.sun = sun; state.target = target;
    if (spec) {
      const q = attitudeAt(t, spec, state, this.object.quaternion);
      for (const e of schedule(spec).slice(1)) { const u = (t - e.at) / Math.max(e.turn, 1e-6); if (u > 0 && u < 1) turning = Math.max(turning, u < 0.14 ? 1 : u > 0.86 ? -1 : 0); }
      if (fl && fl.burn) for (const w of this.burns) {
        const k = burnWeight(t, w, fl.burn.turn);
        if (k > 0) q.slerp(attitudeQuaternion(fl.burn.attitude, {...state, thrust: this._thrustAt(w, state)}, Q2), k);
        const a = (t - (w.start - fl.burn.turn * 1.15)) / fl.burn.turn, b = (t - w.end - fl.burn.turn * 0.15) / fl.burn.turn;
        for (const u of [a, b]) if (u > 0 && u < 1 && (u < 0.14 || u > 0.86)) turning = u < 0.14 ? 1 : -1;
      }
      this.object.updateMatrixWorld(true);
    }
    for (const arm of this.wings) if (sun) { arm.parent.getWorldQuaternion(WQ).invert(); arm.rotation.x = trackAngle(W3.copy(sun).applyQuaternion(WQ)); }
    for (const d of this.dishes) if (target) { d.az.parent.getWorldQuaternion(WQ).invert(); const [az, el] = aimAngles(W3.copy(target).applyQuaternion(WQ)); d.az.rotation.y = az; d.el.rotation.x = el; }
    for (const s of this.spinners) s.rotation.y = (options.spin ?? 1) * s.userData.spin.rate * t;
    if (options.deploy !== undefined) for (const f of this.folds) f(options.deploy);
    const base = typeof o.throttle === "function" ? o.throttle(t) : (o.throttle ?? (this.burns.length ? throttleAt(t, this.burns) : 0));
    this.engines.forEach((e, i) => {
      const k = clamp(Array.isArray(base) ? (base[i] ?? 0) : base), f = k * flicker(t, i);
      if (e.plume) { e.plume.visible = k > 0.002; const u = e.plume.material.uniforms.uNow.value; u.x = f; u.y = t; }
      const c = e.plume ? e.plume.userData.plume.color : PLUMES[e.kind].core;
      e.glow.color.setRGB(0.02 + c[0] * f * 3.2, 0.02 + c[1] * f * 3.2, 0.02 + c[2] * f * 3.2);
    });
    this.thrusters.forEach((quad, i) => quad.forEach((plume, j) => {
      const auto = turning !== 0 && ((i + j + (turning > 0 ? 0 : 1)) % 2 === 0) ? 0.75 + 0.25 * Math.sin(TAU * 23 * t + i) : 0;
      const k = clamp(typeof o.rcs === "function" ? o.rcs(t, i, j) : (o.rcs ?? auto));
      plume.visible = k > 0.002; const u = plume.material.uniforms.uNow.value; u.x = k; u.y = t + i * 0.37;
    }));
    this.lights.forEach((l, i) => {
      const k = blink(l.kind, t, l.phase) * (typeof o.lights === "function" ? o.lights(t, i) : o.lights);
      l.lamp.material.color.copy(l.color).multiplyScalar(0.06 + 2.2 * k); l.glow.material.uniforms.uLevel.value = 1.6 * k; l.glow.visible = k > 0.003;
    });
    this.object.updateMatrixWorld(true);
    let small = 0;
    if (o.camera) {
      const cam = o.camera; cam.updateMatrixWorld();
      const at = W3.setFromMatrixPosition(this.object.matrixWorld), eye = W2.setFromMatrixPosition(cam.matrixWorld), dist = at.distanceTo(eye), scale = this.object.getWorldScale(V3()).x;
      const px = this.size.radius * scale * o.height * 0.5 * cam.projectionMatrix.elements[5] / Math.max(dist, 1e-9);
      small = 1 - smooth(1.6, 4.5, px);
      const hidden = px < 1.6;
      if (this.root.visible === hidden) this.root.visible = !hidden;
      this.glint.visible = small > 0.001;
      if (this.glint.visible) {
        const view = eye.clone().sub(at).normalize(), s = sun ? sun.clone() : view.clone(), half = s.clone().add(view).normalize(), phase = 0.5 + 0.5 * s.dot(view);
        let flash = 0, area = 0;
        for (const f of this.facets) { const n = V3().copy(f.normal).applyQuaternion(f.node.getWorldQuaternion(WQ)); area += f.area; flash += f.area * f.gloss * Math.pow(Math.max(0, n.dot(half)), GLINT.sharpness) * GLINT.gain + f.area * 0.25 * Math.max(0, n.dot(s)) * Math.max(0, n.dot(view)); }
        const R = this.size.radius, body = 0.22 * (0.15 + 0.85 * phase) * 0.35, light = body + (area > 0 ? flash / (Math.PI * R * R) : 0);
        const u = this.glint.material.uniforms; u.uSize.value.set(R * 0.75, GLOW_PIXELS); u.uLevel.value = Math.min(40, light * 5.5 * 1.9) * small; u.uFloor.value = o.marker * small;
        this.glintLevel = u.uLevel.value;
      }
    } else if (!this.root.visible) this.root.visible = true;
    this.state = {t, sun: sun ? sun.toArray() : null, target: target ? target.toArray() : null, throttle: base, turning, small};
    return this;
  }

  /** Let this craft hide `star`'s glare (a Star of vidgen/space-light): adds its balls to star.occluders. */
  shade(star) { star.occluders = [...star.occluders.filter((x) => !this.occluders.includes(x)), ...this.occluders]; return this; }

  dispose() {
    this.object.traverse((n) => { if (n.isMesh && n.geometry !== GLOW_GEOMETRY) n.geometry.dispose(); if (n.isMesh && (n.material.isShaderMaterial || n.material.isMeshBasicMaterial)) n.material.dispose(); });
    for (const m of Object.values(this.materials)) m.dispose();
    this.object.removeFromParent();
  }
}
const W_M = new THREE.Matrix4(), W_B = new THREE.Box3();

// ---------- reflections: the sky and the worlds round a craft, as scene.environment ----------
/** What a craft's metal mirrors: the scene seen from `at` (an Object3D or [x, y, z]; default the origin) drawn
 * once into a small cube and blurred for every roughness (PMREM): the sky, and the day side of a world close by,
 * so foil in the sun's shadow shows the planet's blue. Craft, stars and glare are left out (the sun is a light,
 * not a reflection). Options: `size` (the cube's faces, 128), `hide` (more objects to leave out), `near`, `far`.
 * Returns {texture, update(): draw it again (after the craft or the worlds have moved far), dispose()}:
 * `scene.environment = env.texture`. Made once: about 0.3 s; it is not drawn every frame. */
export function craftEnvironment(renderer, scene, options = {}) {
  known("craftEnvironment options", options, ["at", "size", "hide", "near", "far"]);
  const size = options.size ?? 128, target = new THREE.WebGLCubeRenderTarget(size, {type: THREE.HalfFloatType, generateMipmaps: true, minFilter: THREE.LinearMipmapLinearFilter});
  const camera = new THREE.CubeCamera(options.near ?? 1, options.far ?? 1e13, target), pmrem = new THREE.PMREMGenerator(renderer);
  for (const face of camera.children) face.fov = 90;          // three's cube faces have a field of view of -90 (their picture turned half round); the worlds of vidgen/space-bodies read the angle
  const env = {texture: null, target: null,
    update() {
      const at = options.at;
      scene.updateMatrixWorld(true);
      if (at && at.isObject3D) camera.position.setFromMatrixPosition(at.matrixWorld); else if (isVec(at)) camera.position.set(...at); else camera.position.set(0, 0, 0);
      camera.updateMatrixWorld(true);
      const hidden = [];
      scene.traverse((n) => { if (n.visible && (n.userData.craft || n.userData.overlay || n.name.startsWith("star ") || (options.hide ?? []).includes(n))) { hidden.push(n); n.visible = false; } });
      const before = renderer.getRenderTarget(), environment = scene.environment, shadows = renderer.shadowMap.autoUpdate;
      scene.environment = null; renderer.shadowMap.autoUpdate = false;
      try { camera.update(renderer, scene); } finally { for (const n of hidden) n.visible = true; scene.environment = environment; renderer.shadowMap.autoUpdate = shadows; renderer.setRenderTarget(before); }
      if (env.target) env.target.dispose();
      env.target = pmrem.fromCubemap(target.texture); env.texture = env.target.texture;
      if (environment && environment === env.previous) scene.environment = env.texture;
      env.previous = env.texture;
      return env;
    },
    dispose() { target.dispose(); pmrem.dispose(); if (env.target) env.target.dispose(); }};
  return env.update();
}

// ---------- ready-made craft: invented designs, another one for every seed ----------
const at3 = (x, y, z, n, u = Z) => point(V3(x, y, z), n, u);
const DESIGNS = {
  // a deep-space probe: a foil-wrapped bus under a fixed high-gain dish (the nose: point it with attitude
  // "target"), power units on a lattice boom, a long magnetometer boom, a scan platform, a tank and an engine
  probe(kit, r, o) {
    const sides = o.sides ?? pick(r, [6, 8, 8, 10]), R = range(r, 0.85, 1.1), H = range(r, 0.95, 1.35), step = 360 / sides, face = (k) => Math.round(k / step) * step;
    const bus = kit.hull({shape: "prism", sides, radius: R, length: H, skin: "foil", greebles: 0.7});
    const deck = attach(bus, "fore", kit.hull({shape: "prism", sides, radius: R * 0.72, length: 0.22, skin: "foil-silver"}), "aft");
    attach(deck, "fore", kit.dish({diameter: o.dish ?? range(r, 2.7, 3.7), gimbal: false, neck: 0.3}));
    const tank = attach(bus, "aft", kit.tank({shape: "sphere", radius: R * range(r, 0.48, 0.6), skin: pick(r, ["foil-silver", "foil", "aluminium"])}), "top");
    attach(tank, "bottom", kit.engine({exit: 0.2, kind: "chemical"}));
    const power = attach(bus, {angle: 0, along: 0.3}, kit.boom({length: range(r, 2.6, 4.2), lattice: true}));
    let unit = attach(power, "tip", kit.powerUnit({length: 1.0, radius: 0.13}));
    for (let i = 1; i < (o.power ?? whole(r, 1, 2)); i++) unit = attach(unit, "tip", kit.powerUnit({length: 1.0, radius: 0.13}), "mount", {gap: 0.08});
    const mag = attach(bus, {angle: 180, along: 0.7}, kit.boom({length: range(r, 5.5, 9), radius: 0.022}));
    attach(mag, "tip", kit.instrument({kind: "magnetometer", size: 0.32}));
    attach(mag, {angle: 90, along: 0.55}, kit.instrument({kind: "magnetometer", size: 0.26}));
    const arm = attach(bus, {angle: face(90), along: 0.72}, kit.boom({length: range(r, 0.9, 1.5), radius: 0.045, skin: "foil-silver"}));
    attach(arm, "tip", kit.instrument({kind: "platform", size: range(r, 0.36, 0.46)}), "mount", {roll: 90});
    around(bus, () => kit.thrusters({size: 0.11}), {count: sides === 6 ? 3 : 4, angle: sides === 6 ? 60 : face(45), along: 0.12});
    attach(bus, {angle: face(270), along: 0.75}, kit.instrument({kind: "tracker", size: 0.28}));
    attach(bus, {angle: face(270) - step, along: 0.3}, kit.antenna({kind: pick(r, ["helix", "omni", "patch"]), length: 0.5}));
    if (r() < 0.6) attach(bus, {angle: face(270) + step, along: 0.5}, kit.instrument({kind: "spectrometer", size: 0.36}));
    attach(bus, {angle: face(135), along: 0.9}, kit.light({kind: "strobe", size: 0.03}));
    return bus;
  },
  // a communications satellite: a box bus in foil, two long tracking wings, reflectors on arms looking the
  // way of the nose (the Earth: attitude "nadir" is not it - use "target" or "radial" turned), feed horns, an engine
  satellite(kit, r, o) {
    const w = range(r, 1.9, 2.4), d = range(r, 1.9, 2.5), L = range(r, 2.6, 3.6), bus = kit.hull({shape: "box", size: [w, d], length: L, skin: "foil"});
    const panels = o.panels ?? whole(r, 3, 5), size = [range(r, 1.9, 2.4), range(r, 2.2, 2.9)];
    for (const a of [0, 180]) attach(bus, {angle: a, along: 0.45}, kit.solarWing({panels, size, yoke: 1.3}));
    const dishes = o.dishes ?? whole(r, 1, 2), D = range(r, 1.9, 2.6);
    for (let i = 0; i < dishes; i++) { const arm = attach(bus, {angle: 90 + 180 * i, along: 0.62}, kit.boom({length: D * 0.62, radius: 0.05})); attach(arm, {angle: 90, along: 0.96}, kit.dish({diameter: D, gimbal: false, neck: 0.25, focal: 0.5})); }
    const deck = attach(bus, "fore", kit.hull({shape: "box", size: [w * 0.82, d * 0.82], length: 0.16, skin: "radiator"}), "aft");
    attach(deck, at3(-w * 0.2, 0.08, d * 0.15, Y), kit.antenna({kind: "horn", length: 0.5}));
    attach(deck, at3(w * 0.22, 0.08, d * 0.2, Y), kit.antenna({kind: "horn", length: 0.36}));
    attach(deck, at3(w * 0.2, 0.08, -d * 0.22, Y), kit.antenna({kind: "helix", length: 0.9}));
    if (dishes < 2) attach(deck, at3(-w * 0.15, 0.08, -d * 0.2, Y), kit.dish({diameter: 0.9, neck: 0.3}));
    for (const a of [90, 270]) for (const k of [0.3, 0.72]) { const p = bus.userData.surface(a, k, 0.012); const b = kit.bins(); b.box("radiator", L * 0.3, 0.02, (a === 90 ? w : w) * 0.7, stand(p.p, p.n, p.u)); if (dishes < 2 || a === 270 || k < 0.5) bus.add(...b.group("louvre").children); }
    attach(bus, "aft", kit.engine({exit: 0.3, kind: "chemical"}));
    for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) attach(bus, at3(sx * w * 0.42, -L / 2, sz * d * 0.42, Y.clone().negate()), kit.thrusters({size: 0.1}));
    attach(bus, {angle: 90, along: 0.95, across: 0.8}, kit.light({kind: "port", size: 0.035}));
    attach(bus, {angle: 270, along: 0.95, across: 0.8}, kit.light({kind: "starboard", size: 0.035}));
    attach(deck, at3(0, 0.08, 0, Y), kit.light({kind: "strobe", size: 0.035}));
    return bus;
  },
  // a modular station: pressurised modules round a node, a cupola under it, an airlock over it, a long truss
  // across with tracking wings and radiators, docking ports; `ring: true` adds a turning ring habitat
  station(kit, r, o) {
    const R = 2.1, core = kit.hull({radius: R, length: range(r, 9, 12), windows: {count: 8, rows: 2, from: 0.3, to: 0.7}, rails: 8, bands: 2, greebles: 0.8, stripe: 0.9});
    const node = attach(core, "fore", kit.hull({radius: R, length: 4.2, rails: 6, bands: 1, greebles: 0.4, skin: "aluminium"}), "aft");
    const labs = o.labs ?? whole(r, 1, 2);
    for (let i = 0; i < labs; i++) { const lab = attach(node, {angle: i * 180, along: 0.5}, kit.hull({radius: R * 0.9, length: range(r, 6.5, 9.5), windows: {count: 6, rows: 1, from: 0.5}, rails: 6, bands: 2, greebles: 0.7, stripe: i ? 0.85 : false}), "aft"); attach(lab, "fore", kit.dockingPort({radius: 0.8})); }
    if (labs < 2) attach(node, {angle: 180, along: 0.5}, kit.dockingPort({radius: 0.8}));
    attach(node, {angle: 270, along: 0.5}, kit.cupola({radius: 1.15}));
    attach(node, {angle: 90, along: 0.5}, kit.airlock({radius: 1.15, length: 2.4}), "mount");
    const front = attach(node, "fore", kit.hull({shape: "taper", radius: R, radius2: 1.1, length: 2.2, rails: 4}), "aft");
    attach(front, "fore", kit.dockingPort({radius: 0.9}));
    let aft = core;
    if (o.ring ?? false) aft = attach(core, "aft", kit.ringHabitat({radius: o.ringRadius ?? range(r, 16, 20), tube: 1.7, spokes: 4}), "fore");
    const service = attach(aft, "aft", kit.hull({radius: R * 0.92, length: range(r, 4.5, 6), skin: "foil", bands: 1, greebles: 1, rails: 4}), "fore");
    const tail = attach(service, "aft", kit.hull({shape: "taper", radius: R * 0.92, radius2: 1.2, length: 1.6, skin: "aluminium"}), "fore");
    attach(tail, "aft", kit.dockingPort({radius: 0.8}));
    around(service, () => kit.thrusters({size: 0.2}), {count: 4, angle: 45, along: 0.2});
    for (const a of [35, 145]) attach(service, {angle: a, along: 0.6}, kit.engine({exit: 0.28, kind: "chemical"}), "mount", {roll: 0});
    const mast = attach(core, {angle: 90, along: 0.45}, kit.truss({length: 3.2, width: 1.5}), "aft");
    const span = o.span ?? range(r, 46, 64), truss = attach(mast, "fore", kit.truss({length: span, width: 1.7}), {angle: 270, along: 0.5}, {roll: 90});
    const pairs = o.wings ?? whole(r, 1, 2), size = [range(r, 5, 6.5), range(r, 3, 3.8)], panels = whole(r, 2, 3);
    for (const s of [0, 1]) for (let k = 0; k < pairs; k++) for (const a of [0, 180]) attach(truss, {angle: a, along: s ? 0.97 - k * 0.14 : 0.03 + k * 0.14}, kit.solarWing({panels, size, yoke: 2.2}));
    for (const s of [0.34, 0.66]) attach(truss, {angle: 90, along: s}, kit.radiator({panels: 3, size: [3.2, 2.3], yoke: 0.8}), "mount", {roll: 90});
    attach(truss, {angle: 270, along: 0.58}, kit.dish({diameter: 1.8, neck: 0.8}));
    attach(truss, "fore", kit.light({kind: "port", size: 0.07})); attach(truss, "aft", kit.light({kind: "starboard", size: 0.07}));
    attach(truss, {angle: 90, along: 0.5}, kit.light({kind: "strobe", size: 0.06}));
    attach(front, {angle: 90, along: 0.5}, kit.light({kind: "dock", size: 0.05}));
    attach(core, {angle: 270, along: 0.2}, kit.antenna({kind: "helix", length: 1.4}));
    return core;
  },
  // a crewed ship: a windowed habitat with a docking nose, a truss spine carrying propellant tanks and
  // radiators, a thrust structure with a ring of engines; `ring: true` adds a turning ring habitat
  ship(kit, r, o) {
    const R = range(r, 2.3, 2.9), hab = kit.hull({radius: R, length: range(r, 8, 11), windows: {count: 10, rows: whole(r, 2, 3), from: 0.3, to: 0.75}, rails: 8, bands: 2, greebles: 0.6, stripe: 0.88});
    const nose = attach(hab, "fore", kit.hull({shape: "nose", radius: R, radius2: 0.95, length: R * 1.1, rails: 4, windows: {count: 6, from: 0.35, lit: 1, size: [0.5, 0.4]}}), "aft");
    attach(nose, "fore", kit.dockingPort({radius: 0.8}));
    attach(hab, {angle: 90, along: 0.82}, kit.cupola({radius: 1.0}));
    let last = hab;
    if (o.ring ?? r() < 0.3) last = attach(hab, "aft", kit.ringHabitat({radius: range(r, 10, 13), tube: 1.5}), "fore");
    const neck = attach(last, "aft", kit.hull({shape: "taper", radius: 1.25, radius2: R * 0.95, length: 2.2, skin: "aluminium", greebles: 0.5}), "fore");
    const L = o.spine ?? range(r, 24, 34), spine = attach(neck, "aft", kit.truss({length: L, width: 1.7}), "fore");
    const rows = whole(r, 2, 3), tr = range(r, 1.2, 1.5), tl = Math.min(L / rows * 0.78, range(r, 6, 8)), tskin = pick(r, ["foil", "paint", "foil-silver"]);
    for (let k = 0; k < rows; k++) around(spine, () => kit.tank({shape: "capsule", radius: tr, length: tl, skin: tskin}), {count: 4, angle: 0, along: (k + 0.5) / rows * 0.84 + 0.14, gap: 0.12});
    for (const a of [90, 270]) attach(spine, {angle: a, along: 0.07}, kit.radiator({panels: whole(r, 2, 3), size: [3.6, 2.6], yoke: 0.6}), "mount", {roll: 90});
    for (const a of [0, 180]) attach(neck, {angle: a, along: 0.5}, kit.solarWing({panels: 2, size: [2.4, 2.1], yoke: 1.6}));
    const base = attach(spine, "aft", kit.hull({shape: "taper", radius: R * 1.05, radius2: 1.25, length: 2.4, skin: "aluminium", greebles: 0.8, bands: 1}), "fore");
    const engines = o.engines ?? whole(r, 3, 5), re = range(r, 0.62, 0.8), ek = o.engine ?? "vacuum";
    for (let i = 0; i < engines; i++) { const a = i * TAU / engines, ring = engines === 1 ? 0 : R * 0.62; attach(base, at3(ring * Math.cos(a), -1.2, ring * Math.sin(a), Y.clone().negate()), kit.engine({exit: re, kind: ek})); }
    around(hab, () => kit.thrusters({size: 0.2}), {count: 4, angle: 45, along: 0.12});
    around(base, () => kit.thrusters({size: 0.2}), {count: 4, angle: 45, along: 0.8});
    const arm = attach(hab, {angle: 270, along: 0.25}, kit.boom({length: 2.6, radius: 0.07}));
    attach(arm, "tip", kit.dish({diameter: range(r, 2.2, 3), neck: 0.5}));
    attach(hab, {angle: 0, along: 0.5, out: 0}, kit.light({kind: "starboard", size: 0.07})); attach(hab, {angle: 180, along: 0.5}, kit.light({kind: "port", size: 0.07}));
    attach(base, {angle: 90, along: 0.4}, kit.light({kind: "strobe", size: 0.06})); attach(nose, {angle: 270, along: 0.3}, kit.light({kind: "beacon", size: 0.06}));
    return hab;
  },
  // a lander (its nose is up): a foil descent stage on four legs with tanks in its bays and one engine under
  // it, an ascent cabin with windows, a port on top
  lander(kit, r, o) {
    const R = range(r, 1.9, 2.3), H = range(r, 1.3, 1.7), stage = kit.hull({shape: "prism", sides: 8, radius: R, length: H, skin: "foil", greebles: 0.8});
    const legs = o.legs ?? 4;
    around(stage, (i) => kit.leg({length: R * 1.45, angle: 34, ladder: i === 0}), {count: legs, angle: 0, along: 0.8});
    around(stage, () => kit.tank({shape: "sphere", radius: R * 0.3, skin: pick(r, ["foil-silver", "aluminium"])}), {count: 4, angle: 45, along: 0.45, gap: -R * 0.2});
    attach(stage, "aft", kit.engine({exit: R * 0.28, length: R * 0.55, kind: o.engine ?? "chemical"}));
    const cabin = attach(stage, "fore", kit.hull({shape: "taper", radius: R * 0.68, radius2: R * 0.5, length: R * 0.95, skin: pick(r, ["paint", "aluminium"]), windows: {count: 2, from: 0.62, angle: -22, lit: 1, size: [0.52, 0.42]}, rails: 4, greebles: 0.6, bands: 1}), "aft");
    attach(cabin, "fore", kit.dockingPort({radius: R * 0.3}));
    around(cabin, () => kit.thrusters({size: 0.13}), {count: 4, angle: 45, along: 0.85});
    const arm = attach(cabin, {angle: 200, along: 0.7}, kit.boom({length: 0.9, radius: 0.04}));
    attach(arm, {angle: 90, along: 0.95}, kit.dish({diameter: R * 0.42, neck: 0.25}));
    attach(cabin, {angle: 110, along: 0.9}, kit.antenna({kind: "whip", length: 1.2}));
    attach(stage, {angle: 90, along: 0.95, out: 0}, kit.light({kind: "white", size: 0.05})); attach(cabin, {angle: 270, along: 0.95}, kit.light({kind: "beacon", size: 0.04}));
    return stage;
  },
  // a cargo tug: a small crew pod, a truss spine with rows of cargo boxes, a tank cluster and two engines
  tug(kit, r, o) {
    const pod = kit.hull({shape: "nose", radius: 1.3, radius2: 0.5, length: 2.4, windows: {count: 5, from: 0.42, lit: 1, size: [0.5, 0.38]}, rails: 3, stripe: 0.12});
    const collar = attach(pod, "aft", kit.hull({radius: 1.3, length: 1.6, greebles: 0.7, bands: 1, skin: "aluminium"}), "fore");
    const rows = o.rows ?? whole(r, 2, 4), box = [2.2, 2.2, range(r, 3.8, 4.8)], L = rows * (box[2] + 0.5) + 1, spine = attach(collar, "aft", kit.truss({length: L, width: 1.25}), "fore");
    for (let k = 0; k < rows; k++) around(spine, (i) => kit.container({size: box, skin: hash2(k, i, kit.seed) < 0.3 ? "accent" : hash2(k, i, kit.seed + 1) < 0.3 ? "aluminium" : "paint"}), {count: 4, angle: 0, along: (k + 0.5) * (box[2] + 0.5) / L + 0.5 / L, gap: 0.08, roll: 0});
    const tanks = attach(spine, "aft", kit.tankCluster({count: whole(r, 3, 4), radius: 0.95, length: 3.4, skin: "foil"}), "fore");
    const plate = attach(tanks, "aft", kit.hull({radius: 1.5, length: 0.5, skin: "aluminium", greebles: 0.5}), "fore");
    for (const s of [1, -1]) attach(plate, at3(s * 0.8, -0.25, 0, Y.clone().negate()), kit.engine({exit: 0.5, kind: o.engine ?? "chemical"}));
    for (const a of [0, 180]) attach(collar, {angle: a, along: 0.5}, kit.solarWing({panels: whole(r, 2, 3), size: [1.8, 1.5], yoke: 0.9}));
    around(collar, () => kit.thrusters({size: 0.16}), {count: 4, angle: 45, along: 0.8});
    around(plate, () => kit.thrusters({size: 0.16}), {count: 4, angle: 45, along: 0.5});
    attach(collar, {angle: 90, along: 0.4}, kit.dish({diameter: 1.3, neck: 0.4}));
    attach(pod, {angle: 0, along: 0.2}, kit.light({kind: "starboard", size: 0.05})); attach(pod, {angle: 180, along: 0.2}, kit.light({kind: "port", size: 0.05})); attach(plate, {angle: 90, along: 0.5}, kit.light({kind: "strobe", size: 0.05}));
    return pod;
  },
};
/** The ready-made craft: what each is, its options beyond the kit's, and its size (metres) for a sense of scale. */
export const CRAFT = Object.freeze({
  probe: Object.freeze({label: "a deep-space probe: foil bus, fixed high-gain dish (the nose), power units on a boom, a long magnetometer boom, a scan platform", options: ["sides", "dish", "power"], scale: "bus 2 m across, dish 2.7 to 3.7 m, 11 to 17 m between the booms' tips"}),
  satellite: Object.freeze({label: "a communications satellite: a foil box bus, two tracking wings, reflectors on arms, feed horns", options: ["panels", "dishes"], scale: "bus 2 by 2 by 3 m, 16 to 28 m across the wings"}),
  station: Object.freeze({label: "a modular station: modules round a node, a cupola, an airlock, a truss with tracking wings and radiators, docking ports", options: ["labs", "wings", "span", "ring", "ringRadius"], scale: "modules 4.2 m across, about 25 m long, the truss 46 to 64 m"}),
  ship: Object.freeze({label: "a crewed ship: windowed habitat, truss spine with propellant tanks and radiators, a ring of engines", options: ["engines", "engine", "spine", "ring"], scale: "42 to 58 m long, habitat 5 to 6 m across"}),
  lander: Object.freeze({label: "a lander (nose up): foil descent stage on four legs, one engine, an ascent cabin with windows", options: ["legs", "engine"], scale: "4 m across the stage, 7 to 9 m across the pads, 5 to 6 m tall"}),
  tug: Object.freeze({label: "a cargo tug: a crew pod, a truss spine with rows of cargo boxes, a tank cluster, two engines", options: ["rows", "engine"], scale: "19 to 32 m long, boxes 2.2 by 2.2 by 4 m"}),
});
const kindSeed = (kind) => [...kind].reduce((s, c) => (Math.imul(s, 31) + c.charCodeAt(0)) >>> 0, 7);
/** A ready-made craft: `kind` (a key of CRAFT), options {seed (1): another design of the kind for every seed;
 * the kit's (accent, foil, detail, wear, lit), the kind's own (CRAFT[kind].options), and a craft's (occlusion,
 * camera, height, sun, target, lights, name)}. Returns a Craft. */
export function craft(kind, options = {}) {
  if (!DESIGNS[kind]) throw fail(`no craft "${kind}"${hint(kind, Object.keys(CRAFT))}; craft: ${Object.keys(CRAFT).join(", ")}`);
  const own = CRAFT[kind].options, kitKeys = Object.keys(KIT_DEFAULTS), craftKeys = Object.keys(CRAFT_DEFAULTS).filter((k) => !["fore", "kind"].includes(k));
  known(`craft("${kind}") options`, options, [...new Set([...kitKeys, ...own, ...craftKeys])]);
  const seed = options.seed ?? 1, sub = (keys) => Object.fromEntries(Object.entries(options).filter(([k]) => keys.includes(k)));
  const kit = new CraftKit({...sub(kitKeys), seed}), r = rng((seed * 2654435761 + kindSeed(kind)) >>> 0);
  return new Craft(DESIGNS[kind](kit, r, sub(own)), kit, {...sub(craftKeys), name: `${kind} ${seed}`, kind, seed});
}
/** A fleet without designing each: `count` craft of `kind` (or of the kinds in a list, in turn) with seeds seed,
 * seed + 1, ..., standing in a loose seeded formation `spacing` metres apart (default 2.5 times the first one's
 * radius). Options: count (5), seed (1), spacing, detail ("far"), and anything craft() takes. Returns {object (a
 * group holding them), craft (the list), update(t, options): every craft's update}. */
export function fleet(kind, options = {}) {
  const {count = 5, seed = 1, spacing = null, detail = "far", ...rest} = options, kinds = Array.isArray(kind) ? kind : [kind];
  const list = Array.from({length: count}, (_, i) => craft(kinds[i % kinds.length], {...rest, detail, seed: seed + i})), r = rng(seed * 613 + 17), object = new THREE.Group();
  const step = spacing ?? 2.5 * list[0].size.radius;
  list.forEach((c, i) => { const row = Math.floor((i + 1) / 2), side = i === 0 ? 0 : i % 2 ? 1 : -1; c.object.position.set(side * row * step * (0.9 + 0.2 * r()), (r() - 0.5) * step * 0.5, -row * step * (0.7 + 0.3 * r())); object.add(c.object); });
  object.name = "fleet";
  return {object, craft: list, update(t, o = {}) { for (const c of list) c.update(t, o); return this; }, dispose() { for (const c of list) c.dispose(); }};
}
/** Reflections without a scene to mirror: a painted environment for `scene.environment`: a faint sky (`sky`:
 * a linear colour) and up to four `worlds`, each a soft disc {direction: [x, y, z] towards it, angle (its
 * radius in degrees), color (linear, what its day side shows)}; default one blue-white world filling the sky
 * below. For a craft far from any world (worlds: []), a test shot, a contact sheet. Returns {texture, dispose()}. */
export function paintedEnvironment(renderer, options = {}) {
  known("paintedEnvironment options", options, ["sky", "worlds", "size"]);
  const worlds = options.worlds ?? [{direction: [0, -1, 0], angle: 72, color: [0.2, 0.3, 0.5]}], sky = options.sky ?? [0.006, 0.007, 0.01];
  if (worlds.length > 4) throw fail("paintedEnvironment: at most 4 worlds");
  for (const w of worlds) known("a painted world", w, ["direction", "angle", "color"]);
  const pad = (make, empty) => Array.from({length: 4}, (_, i) => (worlds[i] ? make(worlds[i]) : empty));
  const material = new THREE.ShaderMaterial({side: THREE.BackSide, depthTest: false, depthWrite: false, toneMapped: false,
    uniforms: {uSky: {value: V3(...sky)}, uDir: {value: pad((w) => new THREE.Vector4(...V3(...w.direction).normalize().toArray(), Math.cos((w.angle ?? 60) * RAD)), new THREE.Vector4(0, 1, 0, 2))}, uColor: {value: pad((w) => V3(...(w.color ?? [0.2, 0.3, 0.5])), V3())}},
    vertexShader: "varying vec3 vDir; void main() { vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: `precision highp float; varying vec3 vDir; uniform vec3 uSky; uniform vec4 uDir[4]; uniform vec3 uColor[4];
      void main() { vec3 d = normalize(vDir), c = uSky;
        for (int i = 0; i < 4; i++) { float k = dot(d, uDir[i].xyz), e = smoothstep(uDir[i].w - 0.03, uDir[i].w + 0.03, k); c = mix(c, uColor[i] * (0.55 + 0.45 * smoothstep(uDir[i].w, 1.0, k)), e); }
        gl_FragColor = vec4(c, 1.0); }`});
  const scene = new THREE.Scene(), ball = new THREE.Mesh(new THREE.SphereGeometry(10, 24, 12), material), target = new THREE.WebGLCubeRenderTarget(options.size ?? 64, {type: THREE.HalfFloatType});
  scene.add(ball);
  const camera = new THREE.CubeCamera(0.1, 100, target), pmrem = new THREE.PMREMGenerator(renderer), before = renderer.getRenderTarget();
  camera.update(renderer, scene); renderer.setRenderTarget(before);
  const made = pmrem.fromCubemap(target.texture);
  target.dispose(); pmrem.dispose(); material.dispose(); ball.geometry.dispose();
  return {texture: made.texture, dispose() { made.dispose(); }};
}
