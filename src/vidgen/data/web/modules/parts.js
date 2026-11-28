// vidgen/parts: the registry of ready-made three.js parts. Part of
// schu-video-generator (MIT licence); imported by a page as "vidgen/parts".
//
// A part is one ready-made thing a page can put into a scene: a sky, a body, a craft, a phenomenon,
// a structure, an effect. Each shipped module describes its parts in a file of its own,
// data/web/parts/<module>.js (served as "vidgen/parts/<module>.js"), so the module itself (and the
// keys of the pages that import it) never changes when a part is added:
//
//   import {definePart} from "vidgen/parts";
//   import {SkyDome, color} from "vidgen/three-kit";
//   definePart({"name": "nebula-dome", "kind": "sky", "module": "vidgen/three-kit",
//               "label": "a nebula with stars, baked once", "use": "const sky = new SkyDome(seed); sky.turn(t)",
//               "options": {"gain": 1}, "seed": 3, "at": 2},
//     ({scene, camera, options, seed}) => { const sky = new SkyDome(seed); ...; return {frame(t) {...}}; });
//
// The first argument is JSON (double-quoted keys and strings, no expressions): `vidgen parts --list`
// reads it without a browser. `make(stage)` puts the part into stage.scene (the default camera at
// (0, 0.8, 6) looking at the origin, one key light and a faint fill; it may move the camera) and may
// return {frame(t)} to set the part to time t (seconds; `at` is the time the contact sheet shows),
// {finish: false} for a picture without vidgen/three-finish's bloom and tone mapping, or both.
// Pages may use the registry too: import the parts file, then buildPart(name, stage, options).
import * as THREE from "three";

export const VERSION = 1;
/** The kinds of parts, in the order the contact sheet shows them. */
export const KINDS = Object.freeze(["sky", "body", "light", "air", "sea", "cloud", "land", "craft", "craft-part", "phenomenon", "camera", "structure", "effect", "environment"]);
/** The fields of a part's description: required ones, then optional ones with their defaults. */
export const REQUIRED = Object.freeze(["name", "kind", "module", "label", "use"]);
export const DEFAULTS = Object.freeze({options: {}, seed: 1, at: 2});
const NAME = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/;
const REGISTRY = new Map();

const fail = (message) => new Error(`vidgen/parts: ${message}`);
function closest(word, choices) {
  let best = null, score = Infinity;
  for (const c of choices) {
    const d = distance(word, c);
    if (d < score) { best = c; score = d; }
  }
  return best !== null && score <= Math.max(2, Math.floor(word.length / 3)) ? ` (did you mean "${best}"?)` : "";
}
function distance(a, b) {
  const row = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0]; row[0] = i;
    for (let j = 1; j <= b.length; j++) { const keep = row[j]; row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = keep; }
  }
  return row[b.length];
}

/** Register a part: `info` (JSON: name, kind, module, label, use; options, seed, at) and `make(stage)`. */
export function definePart(info, make) {
  for (const key of REQUIRED) if (typeof info[key] !== "string" || !info[key]) throw fail(`a part needs "${key}" (a string): ${JSON.stringify(info)}`);
  for (const key of Object.keys(info)) if (!REQUIRED.includes(key) && !(key in DEFAULTS)) throw fail(`part "${info.name}": unknown field "${key}"${closest(key, [...REQUIRED, ...Object.keys(DEFAULTS)])}`);
  if (!NAME.test(info.name)) throw fail(`part name "${info.name}": lower-case words joined by hyphens`);
  if (!KINDS.includes(info.kind)) throw fail(`part "${info.name}": kind "${info.kind}"${closest(info.kind, KINDS)}; kinds: ${KINDS.join(", ")}`);
  if (REGISTRY.has(info.name)) throw fail(`part "${info.name}" is defined twice`);
  if (typeof make !== "function") throw fail(`part "${info.name}": make(stage) must be a function`);
  const entry = Object.freeze({...DEFAULTS, ...info, options: Object.freeze({...(info.options ?? {})}), make});
  REGISTRY.set(info.name, entry);
  return entry;
}

/** The registered parts (in the order defined), of `kind` and whose names contain `name` when given. */
export function parts({kind = null, name = null} = {}) {
  return [...REGISTRY.values()].filter((p) => (kind === null || p.kind === kind) && (name === null || p.name.includes(name)));
}

/** The part called `name`; an error naming the closest one when there is none. */
export function part(name) {
  const p = REGISTRY.get(name);
  if (!p) throw fail(`no part "${name}"${closest(name, [...REGISTRY.keys()])}; import its file ("vidgen/parts/<module>.js") first`);
  return p;
}

/** A scene with the default camera and light for a frame of `width` x `height`: {scene, camera, key, fill}. */
export function defaultStage(width, height) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x000000);
  const camera = new THREE.PerspectiveCamera(40, width / height, 0.05, 5000);
  camera.position.set(0, 0.8, 6); camera.lookAt(0, 0, 0); camera.updateMatrixWorld();
  const key = new THREE.DirectionalLight(0xfff4e6, 2.6); key.position.set(4, 3, 5);
  const fill = new THREE.HemisphereLight(0x8fb4ff, 0x000000, 0.12);
  scene.add(key, fill);
  return {scene, camera, key, fill};
}

/** Put the part `name` into `stage` ({renderer, scene, camera, width, height, ctx}) with its options
 * (`options` over its defaults) and seed: what its make returned ({frame(t)}, {finish}), or {}. */
export function buildPart(name, stage, options = {}, seed = null) {
  const p = part(name);
  const made = p.make({...stage, options: {...p.options, ...options}, seed: seed ?? p.seed, part: p});
  return made ?? {};
}
