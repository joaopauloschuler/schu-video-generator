// vidgen's 3D page (DESIGN.md §114): builds a three.js scene from vidgen's scene description
// (JSON, version 1: shapes, labels, groups, stand-ins; tracks of position, rotation, scale,
// opacity, emissive glow, arrow length and the camera) and draws the frame at a time vidgen
// gives, as it looks or as a guide pass (depth, outline, mask). Time comes only from frame(t):
// no requestAnimationFrame, no clock, no randomness, so the same description gives the same
// pixels.
import * as THREE from './three.module.js';

const DESCRIPTION_VERSION = 1;
const DRAW_MODES = ['normal', 'depth', 'outline', 'mask'];

let renderer = null;
let scene = null;
let camera = null;
let description = null;
let outline = null;        // the outline pass's buffers and edge shader
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

// An arrow along +y, centred: a shaft and a cone head, size [thickness, length, thickness]. Both
// parts are unit-high meshes stretched to their length, so a `length` track can change it.
function arrow(obj) {
  const t = obj.size[0];
  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(t / 2, t / 2, 1, SEGMENTS / 2), material(obj));
  const tip = new THREE.Mesh(new THREE.ConeGeometry(1.25 * t, 1, SEGMENTS / 2), material(obj));
  const group = new THREE.Group();
  group.add(shaft, tip);
  group.userData.setLength = (length) => {
    const head = Math.min(3.5 * t, 0.45 * length);
    shaft.scale.y = length - head;
    shaft.position.y = -head / 2;
    tip.scale.y = head;
    tip.position.y = length / 2 - head / 2;
  };
  group.userData.setLength(obj.size[1]);
  return group;
}

// A character stand-in: a capsule (size [width, height, depth]) with a nose on its front (+z)
// showing where it faces, and its name above its head.
function standin(obj) {
  const [w, h, d] = obj.size;
  const r = Math.min(w, d) / 2;
  const body = new THREE.CapsuleGeometry(r, Math.max(h - 2 * r, 0), 8, SEGMENTS);
  body.scale(w / (2 * r), 1, d / (2 * r));
  const group = new THREE.Group();
  group.add(new THREE.Mesh(body, material(obj)));
  const nose = new THREE.ConeGeometry(0.22 * w, 0.55 * w, SEGMENTS / 2);
  nose.rotateX(Math.PI / 2);   // pointing +z
  const noseMesh = new THREE.Mesh(nose, new THREE.MeshLambertMaterial({ color: obj.nose }));
  noseMesh.position.set(0, 0.28 * h, d / 2 + 0.2 * w);
  group.add(noseMesh);
  if (obj.name) {
    const tag = label({ text: obj.name, size: [0, obj.name_size, 0], color: obj.name_color, plate: obj.plate, plate_opacity: obj.plate_opacity });
    tag.position.y = h / 2 + obj.name_gap + obj.name_size;
    group.add(tag);
  }
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
  // screen_size: the size it has at the start, wherever the camera goes (three.js then
  // multiplies the scale by the depth, so divide by the depth at the start)
  const depth = obj.screen_depth || 1;
  if (obj.screen_depth) sprite.material.sizeAttenuation = false;
  const height = obj.size[1] * canvas.height / LABEL_PX / depth;
  sprite.scale.set(height * canvas.width / canvas.height, height, 1);
  return sprite;
}

function build(obj) {
  if (obj.shape === 'group') return new THREE.Group();
  if (obj.shape === 'arrow') return arrow(obj);
  if (obj.shape === 'label') return label(obj);
  if (obj.shape === 'standin') return standin(obj);
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
  node.userData.opacity = obj.opacity ?? 1;
  node.userData.emissive = [0, 0, 0];
  node.userData.parentId = obj.parent || null;
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
  } else if (property === 'scale') {
    target.scale.set(value[0], value[1], value[2]);
  } else if (property === 'opacity') {
    target.userData.opacity = value[0];
  } else if (property === 'emissive') {
    target.userData.emissive = value;
  } else if (property === 'length') {
    if (!target.userData.setLength) throw new Error(`'${target.name}' is not an arrow; it has no length`);
    target.userData.setLength(value[0]);
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

// Opacity and glow of each object: its own times its parents' (opacity) or the brightest of
// them (glow), set on the materials of its own parts; an object at opacity 0 is not drawn.
function applyLooks() {
  const looks = new Map();
  for (const obj of description.objects) {
    const node = named.get(obj.id);
    const parent = looks.get(node.userData.parentId);
    const own = node.userData.emissive;
    const look = {
      opacity: node.userData.opacity * (parent ? parent.opacity : 1),
      emissive: parent ? own.map((c, i) => Math.max(c, parent.emissive[i])) : own,
    };
    looks.set(obj.id, look);
    if (description.draw_mode !== 'normal') {
      // a guide pass: flat, no fading or glow; shown from half opacity, labels never
      node.visible = look.opacity >= 0.5 && !node.isSprite;
      continue;
    }
    node.visible = look.opacity > 0;
    node.traverse((part) => {
      if (part.userData.id !== obj.id || !part.material) return;
      const m = part.material;
      const fading = look.opacity < 1 || part.isSprite;
      if (m.transparent !== fading) { m.transparent = fading; m.needsUpdate = true; }
      m.opacity = look.opacity;
      m.depthWrite = look.opacity >= 1;
      if (m.emissive) m.emissive.setRGB(look.emissive[0], look.emissive[1], look.emissive[2], THREE.SRGBColorSpace);
    });
  }
}

function applyTimeline(t) {
  for (const track of description.timeline.tracks) {
    setVector(targetOf(track.target), track.property, trackValue(track, t));
  }
  applyLooks();
  camera.lookAt(vec(camera.userData.lookAt));
  camera.updateMatrixWorld();
}

// ----- guide passes (DESIGN.md §114.14) -----------------------------------------------------
// Every part of every object gets the pass's own flat material (no light); labels and name tags
// are hidden. Values are written as they are (no colour conversion), so a mask colour or a depth
// grey reaches the PNG exactly.

const PASS_VERTEX = `
varying vec3 vNormal;
varying float vDepth;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vNormal = normalMatrix * normal;
  vDepth = -mv.z;
  gl_Position = projectionMatrix * mv;
}`;

// depth: near (depth_range[0]) white, far (depth_range[1]) black, linear in the distance along the view
const DEPTH_FRAGMENT = `
uniform float near;
uniform float far;
varying float vDepth;
void main() {
  float v = clamp((far - vDepth) / (far - near), 0.0, 1.0);
  gl_FragColor = vec4(vec3(v), 1.0);
}`;

const MASK_FRAGMENT = `
uniform vec3 color;
void main() { gl_FragColor = vec4(color, 1.0); }`;

// outline, first step: the view-space normal and depth (channel 0) or the object's number (channel 1)
const GBUFFER_FRAGMENT = `
uniform float channel;
uniform float objectId;
varying vec3 vNormal;
varying float vDepth;
void main() {
  vec3 n = normalize(vNormal) * (gl_FrontFacing ? 1.0 : -1.0);
  gl_FragColor = channel < 0.5 ? vec4(n, vDepth) : vec4(objectId, 0.0, 0.0, 1.0);
}`;

const QUAD_VERTEX = `
varying vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

// outline, second step: black where the object changes (its silhouette), where the surface
// bends sharply (a crease: normals more than ~37 degrees apart) or where an object hides part of
// itself (a step in depth: 1 / depth is linear across a flat face, so its second difference is 0)
const EDGE_FRAGMENT = `
uniform sampler2D tNormal;
uniform sampler2D tId;
uniform vec2 texel;
varying vec2 vUv;
const float NORMAL_COS = 0.8;
const float DEPTH_STEP = 0.02;
float idAt(vec2 o) { return texture2D(tId, vUv + o).r; }
vec4 gAt(vec2 o) { return texture2D(tNormal, vUv + o); }
void main() {
  vec2 dx = vec2(texel.x, 0.0);
  vec2 dy = vec2(0.0, texel.y);
  float id = idAt(vec2(0.0));
  bool edge = idAt(dx) != id || idAt(-dy) != id;
  if (!edge && id > 0.5) {
    vec4 c = gAt(vec2(0.0));
    vec4 r = gAt(dx);
    vec4 b = gAt(-dy);
    edge = dot(c.xyz, r.xyz) < NORMAL_COS || dot(c.xyz, b.xyz) < NORMAL_COS;
    if (!edge && idAt(-dx) == id && idAt(dy) == id) {
      float ic = 1.0 / c.w;
      float sx = abs(1.0 / gAt(-dx).w + 1.0 / r.w - 2.0 * ic);
      float sy = abs(1.0 / gAt(dy).w + 1.0 / b.w - 2.0 * ic);
      edge = max(sx, sy) > DEPTH_STEP * ic;
    }
  }
  gl_FragColor = vec4(vec3(edge ? 0.0 : 1.0), 1.0);
}`;

function rgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return new THREE.Vector3(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255);
}

function passMaterial(desc, obj, number, side, channel) {
  const mode = desc.draw_mode;
  if (mode === 'depth') {
    const [near, far] = desc.depth_range;
    return new THREE.ShaderMaterial({ vertexShader: PASS_VERTEX, fragmentShader: DEPTH_FRAGMENT, side, uniforms: { near: { value: near }, far: { value: far } } });
  }
  if (mode === 'mask') {
    const color = desc.mask_colors[obj.id];
    if (!color) throw new Error(`mask: no colour for object '${obj.id}'`);
    return new THREE.ShaderMaterial({ vertexShader: PASS_VERTEX, fragmentShader: MASK_FRAGMENT, side, uniforms: { color: { value: rgb(color) } } });
  }
  return new THREE.ShaderMaterial({ vertexShader: PASS_VERTEX, fragmentShader: GBUFFER_FRAGMENT, side, uniforms: { channel, objectId: { value: number } } });
}

// The outline pass's buffers (float, one value per pixel, no filtering) and its edge shader on a
// quad covering the frame; lines are about 1 px per 540 px of the shorter side.
function outlineBuffers(width, height) {
  const options = { type: THREE.FloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: true };
  const geometryBuffer = new THREE.WebGLRenderTarget(width, height, options);
  const idBuffer = new THREE.WebGLRenderTarget(width, height, options);
  const px = Math.max(1, Math.round(Math.min(width, height) / 540));
  const edges = new THREE.ShaderMaterial({
    vertexShader: QUAD_VERTEX, fragmentShader: EDGE_FRAGMENT, depthTest: false, depthWrite: false,
    uniforms: { tNormal: { value: geometryBuffer.texture }, tId: { value: idBuffer.texture }, texel: { value: new THREE.Vector2(px / width, px / height) } },
  });
  const quad = new THREE.Scene();
  quad.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), edges));
  return { geometryBuffer, idBuffer, quad, quadCamera: new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1), channel: { value: 0 } };
}

function applyDrawMode(desc) {
  const mode = desc.draw_mode;
  if (!DRAW_MODES.includes(mode)) throw new Error(`unknown draw mode '${mode}'`);
  if (mode === 'normal') return;
  if (mode === 'depth' && !desc.depth_range) throw new Error('depth pass without depth_range');
  if (mode === 'mask' && !desc.mask_colors) throw new Error('mask pass without mask_colors');
  if (mode === 'outline') outline = outlineBuffers(desc.width, desc.height);
  scene.background = mode === 'outline' ? null : new THREE.Color(0, 0, 0);
  desc.objects.forEach((obj, k) => {
    named.get(obj.id).traverse((part) => {
      if (part.userData.id !== obj.id) return;
      if (part.isSprite) { part.visible = false; return; }
      if (!part.isMesh) return;
      part.material = passMaterial(desc, obj, k + 1, part.material.side, outline && outline.channel);
    });
  });
}

function renderOutline() {
  renderer.setClearColor(0x000000, 0);
  for (const [channel, target] of [[0, outline.geometryBuffer], [1, outline.idBuffer]]) {
    outline.channel.value = channel;
    renderer.setRenderTarget(target);
    renderer.clear();
    renderer.render(scene, camera);
  }
  renderer.setRenderTarget(null);
  renderer.render(outline.quad, outline.quadCamera);
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
  if (desc.objects.some((o) => o.shape === 'label' || o.name)) await loadFont();
  const canvas = document.getElementById('stage');
  // guide passes without antialiasing: a mask colour or a depth grey is never blended at an edge
  const antialias = desc.draw_mode === 'normal';
  renderer = new THREE.WebGLRenderer({ canvas, antialias, preserveDrawingBuffer: true, alpha: false });
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
  outline = null;
  desc.lights.forEach(addLight);
  desc.objects.forEach(addObject);
  applyDrawMode(desc);
  return { three: THREE.REVISION };
}

// Draw the frame at t seconds and return it as a PNG data URL.
function frame(t) {
  applyTimeline(t);
  if (outline) renderOutline();
  else renderer.render(scene, camera);
  return renderer.domElement.toDataURL('image/png');
}

window.vidgen3d = { load, frame };
