// vidgen/baked: pictures a page bakes once, kept between pages (DESIGN.md §123.2). Part of
// schu-video-generator (MIT licence); imported by a page as "vidgen/baked".
//
//   import {baked} from "vidgen/baked";
//   const [map] = baked(renderer, "my-module/surface", {version: 1, seed, size}, {
//     targets: () => [new THREE.WebGLCubeRenderTarget(size, {type: THREE.HalfFloatType, ...})],
//     draw: ([map]) => { /* render the six faces, make the mipmaps */ },
//   });
//
// `targets()` makes the render targets (2D or cube; RGBA; unsigned byte, half float or float; null
// for one not needed) the same way every time; `draw(targets)` fills them. With vidgen's cache on
// (a page of vidgen's in headless Chromium) the first page that asks bakes, reads the targets' level
// 0 back and hands the bytes to vidgen, which keeps them in its cache folder; a later page (another
// scene, still, render or parallel job) gets the bytes and uploads them instead of baking, and makes
// the mipmaps again when the bake had them. The pixels are the same bit for bit. Anywhere else (Node,
// another browser, the cache off, a stored entry missing or damaged) `draw` runs as without the cache.
// vidgen stores the bytes compressed (raw deflate, RFC 1951; a half float's or a float's bytes split into
// planes first): fewer bytes cross to the page, which inflates them and joins the planes.
//
// The key. vidgen keys an entry by `name`, `inputs`, the targets' sizes and types, the GL renderer
// and its extensions, vidgen's own modules and three.js (any change of one is a new key) and what
// draws the pages (Chromium, its flags). `inputs` must hold every other thing the pixels depend on:
// the options the bake reads, and a version of the bake's code when it is not one of vidgen's
// modules (a project's own script). Numbers, strings, booleans, arrays and plain objects only.
import * as THREE from "three";

/** Bumped when what this module stores changes. */
export const VERSION = 1;
const ORIGIN = "http://vidgen-web.invalid", ROUTE = "/__vidgen__/baked/";
const TYPES = {[THREE.UnsignedByteType]: "u8", [THREE.HalfFloatType]: "f16", [THREE.FloatType]: "f32"};
const BYTES = {u8: 4, f16: 8, f32: 16}, WIDTH = {u8: 1, f16: 2, f32: 4};
let service;   // undefined: not asked yet; false: no cache here; true: vidgen keeps baked maps

// ---------- the page's line to vidgen: small synchronous requests on vidgen's own origin ----------
function request(method, path, body = null, binary = false) {
  const x = new XMLHttpRequest();
  x.open(method, ROUTE + path, false);
  if (binary) x.overrideMimeType("text/plain; charset=x-user-defined");
  if (body !== null) x.setRequestHeader("Content-Type", "application/json");
  x.send(body === null ? null : JSON.stringify(body));
  return x;
}
function available() {
  if (service !== undefined) return service;
  service = false;
  try {
    if (typeof XMLHttpRequest !== "undefined" && typeof location !== "undefined" && location.origin === ORIGIN) {
      const x = request("GET", "status");
      service = x.status === 200 && JSON.parse(x.responseText).on === true;
    }
  } catch { service = false; }
  return service;
}

/** The float32 `x` as the bits of the nearest half float (ties to even). Exact for every half. Pure. */
export function halfBits(x) {
  F32[0] = x;
  const b = U32[0], sign = (b >>> 16) & 0x8000, m = b & 0x7fffff;
  let e = ((b >>> 23) & 0xff) - 112;
  if (e === 143) return sign | 0x7c00 | (m ? 0x200 : 0);            // infinity, NaN
  if (e >= 31) return sign | 0x7c00;
  if (e <= 0) {                                                      // a subnormal half, or zero
    if (e < -10) return sign;
    const full = m | 0x800000, shift = 14 - e, rest = full & ((1 << shift) - 1), mid = 1 << (shift - 1);
    let h = full >>> shift;
    if (rest > mid || (rest === mid && (h & 1))) h++;
    return sign | h;
  }
  let h = (e << 10) | (m >>> 13);
  const rest = m & 0x1fff;
  if (rest > 0x1000 || (rest === 0x1000 && (h & 1))) h++;
  return sign | h;
}
const F32 = new Float32Array(1), U32 = new Uint32Array(F32.buffer);

// ---------- inflate (RFC 1951): the stored parts are raw deflate streams of Python's zlib ----------
const LENGTH_BASE = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258];
const LENGTH_EXTRA = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0];
const DIST_BASE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577];
const DIST_EXTRA = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13];
const ORDER = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15];
// a decoding table for code lengths `lengths`: indexed by the next `bits` input bits, (symbol << 4) | length
function huffman(lengths) {
  let bits = 1;
  for (const n of lengths) bits = Math.max(bits, n);
  const count = new Uint16Array(16), next = new Uint16Array(16), table = new Int32Array(1 << bits);
  for (const n of lengths) count[n]++;
  count[0] = 0;
  for (let n = 1, code = 0; n < 16; n++) { code = (code + count[n - 1]) << 1; next[n] = code; }
  for (let sym = 0; sym < lengths.length; sym++) {
    const n = lengths[sym];
    if (!n) continue;
    let code = next[n]++, rev = 0;
    for (let k = 0; k < n; k++) { rev = (rev << 1) | (code & 1); code >>= 1; }
    for (let k = rev; k < table.length; k += 1 << n) table[k] = (sym << 4) | n;
  }
  return {table, bits};
}
let FIXED = null;
const damaged = (what) => new Error(`inflate: ${what}`);
/** Inflate the raw deflate stream `src` (a Uint8Array) into `out` (of its exact size); throws on a damaged stream. Pure. */
export function inflate(src, out) {
  const end = src.length + 4;
  let pos = 0, buf = 0, cnt = 0, op = 0;
  const take = (n) => { while (cnt < n) { buf |= src[pos++] << cnt; cnt += 8; } const v = buf & ((1 << n) - 1); buf >>>= n; cnt -= n; return v; };
  const decode = (h) => { while (cnt < 15) { buf |= src[pos++] << cnt; cnt += 8; } const e = h.table[buf & ((1 << h.bits) - 1)], n = e & 15; if (!n) throw damaged("a bad code"); buf >>>= n; cnt -= n; return e >> 4; };
  for (let last = 0; !last;) {
    last = take(1);
    const kind = take(2);
    if (kind === 0) {                                   // stored: whole bytes after the byte boundary
      pos -= cnt >> 3; buf = 0; cnt = 0;
      const len = src[pos] | (src[pos + 1] << 8);
      if (((src[pos + 2] | (src[pos + 3] << 8)) ^ 0xffff) !== len || pos + 4 + len > src.length || op + len > out.length) throw damaged("a bad stored block");
      out.set(src.subarray(pos + 4, pos + 4 + len), op); pos += 4 + len; op += len;
      continue;
    }
    let lit, dist;
    if (kind === 1) {
      if (!FIXED) {
        const l = new Uint8Array(288); l.fill(8, 0, 144); l.fill(9, 144, 256); l.fill(7, 256, 280); l.fill(8, 280, 288);
        FIXED = [huffman(l), huffman(new Uint8Array(30).fill(5))];
      }
      [lit, dist] = FIXED;
    } else if (kind === 2) {
      const nlit = take(5) + 257, ndist = take(5) + 1, ncode = take(4) + 4, cl = new Uint8Array(19);
      for (let i = 0; i < ncode; i++) cl[ORDER[i]] = take(3);
      const ch = huffman(cl), lengths = new Uint8Array(nlit + ndist);
      for (let i = 0; i < lengths.length;) {
        const sym = decode(ch);
        if (sym < 16) { lengths[i++] = sym; continue; }
        if (sym === 16 && i === 0) throw damaged("bad code lengths");
        const value = sym === 16 ? lengths[i - 1] : 0, times = sym === 16 ? 3 + take(2) : sym === 17 ? 3 + take(3) : 11 + take(7);
        if (i + times > lengths.length) throw damaged("bad code lengths");
        lengths.fill(value, i, i + times); i += times;
      }
      lit = huffman(lengths.subarray(0, nlit)); dist = huffman(lengths.subarray(nlit));
    } else throw damaged("a bad block type");
    const lt = lit.table, lm = (1 << lit.bits) - 1, dt = dist.table, dm = (1 << dist.bits) - 1, size = out.length;
    for (;;) {                                          // the hot loop, written out: a literal, a copy or the block's end
      if (pos > end) throw damaged("the stream ends early");
      while (cnt < 15) { buf |= src[pos++] << cnt; cnt += 8; }
      let e = lt[buf & lm], n = e & 15;
      if (!n) throw damaged("a bad code");
      buf >>>= n; cnt -= n;
      const sym = e >> 4;
      if (sym < 256) { if (op >= size) throw damaged("too long"); out[op++] = sym; continue; }
      if (sym === 256) break;
      const li = sym - 257;
      if (li >= 29) throw damaged("a bad length");
      let length = LENGTH_BASE[li];
      if (LENGTH_EXTRA[li]) length += take(LENGTH_EXTRA[li]);
      while (cnt < 15) { buf |= src[pos++] << cnt; cnt += 8; }
      e = dt[buf & dm]; n = e & 15;
      if (!n || e >> 4 >= 30) throw damaged("a bad distance");
      buf >>>= n; cnt -= n;
      const di = e >> 4, d = DIST_BASE[di] + (DIST_EXTRA[di] ? take(DIST_EXTRA[di]) : 0);
      if (d > op || op + length > size) throw damaged("a bad copy");
      if (d >= length && length > 24) { out.copyWithin(op, op - d, op - d + length); op += length; continue; }
      for (let k = 0; k < length; k++, op++) out[op] = out[op - d];
    }
  }
  if (op !== out.length) throw damaged("too short");
  return out;
}

/** Values of `width` bytes from `width` planes (every value's byte 0, then every byte 1...), as vidgen stores them. Pure. */
export function joinPlanes(planes, width) {
  if (width === 1) return planes;
  const out = new Uint8Array(planes.length), count = planes.length / width;
  for (let k = 0; k < width; k++) { const from = k * count; for (let i = 0, j = k; i < count; i++, j += width) out[j] = planes[from + i]; }
  return out;
}

/** What is stored of each target: one part per face (6 for a cube, 1 for a 2D target), or null when a target cannot be kept. Pure. */
export function layout(targets) {
  const parts = [];
  for (let i = 0; i < targets.length; i++) {
    const rt = targets[i];
    if (rt === null || rt === undefined) continue;
    const type = TYPES[rt.texture.type];
    if (!rt.isWebGLRenderTarget || rt.texture.format !== THREE.RGBAFormat || !type || rt.textures.length !== 1 || rt.depth > 1 || rt.samples > 0) return null;
    const faces = rt.isWebGLCubeRenderTarget ? 6 : 1;
    for (let face = 0; face < faces; face++) parts.push({target: i, face, width: rt.width, height: rt.height, type, bytes: rt.width * rt.height * BYTES[type]});
  }
  return parts;
}

// the GL renderer and what of it can change a bake's pixels (the unmasked names: Chromium's RENDERER is "WebKit WebGL")
function rendererInfo(renderer) {
  const gl = renderer.getContext(), debug = gl.getExtension("WEBGL_debug_renderer_info");
  return {renderer: String(gl.getParameter(debug ? debug.UNMASKED_RENDERER_WEBGL : gl.RENDERER)), vendor: String(gl.getParameter(debug ? debug.UNMASKED_VENDOR_WEBGL : gl.VENDOR)),
    version: String(gl.getParameter(gl.VERSION)), shading: String(gl.getParameter(gl.SHADING_LANGUAGE_VERSION)), extensions: (gl.getSupportedExtensions() ?? []).slice().sort()};
}
const glType = (gl, type) => ({u8: gl.UNSIGNED_BYTE, f16: gl.HALF_FLOAT, f32: gl.FLOAT})[type];
const view = (bytes, type) => type === "u8" ? bytes : type === "f16" ? new Uint16Array(bytes.buffer, bytes.byteOffset, bytes.length / 2) : new Float32Array(bytes.buffer, bytes.byteOffset, bytes.length / 4);

// level 0 of one face, as the bytes of its type (a half-float target read as float when the GL reads it so, then made half again)
function readPart(renderer, rt, part) {
  const gl = renderer.getContext(), props = renderer.properties.get(rt);
  const framebuffer = rt.isWebGLCubeRenderTarget ? props.__webglFramebuffer[part.face] : props.__webglFramebuffer;
  const current = renderer.getRenderTarget();
  renderer.state.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
  try {
    const out = new Uint8Array(part.bytes), n = part.width * part.height * 4;
    if (part.type === "f16" && gl.getParameter(gl.IMPLEMENTATION_COLOR_READ_TYPE) !== gl.HALF_FLOAT) {
      const f = new Float32Array(n), h = new Uint16Array(out.buffer);
      gl.readPixels(0, 0, part.width, part.height, gl.RGBA, gl.FLOAT, f);
      for (let i = 0; i < n; i++) h[i] = halfBits(f[i]);
    } else {
      gl.readPixels(0, 0, part.width, part.height, gl.RGBA, glType(gl, part.type), view(out, part.type));
    }
    return out;
  } finally {
    renderer.state.bindFramebuffer(gl.FRAMEBUFFER, current === null ? null : renderer.properties.get(current).__webglFramebuffer);
  }
}

// a stored entry into the targets; false (and nothing to undo: draw() then fills them whole) on any trouble
function load(renderer, targets, parts, found) {
  const gl = renderer.getContext();
  for (const rt of targets) if (rt) renderer.initRenderTarget(rt);
  for (let k = 0; k < 16 && gl.getError() !== gl.NO_ERROR; k++) { /* clear errors that are not ours */ }
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i], x = request("GET", `${found.key}/${i}`, null, true);
    if (x.status !== 200) return false;
    const text = x.responseText, packed = new Uint8Array(text.length);
    for (let k = 0; k < packed.length; k++) packed[k] = text.charCodeAt(k) & 255;
    const bytes = joinPlanes(inflate(packed, new Uint8Array(part.bytes)), WIDTH[part.type]);
    const rt = targets[part.target], cube = rt.isWebGLCubeRenderTarget, bind = cube ? gl.TEXTURE_CUBE_MAP : gl.TEXTURE_2D;
    renderer.state.bindTexture(bind, renderer.properties.get(rt.texture).__webglTexture);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false); gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE); gl.pixelStorei(gl.UNPACK_ALIGNMENT, 4);
    gl.pixelStorei(gl.UNPACK_ROW_LENGTH, 0); gl.pixelStorei(gl.UNPACK_SKIP_PIXELS, 0); gl.pixelStorei(gl.UNPACK_SKIP_ROWS, 0);
    gl.texSubImage2D(cube ? gl.TEXTURE_CUBE_MAP_POSITIVE_X + part.face : gl.TEXTURE_2D, 0, 0, 0, part.width, part.height, gl.RGBA, glType(gl, part.type), view(bytes, part.type));
    if (gl.getError() !== gl.NO_ERROR) return false;
  }
  const mipmaps = found.meta?.mipmaps ?? [];
  targets.forEach((rt, i) => {
    if (!rt) return;
    rt.texture.generateMipmaps = mipmaps[i] === true;
    if (mipmaps[i] !== true) return;
    const bind = rt.isWebGLCubeRenderTarget ? gl.TEXTURE_CUBE_MAP : gl.TEXTURE_2D;
    renderer.state.bindTexture(bind, renderer.properties.get(rt.texture).__webglTexture);
    gl.generateMipmap(bind);
  });
  return gl.getError() === gl.NO_ERROR;
}

// the bake's level 0 handed to vidgen: kept in the page as Blobs, which vidgen reads after the hook returns
function save(renderer, targets, parts, key) {
  const blobs = parts.map((part) => new Blob([readPart(renderer, targets[part.target], part)]));
  const meta = {mipmaps: targets.map((rt) => !!rt && rt.texture.generateMipmaps === true && rt.texture.minFilter !== THREE.LinearFilter && rt.texture.minFilter !== THREE.NearestFilter)};
  (globalThis.__vidgenBaked ??= []).push({key, blobs, meta});
  request("POST", `${key}/ready`, {parts: parts.map((p) => p.bytes), meta});
}

/** The render targets `targets()` makes, filled by `draw(targets)` or, when vidgen has kept this bake
 * (same `name`, `inputs`, targets and renderer), from vidgen's cache. Synchronous; never fails for the
 * cache's sake (a missing or damaged entry bakes). See the head of this file for what `inputs` must hold. */
export function baked(renderer, name, inputs, {targets, draw}) {
  const list = targets();
  if (!Array.isArray(list)) throw new Error(`baked("${name}"): targets() must return an array of render targets`);
  const parts = available() ? layout(list) : null;
  let found = null;
  if (parts !== null && parts.length > 0) {
    try {
      const x = request("POST", "lookup", {name: String(name), inputs, renderer: rendererInfo(renderer), parts, module: VERSION});
      found = x.status === 200 ? JSON.parse(x.responseText) : null;
    } catch { found = null; }
    let loaded = false;
    try { loaded = !!(found && found.found && load(renderer, list, parts, found)); } catch { loaded = false; }
    if (loaded) return list;
    if (found && found.found) {
      try { request("POST", `${found.key}/damaged`, {}); } catch { found = null; }
    }
  }
  draw(list);
  if (found && found.key) {
    try { save(renderer, list, parts, found.key); } catch { /* the bake stands; nothing kept */ }
  }
  return list;
}
