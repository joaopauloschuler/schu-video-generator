// vidgen/space-bodies: planets, moons and rings from a seed (DESIGN.md §122.7). Part of
// schu-video-generator (MIT licence); imported by a page as "vidgen/space-bodies".
//
//   import {planet} from "vidgen/space-bodies";
//   const earth = planet(renderer, "earth");                       // a ready-made world (PRESETS) ...
//   const world = planet(renderer, {type: "ocean", seed: 7, rings: {seed: 2}});   // ... or one of your own
//   scene.add(earth.object);                                       // radius 1; scale and place it as any object
//   earth.update(t, {sun: [3, 1, 2]});                             // spin, clouds, bands at time t; where the sun is
//   const saturn = planet(renderer, "Saturn", {space});            // with ctx.orbits: placed, sized, tilted, spun, lit
//   function frame(t) { space.update(t, view); saturn.update(t); finish.render(t); }
//
// What is drawn. A body is one sphere whose every pixel is worked out from the view ray: the exact
// round limb (anti-aliased), the surface from two cube maps baked once from the seed (colour and
// gloss or glow; relief and clouds or heights), one hard sun, the air as a shell of exponentially
// thinning gas (blue limb, red terminator, the lit ring of a backlit world), rings as a flat disc with
// a radial profile, their shadow on the globe and the globe's on them. Nothing is random at draw time
// and nothing is kept between frames: the picture is a function of t, the seed and the options.
//
// Frame. The body's own axes: +y the north pole, +x the prime meridian (as vidgen/space-scale turns a
// body of ctx.orbits). Light: linear values for a tone-mapped picture (vidgen/three-finish), a white
// surface facing the sun = `light` (1); drawn straight to the canvas a body applies the ACES curve and
// the sRGB encoding itself, as vidgen/space-sky does. The depth is written per pixel (gl_FragDepth):
// use vidgen/space-scale's `split` (default) or `single` depth, not a logarithmic depth buffer.
//
// No real maps: every surface is an invented lookalike in character and colour.
import * as THREE from "three";
import {rng} from "vidgen/music-time";

export const VERSION = 1;
const RAD = Math.PI / 180, TAU = Math.PI * 2;
const PREFIX = "vidgen/space-bodies";

// ---------- checks ----------
const fail = (message) => new Error(`${PREFIX}: ${message}`);
function editDistance(a, b) {
  const row = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0]; row[0] = i;
    for (let j = 1; j <= b.length; j++) { const keep = row[j]; row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = keep; }
  }
  return row[b.length];
}
function hint(word, choices) {
  let best = null, score = Infinity;
  for (const c of choices) { const d = editDistance(String(word).toLowerCase(), c.toLowerCase()); if (d < score) { best = c; score = d; } }
  return best !== null && score <= Math.max(2, Math.floor(String(word).length / 3)) ? ` (did you mean "${best}"?)` : "";
}
function known(where, object, keys) {
  if (object === null || typeof object !== "object" || Array.isArray(object)) throw fail(`${where} must be an object, got ${JSON.stringify(object)}`);
  for (const k of Object.keys(object)) if (!keys.includes(k)) throw fail(`${where}: unknown option "${k}"${hint(k, keys)}; known: ${keys.join(", ")}`);
}
function number(where, v, lo, hi) {
  if (typeof v !== "number" || !Number.isFinite(v) || v < lo || v > hi) throw fail(`${where} must be a number from ${lo} to ${hi}, got ${JSON.stringify(v)}`);
  return v;
}
function choice(where, v, list) {
  if (!list.includes(v)) throw fail(`${where} must be one of ${list.map((x) => JSON.stringify(x)).join(", ")}, got ${JSON.stringify(v)}${hint(v, list)}`);
  return v;
}
/** A colour as linear [r, g, b]: a hex number or CSS string (sRGB), a THREE.Color, or [r, g, b] already linear. */
export function linearColor(where, v) {
  if (Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === "number" && Number.isFinite(x) && x >= 0)) return v.slice();
  if (typeof v === "number" || typeof v === "string") { const c = new THREE.Color(v); return [c.r, c.g, c.b]; }
  if (v && v.isColor) return [v.r, v.g, v.b];
  throw fail(`${where} must be a colour (0xrrggbb, a CSS string or linear [r, g, b]), got ${JSON.stringify(v)}`);
}
const hex = (v) => linearColor("colour", v);
const mix = (a, b, u) => a + (b - a) * u;
const mix3 = (a, b, u) => [mix(a[0], b[0], u), mix(a[1], b[1], u), mix(a[2], b[2], u)];
const clamp01 = (x) => Math.min(1, Math.max(0, x));
const smooth = (a, b, x) => { const u = clamp01((x - a) / (b - a)); return u * u * (3 - 2 * u); };
/** The unit vector of a latitude and longitude (degrees) in the body's axes (+y north, +x the prime meridian). */
export const onGlobe = (lat, lon) => [Math.cos(lat * RAD) * Math.cos(lon * RAD), Math.sin(lat * RAD), -Math.cos(lat * RAD) * Math.sin(lon * RAD)];

// ---------- the baking shaders: noise ----------
const BAKE_VERT = "void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }";
const fbm = (name, octaves, gain = 0.5, lacunarity = 2.02) => `
float ${name}(vec3 p) { float a = 0.5, s = 0.0; for (int i = 0; i < ${octaves}; i++) { s += a * gnoise(p); p = p * ${lacunarity.toFixed(3)} + vec3(17.13, 3.71, 9.27); a *= ${gain.toFixed(3)}; } return s; }`;
const ridge = (name, octaves, gain = 0.5) => `
float ${name}(vec3 p) { float a = 0.5, s = 0.0, w = 1.0; for (int i = 0; i < ${octaves}; i++) { float n = 1.0 - abs(gnoise(p)); n *= n; s += a * n * w; w = clamp(n * 1.6, 0.0, 1.0); p = p * 2.07 + vec3(5.3, 11.9, 2.1); a *= ${gain.toFixed(3)}; } return s; }`;
const NOISE = /* glsl */`
precision highp float; precision highp int;
uniform vec3 uRight, uUp, uFwd, uOff; uniform float uSize; uniform float uP[24]; uniform vec3 uC[12]; uniform vec4 uS[32];
uniform samplerCube uK0, uK1, uK2; uniform sampler2D uRamp;
vec3 faceDirection() { vec2 uv = gl_FragCoord.xy / uSize * 2.0 - 1.0; return normalize(uFwd + uv.x * uRight + uv.y * uUp); }
uint hsh(ivec3 p) { uvec3 q = uvec3(p) * uvec3(2654435761u, 2246822519u, 3266489917u); uint h = q.x ^ q.y ^ q.z; h ^= h >> 15; h *= 2246822519u; h ^= h >> 13; h *= 3266489917u; h ^= h >> 16; return h; }
// the gradient at a lattice corner is one of the cube's eight diagonals: its dot product is three signs
float gdot(uint h, vec3 f) { h *= 2246822519u; h ^= h >> 15; h *= 3266489917u; uvec3 s = uvec3(h, h << 1, h << 2) & 0x80000000u; vec3 v = uintBitsToFloat(floatBitsToUint(f) ^ s); return v.x + v.y + v.z; }
// gradient noise, about -1 to 1, smooth to the second derivative (relief is lit by its slope)
float gnoise(vec3 x) {
  vec3 fl = floor(x), f = x - fl, g = f - 1.0;
  vec3 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  uvec3 a = uvec3(ivec3(fl)) * uvec3(2654435761u, 2246822519u, 3266489917u), b = a + uvec3(2654435761u, 2246822519u, 3266489917u);
  uint aa = a.x ^ a.y, ba = b.x ^ a.y, ab = a.x ^ b.y, bb = b.x ^ b.y;
  float lo = mix(mix(gdot(aa ^ a.z, f), gdot(ba ^ a.z, vec3(g.x, f.y, f.z)), u.x), mix(gdot(ab ^ a.z, vec3(f.x, g.y, f.z)), gdot(bb ^ a.z, vec3(g.x, g.y, f.z)), u.x), u.y);
  float hi = mix(mix(gdot(aa ^ b.z, vec3(f.x, f.y, g.z)), gdot(ba ^ b.z, vec3(g.x, f.y, g.z)), u.x), mix(gdot(ab ^ b.z, vec3(f.x, g.y, g.z)), gdot(bb ^ b.z, g), u.x), u.y);
  return mix(lo, hi, u.z) * 0.95;
}
vec4 hash4(ivec3 i) { uint h = hsh(i); return vec4(float(h & 255u), float((h >> 8) & 255u), float((h >> 16) & 255u), float(h >> 24)) / 255.0; }
vec3 turn(vec3 p, vec3 axis, float angle) { float c = cos(angle), s = sin(angle); return p * c + cross(axis, p) * s + axis * dot(axis, p) * (1.0 - c); }
float arc(vec3 a, vec3 b) { return acos(clamp(dot(a, b), -1.0, 1.0)); }
// a crater's height across its radius (d = 1 at the rim): a bowl with a flat floor, a sharp rim, a gentle apron
float bowl(float d, float floor_) { return (d < 1.0 ? max(d * d - 1.0, -floor_) : 0.0) + 0.30 * exp(-pow(abs(d - 1.0) * (d < 1.0 ? 8.0 : 3.0), 1.5)); }
// one size class of small craters: one may sit in each cell of a lattice of f cells a radius, on the sphere
float pocks(vec3 p, float f, int seed, float share) {
  vec3 x = p * f, c0 = floor(x - 0.5); float h = 0.0;
  for (int k = 0; k < 8; k++) {
    vec3 cell = c0 + vec3(float(k & 1), float((k >> 1) & 1), float((k >> 2) & 1));
    vec4 r = hash4(ivec3(cell) + seed);
    vec3 centre = cell + 0.25 + 0.5 * r.xyz;
    float off = abs(length(centre) - f), rad = 0.09 + 0.25 * r.w * r.w;
    float d = length(x - normalize(centre) * f) / rad;
    h += rad * bowl(d, 0.8) * step(off, 0.5) * step(fract(r.x * 7.31 + r.y * 3.17), share);
  }
  return 0.26 * h / f;
}
${fbm("fbm2", 2)}${fbm("fbm3", 3)}${fbm("fbm4", 4)}${fbm("fbmH", "OCT", 0.52)}${fbm("fbmC", "OCT", 0.58)}${ridge("ridge4", 4)}${ridge("ridgeM", "OCTM")}
`;

// ---------- the surface types: what each bakes ----------
// A type bakes in three passes. `coarse(p, which)` gives slow fields (warps, climates, wound air) on
// small cube maps uK0..uK2; `fields(p)` gives vec4(height, three fields of its own) at full size;
// `paint` turns them (and the slope of the height) into colour, gloss or glow. uP: numbers, uC:
// colours, uS: placed things (craters, cyclones, storms, cracks), set from the options and the seed.
const OCEAN_COARSE = /* glsl */`
vec4 coarse(vec3 p, int which) {
  vec3 q = p * uP[0] + uOff;
  if (which == 0) return vec4(fbm3(q * 0.9 + 31.4), fbm3(q * 0.9 + 67.9), fbm3(q * 0.9 + 113.5), fbm3(q * 1.6 + 7.7));
  if (which == 2) return vec4(fbm4(q * 1.9 + 201.0), fbm4(q * 2.7 + 57.0), fbm4(q * 4.1 + 301.0), fbm3(q * 3.0 + 401.0));
  vec3 c = p; float eyes = 0.0;
  for (int i = 0; i < 12; i++) {                    // the weather systems: each winds the air around its eye
    vec4 s = uS[i];
    float d = arc(c, s.xyz) / abs(s.w);
    c = turn(c, s.xyz, sign(s.w) * uP[12] * exp(-d * d * 1.2) / (0.3 + d));
    d = arc(p, s.xyz) / abs(s.w);
    eyes += 0.20 * exp(-d * d * 1.6) - 0.6 * exp(-d * d * 120.0);
  }
  return vec4(c, eyes);
}`;
const OCEAN_FIELDS = /* glsl */`
float cloudField(vec3 p) {
  vec4 k = textureCube(uK1, p);
  vec3 c = normalize(k.xyz);
  float lat = asin(clamp(c.y, -1.0, 1.0));
  vec3 w = textureCube(uK0, c.zxy).xyz;
  vec3 q = c * vec3(1.0, 1.7, 1.0) * uP[8] + uOff.zxy * 1.7;
  float n = fbmC(q + 0.9 * w);                                     // decks, streets and fronts
  float cells = 1.0 - 2.0 * abs(fbm3(q * 6.1 + w * 2.0 + 9.0));    // the small cells that break a deck up
  float wisps = fbm3(c * vec3(1.0, 4.5, 1.0) * uP[8] * 1.3 + w * 1.2 + 77.0);   // high thin cloud drawn out along the wind
  // more cloud on the equator's wet belt and the storm tracks, clear skies over the dry belts between
  float belt = 0.12 * exp(-lat * lat * 45.0) + 0.14 * smoothstep(0.5, 0.95, abs(lat)) - 0.16 * exp(-pow((abs(lat) - 0.42) * 4.5, 2.0));
  float v = n + belt + k.a + uP[9];
  float deck = smoothstep(0.0, 0.30, v + 0.10 * cells);
  float body = deck * (0.50 + 0.50 * smoothstep(-0.45, 0.5, cells)) * (0.62 + 0.55 * smoothstep(0.08, 0.55, v));
  float thin = 0.34 * smoothstep(0.02, 0.4, wisps + 0.35 * v + 0.08);
  return clamp(max(body, thin), 0.0, 1.0);
}
vec4 fields(vec3 p) {
  vec4 k0 = textureCube(uK0, p), k2 = textureCube(uK2, p);
  vec3 q = p * uP[0] + uOff, w = k0.xyz;
  float c = fbmH(q + uP[1] * w) + 0.10 * k2.a;
  float e = c - uP[2];                                             // over the sea when positive
  float land = smoothstep(0.0, 0.05, e);
  float chains = smoothstep(-0.12, 0.22, k0.a + 0.5 * w.x);
  float m = ridgeM(q * 3.3 + w * 0.9 + 19.0);
  float h = e + land * (chains * m * m * uP[3] + 0.03 * k2.a);
  float lat = asin(clamp(p.y, -1.0, 1.0));
  float wet = 0.5 + 0.8 * k2.x + 0.22 * cos(lat * 6.0) - 0.25 * max(h, 0.0) + uP[5];
  float warm = 1.0 - 1.12 * pow(abs(p.y), 1.6) - 0.9 * max(h - 0.05, 0.0) + 0.10 * k2.y + uP[4];
  return vec4(h, wet, warm, uP[10] > 0.0 ? cloudField(p) : 0.0);
}`;
const OCEAN_PAINT = /* glsl */`
void paint(vec3 n, vec4 F, float slope, out vec3 albedo, out float gloss, out float glow) {
  float h = F.r, wet = clamp(F.g, 0.0, 1.0), warm = F.b;
  vec4 k2 = textureCube(uK2, n);
  float fine = gnoise(n * 37.0 + uOff), finer = gnoise(n * uSize * 0.42 + 7.0);
  float land = smoothstep(-0.004, 0.004, h);
  vec3 sea = mix(uC[0], uC[1], pow(smoothstep(-0.16, 0.0, h), 3.0)) * (1.0 + 0.25 * k2.y);
  float dry = 1.0 - wet + 0.06 * fine;
  vec3 ground = mix(uC[4], uC[3], smoothstep(0.30, 0.50, dry));
  ground = mix(ground, uC[2], smoothstep(0.50, 0.72, dry));
  ground *= 1.0 + 0.35 * k2.a + 0.12 * fine;                                            // patchy, as real country is
  ground = mix(ground, uC[7], smoothstep(0.36, 0.18, warm));                            // tundra where it is cold
  ground = mix(ground, uC[5], clamp(smoothstep(0.10, 0.34, h) * 0.8 + smoothstep(0.5, 1.6, slope) * 0.5, 0.0, 1.0));   // bare rock on high and steep ground
  float snow = smoothstep(0.17, 0.09, warm - 0.035 * fine);
  float pack = smoothstep(0.10, 0.04, warm - 0.045 * fine);                             // sea ice
  albedo = mix(mix(sea, uC[6] * vec3(0.93, 0.97, 1.0), pack), mix(ground, uC[6], snow), land);
  gloss = (1.0 - land) * (1.0 - pack);
  // towns: on low, green or coastal ground, in clusters; none on ice, few in deserts
  float people = smoothstep(0.08, 0.4, k2.z + 0.3 * smoothstep(0.10, 0.0, h) - 0.28) * smoothstep(0.75, 0.45, dry) * smoothstep(0.15, 0.3, warm) * smoothstep(0.3, 0.1, h);
  float dots = pow(clamp(0.5 + 0.6 * finer, 0.0, 1.0), 5.0) * smoothstep(0.0, 0.45, fine + 0.6 * k2.a);
  glow = land * (1.0 - snow) * people * dots * uP[11];
}`;

// an airless, cratered world: highlands, dark plains (maria), craters of every size, a few fresh ones with rays
const ROCKY_COARSE = /* glsl */`
vec4 coarse(vec3 p, int which) {
  vec3 q = p * uP[0] + uOff;
  if (which == 0) return vec4(fbm3(q + 31.4), fbm3(q + 67.9), fbm3(q + 113.5), fbm4(q * 0.75 + 7.7));
  if (which == 2) return vec4(fbm4(q * 2.3 + 201.0), fbm4(q * 5.1 + 57.0), fbm3(q * 9.0 + 301.0), 0.0);
  float rays = 0.0;
  for (int i = 0; i < 5; i++) {                     // the youngest craters threw bright streaks far over the old ground
    vec4 s = uS[i]; float d = arc(p, s.xyz) / s.w;
    vec3 dir = normalize(p - s.xyz * dot(p, s.xyz) + 1e-6);
    float streak = gnoise(dir * 4.0 + float(i) * 13.0) + 0.6 * gnoise(dir * 11.0 + float(i) * 7.0);
    rays += smoothstep(0.05, 0.9, streak) * exp(-d / (3.0 + 4.0 * uP[6])) * smoothstep(0.9, 1.5, d) + 0.8 * exp(-max(d - 1.0, 0.0) * 1.6) * smoothstep(0.75, 1.0, d);
  }
  return vec4(rays * uP[6], 0.0, 0.0, 0.0);
}`;
const ROCKY_FIELDS = /* glsl */`
vec4 fields(vec3 p) {
  vec4 k0 = textureCube(uK0, p), k1 = textureCube(uK1, p), k2 = textureCube(uK2, p);
  vec3 q = p * uP[0] + uOff, w = k0.xyz;
  float rough = fbmH(q * 4.0 + 0.6 * w);
  float mare = smoothstep(uP[2] - 0.03, uP[2] + 0.03, k0.a + 0.12 * w.x + 0.03 * k2.y + 0.05 * rough);
  for (int i = 5; i < 11; i++) { vec4 s = uS[i]; mare = max(mare, smoothstep(0.9, 0.78, arc(p, s.xyz) / s.w + 0.1 * rough) * step(0.09, s.w) * step(0.03, uP[8])); }   // the largest basins are flooded too
  float h = (0.022 * rough + 0.004 * k2.x) * (1.0 - 0.85 * mare) - 0.006 * mare;
  float few = 1.0 - 0.72 * mare;                                   // the plains are younger: fewer craters
  float pk = pocks(p, 5.0, 11, 0.8 * few * uP[4]) + pocks(p, 9.0, 23, 0.9 * few * uP[4]) + pocks(p, 17.0, 37, 0.9 * few * uP[4]) + pocks(p, 31.0, 43, 0.9 * few * uP[4]);
#if OCT > 5
  pk += pocks(p, 57.0, 51, 0.9 * few * uP[4]);
#endif
#if OCT > 6
  pk += pocks(p, 110.0, 67, 0.9 * few * uP[4]);
#endif
  h += pk * uP[5];
  float fresh = 0.0;
  for (int j = 0; j < 28; j++) {                    // the big ones, oldest first: each wipes out what lay under it
    int i = 27 - j; vec4 s = uS[i]; float d = arc(p, s.xyz) / s.w;
    float inside = smoothstep(1.15, 0.85, d);
    h = mix(h, h * 0.25, inside) + 0.22 * s.w * bowl(d, 0.62 - 3.0 * s.w) * uP[5] + (d < 0.16 && s.w > 0.05 ? 0.10 * s.w * (1.0 - d / 0.16) : 0.0);
    if (i < 5) fresh += inside;
  }
  return vec4(h, mare, k1.r + 0.5 * fresh, 0.0);
}`;
const ROCKY_PAINT = /* glsl */`
void paint(vec3 n, vec4 F, float slope, out vec3 albedo, out float gloss, out float glow) {
  vec4 k2 = textureCube(uK2, n);
  float fine = gnoise(n * 43.0 + uOff);
  albedo = mix(uC[0], uC[1], F.g * (0.82 + 0.3 * k2.y)) * (1.0 + 0.34 * k2.x + 0.16 * k2.y + 0.09 * fine);
  albedo = mix(albedo, uC[3], smoothstep(0.1, 0.5, k2.z + 0.3 * k2.x) * uP[7]);        // a second kind of ground
  albedo *= 1.0 + 0.22 * smoothstep(0.25, 1.1, slope);                                 // steep slopes shed their dark dust
  albedo = mix(albedo, uC[2], clamp(F.b, 0.0, 0.9));                                   // rays and fresh ejecta
  gloss = 0.0; glow = 0.0;
}`;

// an ice shell: bright, smooth, crossed by long dark cracks (lineae), stained plains, few craters
const ICY_COARSE = /* glsl */`
vec4 coarse(vec3 p, int which) {
  vec3 q = p * uP[0] + uOff;
  if (which == 0) return vec4(fbm3(q + 31.4), fbm3(q + 67.9), fbm3(q + 113.5), fbm4(q * 0.8 + 7.7));
  if (which == 2) return vec4(fbm4(q * 2.3 + 201.0), fbm4(q * 5.1 + 57.0), fbm3(q * 9.0 + 301.0), 0.0);
  return vec4(0.0);
}`;
const ICY_FIELDS = /* glsl */`
vec4 fields(vec3 p) {
  vec4 k0 = textureCube(uK0, p), k2 = textureCube(uK2, p);
  vec3 q = p * uP[0] + uOff, w = k0.xyz;
  vec3 pw = normalize(p + 0.06 * w + 0.012 * vec3(k2.y, k2.x, k2.z));
  float stain = 0.0, ridges = 0.0;
  for (int i = 0; i < 26; i++) {                    // each crack follows a circle on the globe, in pieces
    vec4 s = uS[i];
    float d = abs(dot(pw, s.xyz) - s.w), width = uP[5] * (0.35 + 0.9 * fract(float(i) * 0.618));
    float shows = smoothstep(-0.35, 0.25, sin(dot(pw, s.yzx) * (1.6 + 0.5 * float(i % 4)) + float(i) * 2.4) + 0.35 * k2.x);
    stain = max(stain, shows * smoothstep(width, width * 0.25, d) * (0.5 + 0.5 * fract(float(i) * 0.37)));
    ridges += shows * (exp(-pow(d / (width * 1.4), 2.0)) - 0.7 * exp(-pow(d / (width * 0.45), 2.0)));
  }
  float net = 1.0 - abs(fbmH(q * 3.1 + 0.8 * w));                   // the fine web of fractures between
  float web = pow(net, 14.0);
  float chaos = smoothstep(uP[2] - 0.07, uP[2] + 0.07, k0.a + 0.15 * k2.x);   // broken, stained country
  float h = 0.0022 * ridges + 0.0016 * web + 0.006 * chaos * fbm3(q * 14.0 + 3.0) + 0.003 * k2.x;
  float few = uP[4] * (0.25 + 0.75 * chaos);
  float pk = pocks(p, 9.0, 11, 0.5 * few) + pocks(p, 21.0, 23, 0.5 * few) + pocks(p, 47.0, 37, 0.5 * few);
  float fresh = 0.0;
  for (int i = 0; i < 6; i++) { vec4 s = uS[i + 32 - 6]; float d = arc(p, normalize(s.xyz)) / s.w; h += 0.2 * s.w * bowl(d, 0.4); fresh += exp(-max(d - 0.6, 0.0) * 0.9) * step(0.5, uP[7]); }
  h += pk * 0.7;
  return vec4(h, max(stain, 0.55 * web * (0.4 + 0.6 * chaos)), chaos, fresh);
}`;
const ICY_PAINT = /* glsl */`
void paint(vec3 n, vec4 F, float slope, out vec3 albedo, out float gloss, out float glow) {
  vec4 k2 = textureCube(uK2, n);
  float fine = gnoise(n * 43.0 + uOff);
  vec3 ice = uC[0] * (1.0 + 0.10 * k2.x + 0.05 * fine);
  albedo = mix(ice, uC[2] * (1.0 + 0.3 * k2.y + 0.1 * fine), F.b * (0.75 + 0.25 * k2.z));     // the stained, broken plains
  albedo = mix(albedo, uC[1], clamp(F.g * uP[6], 0.0, 1.0));                                  // the cracks' dark fill
  albedo = mix(albedo, uC[3], clamp(F.a * 0.6, 0.0, 0.85));                                   // fresh ice thrown from young craters
  albedo *= 1.0 + 0.15 * smoothstep(0.2, 0.9, slope);
  gloss = 0.0; glow = 0.0;
}`;

// a dusty desert world: bright dust and dark old lava, shield volcanoes, a canyon system, craters, polar caps
const DESERT_COARSE = /* glsl */`
vec4 coarse(vec3 p, int which) {
  vec3 q = p * uP[0] + uOff;
  if (which == 0) return vec4(fbm3(q + 31.4), fbm3(q + 67.9), fbm3(q + 113.5), fbm4(q * 0.7 + 7.7));
  if (which == 2) return vec4(fbm4(q * 2.3 + 201.0), fbm4(q * 5.1 + 57.0), fbm3(q * 9.0 + 301.0), fbm4(q * 1.3 + 91.0));
  return vec4(0.0);
}`;
const DESERT_FIELDS = /* glsl */`
vec4 fields(vec3 p) {
  vec4 k0 = textureCube(uK0, p), k2 = textureCube(uK2, p);
  vec3 q = p * uP[0] + uOff, w = k0.xyz;
  float low = smoothstep(-0.25, 0.25, k0.a + 0.35 * p.y * uP[8]);       // the low, smooth half of the world
  float rough = fbmH(q * 2.2 + 0.7 * w), crags = ridgeM(q * 4.0 + w + 19.0);
  float h = 0.012 * rough * (1.0 - 0.6 * low) - 0.010 * low + 0.006 * crags * crags * smoothstep(0.0, 0.3, k2.a) * (1.0 - low);
  float few = uP[4] * (1.0 - 0.75 * low);
  float pk = pocks(p, 6.0, 11, 0.7 * few) + pocks(p, 13.0, 23, 0.7 * few) + pocks(p, 29.0, 37, 0.6 * few);
#if OCT > 5
  pk += pocks(p, 63.0, 51, 0.6 * few);
#endif
  h += pk * 0.7;
  for (int i = 0; i < 8; i++) { vec4 s = uS[i]; float d = arc(p, s.xyz) / s.w; h = mix(h, h * 0.3, smoothstep(1.15, 0.85, d)) + 0.25 * s.w * bowl(d, 0.5); }
  for (int i = 8; i < 12; i++) {                    // shield volcanoes: broad, gentle, a pit at the top
    vec4 s = uS[i]; float d = arc(p, s.xyz) / s.w;
    h += 0.16 * s.w * (pow(max(1.0 - d, 0.0), 1.6) - 0.35 * smoothstep(0.13, 0.07, d)) * uP[9];
  }
  float canyon = 0.0;
  vec3 pw = normalize(p + 0.05 * w + 0.015 * vec3(k2.y, k2.z, k2.x));
  float side = 0.7 * smoothstep(0.88, 1.0, ridge4(q * 6.0 + w * 2.0));
  for (int i = 12; i < 20; i += 2) {                // canyons: troughs along a circle, as long as their arc, with side branches
    vec4 a = uS[i], b = uS[i + 1];
    float along = arc(p, b.xyz) / b.w, d = abs(dot(pw, a.xyz) - a.w), width = 0.016 * (1.0 - 0.55 * along) * (1.0 + 0.5 * k2.x);
    float reach = smoothstep(1.0, 0.75, along);
    canyon = max(canyon, reach * max(smoothstep(width, width * 0.45, d), side * smoothstep(width * 4.0, width, d)));
  }
  h -= 0.014 * canyon * uP[10];
  float cap = smoothstep(uP[3] - 0.03, uP[3] + 0.015, abs(p.y) + 0.035 * k2.x + 0.02 * sin(atan(p.z, p.x) * 3.0 + 9.0 * abs(p.y)) + 1.2 * h);
  float dark = smoothstep(uP[2] - 0.12, uP[2] + 0.12, k2.a + 0.5 * w.y - 0.25 * low + 0.3) ;
  return vec4(h, dark, cap, canyon);
}`;
const DESERT_PAINT = /* glsl */`
void paint(vec3 n, vec4 F, float slope, out vec3 albedo, out float gloss, out float glow) {
  vec4 k2 = textureCube(uK2, n);
  float fine = gnoise(n * 43.0 + uOff);
  vec3 dust = mix(uC[0], uC[2], smoothstep(-0.3, 0.3, k2.y + 0.5 * k2.x));                // two tones of dust
  albedo = mix(dust, uC[1], F.g * (0.8 + 0.2 * k2.z)) * (1.0 + 0.16 * k2.x + 0.07 * fine);
  albedo *= 1.0 - 0.35 * F.a - 0.25 * smoothstep(0.3, 1.2, slope);                        // canyon floors and steep walls are darker
  albedo = mix(albedo, uC[3], F.b);                                                       // the caps' ice
  gloss = 0.0; glow = 0.0;
}`;

// a molten world: a dark crust broken into plates, glowing where it parts; or (style 1) sulphur plains with dark vents
const LAVA_COARSE = /* glsl */`
vec4 coarse(vec3 p, int which) {
  vec3 q = p * uP[0] + uOff;
  if (which == 0) return vec4(fbm3(q + 31.4), fbm3(q + 67.9), fbm3(q + 113.5), fbm4(q * 0.8 + 7.7));
  if (which == 2) return vec4(fbm4(q * 2.3 + 201.0), fbm4(q * 5.1 + 57.0), fbm3(q * 9.0 + 301.0), fbm4(q * 1.4 + 91.0));
  return vec4(0.0);
}`;
const LAVA_FIELDS = /* glsl */`
vec4 fields(vec3 p) {
  vec4 k0 = textureCube(uK0, p), k2 = textureCube(uK2, p);
  vec3 q = p * uP[0] + uOff, w = k0.xyz;
  float hot = smoothstep(-0.30, 0.50, k0.a + 0.3 * w.z + uP[2]);          // where the crust is thin
  float plates = abs(fbmH(q * 1.9 + 0.9 * w)), small = abs(fbm4(q * 7.0 + 1.5 * w + 40.0));
  float seam = min(plates, 0.55 * small + 0.06 * (1.0 - hot));            // near 0 along the cracks
  float width = 0.005 + 0.035 * hot * hot;
  float glow = smoothstep(width, width * 0.2, seam) * (0.35 + 0.65 * hot) + 0.8 * smoothstep(0.97, 1.06, hot + 0.14 * k2.x);   // cracks, and seas of lava where it is hottest
  float crust = fbmC(q * 4.2 + w + 77.0);
  float h = 0.010 * smoothstep(0.0, 0.12, seam) + 0.006 * crust * (1.0 - glow);
  float vents = 0.0, rings = 0.0;
  for (int i = 0; i < 16; i++) {                    // vents: a dark floor, a hot spot, a ring of fallout
    vec4 s = uS[i]; float d = arc(p, s.xyz) / s.w, edge = d + 0.25 * k2.y;
    vents = max(vents, smoothstep(0.42, 0.28, edge));
    rings = max(rings, smoothstep(0.35, 0.6, edge) * smoothstep(1.3, 0.75, edge) * (0.5 + 0.5 * fract(float(i) * 0.618)));
    h += 0.05 * s.w * (smoothstep(1.0, 0.4, d) - 1.4 * smoothstep(0.42, 0.3, d)) * uP[7];
  }
  if (uP[7] > 0.5) glow = vents * smoothstep(0.15, 0.6, k2.z + 0.35) * 0.55;
  return vec4(h, clamp(glow * uP[3], 0.0, 1.0), vents, rings);
}`;
const LAVA_PAINT = /* glsl */`
void paint(vec3 n, vec4 F, float slope, out vec3 albedo, out float gloss, out float glow_) {
  vec4 k0 = textureCube(uK0, n), k2 = textureCube(uK2, n);
  float fine = gnoise(n * 43.0 + uOff);
  if (uP[7] > 0.5) {                                 // sulphur: pale plains, orange and white patches, red fallout, black vents
    vec3 c = mix(uC[0], uC[1], smoothstep(-0.2, 0.25, k0.a + 0.4 * k2.x));
    c = mix(c, uC[2], smoothstep(0.1, 0.4, k2.a + 0.3 * k2.y));
    c = mix(c, uC[4], smoothstep(0.55, 1.0, abs(n.y) + 0.2 * k2.x) * 0.8);             // the poles' darker frost
    c *= 1.0 + 0.14 * k2.y + 0.07 * fine;
    c = mix(c, uC[3], F.a * 0.8);
    albedo = mix(c, uC[5], F.b);
  } else {
    albedo = mix(uC[0], uC[1], smoothstep(-0.3, 0.4, k2.a + 0.5 * k2.x)) * (1.0 + 0.25 * k2.y + 0.12 * fine);   // basalt and ash
    albedo = mix(albedo, uC[2], smoothstep(0.0, 0.5, F.g));                                                    // crust scorched beside the fire
  }
  gloss = 0.0; glow_ = F.g;
}`;

// a giant of gas: belts and zones along the parallels, unruly where they meet, storms that bend the bands
const GAS_COARSE = /* glsl */`
vec4 coarse(vec3 p, int which) {
  vec3 q = p * vec3(1.0, uP[1], 1.0) * uP[0] + uOff;
  if (which == 0) return vec4(fbm3(q * 0.9 + 31.4), fbm3(q * 0.9 + 67.9), fbm3(q * 0.9 + 113.5), fbm3(q * 0.5 + 7.7));
  if (which == 2) return vec4(fbm4(p * 2.0 + uOff + 201.0), 0.0, 0.0, 0.0);
  vec3 c = p;
  for (int i = 0; i < 12; i++) {                    // each storm turns the air round itself
    vec4 s = uS[i]; float d = arc(c, s.xyz) / abs(s.w);
    c = turn(c, s.xyz, sign(s.w) * uP[6] * exp(-d * d * 0.9) / (0.25 + d));
  }
  return vec4(c, 0.0);
}`;
const GAS_FIELDS = /* glsl */`
vec4 fields(vec3 p) {
  vec4 k0 = textureCube(uK0, p);
  vec3 c = normalize(textureCube(uK1, p).xyz), w = k0.xyz;
  vec3 q = c * vec3(1.0, uP[1], 1.0) * uP[0] + uOff;
  float unruly = texture2D(uRamp, vec2(0.5 + 0.5 * c.y, 0.5)).a;
  float turb = fbmH(q * 1.3 + 1.1 * w);                                   // long streamers, torn where the warp is strong
  vec3 q2 = q + vec3(0.9, 0.25, 0.9) * turb;
  float curl = fbm4(q2 * vec3(3.1, 1.5, 3.1) + 2.0 * w + 23.0);           // the small eddies along a belt's edge
  float v = 0.5 + 0.5 * c.y + uP[2] * (0.10 + unruly) * (0.034 * turb + 0.026 * curl) + 0.006 * k0.a * uP[2];
  float streaks = fbmC(q2 * vec3(1.6, 4.0, 1.6) + 1.2 * w + 40.0);
  float storm = 0.0;
  for (int i = 0; i < 12; i++) {
    vec4 s = uS[i]; float dy = (p.y - s.y) / abs(s.w), d = arc(p, s.xyz) / abs(s.w);
    float e = sqrt(max(d * d - dy * dy, 0.0) * 0.36 + dy * dy * 1.9) + 0.10 * turb;     // an oval, longer along the parallel
    float m = smoothstep(1.0, i == 0 ? 0.7 : 0.3, e);
    storm = i == 0 ? m * uP[7] : mix(storm, -1.0, m);
  }
  return vec4(v, streaks, storm, turb + 0.6 * curl);
}`;
const GAS_PAINT = /* glsl */`
void paint(vec3 n, vec4 F, float slope, out vec3 albedo, out float gloss, out float glow) {
  vec4 band = texture2D(uRamp, vec2(clamp(F.r, 0.002, 0.998), 0.5));
  vec3 c = band.rgb * band.rgb;
  c *= 1.0 + uP[3] * (1.9 * F.g + 0.6 * F.a);
  c = mix(c, uC[0], max(F.b, 0.0) * (0.75 + 0.5 * F.g));                  // the great storm
  c = mix(c, uC[1], max(-F.b, 0.0) * 0.6);                                // white ovals
  float polar = smoothstep(0.62, 0.98, abs(n.y) + 0.04 * F.a);
  albedo = mix(c, uC[2] * (1.0 + 0.2 * F.a), polar * uP[4]);              // the poles' haze
  gloss = 0.0; glow = 0.0;
}`;

// ---------- bands and rings: profiles from a seed (pure, tested in Node) ----------
// the inverse error function (Winitzki's approximation: enough to place a sea level)
function erfinv(x) { const a = 0.147, l = Math.log(1 - x * x), u = 2 / (Math.PI * a) + l / 2; return Math.sign(x) * Math.sqrt(Math.sqrt(u * u - l / a) - u); }
/** The level a field of normal spread `sigma` must pass for `share` of the globe to lie above it. */
export const levelFor = (share, sigma) => sigma * Math.SQRT2 * erfinv(1 - 2 * Math.min(0.98, Math.max(0.02, share)));
// smooth noise along a line: `counts` octaves of random values, read at u from 0 to 1
function lineNoise(r, counts) {
  const oct = counts.map((k) => Array.from({length: k + 2}, () => r()));
  return (u, j) => { const x = clamp01(u) * (oct[j].length - 2), i = Math.floor(x), f = x - i; return mix(oct[j][i], oct[j][i + 1], f * f * (3 - 2 * f)); };
}

/** The colours of a giant along its latitudes (south pole to north, `n` entries of [r, g, b, unruly]):
 * zones and belts in turn, each a little different; `unruly` is how much the bands' edges are stirred
 * there. Pure: the same seed, the same bands. */
export function bandRamp(seed, {bands = 13, contrast = 1, zones, belts, n = 512} = {}) {
  const r = rng(seed * 2909 + 5), count = Math.max(3, Math.round(bands)) | 1;      // odd: a zone on the equator
  const edges = [-90];
  for (let i = 1; i < count; i++) edges.push(-90 + 180 * i / count + (r() - 0.5) * 70 / count);
  edges.push(90);
  const mid = (count - 1) / 2, cols = [];
  for (let i = 0; i < count; i++) {
    const list = (i - mid) % 2 === 0 ? zones : belts, c = list[Math.floor(r() * list.length)], k = 0.9 + 0.2 * r();
    cols.push(c.map((x) => x * k));
  }
  const mean = [0, 1, 2].map((j) => cols.reduce((s, c) => s + c[j], 0) / count), fine = lineNoise(r, [34, 90, 240]), out = [];
  for (let i = 0; i < n; i++) {
    const lat = Math.asin(2 * (i + 0.5) / n - 1) / RAD;
    let b = 0; while (b < count - 1 && lat > edges[b + 1]) b++;
    const soft = 0.2 * (edges[b + 1] - edges[b]);
    let c = cols[b], edge = 1;
    if (b > 0 && lat - edges[b] < soft) { c = mix3(cols[b - 1], cols[b], smooth(-soft, soft, lat - edges[b])); edge = (lat - edges[b]) / soft; }
    if (b < count - 1 && edges[b + 1] - lat < soft) { c = mix3(cols[b], cols[b + 1], smooth(-soft, soft, lat - edges[b + 1])); edge = (edges[b + 1] - lat) / soft; }
    const u = (lat + 90) / 180, streak = 0.45 * fine(u, 0) + 0.33 * fine(u, 1) + 0.22 * fine(u, 2) - 0.5;
    out.push([...c.map((v, j) => Math.max(0, (mean[j] + (v - mean[j]) * contrast) * (1 + 0.6 * streak * Math.min(1, contrast)))), (1 - 0.7 * edge) * smooth(88, 55, Math.abs(lat))]);
  }
  return out;
}

export const RING_STYLES = Object.freeze(["broad", "narrow"]);
/** A ring system's profile from its inner edge to its outer (`n` entries of [r, g, b, optical depth]).
 * "broad": a wide sheet in provinces (a thin inner one, a dense middle, a main gap, an outer one), cut by
 * ringlets and `gaps` narrow gaps; "narrow": `gaps` thin rings and a little dust. Pure: the same seed, the same rings. */
export function ringProfile(seed, {style = "broad", color = [0.62, 0.52, 0.38], opacity = 1, gaps = 7, n = 1024} = {}) {
  const r = rng(seed * 4099 + 7), noise = lineNoise(r, [7, 19, 53, 150, 400]), out = [];
  const a = 0.15 + 0.10 * r(), b = 0.58 + 0.10 * r(), gap = 0.03 + 0.025 * r(), outer = 0.35 + 0.5 * r(), dense = 1.0 + 1.2 * r();
  const cuts = Array.from({length: Math.max(0, Math.round(gaps))}, () => ({at: style === "broad" ? 0.04 + 0.94 * r() : 0.08 + 0.84 * r(), width: style === "broad" ? 0.0015 + 0.006 * r() * r() : 0.003 + 0.02 * r() * r(), depth: 0.3 + 1.6 * r()}));
  for (let i = 0; i < n; i++) {
    const u = (i + 0.5) / n;
    let tau, tint;
    if (style === "broad") {
      const inner = 0.07 + 0.10 * noise(u, 1), middle = dense * (0.55 + 0.9 * noise(u, 0)), far = outer * (0.7 + 0.6 * noise(u, 1));
      tau = mix(inner, middle, smooth(a - 0.012, a + 0.012, u));
      tau = mix(tau, 0.02, smooth(b - 0.004, b + 0.004, u));
      tau = mix(tau, far, smooth(b + gap - 0.004, b + gap + 0.004, u));
      tau *= 0.45 + 1.1 * (0.45 * noise(u, 2) + 0.33 * noise(u, 3) + 0.22 * noise(u, 4));           // ringlets
      for (const c of cuts) tau *= 1 - Math.min(1, c.depth) * smooth(c.width, c.width * 0.4, Math.abs(u - c.at));
      tau *= smooth(0, 0.01, u) * smooth(1, 0.993, u);
      const grey = (color[0] + color[1] + color[2]) / 3;
      tint = mix3([grey * 0.62, grey * 0.6, grey * 0.6], color, smooth(a - 0.05, a + 0.08, u)).map((v) => v * (0.80 + 0.22 * noise(u, 1) + 0.30 * noise(u, 2) + 0.24 * noise(u, 3) - 0.12 * noise(u, 4)) * (u > b + gap ? 1.05 : 1));
    } else {
      tau = 0.006 * noise(u, 1);
      for (const c of cuts) tau += c.depth * Math.exp(-Math.pow((u - c.at) / c.width, 4));
      tint = color.map((v) => v * (0.85 + 0.3 * noise(u, 2)));
    }
    out.push([...tint, Math.min(4, tau * opacity)]);
  }
  return out;
}

// ---------- the types: options, palettes, and what the seed places ----------
const anywhere = (r, lo, hi, skew = 1) => {
  const y = 2 * r() - 1, a = r() * TAU, c = Math.sqrt(1 - y * y);
  return [c * Math.cos(a), y, c * Math.sin(a), lo + (hi - lo) * Math.pow(r(), skew)];
};
const P = (list) => list.map(hex);
const KINDS = {
  ocean: {
    coarse: OCEAN_COARSE, fields: OCEAN_FIELDS, paint: OCEAN_PAINT, relief: "smoothstep(0.0, 0.01, F.r)", last: "F.a", air: "earth",
    features: {clouds: true, glint: true, glow: "lights", relief: true},
    defaults: {land: 0.3, mountains: 1, ice: 1, wet: 0, clouds: 0.5, cloudDrift: 0, lights: 0.3, relief: 1, palette: "earth"},
    // sea deep, sea shallow; land dry, grass, forest, rock, (snow), tundra; snow; clouds; lights
    palettes: {
      earth: {sea: [0x02081c, 0x0c3f5a], land: [0xb39b72, 0x77794a, 0x1c3312, 0x6a6258, 0x7b7462], snow: 0xf2f6fa, clouds: 0xeef0f2, lights: 0xffc98a},
      verdant: {sea: [0x021a1c, 0x12665e], land: [0xc2a070, 0x8a7a3a, 0x3a2a1a, 0x5c5248, 0x6f6a52], snow: 0xf4f4ee, clouds: 0xf2efe8, lights: 0xbfe8ff},
      rust: {sea: [0x0a0c20, 0x2a3a66], land: [0xb8704a, 0x8a4a34, 0x5a2a2a, 0x54463e, 0x6a5a50], snow: 0xf0ece8, clouds: 0xf0e8e0, lights: 0xffd9a0},
    },
    setup(o, r, b) {
      const pal = o.palette;
      b.numbers[0] = 1.25 + 0.35 * r(); b.numbers[1] = 0.85; b.numbers[2] = levelFor(o.land, 0.215); b.numbers[3] = 0.55 * o.mountains;
      b.numbers[4] = 0.10 * (1 - o.ice); b.numbers[5] = 0.25 * o.wet;
      b.numbers[8] = 2.3; b.numbers[9] = -0.02 + 0.6 * (o.clouds - 0.5); b.numbers[10] = o.clouds > 0 ? 1 : 0; b.numbers[11] = o.lights > 0 ? 1 : 0; b.numbers[12] = 2.4;
      [...pal.sea, ...pal.land].forEach((c, i) => { b.colors[i] = hex(c); });
      b.colors[7] = b.colors[6]; b.colors[6] = hex(pal.snow);
      for (let i = 0; i < 12; i++) {                       // the weather systems of the storm tracks, by turns north and south
        const south = i % 2 === 1, g = onGlobe((38 + 24 * r()) * (south ? -1 : 1), i * 61 + 40 * r());
        b.spots[i] = [...g, (0.11 + 0.10 * r()) * (south ? -1 : 1)];
      }
      b.bump = 0.035 * o.relief;
    },
  },
  rocky: {
    coarse: ROCKY_COARSE, fields: ROCKY_FIELDS, paint: ROCKY_PAINT, relief: "1.0", last: "0.5 + F.r * 12.0", air: null,
    features: {shadows: 12, relief: true, regolith: 0.6},
    defaults: {craters: 1, maria: 0.3, rays: 1, patches: 0, relief: 1, palette: "moon"},
    // highlands, maria, rays, patches
    palettes: {
      moon: [0x97938c, 0x504d49, 0xd4d1cb, 0x7d7468],
      mercury: [0x8f8274, 0x61584e, 0xd6cab8, 0x6e6258],
      callisto: [0x574a3c, 0x43392f, 0xe0d9cb, 0x6a5a46],
      cinder: [0x6a4236, 0x2c2222, 0xc2957a, 0x47342f],
    },
    setup(o, r, b) {
      b.numbers[0] = 1.3 + 0.4 * r(); b.numbers[2] = levelFor(o.maria, 0.19); b.numbers[4] = Math.min(1.3, o.craters); b.numbers[5] = Math.min(1.6, 0.5 + 0.5 * o.craters);
      b.numbers[6] = o.rays; b.numbers[7] = o.patches; b.numbers[8] = o.maria;
      P(o.palette).forEach((c, i) => { b.colors[i] = c; });
      const big = Math.round(Math.min(23, 4 + 14 * o.craters));
      for (let i = 0; i < 5; i++) b.spots[i] = anywhere(r, 0.02, 0.055, 1);              // the young ones, with rays: cut last
      for (let i = 0; i < big; i++) b.spots[5 + i] = anywhere(r, 0.035, 0.20, 2.2);      // the old basins and craters
      b.bump = 1.0 * o.relief;
    },
  },
  icy: {
    coarse: ICY_COARSE, fields: ICY_FIELDS, paint: ICY_PAINT, relief: "1.0", last: "0.5 + F.r * 20.0", air: null,
    features: {shadows: 20, relief: true, regolith: 0.5},
    defaults: {cracks: 1, dark: 0.3, craters: 0.4, relief: 1, palette: "europa"},
    // ice, the cracks' fill, stained plains, fresh ice
    palettes: {
      europa: [0xdcd6ca, 0x6b3e2a, 0xa98a68, 0xf4f4f0],
      ganymede: [0xb1ada4, 0x5a5048, 0x62584e, 0xeceae4],
      glacier: [0xd0e2ec, 0x3d6f8f, 0x8fb0c4, 0xffffff],
      snow: [0xf0f2f4, 0x86aac0, 0xd6dde2, 0xffffff],
    },
    setup(o, r, b) {
      b.numbers[0] = 1.3 + 0.4 * r(); b.numbers[2] = levelFor(o.dark, 0.19); b.numbers[4] = o.craters; b.numbers[5] = 0.0035 + 0.003 * Math.min(1.5, o.cracks); b.numbers[6] = Math.min(1.5, o.cracks);
      b.numbers[7] = o.craters > 0.5 ? 1 : 0;
      P(o.palette).forEach((c, i) => { b.colors[i] = c; });
      for (let i = 0; i < 26; i++) { const s = anywhere(r, 0, 1); b.spots[i] = [s[0], s[1], s[2], o.cracks > 0 ? (r() - 0.5) * 1.2 : 9]; }
      for (let i = 26; i < 32; i++) b.spots[i] = anywhere(r, 0.015, 0.07 * Math.min(1.5, 0.3 + o.craters), 2);
      b.bump = 1.0 * o.relief;
    },
  },
  desert: {
    coarse: DESERT_COARSE, fields: DESERT_FIELDS, paint: DESERT_PAINT, relief: "1.0", last: "0.5 + F.r * 12.0", air: "mars",
    features: {shadows: 12, relief: true, regolith: 0.35},
    defaults: {dark: 0.35, caps: 1, craters: 0.6, canyons: 1, volcanoes: 1, relief: 1, palette: "mars"},
    // dust, dark ground, a second dust, the caps
    palettes: {
      mars: [0xc67c4c, 0x5b3a2c, 0xdb9c64, 0xf2ece4],
      ochre: [0xcba25c, 0x4a5a58, 0xb37a42, 0xf0f0ea],
      slate: [0x9a9aa2, 0x3c3e4a, 0xb4aca0, 0xf4f6f8],
    },
    setup(o, r, b) {
      b.numbers[0] = 1.3 + 0.4 * r(); b.numbers[2] = levelFor(o.dark, 0.25) + 0.3; b.numbers[3] = o.caps > 0 ? 1 - 0.07 * o.caps : 9; b.numbers[4] = o.craters;
      b.numbers[8] = r() < 0.5 ? 1 : -1; b.numbers[9] = o.volcanoes; b.numbers[10] = o.canyons;
      P(o.palette).forEach((c, i) => { b.colors[i] = c; });
      for (let i = 0; i < 8; i++) b.spots[i] = anywhere(r, 0.03, 0.14 * Math.min(1.5, 0.4 + o.craters), 2.5);
      for (let i = 8; i < 12; i++) { const g = onGlobe((r() - 0.5) * 60, 200 + (r() - 0.5) * 70); b.spots[i] = [...g, o.volcanoes > 0 ? 0.08 + 0.10 * r() : 1e-4]; }
      for (let i = 12; i < 20; i += 2) {                    // each canyon: a tilted circle's pole and offset; the arc's middle and half length
        const mid = onGlobe((r() - 0.5) * 40, 60 + 90 * (i - 12) / 2 + 40 * r()), any = anywhere(r, 0, 1);
        const pole = new THREE.Vector3(...mid).cross(new THREE.Vector3(any[0], any[1] * 3 + 1.5, any[2])).normalize();
        b.spots[i] = [pole.x, pole.y, pole.z, 0]; b.spots[i + 1] = [...mid, o.canyons > 0 ? (i === 12 ? 0.55 : 0.12 + 0.2 * r()) : 1e-4];
      }
      b.bump = 1.0 * o.relief;
    },
  },
  lava: {
    coarse: LAVA_COARSE, fields: LAVA_FIELDS, paint: LAVA_PAINT, relief: "1.0", last: "0.5 + F.r * 14.0", air: null,
    features: {shadows: 14, relief: true, glow: "heat", regolith: 0.3},
    defaults: {heat: 0.5, style: "crust", vents: 1, glow: 1, relief: 1, palette: null},
    palettes: {
      ember: [0x1c1512, 0x362e29, 0x3d1a10, 0, 0, 0],                    // basalt, ash, scorched crust
      io: [0xdcc86c, 0xcb8c3c, 0xeae4c2, 0xab452b, 0x8c6c3c, 0x1a1512],  // sulphur, orange, white frost, red fallout, polar frost, vents
    },
    setup(o, r, b) {
      const sulphur = o.style === "sulphur";
      b.numbers[0] = 1.3 + 0.4 * r(); b.numbers[2] = (o.heat - 0.5) * 0.9; b.numbers[3] = 1; b.numbers[7] = sulphur ? 1 : 0;
      P(o.palette).forEach((c, i) => { b.colors[i] = c; });
      const n = Math.round(Math.min(16, (sulphur ? 14 : 5) * o.vents));
      for (let i = 0; i < 16; i++) b.spots[i] = i < n ? anywhere(r, 0.02, sulphur ? 0.10 : 0.06, 2) : [0, 1, 0, 1e-4];
      b.bump = (sulphur ? 0.6 : 1.0) * o.relief;
    },
  },
  gas: {
    coarse: GAS_COARSE, fields: GAS_FIELDS, paint: GAS_PAINT, relief: "0.0", last: "0.0", air: "giant",
    features: {flow: true},
    defaults: {bands: 17, contrast: 1, turbulence: 1, storms: 6, spot: 1, drift: 0, polar: 0.6, palette: "jupiter"},
    palettes: {
      jupiter: {zones: [0xe6dccb, 0xd8cab0, 0xece5d8, 0xcfc2ad], belts: [0x8f735f, 0x7d6a5c, 0xa58e78, 0x6f6660, 0x9a7c64], pole: 0x7c766a, spot: 0xb5553a, oval: 0xf4eede},
      saturn: {zones: [0xe5d1a0, 0xdcc690, 0xecdbb0], belts: [0xc4a46c, 0xb69664, 0xcfb078], pole: 0x9e9878, spot: 0xeadfc2, oval: 0xf2e8cc},
      venus: {zones: [0xeae1c2, 0xe4d8b2], belts: [0xd6c596, 0xdccfa6], pole: 0xe2d8b6, spot: 0xeae1c2, oval: 0xf0e8d0},
      titan: {zones: [0xdba44c, 0xd69c46], belts: [0xc88c3a, 0xcf943f], pole: 0xb47e36, spot: 0xdba44c, oval: 0xe0b060},
      tempest: {zones: [0xd9b6e2, 0xe8cbea, 0xc59cda], belts: [0x6b3b8d, 0x8b4b9d, 0x4b2b6d], pole: 0x3b2b5d, spot: 0xf2d262, oval: 0xf8eaff},
      copper: {zones: [0xe8c9a0, 0xf0dcc0], belts: [0x2f6f6a, 0x3f8078, 0x9a5a38], pole: 0x2a4a4c, spot: 0xf4f0e0, oval: 0xf6f2e6},
    },
  },
  "ice-giant": {
    air: "ice",
    defaults: {bands: 7, contrast: 0.3, turbulence: 0.5, storms: 2, spot: 0, drift: 0, polar: 0.35, palette: "neptune"},
    palettes: {
      uranus: {zones: [0xa8dfe4, 0xb5e5e9], belts: [0x98d4dc, 0xa0d9df], pole: 0xc6edef, spot: 0x7fc4d0, oval: 0xe8fafa},
      neptune: {zones: [0x3f70da, 0x4b7be2], belts: [0x2c55bc, 0x3661c6], pole: 0x2a4ba2, spot: 0x14265a, oval: 0xeaf2ff},
      azure: {zones: [0x70b8ea, 0x8dcaf2], belts: [0x2b6cba, 0x3b7cca], pole: 0x1f4c92, spot: 0x13326c, oval: 0xffffff},
      jade: {zones: [0x8fd8b4, 0xa8e4c4], belts: [0x4fa888, 0x5fb894], pole: 0x3a7a6a, spot: 0x1f4c44, oval: 0xf0fff8},
    },
  },
};
KINDS.gas.setup = function (o, r, b) {
  const pal = o.palette;
  b.numbers[0] = 2.2 + 0.6 * r(); b.numbers[1] = 3.4; b.numbers[2] = o.turbulence; b.numbers[3] = 0.16 * Math.sqrt(o.contrast) * Math.min(1.5, o.turbulence + 0.3); b.numbers[4] = o.polar;
  b.numbers[6] = 1.6 * Math.min(1.5, o.turbulence); b.numbers[7] = o.spot > 0 ? 1 : 0;
  b.colors[0] = hex(pal.spot); b.colors[1] = hex(pal.oval); b.colors[2] = hex(pal.pole);
  const south = r() < 0.6 ? -1 : 1;
  b.spots[0] = o.spot > 0 ? [...onGlobe(south * (16 + 10 * r()), 20 + 40 * r()), -south * (0.10 + 0.07 * r()) * o.spot] : [0, 1, 0, 1e-4];
  const n = Math.round(Math.min(11, o.storms));
  for (let i = 1; i < 12; i++) {
    const lat = (22 + 40 * r()) * (r() < 0.5 ? -1 : 1);
    b.spots[i] = i <= n ? [...onGlobe(lat, r() * 360), -Math.sign(lat) * (0.018 + 0.03 * r() * r())] : [0, 1, 0, 1e-4];
  }
  b.ramp = bandRamp(o.seed, {bands: o.bands, contrast: o.contrast, zones: P(pal.zones), belts: P(pal.belts)});
  b.bump = 0;
};
for (const k of ["coarse", "fields", "paint", "relief", "last", "features", "setup"]) KINDS["ice-giant"][k] = KINDS.gas[k];
/** The surface types. */
export const TYPES = Object.freeze(Object.keys(KINDS));
/** Each type's palettes by name. */
export const PALETTES = Object.freeze(Object.fromEntries(TYPES.map((t) => [t, Object.freeze(Object.keys(KINDS[t].palettes))])));
KINDS.lava.defaults.palette = "ember";

/** The air of a body by name: zenith optical depths (red, green, blue) of its gas (`rayleigh`) and haze
 * (`haze`), what it absorbs besides (`absorb`), the scale height as a share of the radius (`height`), how
 * strongly the haze throws light onward (`forward`), the twilight's and the night glow's strength. */
export const AIRS = Object.freeze({
  earth: {rayleigh: [0.062, 0.130, 0.290], haze: [0.022, 0.022, 0.022], absorb: [0.004, 0.012, 0.001], height: 0.0014, forward: 0.72, twilight: 1, glow: [0.0006, 0.0016, 0.0007]},
  mars: {rayleigh: [0.002, 0.004, 0.010], haze: [0.085, 0.070, 0.050], absorb: [0.000, 0.012, 0.045], height: 0.0032, forward: 0.76, twilight: 0.6, glow: [0, 0, 0]},
  venus: {rayleigh: [0.06, 0.11, 0.22], haze: [0.22, 0.21, 0.18], absorb: [0.00, 0.01, 0.05], height: 0.0030, forward: 0.6, twilight: 1.5, glow: [0, 0, 0]},
  titan: {rayleigh: [0.02, 0.04, 0.10], haze: [0.42, 0.30, 0.14], absorb: [0.00, 0.06, 0.26], height: 0.016, forward: 0.62, twilight: 1.5, glow: [0, 0, 0]},
  giant: {rayleigh: [0.010, 0.018, 0.036], haze: [0.03, 0.03, 0.03], absorb: [0.01, 0.01, 0.01], height: 0.0016, forward: 0.6, twilight: 1, glow: [0, 0, 0]},
  ice: {rayleigh: [0.030, 0.075, 0.160], haze: [0.03, 0.035, 0.04], absorb: [0.20, 0.03, 0.00], height: 0.0020, forward: 0.6, twilight: 1, glow: [0, 0, 0]},
  thin: {rayleigh: [0.010, 0.020, 0.045], haze: [0.012, 0.012, 0.012], absorb: [0, 0, 0], height: 0.0022, forward: 0.7, twilight: 0.6, glow: [0, 0, 0]},
  smoke: {rayleigh: [0.004, 0.006, 0.010], haze: [0.09, 0.07, 0.06], absorb: [0.01, 0.03, 0.05], height: 0.0035, forward: 0.7, twilight: 0.5, glow: [0.004, 0.0012, 0.0003]},
});
const AIR_KEYS = ["like", "rayleigh", "haze", "absorb", "height", "forward", "twilight", "glow", "density"];
const RING_KEYS = ["seed", "style", "inner", "outer", "color", "opacity", "gaps", "dust"];
const RING_DEFAULTS = {style: "broad", inner: 1.25, outer: 2.3, color: 0xe6dcc6, opacity: 1, gaps: 7, dust: 0.25};

/** Ready-made worlds: lookalikes of the Solar System's bodies in character and colour (no real maps),
 * then a few invented ones. `tilt` (degrees) and `oblateness` are the body's own; every option may be overridden. */
export const PRESETS = Object.freeze({
  mercury: {type: "rocky", seed: 11, palette: "mercury", maria: 0.18, rays: 1.3, craters: 1.2, tilt: 0.03},
  venus: {type: "gas", seed: 12, palette: "venus", bands: 5, contrast: 0.5, turbulence: 0.9, storms: 0, spot: 0, polar: 0.15, air: "venus", tilt: 177.4},
  earth: {type: "ocean", seed: 13, tilt: 23.44},
  moon: {type: "rocky", seed: 14, palette: "moon", maria: 0.3, tilt: 6.7},
  mars: {type: "desert", seed: 15, palette: "mars", tilt: 25.2},
  jupiter: {type: "gas", seed: 16, palette: "jupiter", oblateness: 0.065, tilt: 3.1},
  saturn: {type: "gas", seed: 17, palette: "saturn", bands: 15, contrast: 0.55, turbulence: 0.45, storms: 3, spot: 0, polar: 0.5, oblateness: 0.098, tilt: 26.7, rings: {seed: 17, inner: 1.24, outer: 2.27}},
  uranus: {type: "ice-giant", seed: 18, palette: "uranus", bands: 5, contrast: 0.2, turbulence: 0.3, storms: 0, oblateness: 0.023, tilt: 97.8, rings: {seed: 18, style: "narrow", inner: 1.6, outer: 2.02, color: 0x6a6660, gaps: 9}},
  neptune: {type: "ice-giant", seed: 19, palette: "neptune", spot: 1, storms: 4, oblateness: 0.017, tilt: 28.3},
  io: {type: "lava", seed: 20, style: "sulphur", palette: "io", heat: 0.5, tilt: 0},
  europa: {type: "icy", seed: 21, palette: "europa", cracks: 1.2, dark: 0.3, craters: 0.15, tilt: 0.1},
  ganymede: {type: "icy", seed: 22, palette: "ganymede", cracks: 0.7, dark: 0.5, craters: 1, tilt: 0.2},
  callisto: {type: "rocky", seed: 23, palette: "callisto", maria: 0.04, rays: 0.8, craters: 1.3, tilt: 0},
  titan: {type: "gas", seed: 24, palette: "titan", bands: 5, contrast: 0.4, turbulence: 0.5, storms: 0, spot: 0, polar: 0.4, air: "titan", tilt: 0.3},
  // invented worlds
  ember: {type: "lava", seed: 31, heat: 0.6, air: "smoke", tilt: 12},
  boreas: {type: "icy", seed: 32, palette: "glacier", cracks: 1.3, dark: 0.4, craters: 0.3, air: "thin", tilt: 31, rings: {seed: 32, style: "narrow", inner: 1.5, outer: 2.1, color: 0xb8c8d4, gaps: 6}},
  ochre: {type: "desert", seed: 33, palette: "ochre", dark: 0.45, caps: 0.6, canyons: 1.4, air: {like: "mars", density: 1.6}, tilt: 18},
  tempest: {type: "gas", seed: 34, palette: "tempest", bands: 11, turbulence: 1.3, storms: 9, oblateness: 0.05, tilt: 21, rings: {seed: 34, inner: 1.35, outer: 2.5, color: 0xd8c8e8, gaps: 10}},
  verdant: {type: "ocean", seed: 35, palette: "verdant", land: 0.45, clouds: 0.6, wet: 0.3, tilt: 14},
  cinder: {type: "rocky", seed: 36, palette: "cinder", maria: 0.4, rays: 0.6, patches: 0.6, tilt: 4},
  azure: {type: "ice-giant", seed: 37, palette: "azure", bands: 9, contrast: 0.5, turbulence: 0.8, spot: 1, storms: 6, oblateness: 0.03, tilt: 24, rings: {seed: 37, inner: 1.5, outer: 2.2, color: 0xe8eef4, opacity: 0.7, gaps: 9}},
});

export const QUALITIES = Object.freeze(["fast", "standard", "fine"]);
/** How many steps the air's light is summed in along a view ray, by `quality`. */
export const AIR_STEPS = Object.freeze({fast: 2, standard: 4, fine: 8});
const COMMON = {type: "rocky", seed: 1, size: null, quality: "standard", light: 1, palette: null, tilt: 0, spin: null, oblateness: 0, air: undefined, rings: null, name: null};
const CONTROL = ["space", "orbits", "body", "sun"];

/** The cube maps' size for a frame `height` pixels tall: a full disc is sharp at 512 in a 720p frame. */
export const sizeFor = (height) => (height >= 900 ? 1024 : height >= 300 ? 512 : 256);

/** The options in full: the preset's (`what` a name of PRESETS, or an options object with its own `type`),
 * then `extra`; every key checked, palettes, air and rings resolved. Pure. */
export function resolveOptions(what = {}, extra = {}) {
  let base = what;
  if (typeof what === "string") {
    const key = what.trim().toLowerCase();
    if (!(key in PRESETS)) throw fail(`no ready-made world "${what}"${hint(key, Object.keys(PRESETS))}; there are: ${Object.keys(PRESETS).join(", ")}`);
    base = {...PRESETS[key], name: key};
  } else if (what === null || typeof what !== "object" || Array.isArray(what)) throw fail(`the world must be a name of PRESETS or an options object, got ${JSON.stringify(what)}`);
  const given = {...base, ...extra};
  const both = (a, b) => a && b && typeof a === "object" && typeof b === "object" && !Array.isArray(a) && !Array.isArray(b);
  if (both(base.rings, extra.rings)) given.rings = {...base.rings, ...extra.rings};      // a change to a ready-made world's rings keeps the rest of them
  for (const k of CONTROL) delete given[k];
  const type = choice("type", given.type ?? COMMON.type, TYPES), kind = KINDS[type];
  known(`a ${type} world's options`, given, [...Object.keys(COMMON), ...Object.keys(kind.defaults)]);
  const o = {...COMMON, ...kind.defaults, ...given, type};
  number("seed", o.seed, 0, 1e9);
  if (o.size !== null && ![64, 128, 256, 512, 1024, 2048].includes(o.size)) throw fail(`size must be 64, 128, 256, 512, 1024 or 2048 (the cube maps' faces), got ${JSON.stringify(o.size)}`);
  choice("quality", o.quality, QUALITIES);
  number("light", o.light, 0, 100); number("tilt", o.tilt, -360, 360); number("oblateness", o.oblateness, 0, 0.5);
  for (const k of Object.keys(kind.defaults)) if (typeof kind.defaults[k] === "number") number(k, o[k], 0, k === "bands" ? 41 : k === "storms" ? 11 : 4);
  if (type === "lava") choice("style", o.style, ["crust", "sulphur"]);
  if (o.spin !== null && o.spin !== "true" && o.spin !== "locked" && !(typeof o.spin === "number" && Number.isFinite(o.spin)))
    throw fail(`spin must be "true" (the body's own turning, from ctx.orbits), "locked" (no turning), or seconds of film for one turn (a number; negative turns backwards), got ${JSON.stringify(o.spin)}`);
  if (typeof o.palette === "string") {
    if (!(o.palette in kind.palettes)) throw fail(`a ${type} world has no palette "${o.palette}"${hint(o.palette, Object.keys(kind.palettes))}; it has: ${Object.keys(kind.palettes).join(", ")}`);
    o.palette = kind.palettes[o.palette];
  } else {
    const model = kind.palettes[kind.defaults.palette];
    if (o.palette === null || typeof o.palette !== "object" || Array.isArray(o.palette) !== Array.isArray(model) || (Array.isArray(model) ? o.palette.length !== model.length : Object.keys(model).some((k) => !(k in o.palette))))
      throw fail(`palette must be a name (${Object.keys(kind.palettes).join(", ")}) or colours shaped like one of them: ${JSON.stringify(model)}`);
  }
  // the air: false for none, a name, or {like: name, ...changes, density: a factor on its depths}
  let air = o.air === undefined ? kind.air : o.air;
  if (air === false || air === null) air = null;
  else {
    if (typeof air === "string") air = {like: air};
    known("air", air, AIR_KEYS);
    const like = air.like ?? kind.air ?? "thin";
    if (!(like in AIRS)) throw fail(`no air "${like}"${hint(like, Object.keys(AIRS))}; there are: ${Object.keys(AIRS).join(", ")}`);
    const a = {...AIRS[like], ...air}, k = number("air.density", a.density ?? 1, 0, 50);
    for (const c of ["rayleigh", "haze", "absorb", "glow"]) a[c] = linearColor(`air.${c}`, a[c]);
    number("air.height", a.height, 1e-5, 0.2); number("air.forward", a.forward, 0, 0.95); number("air.twilight", a.twilight, 0, 5);
    air = {rayleigh: a.rayleigh.map((x) => x * k), haze: a.haze.map((x) => x * k), absorb: a.absorb.map((x) => x * k), height: a.height, forward: a.forward, twilight: a.twilight, glow: a.glow};
    if (air.rayleigh.concat(air.haze).every((x) => x === 0)) air = null;
  }
  o.air = air;
  if (o.rings === false || o.rings === null) o.rings = null;
  else {
    const rings = o.rings === true ? {} : o.rings;
    known("rings", rings, RING_KEYS);
    const g = {...RING_DEFAULTS, seed: o.seed, ...rings};
    choice("rings.style", g.style, RING_STYLES);
    number("rings.inner", g.inner, 1.01, 50); number("rings.outer", g.outer, g.inner + 0.01, 100); number("rings.opacity", g.opacity, 0, 10); number("rings.gaps", g.gaps, 0, 40); number("rings.dust", g.dust, 0, 1);
    g.color = linearColor("rings.color", g.color);
    o.rings = g;
  }
  return o;
}

/** What the seed and the options give the bake: numbers, colours, placed things, the relief's scale, a giant's bands. Pure. */
export function bakeInputs(o) {
  const b = {offset: null, numbers: new Array(24).fill(0), colors: Array.from({length: 12}, () => [0, 0, 0]), spots: Array.from({length: 32}, () => [0, 1, 0, 1e-4]), bump: 0, ramp: null};
  const r = rng(o.seed * 7919 + 13);
  b.offset = [r() * 60 + 3, r() * 60 + 3, r() * 60 + 3];
  KINDS[o.type].setup(o, r, b);
  return b;
}

// ---------- the bake ----------
// the six faces as OpenGL addresses them: direction = forward + s right + t up
const FACES = [
  [[1, 0, 0], [0, 0, -1], [0, -1, 0]], [[-1, 0, 0], [0, 0, 1], [0, -1, 0]], [[0, 1, 0], [1, 0, 0], [0, 0, 1]],
  [[0, -1, 0], [1, 0, 0], [0, 0, -1]], [[0, 0, 1], [1, 0, 0], [0, -1, 0]], [[0, 0, -1], [-1, 0, 0], [0, -1, 0]],
];
const COARSE_MAIN = "uniform int uWhich; void main() { gl_FragColor = coarse(faceDirection(), uWhich); }";
const FIELDS_MAIN = "void main() { gl_FragColor = fields(faceDirection()); }";
// the last pass: the slope of the height from its neighbours, the colour, and the two maps' packing:
// A = sqrt(albedo), 0.5 + gloss / 2 - glow / 2;  B = the relief's push on the normal, clouds or height
const PAINT_MAIN = /* glsl */`
uniform samplerCube uFields; uniform float uBump;
void main() {
  vec3 n = faceDirection();
  vec4 F = textureCube(uFields, n);
  vec3 t1 = normalize(cross(abs(n.y) < 0.9 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0), n)), t2 = cross(n, t1);
  float e = 1.6 / uSize;
  float h1 = textureCube(uFields, normalize(n + e * t1)).r - textureCube(uFields, normalize(n - e * t1)).r;
  float h2 = textureCube(uFields, normalize(n + e * t2)).r - textureCube(uFields, normalize(n - e * t2)).r;
  vec3 push = -(h1 * t1 + h2 * t2) / (2.0 * e) * uBump;       // the tangent of the slope, in the body's axes
#ifdef MAP_A
  vec3 albedo; float gloss, glow;
  paint(n, F, length(push), albedo, gloss, glow);
  gl_FragColor = vec4(sqrt(clamp(albedo, 0.0, 1.0)), clamp(0.5 + 0.5 * gloss - 0.5 * glow, 0.0, 1.0));
#else
  gl_FragColor = vec4(clamp((128.0 + push * RELIEF * 127.0 * 0.5) / 255.0, 0.0, 1.0), clamp(LAST, 0.0, 1.0));
#endif
}`;
const COARSE_SIZE = 128;
const bytes = (rows, depth) => { const d = new Uint8Array(rows.length * 4); rows.forEach((c, i) => { for (let j = 0; j < 3; j++) d[4 * i + j] = Math.round(255 * Math.sqrt(clamp01(c[j]))); d[4 * i + 3] = Math.round(255 * clamp01(c[3] / depth)); }); return d; };
function lineTexture(rows, depth, mipmaps) {
  const t = new THREE.DataTexture(bytes(rows, depth), rows.length, 1, THREE.RGBAFormat, THREE.UnsignedByteType);
  t.magFilter = THREE.LinearFilter; t.minFilter = mipmaps ? THREE.LinearMipmapLinearFilter : THREE.LinearFilter; t.generateMipmaps = mipmaps;
  t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping; t.needsUpdate = true;
  return t;
}

// the two maps of a body: {A, B} cube render targets with mipmaps
function bakeBody(renderer, o, inputs) {
  const kind = KINDS[o.type], size = o.size;
  const float = renderer.extensions.has("EXT_color_buffer_float") && renderer.extensions.has("OES_texture_float_linear");
  const data = (n) => new THREE.WebGLCubeRenderTarget(n, {type: float ? THREE.FloatType : THREE.HalfFloatType, magFilter: THREE.LinearFilter, minFilter: THREE.LinearFilter, generateMipmaps: false, depthBuffer: false});
  const map = () => new THREE.WebGLCubeRenderTarget(size, {type: THREE.UnsignedByteType, magFilter: THREE.LinearFilter, minFilter: THREE.LinearMipmapLinearFilter, generateMipmaps: false, depthBuffer: false});
  const K = [0, 1, 2].map(() => data(Math.min(COARSE_SIZE, size))), fields = data(size), A = map(), B = kind.features.relief || kind.features.clouds ? map() : null;
  const ramp = inputs.ramp ? lineTexture(inputs.ramp, 1, false) : null;
  const face = {uRight: {value: new THREE.Vector3()}, uUp: {value: new THREE.Vector3()}, uFwd: {value: new THREE.Vector3()}, uSize: {value: size},
    uOff: {value: new THREE.Vector3(...inputs.offset)}, uP: {value: inputs.numbers}, uC: {value: inputs.colors.map((c) => new THREE.Vector3(...c))}, uS: {value: inputs.spots.map((s) => new THREE.Vector4(...s))},
    uK0: {value: null}, uK1: {value: null}, uK2: {value: null}, uRamp: {value: ramp}};
  const oct = Math.max(4, Math.min(9, Math.round(Math.log2(size)) - 3));
  const defines = {OCT: oct, OCTM: oct - 1};
  const pass = (fragmentShader, uniforms = {}, more = {}) => new THREE.ShaderMaterial({uniforms: {...face, ...uniforms}, defines: {...defines, ...more}, vertexShader: BAKE_VERT, fragmentShader, depthTest: false, depthWrite: false});
  const coarse = pass(`${NOISE}${kind.coarse}\n${COARSE_MAIN}`, {uWhich: {value: 0}});
  const first = pass(`${NOISE}${kind.fields}\n${FIELDS_MAIN}`);
  const paintA = pass(`${NOISE}${kind.paint}\n${PAINT_MAIN}`, {uFields: {value: fields.texture}, uBump: {value: inputs.bump}}, {MAP_A: 1});
  const paintB = pass(`${NOISE}${PAINT_MAIN}`, {uFields: {value: fields.texture}, uBump: {value: inputs.bump}}, {RELIEF: `(${kind.relief})`, LAST: `(${kind.last})`});
  const geometry = new THREE.PlaneGeometry(2, 2), quad = new THREE.Mesh(geometry, first), scene = new THREE.Scene(), camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  quad.frustumCulled = false; scene.add(quad);
  const target = renderer.getRenderTarget(), active = renderer.getActiveCubeFace(), level = renderer.getActiveMipmapLevel(), xr = renderer.xr.enabled, autoClear = renderer.autoClear;
  renderer.xr.enabled = false; renderer.autoClear = true;
  const faces = (rt, material) => {
    quad.material = material; face.uSize.value = rt.width;
    for (let i = 0; i < 6; i++) {
      const [fwd, right, up] = FACES[i];
      face.uFwd.value.set(...fwd); face.uRight.value.set(...right); face.uUp.value.set(...up);
      renderer.setRenderTarget(rt, i); renderer.render(scene, camera);
    }
  };
  K.forEach((rt, i) => { coarse.uniforms.uWhich.value = i; coarse.uniformsNeedUpdate = true; faces(rt, coarse); });
  face.uK0.value = K[0].texture; face.uK1.value = K[1].texture; face.uK2.value = K[2].texture;
  faces(fields, first);
  for (const [rt, material] of [[A, paintA], [B, paintB]]) {
    if (!rt) continue;
    faces(rt, material);
    rt.texture.generateMipmaps = true;                 // the mipmaps once, after the last face (an empty draw that must not clear it)
    renderer.autoClear = false; renderer.setRenderTarget(rt, 5); renderer.render(new THREE.Scene(), camera); renderer.autoClear = true;
  }
  renderer.setRenderTarget(target, active, level);
  renderer.xr.enabled = xr; renderer.autoClear = autoClear;
  for (const x of [coarse, first, paintA, paintB, geometry, fields, ramp, ...K]) if (x) x.dispose();
  return {A, B};
}

// ---------- drawing ----------
const TONE = THREE.ShaderChunk.tonemapping_pars_fragment.replace("uniform float toneMappingExposure;", "const float toneMappingExposure = 1.0;");
// shared by the globe and the rings. To the canvas: the curve and encoding vidgen/three-finish would apply (ACES, sRGB), and a dither
const SHARED = /* glsl */`
precision highp float;
varying vec3 vObj;
uniform vec3 uCam, uSunO, uLight; uniform vec4 uViewZ; uniform vec2 uProj; uniform float uPix, uDisplay;
${TONE}
float dither(vec2 p) { vec3 q = fract(vec3(p.xyx) * 0.1031); q += dot(q, q.yzx + 33.33); return fract((q.x + q.y) * q.z); }
vec3 display(vec3 c) {
  c = clamp(ACESFilmicToneMapping(max(c, 0.0)), 0.0, 1.0);
  c = mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
  return c + (dither(gl_FragCoord.xy) + dither(gl_FragCoord.xy * 1.7 + 91.0) - 1.0) / 255.0;
}
// premultiplied colour out: linear light into a render target, the finished picture to the canvas
vec4 put(vec3 col, float alpha) { return vec4(uDisplay < 0.5 ? col : display(col), alpha); }
float depthOf(vec3 p) { float z = dot(uViewZ, vec4(p, 1.0)); return clamp(0.5 - 0.5 * (uProj.x * z + uProj.y) / z, 0.0, 1.0); }
`;
const SHELL_VERT = /* glsl */`
uniform vec3 uGrow; varying vec3 vObj;
void main() {
  vObj = position * uGrow;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(vObj, 1.0);
  gl_Position.z = min(gl_Position.z, gl_Position.w * 0.99999);   // the far side of the shell may pass the far plane: the depth is written per pixel
}`;
const BODY_FRAG = /* glsl */`
${SHARED}
uniform samplerCube uA, uB; uniform sampler2D uRing;
uniform vec3 uSunW, uFill, uFillW, uOb, uGlowColor, uCloudColor, uBetaR, uBetaM, uExt, uAirGlow;
uniform mat3 uNorm, uDirW;
uniform float uPoint, uSpot, uSigma, uBump, uGloss, uRegolith;
uniform vec2 uTerm;
uniform vec4 uCloud;          // amount, turn of the deck (radians), height (radii), shadow strength
uniform vec4 uShadow;         // two reaches towards the sun (radians), the map's units per radius, softness
uniform vec4 uFlow;           // the winds' greatest shear (radians), bands, the cycle's phase
uniform vec4 uAir;            // scale height (radii), top (scale heights), forward share g, twilight
uniform vec4 uRings;          // inner, outer radius; the profile's length; opacity
#ifdef ECLIPSE
uniform vec4 uEclipse[ECLIPSE];      // other bodies towards the sun: middle (this body's axes and radii), radius
uniform vec4 uEclipseAir[ECLIPSE];   // the light their air bends into their shadow; the tangent of the sun's angular radius
#endif
vec3 turnY(vec3 p, float a) { float c = cos(a), s = sin(a); return vec3(c * p.x + s * p.z, p.y, c * p.z - s * p.x); }
#ifdef AIR
// the air between a point (X its distance from the centre and h its height, in scale heights) and space
// along a direction whose cosine to the vertical is c, in zenith columns (Chapman's function, after
// Schueler's approximation); under the horizon: twice the tangent path less the path upward
float column(float X, float h, float c) {
  float k = sqrt(1.5708 * X), up = k / (k * abs(c) + 1.0) * exp(-h);
  float s = sqrt(max(1.0 - c * c, 0.0)), ht = X * s - 1.0 / uAir.x;
  float tang = 2.0 * sqrt(1.5708 * X * s) * exp(-max(ht, -6.0));
  return c >= 0.0 ? up : max(tang - up, up);
}
#endif
void main() {
  vec3 ro = uCam, rd = normalize(vObj - uCam);
  float tm = -dot(ro, rd), b2 = dot(ro, ro) - tm * tm, b = sqrt(max(b2, 0.0));
  float px = uPix * max(tm, 1e-9);                                    // a pixel at the limb, in radii
  float cover = clamp(0.5 + (1.0 - b) / px, 0.0, 1.0) * step(0.0, tm);
  float th = tm - sqrt(max(1.0 - b2, 0.0));
  vec3 p = normalize(ro + rd * th);
  vec3 nW = normalize(uNorm * p), vW = -normalize(uDirW * rd);
  float mu = dot(nW, uSunW);
  // ---- the surface ----
#ifdef FLOW
  // every latitude has its own wind: two copies of the map, each wound half a cycle one way and back, cross-faded
  float wind = uFlow.x * sin(p.y * uFlow.y), f1 = fract(uFlow.z), f2 = fract(uFlow.z + 0.5);
  vec4 A = mix(textureCube(uA, turnY(p, wind * (f2 - 0.5))), textureCube(uA, turnY(p, wind * (f1 - 0.5))), 1.0 - abs(2.0 * f1 - 1.0));
#else
  vec4 A = textureCube(uA, p);
#endif
  vec3 albedo = A.rgb * A.rgb, N = nW;
  float gloss = max(A.a * 2.0 - 1.0, 0.0), glow = max(1.0 - A.a * 2.0, 0.0), shade = 1.0;
#ifdef RELIEF
  vec4 B = textureCube(uB, p);
  N = normalize(uNorm * (p + (B.rgb - 128.0 / 255.0) * (2.0 * uBump)));
#endif
  float nl = max(dot(N, uSunW), 0.0), nv = max(dot(N, vW), 0.0);
  // dusty ground throws light back the way it came (a full moon is flat, not a ball): Lommel-Seeliger's law mixed into Lambert's
  float lit = mix(nl, 2.0 * nl / (nl + nv + 1e-3), uRegolith) * smoothstep(uTerm.x, uTerm.y, mu);
  vec3 toSun = normalize(uSunO - p * dot(uSunO, p) + 1e-6);           // along the ground towards the sun
#ifdef SHADOWS
  // the relief's own shadows: is the ground towards the sun higher than the sun's ray from here?
  float rise = max(mu, 0.0) / sqrt(max(1.0 - mu * mu, 1e-4)) * uShadow.z;
  float o1 = textureCube(uB, normalize(p + toSun * uShadow.x)).a - B.a - uShadow.x * rise;
  float o2 = textureCube(uB, normalize(p + toSun * uShadow.y)).a - B.a - uShadow.y * rise;
  shade = 1.0 - smoothstep(0.0, uShadow.w, max(o1, o2));
#endif
  vec3 sunAtGround = uLight, sky = vec3(0.0), ecl = vec3(1.0);
#ifdef ECLIPSE
  // other bodies' shadows (vidgen/space-light sets them): how much of the sun's disc each hides from here, a soft disc test
  for (int i = 0; i < ECLIPSE; i++) {
    vec3 c = uEclipse[i].xyz - p;
    float s = dot(c, uSunO), d = length(c - uSunO * s), r = uEclipse[i].w, w = max(s, 0.0) * uEclipseAir[i].w + 1e-5;
    float hid = min(1.0, r * r / (w * w)) * (1.0 - smoothstep(abs(r - w), r + w, d)) * step(0.0, s);
    ecl *= mix(vec3(1.0), uEclipseAir[i].rgb, hid);
  }
  sunAtGround *= ecl;
#endif
#ifdef RINGS
  // the rings' shadow: where the sun's ray from here crosses their plane
  vec3 pu = p * uOb, su = normalize(uSunO * uOb);
  float ts = -pu.y / (abs(su.y) > 1e-5 ? su.y : 1e-5);
  float ur = (length(pu.xz + su.xz * ts) - uRings.x) / (uRings.y - uRings.x);
  float tau = texture2D(uRing, vec2(clamp(ur, 0.0, 1.0), 0.5), 1.0).a * 4.0 * uRings.w * step(0.0, ts) * step(0.0, ur) * step(ur, 1.0);
  sunAtGround *= exp(-tau / max(abs(su.y), 0.02));
#endif
#ifdef AIR
  float X0 = 1.0 / uAir.x;
  vec3 airSun = exp(-uExt * column(X0, 0.0, mu));
  sky = ecl * uBetaR / uExt * (1.0 - exp(-uExt * 1.5)) * smoothstep(-0.25, 0.35, mu) * uAir.w * 0.35;   // the sky's own light on the ground
  sunAtGround *= airSun;
#endif
#ifdef CLOUDS
  float reach = uCloud.z * min(sqrt(max(1.0 - mu * mu, 0.0)) / max(mu, 0.12), 8.0);
  float cloud = textureCube(uB, turnY(p, uCloud.y)).a, cloudSun = textureCube(uB, turnY(normalize(p + toSun * reach), uCloud.y)).a;
  shade *= 1.0 - uCloud.w * smoothstep(0.05, 0.75, cloudSun) * (1.0 - 0.5 * cloud);
#endif
  vec3 S = albedo * (sunAtGround * lit * shade + uLight * sky + uFill * max(dot(N, uFillW), 0.0));
#ifdef GLINT
  // the sun's glitter on water: one wide lobe (the waves), a microfacet model's rough-surface term
  vec3 hv = normalize(uSunW + vW);
  float nh = max(dot(nW, hv), 0.0), nvs = max(dot(nW, vW), 0.0), a2 = uGloss * uGloss;
  float dn = nh * nh * (a2 - 1.0) + 1.0, fres = 0.02 + 0.98 * pow(1.0 - max(dot(hv, vW), 0.0), 5.0);
  S += sunAtGround * gloss * shade * fres * a2 / (dn * dn) * max(mu, 0.0) / (4.0 * max(nvs, 0.05) * max(mu, 0.05) + 0.02);
  S += uLight * sky * gloss * 0.45 * pow(1.0 - nvs, 4.0);            // the sky mirrored at grazing angles
#endif
#ifdef GLOW_HEAT
  S += uGlowColor * vec3(1.0, 0.22 + 0.62 * glow, 0.03 + 0.5 * glow * glow) * glow * glow;   // from dull red to yellow-white as it gets hotter
#endif
#ifdef GLOW_LIGHTS
  S += uGlowColor * glow * smoothstep(0.02, -0.12, mu);
#endif
#ifdef CLOUDS
  float thick = clamp(cloud * uCloud.x * 1.15, 0.0, 1.0);
  float relief = clamp(1.0 + 1.5 * (cloud - cloudSun), 0.5, 1.2);     // a deck is darker where higher cloud stands sunward of it
  float mc = max(mu, 0.0);
  vec3 cloudLight = sunAtGround * mc * (0.30 + 0.70 * sqrt(mc)) * relief;
#ifdef AIR
  cloudLight = mix(cloudLight, uLight * ecl * sqrt(airSun) * max(mu + 0.02, 0.0) * relief, 0.5) + uLight * sky * 1.3;   // the tops stand above half the air: less red than the ground
#endif
  S = mix(S, uCloudColor * (0.72 + 0.28 * cloud) * cloudLight + uFill * max(dot(nW, uFillW), 0.0), thick);
#endif
  // ---- the air ----
  vec3 scat = vec3(0.0), through = vec3(1.0);
#ifdef AIR
  float Ra = 1.0 + uAir.x * uAir.y, half_ = sqrt(max(Ra * Ra - b2, 0.0));
  float hit = step(b2, 1.0) * step(0.0, tm);
  float t0 = max(tm - half_, 0.0), t1 = mix(tm + half_, th, hit);
  float inAir = step(b2, Ra * Ra) * step(0.0, t1 - t0);
  float cosv = dot(rd, uSunO);
  vec3 phase = 0.25 * (uBetaR * 0.75 * (1.0 + cosv * cosv) + uBetaM * (1.0 - uAir.z * uAir.z) / pow(1.0 + uAir.z * uAir.z - 2.0 * uAir.z * cosv, 1.5)) / uExt;
  vec3 x = ro + rd * t0; float r = length(x);
  float c0 = column(r * X0, (r - 1.0) * X0, -dot(x, rd) / r);
  vec3 T = vec3(1.0);
  for (int i = 1; i <= STEPS; i++) {                // the light the air sends this way, summed slab by slab; each slab's share is exact
    float t = mix(t0, t1, float(i) / float(STEPS)), tmid = mix(t0, t1, (float(i) - 0.5) / float(STEPS));
    x = ro + rd * t; r = length(x);
    vec3 Tn = exp(-uExt * max(column(r * X0, (r - 1.0) * X0, -dot(x, rd) / r) - c0, 0.0));
    x = ro + rd * tmid; r = length(x);
    float cs = column(r * X0, max(r - 1.0, 0.0) * X0, dot(x, uSunO) / r);
    vec3 Ts = exp(-uExt * cs) + uAir.w * 0.2 * exp(-uExt * cs * 0.12) * smoothstep(-0.35, 0.1, dot(x, uSunO) / r);   // the sun through the air, and the air's own second-hand light
    scat += (T - Tn) * (phase * Ts * uLight * ecl + uAirGlow);
    T = Tn;
  }
  scat *= inAir; through = mix(vec3(1.0), T, inAir);
#endif
  vec3 col = S * through * cover + scat;
  float alpha = 1.0 - (1.0 - cover) * dot(through, vec3(0.3333));
  // smaller than a pixel or two: one steady spot holding the whole disc's light (a Lambert sphere at this phase)
  float ph = acos(clamp(dot(normalize(uCam), uSunO), -1.0, 1.0)), dpx = b / (uPix * length(ro));
  vec4 mean = textureCube(uA, normalize(uCam), 20.0);
  vec3 spot = mean.rgb * mean.rgb * uLight * 0.6667 * (sin(ph) + (3.14159 - ph) * cos(ph)) / 3.14159 * uSpot * exp(-0.5 * dpx * dpx / (uSigma * uSigma));
  col = mix(col, spot, uPoint); alpha = mix(alpha, 0.0, uPoint);
  if (alpha <= 0.0 && dot(col, vec3(1.0)) <= 0.0) discard;
  gl_FragDepth = depthOf(ro + rd * (cover > 0.0 ? th * 0.998 : tm));
  gl_FragColor = put(col, alpha);
}`;
const RING_VERT = /* glsl */`
uniform vec3 uGrow; varying vec3 vObj;
void main() {
  vObj = position * uGrow;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(vObj, 1.0);
  gl_Position.z = min(gl_Position.z, gl_Position.w * 0.99999);
}`;
// the rings: where the view ray crosses their plane (y = 0), the profile at that radius averaged over the
// pixel's footprint; lit as a thin layer of grains scattering once (Chandrasekhar's reflection and
// transmission), bright seen from the sunlit side, a ghost of the thin parts from the far side
const RING_FRAG = /* glsl */`
${SHARED}
uniform sampler2D uRing; uniform vec4 uRings; uniform vec3 uOb, uFill; uniform float uSide, uDust;
float hg(float g, float c) { return (1.0 - g * g) / pow(1.0 + g * g - 2.0 * g * c, 1.5); }
void main() {
  vec3 ro = uCam, rd = normalize(vObj - uCam);
  float t = -ro.y / (abs(rd.y) > 1e-7 ? rd.y : 1e-7);
  vec3 P = ro + rd * t;
  float u = (length(P.xz) - uRings.x) / (uRings.y - uRings.x), w = max(fwidth(u), 1e-5);
  if (t <= 0.0 || (dot(P, uCam) > 0.0 ? 1.0 : -1.0) != uSide) discard;
  float lo = max(u - 0.5 * w, 0.0), hi = min(u + 0.5 * w, 1.0);
  if (hi <= lo) discard;
  vec4 tex = textureLod(uRing, vec2(0.5 * (lo + hi), 0.5), log2(max((hi - lo) * uRings.z, 1.0)));
  float tau = tex.a * 4.0 * uRings.w, mu = max(abs(rd.y), 1e-3), mu0 = max(abs(uSunO.y), 1e-3);
  float same = step(0.0, ro.y * uSunO.y), gap = mu - mu0;
  gap = abs(gap) < 2e-3 ? 2e-3 : gap;
  float back = mu0 / (mu0 + mu) * (1.0 - exp(-tau * (1.0 / mu + 1.0 / mu0)));
  float thru = mu0 / gap * (exp(-tau / mu) - exp(-tau / mu0));
  float c = dot(rd, uSunO), dusty = uDust * exp(-tau * 1.5);
  float phase = mix(hg(-0.32, c), hg(0.78, c), dusty);
  // the globe's shadow: does the sun's ray from here pass through the globe?
  vec3 su = normalize(uSunO / uOb);
  float along = dot(P, su), miss = sqrt(max(dot(P, P) - along * along, 0.0));
  float soft = 0.004 + 0.012 * max(-along, 0.0) + uPix * t;
  float sun = along > 0.0 ? 1.0 : smoothstep(1.0 - soft, 1.0 + soft, miss);
  vec3 grain = tex.rgb * tex.rgb;
  vec3 col = grain * (uLight * 0.25 * phase * mix(thru * 1.8, back * 3.0, same) * sun + uFill * (1.0 - exp(-tau / mu)) * 0.3);
  float share = (hi - lo) / w, alpha = (1.0 - exp(-tau / mu)) * share;
  gl_FragDepth = depthOf(P);
  gl_FragColor = put(col * share, alpha);
}`;
const BLEND = {transparent: true, depthTest: true, blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor,
  blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor, toneMapped: false, fog: false, side: THREE.BackSide};
const yUp = (v) => [v[0], v[2], -v[1]];
/** A spot's width (pixels) for a disc of `rho` pixels' radius: never under 0.62, as the stars of vidgen/space-sky. */
export const spotSigma = (rho) => Math.max(0.62, 0.71 * rho);
/** How much of a spot a disc of `rho` pixels' radius is drawn as: 0 from 2.5 pixels up, 1 from 1.5 down. */
export const pointShare = (rho) => clamp01(2.5 - rho);
/** The share of a full disc's light a round, matt body shows at phase angle `phase` (radians; 0 = full). */
export const phaseLight = (phase) => (Math.sin(phase) + (Math.PI - phase) * Math.cos(phase)) / Math.PI;

/** A body: `object` (a THREE.Group of radius 1; with `space` already placed and sized) and update(t, {sun}). */
export class Body {
  /** `renderer`: the page's; `what`: a name of PRESETS or an options object; `extra`: options over those, and
   * `space` (a vidgen/space-scale SpaceView: the body is added to it at the body of ctx.orbits called `body`,
   * default the preset's name), `orbits` (ctx.orbits without a SpaceView: spin and sun only), `sun`. */
  constructor(renderer, what = {}, extra = {}) {
    if (!renderer || !renderer.isWebGLRenderer) throw fail("the first argument must be the page's THREE.WebGLRenderer");
    known("the third argument", extra, [...CONTROL, ...Object.keys(COMMON), ...new Set(TYPES.flatMap((t) => Object.keys(KINDS[t].defaults)))]);
    const o = this.options = resolveOptions(what, extra), kind = KINDS[o.type], f = kind.features, air = o.air;
    o.size = o.size ?? sizeFor(renderer.getDrawingBufferSize(new THREE.Vector2()).y);
    this.renderer = renderer;
    this.maps = bakeBody(renderer, o, bakeInputs(o));
    const v3 = (a) => new THREE.Vector3(...a), pal = o.palette;
    const shared = {uCam: {value: new THREE.Vector3()}, uSunO: {value: new THREE.Vector3(1, 0, 0)}, uLight: {value: new THREE.Vector3(o.light, o.light, o.light)}, uFill: {value: new THREE.Vector3()},
      uViewZ: {value: new THREE.Vector4()}, uProj: {value: new THREE.Vector2()}, uPix: {value: 0.001}, uDisplay: {value: 0}, uOb: {value: new THREE.Vector3(1, 1 - o.oblateness, 1)},
      uRing: {value: null}, uRings: {value: new THREE.Vector4(1.2, 2.3, 1024, 1)}};
    const u = this.uniforms = {
      ...shared, uA: {value: this.maps.A.texture}, uB: {value: this.maps.B ? this.maps.B.texture : null}, uSunW: {value: new THREE.Vector3(1, 0, 0)}, uFillW: {value: new THREE.Vector3(0, 1, 0)},
      uNorm: {value: new THREE.Matrix3()}, uDirW: {value: new THREE.Matrix3()}, uGrow: {value: new THREE.Vector3(1, 1, 1)},
      uPoint: {value: 0}, uSpot: {value: 1}, uSigma: {value: 1}, uBump: {value: 1}, uGloss: {value: 0.2}, uRegolith: {value: f.regolith ?? 0},
      uTerm: {value: air ? new THREE.Vector2(-0.02, 0.06) : new THREE.Vector2(-0.004, 0.012)},
      uGlowColor: {value: f.glow === "lights" ? v3(hex(pal.lights)).multiplyScalar(o.lights) : new THREE.Vector3(1, 1, 1).multiplyScalar(1.5 * (o.glow ?? 1))},
      uCloudColor: {value: f.clouds ? v3(hex(pal.clouds)) : new THREE.Vector3(1, 1, 1)}, uCloud: {value: new THREE.Vector4(1, 0, 0.005, 0.7)},
      uShadow: {value: new THREE.Vector4(2.5 / o.size, 7 / o.size, (f.shadows ?? 1) / Math.max(1e-3, o.relief ?? 1), 5 / 255)}, uFlow: {value: new THREE.Vector4(0, 9, 0, 0)},
      uBetaR: {value: new THREE.Vector3()}, uBetaM: {value: new THREE.Vector3()}, uExt: {value: new THREE.Vector3(1, 1, 1)}, uAirGlow: {value: new THREE.Vector3()}, uAir: {value: new THREE.Vector4(0.0014, 8, 0.7, 1)},
    };
    const defines = {STEPS: AIR_STEPS[o.quality]};
    if (air) defines.AIR = 1;
    if (f.clouds && o.clouds > 0) defines.CLOUDS = 1;
    if (f.relief) defines.RELIEF = 1;
    if (f.shadows) defines.SHADOWS = 1;
    if (f.glint) defines.GLINT = 1;
    if (f.glow === "heat" && o.glow > 0) defines.GLOW_HEAT = 1;
    if (f.glow === "lights" && o.lights > 0) defines.GLOW_LIGHTS = 1;
    if (f.flow && o.drift > 0) defines.FLOW = 1;
    if (o.rings) defines.RINGS = 1;
    this.material = new THREE.ShaderMaterial({...BLEND, uniforms: u, defines, vertexShader: SHELL_VERT, fragmentShader: BODY_FRAG, depthWrite: true});
    this.geometry = new THREE.SphereGeometry(1.008, 48, 24);
    this.geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1.008 * (air ? 1 + air.height * 8 : 1));
    // three.js draws see-through things at one place in the order they were made: the rings' far half, the globe, the near half
    const far = o.rings ? new THREE.Mesh() : null;
    this.mesh = new THREE.Mesh(this.geometry, this.material);
    const near = o.rings ? new THREE.Mesh() : null;
    this.ringMeshes = [far, near];
    this.mesh.scale.set(1, 1 - o.oblateness, 1);
    this.spinner = new THREE.Group();
    this.object = new THREE.Group(); this.object.name = `space body ${o.name ?? o.type}`; this.object.add(this.spinner);
    /** The direction to the sun and its light (a THREE.Vector3 in the scene's axes; linear colour times strength). */
    this.sun = new THREE.Vector3(1, 0.25, 0.6).normalize();
    /** A second, weak light from `fill.direction` of colour `fill.color` (planet-shine, ring-shine: a later step's to set). */
    this.fill = {direction: new THREE.Vector3(0, 1, 0), color: new THREE.Color(0, 0, 0)};
    this.rings = null;
    this.spinner.add(this.mesh);
    if (o.rings) this._makeRings(shared);
    this.mesh.onBeforeRender = (r, scene, camera) => this._before(r, camera, this.mesh, u, true);
    this.material.addEventListener("dispose", () => this._free());
    // ctx.orbits: the body's place, size, pole and turning
    this.space = extra.space ?? null;
    this.orbits = extra.orbits ?? (this.space ? this.space.orbits : null);
    this.body = null;
    if (this.orbits) {
      const want = String(extra.body ?? o.name ?? "").toLowerCase();
      this.body = this.orbits.names.find((n) => n.toLowerCase() === want) ?? this.orbits.names.find((n) => (this.orbits.bodies[n].key ?? "").toLowerCase() === want) ?? null;
      if (!this.body) throw fail(`the orbit data has no body "${extra.body ?? o.name ?? ""}"${hint(want, this.orbits.names)}; it has: ${this.orbits.names.join(", ")} (give {body: name})`);
      this.sunBody = this.orbits.names.find((n) => this.orbits.bodies[n].key === "sun") ?? null;
      if (this.space) this.space.add(this.object, {body: this.body, spin: false});
    } else if (extra.body !== undefined || this.space) throw fail("space / body need orbit data: a web scene with orbit_data: (ctx.orbits)");
    if (extra.sun) this.setSun(extra.sun);
    this.update(0);
  }

  _makeRings(shared) {
    const g = this.options.rings, rows = ringProfile(g.seed, g);
    const texture = lineTexture(rows, 4, true);
    shared.uRing.value = texture; shared.uRings.value.set(g.inner, g.outer, rows.length, 1);
    const geometry = new THREE.CylinderGeometry(1, 1, 2, 96, 1);
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), g.outer * 1.03);
    const make = (side) => {
      const uniforms = {...shared, uGrow: {value: new THREE.Vector3(g.outer * 1.012, 0.01, g.outer * 1.012)}, uSide: {value: side}, uDust: {value: g.dust}};
      const material = new THREE.ShaderMaterial({...BLEND, uniforms, vertexShader: RING_VERT, fragmentShader: RING_FRAG, depthWrite: false});
      const mesh = this.ringMeshes[side < 0 ? 0 : 1];
      mesh.geometry = geometry; mesh.material = material;
      mesh.onBeforeRender = (r, scene, camera) => this._before(r, camera, mesh, uniforms, false);
      return mesh;
    };
    this.rings = {texture, geometry, back: make(-1), front: make(1), profile: rows};
    this.spinner.add(this.rings.back, this.rings.front);
  }

  // what a draw needs from the camera and the frame it draws into
  _before(renderer, camera, mesh, u, globe) {
    const s = this._scratch ?? (this._scratch = {inv: new THREE.Matrix4(), mv: new THREE.Matrix4(), view: new THREE.Vector4(), cam: new THREE.Vector3(), m3: new THREE.Matrix3(), sun: new THREE.Vector3()});
    const o = this.options, air = o.air;
    renderer.getCurrentViewport(s.view);
    s.inv.copy(mesh.matrixWorld).invert();
    u.uCam.value.copy(s.cam.setFromMatrixPosition(camera.matrixWorld)).applyMatrix4(s.inv);
    s.sun.copy(this.sun).normalize();
    u.uSunO.value.copy(s.sun).applyMatrix3(s.m3.setFromMatrix4(s.inv)).normalize();
    s.mv.multiplyMatrices(camera.matrixWorldInverse, mesh.matrixWorld);
    const e = s.mv.elements, pe = camera.projectionMatrix.elements;
    u.uViewZ.value.set(e[2], e[6], e[10], e[14]); u.uProj.value.set(pe[10], pe[14]);
    const pix = 2 * Math.tan((camera.fov ?? 40) * RAD / 2) / s.view.w, dist = u.uCam.value.length();
    u.uPix.value = pix;
    u.uFill.value.set(this.fill.color.r, this.fill.color.g, this.fill.color.b);
    u.uDisplay.value = renderer.getRenderTarget() === null ? 1 : 0;
    if (!globe) {
      u.uGrow.value.y = Math.max(0.004, 3 * pix * dist);                // the slab the rings are found in: never thinner than a few pixels
    } else {
      u.uSunW.value.copy(s.sun); u.uFillW.value.copy(this.fill.direction).normalize();
      u.uNorm.value.getNormalMatrix(mesh.matrixWorld); u.uDirW.value.setFromMatrix4(mesh.matrixWorld);
      const rho = 1 / (pix * Math.max(dist, 1e-9));              // the disc's radius in pixels
      let top = 1;
      if (air) {
        // a shell thinner than a pixel would flicker along the limb: it is drawn at least 0.7 px deep, and thinner in density
        const H = Math.max(air.height, 0.7 * pix * dist), thin = Math.pow(air.height / H, 0.4);
        u.uAir.value.set(H, 8, air.forward, air.twilight);
        u.uBetaR.value.set(...air.rayleigh).multiplyScalar(thin); u.uBetaM.value.set(...air.haze).multiplyScalar(thin);
        u.uExt.value.set(...air.rayleigh.map((x, i) => (x + air.haze[i] + air.absorb[i]) * thin));
        u.uAirGlow.value.set(...air.glow);
        top = 1 + 8 * H;
      }
      const sigma = spotSigma(rho), point = pointShare(rho);
      u.uPoint.value = point; u.uSpot.value = rho * rho / (2 * sigma * sigma); u.uSigma.value = sigma;
      u.uGrow.value.setScalar(Math.max(top, point > 0 ? 4 * sigma / rho : 0));
    }
    mesh.material.uniformsNeedUpdate = true;
  }

  /** Where the sun is: a direction ([x, y, z] or a Vector3, in the scene's axes), and optionally its `color` and `intensity`. */
  setSun(direction, {color = null, intensity = null} = {}) {
    if (Array.isArray(direction)) this.sun.set(...direction); else this.sun.copy(direction);
    if (this.sun.lengthSq() === 0) throw fail("setSun: the direction is zero");
    this.sun.normalize();
    if (color !== null || intensity !== null) {
      const c = color === null ? [1, 1, 1] : linearColor("setSun color", color), k = intensity ?? this.options.light;
      this.uniforms.uLight.value.set(c[0] * k, c[1] * k, c[2] * k);
    }
    return this;
  }

  /** The body at scene time `t` (seconds): its turning, its clouds' and bands' drift; with orbit data its
   * pole and, when the data has the Sun, the sun's direction. `sun` sets the direction (as setSun). */
  update(t, {sun = null} = {}) {
    const o = this.options, u = this.uniforms, q = this.orbits && this.body ? this.orbits.quaternion(this.body, t) : null;
    let angle = 0;                                                      // the turn about the pole, radians
    if (typeof o.spin === "number" && o.spin !== 0) angle = TAU * t / o.spin;
    if (q) {
      // the data's turn (pole and prime meridian); "locked" and a stated rate keep the pole and replace the turning
      this.object.quaternion.set(q[0], q[2], -q[1], q[3]);
      const spin = o.spin ?? "true", w = this.orbits.spin(this.body, t), w0 = this.orbits.spin(this.body, 0);
      this.spinner.rotation.set(0, spin === "true" || w === null ? 0 : w0 - w + angle, 0);
    } else {
      this.object.rotation.set(0, 0, -o.tilt * RAD);
      this.spinner.rotation.set(0, angle, 0);
    }
    if (this.orbits && this.body && this.sunBody && !sun) {
      const a = this.orbits.position(this.sunBody, t), b = this.orbits.position(this.body, t);
      this.sun.set(...yUp([a[0] - b[0], a[1] - b[1], a[2] - b[2]])).normalize();
    }
    if (sun) this.setSun(sun);
    u.uCloud.value.set(1, -(o.cloudDrift ?? 0) * t * RAD, 0.005, 0.7);
    // the winds: the greatest shear of a cycle is a sixth of a radian; the cycle's length follows from the drift (degrees a second)
    const drift = o.drift ?? 0;
    u.uFlow.value.set(0.17, Math.max(3, (o.bands ?? 9) * 0.9), drift > 0 ? t * drift * RAD / 0.17 : 0, 0);
    return this;
  }

  /** The degrees the globe turns from one frame to the next at scene time `t` (with orbit data and `spin: "true"`). */
  turnPerFrame(t = 0) {
    const o = this.options;
    if (typeof o.spin === "number") return o.spin === 0 ? 0 : 360 / Math.abs(o.spin) / this._fps();
    if (!this.orbits || !this.body || o.spin === "locked") return 0;
    const dt = 1 / this._fps(), a = this.orbits.spin(this.body, t), b = this.orbits.spin(this.body, t + dt);
    if (a === null || b === null) return 0;
    const rotation = this.orbits.bodies[this.body].rotation, period = rotation && rotation.period ? Math.abs(rotation.period) : null;
    // the data's angle is folded into one turn: the true step comes from the period and the scene's speed-up
    const sim = this.orbits.time(t + dt) - this.orbits.time(t);
    return period ? 360 * sim / period : Math.abs(b - a) / RAD;
  }
  _fps() { return (this.orbits && this.orbits.fps) || 30; }

  /** What a viewer would see wrong, in words (an empty list when nothing): a globe that turns so far a frame that it flickers. */
  problems(t = 0) {
    const step = this.turnPerFrame(t), out = [];
    if (step > 12) out.push(`${this.body ?? this.options.name ?? "the body"} turns ${step.toFixed(0)} degrees a frame at this speed-up: it will flicker; give spin: "locked", or spin: seconds of film for one turn (an artistic rate: say so)`);
    return out;
  }

  _free() { this.maps.A.dispose(); if (this.maps.B) this.maps.B.dispose(); }
  /** Free the maps, the materials and the geometry. */
  dispose() {
    this.material.dispose(); this.geometry.dispose();
    if (this.rings) { this.rings.texture.dispose(); this.rings.geometry.dispose(); this.rings.back.material.dispose(); this.rings.front.material.dispose(); }
  }
}
/** A planet or a moon: `planet(renderer, "earth")`, `planet(renderer, {type: "gas", seed: 3})`, `planet(renderer, "Saturn", {space})`. */
export const planet = (renderer, what, extra) => new Body(renderer, what, extra);
