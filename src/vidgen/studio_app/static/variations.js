// Variations (DESIGN.md §94.17): one click makes four siblings of the current version, each a
// different kind of change (harmony, pattern, mix, energy), rendered and checked by the server in
// the background and shown side by side. ▶ plays one at the same moment as what was playing
// (again: back to the current version); Keep makes it the next version; More like this makes
// four variations of it; Shuffle four others of the same version (a counter: reproducible).

import { api } from "./api.js";
import { escapeHtml } from "./yaml_view.js";

const $ = (id) => document.getElementById(id);
const MARK = { ok: "✓", note: "•", fix: "!" };
const KINDS = ["harmony", "pattern", "mix", "energy"];
const POLL_MS = 600;

let ctx = null;
let batch = null;      // the batch shown (the server's document)
let polling = 0;

function setBusy(on) {
  if (on) document.body.dataset.variations = "running";
  else if (batch) document.body.dataset.variations = batch.state;
  else delete document.body.dataset.variations;
}

// The candidate playing, as "b0002/c", or null.
export function auditionId() {
  return ctx?.state.variation ?? null;
}

// Back to the current version (a new version, undo, A/B...): no candidate plays any more.
export function stopAudition(refresh = false) {
  if (!ctx.state.variation) return;
  ctx.state.variation = null;
  ctx.state.variationLabel = null;
  if (batch) draw();
  if (refresh) ctx.refreshAudio();
}

function baseWords(doc) {
  if (doc.base?.batch) return `more like ${doc.base.letter} of ${doc.base.batch}`;
  return `of v${doc.root}`;
}

function cardHtml(item) {
  const id = `${batch.id}/${item.letter}`;
  const playing = ctx.state.variation === id;
  const check = item.check;
  const render = item.render;
  let state;
  if (item.status === "failed") state = `<span class="v-fail">failed: ${escapeHtml(item.error || "")}</span>`;
  else if (check) {
    state = `<span class="v-verdict ${check.level}"><i aria-hidden="true">${MARK[check.level]}</i> ${escapeHtml(check.verdict)}</span>`;
  } else if (item.status === "checking") state = `<span class="dim">checking…</span>`;
  else if (item.status === "rendered") state = `<span class="dim">rendered · check waiting</span>`;
  else if (item.status === "rendering") state = `<span class="dim">rendering…</span>`;
  else state = `<span class="dim">waiting</span>`;
  const nums = check ? check.headline.filter((h) => h.name !== "loudness").map((h) =>
    `<span class="num ${h.level}" title="${escapeHtml(h.title)}"><span class="dim">${escapeHtml(h.name)}</span> ${escapeHtml(h.value)}</span>`).join("") : "";
  let made = "";
  if (render?.cached) made = "from the cache";
  else if (render) {
    const scaled = render.scaled?.length ? ` · ${render.scaled.join(", ")} at the new volume` : "";
    const secs = `${render.render_seconds.toFixed(1)} s`;
    made = render.tracks.length ? `${render.tracks.join(", ")} rendered${scaled}, mixed: ${secs}` : `stems kept${scaled}, mixed in ${secs}`;
  }
  const picture = check
    ? `<img class="v-spectro" src="${escapeHtml(check.image.url)}" alt="Spectrogram of variation ${item.letter}">`
    : `<div class="v-spectro pending" aria-hidden="true"></div>`;
  const ready = Boolean(render) && item.status !== "failed";
  const kept = item.kept != null;
  // the kind's colour comes from a class (the page's CSP allows no inline styles)
  const kind = KINDS.includes(item.kind) ? item.kind : "pattern";
  return `<article class="v-card kind-${kind}${playing ? " playing" : ""}${kept ? " kept" : ""}" data-letter="${item.letter}" data-status="${escapeHtml(item.status)}">
    <header><span class="v-letter">${item.letter}</span><span class="v-kind">${escapeHtml(item.kind)}</span>${kept ? `<span class="v-kept">kept as v${item.kept}</span>` : ""}</header>
    <p class="var-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</p>
    <div class="v-state">${state}</div>
    <div class="v-nums">${nums}</div>
    ${picture}
    <div class="v-made dim">${escapeHtml(made)}</div>
    <div class="v-acts">
      <button class="btn small v-play" data-act="play" aria-pressed="${playing}" ${ready ? "" : "disabled"}
        title="${playing ? "Back to the current version, at the same moment" : "Play this variation at the same moment (click again: back to the current version)"}">${playing ? "■ back" : "▶ Play"}</button>
      <button class="btn small primary v-keep" data-act="keep" ${ready ? "" : "disabled"} title="${kept ? `It is v${item.kept}: make that the current version` : `Make it the next version (its parent: v${batch.root})`}">${kept ? `Go to v${item.kept}` : "Keep"}</button>
      <button class="btn small v-more" data-act="more" title="Four new variations of this one">More like this</button>
    </div>
  </article>`;
}

function draw() {
  const panel = $("variations-panel");
  if (!batch) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const running = batch.state === "running";
  const t = batch.timing || {};
  const timing = running ? "" : ` · rendered in ${t.render ?? "–"} s, checked in ${t.check ?? "–"} s`;
  $("variations-title").innerHTML = `Variations <span class="dim">${escapeHtml(baseWords(batch))}${batch.shuffle ? ` · shuffle ${batch.shuffle}` : ""}</span>`;
  $("variations-chain").textContent = batch.chain?.length ? `after: ${batch.chain.join(" → ")}` : "";
  $("variations-progress").textContent = running ? batch.progress : `${batch.progress}${timing}`;
  $("variations-progress").classList.toggle("busy", running);
  $("variations-cards").innerHTML = batch.items.map(cardHtml).join("");
  setBusy(running);
}

async function poll(id) {
  clearTimeout(polling);
  try {
    const doc = await api.variationBatch(id);
    if (!batch || batch.id !== id) return;
    const finished = batch.state === "running" && doc.state !== "running";
    batch = doc;
    draw();
    if (doc.state === "running") polling = setTimeout(() => poll(id), POLL_MS);
    else if (finished) {
      const t = doc.timing || {};
      ctx.status(`variations ${baseWords(doc)}: ${doc.items.length} rendered in ${t.render ?? "–"} s and checked in ${t.check ?? "–"} s`);
    }
  } catch (err) {
    ctx.status(err.message, "error");
  }
}

async function start(request, words) {
  if (document.body.dataset.draft) {
    ctx.status("the score file has typed text with problems: fix or revert it first", "error");
    return;
  }
  setBusy(true);
  $("variations-btn").disabled = true;
  ctx.status(`${words}…`, "busy");
  try {
    stopAudition(true);
    batch = await api.variations(request);
    draw();
    ctx.status(`${words}: ${batch.items.length} made, rendering and checking them`, "busy");
    poll(batch.id);
  } catch (err) {
    ctx.status(err.message, "error");
    setBusy(false);
  } finally {
    $("variations-btn").disabled = !ctx.state.session;
  }
}

function play(item) {
  const id = `${batch.id}/${item.letter}`;
  if (ctx.state.variation === id) {
    stopAudition(true);
    ctx.status(`back to v${ctx.state.score?.version}`);
    return;
  }
  ctx.state.ab.on = false;
  ctx.state.variation = id;
  ctx.state.variationLabel = `${item.letter} · ${item.label}`;
  draw();
  ctx.refreshAudio().then(() => {
    if (!ctx.player.playing) ctx.play();
  });
}

async function keep(item) {
  try {
    const doc = await api.keepVariation(batch.id, item.letter);
    const before = ctx.state.score?.text ?? null;
    ctx.state.variation = null;
    ctx.state.variationLabel = null;
    ctx.state.ab.on = false;
    ctx.show(doc, before);
    ctx.status(`kept variation ${item.letter} as v${doc.score.version}`, "busy");
    ctx.refreshAudio();
    await poll(batch.id);
  } catch (err) {
    ctx.status(err.message, "error");
  }
}

function onCardClick(e) {
  const button = e.target.closest("button[data-act]");
  if (!button || !batch) return;
  const letter = button.closest(".v-card")?.dataset.letter;
  const item = batch.items.find((i) => i.letter === letter);
  if (!item) return;
  if (button.dataset.act === "play") play(item);
  else if (button.dataset.act === "keep") keep(item);
  else if (button.dataset.act === "more") start({ batch: batch.id, letter }, `four more like ${letter}`);
}

// A version is shown (an edit, undo, a kept candidate...): the button and the cards' Play state.
export function showVariationsButton() {
  $("variations-btn").disabled = !ctx.state.session || Boolean(document.body.dataset.draft);
  if (batch) draw();
}

export function initVariations(c) {
  ctx = c;
  ctx.state.variation = null;
  $("variations-btn").addEventListener("click", () => {
    const version = ctx.state.score?.version;
    if (version != null) start({ version }, `variations of v${version}`);
  });
  $("variations-shuffle").addEventListener("click", () => {
    if (!batch) return;
    const base = batch.base?.batch ? { batch: batch.base.batch, letter: batch.base.letter } : { version: batch.root };
    start({ ...base, shuffle: (batch.shuffle || 0) + 1 }, "four others");
  });
  $("variations-close").addEventListener("click", () => {
    clearTimeout(polling);
    stopAudition(true);
    batch = null;
    draw();
    setBusy(false);
  });
  $("variations-cards").addEventListener("click", onCardClick);
}
