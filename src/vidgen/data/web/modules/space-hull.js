// vidgen/space-hull: hulls of giant ships, 0.5 to 10 km long. Part of schu-video-generator
// (MIT licence); imported by a page as "vidgen/space-hull". It builds on the kit of vidgen/space-craft.
//
//   import {hull, hullFleet} from "vidgen/space-hull";
//   const ship = hull("carrier", {seed: 4, length: 3000});   // a family of HULLS (spine, carrier, cluster, lance,
//                                                            // wheel, ark, twin), another member for every seed
//   scene.add(ship.object);                                  // metres; +z the bow, +y up, +x port; its middle at the origin
//   ship.fly(space, {body: "Ship"});                         // a body of ctx.orbits (vidgen/space-craft's fly)
//   ship.update(t, {sun, throttle: 0.6});                    // bells fire, rings turn, lights blink
//   ship.scaleRef("ship", {at: "hangar-1"});                 // a 50 m craft of the kit beside a named place: a sense of size
//   ship.problems()                                          // what looks wrong (buried bells, absurd proportions, ...)
//
// These are the large forms only: masses that read in silhouette and under one hard sun, with big plates of
// their own tone, real recesses and hangar mouths as dark voids. For the fine detail a hull carries a contract:
// `regions` (named, with a box, an outward direction and what the surface is), `anchors`
// (bells, hangar mouths, docks, lights, the command place), `charts` (every large face's place in one atlas,
// with its metres per texel; the meshes' `uv1`) and `uv` in metres.
//
// The designs are invented, with a language of their own: every function is a mass of its own (crew, propellant,
// cargo, heat, drive) joined by visible structure; one long axis, because thrust loads run along it; radiators
// are the largest surfaces; nothing is streamlined, because these ships never meet air: bows are blunt faces,
// frames, shields or rings; a ship is lopsided where its work asks for it; command sits inside the hull, never
// on a tower. No film, game or book ship is copied. Nothing is random at draw time: a hull is a function of its
// family, seed and options.
import * as THREE from "three";
import {rng} from "vidgen/music-time";
import {CraftKit, Craft, GLARE, ACCENTS, platingMaps, craft as kitCraft} from "vidgen/space-craft";

export const VERSION = 2;
const PREFIX = "vidgen/space-hull";
const TAU = Math.PI * 2, RAD = Math.PI / 180;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const mix = (a, b, u) => a + (b - a) * u;
const smooth = (a, b, x) => { const u = clamp((x - a) / (b - a)); return u * u * (3 - 2 * u); };
const V3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const X = V3(1, 0, 0), Y = V3(0, 1, 0), Z = V3(0, 0, 1), I = new THREE.Matrix4();
const fail = (message) => new Error(`${PREFIX}: ${message}`);
function distance(a, b) {
  const d = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = d[0]; d[0] = i;
    for (let j = 1; j <= b.length; j++) { const cur = d[j]; d[j] = Math.min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = cur; }
  }
  return d[b.length];
}
function hint(key, names) {
  const best = names.map((k) => [distance(String(key).toLowerCase(), k.toLowerCase()), k]).sort((x, y) => x[0] - y[0])[0];
  return best && best[0] <= Math.max(2, String(key).length / 3) ? ` (did you mean "${best[1]}"?)` : "";
}
function known(where, object, keys) {
  if (object === null || typeof object !== "object" || Array.isArray(object)) throw fail(`${where} must be an object, got ${JSON.stringify(object)}`);
  for (const k of Object.keys(object)) if (!keys.includes(k)) throw fail(`${where}: unknown option "${k}"${hint(k, keys)}; options: ${keys.join(", ")}`);
}
function choice(where, value, choices) {
  if (!choices.includes(value)) throw fail(`${where}: "${value}"${hint(String(value), choices)}; one of: ${choices.join(", ")}`);
  return value;
}
function number(where, value, lo, hi) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < lo || value > hi) throw fail(`${where} must be a number from ${lo} to ${hi}, got ${JSON.stringify(value)}`);
  return value;
}
const hash1 = (x, k = 0) => { let h = Math.imul(x | 0, 374761393) ^ Math.imul(k | 0, 1274126177); h = Math.imul(h ^ (h >>> 13), 1103515245); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
const hash3 = (x, y, z, k = 0) => hash1(Math.imul(x | 0, 73856093) ^ Math.imul(y | 0, 19349663) ^ Math.imul(z | 0, 83492791), k);
// smooth noise in space, 0..1, and four octaves of it: the same on every machine
function noise3(x, y, z, k = 0) {
  const ix = Math.floor(x), iy = Math.floor(y), iz = Math.floor(z), f = (u) => u * u * (3 - 2 * u), fx = f(x - ix), fy = f(y - iy), fz = f(z - iz);
  const c = (a, b, d) => hash3(ix + a, iy + b, iz + d, k);
  return mix(mix(mix(c(0, 0, 0), c(1, 0, 0), fx), mix(c(0, 1, 0), c(1, 1, 0), fx), fy), mix(mix(c(0, 0, 1), c(1, 0, 1), fx), mix(c(0, 1, 1), c(1, 1, 1), fx), fy), fz);
}
const fbm = (x, y, z, k = 0) => (noise3(x, y, z, k) + 0.5 * noise3(2 * x, 2 * y, 2 * z, k + 1) + 0.25 * noise3(4 * x, 4 * y, 4 * z, k + 2) + 0.125 * noise3(8 * x, 8 * y, 8 * z, k + 3)) / 1.875;
const pick = (r, list) => list[Math.min(list.length - 1, Math.floor(r() * list.length))];
const range = (r, a, b) => a + (b - a) * r();
const whole = (r, a, b) => a + Math.min(b - a, Math.floor(r() * (b - a + 1)));
const round = (x, step = 0.001) => Math.round(x / step) * step;
const arr = (v) => [v.x, v.y, v.z];

// ---------- the atlas: every large face has a rectangle of its own ----------
/** Lay `charts` ([{size: [w, h] metres, weight}]) into the unit square without overlap, each as large as the
 * common scale allows (shelves, the long side lying; a chart longer than the square is drawn smaller, by itself).
 * Sets each chart's `rect` ([u0, v0, u1, v1]), `turned` (its w runs along v) and `scale` (atlas units per
 * metre); the corner under `reserve` is left free. Returns the common scale. `pad`: the gap between charts. */
export function packCharts(charts, pad = 1 / 512, reserve = 4 / 512) {
  const order = charts.map((c, i) => i).sort((a, b) => Math.min(...charts[b].size) * (charts[b].weight ?? 1) - Math.min(...charts[a].size) * (charts[a].weight ?? 1) || a - b);
  const lay = (s, write) => {
    let x = pad, y = reserve + pad, shelf = 0;
    for (const i of order) {
      const c = charts[i], long = Math.max(...c.size), short = Math.min(...c.size), k = Math.min(s * (c.weight ?? 1), (1 - 2 * pad) / long), pw = long * k, ph = short * k;
      if (x + pw + pad > 1) { x = pad; y += shelf + pad; shelf = 0; }
      if (y + ph + pad > 1) return false;
      if (write) { c.rect = [x, y, x + pw, y + ph]; c.turned = c.size[1] > c.size[0]; c.scale = k; }
      x += pw + pad; shelf = Math.max(shelf, ph);
    }
    return true;
  };
  if (!charts.length) return 0;
  let lo = 0, hi = 1 / Math.max(1e-9, Math.min(...charts.map((c) => Math.min(...c.size) * (c.weight ?? 1))));
  for (let n = 0; n < 40; n++) { const mid = 0.5 * (lo + hi); if (lay(mid, false)) lo = mid; else hi = mid; }
  lay(lo, true);
  return lo;
}

// ---------- surfaces ----------
/** The hull colours a seed chooses from: two hull tones and a dark metal (one accent comes from the kit). */
export const PALETTES = Object.freeze({
  bone: Object.freeze({a: 0xcfcbc2, b: 0x9c9da0, c: 0x3a3d42}),
  slate: Object.freeze({a: 0x9299a2, b: 0x6b717a, c: 0x2b2e33}),
  iron: Object.freeze({a: 0x74777c, b: 0x54575c, c: 0x232528}),
  sand: Object.freeze({a: 0xc6bba8, b: 0x928a7d, c: 0x38352f}),
  frost: Object.freeze({a: 0xd6dadf, b: 0x9da6b1, c: 0x363c45}),
});
/** The named surfaces of a hull (`kit.materials[name]`). */
export const HULL_SKINS = Object.freeze(["hull-a", "hull-b", "hull-c", "hull-accent", "hull-radiator", "hull-tank", "hull-truss", "hull-rock", "hull-void", "hull-glass"]);
/** What a region's surface is, for whoever adds the fine detail: `material` (what it is made of), `expects`
 * (the detail that belongs there) and `density` (its share of the atlas's texels per metre). */
export const SURFACES = Object.freeze({
  plating: Object.freeze({material: "painted hull plate", expects: "panel lines, hatches, pipe runs, a few lit ports", density: 1}),
  windows: Object.freeze({material: "painted hull plate over crew decks", expects: "rows of windows by the thousand, some lit", density: 1.4}),
  hangar: Object.freeze({material: "dark recess", expects: "a lit bay: floor markings, parked craft, door frames", density: 1.6}),
  trench: Object.freeze({material: "dark metal", expects: "pipe runs, gantries, lights along the walls", density: 1.2}),
  radiator: Object.freeze({material: "white radiator panels", expects: "panel grid, feed pipes at the root, a dull glow when hot", density: 0.35}),
  engine: Object.freeze({material: "dark metal thrust structure", expects: "manifolds, gimbal frames, heat stains, the bells' glow", density: 0.8}),
  tank: Object.freeze({material: "insulated propellant tank", expects: "bands, feed lines, frost marks", density: 0.5}),
  cargo: Object.freeze({material: "painted containers and frames", expects: "container grid, numbers, a few missing boxes", density: 0.8}),
  shield: Object.freeze({material: "layered shield plate", expects: "concentric rings, impact pits", density: 0.4}),
  rock: Object.freeze({material: "rock", expects: "craters, cut terraces, drill mouths, lights of built structure", density: 0.45}),
  dock: Object.freeze({material: "painted hull plate", expects: "docking collars, guide lights, markings", density: 1.4}),
  truss: Object.freeze({material: "open truss", expects: "nothing baked: struts are geometry", density: 0}),
});
const TEXTURES = new Map();
function tiled(name, tile, make) {
  if (!TEXTURES.has(name)) TEXTURES.set(name, make());
  const key = `${name}|${tile}`;
  if (!TEXTURES.has(key)) {
    const m = TEXTURES.get(name), one = (data, srgb) => {
      const t = new THREE.DataTexture(data, m.size, m.size, THREE.RGBAFormat);
      t.wrapS = t.wrapT = THREE.RepeatWrapping; t.magFilter = THREE.LinearFilter; t.minFilter = THREE.LinearMipmapLinearFilter; t.generateMipmaps = true; t.anisotropy = 2; t.repeat.set(1 / tile, 1 / tile);
      if (srgb) t.colorSpace = THREE.SRGBColorSpace;
      t.needsUpdate = true;
      return t;
    };
    TEXTURES.set(key, {map: one(m.albedo, true), normalMap: one(m.normal, false), roughnessMap: one(m.orm, false)});
  }
  return TEXTURES.get(key);
}
/** Rock, as numbers: {albedo, normal, orm, size}: four octaves of smooth noise, tiling, with pits. */
export function rockMaps(size = 256, seed = 1) {
  const h = new Float32Array(size * size), per = 8, at = (x, y) => h[((y + size) % size) * size + ((x + size) % size)];
  const wrap = (x, y, f, k) => { const p = per * f, ix = Math.floor(x * p), iy = Math.floor(y * p), fx = x * p - ix, fy = y * p - iy, s = (u) => u * u * (3 - 2 * u), c = (a, b) => hash3((ix + a) % p, (iy + b) % p, f, seed + k); return mix(mix(c(0, 0), c(1, 0), s(fx)), mix(c(0, 1), c(1, 1), s(fx)), s(fy)); };
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) { const u = x / size, v = y / size; h[y * size + x] = wrap(u, v, 1, 0) + 0.5 * wrap(u, v, 2, 1) + 0.28 * Math.abs(2 * wrap(u, v, 4, 2) - 1) + 0.14 * wrap(u, v, 8, 3); }
  const albedo = new Uint8Array(size * size * 4), normal = new Uint8Array(size * size * 4), orm = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const k = 4 * (y * size + x), dx = (at(x + 1, y) - at(x - 1, y)) * 9, dy = (at(x, y + 1) - at(x, y - 1)) * 9, l = 1 / Math.hypot(dx, dy, 1), c = clamp(0.62 + 0.3 * at(x, y) / 1.9) * 255;
    albedo.set([c, c, c, 255], k); normal.set([127.5 - dx * l * 127.5, 127.5 - dy * l * 127.5, 127.5 + l * 127.5, 255], k); orm.set([255, 235, 255, 255], k);
  }
  return {albedo, normal, orm, size};
}
const MAPS = {
  plates: () => ({...platingMaps(512, {seed: 31, depth: 6, rivets: false, pillow: 0.2, tone: 0.045, specks: 0, groove: 0.4}), size: 512}),
  grid: () => ({...platingMaps(256, {seed: 32, tiles: 6, rivets: false, pillow: 0.15, tone: 0.05, specks: 0, groove: 1}), size: 256}),
  rock: () => rockMaps(256, 7),
};
function capGlare(shader) {
  shader.uniforms.uGlareCap = GLARE;
  shader.fragmentShader = shader.fragmentShader.replace("void main() {", "uniform float uGlareCap;\nvoid main() {")
    .replace("#include <lights_fragment_end>", "#include <lights_fragment_end>\nreflectedLight.directSpecular = min(reflectedLight.directSpecular, vec3(uGlareCap));");
}
function hullMaterials(kit, {palette, tile, wear}) {
  const p = PALETTES[palette];
  const std = (o, maps = null, scale = 1) => {
    const m = new THREE.MeshStandardMaterial({vertexColors: true, ...o});
    if (maps) { m.map = maps.map; m.normalMap = maps.normalMap; m.normalScale = new THREE.Vector2(scale, scale); m.roughnessMap = maps.roughnessMap; }
    m.onBeforeCompile = capGlare; m.customProgramCacheKey = () => "vidgen-hull";
    return m;
  };
  const plates = tiled("plates", tile, MAPS.plates), grid = tiled("grid", tile * 0.5, MAPS.grid), rock = tiled("rock", tile * 2.5, MAPS.rock);
  const M = {"hull-a": std({color: p.a, roughness: 0.95, metalness: 0.05}, plates, 0.9 * wear), "hull-b": std({color: p.b, roughness: 0.95, metalness: 0.08}, plates, 0.9 * wear),
    "hull-c": std({color: p.c, roughness: 0.75, metalness: 0.55}, plates, 0.7 * wear), "hull-accent": std({color: kit.accent, roughness: 0.9, metalness: 0.05}, plates, 0.6 * wear),
    "hull-radiator": std({color: 0xdcdcd8, roughness: 0.8, metalness: 0.05}, grid, 0.5), "hull-tank": std({color: 0xbfc2c6, roughness: 0.62, metalness: 0.55}, grid, 0.35),
    "hull-truss": std({color: p.c, roughness: 0.6, metalness: 0.6}), "hull-rock": std({color: 0x6f675d, roughness: 1, metalness: 0}, rock, 1.6),
    "hull-void": std({color: 0x07080a, roughness: 1, metalness: 0}), "hull-glass": std({color: 0x0a0d12, roughness: 0.08, metalness: 0.9})};
  for (const [name, m] of Object.entries(M)) { m.name = name; m.envMapIntensity = 1; }
  return M;
}

// ---------- geometry: faces go into one bucket per part and surface; charts and regions are kept beside ----------
const st = (z, s = 1, o = [0, 0]) => ({z, s: typeof s === "number" ? [s, s] : s, o});
/** A rectangle w by h with its corners cut by c, as a polygon (counter-clockwise seen from +z). */
export const rect = (w, h, c = 0) => (c > 0 ? [[-w / 2 + c, -h / 2], [w / 2 - c, -h / 2], [w / 2, -h / 2 + c], [w / 2, h / 2 - c], [w / 2 - c, h / 2], [-w / 2 + c, h / 2], [-w / 2, h / 2 - c], [-w / 2, -h / 2 + c]]
  : [[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]]);
const ngon = (r, n, turn = 0.5) => Array.from({length: n}, (_, i) => { const a = (i + turn) * TAU / n; return [r * Math.cos(a), r * Math.sin(a)]; });
/** A hull's cross-section with real recesses: a rectangle W by H (corners cut by c) with a `trench` ({w, d}:
 * a slot in its top) and `slots` ([{side: 1 port | -1 starboard, y0, y1, d}]: slots in its sides). Returns
 * {poly, tags}: the polygon and, for the edge starting at each point, what it is (bottom, top, port, starboard,
 * chamfer, wall, floor, slot, back). */
export function sectionOf(W, H, c, {trench = null, slots = []} = {}) {
  const poly = [], tags = [], add = (x, y, tag) => { poly.push([x, y]); tags.push(tag); };
  const side = (s) => slots.find((q) => q.side === s);
  add(-W / 2 + c, -H / 2, "bottom"); add(W / 2 - c, -H / 2, "chamfer"); add(W / 2, -H / 2 + c, "port");
  const p = side(1);
  if (p) { add(W / 2, p.y0, "slot"); add(W / 2 - p.d, p.y0, "back"); add(W / 2 - p.d, p.y1, "slot"); add(W / 2, p.y1, "port"); }
  add(W / 2, H / 2 - c, "chamfer"); add(W / 2 - c, H / 2, "top");
  if (trench) { add(trench.w / 2, H / 2, "wall"); add(trench.w / 2, H / 2 - trench.d, "floor"); add(-trench.w / 2, H / 2 - trench.d, "wall"); add(-trench.w / 2, H / 2, "top"); }
  add(-W / 2 + c, H / 2, "chamfer"); add(-W / 2, H / 2 - c, "starboard");
  const s = side(-1);
  if (s) { add(-W / 2, s.y1, "slot"); add(-W / 2 + s.d, s.y1, "back"); add(-W / 2 + s.d, s.y0, "slot"); add(-W / 2, s.y0, "starboard"); }
  add(-W / 2, -H / 2 + c, "chamfer");
  return {poly, tags};
}
const basis = (x, y, z, p = V3()) => new THREE.Matrix4().makeBasis(x, y, z).setPosition(p);
const move = (x, y, z) => new THREE.Matrix4().makeTranslation(x, y, z);

/** What a hull is built in: faces in metres in the hull's axes (+z the bow, +y up, +x port), collected by part
 * (`part(name, flags)`: a mass of its own; {sparse: an open or thin thing, left out of the shadow balls and the
 * profile; spin: radians a second round +z}) and
 * region (`region(name, detail)`: a named place for the fine detail, `detail` a key of SURFACES). Shapes:
 * loft (a polygon carried through stations), lathe (a profile turned round an axis), block, drum, capsule,
 * ball, rod, truss, vane, dish, mouth, rock. Every face wider than `minChart` gets a chart in the atlas. */
export class Shell {
  constructor(kit, options = {}) {
    this.kit = kit; this.far = kit.far; this.plate = options.plate ?? 70; this.minChart = options.minChart ?? 14; this.count = 0; this.weather = null;
    this.buckets = new Map(); this.parts = new Map(); this.regions = new Map(); this.charts = []; this.extra = [];
    this.now = {part: null, region: null};
    this.part("hull").region("midship");
  }
  part(name, flags = {}) { if (!this.parts.has(name)) this.parts.set(name, {name, ...flags}); this.now.part = this.parts.get(name); return this; }
  region(name, detail = "plating") {
    choice("a region's detail", detail, Object.keys(SURFACES));
    if (!this.regions.has(name)) this.regions.set(name, {name, detail, box: new THREE.Box3(), sum: V3(), area: 0, charts: [], skins: new Map()});
    this.now.region = this.regions.get(name);
    return this;
  }
  _bucket(skin) {
    if (!this.kit.materials[skin]) throw fail(`no surface "${skin}"${hint(skin, HULL_SKINS)}; surfaces: ${HULL_SKINS.join(", ")}`);
    const key = `${this.now.part.name}|${skin}`;
    if (!this.buckets.has(key)) this.buckets.set(key, {part: this.now.part, skin, pos: [], nor: [], uv: [], cuv: [], col: []});
    return this.buckets.get(key);
  }
  // a face of three or four corners P (counter-clockwise from outside), normals N (one or one each), chart places C
  _face(skin, region, P, N, C, chart, off, tone) {
    const b = this._bucket(skin), w = skin === "hull-void" ? null : this.weather, rgb = Array.isArray(tone);
    for (const i of P.length === 4 ? [0, 1, 2, 0, 2, 3] : [0, 1, 2]) {
      const p = P[i], n = N.isVector3 ? N : N[i], k = w ? w(p) : 1;
      b.pos.push(p.x, p.y, p.z); b.nor.push(n.x, n.y, n.z); b.uv.push(C[i][0] + off[0], C[i][1] + off[1]); b.cuv.push(chart, C[i][0], C[i][1]);
      if (rgb) b.col.push(tone[0] * k, tone[1] * k, tone[2] * k); else b.col.push(tone * k, tone * k, tone * k);
    }
    if (region) {
      const cr = V3().subVectors(P[1], P[0]).cross(V3().subVectors(P[P.length - 1], P[0])), a = cr.length() * (P.length === 4 ? 1 : 0.5);
      for (const p of P) region.box.expandByPoint(p);
      region.sum.addScaledVector(N.isVector3 ? N : N[0], a); region.area += a; region.skins.set(skin, (region.skins.get(skin) ?? 0) + a);
    }
  }
  _chart(region, name, w, h, frame, kind = "plane") {
    const density = SURFACES[region.detail].density;
    if (!(density > 0) || Math.min(w, h) < this.minChart) return -1;
    const id = this.charts.length;
    this.charts.push({id, name: `${region.name}/${name}`, region: region.name, kind, size: [w, h], weight: density, ...frame});
    region.charts.push(id);
    return id;
  }

  /** Carry the polygon `poly` ([[x, y], ...], counter-clockwise seen from +z) through `stations` ([{z, s: its
   * scale or [sx, sy], o: [x, y] its offset}], z rising): a prism, a taper, a bevelled block. Options: `at` (a
   * Matrix4 standing it in the hull), `edge` ((i) => {skin, region, name} | false for the faces of edge i),
   * `caps` ([first, last]: close the ends), `cap` (the ends' surface), `tone` (how far the big plates differ),
   * `tint` ([r, g, b] | (p) => [r, g, b]), `plates` (false: one plate per face). */
  loft(skin, poly, stations, o = {}) {
    const at = o.at ?? I, n = poly.length, id = this.count++, off = [hash1(id, 1) * 311, hash1(id, 2) * 311], amount = o.tone ?? 0.035, plate = this.far || o.plates === false ? 1e9 : this.plate;
    const pts = stations.map((s) => poly.map((q) => V3(s.o[0] + q[0] * s.s[0], s.o[1] + q[1] * s.s[1], s.z).applyMatrix4(at)));
    const tint = (p, t) => { const c = typeof o.tint === "function" ? o.tint(p) : o.tint; return c ? [c[0] * t, c[1] * t, c[2] * t] : t; };
    const here = this.now.region;
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n, e = o.edge ? o.edge(i) : null;
      if (e === false) continue;
      const sk = (e && e.skin) ?? skin, region = e && e.region ? this.regions.get(e.region) ?? this.region(e.region, e.detail).now.region : here;
      this.now.region = here;
      const lens = pts.map((ring) => ring[i].distanceTo(ring[j])), mids = pts.map((ring) => ring[i].clone().add(ring[j]).multiplyScalar(0.5)), cum = [0];
      for (let k = 1; k < pts.length; k++) cum.push(cum[k - 1] + mids[k].distanceTo(mids[k - 1]));
      const w = Math.max(...lens), h = cum[cum.length - 1];
      if (w < 1e-6 || h < 1e-6) continue;
      let best = 0, frame = null;
      const faces = [];
      for (let k = 0; k < pts.length - 1; k++) {
        const A = pts[k][i], B = pts[k][j], C = pts[k + 1][j], D = pts[k + 1][i], nrm = V3().subVectors(lens[k] > 1e-6 ? B : C, A).cross(V3().subVectors(D, A));
        const size = nrm.length();
        if (size < 1e-9) continue;
        nrm.divideScalar(size);
        const c = [[w / 2 - lens[k] / 2, cum[k]], [w / 2 + lens[k] / 2, cum[k]], [w / 2 + lens[k + 1] / 2, cum[k + 1]], [w / 2 - lens[k + 1] / 2, cum[k + 1]]];
        faces.push({P: [A, B, C, D], nrm, c, k});
        if (size > best && lens[k] > 1e-6) { best = size; const du = V3().subVectors(B, A).normalize(), dv = V3().crossVectors(nrm, du); frame = {origin: A.clone().addScaledVector(du, -c[0][0]).addScaledVector(dv, -c[0][1]), du, dv, normal: nrm.clone()}; }
      }
      const chart = frame && o.chart !== false ? this._chart(region, (e && e.name) ?? `side ${i}`, w, h, frame) : -1;
      for (const f of faces) {
        const nu = Math.max(1, Math.round(Math.max(lens[f.k], lens[f.k + 1]) / plate)), nv = Math.max(1, Math.round((cum[f.k + 1] - cum[f.k]) / plate));
        const at2 = (u, v, P4) => P4[0].clone().lerp(P4[1], u).lerp(P4[3].clone().lerp(P4[2], u), v), uv2 = (u, v) => [mix(mix(f.c[0][0], f.c[1][0], u), mix(f.c[3][0], f.c[2][0], u), v), mix(f.c[0][1], f.c[3][1], v)];
        for (let a = 0; a < nu; a++) for (let b = 0; b < nv; b++) {
          const u0 = a / nu, u1 = (a + 1) / nu, v0 = b / nv, v1 = (b + 1) / nv, P = [at2(u0, v0, f.P), at2(u1, v0, f.P), at2(u1, v1, f.P), at2(u0, v1, f.P)];
          const t = 1 + amount * (2 * hash3(id, i * 64 + f.k, a * 257 + b, this.kit.seed) - 1) * (hash3(id + 9, i * 64 + f.k, a * 257 + b, this.kit.seed) < 0.1 ? 2.2 : 1);
          this._face(sk, region, P, f.nrm, [uv2(u0, v0), uv2(u1, v0), uv2(u1, v1), uv2(u0, v1)], chart, off, tint(P[0], t));
        }
      }
    }
    const caps = o.caps ?? [true, true];
    for (const [end, k, sign] of [[0, 0, -1], [1, stations.length - 1, 1]]) {
      const s = stations[k];
      if (!caps[end] || Math.abs(s.s[0] * s.s[1]) < 1e-9) continue;
      const flat = poly.map((q) => new THREE.Vector2(q[0] * s.s[0], q[1] * s.s[1])), tris = THREE.ShapeUtils.triangulateShape(flat, []), nrm = V3(0, 0, sign).transformDirection(at);
      const xs = flat.map((q) => q.x), ys = flat.map((q) => q.y), x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      const cu = (q) => (sign > 0 ? q.x - x0 : x1 - q.x), du = V3(sign, 0, 0).transformDirection(at), dv = V3(0, 1, 0).transformDirection(at);
      const origin = V3(s.o[0] + (sign > 0 ? x0 : x1), s.o[1] + y0, s.z).applyMatrix4(at), sk = (o.cap && o.cap.skin) ?? skin, region = o.cap && o.cap.region ? this.region(o.cap.region, o.cap.detail).now.region : here;
      this.now.region = here;
      const chart = o.chart !== false ? this._chart(region, sign > 0 ? "fore face" : "aft face", x1 - x0, y1 - y0, {origin, du, dv, normal: nrm}) : -1;
      for (const [a, b, c] of tris) {
        const P = [a, b, c].map((v) => pts[k][v]), order = V3().subVectors(P[1], P[0]).cross(V3().subVectors(P[2], P[0])).dot(nrm) >= 0 ? [0, 1, 2] : [0, 2, 1], F = [a, b, c].map((v) => flat[v]);
        this._face(sk, region, order.map((v) => P[v]), nrm, order.map((v) => [cu(F[v]), F[v].y - y0]), chart, off, tint(P[0], 1 - 0.5 * amount));
      }
    }
    return this;
  }

  /** Turn the profile `profile` ([[r, z], ...]; z rising gives a wall that faces out) round +z. Options: `at`,
   * `sides`, `facet` (flat sides: a polygon, not a round), `smooth` (no creases along the profile: a ball, a
   * tank's end), `tone`, `tint`, `name`. One chart: u round, v along the profile. */
  lathe(skin, profile, o = {}) {
    const at = o.at ?? I, sides = Math.max(6, this.far && !o.facet ? Math.round((o.sides ?? 24) / 2) : (o.sides ?? 24)), id = this.count++, off = [hash1(id, 1) * 311, hash1(id, 2) * 311], amount = o.tone ?? 0.035, region = this.now.region;
    const rmax = Math.max(...profile.map((q) => q[0])), plate = this.far ? 1e9 : this.plate, prof = [profile[0]];
    for (let k = 1; k < profile.length; k++) { const a = profile[k - 1], b = profile[k], m = o.smooth ? 1 : Math.max(1, Math.min(8, Math.round(Math.hypot(b[0] - a[0], b[1] - a[1]) / plate))); for (let q = 1; q <= m; q++) prof.push([mix(a[0], b[0], q / m), mix(a[1], b[1], q / m)]); }
    const cum = [0];
    for (let k = 1; k < prof.length; k++) cum.push(cum[k - 1] + Math.hypot(prof[k][0] - prof[k - 1][0], prof[k][1] - prof[k - 1][1]));
    const w = TAU * rmax, h = cum[cum.length - 1], turn = o.turn ?? 0, ang = (j) => (j + turn) * TAU / sides;
    const chart = o.chart !== false ? this._chart(region, o.name ?? "round", w, h, {origin: V3(0, 0, prof[0][1]).applyMatrix4(at), axis: V3(0, 0, 1).transformDirection(at), radius: rmax}, "round") : -1;
    const seg = prof.slice(1).map((b, k) => { const a = prof[k], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1; return [(b[1] - a[1]) / l, -(b[0] - a[0]) / l]; });
    const vn = prof.map((_, k) => { const a = seg[Math.max(0, k - 1)], b = seg[Math.min(seg.length - 1, k)], l = Math.hypot(a[0] + b[0], a[1] + b[1]) || 1; return [(a[0] + b[0]) / l, (a[1] + b[1]) / l]; });
    const P = (k, a) => V3(prof[k][0] * Math.cos(a), prof[k][0] * Math.sin(a), prof[k][1]).applyMatrix4(at), N = (q, a) => V3(q[0] * Math.cos(a), q[0] * Math.sin(a), q[1]).transformDirection(at);
    for (let k = 0; k < prof.length - 1; k++) for (let j = 0; j < sides; j++) {
      const a0 = ang(j), a1 = ang(j + 1), am = 0.5 * (a0 + a1), A = P(k, a0), B = P(k, a1), C = P(k + 1, a1), D = P(k + 1, a0);
      if (prof[k][0] < 1e-6 && prof[k + 1][0] < 1e-6) continue;
      const nrm = o.facet ? N(seg[k], am) : o.smooth ? [N(vn[k], a0), N(vn[k], a1), N(vn[k + 1], a1), N(vn[k + 1], a0)] : [N(seg[k], a0), N(seg[k], a1), N(seg[k], a1), N(seg[k], a0)];
      const t = 1 + amount * (2 * hash3(id, k, j, this.kit.seed) - 1), c = [[j / sides * w, cum[k]], [(j + 1) / sides * w, cum[k]], [(j + 1) / sides * w, cum[k + 1]], [j / sides * w, cum[k + 1]]];
      const tone = typeof o.tint === "function" ? o.tint(A).map((v) => v * t) : o.tint ? o.tint.map((v) => v * t) : t;
      if (prof[k][0] < 1e-6) this._face(skin, region, [A, C, D], o.facet ? nrm : [nrm[0], nrm[2], nrm[3]], [c[0], c[2], c[3]], chart, off, tone);
      else if (prof[k + 1][0] < 1e-6) this._face(skin, region, [A, B, C], o.facet ? nrm : [nrm[0], nrm[1], nrm[2]], [c[0], c[1], c[2]], chart, off, tone);
      else this._face(skin, region, [A, B, C, D], nrm, c, chart, off, tone);
    }
    return this;
  }

  /** A block w by h by d (d along z) with its long edges cut by `chamfer` and its ends bevelled by `bevel`, its
   * middle at `p` ([x, y, z]); `at` (a Matrix4) instead of p; the loft's other options. */
  block(skin, [w, h, d], p = [0, 0, 0], o = {}) {
    const {chamfer = 0, bevel = 0, ...rest} = o, b = Math.min(bevel, 0.45 * Math.min(w, h, d)), inset = [(w - 2 * b) / w, (h - 2 * b) / h];
    return this.loft(skin, rect(w, h, Math.min(chamfer, 0.45 * Math.min(w, h))), b > 0 ? [st(-d / 2, inset), st(-d / 2 + b), st(d / 2 - b), st(d / 2, inset)] : [st(-d / 2), st(d / 2)], {at: move(...p), ...rest});
  }
  /** A drum of `radius` from z0 to z1 round the axis through (x, y): `sides`, `facet`, `bevel` (its rims cut). */
  drum(skin, radius, [z0, z1], o = {}) {
    const {x = 0, y = 0, bevel = 0, ...rest} = o, b = Math.min(bevel, 0.4 * radius, 0.4 * (z1 - z0));
    return this.lathe(skin, b > 0 ? [[0, z0], [radius - b, z0], [radius, z0 + b], [radius, z1 - b], [radius - b, z1], [0, z1]] : [[0, z0], [radius, z0], [radius, z1], [0, z1]], {at: move(x, y, 0), ...rest});
  }
  /** A tank with round ends from a to b ([x, y, z]) of `radius`; a ball when a is b. */
  capsule(skin, a, b, radius, o = {}) {
    const A = V3(...a), B = V3(...b), len = A.distanceTo(B), n = this.far ? 3 : 6, prof = [];
    for (let i = 0; i <= n; i++) { const u = i / n * Math.PI / 2; prof.push([radius * Math.sin(u), -len / 2 - radius * Math.cos(u)]); }
    for (let i = n; i >= 0; i--) { const u = i / n * Math.PI / 2; prof.push([radius * Math.sin(u), len / 2 + radius * Math.cos(u)]); }
    const z = len > 1e-6 ? B.clone().sub(A).normalize() : Z.clone(), x = Math.abs(z.y) < 0.9 ? V3().crossVectors(Y, z).normalize() : X.clone(), y = V3().crossVectors(z, x);
    return this.lathe(skin, prof, {at: basis(x, y, z, A.clone().add(B).multiplyScalar(0.5)), smooth: true, sides: 20, name: "tank", tone: 0.015, ...o});
  }
  /** A square strut from a to b (Vector3), `w` wide: no chart. */
  rod(skin, a, b, w) {
    const z = b.clone().sub(a), len = z.length();
    if (len < 1e-6) return this;
    z.divideScalar(len);
    const x = Math.abs(z.y) < 0.9 ? V3().crossVectors(Y, z).normalize() : X.clone(), y = V3().crossVectors(z, x);
    return this.loft(skin, rect(w, w), [st(0), st(len)], {at: basis(x, y, z, a), caps: [false, false], chart: false, plates: false, tone: 0});
  }
  /** An open truss from a to b ([x, y, z]), `width` square: four chords, frames and diagonals every `bay`. */
  truss(a, b, width, o = {}) {
    const A = V3(...a), B = V3(...b), len = A.distanceTo(B), z = B.clone().sub(A).normalize(), x = Math.abs(z.y) < 0.9 ? V3().crossVectors(Y, z).normalize() : X.clone(), y = V3().crossVectors(z, x);
    const bays = Math.max(1, Math.round(len / ((o.bay ?? 1.4) * width) / (this.far ? 2 : 1))), t = width * (o.thick ?? 0.07), h = width / 2, skin = o.skin ?? "hull-truss";
    const corner = (i, k) => A.clone().addScaledVector(z, len * k / bays).addScaledVector(x, [h, -h, -h, h][i % 4]).addScaledVector(y, [h, h, -h, -h][i % 4]);
    for (let i = 0; i < 4; i++) this.rod(skin, corner(i, 0), corner(i, bays), t * 1.4);
    for (let k = 0; k <= bays; k++) for (let i = 0; i < 4; i++) { this.rod(skin, corner(i, k), corner(i + 1, k), t); if (k < bays) this.rod(skin, corner(i, k), corner(i + 1, k + 1), t * 0.8); }
    return this;
  }
  /** A radiator vane: a thin panel standing out from `root` ([x, y, z]: the middle of its root edge, which runs
   * along z) in the direction `out`, `span` long and `chord` wide; `taper` (its outer edge's share of the chord),
   * `thick`, `ribs`. Its faces are the current region's; warm at the root where the coolant comes in. */
  vane(root, out, span, chord, o = {}) {
    const p = V3(...root), zl = V3(...out).normalize(), xl = Z.clone(), yl = V3().crossVectors(zl, xl).normalize(), at = basis(xl, yl, zl, p), thick = o.thick ?? Math.max(1.5, chord * 0.012), taper = o.taper ?? 0.8, ribs = this.far ? 0 : (o.ribs ?? 3);
    const warm = (q) => { const u = clamp(q.clone().sub(p).dot(zl) / span); return [1.0, 0.95 - 0.1 * (1 - u) * (1 - u), 0.92 - 0.22 * (1 - u) * (1 - u)]; };
    this.loft("hull-radiator", rect(chord, thick), [st(0), st(span * 0.86), st(span, [taper, 1])], {at, tone: 0.035, tint: warm});
    for (let i = 0; i <= ribs; i++) { const u = (i + 0.35) / (ribs + 0.7) * 0.86; this.loft("hull-c", rect(chord * 1.01, thick * 2.6), [st(span * u - thick), st(span * u + thick)], {at, chart: false, plates: false, tone: 0}); }
    this.loft("hull-c", rect(thick * 3, thick * 3), [st(0), st(span * 0.86)], {at: at.clone().multiply(move(chord / 2, 0, 0)), chart: false, plates: false, tone: 0});
    this.loft("hull-c", rect(thick * 3, thick * 3), [st(0), st(span * 0.86)], {at: at.clone().multiply(move(-chord / 2, 0, 0)), chart: false, plates: false, tone: 0});
    return this;
  }
  /** A dish of `radius` on a mast: it stands on `p` ([x, y, z]) and looks along `n`; `mast` (its length). */
  dish(p, n, radius, o = {}) {
    const z = V3(...n).normalize(), x = Math.abs(z.y) < 0.9 ? V3().crossVectors(Y, z).normalize() : X.clone(), y = V3().crossVectors(z, x), mast = o.mast ?? radius * 0.8, base = V3(...p), top = base.clone().addScaledVector(z, mast), prof = [], back = [];
    for (let i = 0; i <= 6; i++) { const u = i / 6; prof.push([radius * u, 0.3 * radius * u * u]); back.push([radius * (1 - u), 0.3 * radius * (1 - u) * (1 - u) - 0.03 * radius]); }
    this.rod("hull-truss", base, top, radius * 0.09);
    this.lathe("hull-b", back, {at: basis(x, y, z, top), sides: 24, smooth: true, chart: false, tone: 0.03});
    this.lathe("hull-a", prof.slice().reverse(), {at: basis(x, y, z, top), sides: 24, smooth: true, chart: false, tone: 0.03});
    this.rod("hull-truss", top.clone().addScaledVector(z, 0.02 * radius), top.clone().addScaledVector(z, 0.75 * radius), radius * 0.04);
    return this;
  }
  /** Low boxes scattered over a flat face, the break-up between the big forms and the fine detail: the face
   * runs from `origin` along `du` and `dv` (Vector3, their lengths the face's), facing `normal`; `count` boxes
   * `size` ([least, most] metres along the face) and `height` ([least, most]) from `seed`; `skins`; `sink` (the
   * share of its height a box stands in the face). No charts;
   * none at "far" detail. */
  scatter(origin, du, dv, normal, o = {}) {
    if (this.far) return this;
    const n = normal.clone().normalize(), lu = du.length(), lv = dv.length(), xu = du.clone().normalize(), xv = dv.clone().normalize(), size = o.size ?? [30, 110], height = o.height ?? [6, 22], skins = o.skins ?? ["hull-b", "hull-a", "hull-c"], seed = (o.seed ?? 0) * 131 + this.kit.seed;
    for (let i = 0; i < (o.count ?? 8); i++) {
      const h = (k) => hash3(i, k, seed, 77), long = mix(size[0], size[1], h(1) * h(1)), wide = Math.max(size[0] * 0.5, long * mix(0.25, 0.7, h(2))), along = h(3) < 0.65, a = Math.min(along ? wide : long, 0.8 * lu), b = Math.min(along ? long : wide, 0.8 * lv), tall = mix(height[0], height[1], h(4) * h(4));
      const c = origin.clone().addScaledVector(xu, a / 2 + h(5) * (lu - a)).addScaledVector(xv, b / 2 + h(6) * (lv - b)).addScaledVector(n, tall * (0.5 - (o.sink ?? 0.02)));
      this.loft(skins[Math.floor(h(7) * skins.length)], rect(a, b), [st(-tall / 2), st(tall / 2)], {at: basis(xu, xv, V3().crossVectors(xu, xv), c), chart: false, plates: false, tone: 0.05, caps: [V3().crossVectors(xu, xv).dot(n) < 0, V3().crossVectors(xu, xv).dot(n) > 0]});
    }
    return this;
  }
  /** A hangar mouth with real depth: a frame round a dark recess `w` by `h` and `depth` deep, its opening's
   * middle at `p` ([x, y, z]) facing `n` (a unit direction across or along the hull, level). Region `name`. */
  mouth(name, p, n, [w, h, depth], o = {}) {
    const zn = V3(...n).normalize(), up = Y.clone(), xl = V3().crossVectors(up, zn).normalize(), f = o.frame ?? 0.14 * Math.min(w, h), skin = o.skin ?? "hull-b", here = this.now.region;
    const at = basis(xl, zn, V3().crossVectors(xl, zn), V3(...p).addScaledVector(zn, -(depth + f) / 2)), sec = sectionOf(w + 2 * f, depth + f, f * 0.25, {trench: {w, d: depth}});
    this.region(name, "hangar");
    const mine = this.now.region;
    this.loft(skin, sec.poly, [st(-h / 2), st(h / 2)], {at, caps: [false, false], edge: (i) => (sec.tags[i] === "floor" ? {skin: "hull-void", name: "back wall"} : sec.tags[i] === "wall" ? {skin: "hull-c", name: "wall"} : {region: here.name})});
    for (const s of [1, -1]) this.loft(skin, rect(w + 2 * f, depth + f, f * 0.25), [st(s > 0 ? h / 2 : -h / 2 - f), st(s > 0 ? h / 2 + f : -h / 2)], {at, edge: () => ({region: here.name}), cap: {region: here.name}});
    this.now.region = here;
    mine.mouth = {p: [...p], n: arr(zn), width: w, height: h, depth};
    return this;
  }
  /** A worked asteroid: a ball of semi-axes `radii` round `centre`, its radius moved by `rough` (a share) of
   * smooth noise at `grain` lumps across, dented by `craters`, cut flat by `cuts` ([{n: [x, y, z], d}]: nothing
   * lies beyond d metres along n from the centre). One chart: u round +z, v from the stern's end to the bow's. */
  rock(centre, radii, o = {}) {
    const c = V3(...centre), rough = o.rough ?? 0.3, grain = o.grain ?? 2.2, seed = this.kit.seed + (o.seed ?? 0), nu = this.far ? 36 : 96, nv = this.far ? 20 : 56, cuts = (o.cuts ?? []).map((q) => ({n: V3(...q.n).normalize(), d: q.d}));
    const craters = Array.from({length: o.craters ?? 7}, (_, i) => { const a = hash1(i, seed + 5) * TAU, zc = 2 * hash1(i, seed + 6) - 1, s = Math.sqrt(1 - zc * zc); return {d: V3(s * Math.cos(a), s * Math.sin(a), zc), size: 0.12 + 0.2 * hash1(i, seed + 7), depth: 0.05 + 0.07 * hash1(i, seed + 8)}; });
    const region = this.now.region, id = this.count++, off = [hash1(id, 1) * 311, hash1(id, 2) * 311], w = TAU * Math.max(radii[0], radii[1]), h = Math.PI * radii[2];
    const at = (i, j) => {
      const th = i / nu * TAU, ph = Math.PI * (1 - j / nv), d = V3(Math.sin(ph) * Math.cos(th), Math.sin(ph) * Math.sin(th), Math.cos(ph));
      let k = 1 + rough * (fbm(d.x * grain + 7, d.y * grain + 3, d.z * grain + 5, seed) - 0.5) * 2;
      for (const cr of craters) { const q = Math.acos(clamp(d.dot(cr.d), -1, 1)) / cr.size; if (q < 1.25) k -= cr.depth * (q < 1 ? 1 - q * q : -0.25 * (1 - smooth(1, 1.25, q))); }
      const p = V3(d.x * radii[0], d.y * radii[1], d.z * radii[2]).multiplyScalar(k);
      let flat = null;
      for (const cut of cuts) { const s = p.dot(cut.n); if (s > cut.d) { p.multiplyScalar(cut.d / s); flat = cut.n; } }
      return {p: p.add(c), flat, tone: 0.78 + 0.5 * fbm(d.x * 5 + 1, d.y * 5 + 2, d.z * 5 + 3, seed + 20) + (flat ? 0.14 : 0)};
    };
    const G = Array.from({length: nv + 1}, (_, j) => Array.from({length: nu + 1}, (_, i) => at(i % nu, j)));
    const nrm = (i, j) => { const g = G[j][i]; if (g.flat) return g.flat; const a = G[j][(i + 1) % nu].p, b = G[j][(i + nu - 1) % nu].p, u = G[Math.min(nv, j + 1)][i].p, d = G[Math.max(0, j - 1)][i].p, n = V3().subVectors(a, b).cross(V3().subVectors(u, d)); return n.lengthSq() > 1e-9 ? n.normalize() : g.p.clone().sub(c).normalize(); };
    const NN = G.map((row, j) => row.map((_, i) => nrm(i, j)));
    const chart = this._chart(region, "rock", w, h, {origin: c.clone().addScaledVector(Z, -radii[2]), axis: Z.clone(), radius: Math.max(radii[0], radii[1])}, "round");
    for (let j = 0; j < nv; j++) for (let i = 0; i < nu; i++) {
      const q = [[i, j], [i + 1, j], [i + 1, j + 1], [i, j + 1]], P = q.map(([a, b]) => G[b][a].p), N = q.map(([a, b]) => NN[b][a]), C = q.map(([a, b]) => [a / nu * w, b / nv * h]), t = 0.25 * q.reduce((s, [a, b]) => s + G[b][a].tone, 0);
      if (j === 0) this._face("hull-rock", region, [P[0], P[2], P[3]], [N[0], N[2], N[3]], [C[0], C[2], C[3]], chart, off, t);
      else if (j === nv - 1) this._face("hull-rock", region, [P[0], P[1], P[2]], [N[0], N[1], N[2]], [C[0], C[1], C[2]], chart, off, t);
      else this._face("hull-rock", region, P, N, C, chart, off, t);
    }
    return this;
  }

  /** Close the shell: the atlas is laid, the meshes are made. Returns {root (a THREE.Group with a point "fore"),
   * regions, charts, scale (atlas units per metre of a chart of weight 1), profile}. */
  finish() {
    const scale = packCharts(this.charts), root = new THREE.Group(), groups = new Map(), box = new THREE.Box3();
    root.name = "hull";
    for (const part of this.parts.values()) {
      const g = new THREE.Group(); g.name = part.name; g.userData.part = part.name; g.userData.points = {};
      if (part.sparse) g.userData.sparse = true;
      if (part.spin) { g.userData.moving = true; g.userData.spin = {rate: part.spin}; g.rotation.set(Math.PI / 2, 0, 0); }
      groups.set(part.name, g); root.add(g);
    }
    const samples = [], loose = [];
    for (const b of this.buckets.values()) {
      const n = b.pos.length / 3, uv1 = new Float32Array(n * 2);
      for (let i = 0; i < n; i++) {
        const c = this.charts[b.cuv[3 * i]], cu = b.cuv[3 * i + 1], cv = b.cuv[3 * i + 2];
        if (!c) { uv1[2 * i] = uv1[2 * i + 1] = 2 / 512; continue; }
        uv1[2 * i] = c.rect[0] + (c.turned ? cv : cu) * c.scale; uv1[2 * i + 1] = c.rect[1] + (c.turned ? cu : cv) * c.scale;
      }
      const g = new THREE.BufferGeometry(), group = groups.get(b.part.name);
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(b.pos), 3)); g.setAttribute("normal", new THREE.BufferAttribute(new Float32Array(b.nor), 3));
      g.setAttribute("uv", new THREE.BufferAttribute(new Float32Array(b.uv), 2)); g.setAttribute("uv1", new THREE.BufferAttribute(uv1, 2)); g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(b.col), 3));
      g.setAttribute("chart", new THREE.BufferAttribute(Float32Array.from({length: n}, (_, i) => b.cuv[3 * i]), 1));   // the chart each corner lies in (-1: none): vidgen/space-hull-detail reads it
      for (let i = 0; i < n; i++) (b.part.sparse ? loose : samples).push(b.pos[3 * i], b.pos[3 * i + 1], b.pos[3 * i + 2]);
      if (b.part.spin) g.applyMatrix4(new THREE.Matrix4().makeRotationX(-Math.PI / 2));
      const mesh = new THREE.Mesh(g, this.kit.materials[b.skin]);
      mesh.castShadow = true; mesh.receiveShadow = true; mesh.name = b.skin;
      group.add(mesh);
    }
    for (const g of [...groups.values()]) if (!g.children.length) root.remove(g);
    for (const e of this.extra) root.add(e);
    for (const list of [samples, loose]) for (let i = 0; i < list.length; i += 3) box.expandByPoint(V3(list[i], list[i + 1], list[i + 2]));
    root.updateMatrixWorld(true);
    for (const e of this.extra) e.traverse((m) => { if (m.isMesh && !m.userData.keep) { m.geometry.computeBoundingBox(); box.union(m.geometry.boundingBox.clone().applyMatrix4(m.matrixWorld)); } });
    const slices = 40, z0 = box.min.z, dz = Math.max(1e-6, box.max.z - z0) / slices, profile = Array.from({length: slices}, (_, k) => ({z: z0 + (k + 0.5) * dz, x: [Infinity, -Infinity], y: [Infinity, -Infinity]}));
    for (let i = 0; i < samples.length; i += 3) { const s = profile[Math.min(slices - 1, Math.max(0, Math.floor((samples[i + 2] - z0) / dz)))]; s.x[0] = Math.min(s.x[0], samples[i]); s.x[1] = Math.max(s.x[1], samples[i]); s.y[0] = Math.min(s.y[0], samples[i + 1]); s.y[1] = Math.max(s.y[1], samples[i + 1]); }
    root.userData.points = {fore: {p: V3(0, 0, box.max.z), n: Z.clone(), u: Y.clone()}};
    return {root, regions: [...this.regions.values()].filter((r) => r.area > 0), charts: this.charts, scale, profile: profile.filter((s) => s.x[0] <= s.x[1])};
  }
}

// ---------- the kit ----------
const KIT = Object.freeze({palette: null, tile: 240, plate: 70});
const KIT_KEYS = ["seed", "accent", "foil", "detail", "wear", "lit"];
/** The parts of a giant hull: the kit of vidgen/space-craft (its bells, plumes and lights) with the hull's own
 * surfaces. Options: the craft kit's (`seed`, `accent`: the one accent colour, `detail`: "near" | "far", `wear`:
 * how deep the plates' lines are drawn) and `palette` (PALETTES; default by the seed), `tile` (metres one
 * repeat of the plate map covers, 240: about 64 plates of 12 to 60 m), `plate` (metres: the size of the big
 * plates each face is cut into, each of its own tone; 70). */
export class HullKit extends CraftKit {
  constructor(options = {}) {
    known("hullKit options", options, [...KIT_KEYS, ...Object.keys(KIT)]);
    super(Object.fromEntries(Object.entries(options).filter(([k]) => KIT_KEYS.includes(k))));
    const o = this.look = {...KIT, ...Object.fromEntries(Object.entries(options).filter(([k, v]) => k in KIT && v !== undefined && v !== null))};
    o.palette = choice("palette", o.palette ?? pick(rng(this.seed * 7411 + 5), Object.keys(PALETTES)), Object.keys(PALETTES));
    number("tile", o.tile, 20, 5000); number("plate", o.plate, 5, 5000);
    Object.assign(this.materials, hullMaterials(this, {palette: o.palette, tile: o.tile, wear: this.options.wear}));
  }
  /** Something to build a hull in (see Shell). */
  shell(options = {}) { known("shell options", options, ["minChart"]); return new Shell(this, {plate: this.look.plate, ...options}); }
  /** Bells in a bank: `plan` (bankPlan's), their plate's middle at (x, y, z) facing the stern; added to the
   * shell `sh`. Returns the anchors of the bells ([{name, p, n, radius, kind, bank}]). */
  bells(sh, plan, [x, y, z], bank = "engine-block", first = 1) {
    const was = this.far, list = [];
    this.far = this.far || plan.places.length > 2;
    plan.places.forEach(([px, py], i) => {
      const e = this.engine({exit: plan.radius, kind: plan.kind});
      e.quaternion.setFromUnitVectors(Y, Z); e.position.set(x + px, y + py, z); sh.extra.push(e);
      list.push({name: `bell-${first + i}`, p: [x + px, y + py, z - plan.length], n: [0, 0, -1], radius: plan.radius, kind: plan.kind, bank});
    });
    this.far = was;
    return list;
  }
  /** A lamp of the craft kit standing on `p`, shining along `n`: `kind` (the kit's LIGHTS). */
  lamp(sh, kind, p, n, size) {
    const l = this.light({kind, size});
    l.quaternion.setFromUnitVectors(Y, V3(...n).normalize()); l.position.set(...p); sh.extra.push(l);
    return {kind, p: [...p], n: [...n]};
  }
  /** Finish a hull from a closed shell: `built` (shell.finish()), `anchors`, a craft's options. See Hull. */
  hull(built, options = {}) { return new Hull(built, this, options); }
}
/** The parts of a giant hull: hullKit({seed, palette, accent, detail, wear, tile, plate}). */
export const hullKit = (options = {}) => new HullKit(options);
/** The layouts of a bank of bells. */
export const BANKS = Object.freeze(["grid", "ring", "row"]);
/** Where `count` bells stand in a field `w` by `h` metres and how large they can be: {places: [[x, y]], radius
 * (a bell's exit), length (plate to exit), kind}. `layout`: "grid" (rows of `rows`), "ring" (round the middle,
 * with one in it from seven up), "row". `fill`: the share of its cell a bell takes (0.84). */
export function bankPlan({w, h, count, rows = 2, layout = "grid", kind = "vacuum", fill = 0.84}) {
  choice("bank layout", layout, BANKS); choice("bell kind", kind, ["chemical", "vacuum", "ion"]); number("bells", count, 1, 64);
  const places = [];
  let radius;
  if (layout === "ring" && count > 2) {
    const mid = count >= 7 ? 1 : 0, n = count - mid, R = 0.5 * Math.min(w, h), k = Math.sin(Math.PI / n);
    radius = fill * R * k / (1 + k); const ring = R - radius / fill;
    for (let i = 0; i < n; i++) places.push([ring * Math.cos((i + 0.5) * TAU / n), ring * Math.sin((i + 0.5) * TAU / n)]);
    if (mid) { places.push([0, 0]); radius = Math.min(radius, fill * (ring - radius / fill)); }
  } else {
    const nr = layout === "row" ? 1 : Math.min(rows, count), nc = Math.ceil(count / nr), cw = w / nc, ch = h / nr;
    radius = 0.5 * fill * Math.min(cw, ch);
    for (let i = 0; i < count; i++) { const row = Math.floor(i / nc), inRow = Math.min(nc, count - row * nc); places.push([((i % nc) + 0.5 - inRow / 2) * cw, (row + 0.5 - nr / 2) * ch]); }
  }
  return {places, radius, length: radius * (kind === "vacuum" ? 3.4 : kind === "ion" ? 1.3 : 2.8), kind};
}

// ---------- a hull ----------
const HULL_KEYS = ["name", "occlusion", "camera", "height", "sun", "target", "lights", "marker"];
/** A giant hull: a Craft of vidgen/space-craft (`object`, update, fly, shade, `occluders`, `shadows`, `size`,
 * `info`, `engines`, dispose) with what the fine detail needs: `regions` ([{name, detail, surface: {material,
 * expects, density}, skin, box: {min, max}, centre, normal, area, charts}]), `region(name)`, `anchors` ({bells,
 * nozzles, hangars, docks, lights, bridge, points}), `anchor(name)` ({p, n}), `charts` ([{id, name, region,
 * kind, size: [w, h] metres, rect: [u0, v0, u1, v1], turned, scale, origin, du, dv, normal | axis, radius}]),
 * `texel(chart, size)` (metres a texel of a `size` atlas covers there), `profile` ([{z, x: [min, max], y}]:
 * the extent of its solid masses along the axis, without trusses, vanes and arrays), `shape` ({radii}: a bounding ellipsoid), `family`, `spec`, `problems()`,
 * `scaleRef(craft, {at})`. Places are metres in the hull's axes (+z the bow, +y up, +x port). */
export class Hull extends Craft {
  constructor(built, kit, options = {}) {
    const {anchors = {}, spec = null, family = null, ...rest} = options;
    known("hull options", rest, [...HULL_KEYS, "seed"]);
    super(built.root, kit, {occlusion: 0, ...rest, fore: "fore", kind: family, seed: rest.seed ?? kit.seed});
    const off = this.root.position.clone(), mv = (p) => [p[0] + off.x, p[1] + off.y, p[2] + off.z], r1 = (v) => v.map((x) => Math.round(x * 100) / 100);
    this.family = family; this.spec = spec; this.scale = built.scale;
    this.charts = built.charts.map((c) => ({id: c.id, name: c.name, region: c.region, kind: c.kind, size: r1(c.size), rect: c.rect, turned: c.turned, scale: c.scale, origin: r1(mv(arr(c.origin))),
      ...(c.kind === "plane" ? {du: arr(c.du), dv: arr(c.dv), normal: arr(c.normal)} : {axis: arr(c.axis), radius: c.radius})}));
    this.regions = built.regions.map((g) => {
      const skin = [...g.skins.entries()].sort((a, b) => b[1] - a[1])[0][0], n = g.sum.lengthSq() > 1e-6 * g.area * g.area ? g.sum.clone().normalize() : V3();
      return {name: g.name, detail: g.detail, surface: SURFACES[g.detail], skin, box: {min: r1(mv(arr(g.box.min))), max: r1(mv(arr(g.box.max)))}, centre: r1(mv(arr(g.box.getCenter(V3())))), normal: r1(arr(n)), area: Math.round(g.area), charts: g.charts, ...(g.mouth ? {mouth: {...g.mouth, p: r1(mv(g.mouth.p))}} : {})};
    });
    const moved = (a) => ({...a, p: r1(mv(a.p))});
    const bells = (anchors.bells ?? []).map(moved), hangars = this.regions.filter((g) => g.mouth).map((g) => ({name: g.name, ...g.mouth}));
    const half = [this.size.width / 2, this.size.height / 2, this.size.length / 2], points = {bow: {p: [0, 0, half[2]], n: [0, 0, 1]}, stern: {p: [0, 0, -half[2]], n: [0, 0, -1]}, top: {p: [0, half[1], 0], n: [0, 1, 0]}, bottom: {p: [0, -half[1], 0], n: [0, -1, 0]},
      port: {p: [half[0], 0, 0], n: [1, 0, 0]}, starboard: {p: [-half[0], 0, 0], n: [-1, 0, 0]}};
    const docks = (anchors.docks ?? []).map(moved), lights = (anchors.lights ?? []).map(moved), bridge = anchors.bridge ? moved(anchors.bridge) : null;
    for (const h of hangars) points[h.name] = {p: h.p, n: h.n};
    docks.forEach((d, i) => { points[`dock-${i + 1}`] = {p: d.p, n: d.n}; });
    for (const b of bells) points[b.name] = {p: b.p, n: b.n};
    if (bridge) points.bridge = {p: bridge.p, n: bridge.n};
    for (const [k, v] of Object.entries(anchors.points ?? {})) points[k] = moved(v);
    this.anchors = {bells, nozzles: bells.map((b) => ({p: b.p, n: b.n, radius: b.radius, kind: b.kind})), hangars, docks, lights, bridge, points};
    this.profile = built.profile.map((s) => ({z: Math.round((s.z + off.z) * 10) / 10, x: r1([s.x[0] + off.x, s.x[1] + off.x]), y: r1([s.y[0] + off.y, s.y[1] + off.y])}));
    this.shape = {radii: half};
    this.shadows = {size: Math.max(1, this.size.radius * 1.04), mapSize: 2048, bias: -0.0006};
    this.refs = [];
  }
  /** The region `name`. */
  region(name) { const g = this.regions.find((q) => q.name === name); if (!g) throw fail(`no region "${name}"${hint(name, this.regions.map((q) => q.name))}; regions: ${this.regions.map((q) => q.name).join(", ")}`); return g; }
  /** The place `name` ({p, n}): bow, stern, top, bottom, port, starboard, bridge, hangar-N, dock-N, bell-N. */
  anchor(name) { const a = this.anchors.points[name]; if (!a) throw fail(`no anchor "${name}"${hint(name, Object.keys(this.anchors.points))}; anchors: ${Object.keys(this.anchors.points).join(", ")}`); return a; }
  /** The metres one texel covers on `chart` (a chart or its id) in an atlas `size` texels square (4096). */
  texel(chart, size = 4096) { const c = typeof chart === "number" ? this.charts[chart] : chart; return 1 / (c.scale * size); }
  /** Stand a known-size craft beside the hull for a sense of size: `craft` (a Craft or a Plane, or a kind of the
   * craft kit: "ship" is 42 to 58 m, "tug" 19 to 32 m, "station" about 60 m), {at (an anchor's name, "port"),
   * gap (metres off the place along its direction; default twice the craft's radius), seed, detail}. The craft
   * rides with the hull (a child of its object), its nose along the hull's. Returns the craft. */
  scaleRef(craft = "ship", options = {}) {
    known("scaleRef options", options, ["at", "gap", "seed", "detail"]);
    const c = typeof craft === "string" ? kitCraft(craft, {seed: options.seed ?? 1, detail: options.detail ?? "near"}) : craft, a = this.anchor(options.at ?? "port");
    if (!c || !c.object || !c.size) throw fail("scaleRef needs a craft (vidgen/space-craft, vidgen/space-plane) or a kind of the craft kit");
    c.object.position.set(...a.p).addScaledVector(V3(...a.n), options.gap ?? 2 * c.size.radius); c.object.quaternion.identity();
    this.object.add(c.object); this.refs.push(c);
    return c;
  }
  /** What looks wrong, as sentences (an empty list: nothing): a length outside 0.5 to 10 km, absurd proportions,
   * a bell buried in the hull or two bells through each other, and the one layout that is too near a well-known
   * fictional ship: a hull narrowing to a point with a raised tower at the stern. */
  problems() {
    const out = [], {length: L, width: W, height: H} = this.size, r0 = (x) => Math.round(x);
    if (L < 500 || L > 10000) out.push(`the hull is ${r0(L)} m long: the kit is made for 500 to 10,000 m (plates, bells and charts are sized for that)`);
    if (Math.max(W, H) > 0.85 * L) out.push(`the hull is ${r0(W)} m wide and ${r0(H)} m high for ${r0(L)} m of length: not a ship with a long axis`);
    if (Math.max(L, W, H) < 1.35 * Math.min(L, W, H)) out.push("the hull is nearly as wide and high as it is long: a cube or a ball, not a ship of this kit");
    if (Math.max(W, H) < 0.012 * L) out.push(`the hull is only ${r0(Math.max(W, H))} m across for ${r0(L)} m of length: a thread`);
    const blocks = this.regions.filter((g) => g.name.startsWith("engine")), others = this.regions.filter((g) => !g.name.startsWith("engine") && g.detail !== "truss");
    const inside = (p, g, m) => p[0] > g.box.min[0] + m && p[0] < g.box.max[0] - m && p[1] > g.box.min[1] + m && p[1] < g.box.max[1] - m && p[2] > g.box.min[2] + m && p[2] < g.box.max[2] - m;
    this.anchors.bells.forEach((b, i) => {
      const block = blocks.find((g) => g.name === b.bank);
      if (block && b.p[2] > block.box.min[2] + 0.2 * b.radius) out.push(`${b.name} is buried: its exit is ${r0(b.p[2] - block.box.min[2])} m ahead of the aft face of ${block.name}`);
      const hit = others.find((g) => inside(b.p, g, 0.1 * b.radius) || inside([b.p[0], b.p[1], b.p[2] - 2 * b.radius], g, 0.1 * b.radius));
      if (hit) out.push(`${b.name} fires into ${hit.name}`);
      for (const c of this.anchors.bells.slice(i + 1)) if (Math.abs(c.p[2] - b.p[2]) < 0.5 * b.radius && Math.hypot(c.p[0] - b.p[0], c.p[1] - b.p[1]) < 0.98 * (b.radius + c.radius)) out.push(`${b.name} and ${c.name} stand through each other`);
    });
    out.push(...forbidden(this.profile, this.regions));
    return out;
  }
  dispose() { for (const c of this.refs) c.dispose(); super.dispose(); }
}
/** The layouts this kit must not make, tested on a hull's extent along its axis (`profile`: [{z, x: [min, max],
 * y: [min, max]}], the stern first) and its regions: a plan that narrows towards the bow to under 0.45 of its
 * greatest width (a wedge) with a tower-N standing in the aft third, and a plan that narrows to under 0.3 (a
 * dagger) even without one. Returns sentences. */
export function forbidden(profile, regions = []) {
  const out = [], n = profile.length;
  if (n < 8) return out;
  const wide = profile.map((s) => s.x[1] - s.x[0]), high = profile.map((s) => s.y[1] - s.y[0]), wmax = Math.max(...wide), z0 = profile[0].z, L = profile[n - 1].z - z0, from = Math.floor(n * 0.4);
  const bow = wide[n - 1], widest = wide.indexOf(wmax);
  let falls = 0, cliff = 0;
  for (let k = from; k < n - 1; k++) { if (wide[k + 1] <= wide[k] + 0.01 * wmax) falls++; cliff = Math.max(cliff, wide[k] - wide[k + 1]); }
  const tapering = widest < 0.6 * n && falls >= 0.8 * (n - 1 - from) && cliff < 0.3 * wmax, deck = [...high].sort((a, b) => a - b)[Math.floor(n / 2)];
  const towers = regions.filter((g) => /^tower/.test(g.name) && g.centre[2] < z0 + 0.36 * L && g.box.max[1] - g.box.min[1] > 0.3 * deck && g.box.max[0] - g.box.min[0] < 0.6 * wmax);
  if (tapering && bow < 0.3 * wmax) out.push(`the plan narrows to a point at the bow (${Math.round(100 * bow / wmax)} % of its greatest width): a dagger hull is too near well-known fictional ships; keep the bow blunt (taper 0.6 or more)`);
  else if (tapering && bow < 0.45 * wmax && towers.length) out.push(`a hull narrowing towards the bow with a raised tower at the stern (${towers[0].name}) is too near a well-known fictional ship: keep the bow blunt (taper 0.6 or more) or move the tower forward and lower it`);
  return out;
}

// ---------- the families: invented designs, another member for every seed ----------
// what a family's builder works with: the shell, the kit, the length, its numbers and the anchors it leaves
class Yard {
  constructor(kit, spec) {
    this.kit = kit; this.sh = kit.shell(); this.L = spec.length; this.spec = spec; this.r = rng((spec.seed * 2246822519 + 97) >>> 0);
    this.anchors = {bells: [], docks: [], lights: [], bridge: null, points: {}};
    const L = this.L, age = spec.age, seed = spec.seed;
    this.sh.weather = (p) => 1 - age * (0.5 * smooth(-0.5 * L + 0.2 * L, -0.5 * L, p.z) + 0.16 * (noise3(p.z / (0.045 * L) + 3, p.x / (0.3 * L), p.y / (0.3 * L), seed) - 0.35));
  }
  /** The drive: a block (or a drum) carrying a bank of bells whose exits stand at `stern`. Returns {z: the
   * block's forward face, plan}. */
  drive({w, h, count, rows = 2, layout = "grid", kind = "vacuum", x = 0, y = 0, stern = -this.L / 2, shape = "block", depth, name = "engine-block"}) {
    const plan = bankPlan({w, h, count, rows, layout, kind}), zp = stern + plan.length, sh = this.sh, inset = (this.spec.inset ?? 0) * this.L;
    sh.part(name).region(name, "engine");
    if (shape === "drum") sh.lathe("hull-c", [[0, zp], [0.5 * w, zp], [0.54 * w, zp + 0.25 * depth], [0.54 * w, zp + depth], [0, zp + depth]], {at: move(x, y, 0), sides: 12, facet: true, name: "drum"});
    else sh.block("hull-c", [w * 1.06, h * 1.12, depth], [x, y, zp + depth / 2], {chamfer: 0.1 * h, bevel: 0.07 * h});
    this.anchors.bells.push(...this.kit.bells(sh, plan, [x, y, zp + inset], name, this.anchors.bells.length + 1));
    return {z: zp + depth, plan};
  }
  lamp(kind, p, n) { this.anchors.lights.push(this.kit.lamp(this.sh, kind, p, n, clamp(this.L / 700, 1.5, 9))); }
  lamps(half, top) { const L = this.L; this.lamp("port", [half, 0, 0], [1, 0, 0]); this.lamp("starboard", [-half, 0, 0], [-1, 0, 0]); this.lamp("strobe", [0, top, 0.3 * L], [0, 1, 0]); this.lamp("beacon", [0, -top, -0.25 * L], [0, -1, 0]); this.lamp("white", [0, top, -0.36 * L], [0, 1, 0]); }
}
const ringOf = (n, radius, turn = 0) => Array.from({length: n}, (_, i) => { const a = (i + turn) * TAU / n; return [radius * Math.cos(a), radius * Math.sin(a)]; });

const BUILD = {
  // a long open truss: the drive at one end behind a shadow disc, radiator vanes in one plane, clusters of
  // propellant tanks, crew drums far forward, a docking face as the bow, an array on a mast to one side
  spine(y, p) {
    const {sh, L} = y, g = p.girth * L, d = y.drive({w: 4.4 * g, h: 4.4 * g, count: p.bells, layout: "ring", shape: "drum", depth: 0.045 * L}), z0 = d.z, zb = L / 2 - 0.04 * L;
    sh.part("shadow disc").region("engine-block", "engine").drum("hull-b", 3.2 * g, [z0 + 0.012 * L, z0 + 0.02 * L], {sides: 16, facet: true, bevel: 0.2 * g});
    sh.part("truss", {sparse: true}).region("truss", "truss").truss([0, 0, z0], [0, 0, zb], g);
    const span = p.vaneSpan * L, sets = [[-0.16, 0.22, 1], [-0.36, 0.12, 0.62]];
    let n = 0;
    for (const [zc, chord, share] of sets.slice(0, p.vanes / 2)) for (const s of [1, -1]) { n++; sh.part(`radiator ${n}`, {sparse: true}).region(`radiator-${n}`, "radiator").vane([s * g / 2, 0, zc * L], [s, 0, 0], span * share, chord * L, {taper: 0.8}); }
    const zone = [-0.03 * L, 0.27 * L], lc = (zone[1] - zone[0]) / p.tanks, rt = p.tank * g;
    for (let k = 0; k < p.tanks; k++) {
      const zc = zone[0] + (k + 0.5) * lc;
      sh.part(`tanks ${k + 1}`).region(`tank-${k + 1}`, "tank");
      for (const [x, yy] of ringOf(p.tankCount, 0.72 * g + rt, 0.5)) sh.capsule("hull-tank", [x, yy, zc - 0.4 * lc + rt], [x, yy, zc + 0.4 * lc - rt], rt);
      sh.drum("hull-c", 0.95 * g, [zc - 0.03 * lc, zc + 0.03 * lc], {sides: 8, facet: true, chart: false});
    }
    const Rd = p.drum * L, ld = 0.048 * L;
    let z = 0.3 * L;
    for (let k = 0; k < p.drums; k++) {
      const R = Rd * (k ? 0.8 : 1);
      sh.part(`habitat ${k + 1}`).region(`habitat-${k + 1}`, "windows").drum("hull-a", R, [z, z + ld], {sides: 16, facet: true, bevel: 0.12 * R});
      if (!sh.far && k === 0) sh.lathe("hull-accent", [[R * 1.012, z + 0.4 * ld], [R * 1.012, z + 0.5 * ld]], {sides: 16, facet: true, chart: false, tone: 0});
      sh.region("midship").drum("hull-b", 0.5 * R, [z + ld, z + ld + 0.018 * L], {sides: 8, facet: true, chart: false});
      z += ld + 0.018 * L;
    }
    y.anchors.bridge = {p: [0, 0.7 * Rd, 0.3 * L], n: [0, 0, -1]};
    sh.part("bow").region("bow", "dock").drum("hull-b", 1.6 * g, [zb - 0.02 * L, L / 2], {sides: 8, facet: true, bevel: 0.35 * g});
    sh.part("dock frame", {sparse: true}).region("truss", "truss");
    const q = ringOf(4, 3.4 * g, 0.5).map(([a, b]) => V3(a, b, L / 2 - 0.012 * L));
    for (let i = 0; i < 4; i++) { sh.rod("hull-truss", q[i], q[(i + 1) % 4], 0.22 * g); sh.rod("hull-truss", q[i], V3(q[i].x * 0.3, q[i].y * 0.3, zb - 0.02 * L), 0.16 * g); }
    y.anchors.docks.push({p: [0, 0, L / 2], n: [0, 0, 1]});
    sh.part("array", {sparse: true}).region("midship").dish([p.side * 0.9 * Rd, 0.3 * Rd, 0.3 * L + 0.5 * ld], [p.side * 0.8, 0.5, 0.35], 0.032 * L, {mast: 0.055 * L});
    y.lamps(span + g / 2, Rd);
  },
  // a thick block with a flat deck: a trench down its middle that opens into a gulf between two blunt prongs at the
  // bow, hangar slots along one side, low terraces on the deck, a keel block under it, two radiators under the stern
  carrier(y, p) {
    const {sh, L, r} = y, W = p.beam * L, H = p.depth * L, c = 0.035 * H, d = y.drive({w: 0.84 * W, h: 0.6 * H, count: p.bells, rows: 2, depth: 0.06 * L}), z0 = d.z;
    const pointed = p.taper < 0.5, prong = (pointed ? 0.3 : 0.11) * L, z1 = L / 2 - prong, tw = p.trench * W, td = 0.3 * H, gulf = Math.max(2.2 * tw, 0.3 * W), sides = p.side === 0 ? [1, -1] : [p.side], off = p.side === 0 ? 1 : -p.side;
    const n = p.segments, shares = Array.from({length: n}, () => range(r, 0.7, 1.3)), total = shares.reduce((a, b) => a + b, 0), bays = new Set();
    for (let k = 0; k < p.hangars; k++) bays.add(1 + Math.round((k + 0.5) * (n - 2) / p.hangars - 0.5));
    let za = z0, hangar = 0;
    for (let i = 0; i < n; i++) {
      const zb = za + (z1 - z0) * shares[i] / total, wf = i === 0 ? 0.88 : bays.has(i) ? 1 : pick(r, [1, 0.96, 0.9, 0.86]), hf = i === 0 ? 0.88 : pick(r, [1, 0.92, 0.84]), up = 0.5 * H * (1 - hf), names = {};
      const slots = [1, -1].map((side) => (bays.has(i) && sides.includes(side) ? (names[side] = `hangar-${++hangar}`, {side, y0: -0.34 * H * hf, y1: 0.1 * H * hf, d: 0.2 * W}) : {side, y0: 0.2 * H * hf, y1: 0.29 * H * hf, d: 0.02 * W}));
      const sec = sectionOf(W * wf, H * hf, c, {trench: tw > 0 ? {w: tw, d: td} : null, slots});
      let seen = 0;
      const which = sec.tags.map((t) => (t === "slot" || t === "back" ? names[[1, -1][Math.floor(seen++ / 3)]] ?? null : null));
      sh.part(`hull ${i + 1}`).region("midship").loft(wf < 0.95 ? "hull-b" : "hull-a", sec.poly, [st(za), st(zb)], {at: move(0, up, 0), edge: (e) => {
        const t = sec.tags[e];
        if (t === "wall" || t === "floor") return {skin: t === "wall" ? "hull-b" : "hull-c", region: "trench", detail: "trench", name: t};
        if (t === "slot" || t === "back") return which[e] ? {skin: t === "back" ? "hull-void" : "hull-c", region: which[e], detail: "hangar", name: t === "back" ? "back wall" : "deck"} : {skin: "hull-c", name: "gallery"};
        return {name: t};
      }});
      for (const q of slots.filter((v) => names[v.side])) {
        sh.regions.get(names[q.side]).mouth = {p: [q.side * W * wf / 2, up + 0.5 * (q.y0 + q.y1), 0.5 * (za + zb)], n: [q.side, 0, 0], width: zb - za, height: q.y1 - q.y0, depth: q.d};
        if (!sh.far) sh.block("hull-accent", [0.012 * W, 0.02 * H, 0.96 * (zb - za)], [q.side * (W * wf / 2 + 0.004 * W), up + q.y1 + 0.03 * H, 0.5 * (za + zb)], {chart: false, tone: 0});
      }
      for (const q of [1, -1]) sh.part("deck works", {sparse: true}).region("midship").scatter(V3(q > 0 ? tw / 2 + 0.02 * W : -W * wf / 2 + 0.03 * W, H / 2, za + 0.04 * (zb - za)), V3(W * wf / 2 - tw / 2 - 0.05 * W, 0, 0), V3(0, 0, 0.92 * (zb - za)), Y, {count: 5, seed: i * 2 + (q > 0 ? 1 : 0), size: [0.012 * L, 0.05 * L], height: [0.03 * H, 0.1 * H]});
      if (!sh.far && i > 0) sh.part("ribs").block("hull-b", [W * 1.012, H * 1.03, 0.006 * L], [0, 0, za], {chamfer: c, chart: false, plates: false});
      za = zb;
    }
    sh.part("bow").region("bow", "dock");
    if (pointed) sh.loft("hull-a", rect(W, 0.84 * H, c), [st(z1), st(L / 2, [p.taper, 0.7])], {at: move(0, 0.08 * H, 0)});
    else for (const q of [1, -1]) { const pw = (W * p.taper - gulf) / 2, ph = (q === off ? 0.62 : 0.78) * H; sh.block("hull-a", [pw, ph, prong * (q === off ? 0.8 : 1)], [q * (gulf + pw) / 2, (H - ph) / 2 - 0.06 * H, z1 + prong * (q === off ? 0.4 : 0.5)], {chamfer: c, bevel: 1.2 * c}); }
    y.anchors.docks.push({p: [0, 0, z1], n: [0, 0, 1]});
    p.towers.forEach((t, k) => {
      const zc = L / 2 - t.at * L, x = t.side * (tw / 2 + 0.03 * W + t.wid * W / 2), th = t.high * H, tl = t.len * L, wd = t.wid * W, lean = t.side * 0.1 * wd;
      sh.part(`tower ${k + 1}`).region(`tower-${k + 1}`, "windows").block("hull-b", [wd, 0.5 * th + 0.04 * H, tl], [x, H / 2 + 0.25 * th - 0.02 * H, zc], {chamfer: 0.05 * th, bevel: 0.05 * th});
      sh.block("hull-a", [0.62 * wd, 0.3 * th, 0.74 * tl], [x + 1.6 * lean, H / 2 + 0.65 * th, zc + (k % 2 ? 0.1 : -0.1) * tl], {chamfer: 0.04 * th, bevel: 0.04 * th});
      sh.block("hull-b", [0.3 * wd, 0.2 * th, 0.3 * tl], [x + 2.4 * lean, H / 2 + 0.9 * th, zc + (k % 2 ? 0.28 : -0.28) * tl], {chamfer: 0.03 * th, bevel: 0.03 * th});
      if (k === 0) y.anchors.bridge = {p: [x, H / 2 + 0.22 * th, zc + tl / 2], n: [0, 0, 1]};
    });
    const kh = p.keel * H;
    if (kh > 0) sh.part("keel").region("keel", "cargo").block("hull-b", [0.5 * W, kh, 0.3 * L], [0, -H / 2 + 0.17 * H - kh / 2, 0.04 * L], {chamfer: 0.2 * kh, bevel: 0.35 * kh});
    if (p.side === 0) [1, -1].forEach((q, k) => sh.part(`radiator ${k + 1}`, {sparse: true}).region(`radiator-${k + 1}`, "radiator").vane([q * 0.3 * W, -H / 2 + 0.17 * H, z0 + 0.13 * L], [q * 0.62, -0.78, 0], p.vaneSpan * L, 0.15 * L, {taper: 0.75}));
    else {
      sh.part("sponson").region("sponson", "plating").block("hull-b", [0.14 * W, 0.46 * H, 0.42 * L], [off * (0.5 * W * 0.86 + 0.06 * W), -0.12 * H, -0.06 * L], {chamfer: 0.05 * H, bevel: 0.12 * H});
      [[-0.17, 0.2, 1], [0.06, 0.12, 0.7]].forEach(([zc, chord, share], k) => sh.part(`radiator ${k + 1}`, {sparse: true}).region(`radiator-${k + 1}`, "radiator").vane([off * (0.43 * W + 0.13 * W), -0.12 * H, zc * L], [off, 0, 0], p.vaneSpan * L * share, chord * L, {taper: 0.78}));
    }
    sh.part("array", {sparse: true}).region("midship").dish([off * 0.3 * W, H / 2, 0.3 * L], [off * 0.25, 1, 0.3], 0.1 * W, {mast: 0.08 * W});
    y.lamps(W / 2, H / 2);
  },
  // an open frame carrying what it carries in plain sight: pressure balls, tanks, container stacks and gaps, a crew
  // block high on the bow, radiators standing up and down from the stern
  cluster(y, p) {
    const {sh, L} = y, fw = p.girth * L, fh = fw * p.aspect, d = y.drive({w: 0.9 * fw, h: 0.86 * fh, count: p.bells, rows: 2, depth: 0.045 * L}), z0 = d.z, crew = 0.11 * L, zf = L / 2 - 0.55 * crew;
    const n = p.cells.length, cl = (zf - z0) / n, t = 0.035 * fw, corner = (i, k) => V3([1, -1, -1, 1][i % 4] * fw / 2, [1, 1, -1, -1][i % 4] * fh / 2, z0 + k * cl);
    sh.part("frame", {sparse: true}).region("truss", "truss");
    for (let i = 0; i < 4; i++) sh.rod("hull-truss", corner(i, 0), corner(i, n), 1.5 * t);
    for (let k = 0; k <= n; k++) for (let i = 0; i < 4; i++) { sh.rod("hull-truss", corner(i, k), corner(i + 1, k), t); if (k < n && (i % 2 === 0 || !sh.far)) sh.rod("hull-truss", corner(i, k), corner(i + 1, k + 1), 0.7 * t); }
    const counts = {};
    p.cells.forEach((kind, k) => {
      const zc = z0 + (k + 0.5) * cl, id = (name, detail) => { counts[name] = (counts[name] ?? 0) + 1; sh.part(`${name} ${counts[name]}`).region(`${name}-${counts[name]}`, detail); };
      if (kind === "ball") { id("tank", "tank"); sh.capsule("hull-tank", [0, 0, zc], [0, 0, zc], Math.min(0.58 * Math.min(fw, fh), 0.5 * cl)); }
      else if (kind === "pair") { id("tank", "tank"); for (const s of [1, -1]) sh.capsule("hull-a", [s * 0.25 * fw, 0, zc - 0.4 * cl + 0.24 * fw], [s * 0.25 * fw, 0, zc + 0.4 * cl - 0.24 * fw], Math.min(0.24 * fw, 0.46 * fh)); }
      else if (kind === "cross") { id("tank", "tank"); const rr = Math.min(0.36 * fh, 0.4 * cl); sh.capsule("hull-tank", [-0.72 * fw + rr, 0, zc], [0.72 * fw - rr, 0, zc], rr); }
      else if (kind === "cargo") {
        id("cargo", "cargo");
        const bx = 0.4 * fw, by = 0.29 * fh, bz = 0.29 * cl;
        for (let a = 0; a < 3; a++) for (let b = 0; b < 3; b++) for (let c = 0; c < 3; c++) {
          const h = hash3(a + 7 * k, b, c, y.spec.seed);
          if (h < 0.14) continue;
          sh.block(h < 0.2 ? "hull-accent" : h < 0.55 ? "hull-b" : "hull-a", [bx, by, bz], [(a - 1) * 0.46 * fw, (b - 1) * 0.32 * fh, zc + (c - 1) * 0.32 * cl], {tone: 0.1, plates: false, chart: false});
        }
      }
    });
    sh.part("bow").region("bow", "windows").block("hull-a", [0.84 * fw, 0.56 * fh, crew], [0, 0.22 * fh, L / 2 - crew / 2], {chamfer: 0.1 * fh, bevel: 0.08 * fh});
    sh.region("bow", "windows").drum("hull-b", 0.16 * fw, [zf - 0.2 * crew, L / 2 - 0.25 * crew], {y: -0.26 * fh, sides: 8, facet: true, bevel: 0.03 * fw});
    y.anchors.bridge = {p: [0, 0.22 * fh, L / 2], n: [0, 0, 1]}; y.anchors.docks.push({p: [0, -0.26 * fh, L / 2 - 0.25 * crew], n: [0, 0, 1]});
    [1, -1].forEach((s, k) => sh.part(`radiator ${k + 1}`, {sparse: true}).region(`radiator-${k + 1}`, "radiator").vane([0, s * fh / 2, z0 + 0.09 * L], [0, s, 0], p.vaneSpan * L * (s > 0 ? 1 : 0.7), 0.14 * L, {taper: 0.8}));
    sh.part("array", {sparse: true}).region("bow").dish([0.2 * fw, 0.5 * fh, L / 2 - 0.7 * crew], [0.35, 1, 0.25], 0.17 * fw, {mast: 0.2 * fw});
    y.lamps(fw / 2, fh / 2);
  },
  // a very long thin hull behind a faceted shield, the crew drum and tanks close behind it, the drive far aft on a
  // truss with long narrow radiators round it
  lance(y, p) {
    const {sh, L} = y, bd = p.body * L, Rs = 0.5 * p.shield * L, cone = p.shieldShape === "cone", d = y.drive({w: 2.7 * bd, h: 2.7 * bd, count: p.bells, layout: p.bells > 2 ? "ring" : "row", rows: 1, shape: "drum", depth: 0.035 * L}), z0 = d.z;
    const zs = L / 2 - (cone ? 0.42 : 0.1) * Rs, zboom = -L / 2 + p.boom * L;
    sh.part("shield").region("bow", "shield").lathe("hull-b", cone ? [[0, zs - 0.12 * Rs], [0.3 * Rs, zs - 0.12 * Rs], [Rs, zs - 0.03 * Rs], [Rs, zs], [0.22 * Rs, L / 2 - 0.02 * Rs], [0, L / 2]]
      : [[0, zs - 0.14 * Rs], [0.3 * Rs, zs - 0.14 * Rs], [Rs, zs - 0.04 * Rs], [Rs, zs + 0.03 * Rs], [0.9 * Rs, L / 2], [0, L / 2]], {sides: cone ? 16 : 24, facet: true, name: "shield", tone: 0.09});
    const zt = zs - 0.12 * Rs;
    sh.part("shield struts", {sparse: true}).region("truss", "truss");
    for (const [a, b] of ringOf(4, 0.72 * Rs, 0.5)) sh.rod("hull-truss", V3(a, b, zs - 0.06 * Rs), V3(a * 0.25 * bd / Rs, b * 0.25 * bd / Rs, zt - 0.09 * L), 0.16 * bd);
    const cuts = [zboom, mix(zboom, zt, 0.38), mix(zboom, zt, 0.7), zt];
    for (let k = 0; k < 3; k++) {
      sh.part(`body ${k + 1}`).region("midship").drum(k === 1 ? "hull-b" : "hull-a", 0.5 * bd * (k === 1 ? 0.84 : 1), [cuts[k], cuts[k + 1]], {sides: 12, facet: true});
      if (!sh.far) sh.drum("hull-c", 0.64 * bd, [cuts[k] - 0.003 * L, cuts[k] + 0.003 * L], {sides: 12, facet: true, chart: false});
    }
    const zh = zt - 0.13 * L, Rh = p.drum * bd;
    sh.part("habitat").region("habitat-1", "windows").drum("hull-a", Rh, [zh - 0.045 * L, zh], {sides: 16, facet: true, bevel: 0.15 * Rh});
    if (!sh.far) sh.lathe("hull-accent", [[Rh * 1.012, zh - 0.03 * L], [Rh * 1.012, zh - 0.024 * L]], {sides: 16, facet: true, chart: false, tone: 0});
    y.anchors.bridge = {p: [0, 0.75 * Rh, zh], n: [0, 0, 1]}; y.anchors.docks.push({p: [bd / 2, 0, mix(zboom, zt, 0.5)], n: [1, 0, 0]});
    sh.part("tanks").region("tank-1", "tank");
    for (const [a, b] of ringOf(6, 0.5 * bd + 0.4 * bd)) sh.capsule("hull-tank", [a, b, zh - 0.15 * L], [a, b, zh - 0.065 * L], 0.4 * bd);
    sh.part("boom", {sparse: true}).region("truss", "truss").truss([0, 0, z0], [0, 0, zboom], 0.56 * bd);
    // what makes it more than a tube: a box girder along its back that carries a gantry, a hangar shed slung under
    // it and open to port, a second, smaller ring of tanks further aft
    const zg0 = mix(zboom, zt, 0.06), zg1 = mix(zboom, zt, 0.62), zshed = mix(zboom, zt, 0.33), shed = [0.07 * L, 0.9 * bd, 2 * bd];
    sh.part("girder").region("midship").block("hull-b", [0.42 * bd, 0.5 * bd, zg1 - zg0], [0, 0.72 * bd, 0.5 * (zg0 + zg1)], {chamfer: 0.08 * bd, bevel: 0.1 * bd});
    if (!sh.far) for (let k = 0; k < 5; k++) sh.block("hull-c", [1.5 * bd, 0.16 * bd, 0.012 * L], [0, 1.02 * bd, mix(zg0, zg1, (k + 0.5) / 5)], {chart: false, plates: false});
    sh.block("hull-a", [0.8 * bd, 0.7 * bd, 0.05 * L], [0, 1.3 * bd, mix(zg0, zg1, 0.78)], {chamfer: 0.1 * bd, bevel: 0.1 * bd});
    sh.part("shed").region("midship").mouth("hangar-1", [1.0 * bd, -1.12 * bd, zshed], [1, 0, 0], shed, {skin: "hull-a"});
    sh.part("shed struts", {sparse: true}).region("truss", "truss");
    for (const s of [-1, 1]) for (const q of [-0.6, 0.6]) sh.rod("hull-truss", V3(q * bd, -0.4 * bd, zshed + s * 0.03 * L), V3(q * bd, -0.7 * bd, zshed + s * 0.03 * L), 0.12 * bd);
    sh.part("tanks 2").region("tank-2", "tank");
    for (const [a, b] of ringOf(3, 0.5 * bd + 0.3 * bd, 0.25)) sh.capsule("hull-tank", [a, b, mix(zboom, zt, 0.1)], [a, b, mix(zboom, zt, 0.2)], 0.3 * bd);
    sh.part("shadow disc").region("engine-block", "engine").drum("hull-b", 1.8 * bd, [z0 + 0.008 * L, z0 + 0.014 * L], {sides: 16, facet: true});
    const chord = 0.6 * (zboom - z0), zc = 0.5 * (zboom + z0) + 0.03 * L;
    for (let k = 0; k < p.vanes; k++) { const a = (p.vanes === 3 ? 90 : 45) * RAD + k * TAU / p.vanes; sh.part(`radiator ${k + 1}`, {sparse: true}).region(`radiator-${k + 1}`, "radiator").vane([0.3 * bd * Math.cos(a), 0.3 * bd * Math.sin(a), zc], [Math.cos(a), Math.sin(a), 0], p.vaneSpan * L, chord, {taper: 0.7, ribs: 5}); }
    y.lamps(Rs, Rs);
  },
  // a thick hub carrying two polygonal crew rings of unequal size that turn against each other, a docking drum as
  // the bow, tanks and a cross of radiators before the drive
  wheel(y, p) {
    const {sh, L} = y, hr = p.hub * L, d = y.drive({w: 5 * hr, h: 5 * hr, count: p.bells, layout: "ring", shape: "drum", depth: 0.05 * L}), z0 = d.z, dock = 0.06 * L, zw = 0.046 * L, th = 0.03 * L;
    const cuts = [z0, -0.05 * L, 0.5 * (p.at * L - 0.5 * p.gap * L) , L / 2 - dock];
    for (let k = 0; k < 3; k++) {
      sh.part(`hub ${k + 1}`).region("midship").drum(k === 1 ? "hull-a" : "hull-b", hr * (k === 1 ? 1.12 : 1), [cuts[k], cuts[k + 1]], {sides: 12, facet: true});
      if (!sh.far && k) sh.drum("hull-c", 1.3 * hr, [cuts[k] - 0.004 * L, cuts[k] + 0.004 * L], {sides: 12, facet: true, chart: false});
    }
    sh.part("bow").region("bow", "dock").drum("hull-a", 2 * hr, [L / 2 - dock, L / 2], {sides: 12, facet: true, bevel: 0.35 * hr});
    y.anchors.docks.push({p: [0, 0, L / 2], n: [0, 0, 1]}); y.anchors.bridge = {p: [0, 2 * hr, L / 2 - dock / 2], n: [0, 1, 0]};
    for (let k = 0; k < p.rings; k++) {
      const R = p.ring * L * (k === 1 ? p.second : k === 2 ? p.second * p.second : 1), zc = p.at * L - k * p.gap * L, rate = (k % 2 ? -1 : 1) * (p.spin ?? Math.sqrt(9.81 / R));
      sh.part(`ring ${k + 1}`, {spin: rate, sparse: true}).region(`ring-${k + 1}`, "windows").lathe("hull-a", [[R + th / 2, zc - zw / 2], [R + th / 2, zc + zw / 2], [R - th / 2, zc + zw / 2], [R - th / 2, zc - zw / 2], [R + th / 2, zc - zw / 2]], {sides: p.sides, facet: true, name: "rim"});
      for (let i = 0; i < p.spokes; i++) { const a = (i + 0.25 * k) * TAU / p.spokes; sh.rod("hull-c", V3(hr * Math.cos(a), hr * Math.sin(a), zc), V3((R - th / 2) * Math.cos(a), (R - th / 2) * Math.sin(a), zc), 0.3 * th); }
      sh.part(`bearing ${k + 1}`).region("midship").drum("hull-c", 1.5 * hr, [zc - 0.6 * zw, zc + 0.6 * zw], {sides: 12, facet: true, chart: false});
      y.anchors.points[`ring-${k + 1}`] = {p: [0, R + th / 2, zc], n: [0, 1, 0]};
    }
    sh.part("tanks").region("tank-1", "tank");
    for (const [a, b] of ringOf(5, 2.2 * hr, 0.25)) sh.capsule("hull-tank", [a, b, -0.25 * L + 1.2 * hr], [a, b, -0.07 * L - 1.2 * hr], 1.2 * hr);
    for (let k = 0; k < 4; k++) { const a = 45 * RAD + k * TAU / 4; sh.part(`radiator ${k + 1}`, {sparse: true}).region(`radiator-${k + 1}`, "radiator").vane([hr * Math.cos(a), hr * Math.sin(a), Math.max(-0.35 * L, z0 + 0.075 * L)], [Math.cos(a), Math.sin(a), 0], p.vaneSpan * L, 0.13 * L, {taper: 0.85}); }
    sh.part("array", {sparse: true}).region("bow").dish([1.4 * hr, -1.4 * hr, L / 2 - dock / 2], [0.7, -0.7, -0.15], 0.03 * L, {mast: 0.05 * L});
    y.lamps(p.ring * L + th / 2, p.ring * L + th / 2);
  },
  // a worked asteroid: cut flat at the bow, on top and at the stern; a hangar portal built out of the bow face, a
  // polygonal collar round its waist carrying radiators, terraces on the mesa, the drive block sunk into the stern
  ark(y, p) {
    const {sh, L} = y, ax = 0.5 * p.girth * L, ay = ax * p.flat, az = 0.41 * L, cz = 0.03 * L, d = y.drive({w: 1.15 * ax, h: 0.95 * ay, count: p.bells, rows: 2, depth: 0.1 * L}), z0 = d.z, bowCut = 0.36 * L;
    sh.part("thrust plate").region("engine-block", "engine").drum("hull-b", 0.86 * Math.min(ax, ay) * 1.1, [z0 - 0.035 * L, z0 + 0.012 * L], {sides: 12, facet: true});
    sh.part("rock").region("rock", "rock").rock([0, 0, cz], [ax, ay, az], {rough: p.rough, craters: 9, cuts: [{n: [0, 0, 1], d: bowCut - cz}, {n: [0, 1, 0], d: 0.74 * ay}, {n: [0, 0, -1], d: Math.min(az * 0.92, cz - (z0 - 0.03 * L))}]});
    const mw = p.mouth * 2 * ax, mh = 0.3 * ay, f = 0.2 * Math.min(mw, mh);
    sh.part("portal").region("bow", "dock").mouth("hangar-1", [0, -0.1 * ay, L / 2], [0, 0, 1], [mw, mh, L / 2 - bowCut + 0.03 * L], {frame: f, skin: "hull-a"});
    for (const s of [1, -1]) sh.block("hull-b", [0.2 * ax, 0.56 * ay, 0.075 * L], [s * (mw / 2 + f + 0.1 * ax), -0.1 * ay, bowCut + 0.02 * L], {chamfer: 0.03 * ax, bevel: 0.03 * ax});
    y.anchors.docks.push({p: [0, 0.3 * ay, bowCut], n: [0, 0, 1]});
    const zc = cz - 0.07 * L, Rc = 1.13 * ax * Math.sqrt(1 - Math.pow((zc - cz) / az, 2)), zw = 0.04 * L, th = 0.028 * L;
    sh.part("collar", {sparse: true}).region("collar", "windows").lathe("hull-a", [[Rc + th / 2, zc - zw / 2], [Rc + th / 2, zc + zw / 2], [Rc - th / 2, zc + zw / 2], [Rc - th / 2, zc - zw / 2], [Rc + th / 2, zc - zw / 2]], {sides: 16, facet: true, name: "rim"});
    for (const [a, b] of ringOf(8, 1, 0.5)) sh.rod("hull-c", V3(a * 0.7 * ax, b * 0.7 * ay, zc), V3(a * (Rc - th / 2), b * (Rc - th / 2), zc), 0.35 * th);
    y.anchors.points.collar = {p: [Rc + th / 2, 0, zc], n: [1, 0, 0]};
    p.vaneAngles.forEach((deg, k) => { const a = deg * RAD; sh.part(`radiator ${k + 1}`, {sparse: true}).region(`radiator-${k + 1}`, "radiator").vane([(Rc + th / 2) * Math.cos(a), (Rc + th / 2) * Math.sin(a), zc], [Math.cos(a), Math.sin(a), 0], p.vaneSpan * L, 0.15 * L, {taper: 0.8}); });
    p.towers.forEach((t, k) => {
      const zt = L / 2 - t.at * L, x = t.side * 0.42 * ax, th2 = t.high * ay, wd = t.wid * ax, tl = t.len * L, top = 0.74 * ay;
      // a terrace is a stepped pile of thin wide tiers, each set back from the one below, with low annexes beside it
      sh.part(`tower ${k + 1}`).region(`tower-${k + 1}`, "windows");
      const tiers = 4, hk = (q) => hash3(k, q, 11, y.spec.seed);
      let base = top - 0.05 * ay, wk = wd, lk = tl, xk = x, zk = zt;
      for (let q = 0; q < tiers; q++) {
        const tall = (q === 0 ? 0.42 : 0.26) * 1.6 * th2 + (q === 0 ? 0.05 * ay : 0);
        sh.block(q % 2 ? "hull-a" : "hull-b", [wk, tall, lk], [xk, base + tall / 2, zk], {chamfer: 0.12 * tall, bevel: 0.1 * tall});
        base += tall; xk -= t.side * 0.09 * wk * (0.5 + hk(q)); zk += (hk(q + 5) - 0.5) * 0.24 * lk; wk *= 0.62 + 0.14 * hk(q + 9); lk *= 0.6 + 0.2 * hk(q + 13);
      }
      for (let q = 0; q < 3; q++) { const aw = wd * (0.3 + 0.3 * hk(q + 20)), al = tl * (0.3 + 0.4 * hk(q + 23)), ah = th2 * (0.25 + 0.3 * hk(q + 26)), side = q === 1 ? -1 : 1; sh.block(q === 2 ? "hull-c" : "hull-b", [aw, ah + 0.05 * ay, al], [x + (q === 2 ? 0 : side * (wd / 2 + aw * 0.45)), top + ah / 2 - 0.025 * ay, zt + (q === 2 ? 1 : hk(q + 29) - 0.5) * (q === 2 ? tl / 2 + al * 0.5 : tl * 0.7)], {chamfer: 0.1 * ah, bevel: 0.1 * ah}); }
      if (k === 0) y.anchors.bridge = {p: [x, top + 0.5 * th2, zt + tl / 2], n: [0, 0, 1]};
    });
    sh.part("mesa works", {sparse: true}).region("rock", "rock").scatter(V3(-0.42 * ax, 0.74 * ay, cz - 0.17 * L), V3(0.84 * ax, 0, 0), V3(0, 0, 0.36 * L), Y, {count: 22, size: [0.008 * L, 0.03 * L], height: [0.03 * ay, 0.1 * ay], sink: 0.4});
    y.lamps(Rc + th / 2, Rc + th / 2);
  },
  // two unequal hulls side by side, one set back: the drive hull with radiators standing up and down from it, the
  // cargo hull with container racks along its outer side; bridges between them, a hangar pod hanging from one
  twin(y, p) {
    const {sh, L, r} = y, w = p.beam * L, h = p.depth * L, gap = p.gap * L, stag = p.stagger * L, rise = p.rise * h;
    const hulls = [{x: gap / 2, y: 0, stern: -L / 2, bow: L / 2 - stag, name: "port-hull", f: 1, c: 0.28 * Math.min(w, h)}, {x: -gap / 2, y: rise, stern: -L / 2 + 0.7 * stag, bow: L / 2, name: "starboard-hull", f: p.second, c: 0.08 * Math.min(w, h)}];
    hulls.forEach((q, k) => {
      const d = y.drive({w: 0.8 * w * q.f, h: 0.72 * h * q.f, count: k ? Math.max(1, p.bells - 1) : p.bells, rows: p.bells > 3 ? 2 : 1, depth: 0.05 * L, x: q.x, y: q.y, stern: q.stern, name: `engine-block-${k + 1}`});
      const cuts = [0, range(r, 0.2, 0.3), range(r, 0.45, 0.6), range(r, 0.74, 0.84), 1].map((u) => mix(d.z, q.bow, u)), scales = [0.9, 1, 0.88, 1];
      for (let i = 0; i < 4; i++) {
        const ww = w * q.f * scales[i], hh = h * q.f * scales[i], za2 = cuts[i], zb2 = cuts[i + 1], bow = i === 3 && k === 1, bv = 0.6 * q.c + 0.03 * h;
        if (k === 1 && i === 1) {   // the cargo hull is open here: its frame and two ball tanks in plain sight
          sh.part("open bay", {sparse: true}).region("truss", "truss").truss([q.x, q.y, za2], [q.x, q.y, zb2], 0.8 * Math.min(ww, hh), {bay: 0.9});
          sh.part("bay tanks").region("tank-1", "tank");
          for (const u of [0.28, 0.72]) sh.capsule("hull-tank", [q.x, q.y, mix(za2, zb2, u)], [q.x, q.y, mix(za2, zb2, u)], Math.min(0.62 * Math.min(ww, hh), 0.2 * (zb2 - za2)));
          continue;
        }
        if (k === 0 && i === 2) {   // the crew live high on the drive hull: a block that stands above its neighbours
          sh.part("crew block").region("habitat-1", "windows").block("hull-a", [0.8 * ww, 0.5 * hh, 0.8 * (zb2 - za2)], [q.x - 0.08 * ww, q.y + 0.5 * hh + 0.2 * hh, 0.5 * (za2 + zb2)], {chamfer: 0.08 * hh, bevel: 0.1 * hh});
          sh.block("hull-b", [0.5 * ww, 0.24 * hh, 0.5 * (zb2 - za2)], [q.x - 0.16 * ww, q.y + 0.5 * hh + 0.55 * hh, mix(za2, zb2, 0.56)], {chamfer: 0.05 * hh, bevel: 0.06 * hh});
        }
        const sec = sectionOf(ww, hh, q.c * scales[i], {trench: k === 0 && i > 0 && i !== 2 ? {w: 0.3 * ww, d: 0.22 * hh} : null, slots: [1, -1].map((side) => ({side, y0: 0.08 * hh, y1: 0.2 * hh, d: 0.03 * ww}))});
        sh.part(`${q.name} ${i + 1}`).region(bow ? "bow" : q.name, bow ? "dock" : "plating").loft(i % 2 ? "hull-a" : (k ? "hull-b" : "hull-a"), sec.poly, [st(za2, [1 - 2 * bv / ww, 1 - 2 * bv / hh]), st(za2 + bv), st(zb2 - bv), st(zb2, [1 - 2 * bv / ww, 1 - 2 * bv / hh])],
          {at: move(q.x, q.y, 0), edge: (e) => ({name: sec.tags[e], ...(["wall", "floor", "slot", "back"].includes(sec.tags[e]) ? {skin: "hull-c"} : {})})});
        sh.part("deck works", {sparse: true}).scatter(V3(q.x - 0.42 * ww, q.y + hh / 2, za2 + 0.06 * (zb2 - za2)), V3(k === 0 && i > 0 ? 0.24 * ww : 0.84 * ww, 0, 0), V3(0, 0, 0.88 * (zb2 - za2)), Y, {count: 4, seed: 10 * k + i, size: [0.008 * L, 0.035 * L], height: [0.03 * h, 0.12 * h]});
      }
    });
    y.anchors.docks.push({p: [-gap / 2, rise, L / 2], n: [0, 0, 1]});
    // a yoke round both hulls near the stern: the frame the thrust of two drives is shared through
    const yz = -L / 2 + stag + 0.07 * L, yw = gap + 1.7 * w, yh = 1.9 * h + Math.abs(rise), yt = 0.26 * h, yd = 0.035 * L, ymid = rise / 2;
    sh.part("yoke").region("midship");
    for (const s of [1, -1]) { sh.block("hull-b", [yw, yt, yd], [0, ymid + s * (yh - yt) / 2, yz], {chamfer: 0.25 * yt, bevel: 0.2 * yt}); sh.block("hull-b", [yt, yh - 2 * yt, yd], [s * (yw - yt) / 2, ymid, yz], {chamfer: 0.25 * yt, bevel: 0.2 * yt, caps: [true, true]}); }
    const za = -L / 2 + stag + 0.15 * L, zb = L / 2 - stag - 0.13 * L, span = gap - 0.6 * w, bridge = (z, k) => {
      const at = basis(V3(gap, -rise, 0).normalize(), V3(rise, gap, 0).normalize(), Z.clone(), V3(0, rise / 2, z));
      sh.part(`bridge ${k + 1}`).region("midship").loft("hull-b", rect(Math.hypot(span, rise), 0.46 * h, 0.07 * h), [st(-0.027 * L, 0.9), st(-0.02 * L), st(0.02 * L), st(0.027 * L, 0.9)], {at});
    };
    const zs = Array.from({length: p.bridges}, (_, k) => (p.bridges === 1 ? 0.5 * (za + zb) : mix(za, zb, k / (p.bridges - 1))));
    zs.forEach(bridge);
    const zp = zs[Math.min(zs.length - 1, Math.ceil(zs.length / 2))], pw = 0.6 * (gap - w), pl = 0.13 * L, py = rise / 2 - 0.42 * h;
    sh.part("pod").region("midship", "windows").block("hull-a", [pw, 0.7 * h, pl], [0, py, zp + 0.01 * L], {chamfer: 0.12 * h, bevel: 0.1 * h});
    sh.part("pod mouth").region("midship", "windows").mouth("hangar-1", [0, py, zp + 0.01 * L + pl / 2 + 0.035 * L], [0, 0, 1], [0.6 * pw, 0.32 * h, 0.035 * L], {skin: "hull-b"});
    y.anchors.bridge = {p: [0, py + 0.35 * h, zp + 0.01 * L], n: [0, 1, 0]};
    [1, -1].forEach((s, k) => sh.part(`radiator ${k + 1}`, {sparse: true}).region(`radiator-${k + 1}`, "radiator").vane([gap / 2, s * 0.46 * h, -0.25 * L], [0, s, 0], p.vaneSpan * L * (s > 0 ? 1 : 0.6), 0.2 * L, {taper: 0.8}));
    const q = hulls[1], rows = sh.far ? 5 : 10, z1 = mix(q.stern, q.bow, 0.3), z2 = mix(q.stern, q.bow, 0.72), bz = (z2 - z1) / rows;
    sh.part("racks").region("cargo-1", "cargo");
    for (let i = 0; i < rows; i++) for (let j = 0; j < 2; j++) {
      const hh = hash3(i, j, 5, y.spec.seed);
      if (hh > 0.12) sh.block(hh < 0.22 ? "hull-accent" : hh < 0.6 ? "hull-b" : "hull-a", [0.16 * w, 0.3 * h * q.f, 0.88 * bz], [q.x - (0.5 * w * q.f + 0.085 * w), q.y + (j - 0.5) * 0.34 * h * q.f, z1 + (i + 0.5) * bz], {tone: 0.1, plates: false, chart: false});
    }
    y.lamps(gap / 2 + w / 2, h / 2 + rise);
  },
};

const near3 = (r, a, b, step = 0.001) => round(range(r, a, b), step);
// each family: what it is, its size, its numbers ([lowest, highest] a description may give, or the choices)
// and how a seed chooses them
const FAMILIES = {
  spine: {label: "a long open truss: the drive behind a shadow disc, radiator vanes in one plane, tank clusters, crew drums forward, a docking face as the bow",
    lengths: [1200, 2800], params: {girth: [0.012, 0.05], drum: [0.03, 0.1], drums: [1, 3], tanks: [1, 4], tankCount: [3, 8], tank: [0.6, 2], vanes: [2, 4], vaneSpan: [0.08, 0.4], bells: [3, 12], side: [-1, 1]},
    design: (r) => ({girth: near3(r, 0.02, 0.028), drum: near3(r, 0.05, 0.068), drums: whole(r, 1, 2), tanks: whole(r, 2, 3), tankCount: whole(r, 4, 6), tank: near3(r, 1.05, 1.4, 0.01), vanes: pick(r, [4, 4, 2]), vaneSpan: near3(r, 0.17, 0.25), bells: pick(r, [3, 4, 5, 7]), side: pick(r, [1, -1])})},
  carrier: {label: "a thick block with a flat deck: a trench that opens into a gulf between two blunt prongs at the bow, hangar slots along a side, low terraces, a keel block",
    lengths: [1800, 4200], params: {beam: [0.1, 0.4], depth: [0.04, 0.25], taper: [0.15, 1], trench: [0, 0.3], segments: [3, 9], hangars: [0, 4], side: [-1, 1], keel: [0, 0.6], vaneSpan: [0.03, 0.25], bells: [2, 16], towers: "list"},
    design: (r) => {
      const side = pick(r, [1, -1, 1, -1, 0]), n = whole(r, 3, 5), towers = Array.from({length: n}, (_, k) => ({at: near3(r, 0.17 + 0.42 * k / n, 0.17 + 0.42 * (k + 0.8) / n, 0.01), side: k % 2 ? (side || 1) : -(side || 1), len: near3(r, 0.1, 0.19, 0.01), wid: near3(r, 0.26, 0.36, 0.01), high: near3(r, 0.24, 0.48, 0.01)}));
      return {beam: near3(r, 0.17, 0.23), depth: near3(r, 0.07, 0.1), taper: near3(r, 0.84, 1, 0.01), trench: near3(r, 0.09, 0.13, 0.01), segments: whole(r, 5, 7), hangars: whole(r, 2, 3), side, keel: near3(r, 0.35, 0.55, 0.01), vaneSpan: near3(r, 0.08, 0.12), bells: pick(r, [8, 10, 12]), towers};
    }},
  cluster: {label: "an open frame carrying its load in plain sight: pressure balls, tanks, container stacks and gaps, a crew block high on the bow",
    lengths: [700, 1700], params: {girth: [0.08, 0.3], aspect: [0.5, 1.2], vaneSpan: [0.05, 0.3], bells: [2, 9], cells: "list"},
    design: (r) => {
      const n = whole(r, 6, 9), cells = Array.from({length: n}, () => pick(r, ["ball", "ball", "pair", "cargo", "cargo", "cross", "gap"]));
      if (!cells.includes("ball")) cells[1] = "ball";
      if (!cells.includes("cargo")) cells[n - 2] = "cargo";
      cells[0] = cells[0] === "gap" ? "pair" : cells[0];
      return {girth: near3(r, 0.13, 0.18), aspect: near3(r, 0.72, 1, 0.01), vaneSpan: near3(r, 0.12, 0.18), bells: pick(r, [4, 4, 6]), cells};
    }},
  lance: {label: "a very long thin hull behind a faceted shield, crew drum and tanks close behind it, the drive far aft on a truss among long narrow radiators",
    lengths: [2500, 6000], params: {body: [0.012, 0.06], shield: [0.08, 0.32], shieldShape: ["cone", "disc"], drum: [1, 3], boom: [0.2, 0.6], vanes: [3, 4], vaneSpan: [0.03, 0.2], bells: [1, 7]},
    design: (r) => ({body: near3(r, 0.022, 0.03), shield: near3(r, 0.15, 0.2), shieldShape: pick(r, ["cone", "cone", "disc"]), drum: near3(r, 1.7, 2.2, 0.01), boom: near3(r, 0.34, 0.44, 0.01), vanes: pick(r, [3, 3, 4]), vaneSpan: near3(r, 0.06, 0.085), bells: pick(r, [1, 3, 3])})},
  wheel: {label: "a thick hub carrying polygonal crew rings of unequal size that turn against each other, a docking drum as the bow, tanks and a cross of radiators",
    lengths: [900, 2400], params: {hub: [0.015, 0.06], ring: [0.1, 0.4], second: [0.4, 1], rings: [1, 3], gap: [0.05, 0.2], at: [0, 0.32], sides: [8, 32], spokes: [3, 12], vaneSpan: [0.04, 0.25], bells: [3, 12], spin: [-1, 1]},
    design: (r) => ({hub: near3(r, 0.026, 0.034), ring: near3(r, 0.2, 0.27), second: near3(r, 0.58, 0.74, 0.01), rings: 2, gap: near3(r, 0.09, 0.12), at: near3(r, 0.14, 0.24, 0.01), sides: pick(r, [12, 16, 16]), spokes: pick(r, [4, 6, 6]), vaneSpan: near3(r, 0.09, 0.13), bells: pick(r, [4, 5, 6])})},
  ark: {label: "a worked asteroid: cut flat at the bow, on top and at the stern, a hangar portal built out of the bow face, a polygonal collar with radiators, terraces on the mesa",
    lengths: [3000, 8000], params: {girth: [0.25, 0.6], flat: [0.6, 1], rough: [0.15, 0.6], mouth: [0.15, 0.5], vaneSpan: [0.05, 0.25], bells: [2, 12], vaneAngles: "list", towers: "list"},
    design: (r) => {
      const n = whole(r, 3, 4), towers = Array.from({length: n}, (_, k) => ({at: near3(r, 0.24 + 0.3 * k / n, 0.24 + 0.3 * (k + 0.7) / n, 0.01), side: k % 2 ? 1 : -1, len: near3(r, 0.06, 0.1, 0.01), wid: near3(r, 0.3, 0.5, 0.01), high: near3(r, 0.12, 0.24, 0.01)}));
      return {girth: near3(r, 0.38, 0.48), flat: near3(r, 0.78, 0.94, 0.01), rough: near3(r, 0.24, 0.36, 0.01), mouth: near3(r, 0.24, 0.32, 0.01), vaneSpan: near3(r, 0.07, 0.1), bells: pick(r, [6, 8]), vaneAngles: pick(r, [[205, 335], [200, 340, 20], [160, 20]]), towers};
    }},
  twin: {label: "two unequal hulls side by side, one set back: a drive hull with radiators standing from it, a cargo hull with container racks, bridges and a hangar pod between",
    lengths: [1200, 3200], params: {beam: [0.03, 0.12], depth: [0.03, 0.12], gap: [0.08, 0.35], stagger: [0, 0.25], second: [0.6, 1], rise: [-1, 1], bridges: [1, 5], vaneSpan: [0.04, 0.25], bells: [1, 6]},
    design: (r) => ({beam: near3(r, 0.075, 0.095), depth: near3(r, 0.06, 0.08), gap: near3(r, 0.18, 0.23), stagger: near3(r, 0.07, 0.14, 0.01), second: near3(r, 0.76, 0.9, 0.01), rise: near3(r, 0.3, 0.6, 0.01), bridges: whole(r, 2, 3), vaneSpan: near3(r, 0.1, 0.14), bells: pick(r, [2, 3, 4])})},
};
/** The families of hull: what each is and its usual length (metres). Each is an invented design. */
export const HULLS = Object.freeze(Object.fromEntries(Object.entries(FAMILIES).map(([k, f]) => [k, Object.freeze({label: f.label, lengths: Object.freeze(f.lengths), params: Object.freeze(Object.keys(f.params))})])));
/** What a `cells` entry of the cluster may be. */
export const CELLS = Object.freeze(["ball", "pair", "cross", "cargo", "gap"]);
const kindSeed = (kind) => [...kind].reduce((s, c) => (Math.imul(s, 31) + c.charCodeAt(0)) >>> 0, 7);
const TOWER = Object.freeze({at: [0.05, 0.95], side: [-1, 1], len: [0.02, 0.3], wid: [0.05, 0.6], high: [0.05, 1.5]});
function checked(family, name, value) {
  const rule = FAMILIES[family].params[name], where = `${family} ${name}`;
  if (rule === "list") {
    if (!Array.isArray(value)) throw fail(`${where} must be a list, got ${JSON.stringify(value)}`);
    if (name === "cells") { if (value.length < 2 || value.length > 14) throw fail("cluster cells: 2 to 14 cells"); value.forEach((c) => choice("cluster cell", c, CELLS)); }
    if (name === "towers") value.forEach((t, i) => { known(`${where}[${i}]`, t, Object.keys(TOWER)); for (const [k, [lo, hi]] of Object.entries(TOWER)) number(`${where}[${i}].${k}`, t[k], lo, hi); });
    if (name === "vaneAngles") value.forEach((a) => number(where, a, 0, 360));
    return value;
  }
  return typeof rule[0] === "string" ? choice(where, value, rule) : number(where, value, rule[0], rule[1]);
}
/** The description of a hull (plain numbers and words: what hullFrom takes): `family` (HULLS), {seed (1),
 * length (metres, 200 to 20,000; default by the seed within the family's usual lengths), age (0 new .. 1: soot
 * towards the stern, streaks), palette (PALETTES), inset (a share of the length the bells are sunk by: a way to
 * make a mistake, see problems()), and any of the family's numbers (HULLS[family].params)}. */
export function hullSpec(family, options = {}) {
  if (!FAMILIES[family]) throw fail(`no hull family "${family}"${hint(String(family), Object.keys(FAMILIES))}; families: ${Object.keys(FAMILIES).join(", ")}`);
  const F = FAMILIES[family], own = Object.keys(F.params);
  known(`hullSpec("${family}") options`, options, ["seed", "length", "age", "palette", "inset", ...own]);
  const seed = options.seed ?? 1, r = rng((seed * 2654435761 + kindSeed(family)) >>> 0), params = F.design(r);
  const length = options.length ?? round(range(r, F.lengths[0], F.lengths[1]), 10), age = options.age ?? near3(r, 0.15, 0.6, 0.01), palette = options.palette ?? pick(r, Object.keys(PALETTES));
  number("length", length, 200, 20000); number("age", age, 0, 1); choice("palette", palette, Object.keys(PALETTES)); number("inset", options.inset ?? 0, 0, 0.3);
  for (const k of own) if (options[k] !== undefined) params[k] = checked(family, k, options[k]);
  return {family, seed, length, age, palette, inset: options.inset ?? 0, ...params};
}
/** A hull from one description (hullSpec's): options are the hull kit's (accent, detail, wear, tile, plate)
 * and a craft's (name, camera, height, sun, lights, marker, occlusion). */
export function hullFrom(spec, options = {}) {
  if (!spec || !FAMILIES[spec.family]) throw fail(`hullFrom needs a description with a family (${Object.keys(FAMILIES).join(", ")}): hullSpec(family, {...})`);
  const kitKeys = [...KIT_KEYS.filter((k) => k !== "seed"), "tile", "plate"];
  known("hullFrom options", options, [...kitKeys, ...HULL_KEYS]);
  const sub = (keys) => Object.fromEntries(Object.entries(options).filter(([k]) => keys.includes(k)));
  const kit = new HullKit({accent: ACCENTS[(spec.seed + kindSeed(spec.family)) % ACCENTS.length], ...sub(kitKeys), seed: spec.seed, palette: spec.palette}), yard = new Yard(kit, spec);
  BUILD[spec.family](yard, spec);
  return new Hull(yard.sh.finish(), kit, {...sub(HULL_KEYS), name: options.name ?? `${spec.family} ${spec.seed}`, family: spec.family, seed: spec.seed, spec, anchors: yard.anchors});
}
/** A ready-made hull: `family` (HULLS: spine, carrier, cluster, lance, wheel, ark, twin), options {seed (1):
 * another member of the family for every seed; length (metres); age; palette; the family's numbers; the kit's
 * (accent, detail: "near" | "far", wear, tile, plate); a craft's (name, camera, height, sun, lights, marker)}. */
export function hull(family, options = {}) {
  if (!FAMILIES[family]) throw fail(`no hull family "${family}"${hint(String(family), Object.keys(FAMILIES))}; families: ${Object.keys(FAMILIES).join(", ")}`);
  const specKeys = ["seed", "length", "age", "palette", "inset", ...Object.keys(FAMILIES[family].params)], kitKeys = [...KIT_KEYS.filter((k) => k !== "seed"), "tile", "plate"];
  known(`hull("${family}") options`, options, [...new Set([...specKeys, ...kitKeys, ...HULL_KEYS])]);
  const sub = (keys) => Object.fromEntries(Object.entries(options).filter(([k]) => keys.includes(k)));
  return hullFrom(hullSpec(family, sub(specKeys)), sub([...kitKeys, ...HULL_KEYS]));
}
/** A fleet without designing each: `count` hulls of `family` (or of the families of a list, in turn) with
 * seeds seed, seed + 1, ..., in a loose seeded formation `spacing` metres apart (default 0.8 of the longest).
 * Options: count (5), seed (1), spacing, detail ("far"), navy (true: one maker built them: every hull has the
 * palette and the accent the fleet's seed chooses; false: each its own), and anything hull() takes for every
 * family named (a `palette` or an `accent` given here is every hull's).
 * Returns {object, hulls, update(t, options), dispose()}. */
export function hullFleet(family, options = {}) {
  const {count = 5, seed = 1, spacing = null, detail = "far", navy = true, ...rest} = options, kinds = Array.isArray(family) ? family : [family], maker = rng(seed * 977 + 3);
  const livery = navy ? {palette: pick(maker, Object.keys(PALETTES)), accent: pick(maker, ACCENTS)} : {};
  const hulls = Array.from({length: count}, (_, i) => hull(kinds[i % kinds.length], {...livery, ...rest, detail, seed: seed + i})), r = rng(seed * 613 + 17), object = new THREE.Group();
  const step = spacing ?? 0.8 * Math.max(...hulls.map((h) => h.size.length));
  hulls.forEach((c, i) => { const row = Math.floor((i + 1) / 2), side = i === 0 ? 0 : i % 2 ? 1 : -1; c.object.position.set(side * row * step * (0.85 + 0.3 * r()), (r() - 0.5) * step * 0.5, -row * step * (0.6 + 0.4 * r())); object.add(c.object); });
  object.name = "hull fleet";
  return {object, hulls, update(t, o = {}) { for (const c of hulls) c.update(t, o); return this; }, dispose() { for (const c of hulls) c.dispose(); }};
}
