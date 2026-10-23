// The score file, editable (DESIGN.md §94.13): a transparent textarea over the highlighted text,
// so typing keeps the colours and line numbers. Typed text is checked as you go (problems with
// their line, the CLI's did-you-mean messages); text that stays valid for 0.8 s becomes the next
// version and the controls follow. Text with problems is a draft: it is never a version, the
// last good version keeps playing, and the controls wait until it is fixed or reverted.

import { api } from "./api.js";
import { changedLines, escapeHtml, showYaml } from "./yaml_view.js";

const CHECK_MS = 300;   // after the last key: check the text
const KEEP_MS = 500;    // then, valid: keep it (0.8 s in all)
const LINE_PX = 18;     // .code line height (12px × 1.5)

let ctx = null;
const ed = { base: "", draft: false, seq: 0, checkTimer: 0, keepTimer: 0 };
const $ = (id) => document.getElementById(id);

export function initYamlEditor(context) {
  ctx = context;
  const input = $("yaml-input");
  input.addEventListener("input", onInput);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Tab" && !e.shiftKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      input.setRangeText("  ", input.selectionStart, input.selectionEnd, "end");
      onInput();
    } else if (e.key === "Escape") {
      input.blur();
    }
  });
  for (const type of ["keyup", "click"]) input.addEventListener(type, caretIntoView);
  $("yaml-problems").addEventListener("click", (e) => {
    const go = e.target.closest("[data-line]");
    if (go) return goToLine(Number(go.dataset.line));
    if (e.target.closest("#yaml-revert")) revert();
  });
}

// Show version text `text` (`before`: the text before an edit, its changed lines flash). A
// person's draft in the focused editor is kept.
export function showScoreText(text, problems = [], before = null) {
  const input = $("yaml-input");
  const typing = document.activeElement === input && input.value !== ed.base && input.value !== text;
  ed.base = text;
  if (typing) return;
  clearTimeout(ed.checkTimer);
  clearTimeout(ed.keepTimer);
  input.value = text;
  draw(text, badLines(problems), changedLines(before, text));
  showProblems(problems, false);
  setDraft(false);
}

function badLines(problems) {
  const bad = new Map();
  for (const p of problems) if (p.line && !bad.has(p.line)) bad.set(p.line, `${p.where ? p.where + ": " : ""}${p.message}`);
  return bad;
}

function draw(text, bad = new Map(), changed = new Set()) {
  showYaml($("yaml"), text, bad, changed);
}

function onInput() {
  const text = $("yaml-input").value;
  draw(text);
  clearTimeout(ed.checkTimer);
  clearTimeout(ed.keepTimer);
  ed.seq++;
  setState(text === ed.base ? "" : "typing…");
  if (text === ed.base) {
    showProblems([], false);
    setDraft(false);
    return;
  }
  ed.checkTimer = setTimeout(() => check(text), CHECK_MS);
}

async function check(text) {
  const seq = ++ed.seq;
  let r;
  try {
    r = await api.validate(text);
  } catch (err) {
    r = { ok: false, problems: [{ where: "", message: err.message, line: null }] };
  }
  if (seq !== ed.seq || $("yaml-input").value !== text) return;
  draw(text, badLines(r.problems));
  showProblems(r.problems, true);
  setDraft(!r.ok);
  if (r.ok) {
    setState("valid · keeping…");
    ed.keepTimer = setTimeout(() => keep(text, seq), KEEP_MS);
  } else {
    setState("draft · not kept");
  }
}

async function keep(text, seq) {
  if (seq !== ed.seq || $("yaml-input").value !== text) return;
  const r = await ctx.commitText(text);
  if (!r.ok) {
    showProblems(r.problems || [], true);
    setDraft(true);
  } else {
    setState("");
  }
}

function revert() {
  const input = $("yaml-input");
  input.value = ed.base;
  ed.seq++;
  clearTimeout(ed.checkTimer);
  clearTimeout(ed.keepTimer);
  const problems = ctx.state.score?.problems || [];
  draw(ed.base, badLines(problems));
  showProblems(problems, false);
  setDraft(false);
  setState("");
  ctx.status(`back to v${ctx.state.score?.version ?? "–"} as it is`);
}

function setState(text) {
  $("yaml-state").textContent = text;
}

// The draft mark: the controls wait while the typed text has problems.
function setDraft(on) {
  ed.draft = on;
  if (on) document.body.dataset.draft = "1";
  else delete document.body.dataset.draft;
}

function showProblems(problems, typed) {
  const box = $("yaml-problems");
  if (!problems.length) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  const version = ctx.state.score?.version;
  const items = problems
    .map((p) => {
      const where = p.where && !p.where.startsWith("line ") ? `<code>${escapeHtml(p.where)}</code> ` : "";
      const line = p.line ? `<button type="button" class="line-link" data-line="${p.line}">line ${p.line}</button>` : '<span class="line-link none">—</span>';
      return `<li>${line}<span>${where}${escapeHtml(p.message)}</span></li>`;
    })
    .join("");
  const count = `${problems.length} problem${problems.length > 1 ? "s" : ""}`;
  const head = typed
    ? `<b>${count}</b> in the typed text · v${version} keeps playing <button type="button" class="btn small" id="yaml-revert">Revert to v${version}</button>`
    : `<b>${count}</b> in this version`;
  box.innerHTML = `<div class="head">${head}</div><ul>${items}</ul>`;
  box.hidden = false;
}

function goToLine(line) {
  const input = $("yaml-input");
  const lines = input.value.split("\n");
  let at = 0;
  for (let i = 0; i < line - 1 && i < lines.length; i++) at += lines[i].length + 1;
  input.focus();
  input.setSelectionRange(at, at + (lines[line - 1] || "").length);
  caretIntoView();
}

// Keep the caret's line in view: the panel scrolls, not the textarea (it is as tall as the text).
function caretIntoView() {
  const input = $("yaml-input");
  const panel = $("yaml-panel");
  const line = input.value.slice(0, input.selectionStart).split("\n").length;
  const top = input.getBoundingClientRect().top - panel.getBoundingClientRect().top + panel.scrollTop + 8 + (line - 1) * LINE_PX;
  const head = panel.querySelector(".yaml-head")?.offsetHeight || 30;
  if (top < panel.scrollTop + head + 10) panel.scrollTop = Math.max(0, top - head - 20);
  else if (top > panel.scrollTop + panel.clientHeight - 40) panel.scrollTop = top - panel.clientHeight + 60;
}
