// vidgen/space-hull-detail: the fine detail of a giant hull and what makes it read as kilometres long.
// Part of schu-video-generator (MIT licence); imported by a page as
// "vidgen/space-hull-detail". It dresses a hull of vidgen/space-hull.
//
//   import {hull} from "vidgen/space-hull";
//   import {dress} from "vidgen/space-hull-detail";
//   const ship = hull("carrier", {seed: 4, length: 3000});
//   const detail = dress(ship, renderer, {lights: 1});       // maps baked once (vidgen/baked), clutter, bays, lights
//   ship.update(t, {sun, throttle});                         // the hull's own update first
//   detail.update(t, {lights: 0.5 + 0.5 * ctx.music.level(t), light});   // window banks, lamps, plumes; `light`: a spaceLight
//
// What is drawn where (nothing here is a mesh per window):
// - two tiling maps per kind of surface (plating, dark metal, radiator, tank), read with the hull's `uv` in
//   metres: one for the 5 to 20 m scale (panel seams, hatches, pipe runs, vents, ribs, straps), one for the 1 to
//   5 m scale (fine panel lines, rivet rows, stencil marks, pits, worn edges). Each fades by the metres one
//   pixel covers, so nothing shimmers without antialiasing.
// - windows by the thousand, in the surface shader: rows follow the decks (the `win` attribute this module
//   computes: metres along the row, metres across the decks, the region's share), a seeded share is lit, warm
//   and cool mixed; filtered over the pixel, so a window smaller than a pixel is a steady sparkle.
// - one map on the hull's atlas (`uv1`): grime and soot, large markings, the light of hangar bays, trenches and
//   floodlights, the light of the plumes on the stern.
// - geometry by instances: deck and trench clutter, parked craft and cargo in the bays, the thrust structure
//   round the bells; navigation, guide and work lights as points; one plume per bank of bells.
// A function of the hull, its seed and vidgen's clock. No weapons. The designs are invented.
import * as THREE from "three";
import {rng} from "vidgen/music-time";
import {baked} from "vidgen/baked";
import {GLARE, PLUMES, flicker, craft as kitCraft} from "vidgen/space-craft";
import {PALETTES} from "vidgen/space-hull";

export const VERSION = 1;
const PREFIX = "vidgen/space-hull-detail";
const TAU = Math.PI * 2;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const mix = (a, b, u) => a + (b - a) * u;
const smooth = (a, b, x) => { const u = clamp((x - a) / (b - a)); return u * u * (3 - 2 * u); };
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
function number(where, value, lo, hi) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < lo || value > hi) throw fail(`${where} must be a number from ${lo} to ${hi}, got ${JSON.stringify(value)}`);
  return value;
}
const hash2 = (x, y, k = 0) => { let h = Math.imul(x | 0, 374761393) ^ Math.imul(y | 0, 668265263) ^ Math.imul(k | 0, 1274126177); h = Math.imul(h ^ (h >>> 13), 1103515245); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
function noise2(x, y, k = 0) {
  const ix = Math.floor(x), iy = Math.floor(y), f = (u) => u * u * (3 - 2 * u), fx = f(x - ix), fy = f(y - iy);
  return mix(mix(hash2(ix, iy, k), hash2(ix + 1, iy, k), fx), mix(hash2(ix, iy + 1, k), hash2(ix + 1, iy + 1, k), fx), fy);
}
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const unit = (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
const along = (o, d, s) => [o[0] + d[0] * s, o[1] + d[1] * s, o[2] + d[2] * s];
const UP = [0, 1, 0];

// ---------- the scales: what is drawn at which distance ----------
/** The two tiling maps: the metres one repeat covers, the metres a pixel may cover before the map has faded
 * ([begins, gone]) and the size of what it holds. */
export const SCALES = Object.freeze({
  mid: Object.freeze({tile: 192, fade: [2.5, 9], holds: "5 to 20 m: panel seams, hatches, pipe runs, vents, ribs, straps"}),
  fine: Object.freeze({tile: 32, fade: [0.35, 1.4], holds: "1 to 5 m: fine panel lines, rivet rows, stencil marks, pits, worn edges"}),
});
/** How much of a scale's detail is left when one pixel covers `metres` of the surface (1 .. 0): the shader's rule. */
export const fade = (scale, metres) => { const s = SCALES[scale]; if (!s) throw fail(`no scale "${scale}"${hint(scale, Object.keys(SCALES))}; scales: ${Object.keys(SCALES).join(", ")}`); return 1 - smooth(s.fade[0], s.fade[1], metres); };
/** The kinds of surface that have tiling maps, and which of the hull's surfaces read which. */
export const KINDS = Object.freeze(["plating", "metal", "radiator", "tank"]);
const KIND_OF = Object.freeze({"hull-a": "plating", "hull-b": "plating", "hull-accent": "plating", "hull-c": "metal", "hull-radiator": "radiator", "hull-tank": "tank", "hull-rock": null});

// a height field with tone and gloss, painted in metres on a tile that wraps
class Paint {
  constructor(size, metres) { this.n = size; this.k = size / metres; this.m = metres; this.h = new Float32Array(size * size); this.t = new Float32Array(size * size); this.r = new Float32Array(size * size); }
  rect(x, y, w, h, dh = 0, dt = 0, dr = 0) {
    const n = this.n, k = this.k, x0 = Math.round(x * k), y0 = Math.round(y * k), nx = Math.min(n, Math.max(1, Math.round(w * k))), ny = Math.min(n, Math.max(1, Math.round(h * k)));
    for (let j = 0; j < ny; j++) { const row = ((((y0 + j) % n) + n) % n) * n; for (let i = 0; i < nx; i++) { const q = row + ((((x0 + i) % n) + n) % n); this.h[q] += dh; this.t[q] += dt; this.r[q] += dr; } }
    return this;
  }
  frame(x, y, w, h, e, dh, dt = 0) { return this.rect(x, y, w, e, dh, dt).rect(x, y + h - e, w, e, dh, dt).rect(x, y + e, e, h - 2 * e, dh, dt).rect(x + w - e, y + e, e, h - 2 * e, dh, dt); }
  // panels by splitting: each of its own tone, a groove along two of its edges
  panels(r, x, y, w, h, least, most, seam, depth, tone) {
    if (Math.max(w, h) > 2 * least && (Math.max(w, h) > most || r() < 0.55)) {
      const cut = Math.round(mix(0.32, 0.68, r()) * Math.max(w, h) * this.k) / this.k;
      if (w >= h) { this.panels(r, x, y, cut, h, least, most, seam, depth, tone); this.panels(r, x + cut, y, w - cut, h, least, most, seam, depth, tone); }
      else { this.panels(r, x, y, w, cut, least, most, seam, depth, tone); this.panels(r, x, y + cut, w, h - cut, least, most, seam, depth, tone); }
      return this;
    }
    return this.rect(x, y, w, h, 0, (r() - 0.5) * 2 * tone * (r() < 0.12 ? 2.4 : 1), (r() - 0.5) * 0.12).rect(x, y, w, seam, -depth, -0.1).rect(x, y, seam, h, -depth, -0.1);
  }
  /** RGBA bytes: the normal's x and y, the tone (128: unchanged), the gloss (128: unchanged). */
  bytes(strength = 1) {
    const n = this.n, out = new Uint8Array(n * n * 4), at = (x, y) => this.h[((y + n) % n) * n + ((x + n) % n)];
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
      const q = y * n + x, sx = (at(x + 1, y) - at(x - 1, y)) * 0.5 * this.k * strength, sy = (at(x, y + 1) - at(x, y - 1)) * 0.5 * this.k * strength, l = 1 / Math.hypot(sx, sy, 1);
      out[4 * q] = Math.round(127.5 - 127.5 * sx * l); out[4 * q + 1] = Math.round(127.5 - 127.5 * sy * l);
      out[4 * q + 2] = Math.round(clamp(0.5 + 0.5 * this.t[q]) * 255); out[4 * q + 3] = Math.round(clamp(0.5 + 0.5 * this.r[q]) * 255);
    }
    return out;
  }
}
// numerals from a grid of three by five bars: plain figures, no alphabet of any invented world
const DIGITS = ["111101101101111", "010110010010111", "111001111100111", "111001111001111", "101101111001001", "111100111001111", "111100111101111", "111001010010010", "111101111101111", "111101111001111"];
const PAINTERS = {
  // painted plate: big panels with hatches, conduits, vents with their soot, a rib now and then
  "plating/mid"(P, r) {
    const M = P.m;
    P.panels(r, 0, 0, M, M, 7, 26, 0.38, 0.22, 0.035);
    for (let i = 0; i < 26; i++) { const w = mix(2.2, 6, r()), h = mix(2.2, 5, r()), x = r() * M, y = r() * M; P.rect(x, y, w, h, 0.08, -0.05, 0.1).frame(x, y, w, h, 0.4, 0.22, -0.12); }
    for (let i = 0; i < 9; i++) {
      const len = mix(40, 150, r()), w = mix(0.8, 1.6, r()), x = r() * M, y = r() * M, flat = r() < 0.65, n = 1 + Math.floor(r() * 3);
      for (let k = 0; k < n; k++) { if (flat) P.rect(x, y + k * 2.1 * w, len, w, 0.5, -0.1, -0.12); else P.rect(x + k * 2.1 * w, y, w, len, 0.5, -0.1, -0.12); }
      for (let s = 2; s < len; s += 7) { if (flat) P.rect(x + s, y - 0.4, 0.6, n * 2.1 * w + 0.4, 0.7, -0.16); else P.rect(x - 0.4, y + s, n * 2.1 * w + 0.4, 0.6, 0.7, -0.16); }
    }
    for (let i = 0; i < 12; i++) {
      const w = mix(4, 8, r()), h = mix(3, 6, r()), x = r() * M, y = r() * M;
      P.rect(x, y, w, h, -0.3, -0.3, 0.2).frame(x - 0.4, y - 0.4, w + 0.8, h + 0.8, 0.4, 0.25, -0.05);
      for (let s = 0.4; s < w - 0.4; s += 0.8) P.rect(x + s, y + 0.3, 0.4, h - 0.6, 0.3, 0.12);
      for (let s = 0; s < 34; s += 0.4) P.rect(x + 0.6, y - s - 0.4, w - 1.2, 0.4, 0, -0.2 * Math.exp(-s / 11));   // soot drawn out behind it
    }
    for (let i = 0; i < 4; i++) P.rect(0, (i + r() * 0.5) * M / 4, M, 1.1, 0.3, 0.03, -0.05);
    for (let i = 0; i < 14; i++) { const len = mix(8, 30, r()), x = r() * M, y = r() * M; if (r() < 0.5) P.rect(x, y, len, 0.2, 0.25, 0.1); else P.rect(x, y, 0.2, len, 0.25, 0.1); }
    return 1.3;
  },
  // the small scale: panel lines, rivet rows, stencil marks (bars: a tile is seen from both sides, so no figures), pits, worn edges, hand holds
  "plating/fine"(P, r) {
    const M = P.m;
    P.panels(r, 0, 0, M, M, 1.3, 4.6, 0.07, 0.035, 0.022);
    for (let i = 0; i < 46; i++) { const len = mix(1.5, 7, r()), x = r() * M, y = r() * M, flat = r() < 0.5; for (let s = 0; s < len; s += 0.38) P.rect(flat ? x + s : x, flat ? y : y + s, 0.09, 0.09, 0.04, -0.14, -0.2); }
    for (let i = 0; i < 12; i++) { const x = r() * M, y = r() * M; const n = 3 + Math.floor(r() * 5), flat = r() < 0.5; for (let k = 0; k < n; k++) { const len = mix(0.4, 1.3, r()), dt = r() < 0.3 ? 0.22 : -0.3; if (flat) P.rect(x + k * 0.5, y, 0.28, len, 0, dt); else P.rect(x, y + k * 0.5, len, 0.28, 0, dt); } }
    for (let i = 0; i < 420; i++) { const s = r() < 0.2 ? 0.14 : 0.07; P.rect(r() * M, r() * M, s, s, -0.03, -0.2, 0.15); }
    for (let i = 0; i < 40; i++) { const len = mix(0.8, 3.2, r()), x = r() * M, y = r() * M; if (r() < 0.5) P.rect(x, y, len, 0.1, 0, 0.16, -0.25); else P.rect(x, y, 0.1, len, 0, 0.16, -0.25); }
    for (let i = 0; i < 18; i++) { const x = r() * M, y = r() * M, w = mix(0.6, 1.1, r()); P.rect(x, y, w, w, 0.02, -0.06).frame(x, y, w, w, 0.07, 0.05, -0.1).rect(x + 0.2 * w, y + 0.45 * w, 0.6 * w, 0.07, 0.07, 0.1); }
    return 1.1;
  },
  // dark structure: pipe bundles, gratings, machine boxes
  "metal/mid"(P, r) {
    const M = P.m;
    P.panels(r, 0, 0, M, M, 5, 18, 0.32, 0.3, 0.07);
    for (let i = 0; i < 14; i++) {
      const len = mix(50, M, r()), w = mix(0.7, 1.8, r()), x = r() * M, y = r() * M, flat = r() < 0.75, n = 2 + Math.floor(r() * 5);
      for (let k = 0; k < n; k++) { if (flat) P.rect(x, y + k * 1.7 * w, len, w, 0.7, 0.1 * (r() - 0.3), -0.2); else P.rect(x + k * 1.7 * w, y, w, len, 0.7, 0.1 * (r() - 0.3), -0.2); }
      for (let s = 3; s < len; s += 9) { if (flat) P.rect(x + s, y - 0.5, 0.8, n * 1.7 * w + 0.6, 1, -0.2); else P.rect(x - 0.5, y + s, n * 1.7 * w + 0.6, 0.8, 1, -0.2); }
    }
    for (let i = 0; i < 30; i++) { const w = mix(3, 11, r()), h = mix(3, 9, r()), x = r() * M, y = r() * M; P.rect(x, y, w, h, mix(0.4, 1.4, r()), 0.16 * (r() - 0.5), 0.1).frame(x, y, w, h, 0.4, 0.2, -0.1); }
    for (let i = 0; i < 10; i++) { const w = mix(8, 20, r()), h = mix(6, 14, r()), x = r() * M, y = r() * M; P.rect(x, y, w, h, -0.25, -0.2, 0.2); for (let s = 0; s < w; s += 1.1) P.rect(x + s, y, 0.38, h, 0.3, 0.1); }
    return 1.3;
  },
  "metal/fine"(P, r) {
    const M = P.m;
    P.panels(r, 0, 0, M, M, 1.6, 5, 0.09, 0.05, 0.05);
    for (let i = 0; i < 9; i++) { const w = mix(3, 8, r()), h = mix(2, 6, r()), x = r() * M, y = r() * M; P.rect(x, y, w, h, -0.04, -0.12); for (let s = 0; s < w; s += 0.36) P.rect(x + s, y, 0.1, h, 0.06, 0.1); for (let s = 0; s < h; s += 0.36) P.rect(x, y + s, w, 0.1, 0.06, 0.1); }
    for (let i = 0; i < 26; i++) { const len = mix(3, 14, r()), x = r() * M, y = r() * M; if (r() < 0.6) P.rect(x, y, len, 0.22, 0.14, 0.08, -0.25); else P.rect(x, y, 0.22, len, 0.14, 0.08, -0.25); }
    for (let i = 0; i < 300; i++) P.rect(r() * M, r() * M, 0.1, 0.1, 0.05, 0.16, -0.3);
    for (let i = 0; i < 160; i++) P.rect(r() * M, r() * M, 0.1, 0.1, -0.03, -0.22, 0.2);
    return 1.1;
  },
  // radiator panels: a grid of panels, a feed pipe along each, fins
  "radiator/mid"(P, r) {
    const M = P.m, nx = 12, ny = 8, w = M / nx, h = M / ny;
    for (let i = 0; i < nx; i++) for (let j = 0; j < ny; j++) { const x = i * w, y = j * h; P.rect(x, y, w, h, 0, (r() - 0.5) * 0.08 * (r() < 0.08 ? 3 : 1)).rect(x, y, w, 0.45, -0.3, -0.16).rect(x, y, 0.45, h, -0.3, -0.16).rect(x + 0.5 * w - 0.5, y, 1, h, 0.5, -0.08, -0.2); }
    for (let j = 0; j < ny; j++) P.rect(0, j * h + 0.5 * h, M, 1.4, 0.6, -0.12, -0.2);
    for (let i = 0; i < 90; i++) P.rect(r() * M, r() * M, 0.8, 0.8, 0.3, -0.14);
    return 1.2;
  },
  "radiator/fine"(P, r) {
    const M = P.m;
    for (let s = 0; s < M; s += 0.5) P.rect(s, 0, 0.19, M, 0.07, 0.07, -0.1);
    for (let s = 0; s < M; s += 4) P.rect(0, s, M, 0.16, 0.1, -0.12);
    for (let i = 0; i < 90; i++) P.rect(r() * M, r() * M, 0.22, 0.22, 0.05, -0.2);
    for (let i = 0; i < 120; i++) P.rect(r() * M, r() * M, 0.09, 0.09, -0.02, -0.25, 0.2);
    return 1;
  },
  // an insulated tank: straps, quilted blankets, a feed line, frost
  "tank/mid"(P, r) {
    const M = P.m;
    for (let s = 0; s < M; s += 8) P.rect(0, s, M, 0.3, -0.12, -0.07);
    for (let s = 0; s < M; s += 12) P.rect(s, 0, 0.3, M, -0.12, -0.07);
    for (let s = 0; s < M; s += 24) P.rect(0, s + 3, M, 1.5, 0.35, -0.16, -0.25);
    P.rect(M * 0.3, 0, 1.6, M, 0.8, -0.12, -0.2).rect(M * 0.3 + 3, 0, 0.8, M, 0.6, -0.1, -0.2);
    for (let s = 2; s < M; s += 12) P.rect(M * 0.3 - 0.6, s, 5.2, 0.8, 1, -0.2);
    for (let i = 0; i < 60; i++) { const w = mix(2, 9, r()); P.rect(r() * M, r() * M, w, mix(1, 5, r()), 0, 0.07 * r()); }
    return 1.1;
  },
  "tank/fine"(P, r) {
    const M = P.m;
    for (let s = 0; s < M; s += 1) P.rect(0, s, M, 0.07, -0.03, -0.06);
    for (let s = 0; s < M; s += 2) P.rect(s, 0, 0.07, M, -0.03, -0.06);
    for (let i = 0; i < 260; i++) P.rect(r() * M, r() * M, 0.1, 0.1, 0.02, 0.14);
    for (let i = 0; i < 8; i++) { const x = r() * M, y = r() * M; for (let k = 0; k < 4; k++) P.rect(x + k * 0.45, y, 0.25, mix(0.4, 1, r()), 0, -0.3); }
    return 1;
  },
};
/** A tiling map as numbers: `kind` (KINDS), `scale` ("mid" | "fine"), `size` texels. Returns {data: RGBA bytes
 * (the normal's x and y, the tone, the gloss; 128 is "unchanged"), size, tile (metres a repeat covers)}. */
export function detailMap(kind, scale, size = 1024) {
  if (!KINDS.includes(kind)) throw fail(`no kind of surface "${kind}"${hint(String(kind), KINDS)}; kinds: ${KINDS.join(", ")}`);
  const s = SCALES[scale];
  if (!s) throw fail(`no scale "${scale}"${hint(String(scale), Object.keys(SCALES))}; scales: ${Object.keys(SCALES).join(", ")}`);
  const P = new Paint(size, s.tile), strength = PAINTERS[`${kind}/${scale}`](P, rng(KINDS.indexOf(kind) * 97 + (scale === "mid" ? 11 : 53)));
  return {data: P.bytes(strength), size, tile: s.tile};
}

// ---------- windows ----------
/** The share of a region's wall cells that carry a bank of windows, by what the region is (a key of the hull
 * module's SURFACES): crew decks are dense, plate has a few ports, tanks, radiators and engines have none. */
export const WINDOWS = Object.freeze({windows: 0.82, dock: 0.3, plating: 0.24, trench: 0.3, rock: 0.05, cargo: 0.05, hangar: 0, radiator: 0, engine: 0, tank: 0, shield: 0, truss: 0});
const NO_WINDOW_SKINS = ["hull-radiator", "hull-tank", "hull-truss", "hull-glass", "hull-void"];
/** The share of banks with windows on a face of surface `skin` in a region whose detail is `detail`. */
export const windowShare = (detail, skin = "hull-a") => (NO_WINDOW_SKINS.includes(skin) ? 0 : WINDOWS[detail] ?? 0);
const WINDOW = Object.freeze({floor: 3.5, pitch: 3.2, size: [1.25, 0.95], lit: 0.36, watch: 0.4, warm: 0.68, cool: 0.22, gain: 2.2, lift: 2.6, bank: [9, 3]});
/** Where a wall's point lies among the decks: [metres along the row, metres across the decks, usable (0 | 1)].
 * A flat face: decks are level (rows of the hull's y), and a face that looks up or down has none. A round
 * face (`round`: its axis): rows run round it, taken from its `uv`; its end faces have none. */
export function windowCoords(p, normal, {round = null, uv = null} = {}) {
  if (round) return Math.abs(dot(normal, round)) > 0.7 ? [0, 0, 0] : [uv[0], uv[1], 1];
  if (Math.abs(normal[1]) > 0.7) return [0, 0, 0];
  return [dot(p, unit(cross(UP, normal))), p[1], 1];
}
/** Which windows exist and which are lit, for a tile of `size` by `size` window places: {watch, rest: RGBA
 * bytes (the light of the windows that stay lit through the night watch, with whether a window exists in
 * alpha; the light of those that come on with `lights`), exist, lit (shares)}. Lit windows cluster by rooms;
 * a run of windows shares its colour: warm, some cool, a few white. */
export function windowCells(seed = 1, {size = 256, lit = WINDOW.lit, watch = WINDOW.watch, warm = WINDOW.warm, cool = WINDOW.cool} = {}) {
  const a = new Uint8Array(size * size * 4), b = new Uint8Array(size * size * 4);
  let exist = 0, on = 0;
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const q = 4 * (y * size + x), there = hash2(x, y, seed + 1) < 0.86 && hash2(x >> 3, y, seed + 2) > 0.1;
    if (!there) continue;
    exist++; a[q + 3] = 255;
    const room = 0.25 + 1.5 * noise2(x / 7 + 3, y / 2.5 + 9, seed + 3), isLit = hash2(x, y, seed + 4) < lit * room;
    if (!isLit) continue;
    on++;
    const run = hash2((x + Math.floor(6 * hash2(0, y, seed + 5))) >> 2, y, seed + 6), c = run < warm ? [1, 0.7 + 0.1 * hash2(x, y, seed + 7), 0.4] : run < warm + cool ? [0.68, 0.84, 1] : [1, 0.96, 0.9];
    const k = 255 * (0.45 + 0.55 * hash2(x, y, seed + 8)), out = hash2(x, y, seed + 9) < watch ? a : b;
    out[q] = c[0] * k; out[q + 1] = c[1] * k; out[q + 2] = c[2] * k; if (out === b) b[q + 3] = 255;
  }
  return {watch: a, rest: b, size, exist: exist / (size * size), lit: on / Math.max(1, exist)};
}

// ---------- what is unique to one hull: marks, floodlights, the light of bays and plumes, grime ----------
const chartPlace = (c, p) => { const d = [p[0] - c.origin[0], p[1] - c.origin[1], p[2] - c.origin[2]]; return [dot(d, c.du), dot(d, c.dv)]; };
const chartPoint = (c, cu, cv) => [c.origin[0] + c.du[0] * cu + c.dv[0] * cv, c.origin[1] + c.du[1] * cu + c.dv[1] * cv, c.origin[2] + c.du[2] * cu + c.dv[2] * cv];
// the frame a mark is drawn in on a flat chart: "up" is the hull's up on a wall, the bow on a deck
function markFrame(c, up3 = null) {
  const up = up3 ?? (Math.abs(c.normal[1]) > 0.7 ? [0, 0, 1] : UP), right = cross(up, c.normal);
  return {up: [dot(up, c.du), dot(up, c.dv)], right: [dot(right, c.du), dot(right, c.dv)]};
}
const bayFrame = (h) => ({t: unit(cross(UP, h.n)), n: h.n, p: h.p, w: h.width, h: h.height, d: h.depth});
/** Is `p` inside the hangar bay `h` (an anchor of anchors.hangars), with `m` metres to spare? */
export function inBay(h, p, m = 2) {
  const f = bayFrame(h), d = [p[0] - f.p[0], p[1] - f.p[1], p[2] - f.p[2]], out = dot(d, f.n);
  return out <= m && out >= -f.d - m && Math.abs(dot(d, f.t)) <= f.w / 2 + m && Math.abs(d[1]) <= f.h / 2 + m;
}
const regionOf = (hull, chart) => hull.regions.find((g) => g.name === chart.region);
/** The large marks of a hull, as rectangles on its charts: [{chart, c: [cu, cv], right, up, a, b}] (centre,
 * the two directions and half sizes, metres in the chart). Hull numbers on the largest wall of each side with
 * a bar under them, a threshold line, landing boxes and a figure on every bay's floor, pads with a cross and a
 * figure and a dashed line on the decks. Figures are plain numerals. */
export function markPlan(hull) {
  const out = [], L = hull.size.length, seed = hull.spec?.seed ?? 1, flat = hull.charts.filter((c) => c.kind === "plane");
  const rect = (c, f, x, y, a, b, o = [0, 0]) => out.push({chart: c.id, c: [o[0] + f.right[0] * x + f.up[0] * y, o[1] + f.right[1] * x + f.up[1] * y], right: f.right, up: f.up, a, b});
  const figure = (c, f, d, x, y, h, o) => { const cell = h / 5; for (let row = 0; row < 5; row++) for (let col = 0; col < 3; col++) if (DIGITS[d][row * 3 + col] === "1") rect(c, f, x + (col - 1) * cell, y + (2 - row) * cell, cell * 0.52, cell * 0.52, o); };
  const box = (c, f, x, y, a, b, t, o) => { rect(c, f, x, y - b, a, t, o); rect(c, f, x, y + b, a, t, o); rect(c, f, x - a, y, t, b, o); rect(c, f, x + a, y, t, b, o); };
  for (const side of [1, -1]) {
    const walls = flat.filter((c) => c.normal[0] * side > 0.8 && Math.min(...c.size) >= 50 && ["plating", "windows", "dock"].includes(regionOf(hull, c).detail) && !hull.anchors.hangars.some((h) => inBay(h, chartPoint(c, c.size[0] / 2, c.size[1] / 2))));
    const c = walls.sort((p, q) => q.size[0] * q.size[1] - p.size[0] * p.size[1])[0];
    if (!c) continue;
    const f = markFrame(c), tall = Math.abs(f.up[0]) > 0.5 ? c.size[0] : c.size[1], wide = Math.abs(f.up[0]) > 0.5 ? c.size[1] : c.size[0], h = clamp(0.3 * tall, 12, 0.03 * L), o = [c.size[0] / 2, c.size[1] / 2], x0 = 0, n = 10 + ((seed * 37 + 11) % 89);
    const shift = (hash2(seed, side, 3) - 0.5) * 0.4 * wide;
    figure(c, f, Math.floor(n / 10), x0 + shift - 2.2 * h / 5, 0.12 * tall, h, o); figure(c, f, n % 10, x0 + shift + 2.2 * h / 5, 0.12 * tall, h, o);
    rect(c, f, x0 + shift, 0.12 * tall - 0.78 * h, 1.6 * h, h * 0.07, o);
  }
  hull.anchors.hangars.forEach((bay, k) => {
    const b = bayFrame(bay);
    for (const c of flat.filter((q) => q.normal[1] > 0.7 && inBay(bay, chartPoint(q, q.size[0] / 2, q.size[1] / 2), 6))) {
      const f = markFrame(c, b.n.map((v) => -v)), o = chartPlace(c, [b.p[0], b.p[1] - b.h / 2, b.p[2]]), spots = clamp(Math.round(b.w / 120), 1, 5), line = clamp(b.d * 0.012, 1.2, 2.6);
      rect(c, f, 0, 0.1 * b.d, 0.47 * b.w, line * 1.6, o);
      for (let i = 0; i < spots; i++) {
        const x = (i + 0.5 - spots / 2) * (0.8 * b.w / spots), a = Math.min(0.26 * b.w / spots, 34), d = Math.min(0.2 * b.d, 28);
        box(c, f, x, 0.52 * b.d, a, d, line, o);
        for (let s = 0.16 * b.d; s < 0.52 * b.d - d - 4; s += 9) rect(c, f, x, s, line * 0.6, 3, o);
      }
      figure(c, f, (k + 1) % 10, -0.4 * b.w, 0.52 * b.d, Math.min(0.3 * b.d, 30), o);
    }
  });
  for (const c of flat.filter((q) => q.normal[1] > 0.9 && q.size[0] >= 110 && q.size[1] >= 110 && ["plating", "windows", "dock"].includes(regionOf(hull, q).detail) && !hull.anchors.hangars.some((h) => inBay(h, chartPoint(q, q.size[0] / 2, q.size[1] / 2), 6)))) {
    const f = markFrame(c), o = [c.size[0] / 2, c.size[1] / 2], pad = clamp(0.16 * Math.min(...c.size), 18, 42), wide = Math.abs(f.up[0]) > 0.5 ? c.size[1] : c.size[0], long = Math.abs(f.up[0]) > 0.5 ? c.size[0] : c.size[1];
    if (hash2(c.id, seed, 21) < 0.6) {
      const x = (hash2(c.id, seed, 22) - 0.5) * 0.5 * wide, y = (hash2(c.id, seed, 23) - 0.5) * 0.5 * long;
      box(c, f, x, y, pad, pad, 1.4, o); rect(c, f, x, y, pad * 0.6, 1, o); rect(c, f, x, y, 1, pad * 0.6, o);
      figure(c, f, (c.id * 7 + seed) % 10, x + pad * 1.5, y, pad * 0.9, o);
    }
    const x = (hash2(c.id, seed, 24) < 0.5 ? -1 : 1) * 0.4 * wide;
    for (let s = -0.44 * long; s < 0.44 * long; s += 26) rect(c, f, x, s, 1.1, 7, o);
  }
  return out;
}
/** The floodlights of a hull: [{chart, c: [cu, cv], dir: [du, dv], reach, p: [x, y, z]}]: a lamp close over a
 * wall whose light runs out along it, on the larger walls of plated and windowed regions, and one under each
 * hull number. */
export function floodPlan(hull) {
  const out = [], seed = hull.spec?.seed ?? 1;
  for (const c of hull.charts) {
    if (c.kind !== "plane" || Math.abs(c.normal[1]) > 0.5 || Math.min(...c.size) < 70 || Math.max(...c.size) < 160) continue;
    if (!["plating", "windows", "dock"].includes(regionOf(hull, c).detail) || hull.anchors.hangars.some((h) => inBay(h, chartPoint(c, c.size[0] / 2, c.size[1] / 2), 6))) continue;
    const n = Math.min(3, Math.round(c.size[0] * c.size[1] / 140000 + hash2(c.id, seed, 31) - 0.35)), f = markFrame(c);
    for (let i = 0; i < n; i++) {
      const cu = mix(0.15, 0.85, hash2(c.id, i, seed + 32)) * c.size[0], cv = mix(0.15, 0.85, hash2(c.id, i, seed + 33)) * c.size[1], s = hash2(c.id, i, seed + 34), dir = s < 0.45 ? f.up : s < 0.7 ? f.up.map((v) => -v) : f.right.map((v) => (s < 0.85 ? v : -v));
      out.push({chart: c.id, c: [cu, cv], dir, reach: mix(70, 150, hash2(c.id, i, seed + 35)), p: along(chartPoint(c, cu, cv), c.normal, 3)});
    }
  }
  return out;
}
/** The map on a hull's atlas, as numbers: RGBA bytes, `size` square. R: grime (128: none; soot behind the bells,
 * streaks along the hull, drips down the walls, by the hull's age), G: marks (markPlan), B: fixed light (the
 * inside of hangar bays and its spill round their mouths, pools along a trench, floodlit patches), A: the light
 * of the plumes on what faces them. `hull`: {charts, regions, anchors, size, spec} (a Hull or its plain numbers). */
export function uniqueMap(hull, size = 2048) {
  const data = new Uint8Array(size * size * 4), seed = hull.spec?.seed ?? 1, age = hull.spec?.age ?? 0.4, bays = hull.anchors.hangars, bells = hull.anchors.bells;
  for (let i = 0; i < size * size; i++) data[4 * i] = 128;
  const floods = floodPlan(hull), marks = markPlan(hull);
  // texels of chart c with their place in the chart: f(index, cu, cv)
  const span = (c, cu0, cu1, cv0, cv1, f) => {
    const [a0, a1, b0, b1] = c.turned ? [cv0, cv1, cu0, cu1] : [cu0, cu1, cv0, cv1];
    const i0 = Math.max(0, Math.floor((c.rect[0] + a0 * c.scale) * size - 0.5)), i1 = Math.min(size - 1, Math.ceil((c.rect[0] + a1 * c.scale) * size - 0.5));
    const j0 = Math.max(0, Math.floor((c.rect[1] + b0 * c.scale) * size - 0.5)), j1 = Math.min(size - 1, Math.ceil((c.rect[1] + b1 * c.scale) * size - 0.5));
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) { const a = ((i + 0.5) / size - c.rect[0]) / c.scale, b = ((j + 0.5) / size - c.rect[1]) / c.scale; if (c.turned) f(4 * (j * size + i), b, a); else f(4 * (j * size + i), a, b); }
  };
  for (const c of hull.charts) {
    const region = regionOf(hull, c), [w, h] = c.size, plane = c.kind === "plane", engine = region.detail === "engine", trench = region.detail === "trench", wall = plane && Math.abs(c.normal[1]) < 0.5;
    const lengthwise = plane ? Math.abs(c.dv[2]) >= Math.abs(c.du[2]) : true, centre = plane ? chartPoint(c, w / 2, h / 2) : null, reach = 0.5 * Math.hypot(w, h);
    const near = plane ? bells.filter((b) => Math.hypot(b.p[0] - centre[0], b.p[1] - centre[1], b.p[2] - centre[2]) < reach + 14 * b.radius) : [];
    const frame = plane ? markFrame(c) : null, mine = floods.filter((f) => f.chart === c.id), lit = plane ? bays.filter((b) => Math.hypot(b.p[0] - centre[0], b.p[1] - centre[1], b.p[2] - centre[2]) < reach + b.width + b.depth) : [];
    span(c, 0, w, 0, h, (q, cu, cv) => {
      const s = lengthwise ? cv : cu, a = lengthwise ? cu : cv;
      let grime = 0.5 - age * (0.14 * (noise2(s / 130 + c.id, a / 9, seed) - 0.4) + 0.08 * (noise2(s / 31, a / 4 + c.id, seed + 1) - 0.5)), light = 0, hot = engine && !plane ? 0.3 : 0;
      if (wall) { const y = frame.up[0] * cu + frame.up[1] * cv, x = frame.right[0] * cu + frame.right[1] * cv, col = noise2(x / 3.5 + c.id, 0.5, seed + 2); grime -= age * 0.16 * smooth(0.62, 0.9, col) * noise2(x / 3.5, y / 70, seed + 3); }
      if (engine) grime -= 0.1;
      if (plane) {
        const p = chartPoint(c, cu, cv);
        for (const b of near) {
          const base = [b.p[0], b.p[1], b.p[2] + b.radius * 3], d = Math.hypot(p[0] - base[0], p[1] - base[1], p[2] - base[2]);
          grime -= 0.2 * Math.exp(-d / (2.4 * b.radius));
          const src = [b.p[0], b.p[1], b.p[2] - 2.5 * b.radius], v = [src[0] - p[0], src[1] - p[1], src[2] - p[2]], l = Math.hypot(v[0], v[1], v[2]) || 1, facing = Math.max(0, dot(c.normal, v) / l);
          hot += 2.2 * b.radius * b.radius / (l * l + b.radius * b.radius) * (0.15 + 0.85 * facing);
        }
        for (const b of lit) {
          const f = bayFrame(b), d = [p[0] - f.p[0], p[1] - f.p[1], p[2] - f.p[2]], out = dot(d, f.n), x = dot(d, f.t), y = d[1];
          if (out <= 2 && out >= -f.d - 2 && Math.abs(x) <= f.w / 2 + 2 && Math.abs(y) <= f.h / 2 + 2) {
            const strips = 0.5 + 0.5 * Math.cos(TAU * x / Math.max(24, f.w / Math.round(f.w / 40))), deep = clamp(-out / f.d);
            light = Math.max(light, (0.42 + 0.4 * strips * strips) * (1 - 0.35 * deep) * (c.normal[1] < -0.7 ? 1.25 : 1));
          } else if (out > -4) {
            const dx = Math.max(0, Math.abs(x) - f.w / 2), dy = Math.max(0, Math.abs(y) - f.h / 2), far = Math.hypot(dx, dy, Math.max(0, out));
            light = Math.max(light, 0.34 * Math.exp(-far / (0.1 * f.h + 5)));
          }
        }
      }
      if (trench) light = Math.max(light, 0.12 + 0.5 * Math.pow(Math.max(0, Math.cos(TAU * s / 46)), 10));
      for (const f of mine) {
        const dx = cu - f.c[0], dy = cv - f.c[1], al = dx * f.dir[0] + dy * f.dir[1], ac = Math.abs(dx * f.dir[1] - dy * f.dir[0]);
        if (al > -4) light = Math.max(light, 0.95 * Math.exp(-Math.pow(ac / (0.22 * Math.max(al, 0) + 5), 2)) * smooth(-4, 6, al) * Math.exp(-Math.max(al, 0) / f.reach));
      }
      data[q] = Math.round(clamp(grime) * 255); data[q + 2] = Math.round(clamp(light) * 255); data[q + 3] = Math.round(clamp(hot) * 255);
    });
  }
  for (const m of marks) {
    const c = hull.charts[m.chart], ex = Math.abs(m.right[0]) * m.a + Math.abs(m.up[0]) * m.b, ey = Math.abs(m.right[1]) * m.a + Math.abs(m.up[1]) * m.b, texel = 1 / (c.scale * size);
    if (m.c[0] + ex < 0 || m.c[0] - ex > c.size[0] || m.c[1] + ey < 0 || m.c[1] - ey > c.size[1]) continue;
    span(c, Math.max(0, m.c[0] - ex - texel), Math.min(c.size[0], m.c[0] + ex + texel), Math.max(0, m.c[1] - ey - texel), Math.min(c.size[1], m.c[1] + ey + texel), (q, cu, cv) => {
      const dx = cu - m.c[0], dy = cv - m.c[1], x = Math.abs(dx * m.right[0] + dy * m.right[1]), y = Math.abs(dx * m.up[0] + dy * m.up[1]);
      data[q + 1] = Math.max(data[q + 1], Math.round(255 * clamp((m.a - x) / texel + 0.5) * clamp((m.b - y) / texel + 0.5)));
    });
  }
  return data;
}

// ---------- lamps and clutter, as numbers ----------
const LAMP_KINDS = Object.freeze({steady: 0, strobe: 1, beacon: 2, chase: 3, work: 4});
const RED = [1, 0.1, 0.06], GREEN = [0.1, 1, 0.3], WHITE = [1, 0.96, 0.88], AMBER = [1, 0.62, 0.2], COOL = [0.75, 0.88, 1];
/** The lamps of a hull: [{p, color: [r, g, b] (linear), size (metres across its glow), kind: steady | strobe |
 * beacon | chase | work, phase}]: red along the port side and green along the starboard (from the profile),
 * white at bow and stern, strobes at the top and bottom, a beacon on every tower, guide rows at each hangar's
 * mouth (amber along the sill, white pairs running into the bay), a lamp at every floodlight. */
export function navLights(hull) {
  const out = [], L = hull.size.length, nav = clamp(0.0045 * L, 5, 24), prof = hull.profile, add = (p, color, size, kind = "steady", phase = 0) => out.push({p, color, size, kind, phase});
  const step = Math.max(1, Math.round(prof.length / 9));
  for (let i = Math.floor(step / 2); i < prof.length; i += step) { const s = prof[i]; add([s.x[1] + 4, s.y[1] - 0.1 * (s.y[1] - s.y[0]), s.z], RED, nav); add([s.x[0] - 4, s.y[1] - 0.1 * (s.y[1] - s.y[0]), s.z], GREEN, nav); }   // just off the hull, near its upper edge
  const end = prof[prof.length - 1], start = prof[0];
  add([0.5 * (end.x[0] + end.x[1]), end.y[1] + 3, end.z], WHITE, nav); add([0.5 * (start.x[0] + start.x[1]), start.y[1] + 3, start.z], WHITE, nav * 1.2);
  add([0, hull.size.height / 2 + 4, 0.22 * L], WHITE, nav * 2.2, "strobe", 0); add([0, -hull.size.height / 2 - 4, -0.2 * L], WHITE, nav * 2.2, "strobe", 0.5);
  for (const g of hull.regions.filter((q) => /^tower/.test(q.name))) add([g.centre[0], g.box.max[1] + 2, g.centre[2]], RED, nav * 1.3, "beacon", hash2(g.centre[2] | 0, 3, 5));
  hull.anchors.hangars.forEach((h, k) => {
    const f = bayFrame(h), n = clamp(Math.round(f.w / 16), 4, 40), floor = f.p[1] - f.h / 2 + 0.6;
    for (let i = 0; i <= n; i++) { const p = along(f.p, f.t, (i / n - 0.5) * f.w * 0.96); add([p[0] + f.n[0] * 1.5, floor, p[2] + f.n[2] * 1.5], AMBER, 3.2); add([p[0] + f.n[0] * 1.5, f.p[1] + f.h / 2 - 0.6, p[2] + f.n[2] * 1.5], COOL, 2.6); }
    const rows = clamp(Math.round(f.w / 120), 1, 5), m = 9;
    for (let r = 0; r < rows; r++) for (const side of [-1, 1]) for (let i = 0; i < m; i++) {
      const x = (r + 0.5 - rows / 2) * (0.8 * f.w / rows) + side * Math.min(0.2 * f.w / rows, 26), p = along(along(f.p, f.t, x), f.n, -(0.04 + 0.4 * i / (m - 1)) * f.d);
      add([p[0], floor, p[2]], WHITE, 3, "chase", (i / m + 0.13 * k) % 1);
    }
  });
  for (const f of floodPlan(hull)) add(f.p, WHITE, 6);
  return out;
}
/** The clutter on a hull's decks and in its trench, as boxes standing on charts: [{chart, p (the foot's middle),
 * s: [along the chart's width, out of the face, along its length], kind: box | pipe | stack | mast | dish,
 * tone}]: low boxes in clusters, long pipe runs, a few tall stacks, masts and small dishes: a town seen from
 * above. `density`: 1 is about one piece every 42 m both ways; `most`: the largest number. */
export function clutterPlan(hull, {density = 1, most = 5000} = {}) {
  const out = [], seed = (hull.spec?.seed ?? 1) * 31 + 7;
  const decks = hull.charts.filter((c) => c.kind === "plane" && Math.min(...c.size) >= 28 && ((c.normal[1] > 0.9 && ["plating", "windows", "dock", "trench", "cargo"].includes(regionOf(hull, c).detail)) || regionOf(hull, c).detail === "trench") && !hull.anchors.hangars.some((h) => inBay(h, chartPoint(c, c.size[0] / 2, c.size[1] / 2), 6)));
  const total = decks.reduce((s, c) => s + c.size[0] * c.size[1], 0), per = Math.min(density / (34 * 34), most / Math.max(1, total));
  for (const c of decks) {
    const [w, h] = c.size, wall = c.normal[1] < 0.5, trench = regionOf(hull, c).detail === "trench", n = Math.round(w * h * per * (trench ? 2.2 : 1)), long = h >= w, clusters = Math.max(1, Math.round(n / 12)), mu = 0.07 * w + 3, mv = 0.07 * h + 3;
    for (let i = 0; i < n; i++) {
      const g = (k) => hash2(c.id * 4099 + i, k, seed), cl = Math.floor(g(1) * clusters), ccu = mix(mu, w - mu, hash2(c.id, cl, seed + 1)), ccv = mix(mv, h - mv, hash2(c.id, cl, seed + 2));
      const gauss = (k) => (g(k) + g(k + 1) + g(k + 2) - 1.5) * 1.2, kindRoll = g(9);
      let cu = clamp(ccu + gauss(10) * 40, mu, w - mu), cv = clamp(ccv + gauss(13) * 40, mv, h - mv), s, kind;
      if (kindRoll < 0.16 || (wall && kindRoll < 0.7)) { const len = Math.min(0.8 * (long ? h : w), mix(40, 240, g(16))), t = mix(1.3, 2.6, g(17)); kind = "pipe"; s = long ? [t, t, len] : [len, t, t]; if (long) { cv = clamp(cv, len / 2 + mv, Math.max(len / 2 + mv, h - len / 2 - mv)); if (wall) cu = mix(0.12, 0.88, g(18)) * w; } else { cu = clamp(cu, len / 2 + mu, Math.max(len / 2 + mu, w - len / 2 - mu)); if (wall) cv = mix(0.12, 0.88, g(18)) * h; } }
      else if (wall) { kind = "box"; s = [mix(3, 9, g(16)), mix(1, 3, g(17)), mix(4, 14, g(18))]; }
      else if (kindRoll < 0.26) { kind = "stack"; const a = mix(3, 7, g(16)); s = [a, mix(12, 32, g(17) * g(17) + 0.1), a * mix(0.8, 1.4, g(18))]; }
      else if (kindRoll < 0.33) { kind = "mast"; s = [0.9, mix(16, 44, g(17)), 0.9]; }
      else if (kindRoll < 0.38) { kind = "dish"; const a = mix(3, 8, g(16)); s = [a, a, a]; }
      else { kind = "box"; const a = mix(4, 22, g(16) * g(16) + 0.05); s = [a, mix(2, 9, g(17) * g(17) + 0.05), a * mix(0.5, 2.2, g(18))]; }
      out.push({chart: c.id, p: chartPoint(c, cu, cv), s, kind, tone: mix(0.72, 1.12, g(19))});
    }
  }
  return out;
}

/** A small craft's way into a hangar bay, for a sense of size: at `u` (0..1) the place and heading on a smooth
 * curve that starts abeam of the mouth (`out` metres off the hull, 700; `along` metres along the mouth's width,
 * -600), turns in and ends over the bay's floor (`height` metres above it, 14; `deep`: the share of the bay's
 * depth, 0.45). Returns {p: [x, y, z], forward: [x, y, z]} in the hull's axes; it slows as it arrives. */
export function bayApproach(hull, name, u, options = {}) {
  known("bayApproach options", options, ["out", "along", "height", "deep"]);
  const h = hull.anchors.hangars.find((q) => q.name === name);
  if (!h) throw fail(`no hangar "${name}"${hint(String(name), hull.anchors.hangars.map((q) => q.name))}; hangars: ${hull.anchors.hangars.map((q) => q.name).join(", ") || "none on this hull"}`);
  const f = bayFrame(h), k = 1 - Math.pow(1 - clamp(u), 2), out = options.out ?? 700, floor = f.p[1] - f.h / 2 + (options.height ?? 14);
  const a = along(along(f.p, f.n, out), f.t, options.along ?? -600), b = along(f.p, f.n, 0.35 * out), c = along(f.p, f.n, -(options.deep ?? 0.45) * f.d);
  a[1] = b[1] = c[1] = floor;
  const at = (q) => [0, 1, 2].map((i) => (1 - q) * (1 - q) * a[i] + 2 * q * (1 - q) * b[i] + q * q * c[i]), p = at(k), d = [0, 1, 2].map((i) => 2 * (1 - k) * (b[i] - a[i]) + 2 * k * (c[i] - b[i]));
  return {p, forward: unit(d)};
}

// ---------- the shaders ----------
const VERT_HEAD = /* glsl */`
attribute vec3 win; attribute vec2 hullAtlas;
varying vec3 vWin; varying vec2 vHullUv; varying vec2 vAtlas;
`;
const VERT_MAIN = "vWin = win; vHullUv = uv; vAtlas = hullAtlas;";
const FRAG_HEAD = /* glsl */`
varying vec3 vWin; varying vec2 vHullUv; varying vec2 vAtlas;
uniform sampler2D uMid, uFine, uAtlas, uCellsA, uCellsB;
uniform vec4 uWin; uniform vec2 uTiles; uniform vec3 uBump, uMark, uBay, uEngine; uniform float uLevel, uWinGain, uDay, uSeed, uGlareCap, uStrip, uLift;
float hHash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
`;
const fadeOf = (s) => `(1.0 - smoothstep(${SCALES[s].fade[0].toFixed(2)}, ${SCALES[s].fade[1].toFixed(2)}, hFp))`;
const FRAG_COLOR = /* glsl */`
float hFp = max(length(dFdx(vHullUv)), length(dFdy(vHullUv)));
float hMid = ${fadeOf("mid")}, hFine = ${fadeOf("fine")};
vec4 hM = vec4(0.5), hF = vec4(0.5), hA = texture2D(uAtlas, vAtlas);
if (hMid > 0.0) hM = texture2D(uMid, vHullUv / uTiles.x);
if (hFine > 0.0) hF = texture2D(uFine, vHullUv / uTiles.y);
diffuseColor.rgb *= mix(1.0, 2.0 * hM.b, hMid * uBump.z) * mix(1.0, 2.0 * hF.b, hFine * uBump.z) * (2.0 * hA.r);
diffuseColor.rgb = mix(diffuseColor.rgb, uMark, hA.g * 0.85);
vec3 hWinLight = vec3(0.0); float hGlass = 0.0;
if (vWin.z > 0.001) {
  vec2 hq = vWin.xy / uWin.xy, hCell = floor(hq), hf = hq - hCell, hw = max(fwidth(hq), vec2(1e-4)), lo = 0.5 - uWin.zw, hi = 0.5 + uWin.zw;
  vec2 cov = clamp((min(hf + 0.5 * hw, hi) - max(hf - 0.5 * hw, lo)) / hw, 0.0, 1.0);
  cov = mix(cov, 2.0 * uWin.zw, smoothstep(0.6, 1.3, hw));
  vec2 bank = floor(hCell / vec2(${WINDOW.bank[0]}.0, ${WINDOW.bank[1]}.0));
  float b1 = hHash(bank + uSeed), b2 = hHash(bank + uSeed + 17.3), hFar = smoothstep(0.5, 2.0, max(hw.x / ${WINDOW.bank[0]}.0, hw.y / ${WINDOW.bank[1]}.0));
  float rowOn = step(0.22, hHash(vec2(hCell.y, bank.x) + uSeed)), rowFar = smoothstep(0.5, 2.0, hw.y);   // some decks have no windows in a bank
  float present = mix(step(b1, vWin.z), vWin.z, hFar) * mix(rowOn, 0.78, rowFar) * cov.x * cov.y, on = mix(smoothstep(b2 - 0.06, b2 + 0.06, uLevel * 1.12 - 0.06), uLevel, hFar);
  vec2 gx = dFdx(hq) * (0.6 / 256.0), gy = dFdy(hq) * (0.6 / 256.0);   // a little sharper than the pixel: sparkle before it is a glow
  if (present > 0.0) {
    vec2 cuv = (hCell + 0.5) / 256.0;
    vec4 ca = textureGrad(uCellsA, cuv, gx, gy), cb = textureGrad(uCellsB, cuv, gx, gy);
    float lift = mix(1.0, uLift, smoothstep(0.3, 1.5, max(hw.x, hw.y)));   // a window under a pixel keeps some of its sparkle (film)
    hWinLight = (ca.rgb + cb.rgb * on) * (present * lift * (0.8 + 0.4 * hf.y));
    hGlass = ca.a * present;
    diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.02, 0.025, 0.035), hGlass);
  }
}
`;
// a bay's back wall: ribs, doors and strips of light, drawn from the wall's place among the decks
const FRAG_BAY = /* glsl */`
vec4 hA = texture2D(uAtlas, vAtlas);
vec2 bq = vWin.xy; float bw = max(fwidth(bq.x), fwidth(bq.y)), bk = 1.0 - smoothstep(1.5, 6.0, bw);
float rib = smoothstep(0.43, 0.47, abs(fract(bq.x / 14.0) - 0.5)), deck = fract(bq.y / 11.0), door = step(abs(fract(bq.x / 42.0) - 0.5), 0.13) * step(deck, 0.62);
float strip = step(0.86, deck) * step(deck, 0.91) * step(abs(fract(bq.x / 14.0) - 0.5), 0.3) * step(0.45, hHash(floor(bq / vec2(14.0, 11.0)) + 3.0));
diffuseColor.rgb = vec3(0.2, 0.21, 0.23) * mix(1.0, (1.0 - 0.45 * rib) * (1.0 - 0.55 * door) * (0.85 + 0.3 * hHash(floor(bq / vec2(14.0, 11.0)))), bk);
vec3 hWinLight = vec3(1.0, 0.95, 0.85) * mix(0.07, strip, bk) * uStrip; float hGlass = 0.0;
`;
const FRAG_NORMAL = /* glsl */`
#ifdef USE_NORMALMAP_TANGENTSPACE
  vec2 hDn = (hM.rg * 2.0 - 1.0) * (hMid * uBump.x) + (hF.rg * 2.0 - 1.0) * (hFine * uBump.y);
  normal = normalize(normal + tbn[0] * hDn.x + tbn[1] * hDn.y);
#endif
`;
const FRAG_ROUGH = "roughnessFactor = mix(clamp(roughnessFactor * mix(1.0, 2.0 * hM.a, hMid) * mix(1.0, 2.0 * hF.a, hFine), 0.05, 1.0), 0.12, hGlass);";
const FRAG_LIGHT = /* glsl */`
reflectedLight.directSpecular = min(reflectedLight.directSpecular, vec3(uGlareCap));
float hSun = dot(reflectedLight.directDiffuse, vec3(0.3333)) / max(dot(diffuseColor.rgb, vec3(0.3333)), 0.02);
float hNight = 1.0 - uDay * smoothstep(0.04, 0.4, hSun);
totalEmissiveRadiance += hWinLight * (uWinGain * hNight) + diffuseColor.rgb * (uBay * (hA.b * hNight) + uEngine * hA.a);
`;
function patch(material, kind, uniforms) {
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms, {uGlareCap: GLARE});
    shader.vertexShader = shader.vertexShader.replace("void main() {", `${VERT_HEAD}void main() {\n${VERT_MAIN}`);
    let f = shader.fragmentShader.replace("void main() {", `${FRAG_HEAD}void main() {`).replace("#include <color_fragment>", `#include <color_fragment>\n${kind === "bay" ? FRAG_BAY : FRAG_COLOR}`).replace("#include <lights_fragment_end>", `#include <lights_fragment_end>\n${FRAG_LIGHT}`);
    if (kind !== "bay") f = f.replace("#include <normal_fragment_maps>", `#include <normal_fragment_maps>\n${FRAG_NORMAL}`).replace("#include <roughnessmap_fragment>", `#include <roughnessmap_fragment>\n${FRAG_ROUGH}`);
    shader.fragmentShader = f;
  };
  material.customProgramCacheKey = () => `vidgen-hull-detail-${kind}`;
  material.needsUpdate = true;
}
const LAMP_VERT = /* glsl */`
attribute vec3 color; attribute vec4 lamp;
uniform float uTime, uGain, uLevel; uniform vec2 uView;
varying vec3 vColor;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * vec4(mv.xyz * 0.998, 1.0);   // drawn a little nearer than it stands: a lamp a metre off a wall kilometres away must not lose to the wall's depth
  float px = lamp.x * length(modelMatrix[0].xyz) * projectionMatrix[1][1] * uView.y * 0.5 / max(-mv.z, 1e-3), on = 1.0, p;   // (a hull drawn smaller keeps its lamps in proportion)
  if (lamp.y > 3.5) on = 0.35 + 0.65 * uLevel;
  else if (lamp.y > 2.5) { p = fract(uTime * 0.9 - lamp.z); on = 0.12 + 0.88 * smoothstep(0.22, 0.0, p); }
  else if (lamp.y > 1.5) { p = fract(uTime + lamp.z); on = p < 0.3 ? pow(sin(3.14159265 * p / 0.3), 2.0) : 0.0; }
  else if (lamp.y > 0.5) { p = fract(uTime / 1.6 + lamp.z) * 1.6; on = (p < 0.07 || (p > 0.2 && p < 0.27)) ? 1.0 : 0.0; }
  float k = min(1.0, px / 2.4);
  vColor = color * (on * uGain * k * k);
  gl_PointSize = on > 0.0 ? max(px, 2.4) : 0.0;
}`;
// (the light is kept under white: a red lamp stays red)
const LAMP_FRAG = /* glsl */`
varying vec3 vColor;
void main() { vec2 d = gl_PointCoord * 2.0 - 1.0; float r2 = dot(d, d), a = max(0.0, exp(-r2 * 4.5) - 0.0111) + 0.3 * exp(-r2 * 40.0); gl_FragColor = vec4(vColor * a, 1.0); }`;
const PLUME_VERT = /* glsl */`
attribute vec2 ax;
varying vec2 vAx; varying vec3 vN; varying vec3 vV;
void main() { vAx = ax; vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalMatrix * normal; vV = -mv.xyz; gl_Position = projectionMatrix * mv; }`;
const PLUME_FRAG = /* glsl */`
varying vec2 vAx; varying vec3 vN; varying vec3 vV;
uniform vec3 uCore, uEdge; uniform vec2 uNow;   // power, time
void main() {
  float rim = abs(dot(normalize(vN), normalize(vV))), light;
  vec3 c;
  if (vAx.y >= 0.0) { light = exp(-vAx.y * vAx.y * 3.2) * pow(rim, 3.0) * 1.6; c = mix(uEdge, uCore, exp(-vAx.y * vAx.y * 9.0)) + vec3(exp(-vAx.y * vAx.y * 40.0)); }
  else { float s = vAx.x, flow = 1.0 + 0.1 * sin(s * 46.0 - uNow.y * 33.0) + 0.06 * sin(s * 17.0 - uNow.y * 21.0); light = exp(-s * 5.0) * smoothstep(0.0, 0.02, s) * (1.0 - smoothstep(0.8, 1.0, s)) * flow; c = uEdge * pow(rim, 2.0) * 0.4 + uCore * pow(rim, 6.0) * 0.8 + vec3(pow(rim, 18.0)) * exp(-s * 7.0); }
  gl_FragColor = vec4(c * light * uNow.x, 1.0);
}`;
const BLIT = {vert: "varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }", frag: "uniform sampler2D map; varying vec2 vUv; void main() { gl_FragColor = texture2D(map, vUv); }"};
// numbers into a render target, byte for byte (what vidgen/baked keeps)
function blit(renderer, data, size, target) {
  const tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat); tex.needsUpdate = true;
  const material = new THREE.ShaderMaterial({uniforms: {map: {value: tex}}, vertexShader: BLIT.vert, fragmentShader: BLIT.frag, depthTest: false, depthWrite: false, blending: THREE.NoBlending, toneMapped: false});
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material), was = renderer.getRenderTarget();
  mesh.frustumCulled = false;
  renderer.setRenderTarget(target); renderer.render(mesh, new THREE.Camera()); renderer.setRenderTarget(was);
  tex.dispose(); material.dispose(); mesh.geometry.dispose();
}
const mapTarget = (size, repeat) => { const t = new THREE.WebGLRenderTarget(size, size, {type: THREE.UnsignedByteType, format: THREE.RGBAFormat, depthBuffer: false, generateMipmaps: true, minFilter: THREE.LinearMipmapLinearFilter, magFilter: THREE.LinearFilter, wrapS: repeat ? THREE.RepeatWrapping : THREE.ClampToEdgeWrapping, wrapT: repeat ? THREE.RepeatWrapping : THREE.ClampToEdgeWrapping, colorSpace: THREE.NoColorSpace}); t.texture.anisotropy = repeat ? 4 : 1; return t; };
const TILES = new WeakMap();
function tileMap(renderer, kind, scale, size) {
  if (!TILES.has(renderer)) TILES.set(renderer, new Map());
  const kept = TILES.get(renderer), key = `${kind}/${scale}/${size}`;
  if (!kept.has(key)) kept.set(key, baked(renderer, "space-hull-detail/tile", {version: VERSION, kind, scale, size}, {targets: () => [mapTarget(size, true)], draw: ([t]) => blit(renderer, detailMap(kind, scale, size).data, size, t)})[0]);
  return kept.get(key).texture;
}
const plainHull = (h) => ({charts: h.charts, regions: h.regions.map((g) => ({name: g.name, detail: g.detail})), anchors: {hangars: h.anchors.hangars, bells: h.anchors.bells}, size: h.size, spec: h.spec});
const cellTexture = (data, size) => { const t = new THREE.DataTexture(data, size, size, THREE.RGBAFormat); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.magFilter = THREE.NearestFilter; t.minFilter = THREE.LinearMipmapLinearFilter; t.generateMipmaps = true; t.needsUpdate = true; return t; };

// ---------- dressing a hull ----------
const DRESS = Object.freeze({windows: true, lights: 1, nav: true, hangars: true, engines: true, clutter: true, marks: true, atlas: null, maps: null, plumes: "both"});
const WINDOW_KEYS = ["lit", "watch", "warm", "cool", "floor", "pitch", "gain", "lift"], HANGAR_KEYS = ["craft", "cargo", "curtain", "light"], ENGINE_KEYS = ["structure", "plume", "light"];
/** How the bells' fire is drawn: the craft kit's plume per bell, one long plume per bank, or both. */
export const PLUME_MODES = Object.freeze(["both", "bank", "bells"]);
const M4 = new THREE.Matrix4(), Q = new THREE.Quaternion(), V = new THREE.Vector3(), VIEW = new THREE.Vector4();
const boxMatrix = (c, p, s) => { const du = new THREE.Vector3(...c.du), n = new THREE.Vector3(...c.normal), dv = new THREE.Vector3(...c.dv); return new THREE.Matrix4().makeBasis(du, n, dv).multiply(new THREE.Matrix4().makeScale(s[0], s[1], s[2])).setPosition(p[0] + n.x * s[1] / 2, p[1] + n.y * s[1] / 2, p[2] + n.z * s[1] / 2); };
function beam(a, b, w) {
  const z = b.clone().sub(a), len = z.length() || 1; z.divideScalar(len);
  const x = Math.abs(z.y) < 0.9 ? new THREE.Vector3(0, 1, 0).cross(z).normalize() : new THREE.Vector3(1, 0, 0), y = z.clone().cross(x);
  return new THREE.Matrix4().makeBasis(x, y, z).multiply(new THREE.Matrix4().makeScale(w, w, len)).setPosition(a.clone().add(b).multiplyScalar(0.5));
}
function instances(geometry, material, matrices, colors = null) {
  const mesh = new THREE.InstancedMesh(geometry, material, matrices.length), c = new THREE.Color();
  matrices.forEach((m, i) => { mesh.setMatrixAt(i, m); if (colors) mesh.setColorAt(i, c.setRGB(...colors[i])); });
  mesh.receiveShadow = true; mesh.castShadow = false;
  return mesh;
}
// a geometry the hull's surfaces can draw: it carries the attributes their shader reads
function hullGeometry(g, metres = 14) {
  const n = g.attributes.position.count, one = (size, f) => { const a = new Float32Array(n * size); for (let i = 0; i < n; i++) f(a, i * size, i); return new THREE.BufferAttribute(a, size); };
  g.setAttribute("uv", one(2, (a, q, i) => { a[q] = g.attributes.uv.getX(i) * metres; a[q + 1] = g.attributes.uv.getY(i) * metres; }));
  g.setAttribute("color", one(3, (a, q) => { a[q] = a[q + 1] = a[q + 2] = 1; }));
  g.setAttribute("win", one(3, () => {})); g.setAttribute("hullAtlas", one(2, (a, q) => { a[q] = a[q + 1] = 2 / 512; }));
  return g;
}
function plumeGeometry(spread) {
  const pos = [], nor = [], ax = [], idx = [], rings = 28, seg = 28;
  for (let i = 0; i <= rings; i++) for (let j = 0; j <= seg; j++) {
    const s = i / rings, a = j / seg * TAU, r = 0.92 + spread * Math.pow(s, 0.8), slope = spread * 0.8 * Math.pow(Math.max(s, 0.02), -0.2);
    pos.push(r * Math.cos(a), r * Math.sin(a), -s); nor.push(Math.cos(a), Math.sin(a), slope); ax.push(s, -1);
  }
  for (let i = 0; i < rings; i++) for (let j = 0; j < seg; j++) { const a = i * (seg + 1) + j, b = a + seg + 1; idx.push(a, b, a + 1, a + 1, b, b + 1); }
  const base = pos.length / 3;
  pos.push(0, 0, -0.004); nor.push(0, 0, -1); ax.push(0, 0);
  for (let j = 0; j <= seg; j++) { const a = j / seg * TAU; pos.push(2.2 * Math.cos(a), 2.2 * Math.sin(a), -0.004); nor.push(0, 0, -1); ax.push(0, 2.2); }
  for (let j = 0; j < seg; j++) idx.push(base, base + 2 + j, base + 1 + j);
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3)); g.setAttribute("ax", new THREE.Float32BufferAttribute(ax, 2)); g.setIndex(idx);
  return g;
}

/** The detail of one hull (see dress): `object` (what was added under the hull), `update(t, options)`,
 * `info` ({windows, lit, lamps, clutter, craft, bake: {ms}}), `maps`, `plan`, dispose(). */
export class HullDetail {
  constructor(hull, renderer, options = {}) {
    known("dress options", options, [...Object.keys(DRESS), "seed"]);
    if (!hull || !hull.charts || !hull.object) throw fail("dress needs a hull of vidgen/space-hull");
    const o = this.options = {...DRESS, ...Object.fromEntries(Object.entries(options).filter(([, v]) => v !== undefined && v !== null))}, far = hull.kit.far;
    const sub = (name, keys, defaults) => { const v = o[name]; if (v === false) return null; if (v !== true) known(`dress ${name}`, v, keys); return {...defaults, ...(v === true ? {} : v)}; };
    const win = sub("windows", WINDOW_KEYS, WINDOW), bays = sub("hangars", HANGAR_KEYS, {craft: far ? 0 : 1, cargo: far ? 0 : 1, curtain: 0.25, light: 1}), eng = sub("engines", ENGINE_KEYS, {structure: !far, plume: 1, light: 1});
    if (!PLUME_MODES.includes(o.plumes)) throw fail(`plumes: "${o.plumes}"${hint(String(o.plumes), PLUME_MODES)}; one of: ${PLUME_MODES.join(", ")}`);
    number("lights", o.lights, 0, 1);
    const clutter = o.clutter === true ? (far ? 0 : 1) : o.clutter === false ? 0 : number("clutter", o.clutter, 0, 4), atlas = o.atlas ?? (far ? 1024 : 2048), size = o.maps ?? (far ? 512 : 1024), seed = options.seed ?? hull.spec?.seed ?? 1;
    for (const [k, v] of [["atlas", atlas], ["maps", size]]) if (![256, 512, 1024, 2048, 4096].includes(v)) throw fail(`${k} must be 256, 512, 1024, 2048 or 4096, got ${JSON.stringify(v)}`);
    this.hull = hull; this.renderer = renderer; this.object = new THREE.Group(); this.object.name = "hull detail"; this.own = []; this.win = win; this.bays = bays; this.eng = eng;
    const t0 = (typeof performance !== "undefined" ? performance : {now: () => 0}).now(), palette = PALETTES[hull.kit.look.palette], lin = (hex) => new THREE.Color(hex);
    // the maps
    const plain = plainHull(hull), unique = baked(renderer, "space-hull-detail/unique", {version: VERSION, size: atlas, hull: plain, marks: !!o.marks}, {targets: () => [mapTarget(atlas, false)], draw: ([t]) => { const d = uniqueMap(plain, atlas); if (!o.marks) for (let i = 1; i < d.length; i += 4) d[i] = 0; blit(renderer, d, atlas, t); }})[0];
    const cells = windowCells(seed, win ? {lit: win.lit, watch: win.watch, warm: win.warm, cool: win.cool} : {lit: 0}), cellsA = cellTexture(cells.watch, cells.size), cellsB = cellTexture(cells.rest, cells.size);
    this.own.push(unique, cellsA, cellsB);
    this.maps = {unique: unique.texture, cells: [cellsA, cellsB]};
    const half = win ? [0.5 * win.size[0] / win.pitch, 0.5 * win.size[1] / win.floor] : [0, 0];
    const shared = this.uniforms = {uAtlas: {value: unique.texture}, uCellsA: {value: cellsA}, uCellsB: {value: cellsB}, uWin: {value: new THREE.Vector4(win?.pitch ?? 3.2, win?.floor ?? 3.5, half[0], half[1])}, uTiles: {value: new THREE.Vector2(SCALES.mid.tile, SCALES.fine.tile)},
      uBay: {value: new THREE.Color()}, uEngine: {value: new THREE.Color()}, uLevel: {value: o.lights}, uWinGain: {value: 0}, uDay: {value: 0.85}, uSeed: {value: (seed * 7.31) % 97}, uStrip: {value: 1}, uLift: {value: 1}};
    for (const [name, m] of Object.entries(hull.materials)) {
      if (!name.startsWith("hull-")) continue;
      if (name === "hull-void") { m.color.set(0xffffff); patch(m, "bay", {...shared, uMid: {value: null}, uFine: {value: null}, uBump: {value: new THREE.Vector3()}, uMark: {value: new THREE.Color()}}); continue; }
      if (!(name in KIND_OF)) continue;
      const kind = KIND_OF[name], mark = name === "hull-c" ? lin(palette.a) : name === "hull-rock" ? lin(0xcfcbc2) : lin(palette.c), k = kind ?? "plating";
      patch(m, kind ?? "rock", {...shared, uMid: {value: tileMap(renderer, k, "mid", size)}, uFine: {value: tileMap(renderer, k, "fine", size)}, uBump: {value: new THREE.Vector3(kind ? 0.9 : 0, kind ? 0.75 : 0, kind ? 1 : 0)}, uMark: {value: mark}});
      if (kind === "plating" || kind === "metal") m.normalScale.multiplyScalar(0.55);   // the large plates step back: the small scale carries the surface now
    }
    // every wall's place among the decks
    let cellsCount = 0;
    const turn = new THREE.Matrix4().makeRotationX(-Math.PI / 2), byName = new Map(hull.regions.map((g) => [g.name, g]));
    hull.object.traverse((mesh) => {
      if (!mesh.isMesh || !mesh.geometry.attributes.chart) return;
      const g = mesh.geometry, P = g.attributes.position.array, U = g.attributes.uv.array, C = g.attributes.chart.array, n = C.length, out = new Float32Array(n * 3), spun = !!(mesh.parent && mesh.parent.userData.spin), bay = mesh.name === "hull-void";
      for (let i = 0; i < n; i += 3) {
        const chart = hull.charts[C[i]];
        if (!chart || (!win && !bay)) continue;
        const p = [0, 1, 2].map((k) => [P[3 * (i + k)], P[3 * (i + k) + 1], P[3 * (i + k) + 2]]), nrm = unit(cross([p[1][0] - p[0][0], p[1][1] - p[0][1], p[1][2] - p[0][2]], [p[2][0] - p[0][0], p[2][1] - p[0][1], p[2][2] - p[0][2]]));
        const area = 0.5 * Math.hypot(...cross([p[1][0] - p[0][0], p[1][1] - p[0][1], p[1][2] - p[0][2]], [p[2][0] - p[0][0], p[2][1] - p[0][1], p[2][2] - p[0][2]]));
        const share = bay ? -1 : windowShare(byName.get(chart.region).detail, mesh.name) * (hull.anchors.hangars.some((h) => inBay(h, p[0], 1) && inBay(h, p[1], 1) && inBay(h, p[2], 1)) ? 0 : 1);
        if (share === 0) continue;
        const axis = chart.kind === "round" ? (spun ? V.set(...chart.axis).applyMatrix4(turn).toArray() : chart.axis) : null;
        for (let k = 0; k < 3; k++) {
          const w = windowCoords(p[k], nrm, axis && !bay ? {round: axis, uv: [U[2 * (i + k)], U[2 * (i + k) + 1]]} : {});
          out.set([w[0], w[1], w[2] * share], 3 * (i + k));
        }
        if (share > 0 && (out[3 * i + 2] > 0)) cellsCount += area * share / ((win.pitch * win.floor));
      }
      g.setAttribute("win", new THREE.BufferAttribute(out, 3)); g.setAttribute("hullAtlas", g.attributes.uv1);
    });
    this.plan = {lamps: o.nav ? navLights(hull) : [], clutter: clutter > 0 ? clutterPlan(hull, {density: clutter}) : [], floods: floodPlan(hull)};
    this._clutter(); this._bays(); this._engines(); this._lamps();
    for (const l of hull.lights) l.lamp.parent.scale.multiplyScalar(0.3);
    hull.object.add(this.object);
    this.info = {windows: Math.round(cellsCount * cells.exist), lit: win ? cells.lit : 0, lamps: this.plan.lamps.length + this.workLights, clutter: this.plan.clutter.length, craft: this.parked, bake: {ms: Math.round((typeof performance !== "undefined" ? performance : {now: () => 0}).now() - t0)}};
    this.update(0);
  }
  _clutter() {
    const hull = this.hull, list = this.plan.clutter, work = this.work = [];
    this.workLights = 0;
    if (!list.length) return;
    const box = hullGeometry(new THREE.BoxGeometry(1, 1, 1)), by = {b: [[], []], c: [[], []]}, dishes = [];
    list.forEach((it, i) => {
      const c = hull.charts[it.chart];
      if (it.kind === "dish") { const m = boxMatrix(c, it.p, [0.5, it.s[1] * 1.3, 0.5]); by.c[0].push(m); by.c[1].push([1, 1, 1]); dishes.push({c, it}); }
      else { const dark = it.kind === "pipe" || it.kind === "mast" || hash2(i, 5, 3) < 0.3, to = dark ? by.c : by.b; to[0].push(boxMatrix(c, it.p, it.s)); to[1].push([it.tone, it.tone, it.tone]); }
      if (it.kind === "mast" || it.kind === "stack" || (it.kind === "box" && hash2(i, 7, 3) < 0.16)) { const n = c.normal, top = it.s[1] + 1.2; work.push({p: [it.p[0] + n[0] * top, it.p[1] + n[1] * top, it.p[2] + n[2] * top], color: it.kind === "mast" ? RED : hash2(i, 8, 3) < 0.7 ? WHITE : COOL, size: it.kind === "mast" ? 3 : 2.2, kind: it.kind === "mast" ? "beacon" : "work", phase: hash2(i, 9, 3)}); }
    });
    this.workLights = work.length;
    this.object.add(instances(box, hull.materials["hull-b"], by.b[0], by.b[1]), instances(box, hull.materials["hull-c"], by.c[0], by.c[1]));
    if (dishes.length) {
      const g = hullGeometry(new THREE.SphereGeometry(1, 14, 5, 0, TAU, 0, 1.1).scale(1, 0.45, 1).rotateX(Math.PI).translate(0, 0.62, 0), 6);
      this.object.add(instances(g, hull.materials["hull-a"], dishes.map(({c, it}) => { const tilt = new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(0.5 * (hash2(it.p[0] | 0, it.p[2] | 0, 1) - 0.5), 0, 0.9 * (hash2(it.p[0] | 0, it.p[2] | 0, 2) - 0.5))); return boxMatrix(c, it.p, [1, 0, 1]).multiply(new THREE.Matrix4().makeTranslation(0, it.s[1] * 1.3, 0)).multiply(tilt).multiply(new THREE.Matrix4().makeScale(it.s[0], it.s[0], it.s[0])); })));
      this.own.push(g);
    }
    this.own.push(box);
  }
  _bays() {
    const hull = this.hull, o = this.bays;
    this.parked = 0; this.crafts = []; this.curtains = [];
    this.bayLight = {value: new THREE.Color()}; this.up = {value: new THREE.Vector3(0, 1, 0)};
    if (!o || !hull.anchors.hangars.length) return;
    const seed = hull.spec?.seed ?? 1, lit = (m) => {
      const c = m.clone(); c.onBeforeCompile = (s) => {
        s.uniforms.uBayLight = this.bayLight; s.uniforms.uBayUp = this.up;
        s.vertexShader = s.vertexShader.replace("void main() {", "uniform vec3 uBayUp; varying float vBayUp;\nvoid main() {").replace("#include <beginnormal_vertex>", "#include <beginnormal_vertex>\n#ifdef USE_INSTANCING\nvBayUp = dot(normalize(mat3(modelMatrix) * (mat3(instanceMatrix) * objectNormal)), uBayUp);\n#else\nvBayUp = 0.0;\n#endif");
        s.fragmentShader = s.fragmentShader.replace("void main() {", "uniform vec3 uBayLight; varying float vBayUp;\nvoid main() {").replace("#include <lights_fragment_end>", "#include <lights_fragment_end>\ntotalEmissiveRadiance += diffuseColor.rgb * uBayLight * (0.45 + 0.55 * vBayUp);");
      };
      c.customProgramCacheKey = () => "vidgen-hull-bay-craft"; this.own.push(c);
      return c;
    };
    const places = {ship: [], tug: []}, boxes = [[], []];
    hull.anchors.hangars.forEach((h, k) => {
      const f = bayFrame(h), floor = f.p[1] - f.h / 2, n = new THREE.Vector3(...f.n), t = new THREE.Vector3(...f.t), spots = clamp(Math.round(f.w / 120), 1, 5);
      if (o.craft > 0) for (let i = 0; i < spots; i++) {
        if (hash2(i, k, seed + 41) > 0.8 * o.craft) continue;
        const kind = f.h > 40 && f.d > 90 && hash2(i, k, seed + 42) < 0.6 ? "ship" : "tug", x = (i + 0.5 - spots / 2) * (0.8 * f.w / spots), yaw = (hash2(i, k, seed + 43) - 0.5) * 0.5;
        const z = n.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw), xa = new THREE.Vector3(0, 1, 0).cross(z).normalize();
        places[kind].push({m: new THREE.Matrix4().makeBasis(xa, new THREE.Vector3(0, 1, 0), z), at: new THREE.Vector3(...f.p).addScaledVector(t, x).addScaledVector(n, -0.52 * f.d).setY(floor)});
      }
      if (o.cargo > 0) for (let i = 0, m = Math.round(o.cargo * f.w / 9); i < m; i++) {
        const g = (q) => hash2(i * 13 + q, k, seed + 44);
        if (g(0) < 0.45) continue;
        const stack = 1 + Math.floor(g(1) * g(1) * 4), x = (i / m - 0.5) * 0.94 * f.w, back = (0.8 + 0.14 * Math.floor(g(2) * 2)) * f.d - 4;
        for (let s = 0; s < stack; s++) { const p = new THREE.Vector3(...f.p).addScaledVector(t, x).addScaledVector(n, -Math.min(back, f.d - 5)).setY(floor + 3 + s * 6.2); boxes[0].push(new THREE.Matrix4().makeBasis(t, new THREE.Vector3(0, 1, 0), n).multiply(new THREE.Matrix4().makeScale(7.4, 6, 14)).setPosition(p)); const a = g(3 + s); boxes[1].push(a < 0.2 ? [0.42, 0.17, 0.08] : a < 0.4 ? [0.12, 0.2, 0.3] : a < 0.7 ? [0.3, 0.31, 0.32] : [0.18, 0.19, 0.2]); }
      }
      if (o.curtain > 0) {
        const m = new THREE.Mesh(new THREE.PlaneGeometry(f.w, f.h), new THREE.ShaderMaterial({uniforms: {uColor: {value: new THREE.Color(0.25, 0.6, 1)}, uPower: {value: o.curtain}, uSize: {value: new THREE.Vector2(f.w, f.h)}},
          vertexShader: "varying vec2 vUv; varying vec3 vN; varying vec3 vV; void main() { vUv = uv; vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalMatrix * normal; vV = -mv.xyz; gl_Position = projectionMatrix * mv; }",
          fragmentShader: "varying vec2 vUv; varying vec3 vN; varying vec3 vV; uniform vec3 uColor; uniform float uPower; uniform vec2 uSize;\nvoid main() { vec2 e = min(vUv, 1.0 - vUv) * uSize; float edge = exp(-min(e.x, e.y) / 5.0), graze = 1.0 - abs(dot(normalize(vN), normalize(vV))); gl_FragColor = vec4(uColor * uPower * (0.05 + 0.55 * edge + 0.5 * graze * graze * graze), 1.0); }",
          blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, side: THREE.DoubleSide, toneMapped: false}));
        m.quaternion.setFromRotationMatrix(M4.makeBasis(t, new THREE.Vector3(0, 1, 0), n)); m.position.set(...f.p).addScaledVector(n, 0.8); m.userData.keep = true;
        this.object.add(m); this.curtains.push(m);
      }
    });
    for (const [kind, list] of Object.entries(places)) {
      if (!list.length) continue;
      const c = kitCraft(kind, {seed: seed + (kind === "ship" ? 3 : 5), detail: "far"}), lift = c.size.height / 2 + 1.5;
      c.update(0); c.object.updateMatrixWorld(true);
      const inv = c.object.matrixWorld.clone().invert(), made = new Map();
      c.object.traverse((m) => {
        if (!m.isMesh || !m.material.isMeshStandardMaterial || m.userData.keep) return;
        if (!made.has(m.material)) made.set(m.material, lit(m.material));
        const local = inv.clone().multiply(m.matrixWorld), im = instances(m.geometry, made.get(m.material), list.map((q) => q.m.clone().setPosition(q.at.x, q.at.y + lift, q.at.z).multiply(local)));
        this.object.add(im);
      });
      this.crafts.push(c); this.parked += list.length;
    }
    if (boxes[0].length) { const g = new THREE.BoxGeometry(1, 1, 1), m = lit(new THREE.MeshStandardMaterial({roughness: 0.8, metalness: 0.2})); this.object.add(instances(g, m, boxes[0], boxes[1])); this.own.push(g); }
  }
  _engines() {
    const hull = this.hull, o = this.eng, banks = new Map();
    this.plumes = []; this.frame = null;
    if (!o) return;
    for (const b of hull.anchors.bells) { if (!banks.has(b.bank)) banks.set(b.bank, []); banks.get(b.bank).push(b); }
    const boxes = [], tones = [], rings = [], shrouds = [], v = (x, y, z) => new THREE.Vector3(x, y, z);
    for (const list of banks.values()) {
      const cx = list.reduce((s, b) => s + b.p[0], 0) / list.length, cy = list.reduce((s, b) => s + b.p[1], 0) / list.length, z = list[0].p[2], r = list[0].radius, R = Math.max(...list.map((b) => Math.hypot(b.p[0] - cx, b.p[1] - cy))) + r, kind = PLUMES[list[0].kind] ? list[0].kind : "vacuum";
      if (o.plume > 0) {
        const spec = PLUMES[kind], spread = 1.0, mesh = new THREE.Mesh(plumeGeometry(spread), new THREE.ShaderMaterial({uniforms: {uCore: {value: new THREE.Color(...spec.core)}, uEdge: {value: new THREE.Color(...spec.edge)}, uNow: {value: new THREE.Vector2(0, 0)}}, vertexShader: PLUME_VERT, fragmentShader: PLUME_FRAG, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, side: THREE.DoubleSide, toneMapped: false}));
        mesh.position.set(cx, cy, z - 0.3 * r); mesh.userData = {keep: true, radius: R, length: 24 * R * o.plume, bells: list.map((b) => hull.anchors.bells.indexOf(b))};
        this.object.add(mesh); this.plumes.push(mesh);
      }
      if (!o.structure) continue;
      const len = r * (list[0].kind === "ion" ? 1.3 : list[0].kind === "vacuum" ? 3.4 : 2.8), zp = z + len;
      for (const b of list) {
        const [x, y] = b.p;
        rings.push(new THREE.Matrix4().makeScale(0.56 * r, 0.56 * r, 0.56 * r).setPosition(x, y, zp - 0.3 * len));
        shrouds.push(new THREE.Matrix4().makeScale(0.7 * r, 0.7 * r, 0.24 * len).setPosition(x, y, zp - 0.12 * len));
        for (let i = 0; i < 3; i++) { const a = i * TAU / 3 + 0.5; boxes.push(beam(v(x + 0.95 * r * Math.cos(a), y + 0.95 * r * Math.sin(a), zp), v(x + 0.56 * r * Math.cos(a), y + 0.56 * r * Math.sin(a), zp - 0.3 * len), 0.07 * r)); tones.push([0.5, 0.5, 0.52]); }
        for (let i = 0; i < 2; i++) { const a = i * Math.PI + 1.6; boxes.push(new THREE.Matrix4().makeScale(0.3 * r, 0.3 * r, 0.26 * len).setPosition(x + 0.86 * r * Math.cos(a), y + 0.86 * r * Math.sin(a), zp - 0.13 * len)); tones.push([0.36, 0.34, 0.33]); }
        for (const c of list) if (c !== b && c.name > b.name) { const d = Math.hypot(c.p[0] - x, c.p[1] - y); if (d < 2.7 * r) { boxes.push(beam(v(x, y, zp - 0.3 * len), v(c.p[0], c.p[1], zp - 0.3 * len), 0.09 * r)); tones.push([0.42, 0.42, 0.44]); } }
      }
      const xs = list.map((b) => b.p[0]), ys = list.map((b) => b.p[1]), x0 = Math.min(...xs) - 1.08 * r, x1 = Math.max(...xs) + 1.08 * r, y0 = Math.min(...ys) - 1.08 * r, y1 = Math.max(...ys) + 1.08 * r, zf = zp - 0.2 * len, corners = [v(x0, y0, zf), v(x1, y0, zf), v(x1, y1, zf), v(x0, y1, zf)];
      corners.forEach((c, i) => { boxes.push(beam(c, corners[(i + 1) % 4], 0.13 * r)); tones.push([0.4, 0.4, 0.42]); boxes.push(beam(c, v(c.x * 0.96 + cx * 0.04, c.y * 0.96 + cy * 0.04, zp + 0.1 * r), 0.1 * r)); tones.push([0.4, 0.4, 0.42]); });
      const m = Math.round((x1 - x0) / (2.2 * r));
      for (let i = 1; i < m; i++) { const x = mix(x0, x1, i / m); boxes.push(beam(v(x, y0, zf), v(x, y1, zf), 0.07 * r)); tones.push([0.36, 0.36, 0.38]); }
    }
    if (!boxes.length) return;
    const metal = this.frame = new THREE.MeshStandardMaterial({color: 0x74767c, roughness: 0.5, metalness: 0.75, emissive: 0x000000}), box = new THREE.BoxGeometry(1, 1, 1), ring = new THREE.TorusGeometry(1, 0.09, 6, 28), shroud = new THREE.CylinderGeometry(1, 1.12, 1, 24, 1, true).rotateX(Math.PI / 2);
    const dark = new THREE.MeshStandardMaterial({color: 0x3a3430, roughness: 0.65, metalness: 0.6, side: THREE.DoubleSide});
    this.object.add(instances(box, metal, boxes, tones), instances(ring, metal, rings), instances(shroud, dark, shrouds));
    this.own.push(metal, dark, box, ring, shroud);
  }
  _lamps() {
    const list = [...this.plan.lamps, ...this.work];
    this.lamps = null;
    if (!list.length) return;
    const g = new THREE.BufferGeometry(), n = list.length, pos = new Float32Array(n * 3), col = new Float32Array(n * 3), lamp = new Float32Array(n * 4);
    list.forEach((l, i) => { pos.set(l.p, 3 * i); col.set(l.color, 3 * i); lamp.set([l.size, LAMP_KINDS[l.kind], l.phase, 0], 4 * i); });
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setAttribute("color", new THREE.BufferAttribute(col, 3)); g.setAttribute("lamp", new THREE.BufferAttribute(lamp, 4));
    const material = new THREE.ShaderMaterial({uniforms: {uTime: {value: 0}, uGain: {value: 1}, uLevel: {value: 1}, uView: {value: new THREE.Vector2(1280, 720)}}, vertexShader: LAMP_VERT, fragmentShader: LAMP_FRAG, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, toneMapped: false});
    const points = this.lamps = new THREE.Points(g, material);
    points.userData.keep = true;   // (never `frustumCulled = false`: vidgen/space-scale draws such things as sky, behind everything)
    points.onBeforeRender = (renderer) => { const v = renderer.getCurrentViewport(VIEW); material.uniforms.uView.value.set(v.z, v.w); };
    this.object.add(points); this.own.push(g, material);
  }
  /** Each frame, after the hull's own update: `lights` (0..1: the night watch only .. every bank of windows
   * on; work lights follow it), `light` (a spaceLight of vidgen/space-light after its update, or `gains`:
   * {lights, film}: an honest exposure dims every lamp and window as it dims a city's lights), `throttle`
   * (default: what the hull's update was given). */
  update(t = 0, options = {}) {
    known("detail update options", options, ["lights", "light", "gains", "throttle"]);
    const hull = this.hull, U = this.uniforms, gains = options.gains ?? options.light?.state?.gains ?? {lights: 1, film: true}, k = gains.lights ?? 1, level = clamp(options.lights ?? this.options.lights);
    const raw = options.throttle ?? hull.state?.throttle ?? 0, th = clamp(Array.isArray(raw) ? raw.reduce((s, x) => s + x, 0) / Math.max(1, raw.length) : typeof raw === "function" ? raw(t) : raw), fire = th * flicker(t, 3);
    U.uLevel.value = level; U.uWinGain.value = this.win ? this.win.gain * k : 0; U.uDay.value = gains.film === false ? 0 : 0.85; U.uLift.value = gains.film === false ? 1 : this.win?.lift ?? 1; U.uStrip.value = 1.5 * k * (this.bays?.light ?? 0);
    const bay = (this.bays?.light ?? 0) * k;
    U.uBay.value.setRGB(1.7 * bay, 1.58 * bay, 1.36 * bay); this.bayLight.value.setRGB(0.95 * bay, 0.9 * bay, 0.8 * bay);
    const kind = hull.anchors.bells[0]?.kind, core = (PLUMES[kind] ?? PLUMES.vacuum).core, e = (this.eng?.light ?? 0) * fire * 2.6;
    U.uEngine.value.setRGB(core[0] * e, core[1] * e, core[2] * e);
    if (this.frame) this.frame.emissive.setRGB(core[0] * e * 0.12, core[1] * e * 0.12, core[2] * e * 0.12);
    this.up.value.set(0, 1, 0).applyQuaternion(hull.object.getWorldQuaternion(Q));
    for (const p of this.plumes) {
      const u = p.userData, own = u.bells.reduce((s, i) => s + clamp(Array.isArray(raw) ? raw[i] ?? 0 : th), 0) / u.bells.length, f = own * flicker(t, 5);
      p.visible = this.options.plumes !== "bells" && own > 0.002; p.scale.set(u.radius, u.radius, u.length * (0.3 + 0.7 * Math.sqrt(own))); p.material.uniforms.uNow.value.set(f * (this.options.plumes === "bank" ? 1.25 : 0.8), t);
    }
    if (this.options.plumes === "bank") for (const en of hull.engines) if (en.plume) en.plume.visible = false;
    if (this.lamps) { const u = this.lamps.material.uniforms; u.uTime.value = t; u.uGain.value = 1.3 * k; u.uLevel.value = level; }
    return this;
  }
  /** Put `craft` (one that scaleRef stood beside this hull: a child of the hull's object) on its way into the
   * hangar `name` at `u` (0..1): see bayApproach. */
  fly(craft, name, u, options = {}) {
    const {p, forward} = bayApproach(this.hull, name, u, options), z = V.set(...forward), x = new THREE.Vector3(0, 1, 0).cross(z).normalize();
    craft.object.position.set(...p); craft.object.quaternion.setFromRotationMatrix(M4.makeBasis(x, z.clone().cross(x), z));
    return this;
  }
  dispose() {
    this.hull.object.remove(this.object);
    for (const l of this.hull.lights) l.lamp.parent.scale.multiplyScalar(1 / 0.3);
    for (const m of this.curtains) { m.geometry.dispose(); m.material.dispose(); }
    for (const p of this.plumes) { p.geometry.dispose(); p.material.dispose(); }
    for (const c of this.crafts) c.dispose();
    for (const x of this.own) x.dispose();
  }
}
/** Dress a hull of vidgen/space-hull with its fine detail (see the head of this file). Options: `lights`
 * (0..1, the level update() starts from; 1), `windows` (false | {lit: the share lit at full level, watch: the
 * share of those that never go out, warm, cool, floor: metres between decks, pitch: metres between windows,
 * gain}), `nav` (navigation, guide and flood lamps), `hangars` (false | {craft: 0..1 how full the bays are,
 * cargo, curtain: the faint glow across a mouth (a look, not physics; 0: none), light}), `engines` (false |
 * {structure, plume: the bank plume's length (1: sixteen bank radii), light}), `plumes` ("both" | "bank": only
 * the long plume per bank, cheaper | "bells": only the kit's), `clutter` (false | a density, 1), `marks`,
 * `atlas` (the unique map's size: 2048, 1024 at "far" detail), `maps` (the tiling maps' size: 1024, 512 at
 * "far"). A hull at "far" detail gets no clutter, parked craft or thrust structure by default. */
export const dress = (hull, renderer, options = {}) => new HullDetail(hull, renderer, options);
/** Dress every hull of a fleet (hullFleet's): returns {details, update(t, options), dispose()}. */
export function dressFleet(fleet, renderer, options = {}) {
  if (!fleet || !Array.isArray(fleet.hulls)) throw fail("dressFleet needs a fleet of vidgen/space-hull (hullFleet)");
  const details = fleet.hulls.map((h) => dress(h, renderer, options));
  return {details, update(t, o = {}) { for (const d of details) d.update(t, o); return this; }, dispose() { for (const d of details) d.dispose(); }};
}
