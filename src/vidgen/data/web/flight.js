// vidgen's flight helper for a `web` scene with `flight_data:`. Run by Chromium after
// vidgen's page script and its orbit helper, only on pages of such scenes: the flights travel in the
// orbit bridge's payload (`info.orbits.flights`); this takes them out and turns them into `ctx.flight`
// (a page with flights and no orbit data then has no `ctx.orbits`).
//
// Units SI: metres, metres per second, seconds, radians, kg/m³. Frame: the scene's local frame (x east,
// y up, z south, the origin on the world's sphere under the anchor, three.js's axes as the air, sea and
// land modules draw them; `ctx.flight.frame`). Every value is read from the frame the time falls on
// (round(t * fps)), never interpolated: the page shows the numbers Python computed for that frame.
// Without `t` a function reads the frame being drawn (vidgen's clock).
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
  const SERIES = { position: 3, velocity: 3, quaternion: 4, speed: 1, mach: 1, height: 1, above_ground: 1, load: 1, bank: 1, pitch: 1, heading: 1, aoa: 1, heating: 1, climb: 1, time: 1 };

  function build(raw) {
    const fps = raw.fps, frames = raw.frames;
    const series = {}, flights = {}, names = [];
    for (const f of raw.flights) {
      names.push(f.name);
      const s = {};
      for (const k in SERIES) s[k] = floats(f[k]);
      s.path = floats(f.path);
      series[f.name] = s;
      flights[f.name] = Object.freeze({ name: f.name, start: f.start, end: f.end, warnings: f.warnings.slice(), legs: f.legs.map((l) => Object.freeze({ ...l })) });
    }
    const one = (name) => {
      if (!(name in series)) throw new Error(`ctx.flight: no flight '${name}' (flights: ${names.join(', ')})`);
      return series[name];
    };
    // The frame of scene time t (seconds from the scene's start; default: the frame drawn).
    const index = (t) => {
      const s = t === undefined ? performance.now() / 1000 : t;
      return Math.min(Math.max(Math.round(s * fps), 0), frames - 1);
    };
    const vec = (a, n, k) => Array.from(a.subarray(k * n, k * n + n));
    const scalar = (key) => function (name, t) { return one(name)[key][index(t)]; };
    const flight = {
      version: raw.version, frame: raw.frame, frameText: raw.frame_text, units: { ...raw.units }, fps, frames, sceneFrames: raw.scene_frames,
      start: raw.start, speedup: raw.speedup, world: raw.world, anchor: raw.anchor, ground: raw.ground,
      approximations: raw.approximations.slice(), warnings: raw.warnings.slice(), names: names.slice(), flights,
      index,
      // Flight seconds at scene time t (negative before the flight starts: it waits at its start).
      time: scalar('time'),
      active(name, t) { return one(name).time[index(t)] >= 0; },
      position(name, t) { return vec(one(name).position, 3, index(t)); },
      velocity(name, t) { return vec(one(name).velocity, 3, index(t)); },
      // The attitude: the quaternion [x, y, z, w] turning the craft's axes (x the left wing, y up, z the nose) into the scene's.
      quaternion(name, t) { return vec(one(name).quaternion, 4, index(t)); },
      speed: scalar('speed'), mach: scalar('mach'), height: scalar('height'), aboveGround: scalar('above_ground'), load: scalar('load'),
      bank: scalar('bank'), pitch: scalar('pitch'), heading: scalar('heading'), aoa: scalar('aoa'), heating: scalar('heating'), climb: scalar('climb'),
      // The path over the planned flight ([[x, y, z], ...], the scene's frame) and the legs as planned.
      path(name) { return triples(one(name).path); },
      legs(name) { one(name); return flights[name].legs.map((l) => ({ ...l })); },
      // The raw per-frame arrays (Float64Array) of a flight.
      series(name) { return one(name); },
      // Put a three.js object where the flight is and turn it as the flight does at scene time t.
      place(object, name, t) { const k = index(t), s = one(name); object.position.set(s.position[3 * k], s.position[3 * k + 1], s.position[3 * k + 2]); object.quaternion.set(s.quaternion[4 * k], s.quaternion[4 * k + 1], s.quaternion[4 * k + 2], s.quaternion[4 * k + 3]); return object; },
    };
    return Object.freeze(flight);
  }

  const start = run.start;
  run.start = function (info) {
    if (info && info.orbits && info.orbits.flights) {
      const { flights, ...rest } = info.orbits;
      info = { ...info, flight: build(flights) };
      if (rest.bodies) info.orbits = rest; else delete info.orbits;
    }
    return start.call(this, info);
  };
})();
