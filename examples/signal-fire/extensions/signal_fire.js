// Signal Fire: a ring of standing stones around a brazier at night, lit by the score
// (assets/music/signal_fire.yaml). No JSON beside the page and no script that measures the music:
// every scene has `music_data` in its params, so `ctx.music` holds the video's music measured per
// frame and the score's hits and notes in song time (`vidgen guide web`, "Pictures that follow the
// music"). The picture is finished by vidgen's module `vidgen/three-finish`.
//
// What follows what (T is song time, `ctx.music.time(t)`):
//   solo, cellos  each note sends up embers from the brazier (brighter when louder)
//   choir         the sky glows while the choir sings, as loud as its hairpins make it
//   timpani       a ring of light on the ground: a pulse per blow, growing through the roll
//   taiko         the stones flash and a shock ring runs over the ground on every hit
//   horns, low    the fire grows with the brass; the low brass swell lifts its light
//   trumpet       a beam of light from the brazier whose height follows the melody's pitch
//   crash, gong   a warm flash over the frame (three-finish's `flash`); the gong a slow one
//   sections      the camera's path and the grade (cool embers, warm fire) follow the form
// Hits change light and colour only; the camera moves slowly and never on a beat.
//
// update(t) sets the whole scene from t and keeps no state between frames.
import * as THREE from "three";
import {Finish} from "vidgen/three-finish";
import {smoothstep, eventLevel, signalLevel} from "vidgen/music-time";
import {softDotTexture} from "vidgen/three-kit";

const STONES = 9, EMBERS = 240, WAVES = 4;
// the stones', flames' and stars' own seeded numbers (not music-time's hash, which would move every stone)
const hash = (n) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };

let M, finish, camera, brazier, flames = [], beam, ring, waves = [], stones = [], embers, skyUniforms, fireLight;

function update(t) {
  const T = M.time(t);

  // the camera: low inside the ring among the embers, turning and rising a little while the music
  // gathers, then lifted over the stones and drawn back for the fire; a function of song time, so
  // the cuts between the scenes do not show
  const turn = 0.3 + 0.9 * smoothstep(2, 24, T);
  const height = 1.1 + 1.0 * smoothstep(8, 16, T) + 3.5 * smoothstep(15, 22, T);
  const distance = 3.4 - 0.4 * smoothstep(0, 8, T) + 6 * smoothstep(16.5, 24.5, T);
  camera.position.set(Math.sin(turn) * distance, height, Math.cos(turn) * distance);
  camera.lookAt(0, 1.2 + 0.6 * smoothstep(15.5, 24.5, T), 0);

  // the fire: grows with the music's level and the brass, flickers on its own (sines of T, no randomness)
  const brass = Math.max(signalLevel(M, "horns", T), 1.2 * signalLevel(M, "low", T));
  const size = 0.4 + 0.35 * M.level(T) + 0.35 * Math.min(1.5, brass);
  flames.forEach((f, i) => {
    const flicker = 1 + 0.25 * Math.sin(T * (5.3 + i * 1.9) + i * 2.1) + 0.15 * Math.sin(T * (11.7 + i * 2.9) + i);
    const tall = size * flicker * (0.8 + 0.5 * hash(i + 70));
    f.scale.set(Math.sqrt(size), tall, Math.sqrt(size));
    f.position.y = 1.0 + tall * 0.5;
  });
  fireLight.intensity = 1.5 + 4 * size;

  // embers: three for every note of the solo violin and the cellos in the last 3.5 s
  const pos = embers.geometry.attributes.position, col = embers.geometry.attributes.color;
  let k = 0;
  for (const track of ["solo", "cellos"]) {
    for (const e of M.notes(track, T - 3.5, T + 1e-6)) {
      const strength = Math.min(1.6, eventLevel(e, e.time)) * (track === "solo" ? 1.3 : 1);
      for (let j = 0; j < 3 && k < EMBERS; j++, k++) {
        const seed = e.index * 7 + j * 131 + (track === "solo" ? 9001 : 0);
        const age = T - e.time, a = hash(seed) * Math.PI * 2, r = 0.15 + 0.35 * hash(seed + 1) * age;
        pos.setXYZ(k, Math.cos(a + age * 0.8) * r, 1.3 + age * (0.35 + 0.35 * hash(seed + 2)), Math.sin(a + age * 0.8) * r);
        const glow = strength * Math.max(0, 1 - age / 3.5) * 5;
        col.setXYZ(k, glow, glow * 0.45, glow * 0.12);
      }
    }
  }
  for (; k < EMBERS; k++) { pos.setXYZ(k, 0, -10, 0); col.setXYZ(k, 0, 0, 0); }
  pos.needsUpdate = col.needsUpdate = true;

  // the timpani's ring of light: each blow a pulse, a roll lighting it as loud as its hairpin has grown
  const roll = M.sounding("timpani", T).filter((e) => e.stroke === "roll");
  const drum = roll.length ? 0.6 * eventLevel(roll[0], T) : 0;
  ring.material.color.setRGB(1.0, 0.45, 0.15).multiplyScalar(0.2 + 1.6 * Math.max(drum, M.pulse("timpani", 0.35, T)));

  // taiko: the stones flash, and a shock ring runs outwards from each of the last few hits
  const flash = M.pulse("taiko", 0.22, T);
  stones.forEach((s) => s.material.emissiveIntensity = 0.02 + 0.5 * flash);
  const hits = M.hits("taiko", T - 1.4, T + 1e-6).slice(-WAVES);
  waves.forEach((w, i) => {
    const e = hits[i];
    w.visible = !!e;
    if (!e) return;
    const age = T - e.time;
    w.scale.setScalar(0.6 + age * 9);
    w.material.color.setRGB(1, 0.6, 0.3).multiplyScalar(e.strength * 0.9 * Math.max(0, 1 - age / 1.4));
  });

  // trumpet: a beam whose height follows the pitch, gliding as the slurred line glides
  const notes = M.notes("trumpet", T - 30, T + 1e-6);
  const cur = notes[notes.length - 1], prev = notes[notes.length - 2];
  if (cur) {
    const h = (p) => 2.5 + (p - 60) * 0.42;
    const height = prev && cur.slur ? THREE.MathUtils.lerp(h(prev.pitch), h(cur.pitch), smoothstep(0, 1, (T - cur.time + 0.12) / 0.24)) : h(cur.pitch);
    beam.scale.set(1, height, 1);
    beam.position.y = 1.2 + height / 2;
    beam.material.color.setRGB(1, 0.85, 0.6).multiplyScalar(0.9 * signalLevel(M, "trumpet", T, 0.8));
    beam.visible = true;
  } else beam.visible = false;

  // the sky: the choir's glow over the horizon, the band of the voices' range in the measured mix
  skyUniforms.uGlow.value = 0.9 * signalLevel(M, "choir", T, 1.5) + 0.6 * M.band(Math.floor(M.bandCount * 0.45), T);
  skyUniforms.uWarm.value = smoothstep(14, 18, T);
}

export function load(ctx) {
  M = ctx.music;
  const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x05070d, 0.035);
  camera = new THREE.PerspectiveCamera(38, ctx.width / ctx.height, 0.1, 200);

  // the sky: a gradient dome with a glow band over the horizon (the choir) and seeded stars
  skyUniforms = {uGlow: {value: 0}, uWarm: {value: 0}};
  const sky = new THREE.Mesh(new THREE.SphereGeometry(90, 32, 16), new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false, uniforms: skyUniforms,
    vertexShader: "varying vec3 vDir; void main() { vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: `uniform float uGlow; uniform float uWarm; varying vec3 vDir;
      void main() {
        float h = clamp(vDir.y, -0.2, 1.0);
        vec3 night = mix(vec3(0.012, 0.018, 0.04), vec3(0.002, 0.003, 0.01), smoothstep(0.0, 0.7, h));
        vec3 glowCol = mix(vec3(0.25, 0.35, 0.8), vec3(1.0, 0.45, 0.15), uWarm);
        float band = exp(-pow((h - 0.06) / 0.12, 2.0));
        gl_FragColor = vec4(night + glowCol * band * uGlow * 0.18, 1.0);
      }`,
  }));
  scene.add(sky);
  const starPos = [];
  for (let i = 0; i < 700; i++) {
    const a = hash(i) * Math.PI * 2, y = 0.08 + 0.92 * hash(i + 0.5);
    const r = Math.sqrt(1 - y * y) * 80;
    starPos.push(Math.cos(a) * r, y * 80, Math.sin(a) * r);
  }
  const starGeo = new THREE.BufferGeometry();
  starGeo.setAttribute("position", new THREE.Float32BufferAttribute(starPos, 3));
  scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({color: 0x9fb4ff, size: 1.6, sizeAttenuation: false, fog: false})));

  // the ground, the stones and the brazier
  const ground = new THREE.Mesh(new THREE.CircleGeometry(60, 48), new THREE.MeshStandardMaterial({color: 0x0e0f12, roughness: 0.95}));
  ground.rotation.x = -Math.PI / 2; scene.add(ground);
  for (let i = 0; i < STONES; i++) {
    const a = (i / STONES) * Math.PI * 2 + 0.2, h = 1.7 + 1.1 * hash(i + 20);
    const stone = new THREE.Mesh(new THREE.BoxGeometry(0.75 + 0.3 * hash(i + 30), h, 0.45 + 0.2 * hash(i + 40)),
      new THREE.MeshStandardMaterial({color: 0x5a5e66, roughness: 0.85, emissive: new THREE.Color(1.0, 0.42, 0.12), emissiveIntensity: 0.05}));
    stone.position.set(Math.cos(a) * 4.3, h / 2, Math.sin(a) * 4.3);
    stone.rotation.y = -a + 0.3 * (hash(i + 50) - 0.5);
    stone.rotation.z = 0.08 * (hash(i + 60) - 0.5);
    scene.add(stone); stones.push(stone);
  }
  brazier = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.32, 1.0, 24), new THREE.MeshStandardMaterial({color: 0x2a2522, metalness: 0.7, roughness: 0.45}));
  brazier.position.y = 0.5; scene.add(brazier);
  const additive = (r, g, b) => new THREE.MeshBasicMaterial({color: new THREE.Color(r, g, b), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, fog: false});
  for (let i = 0; i < 7; i++) {   // seven thin tongues of flame around the middle, the inner ones whiter
    const a = (i / 7) * Math.PI * 2, r = i === 0 ? 0 : 0.16 + 0.06 * hash(i + 80), hot = i === 0 ? 1 : 0.55;
    const f = new THREE.Mesh(new THREE.ConeGeometry(0.11 + 0.05 * hash(i + 90), 1.0, 10, 1, true), additive(0.9, 0.34 + 0.24 * hot, 0.06 + 0.16 * hot));
    f.geometry.translate(Math.cos(a) * r, 0, Math.sin(a) * r);
    scene.add(f); flames.push(f);
  }
  fireLight = new THREE.PointLight(0xff9a50, 10, 0, 2);
  fireLight.position.set(0, 1.8, 0); scene.add(fireLight);
  scene.add(new THREE.HemisphereLight(0x2a3a66, 0x050505, 0.35));

  // the timpani's ring, the taiko's shock rings, the trumpet's beam, the embers
  ring = new THREE.Mesh(new THREE.RingGeometry(5.0, 5.25, 96), additive(1, 0.45, 0.15));
  ring.rotation.x = -Math.PI / 2; ring.position.y = 0.02; scene.add(ring);
  for (let i = 0; i < WAVES; i++) {
    const w = new THREE.Mesh(new THREE.RingGeometry(0.95, 1.0, 96), additive(1, 0.6, 0.3));
    w.rotation.x = -Math.PI / 2; w.position.y = 0.03; scene.add(w); waves.push(w);
  }
  beam = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.09, 1, 16, 1, true), additive(1, 0.85, 0.6));
  scene.add(beam);
  const emberGeo = new THREE.BufferGeometry();
  emberGeo.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(EMBERS * 3), 3));
  emberGeo.setAttribute("color", new THREE.Float32BufferAttribute(new Float32Array(EMBERS * 3), 3));
  embers = new THREE.Points(emberGeo, new THREE.PointsMaterial({size: 0.14, map: softDotTexture(32, [0.4, 0.5]),   // a soft round spark, not a square point
    vertexColors: true, transparent: true,
    blending: THREE.AdditiveBlending, depthWrite: false, fog: false}));
  embers.frustumCulled = false;
  scene.add(embers);

  const draft = ctx.width < 640;
  finish = new Finish(renderer, scene, camera, ctx, {
    update,
    bloom: {strength: 0.2, radius: 0.2, threshold: 1.2, scale: draft ? 0.25 : 0.5},
    toneMapping: "aces",
    // cool and blue among the embers, warm once the fire is lit
    grade: (t) => { const w = smoothstep(14, 18, M.time(t)); return {temperature: -0.18 + 0.36 * w, saturation: 0.95 + 0.15 * w, contrast: 1.05}; },
    vignette: 0.4,
    grain: 0.025,
    // the crash and the gong: a warm flash over the frame, the gong's slower and fainter
    flash: (t) => { const T = M.time(t); return {amount: 0.18 * M.pulse("crash", 0.5, T) + 0.06 * M.pulse("gong", 1.8, T), color: [1, 0.6, 0.3]}; },
    dof: draft ? false : {focus: brazier, fStop: 2.8, unit: 0.3, maxBlur: 8, quality: "low"},
  });
  finish.warmUp(0);
}

export function frame(t) {
  finish.render(t);
}
