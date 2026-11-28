// vidgen/camera-looks: camera looks for three.js `web` scenes and `space` scenes (Steps 400–401).
// Part of schu-video-generator (MIT licence); imported by a page as "vidgen/camera-looks".
//
//   import {cameraLook} from "vidgen/camera-looks";
//   const look = cameraLook("drone", {finish: {noise: 0.006}});      // your own options win, key by key
//   finish = new Finish(renderer, scene, camera, ctx, look.finish);   // vidgen/three-finish
//   view = cam.operator(view, look.operator);                         // vidgen/space-camera-air (or operate)
//
// A look is a matched set of vidgen/three-finish's options (the sensor, the lens, the bloom,
// vignette and grade) and the camera operator's of vidgen/space-camera-air (the hand, the automatic exposure and
// the horizon): one kind of camera and the person or mount holding it. The table is written as JSON
// (quoted keys, numbers, strings; no functions) so vidgen reads the same table in Python for `camera_look:` of
// `space` scenes. `camera` (the sensor and the lens, nobody holding it) is what a `space` scene gets unless it gives
// `camera_look:` (`none`: the clean render); a page of your own gets nothing unless it asks. Motion blur is left to
// the scene: it multiplies a frame's cost by its samples. Data and two pure functions; nothing is drawn here.

const PREFIX = "vidgen/camera-looks";

export const CAMERA_LOOKS = Object.freeze({
  // the camera every `space` scene gets unless it says otherwise (Step 401): the sensor and the lens of a good small
  // camera and nobody holding it: a fine noise, a short dynamic range, light sharpening, the lens's own bend, faint
  // fringes and a lighter vignette towards the corners and a faint warm halation; no hand, no horizon error, no automatic exposure
  "camera": {
    "finish": {"noise": {"amount": 0.006}, "range": {"stops": 2.8, "shoulder": 0.1}, "sharpen": 0.3, "distort": 1,
               "edges": {"soft": 1, "fringe": 0.6}, "halation": {"amount": 0.15, "threshold": 0.45}, "vignette": 0.2},
    "operator": {}
  },
  // handheld through a spacecraft's window: braced against the frame (a calm hand), the window's glass veils the
  // shadows and spreads the highlights, its frame darkens the corners; a small camera's noise; cloud tops clip
  "window_handheld": {
    "finish": {"noise": {"amount": 0.01}, "range": {"stops": 2, "shoulder": 0.08}, "sharpen": 0.3, "distort": 1,
               "edges": {"soft": 1.4, "fringe": 0.7}, "halation": {"amount": 0.3, "threshold": 0.35, "radius": 8},
               "bloom": {"strength": 0.45, "radius": 0.7, "threshold": 0.8}, "vignette": {"amount": 0.45, "inner": 0.25, "outer": 1.3},
               "grade": {"lift": 0.012, "saturation": 0.92}},
    "operator": {"hand": {"style": "handheld", "amount": 0.6}, "exposure": {"strength": 0.3, "hunt": 0.5, "most": 1}, "horizon": {"degrees": 0.8}}
  },
  // a small camera on a gimbal: vibration only, a wide lens that bends, crisp and a little saturated, a smooth meter
  "drone": {
    "finish": {"noise": {"amount": 0.008, "size": 1.4, "color": 0.4}, "range": {"stops": 2.4, "shoulder": 0.1}, "sharpen": 0.7, "distort": 1.2,
               "edges": {"soft": 1.2, "fringe": 1}, "halation": {"amount": 0.15, "threshold": 0.45}, "bloom": {"strength": 0.25, "radius": 0.4, "threshold": 1}, "vignette": 0.2,
               "grade": {"saturation": 1.08, "contrast": 1.03}},
    "operator": {"hand": {"style": "mounted", "amount": 0.5}, "exposure": {"strength": 0.35, "hunt": 0.25, "speed": 0.35, "most": 1}}
  },
  // a broadcast camera with a long lens on a heavy head: a big sensor's fine noise, a soft knee, strong detail
  // enhancement, colour fringes of a long zoom, the iris ridden slowly by hand (no hunting)
  "broadcast_long_lens": {
    "finish": {"noise": {"amount": 0.006, "floor": 0.03}, "range": {"stops": 2.8, "shoulder": 0.15}, "sharpen": {"amount": 0.9, "radius": 1.5, "limit": 0.05},
               "edges": {"soft": 0.6, "fringe": 1.4, "power": 1.5}, "halation": {"amount": 0.2, "threshold": 0.45}, "bloom": {"strength": 0.3, "radius": 0.6, "threshold": 0.9},
               "vignette": 0.15, "grade": {"saturation": 1.05, "contrast": 1.06}},
    "operator": {"hand": {"style": "mounted", "amount": 0.35, "sway": 0.1}, "exposure": {"strength": 0.3, "delay": 0.5, "speed": 0.2, "hunt": 0, "most": 1}}
  },
  // a phone: a tiny sensor's blotchy noise, heavy sharpening, punchy colour, its lens corrected in software, a light
  // hand and a meter that is quick and hunts
  "phone": {
    "finish": {"noise": {"amount": 0.009, "size": 2, "color": 0.6}, "range": {"stops": 2.3, "shoulder": 0.03, "black": 0.01},
               "sharpen": {"amount": 1.2, "limit": 0.08}, "distort": 0.5, "edges": {"soft": 1.8, "fringe": 0.5}, "halation": {"amount": 0.08, "threshold": 0.5},
               "bloom": {"strength": 0.35, "radius": 0.5, "threshold": 0.9}, "vignette": 0.2, "grade": {"saturation": 1.12, "lift": 0.004}},
    "operator": {"hand": {"style": "handheld", "amount": 0.8, "tremor": 0.015, "reframe": 5}, "exposure": {"strength": 0.45, "delay": 0.1, "speed": 0.8, "hunt": 0.7, "most": 1},
                 "horizon": {"degrees": 1.5}}
  },
  // an action camera bolted to the craft or a chase plane: the engine's vibration, an ultra-wide lens that bends with
  // soft fringed corners, contrasty, an automatic exposure; level with what it is bolted to (no horizon error)
  "chase_mount": {
    "finish": {"noise": {"amount": 0.01, "size": 1.4}, "range": {"stops": 2, "shoulder": 0.05}, "sharpen": 0.8, "distort": 1.3,
               "edges": {"soft": 1.8, "fringe": 1.2}, "halation": {"amount": 0.15, "threshold": 0.45}, "bloom": {"strength": 0.3}, "vignette": 0.35,
               "grade": {"saturation": 1.1, "contrast": 1.05}},
    "operator": {"hand": {"style": "mounted", "amount": 1.5}, "exposure": {"strength": 0.4, "hunt": 0.5, "most": 1}}
  }
});
for (const look of Object.values(CAMERA_LOOKS)) { Object.freeze(look); Object.freeze(look.finish); Object.freeze(look.operator); }
/** The main value of a group given as a number, per section: the finish's (vidgen/three-finish's own) and the
 * operator's. `noise: 0.006` over a look is the look's noise with its amount at 0.006. */
export const LOOK_MAIN = Object.freeze({
  "finish": {"vignette": "amount", "flash": "amount", "bloom": "strength", "noise": "amount", "range": "stops", "sharpen": "amount",
             "distort": "amount", "edges": "soft", "halation": "amount"},
  "operator": {"exposure": "strength", "horizon": "degrees"}
});

const fail = (msg) => new Error(`${PREFIX}: ${msg}`);
function distance(a, b) {
  const d = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = d[0]; d[0] = i;
    for (let j = 1; j <= b.length; j++) { const cur = d[j]; d[j] = Math.min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = cur; }
  }
  return d[b.length];
}
function hint(name, known) {
  const best = known.map((k) => [distance(name.toLowerCase(), k.toLowerCase()), k]).sort((x, y) => x[0] - y[0])[0];
  return best && best[0] <= Math.max(2, name.length / 3) ? ` (did you mean "${best[1]}"?)` : "";
}
const plain = (v) => v !== null && typeof v === "object" && !Array.isArray(v) && !v.isColor && !v.isObject3D && !v.isVector3;

/** `own` over `base` (one section of a look: its finish or its operator), as a scene's own options go over a
 * look's: an object merges into the look's object key by key, at every depth; `true` keeps the look's group as
 * it is; a number (not 0) sets the group's main value (`main`, LOOK_MAIN's section); the hand's style named again
 * keeps the look's hand, another style (as a string or an object's `style`) replaces it; anything else (false, 0,
 * null, a string, an array) replaces the look's value. Neither argument is changed. */
export function lookMerge(base, own, main = {}) {
  const out = {...base};
  for (const [k, v] of Object.entries(own ?? {})) {
    const b = out[k];
    if (v === undefined) continue;
    if (!plain(b)) out[k] = v;
    else if (v === true) out[k] = b;
    else if (typeof v === "number" && v !== 0 && main[k]) out[k] = {...b, [main[k]]: v};
    else if (k === "hand" && typeof v === "string") out[k] = v === b.style ? b : v;
    else if (plain(v)) out[k] = k === "hand" && v.style !== undefined && v.style !== b.style ? v : lookMerge(b, v);
    else out[k] = v;
  }
  return out;
}

/** The options of camera look `name` (a key of CAMERA_LOOKS, or "none": no look, your own options alone) with
 * `own` = {finish, operator} over them (lookMerge: yours win, key by key). Returns new objects {finish, operator}: `finish` for vidgen/three-finish's
 * `Finish`, `operator` for vidgen/space-camera-air's `operate` or `airCamera(...).operator`. `metered: false`
 * leaves the look's automatic exposure out (a page with no meter, such as an orbital space scene's). */
export function cameraLook(name, own = {}, {metered = true} = {}) {
  if (typeof name !== "string" || !(name in CAMERA_LOOKS || name === "none")) {
    const looks = [...Object.keys(CAMERA_LOOKS), "none"];
    throw fail(`no camera look ${JSON.stringify(name)}${hint(String(name), looks)}; looks: ${looks.join(", ")}`);
  }
  if (own === null || typeof own !== "object" || Array.isArray(own)) throw fail(`a camera look's own options are {finish, operator}, got ${JSON.stringify(own)}`);
  for (const k of Object.keys(own)) if (k !== "finish" && k !== "operator") throw fail(`unknown option "${k}"${hint(k, ["finish", "operator"])}; a camera look's own options are finish and operator`);
  const copy = (v) => JSON.parse(JSON.stringify(v));
  if (name === "none") return {finish: copy(own.finish ?? {}), operator: copy(own.operator ?? {})};
  const operator = copy(CAMERA_LOOKS[name].operator);
  if (!metered) delete operator.exposure;
  return {finish: lookMerge(copy(CAMERA_LOOKS[name].finish), own.finish, LOOK_MAIN.finish), operator: lookMerge(operator, own.operator, LOOK_MAIN.operator)};
}
