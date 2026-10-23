// Versions, undo / redo and A/B (DESIGN.md §94.4, §94.15). Every committed edit is a version on
// the server; undo goes to the current version's parent, redo back down the branch last undone,
// picking a version from the list makes it the current one (a new edit then starts a branch:
// nothing is deleted). A/B plays another version (the original preset by default, or any one
// picked) at the same moment, level-matched; the indicator says which one is playing.

import { api } from "./api.js";
import { escapeHtml } from "./yaml_view.js";

const $ = (id) => document.getElementById(id);
let ctx = null;

// ----- A/B ---------------------------------------------------------------------------------

// The version A stands for: the one picked, else the session's first (the preset or the text given).
function aVersion() {
  const versions = ctx.state.session?.versions || [];
  const picked = ctx.state.ab.version;
  return versions.some((v) => v.number === picked) ? picked : versions[0]?.number ?? null;
}

// The version that should play now: A while A/B is on A, else the current one.
export function playingVersion() {
  const { state } = ctx;
  return state.ab.on && aVersion() !== null ? aVersion() : state.score?.version ?? null;
}

function versionName(number) {
  const v = (ctx.state.session?.versions || []).find((x) => x.number === number);
  if (!v) return `v${number}`;
  return number === ctx.state.session.versions[0]?.number && (v.origin === "preset" || v.origin === "text") ? `v${number} original` : `v${number}`;
}

export function showAB() {
  const { state } = ctx;
  const a = aVersion();
  const current = state.score?.version;
  const usable = a !== null && current !== undefined && a !== current;
  if (!usable && state.ab.on) state.ab.on = false;
  const button = $("ab");
  button.disabled = !usable;
  button.setAttribute("aria-pressed", String(state.ab.on));
  $("ab-label").textContent = a === null ? "A/B" : `A/B ${a === state.session.versions[0]?.number ? "original" : `v${a}`}`;
  button.title = usable
    ? `Compare: A = ${versionName(a)}, B = v${current} (the current version), at the same moment and level. Click to switch.`
    : "A/B: make a change first (A is the original preset, or pick a version in the list to compare)";
  const ind = $("ab-state");
  ind.hidden = !usable;
  ind.dataset.side = state.ab.on ? "A" : "B";
  ind.innerHTML = state.ab.on
    ? `<b>A</b> ${escapeHtml(versionName(a))}`
    : `<b>B</b> v${current} current`;
  ind.title = state.ab.on ? `Playing A: ${versionName(a)}. Click A/B to go back to the current version.` : "Playing B: the current version";
  document.body.dataset.ab = state.ab.on ? "A" : "B";
}

function toggleAB(on = !ctx.state.ab.on) {
  ctx.state.ab.on = on;
  showAB();
  ctx.onAB?.();
  ctx.refreshAudio();
}

// Hear version `number` as A against the current one (B), or go back to B (`on` false): the
// proposal banner's A/B (Step 198).
export function abWith(number, on = true) {
  ctx.state.ab.version = number;
  toggleAB(on);
}

// Compare with version `number` (A) from now on.
function compareWith(number) {
  ctx.state.ab.version = number;
  closeMenu();
  toggleAB(true);
}

// ----- undo / redo / current ---------------------------------------------------------------

async function move(call, words) {
  const { state } = ctx;
  if (document.body.dataset.draft) {
    ctx.status("the score file has typed text with problems: fix or revert it first", "error");
    return;
  }
  const before = state.score?.text ?? null;
  const from = state.score?.version;
  try {
    const doc = await call();
    if (doc.score?.version === from) return;
    state.ab.on = false;
    ctx.show(doc, before);
    ctx.status(`${words} → v${doc.score.version} · ${currentLabel()}`, "busy");
    ctx.refreshAudio();
  } catch (err) {
    ctx.status(err.message, "error");
  }
}

function currentLabel() {
  const s = ctx.state.session;
  return s?.versions.find((v) => v.number === s.current)?.label || "";
}

export const undo = () => move(() => api.undo(), "undo");
export const redo = () => move(() => api.redo(), "redo");

// ----- the version list ---------------------------------------------------------------------

function clockOf(created) {
  // "2026-10-22T14:03:51" -> "14:03"
  return typeof created === "string" && created.length >= 16 ? created.slice(11, 16) : "";
}

// The current version's ancestors (the branch it is on), for the list's dimming.
function lineage(versions, current) {
  const byNumber = new Map(versions.map((v) => [v.number, v]));
  const out = new Set();
  for (let n = current; n != null && !out.has(n); n = byNumber.get(n)?.parent ?? null) out.add(n);
  return out;
}

const menuState = { renaming: null, sessions: null, drawing: false };

function renderMenu() {
  const { state } = ctx;
  const s = state.session;
  const list = $("version-list");
  if (!s) {
    list.innerHTML = "";
    return;
  }
  const typing = $("rename-input"); // a name being typed survives a re-render (the sessions arriving)
  const typed = typing ? { value: typing.value, start: typing.selectionStart, end: typing.selectionEnd, focused: document.activeElement === typing } : null;
  const versions = [...s.versions].reverse();
  const onBranch = lineage(s.versions, s.current);
  const a = aVersion();
  const rows = versions.map((v) => {
    const current = v.number === s.current;
    const parentNote = v.parent == null ? "start" : v.parent === v.number - 1 ? "" : `from v${v.parent}`;
    const label = menuState.renaming === v.number
      ? `<input class="field rename" id="rename-input" value="${escapeHtml(v.label)}" maxlength="120" aria-label="Name of v${v.number}">`
      : `<span class="v-label" title="${escapeHtml(v.label)}">${escapeHtml(v.label)}</span>`;
    return `<li class="version${current ? " current" : ""}${onBranch.has(v.number) ? "" : " off-branch"}" data-version="${v.number}" role="none">
      <button class="v-main" data-act="current" role="menuitemradio" aria-checked="${current}" title="${current ? "The current version" : `Make v${v.number} the current version`}">
        <span class="v-num">v${v.number}</span>${label}
        <span class="v-meta">${escapeHtml(clockOf(v.created))}${parentNote ? ` · ${escapeHtml(parentNote)}` : ""}${v.origin === "check" ? " · check" : ""}</span>
      </button>
      <button class="v-act star${v.starred ? " on" : ""}" data-act="star" aria-pressed="${Boolean(v.starred)}" aria-label="Star v${v.number}" title="${v.starred ? "Unstar" : "Star (keep it in mind)"}">${v.starred ? "★" : "☆"}</button>
      <button class="v-act" data-act="rename" aria-label="Rename v${v.number}" title="Rename">✎</button>
      <button class="v-act ab-pick${a === v.number && state.ab.on ? " on" : ""}" data-act="compare" aria-label="Compare v${v.number} with the current version (A/B)" title="A/B: compare with the current version" ${current ? "disabled" : ""}>A/B</button>
    </li>`;
  });
  const sessions = menuState.sessions || [];
  const others = sessions.filter((x) => !x.open).slice(0, 8);
  menuState.drawing = true; // the old rename field's blur is not a rename
  list.innerHTML =`<li class="menu-head" role="none">Versions of ${escapeHtml(s.title)} <span class="dim">· newest first · ★ starred</span></li>${rows.join("")}`
    + (others.length ? `<li class="menu-head" role="none">Earlier sessions</li>` + others.map((x) => `<li class="session-row" role="none">
        <button class="v-main" data-act="open" data-session="${escapeHtml(x.id)}" role="menuitem" title="Open this session (its current version)">
          <span class="v-label">${escapeHtml(x.title || x.preset || x.id)}</span>
          <span class="v-meta">${escapeHtml((x.created || "").replace("T", " ").slice(0, 16))} · ${x.versions} version${x.versions === 1 ? "" : "s"}</span>
        </button></li>`).join("") : "");
  menuState.drawing = false;
  const input = $("rename-input");
  if (input && typed) {
    input.value = typed.value;
    if (typed.focused) {
      input.focus();
      input.setSelectionRange(typed.start, typed.end);
    }
  } else if (input) {
    input.focus();
    input.select();
  }
}

export function showVersions() {
  const { state } = ctx;
  const s = state.session;
  const current = s?.versions.find((v) => v.number === s.current);
  $("version-name").textContent = state.score ? `v${state.score.version}` : "v–";
  $("version-star").hidden = !current?.starred;
  $("versions").disabled = !s;
  $("versions").title = current ? `v${current.number}: ${current.label} — ${s.versions.length} version${s.versions.length > 1 ? "s" : ""} (click for the list)` : "";
  $("undo").disabled = !s?.can_undo;
  $("redo").disabled = !s?.can_redo;
  $("undo").title = s?.can_undo ? `Undo: back to v${current.parent} (Ctrl+Z)` : "Nothing to undo";
  $("redo").title = s?.can_redo ? `Redo: forward to v${s.redo[s.redo.length - 1]} (Ctrl+Shift+Z)` : "Nothing to redo";
  showAB();
  if (!$("version-list").hidden) renderMenu();
}

async function openMenu() {
  $("version-list").hidden = false;
  $("versions").setAttribute("aria-expanded", "true");
  renderMenu();
  try {
    menuState.sessions = await api.sessions();
    if (!$("version-list").hidden) renderMenu();
  } catch {
    // the list of earlier sessions is a nicety
  }
}

function closeMenu() {
  menuState.renaming = null;
  $("version-list").hidden = true;
  $("versions").setAttribute("aria-expanded", "false");
}

async function rename(number, label) {
  menuState.renaming = null;
  const v = ctx.state.session.versions.find((x) => x.number === number);
  if (!label.trim() || label === v?.label) return renderMenu();
  try {
    const r = await api.updateVersion(number, { label });
    ctx.state.session = r.session;
    showVersions();
  } catch (err) {
    ctx.status(err.message, "error");
    renderMenu();
  }
}

async function onMenuClick(e) {
  const button = e.target.closest("button");
  if (!button) return;
  const row = button.closest("li");
  const number = Number(row?.dataset.version);
  const act = button.dataset.act;
  if (act === "current" && menuState.renaming === number) return;
  if (act === "current") {
    closeMenu();
    if (number !== ctx.state.session.current) await move(() => api.setCurrent(number), "picked");
  } else if (act === "star") {
    const v = ctx.state.session.versions.find((x) => x.number === number);
    try {
      const r = await api.updateVersion(number, { starred: !v.starred });
      ctx.state.session = r.session;
      showVersions();
    } catch (err) {
      ctx.status(err.message, "error");
    }
  } else if (act === "rename") {
    menuState.renaming = number;
    renderMenu();
  } else if (act === "compare") {
    compareWith(number);
  } else if (act === "open") {
    closeMenu();
    await ctx.openSession(button.dataset.session);
  }
}

export function initVersions(c) {
  ctx = c;
  ctx.state.ab = { on: false, version: null };
  $("ab").addEventListener("click", () => toggleAB());
  $("undo").addEventListener("click", undo);
  $("redo").addEventListener("click", redo);
  const list = $("version-list");
  $("versions").addEventListener("click", () => (list.hidden ? openMenu() : closeMenu()));
  list.addEventListener("click", onMenuClick);
  list.addEventListener("keydown", (e) => {
    if (e.target.id === "rename-input") {
      if (e.key === "Enter") rename(menuState.renaming, e.target.value);
      else if (e.key === "Escape") {
        menuState.renaming = null;
        renderMenu();
      }
      e.stopPropagation();
      return;
    }
    if (e.key === "Escape") {
      closeMenu();
      $("versions").focus();
    }
  });
  list.addEventListener("focusout", (e) => {
    if (e.target.id === "rename-input" && menuState.renaming !== null && !menuState.drawing) rename(menuState.renaming, e.target.value);
  });
  document.addEventListener("click", (e) => {
    // the path as dispatched: a click that re-renders the list has a detached target by now
    if (!list.hidden && !e.composedPath().some((el) => el.classList?.contains("versions-wrap"))) closeMenu();
  });
  document.addEventListener("keydown", (e) => {
    const typing = e.target.closest?.("input, textarea, select, [contenteditable]");
    if (typing || !(e.ctrlKey || e.metaKey)) return;
    const key = e.key.toLowerCase();
    if (key === "z" && !e.shiftKey) undo();
    else if ((key === "z" && e.shiftKey) || key === "y") redo();
    else return;
    e.preventDefault();
  });
}
