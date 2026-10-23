// The check panel (DESIGN.md §94.15): `vidgen music check` of the current version, made by the
// server in the background after each render (from the stems it keeps; a newer version's check
// replaces an older one under way), shown as a verdict and headline numbers, the spectrogram
// with the section marks and the playhead, plain-language advice with [Apply] where the fix is
// mechanical (a new version labelled with the advice), and the full report.

import { api } from "./api.js";
import { escapeHtml } from "./yaml_view.js";

const $ = (id) => document.getElementById(id);
const MARK = { ok: "✓", note: "•", fix: "!" };
const CHECK_DELAY_MS = 500; // after a render plays: a burst of edits checks only the last one

let ctx = null;
let shown = null;     // the check on screen
let wanted = null;    // the version whose check is asked for
let timer = 0;

function setState(text) {
  $("check-state").textContent = text;
  if (text) document.body.dataset.checking = "1";
  else delete document.body.dataset.checking;
}

// Ask for the check of version `number` (after a render of it played).
export function requestCheck(number) {
  if (number == null) return;
  wanted = number;
  clearTimeout(timer);
  if (shown && shown.version !== number) $("check-panel").classList.add("stale");
  setState(`checking v${number}…`);
  timer = setTimeout(() => run(number), CHECK_DELAY_MS);
}

async function run(number) {
  try {
    for (;;) {
      if (wanted !== number) return;
      const r = await api.check(number, 25);
      if (wanted !== number) return;
      if (r.status === "done") return show(r);
      if (r.status === "superseded") return;
    }
  } catch (err) {
    if (wanted === number) setState(`check: ${err.message}`);
  }
}

function headlineHtml(doc) {
  return doc.headline.map((h) => `<span class="num ${h.level}" title="${escapeHtml(h.title)}"><span class="dim">${escapeHtml(h.name)}</span> ${escapeHtml(h.value)}${h.level === "ok" ? "" : ` <i aria-label="${h.level}">${MARK[h.level]}</i>`}</span>`).join("");
}

// Advice: each finding that is not ok, its words, its lines and the [Apply] buttons.
function adviceHtml(doc) {
  const items = doc.findings.map((f, i) => ({ ...f, i })).filter((f) => f.level !== "ok");
  if (!items.length) {
    return `<p class="all-good">${MARK.ok} Nothing to change: it leaves room for the voice, its loudness is steady and its sections do their job.</p>`;
  }
  const current = ctx.state.score?.version === doc.version && !document.body.dataset.draft;
  return items.map((f) => {
    const lines = f.fixes.map((text, k) => {
      const edits = f.edits.filter((e) => e.fix === k);
      const buttons = edits.map((e) => `<button class="btn small apply" data-edit="${escapeHtml(e.id)}" ${current ? "" : "disabled"}
          title="${current ? `Make a new version with: ${escapeHtml(e.ops.map((o) => `${o.path} = ${JSON.stringify(o.value)}`).join("; "))}` : "This check is of another version: check the current one first"}">Apply: ${escapeHtml(e.label)}</button>`).join("");
      return `<li><span class="fix-text">${codeWords(text)}</span>${buttons ? `<span class="applies">${buttons}</span>` : ""}</li>`;
    }).join("");
    return `<div class="finding ${f.level}"><div class="f-head"><span class="badge ${f.level}">${f.level === "fix" ? "fix" : "note"}</span> <b>${escapeHtml(f.topic)}</b></div>
      <p>${codeWords(f.text)}</p>${lines ? `<ul>${lines}</ul>` : ""}</div>`;
  }).join("");
}

// The advice's `score keys` in backticks as code.
function codeWords(text) {
  return escapeHtml(text).replace(/`([^`]+)`/g, "<code>$1</code>");
}

function show(doc) {
  shown = doc;
  setState("");
  const panel = $("check-panel");
  panel.classList.remove("stale");
  panel.dataset.level = doc.level;
  $("check-verdict").innerHTML = `<i aria-hidden="true">${MARK[doc.level]}</i> ${escapeHtml(doc.verdict)}`;
  $("check-verdict").title = `the check of v${doc.version} (vidgen music check), made in ${doc.timings?.check ?? "?"} s`;
  $("check-headline").innerHTML = headlineHtml(doc);
  const advice = doc.findings.filter((f) => f.level !== "ok").length;
  $("check-toggle-count").textContent = advice ? ` · ${advice} advice` : "";
  $("check-for").textContent = `v${doc.version}`;
  $("check-image").src = doc.image.url;
  $("check-image").alt = `Spectrogram of v${doc.version} with its sections marked; under it each bar's level in the voice's range against the limit`;
  $("check-advice").innerHTML = adviceHtml(doc);
  $("check-report").textContent = doc.text;
  tickCheck(ctx.state.time);
}

// The playhead on the spectrogram.
export function tickCheck(seconds) {
  if (!shown) return;
  const img = shown.image;
  const x = (img.left + seconds * img.px_per_second) / img.width;
  const head = $("check-playhead");
  head.hidden = !(x >= 0 && x <= 1);
  head.style.left = `${(100 * x).toFixed(3)}%`;
}

// A new version is shown: the advice buttons apply only to the version checked.
export function showCheckVersion() {
  if (shown) $("check-advice").innerHTML = adviceHtml(shown);
  if (shown && ctx.state.score?.version !== shown.version) $("check-panel").classList.add("stale");
  else if (shown) $("check-panel").classList.remove("stale");
}

function setOpen(open) {
  $("check-body").hidden = !open;
  $("check-toggle").setAttribute("aria-expanded", String(open));
  ctx.storage("vidgen-studio-check-open", open ? "1" : "0");
}

async function apply(id, button) {
  const doc = shown;
  button.disabled = true;
  const r = await ctx.commitWith(() => api.applyCheck(doc.version, doc.key, id));
  if (!r.ok) button.disabled = false;
}

export function initCheck(c) {
  ctx = c;
  $("check-toggle").addEventListener("click", () => setOpen($("check-body").hidden));
  setOpen(ctx.storage("vidgen-studio-check-open") === "1");
  $("check-advice").addEventListener("click", (e) => {
    const button = e.target.closest("button.apply");
    if (button && shown) apply(button.dataset.edit, button);
  });
  $("check-spectro").addEventListener("click", (e) => {
    if (!shown) return;
    const rect = $("check-image").getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * shown.image.width;
    const seconds = (px - shown.image.left) / shown.image.px_per_second;
    if (seconds >= 0) ctx.seekTo(seconds);
  });
}
