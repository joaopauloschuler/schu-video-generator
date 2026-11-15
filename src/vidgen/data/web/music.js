// vidgen's music helper for a `web` scene with `music_data:` (DESIGN.md §120.8). Run by Chromium
// after vidgen's own page script, only on pages of such scenes: it turns the data vidgen sends
// (`info.music`) into `ctx.music`, with functions reading the video's music at a song time.
//
// Times: `T` is song time (seconds into the music the scene's cue plays; it goes on counting
// through the repeats of a loop). Without `T` a function reads the frame being drawn
// (`ctx.music.now()` = `t0` + the scene's time).
(() => {
  if (window.top !== window) return;
  const run = window.__vidgen;
  if (!run || typeof run.start !== 'function') return;
  const RATE = 48000;

  const bytes = (b64) => {
    const s = atob(b64 || '');
    const out = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
    return out;
  };
  const typed = (b64, Kind, n, fill) => {
    if (b64 === undefined) return new Kind(n).fill(fill);
    const raw = bytes(b64);
    return new Kind(raw.buffer, 0, raw.byteLength / Kind.BYTES_PER_ELEMENT);
  };
  const unit = (b64) => Float32Array.from(bytes(b64), (v) => v / 255);

  function events(name, col) {
    const n = col.count;
    const t = typed(col.t, Uint32Array, n, 0), d = typed(col.d, Uint32Array, n, 0);
    const p = col.p === undefined ? null : typed(col.p, Uint8Array, n, 255);
    const v = typed(col.v, Float32Array, n, 0), g = typed(col.g, Float32Array, n, 1);
    const e = col.e === undefined ? v : typed(col.e, Float32Array, n, 0);
    const ins = typed(col.i, Uint8Array, n, 0), st = typed(col.s, Uint8Array, n, 255), sl = typed(col.l, Uint8Array, n, 0);
    const chords = col.c || {};
    const list = [];
    for (let k = 0; k < n; k++) {
      const time = t[k] / RATE, duration = d[k] / RATE;
      const pitch = p === null || p[k] === 255 ? null : p[k];
      const pitches = pitch === null ? [] : [pitch, ...(chords[k] || [])];
      list.push(Object.freeze({
        track: name, kind: col.kind === 'drum' ? 'hit' : 'note', instrument: col.instruments[ins[k]], index: k,
        time, duration, end: time + duration, pitch, pitches,
        dynamic: v[k], dynamicEnd: e[k], gain: g[k], strength: g[k] * Math.pow(10, v[k] / 20),
        stroke: st[k] === 255 ? null : col.strokes[st[k]], slur: sl[k] === 1,
      }));
    }
    return list;
  }

  // The index of the last of `list` (sorted by time) starting at or before T, -1 before the first.
  function lastIndex(list, T) {
    let lo = 0, hi = list.length - 1, k = -1;
    while (lo <= hi) {
      const m = (lo + hi) >> 1;
      if (list[m].time <= T + 1e-6) { k = m; lo = m + 1; } else hi = m - 1;
    }
    return k;
  }

  function build(raw) {
    const fps = raw.fps, frames = raw.frames, nb = raw.bands, first = raw.first, t0 = raw.t0, from = raw.from, to = raw.to;
    const series = {};
    for (const name of ['bands', 'level', 'low', 'onset']) series[name] = unit(raw.series[name]);
    const score = raw.score;
    const tracks = {}, byTrack = {};
    if (score) {
      for (const name in score.tracks) {
        const col = score.tracks[name];
        byTrack[name] = events(name, col);
        tracks[name] = Object.freeze({ kind: col.kind, instruments: col.instruments.slice(), count: col.count });
      }
    }
    const now = () => t0 + performance.now() / 1000;
    const at = (T) => (T === undefined ? now() : T);
    // The position of song time T (fractional) among the frames sent (video frames from..to-1;
    // before or after them the first or last is read).
    const position = (T) => Math.min(Math.max(first + (at(T) - t0) * fps - from, 0), Math.max(to - from - 1.000001, 0));
    const read = (values, stride, offset, T) => {
      const x = position(T), i = Math.floor(x), f = x - i, last = to - from - 1;
      const a = values[i * stride + offset], b = values[Math.min(i + 1, last) * stride + offset];
      return a + (b - a) * f;
    };
    const pick = (track, kind) => {
      if (track !== undefined && track !== null) {
        if (!(track in byTrack)) {
          const known = Object.keys(byTrack);
          throw new Error(`ctx.music: no track '${track}' (${known.length ? 'tracks: ' + known.join(', ') : 'the scene\'s music has no score'})`);
        }
        return byTrack[track];
      }
      const all = [];
      for (const name in byTrack) if (kind === undefined || (tracks[name].kind === 'drum') === (kind === 'hit')) all.push(...byTrack[name]);
      return all.sort((a, b) => a.time - b.time || (a.track < b.track ? -1 : 1));
    };
    const between = (list, a, b) => {
      const lo = a === undefined ? -Infinity : a, hi = b === undefined ? Infinity : b;
      return list.filter((e) => e.time >= lo - 1e-6 && e.time < hi - 1e-6);
    };
    const music = {
      fps, frames, first, from, to, t0, start: raw.start, bandCount: nb, edges: raw.edges.slice(),
      source: raw.source, score: score ? { tempo: score.tempo, time: score.time, beat: score.beat, bar: score.bar, seconds: score.seconds,
        loop: score.loop, file: score.file, sections: score.sections.map((s) => ({ ...s })) } : null,
      tracks,
      // Song time at the scene's time t (seconds from the scene's start; default: the frame drawn).
      time(t) { return t0 + (t === undefined ? performance.now() / 1000 : t); },
      now,
      band(i, T) {
        if (!(i >= 0 && i < nb)) throw new Error(`ctx.music.band(${i}): there are ${nb} bands (0 to ${nb - 1})`);
        return read(series.bands, nb, Math.floor(i), T);
      },
      bands(T) { const out = new Float32Array(nb); for (let i = 0; i < nb; i++) out[i] = read(series.bands, nb, i, T); return out; },
      level(T) { return read(series.level, 1, 0, T); },
      low(T) { return read(series.low, 1, 0, T); },
      onset(T) { return read(series.onset, 1, 0, T); },
      // Events starting in [from, to) (song seconds; both optional). No track: every drum track's (hits) / other track's (notes).
      hits(track, from, to) { return between(pick(track, 'hit'), from, to); },
      notes(track, from, to) { return between(pick(track, 'note'), from, to); },
      events(track, from, to) { return between(pick(track), from, to); },
      // The last event of the track starting at or before T, or null.
      last(track, T) { const list = pick(track), k = lastIndex(list, at(T)); return k < 0 ? null : list[k]; },
      // The events of the track sounding at T (started, not yet over).
      sounding(track, T) {
        const list = pick(track), now = at(T), out = [];
        for (let k = lastIndex(list, now); k >= 0; k--) if (list[k].end > now) out.unshift(list[k]);
        return out;
      },
      // An envelope of the track's hits: each event's strength falling by exp(-age / decay); the largest of the last eight.
      pulse(track, decay = 0.1, T) {
        const list = pick(track), now = at(T);
        let v = 0;
        for (let k = lastIndex(list, now), n = 0; k >= 0 && n < 8; k--, n++) v = Math.max(v, list[k].strength * Math.exp(-(now - list[k].time) / decay));
        return v;
      },
      // The score section playing at T ({name, start, end} in song seconds of one pass), or null.
      section(T) {
        if (!score) return null;
        let now = at(T);
        if (score.loop && score.seconds > 0) now = ((now % score.seconds) + score.seconds) % score.seconds;
        return music.score.sections.find((s) => s.start <= now + 1e-6 && now < s.end - 1e-6) || null;
      },
    };
    return Object.freeze(music);
  }

  const start = run.start;
  run.start = function (info) {
    if (info && info.music) info = { ...info, music: build(info.music) };
    return start.call(this, info);
  };
})();
