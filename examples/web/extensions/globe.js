// A small planet in three.js, written by hand: `import * as THREE from "three"` loads the
// three.js vidgen ships (no download). Oceans, land and ice caps in the theme's colours, lit by a
// sun; clouds drift round it. The camera follows the narration: it rises over the north pole on
// the second beat and comes back on the third, eased between beats. The canvas is transparent,
// so the video's background shows behind the planet.
import * as THREE from "three";

let renderer, scene, camera, planet, clouds;

// A smooth, repeatable noise on the sphere (no Math.random needed): sums of sines.
function landNoise(v) {
  return Math.sin(v.x * 3.1 + 1.7) * Math.cos(v.y * 2.3 - 0.4) + 0.6 * Math.sin(v.z * 4.3 + v.x * 1.9) + 0.35 * Math.sin(v.y * 7.1 + v.z * 5.3);
}

function makePlanet(theme) {
  // A low-poly sphere: every triangle one colour (from the noise at its centre), land raised a
  // little; positions are displaced by the noise at each corner, so the surface stays closed.
  const geometry = new THREE.IcosahedronGeometry(1, 9);
  const position = geometry.attributes.position;
  const colors = new Float32Array(position.count * 3);
  const deep = new THREE.Color(theme.colors.primary).multiplyScalar(0.5);
  const shallow = new THREE.Color(theme.colors.primary).multiplyScalar(0.8);
  const land = new THREE.Color(theme.colors.tertiary);
  const ice = new THREE.Color(theme.colors.text);
  const v = new THREE.Vector3();
  const centre = new THREE.Vector3();
  for (let i = 0; i < position.count; i++) {
    v.fromBufferAttribute(position, i);
    position.setXYZ(i, ...v.multiplyScalar(1 + 0.03 * Math.max(0, landNoise(v) - 0.5)).toArray());
  }
  for (let f = 0; f < position.count; f += 3) {
    centre.set(0, 0, 0);
    for (let k = 0; k < 3; k++) centre.add(v.fromBufferAttribute(position, f + k));
    centre.normalize();
    const n = landNoise(centre);
    const tone = Math.abs(centre.y) > 0.84 ? ice : n > 0.5 ? land : n > 0.25 ? shallow : deep;
    for (let k = 0; k < 3; k++) tone.toArray(colors, (f + k) * 3);
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geometry.computeVertexNormals();
  const material = new THREE.MeshStandardMaterial({vertexColors: true, flatShading: true, roughness: 0.8, metalness: 0});
  return new THREE.Mesh(geometry, material);
}

function makeClouds(theme) {
  const group = new THREE.Group();
  const material = new THREE.MeshStandardMaterial({color: theme.colors.text, roughness: 1, flatShading: true});
  const puff = new THREE.IcosahedronGeometry(0.06, 1);
  for (let i = 0; i < 22; i++) {
    const cloud = new THREE.Group();
    for (let k = 0; k < 4; k++) {
      const m = new THREE.Mesh(puff, material);
      m.position.set(k * 0.05 - 0.075, Math.sin(k * 2.1) * 0.015, 0);
      m.scale.setScalar(0.8 + 0.3 * Math.sin(i + k));
      cloud.add(m);
    }
    const lat = Math.sin(i * 2.399) * 1.1, lon = i * 2.399;   // spread evenly (golden angle)
    cloud.position.setFromSphericalCoords(1.09, Math.PI / 2 - lat * 0.62, lon);
    cloud.lookAt(0, 0, 0);
    group.add(cloud);
  }
  return group;
}

export function load(ctx) {
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: true, alpha: true});
  renderer.setSize(ctx.width, ctx.height, false);
  renderer.setClearColor(0x000000, 0);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(ctx.orientation === "portrait" ? 40 : 30, ctx.width / ctx.height, 0.1, 50);
  scene.add(new THREE.HemisphereLight(ctx.theme.colors.text, ctx.theme.background, 0.35));
  const sun = new THREE.DirectionalLight(0xffffff, 3.2);
  sun.position.set(-4, 2, 3);
  scene.add(sun);
  planet = makePlanet(ctx.theme);
  planet.rotation.z = 0.41;   // Earth's tilt, 23.4 degrees
  scene.add(planet);
  clouds = makeClouds(ctx.theme);
  scene.add(clouds);
}

const smooth = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));

// How far over the pole the camera is at t: 0 on beat 1, 1 on beat 2, back to 0 on beat 3.
function overPole(t, ctx) {
  const [, second, third] = ctx.beats;
  if (!second) return 0;
  const up = smooth((t - second.start + 0.3) / 1.4);
  const down = third ? smooth((t - third.start + 0.3) / 1.4) : 0;
  return up - down;
}

export function frame(t, ctx) {
  planet.rotation.y = t * 0.35;
  clouds.rotation.y = t * 0.47;
  clouds.rotation.x = 0.41;
  const lift = overPole(t, ctx) * 1.05;   // radians above the equator
  const distance = 6.4;
  camera.position.set(0, Math.sin(lift) * distance, Math.cos(lift) * distance);
  camera.lookAt(0, ctx.orientation === "portrait" ? 0 : -0.1, 0);
  renderer.render(scene, camera);
}
