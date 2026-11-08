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

const SEGMENTS = 48;
// The font of labels (vidgen's bundled Inter Bold, served with the page): the same text on every machine.
const LABEL_FONT = 'vidgen-label';
const LABEL_PX = 96;          // canvas pixels of a label's text height
const LABEL_PAD = 0.35;       // padding around the text, in text heights

// A mesh's geometry: unit shapes scaled to the object's size in the geometry itself, so the
// object's own scale stays 1 and its children keep their size.
function geometry(obj) {
  const [w, h, d] = obj.size;
  let g;
  if (obj.shape === 'box') {
    return new THREE.BoxGeometry(w, h, d);
  } else if (obj.shape === 'sphere') {
    g = new THREE.SphereGeometry(0.5, SEGMENTS, SEGMENTS / 2);
  } else if (obj.shape === 'cylinder') {
    g = new THREE.CylinderGeometry(0.5, 0.5, 1, SEGMENTS);
  } else if (obj.shape === 'cone') {
    g = new THREE.ConeGeometry(0.5, 1, SEGMENTS);
  } else if (obj.shape === 'torus') {
    // outer width w, thickness h, lying flat (the ring in the x-z plane); depth d by scaling
    const tube = h / 2;
    g = new THREE.TorusGeometry(w / 2 - tube, tube, SEGMENTS / 2, SEGMENTS * 2);
    g.rotateX(-Math.PI / 2);
    g.scale(1, 1, d / w);
    return g;
  } else if (obj.shape === 'plane') {
    g = new THREE.PlaneGeometry(w, d);
    g.rotateX(-Math.PI / 2);   // facing up
    return g;
  } else {
    throw new Error(`unknown shape '${obj.shape}'`);
  }
  g.scale(w, h, d);
  return g;
}

function material(obj) {
  const side = obj.shape === 'plane' ? THREE.DoubleSide : THREE.FrontSide;
  return new THREE.MeshLambertMaterial({ color: obj.color, side });
}

// An arrow along +y, centred: a shaft and a cone head, size [thickness, length, thickness].
function arrow(obj) {
  const [t, length] = obj.size;
  const head = Math.min(3.5 * t, 0.45 * length);
  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(t / 2, t / 2, length - head, SEGMENTS / 2), material(obj));
  shaft.position.y = -head / 2;
  const tip = new THREE.Mesh(new THREE.ConeGeometry(1.25 * t, head, SEGMENTS / 2), material(obj));
  tip.position.y = length / 2 - head / 2;
  const group = new THREE.Group();
  group.add(shaft, tip);
  return group;
}

// A label: its text on a rounded plate, always facing the camera, size = the text's height.
function label(obj) {
  const font = `bold ${LABEL_PX}px ${LABEL_FONT}`;
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  ctx.font = font;
  const pad = LABEL_PAD * LABEL_PX;
  canvas.width = Math.ceil(ctx.measureText(obj.text).width + 2 * pad);
  canvas.height = Math.ceil(LABEL_PX * 1.25 + 2 * pad);
  ctx.font = font;
  ctx.globalAlpha = obj.plate_opacity;
  ctx.fillStyle = obj.plate;
  ctx.beginPath();
  ctx.roundRect(0, 0, canvas.width, canvas.height, pad);
  ctx.fill();
  ctx.globalAlpha = 1;
  ctx.fillStyle = obj.color;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(obj.text, canvas.width / 2, canvas.height / 2);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true }));
  const height = obj.size[1] * canvas.height / LABEL_PX;
  sprite.scale.set(height * canvas.width / canvas.height, height, 1);
  return sprite;
}

function build(obj) {
  if (obj.shape === 'group') return new THREE.Group();
  if (obj.shape === 'arrow') return arrow(obj);
  if (obj.shape === 'label') return label(obj);
  return new THREE.Mesh(geometry(obj), material(obj));
}

// Objects come parents first; a child's position and rotation are in its parent's frame.
function addObject(obj) {
  const node = build(obj);
  node.name = obj.id;
  node.userData.id = obj.id;
  node.traverse((part) => { part.userData.id = obj.id; });
  setVector(node, 'position', obj.position);
  setVector(node, 'rotation', obj.rotation);
  if (obj.parent) {
    const parent = named.get(obj.parent);
    if (!parent) throw new Error(`object '${obj.id}': unknown parent '${obj.parent}'`);
    parent.add(node);
  } else {
    scene.add(node);
  }
  named.set(obj.id, node);
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

async function loadFont() {
  const face = new FontFace(LABEL_FONT, 'url(inter-bold.ttf)');
  await face.load();
  document.fonts.add(face);
}

async function load(desc) {
  if (desc.version !== DESCRIPTION_VERSION) {
    throw new Error(`scene description version ${desc.version}; this page reads ${DESCRIPTION_VERSION}`);
  }
  description = desc;
  if (desc.objects.some((o) => o.shape === 'label')) await loadFont();
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
