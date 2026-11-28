// vidgen's orbit helper for a `web` scene with `orbit_data:`. Run by Chromium
// after vidgen's own page script, only on pages of such scenes: it turns the data vidgen sends
// (`info.orbits`, computed in Python by vidgen's orbit model) into `ctx.orbits`.
//
// Units SI: metres, metres per second, seconds, radians. Frame: the mean ecliptic and equinox of
// J2000 (x towards the equinox, z towards the ecliptic's north pole), origin the central body;
// `ctx.orbits.frame` says which (a flyby: the planet's own frame). Every value is read from the
// frame the time falls on (round(t * fps)), never interpolated: the page shows the numbers Python
// computed for that frame. Without `t` a function reads the frame being drawn (vidgen's clock).
(() => {
  if (window.top !== window) return;
  const run = window.__vidgen;
  if (!run || typeof run.start !== 'function') return;

  const floats = (b64) => {
    const s = atob(b64 || '');
    const raw = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) raw[i] = s.charCodeAt(i);
    return new Float64Array(raw.buffer);
  };
  const triples = (a) => { const out = []; for (let i = 0; i < a.length; i += 3) out.push([a[i], a[i + 1], a[i + 2]]); return out; };

  function build(raw) {
    const fps = raw.fps, frames = raw.frames;
    const time = floats(raw.time);
    const series = {}, bodies = {}, names = [];
    for (const b of raw.bodies) {
      names.push(b.name);
      series[b.name] = {
        position: floats(b.position), velocity: floats(b.velocity),
        quaternion: b.quaternion ? floats(b.quaternion) : null, spin: b.spin ? floats(b.spin) : null,
        path: b.path ? floats(b.path) : null, conic: b.conic ? floats(b.conic) : null,
      };
      const info = {};
      for (const k in b) if (!['position', 'velocity', 'quaternion', 'spin', 'path', 'conic'].includes(k)) info[k] = b[k];
      bodies[b.name] = Object.freeze(info);
    }
    const body = (name) => {
      if (!(name in series)) throw new Error(`ctx.orbits: no body '${name}' (bodies: ${names.join(', ')})`);
      return series[name];
    };
    // The frame of scene time t (seconds from the scene's start; default: the frame drawn).
    const index = (t) => {
      const s = t === undefined ? performance.now() / 1000 : t;
      return Math.min(Math.max(Math.round(s * fps), 0), frames - 1);
    };
    const vec = (a, n, k) => (a === null ? null : Array.from(a.subarray(k * n, k * n + n)));
    const orbits = {
      version: raw.version, frame: raw.frame, frameText: raw.frame_text, units: { ...raw.units }, fps, frames,
      sceneFrames: raw.scene_frames, seconds: raw.seconds, span: raw.span, speedup: raw.speedup, jd0: raw.jd0, date: raw.date,
      dynamics: raw.dynamics, approximations: raw.approximations.slice(), names: names.slice(), bodies,
      index,
      // Simulated seconds since the first frame, and the Julian date, at scene time t.
      time(t) { return time[index(t)]; },
      jd(t) { return raw.jd0 + time[index(t)] / 86400; },
      position(name, t) { return vec(body(name).position, 3, index(t)); },
      velocity(name, t) { return vec(body(name).velocity, 3, index(t)); },
      // `name`'s position minus `to`'s (e.g. a moon around its planet).
      relative(name, to, t) { const a = this.position(name, t), b = this.position(to, t); return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; },
      // The body's orientation: the quaternion [x, y, z, w] turning its own axes (x the prime
      // meridian, z the north pole) into the data's frame; null for a body without rotation data.
      quaternion(name, t) { return vec(body(name).quaternion, 4, index(t)); },
      // The prime meridian's angle W (rad, 0 to 2π) from the equator's node, null without rotation data.
      spin(name, t) { const s = body(name).spin; return s === null ? null : s[index(t)]; },
      // The body's path over the scene and its orbit at the start, relative to its parent ([[x, y, z], ...]).
      path(name) { const p = body(name).path; return p === null ? [] : triples(p); },
      conic(name) { const p = body(name).conic; return p === null ? [] : triples(p); },
      burns(name) { body(name); return (bodies[name].burns || []).map((b) => ({ ...b })); },
      // The raw per-frame arrays (Float64Array) of a body: position, velocity, quaternion, spin, path, conic.
      series(name) { return body(name); },
      // three.js is y-up: the data's (x, y, z) is three's (x, z, -y), a quaternion (x, y, z, w) is (x, z, -y, w).
      yUp(v) { return [v[0], v[2], -v[1]]; },
      yUpQuaternion(q) { return [q[0], q[2], -q[1], q[3]]; },
    };
    return Object.freeze(orbits);
  }

  const start = run.start;
  run.start = function (info) {
    if (info && info.orbits) info = { ...info, orbits: build(info.orbits) };
    return start.call(this, info);
  };
})();
