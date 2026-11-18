// vidgen/space-scene-air: what the page of a declarative `space` scene in the air or beside a giant ship needs
// besides the parts and vidgen/space-scene (DESIGN.md §123.14). Part of schu-video-generator (MIT licence);
// imported as "vidgen/space-scene-air" by the page vidgen writes for such a scene (and by the same page written
// out with `vidgen space-page`). A module of its own, so vidgen/space-scene's bytes (in the keys of every
// earlier `space` scene) stay as they were.
//
//   const gear = ramp(t, {over: [10, 14], from: 0, to: 1});                // eased from 0 to 1 over 10..14 s
//   const flash = flashes(t, [{at: 8, amount: 3, rise: 0.25, fall: 0.6}]);  // three-finish's flash, one curve across a cut
//   const strikes = hitTimes(ctx.music, "kick");                             // the kick's hits as seconds of the scene
//   const m = once(() => matchDisc(...));                                    // worked out once, on first use
//
// Everything is a function of the scene time t and what it is given: nothing is kept between frames but what
// `once` keeps (a value of the scene, the same at every t). No three.js: the mathematics runs in Node.
import {flashCut} from "vidgen/space-camera";
import {trackArrays} from "vidgen/music-time";

export const VERSION = 1;
const PREFIX = "vidgen/space-scene-air";
const fail = (message) => new Error(`${PREFIX}: ${message}`);
const isNum = (x) => typeof x === "number" && Number.isFinite(x);

/** A value that moves from `from` to `to` over `over` = [start, end] (seconds of the scene), eased in and out
 * (a smoothstep); before the start `from`, after the end `to`. */
export function ramp(t, {over, from = 0, to = 1}) {
  if (!Array.isArray(over) || over.length !== 2 || !over.every(isNum) || !(over[1] > over[0])) throw fail(`a ramp's over must be [start, end] with end after start, got ${JSON.stringify(over)}`);
  const u = Math.min(1, Math.max(0, (t - over[0]) / (over[1] - over[0])));
  return from + (to - from) * u * u * (3 - 2 * u);
}

/** The flash of three-finish at t: the sum of vidgen/space-camera's flashCut for each cut ({at, amount, rise,
 * fall}; `at` seconds of the scene, which may be the scene's end or its start: the scene on each side of the cut
 * asks with its own time and the same cut, so the light is one curve across it). */
export function flashes(t, cuts) {
  if (!Array.isArray(cuts)) throw fail(`flashes needs a list of cuts, got ${JSON.stringify(cuts)}`);
  let sum = 0;
  for (const c of cuts) {
    if (!c || !isNum(c.at)) throw fail(`a flash needs at: the cut's time in seconds of the scene, got ${JSON.stringify(c)}`);
    sum += flashCut(t, c.at, {amount: c.amount ?? 3, rise: c.rise ?? 0.25, fall: c.fall ?? 0.6});
  }
  return sum;
}

/** The hits of a track of the score as seconds of the scene (song time less the scene's start in the song),
 * for vidgen/space-clouds' lightning `times`: a strike on each hit. */
export function hitTimes(music, track) {
  if (!music) throw fail(`strikes on the hits of "${track}" need the music on the page (music_data:)`);
  const hits = trackArrays(music, {hits: [track]}).hits[track];
  const times = Array.from(hits && hits.t ? hits.t : [], (x) => x - (music.t0 ?? 0));
  return times;
}

/** `f()` worked out once, the first time the returned function is called, and kept: for a value of the scene
 * that does not depend on t (a match cut's distance and place, from the shot before the cut). */
export function once(f) {
  let done = false, value;
  return () => { if (!done) { value = f(); done = true; } return value; };
}
