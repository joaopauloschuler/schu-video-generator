// vidgen's 3D page (DESIGN.md §114): builds a three.js scene from vidgen's scene description
// (JSON, version 1) and draws the frame at a time vidgen gives. Time comes only from frame(t):
// no requestAnimationFrame, no clock, no randomness, so the same description gives the same
// pixels.
import * as THREE from './three.module.js';

const DESCRIPTION_VERSION = 1;
const DRAW_MODES = ['normal'];

let renderer = null;
let scene = null;
let camera = null;
let description = null;
const named = new Map();   // object id -> THREE.Object3D

function vec(v) {
  return new THREE.Vector3(v[0], v[1], v[2]);
}

function geometry(obj) {
  if (obj.shape === 'box') {
    const [w, h, d] = obj.size;
    return new THREE.BoxGeometry(w, h, d);
  }
  throw new Error(`unknown shape '${obj.shape}'`);
}

function addObject(obj) {
  const mesh = new THREE.Mesh(geometry(obj), new THREE.MeshLambertMaterial({ color: obj.color }));
  mesh.name = obj.id;
  setVector(mesh, 'position', obj.position);
  setVector(mesh, 'rotation', obj.rotation);
  scene.add(mesh);
  named.set(obj.id, mesh);
}

function addLight(light) {
  if (light.kind === 'ambient') {
    const ambient = new THREE.AmbientLight(light.color, light.intensity);
    ambient.name = light.id;
    scene.add(ambient);
  } else if (light.kind === 'sun') {
    const sun = new THREE.DirectionalLight(light.color, light.intensity);
    sun.name = light.id;
    sun.position.copy(vec(light.position));
    scene.add(sun);
    scene.add(sun.target);   // aims at the origin
  } else {
    throw new Error(`unknown light kind '${light.kind}'`);
  }
}

// The camera's field of view is the angle across the frame's shorter side (so a subject framed
// in 16:9 stays framed in 9:16); three.js wants the vertical one.
function verticalFov(fov, aspect) {
  if (aspect >= 1) return fov;
  const half = THREE.MathUtils.degToRad(fov) / 2;
  return THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(half) / aspect));
}

function setVector(target, property, value) {
  if (property === 'position') {
    target.position.set(value[0], value[1], value[2]);
  } else if (property === 'rotation') {
    const r = THREE.MathUtils.degToRad;
    target.rotation.set(r(value[0]), r(value[1]), r(value[2]), 'XYZ');
  } else if (property === 'look_at') {
    target.userData.lookAt = value;
  } else {
    throw new Error(`unknown property '${property}'`);
  }
}

const EASINGS = {
  linear: (u) => u,
  smooth: (u) => u * u * (3 - 2 * u),
};

// The value of a track at time t: its keys' values, eased between neighbours, held before the
// first key and after the last.
function trackValue(track, t) {
  const keys = track.keys;
  if (t <= keys[0].t) return keys[0].value;
  const last = keys[keys.length - 1];
  if (t >= last.t) return last.value;
  let k = 0;
  while (keys[k + 1].t < t) k += 1;
  const a = keys[k];
  const b = keys[k + 1];
  const ease = EASINGS[track.easing || 'linear'];
  if (!ease) throw new Error(`unknown easing '${track.easing}'`);
  const u = ease((t - a.t) / (b.t - a.t));
  return a.value.map((v, i) => v + (b.value[i] - v) * u);
}

function targetOf(id) {
  if (id === 'camera') return camera;
  const target = named.get(id);
  if (!target) throw new Error(`track for unknown object '${id}'`);
  return target;
}

function applyTimeline(t) {
  for (const track of description.timeline.tracks) {
    setVector(targetOf(track.target), track.property, trackValue(track, t));
  }
  camera.lookAt(vec(camera.userData.lookAt));
  camera.updateMatrixWorld();
}

// The hook for guide passes (Step 301: depth, outline, mask): only 'normal' exists now.
function applyDrawMode(mode) {
  if (!DRAW_MODES.includes(mode)) throw new Error(`unknown draw mode '${mode}'`);
}

function load(desc) {
  if (desc.version !== DESCRIPTION_VERSION) {
    throw new Error(`scene description version ${desc.version}; this page reads ${DESCRIPTION_VERSION}`);
  }
  description = desc;
  const canvas = document.getElementById('stage');
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true, alpha: false });
  renderer.setPixelRatio(1);
  renderer.setSize(desc.width, desc.height, false);
  scene = new THREE.Scene();
  scene.background = new THREE.Color(desc.background);
  const cam = desc.camera;
  const aspect = desc.width / desc.height;
  camera = new THREE.PerspectiveCamera(verticalFov(cam.fov, aspect), aspect, cam.near, cam.far);
  camera.name = 'camera';
  setVector(camera, 'position', cam.position);
  setVector(camera, 'look_at', cam.look_at);
  named.clear();
  desc.lights.forEach(addLight);
  desc.objects.forEach(addObject);
  applyDrawMode(desc.draw_mode);
  return { three: THREE.REVISION };
}

// Draw the frame at t seconds and return it as a PNG data URL.
function frame(t) {
  applyTimeline(t);
  renderer.render(scene, camera);
  return renderer.domElement.toDataURL('image/png');
}

window.vidgen3d = { load, frame };
