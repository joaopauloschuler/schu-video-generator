// vidgen/music-time: song time, bars and beats, the score's events and the pictures' reactions to
// them, for `web` scenes of music videos. Part of schu-video-generator (MIT
// licence); imported by a page as "vidgen/music-time". Plain JavaScript: no three.js, no DOM.
//
// Song time T is seconds into the music (`ctx.music.time(t)` with `music_data:`). A page that draws
// every frame from T alone, and never from the frame before, looks the same on both sides of a cut
// between two scenes on one script. The shapes, seeded numbers and keyframes here are what the
// example films ("Parallel Space", "Escapement", "Signal Fire") wrote by hand, with the same
// arithmetic, so a port of a film keeps its pictures.
//
// Tracks: `trackArrays(ctx.music, ...)` copies a scene's hits ({t, g}: times and gains) and notes
// ({t, d, p}: times, lengths, pitches) into sorted Float32Arrays, read by the envelope functions
// below; signalLevel() and eventLevel() read ctx.music's event objects directly.

export const VERSION = 1;

// ---------- shaping ----------
export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const mix = (a, b, u) => a + (b - a) * u;
/** 0 below a, 1 above b, a smooth S between (cubic). smoothstep(0, 1, u) is the cubic ease. */
export const smoothstep = (a, b, x) => { const u = clamp((x - a) / (b - a)); return u * u * (3 - 2 * u); };
/** The quintic ease of u clamped to 0..1: starts and stops with no jump in speed or acceleration. */
export const smootherstep = (u) => { u = clamp(u); return u * u * u * (u * (u * 6 - 15) + 10); };
export const easeOutCubic = (u) => 1 - Math.pow(1 - clamp(u), 3);
export const dbToGain = (db) => Math.pow(10, db / 20);

// ---------- seeded numbers ----------
/** A generator of numbers in [0, 1) from an integer seed (mulberry32): the same seed, the same sequence. */
export function rng(seed) { let s = seed >>> 0; return () => { s = (s + 0x6D2B79F5) >>> 0; let r = Math.imul(s ^ (s >>> 15), 1 | s); r ^= r + Math.imul(r ^ (r >>> 7), 61 | r); return ((r ^ (r >>> 14)) >>> 0) / 4294967296; }; }
/** A number in [0, 1) for the pair (i, k), without state: the same pair, the same number. */
export const hash = (i, k = 0) => { const x = Math.sin(i * 127.1 + k * 311.7 + 0.5) * 43758.5453; return x - Math.floor(x); };

// ---------- moves ----------
/** A point moving through keyframes [[t, x, y, ...], ...], each segment eased (cubic); held before the first and after the last. */
export function keyframes(keys, t) {
  if (t <= keys[0][0]) return keys[0].slice(1);
  for (let i = 0; i < keys.length - 1; i++) if (t <= keys[i + 1][0]) { const a = keys[i], b = keys[i + 1], u = smoothstep(0, 1, (t - a[0]) / (b[0] - a[0])); return a.slice(1).map((v, k) => mix(v, b[k + 1], u)); }
  return keys[keys.length - 1].slice(1);
}
/** One smooth move from point a to point b (arrays) as u goes from 0 to 1 (quintic ease, no stop in the middle). */
export const glide = (a, b, u) => a.map((v, k) => mix(v, b[k], smootherstep(u)));

// ---------- camera paths (Step 359) ----------
/** The camera circling `centre` at song time T: [x, y, z, lx, ly, lz] for three-kit's aimCamera(...x).
 * radius, height (above the centre), speed (radians a second; negative turns the other way), phase
 * (the angle at T = 0), bob (how far the height swings, once every two turns). From T alone, so the
 * same T gives the same place on both sides of a cut. */
export function orbit(T, {centre = [0, 0, 0], radius = 20, height = 3, speed = 0.05, phase = 0, bob = 0} = {}) {
  const a = phase + speed * T;
  return [centre[0] + Math.sin(a) * radius, centre[1] + height + bob * Math.sin(a * 0.5), centre[2] + Math.cos(a) * radius, centre[0], centre[1], centre[2]];
}
/** The point at u (0..1, clamped) on a smooth path through every one of `points` ([[x, y, z], ...], two
 * or more): a Catmull-Rom spline, one segment per pair, the ends continued in their own direction. */
export function pathPoint(points, u) {
  const n = points.length - 1, s = clamp(u) * n, i = Math.min(n - 1, Math.floor(s)), f = s - i;
  const at = (k) => k < 0 ? points[0].map((v, j) => 2 * v - points[1][j]) : k > n ? points[n].map((v, j) => 2 * v - points[n - 1][j]) : points[k];
  const p0 = at(i - 1), p1 = at(i), p2 = at(i + 1), p3 = at(i + 2);
  return p1.map((_, k) => 0.5 * (2 * p1[k] + (p2[k] - p0[k]) * f + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * f * f + (3 * p1[k] - p0[k] - 3 * p2[k] + p3[k]) * f * f * f));
}
/** A flight along the path through `points` at u (0..1): [x, y, z, lx, ly, lz], looking at the point
 * `ahead` further along it (beyond the end: on along the last segment's direction). */
export function flyThrough(points, u, ahead = 0.05) {
  const p = pathPoint(points, u), v = u + ahead;
  const q = v <= 1 ? pathPoint(points, v) : pathPoint(points, 1).map((e, k) => e + (e - pathPoint(points, 1 - (v - 1))[k]));
  return [...p, ...q];
}

// ---------- a colour script (Step 359) ----------
const HEX = /^#[0-9a-f]{6}$/i;
const channels = (c) => [(c >> 16) & 255, (c >> 8) & 255, c & 255];
/** A colour script: `stops` [{at: song seconds, base: "#rrggbb", ...}, ...] sorted by `at` (as `vidgen music
 * plan` writes them in data.script). Returns (T) => the stop in force at T (the last at or before it; the
 * first before any) with its "#rrggbb" values as numbers (0xrrggbb, for three.js's Color or three-kit's
 * color). With glide > 0 the colours ease into the next stop's over the `glide` s before it, so they
 * still change exactly at the stop (a cut on a bar line) and never across it. */
export function colourScript(stops, glide = 0) {
  const parsed = stops.map((s) => Object.fromEntries(Object.entries(s).map(([k, v]) => [k, typeof v === "string" && HEX.test(v) ? parseInt(v.slice(1), 16) : v])));
  return (T) => {
    let i = 0;
    while (i + 1 < parsed.length && parsed[i + 1].at <= T + 1e-6) i++;
    const a = parsed[i], b = parsed[i + 1];
    if (!(glide > 0) || !b || T < b.at - glide) return a;
    const u = smoothstep(b.at - glide, b.at, T), out = {...a};
    for (const k of Object.keys(a)) if (k !== "at" && typeof a[k] === "number" && typeof b[k] === "number" && typeof stops[i][k] === "string") {
      const x = channels(a[k]), y = channels(b[k]);
      out[k] = x.reduce((c, v, j) => (c << 8) | Math.round(mix(v, y[j], u)), 0);
    }
    return out;
  };
}

// ---------- bars and beats ----------
/** How many whole `length`s (a bar, a beat, a sixteenth, in seconds) have passed at T: robust to a T a
 * rounding error short of a bar line. */
export const count = (T, length) => Math.floor(T / length + 1e-6);
/** Lengths of a bar of `bar` seconds: {bar, beat, sixteenth} (`beats` beats, 4 sixteenths a beat). */
export function barClock(bar, beats = 4) { return {bar, beat: bar / beats, sixteenth: bar / (beats * 4)}; }

// ---------- the score's events as arrays ----------
/** Hits {name: {t, g}} and notes {name: {t, d, p}} of ctx.music as Float32Arrays sorted by time.
 * `hits`, `notes`: track names, or {name: [score tracks]} to gather several tracks under one name.
 * `grid` (seconds, e.g. a sixteenth): times and lengths rounded to 1/1000 of it, as an exporter that
 * wrote them in sixteenths to three decimals did. A note's pitch is 0 when it has none. */
export function trackArrays(music, {hits = [], notes = [], grid = null} = {}) {
  const snap = grid ? (x) => Math.round(x / grid * 1000) / 1000 * grid : (x) => x;
  const gather = (spec) => Array.isArray(spec) ? Object.fromEntries(spec.map((k) => [k, [k]])) : spec;
  const list = (sources) => sources.length === 1 ? music.events(sources[0]) : sources.flatMap((k) => music.events(k)).sort((a, b) => a.time - b.time);
  const out = {hits: {}, notes: {}};
  for (const [name, sources] of Object.entries(gather(hits))) {
    const h = list(sources); out.hits[name] = {t: Float32Array.from(h, (e) => snap(e.time)), g: Float32Array.from(h, (e) => e.gain)};
  }
  for (const [name, sources] of Object.entries(gather(notes))) {
    const n = list(sources); out.notes[name] = {t: Float32Array.from(n, (e) => snap(e.time)), d: Float32Array.from(n, (e) => snap(e.duration)), p: Float32Array.from(n, (e) => e.pitch ?? 0)};
  }
  return out;
}
/** The index of the last of the sorted `times` at or before T (within 10 µs), -1 before the first. */
export function lastIndex(times, T) { let lo = 0, hi = times.length - 1, k = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (times[m] <= T + 1e-5) { k = m; lo = m + 1; } else hi = m - 1; } return k; }

// ---------- reactions (track arrays) ----------
/** A drum's envelope: each of the last three hits its gain (at most 1.25) falling by exp(-age / decay);
 * the largest. 0 for a missing track. Use it for brightness (kick -> a light pulse), never for zoom. */
export function hitEnvelope(track, T, decay) {
  if (!track) return 0;
  let v = 0;
  for (let j = lastIndex(track.t, T), n = 0; j >= 0 && n < 3; j--, n++) v = Math.max(v, Math.min(track.g[j], 1.25) * Math.exp(-(T - track.t[j]) / decay));
  return v;
}
/** How many hits of the track have come by T. */
export function hitCount(track, T) { return track ? lastIndex(track.t, T) + 1 : 0; }
/** Seconds since the last hit of the track (1e9 before the first). */
export function hitAge(track, T) { const i = track ? lastIndex(track.t, T) : -1; return i < 0 ? 1e9 : T - track.t[i]; }
/** The note playing at T (or played last): {i, p: pitch, age: seconds since it began, d: its length}, or null. */
export function noteAt(track, T) { const i = track ? lastIndex(track.t, T) : -1; return i < 0 ? null : {i, p: track.p[i], age: T - track.t[i], d: track.d[i]}; }
/** exp(-age / decay) of the last note: a glint on every note. */
export function noteEnvelope(track, T, decay) { const q = noteAt(track, T); return q ? Math.exp(-q.age / decay) : 0; }
/** How loud a held note sounds at T: a linear attack over `attack` s, held for its length, then exp(-after / release). */
export function noteLevel(track, T, attack = 0.05, release = 0.5) { const q = noteAt(track, T); if (!q) return 0; return q.age < q.d ? clamp(q.age / attack) : Math.exp(-(q.age - q.d) / release); }
/** The melody's [pitch, level] at T: the pitch glides from the note before (when it ended under 0.4 s
 * earlier) over `glide` s; the level as noteLevel with a 0.45 s release, a note's 0.05 s attack rising
 * from the level the note before has at its start (a line of notes keeps its light). Before the first
 * note: [first pitch or 69, 0]. */
export function melody(track, T, glide = 0.07) {
  const i = track ? lastIndex(track.t, T) : -1;
  if (i < 0) return [track && track.p.length ? track.p[0] : 69, 0];
  const age = T - track.t[i], prev = i > 0 && track.t[i] - (track.t[i - 1] + track.d[i - 1]) < 0.4 ? track.p[i - 1] : track.p[i];
  const p = mix(prev, track.p[i], smoothstep(0, glide, age));
  if (age >= track.d[i]) return [p, Math.exp(-(age - track.d[i]) / 0.45)];
  const rise = clamp(age / 0.05);
  if (rise >= 1 || i === 0) return [p, rise];
  const before = track.t[i] - track.t[i - 1], from = before < track.d[i - 1] ? clamp(before / 0.05) : Math.exp(-(before - track.d[i - 1]) / 0.45);
  return [p, from + (1 - from) * rise];
}

// ---------- reactions (ctx.music events) ----------
/** An event's level at T, 1 for an unmarked note: its dynamic (dB) moving from `dynamic` to `dynamicEnd`
 * over its length (a hairpin), times its accent `gain`. */
export function eventLevel(e, T) {
  const u = e.duration > 0 ? Math.min(1, Math.max(0, (T - e.time) / e.duration)) : 0;
  return e.gain * dbToGain(e.dynamic + (e.dynamicEnd - e.dynamic) * u);
}
/** How strongly a track sounds at T (0 when silent): the loudest of its events of the last 12 s that
 * still sound, each faded out over `release` s after its end. */
export function signalLevel(music, track, T, release = 0.6) {
  let v = 0;
  for (const e of music.events(track, T - 12, T + 1e-6)) {
    const after = T - e.end;
    if (after < release) v = Math.max(v, eventLevel(e, Math.min(T, e.end)) * (after > 0 ? 1 - after / release : 1));
  }
  return v;
}

// ---------- what a scene follows (Step 359) ----------
/** The reactions a page drafted by `vidgen music plan` follows. `react` = {pulse, ring, glint, glow}: track
 * names (data.react). Returns {song} (trackArrays of them) and functions of song time T: pulse(T) the
 * strongest envelope of the pulse tracks (hitEnvelope, `decay` s; 0 without any) for brightness; glow(T)
 * the loudest glow track (signalLevel, `release` s; without any, the measured level ctx.music.level(T));
 * drop(T) a flash after each of `drops` (song seconds) fading over `flash` s; and ring (the first ring
 * track's hits or null) and glints (the glint tracks' notes) for three-kit's shock rings and glints. */
export function reactions(music, react = {}, {decay = 0.18, release = 1.2, drops = [], flash = 0.5} = {}) {
  const pulse = react.pulse ?? [], ring = react.ring ?? [], glint = react.glint ?? [], glow = react.glow ?? [];
  const song = trackArrays(music, {hits: [...new Set([...pulse, ...ring])], notes: glint});
  return {
    song,
    pulse: (T) => pulse.reduce((v, n) => Math.max(v, hitEnvelope(song.hits[n], T, decay)), 0),
    glow: (T) => glow.length ? glow.reduce((v, n) => Math.max(v, signalLevel(music, n, T, release)), 0) : music.level(T),
    drop: (T) => drops.reduce((v, d) => T >= d - 1e-6 ? Math.max(v, Math.exp(-(T - d) / flash)) : v, 0),
    ring: ring.length ? song.hits[ring[0]] : null,
    glints: glint.map((n) => song.notes[n]),
  };
}
