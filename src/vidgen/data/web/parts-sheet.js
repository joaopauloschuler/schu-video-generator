// The page `vidgen parts` draws its contact sheet with (DESIGN.md §122.5): frame n builds part n of
// ctx.data.names in a scene of its own (vidgen/parts' default camera and light), sets it to its time
// `at` and draws it, through vidgen/three-finish (bloom, ACES; no grain) unless the part says
// {finish: false}. The previous part is taken down first: one browser, one renderer, every part.
import * as THREE from "three";
import {Finish} from "vidgen/three-finish";
import {buildPart, defaultStage, part} from "vidgen/parts";

let renderer = null, names = [], shown = null;

export async function load(ctx) {
  for (const file of ctx.data.files) await import(file);
  names = ctx.data.names;
  names.forEach(part);   // an unknown name stops here, with the closest one
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: true, stencil: true});
  renderer.setSize(ctx.width, ctx.height, false);
}

function takeDown() {
  if (!shown) return;
  shown.scene.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    for (const m of [o.material].flat()) if (m) { for (const v of Object.values(m)) if (v && v.isTexture) v.dispose(); m.dispose(); }
  });
  for (const t of [shown.scene.background, shown.scene.environment]) if (t && t.isTexture) t.dispose();
  if (shown.finish) shown.finish.dispose();
  renderer.renderLists.dispose();
  shown = null;
}

export function frame(t, ctx) {
  takeDown();
  const n = Math.round(t * ctx.fps), p = part(names[n]);
  const stage = {...defaultStage(ctx.width, ctx.height), renderer, width: ctx.width, height: ctx.height, ctx};
  const made = buildPart(p.name, stage);
  if (made.frame) made.frame(p.at);
  shown = {scene: stage.scene, finish: null};
  renderer.setRenderTarget(null);
  if (made.finish === false) {
    renderer.render(stage.scene, stage.camera);
  } else {
    shown.finish = new Finish(renderer, stage.scene, stage.camera, ctx, {grain: 0, bloom: {strength: 0.12, radius: 0, threshold: 1.0, scale: 0.5}});
    shown.finish.render(p.at);
  }
}
