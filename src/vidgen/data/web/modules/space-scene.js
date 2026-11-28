// vidgen/space-scene: what the page of a declarative `space` scene needs besides the parts. Part of schu-video-generator (MIT licence); imported as "vidgen/space-scene" by the page
// vidgen writes for a `space` scene of video.yaml (and by the same page written out with `vidgen
// space-page`, to go on in code).
//
//   const at = sceneTime(ctx, {bar: 9, beat: 1});              // song bar 9 as seconds of the scene
//   const view = moveTrack([{name: "camera[1] (arc)", start: 0, shot: (t) => cam.arc(t, {...})}, ...]);
//   const pulse = reaction(ctx.music, {on: "kick", kind: "hits", decay: 0.18});   // pulse(t): 0..1.25
//   pageNote("camera[1] (arc): at 2.00 s: Saturn is 2.1 px in radius ...");        // a warning in vidgen's log
//
// Everything is a function of the scene time t and what it is given: nothing is kept between frames.
// No three.js: the mathematics runs in Node.
import {hitEnvelope, noteEnvelope, signalLevel, trackArrays} from "vidgen/music-time";

export const VERSION = 1;
const PREFIX = "vidgen/space-scene";
const RAD = Math.PI / 180;
const fail = (message) => new Error(`${PREFIX}: ${message}`);

/** A time of the scene's YAML as seconds of the scene: a number is already seconds; {bar, beat} is a place
 * in the song (bars and beats counted from 1, as `vidgen music plan` prints them) read with the score's
 * bar and beat (`ctx.music.score`) and the song time at the scene's start (`ctx.music.t0`). */
export function sceneTime(ctx, time, where = "a time") {
  if (typeof time === "number") return time;
  if (!time || typeof time !== "object" || typeof time.bar !== "number") throw fail(`${where} must be seconds or {bar, beat}, got ${JSON.stringify(time)}`);
  const music = ctx && ctx.music, score = music && music.score;
  if (!score) throw fail(`${where} is in bars, but the page has no score (give the scene music_data: and the video a score file as music:)`);
  return (time.bar - 1) * score.bar + ((time.beat ?? 1) - 1) * score.beat - music.t0;
}

// how far two shots are apart: the camera's step (metres) against its distance to what it looks at, and the turn (degrees)
function shotGap(a, b) {
  const d = Math.hypot(a.from[0] - b.from[0], a.from[1] - b.from[1], a.from[2] - b.from[2]);
  const reach = Math.max(a.distance ?? 0, b.distance ?? 0, a.focus ?? 0, b.focus ?? 0, 1e-9);
  const cos = a.forward[0] * b.forward[0] + a.forward[1] * b.forward[1] + a.forward[2] * b.forward[2];
  return {step: d / reach, turn: Math.acos(Math.min(1, Math.max(-1, cos))) / RAD, metres: d, fov: Math.abs((a.fov ?? 0) - (b.fov ?? 0))};
}

/** The camera of a scene made of moves one after another: `moves` = [{name, start, cut, shot(t)}] sorted by
 * `start` (seconds of the scene); at t the last move that has started is used (the first one before its
 * start). Where a move takes over from the one before without `cut`, the two shots at that time must meet
 * (the camera's place within 1 % of its distance to the subject, its direction within 1 degree, its field
 * of view within 0.5 degrees): otherwise an error naming both moves and how far apart they are, so a jump
 * is never drawn by accident. Returns view(t) -> shot. */
export function moveTrack(moves, {step = 0.01, turn = 1, fov = 0.5} = {}) {
  if (!Array.isArray(moves) || !moves.length) throw fail("moveTrack needs at least one move");
  for (let k = 1; k < moves.length; k++) {
    const a = moves[k - 1], b = moves[k];
    if (!(b.start >= a.start)) throw fail(`${b.name} starts at ${b.start.toFixed(2)} s, before ${a.name} (${a.start.toFixed(2)} s): give the moves in time order`);
    if (b.cut) continue;
    const g = shotGap(a.shot(b.start), b.shot(b.start));
    if (g.step > step || g.turn > turn || g.fov > fov)
      throw fail(`${b.name} does not start where ${a.name} leaves the camera at ${b.start.toFixed(2)} s (the camera jumps ${g.metres.toPrecision(3)} m, ` +
        `${(100 * g.step).toFixed(1)} % of its distance, and turns ${g.turn.toFixed(1)} degrees${g.fov > fov ? `, the lens changes by ${g.fov.toFixed(1)} degrees` : ""}): ` +
        "give it cut: true for a cut, or choose the moves so that they meet");
  }
  return (t) => {
    let k = 0;
    while (k + 1 < moves.length && t >= moves[k + 1].start - 1e-9) k++;
    return moves[k].shot(t);
  };
}

/** What a scene reacts to in the music, as a function of the scene time: `on` a track of the score or
 * "level" (the measured level of the video's music); `kind`: "hits" (each hit's gain falling by exp(-age /
 * decay): a pulse), "notes" (exp(-age / decay) from each note: a glint), "signal" (how strongly the track
 * sounds, released over `release` s: a level), "level" (ctx.music.level). Returns f(t) >= 0 (about 0..1). */
export function reaction(music, {on, kind, decay = 0.18, release = 1.2}) {
  if (!music) throw fail(`a reaction to "${on}" needs the music on the page (music_data:)`);
  if (on === "level" || kind === "level") return (t) => music.level(music.time(t));
  if (kind === "signal") return (t) => signalLevel(music, on, music.time(t), release);
  const arrays = trackArrays(music, kind === "notes" ? {notes: [on]} : {hits: [on]});
  if (kind === "notes") { const track = arrays.notes[on]; return (t) => noteEnvelope(track, music.time(t), decay); }
  if (kind === "hits") { const track = arrays.hits[on]; return (t) => hitEnvelope(track, music.time(t), decay); }
  throw fail(`a reaction's kind is "hits", "notes", "signal" or "level", got ${JSON.stringify(kind)}`);
}

/** A thing standing in a scene without orbit data, for the camera: {name, at(t) ([x, y, z] metres, the data's
 * axes: z up), radius}; `velocity` (m/s) moves it on a straight line from `at` at t = 0. */
export function freeSubject(name, at, radius = 0, velocity = null) {
  const v = velocity ?? [0, 0, 0];
  return {name, radius, at: (t) => [at[0] + v[0] * t, at[1] + v[1] * t, at[2] + v[2] * t]};
}

/** Leave a sentence for vidgen to print as a warning when the page has loaded (the problems a picture shows
 * that only the page can know: a subject under 3 px, a globe that turns too fast...). Each sentence once. */
export function pageNote(text) {
  const notes = (globalThis.__vidgenNotes ??= []);
  if (!notes.includes(String(text))) notes.push(String(text));
  return notes;
}

/** The camera's own checks of each move over its stretch of the scene (vidgen/space-camera's `check`) as page
 * notes: "camera[2] (fly-by): at 3.20 s: the camera is inside Saturn ...". `until`: the scene's length; the
 * moves are looked at on every frame (`fps`; at least 24 times), so a camera that follows a craft round a
 * world under a large speed-up is not taken for one that cuts through it between two far samples. */
export function checkMoves(cam, moves, until, {fps = 30} = {}) {
  const out = [];
  moves.forEach((m, k) => {
    const end = k + 1 < moves.length ? moves[k + 1].start : until;
    if (!(end > m.start)) return;
    const steps = Math.max(24, Math.ceil((end - m.start) * fps));
    for (const p of cam.check(m.shot, {from: m.start, to: end, steps})) { pageNote(`${m.name}: ${p}`); out.push(`${m.name}: ${p}`); }
  });
  return out;
}
