// vidgen studio, the page (DESIGN.md §94.7, §94.12, §94.13): the top bar's preset picker, the
// song strip (strip.js), transport, the timeline (timeline.js), the track list (tracks.js), the
// inspector (inspector.js), the score file editable both ways (yaml_edit.js) and the status
// line. State lives on the server (the session); every committed edit is a new version, then
// rendered and played on from the same moment.

import { api, onConnection } from "./api.js";
import { initCheck, requestCheck, showCheckVersion, tickCheck } from "./check.js";
import { initExports, showExports } from "./exports.js";
import { initInspector, showInspector, tickInspector } from "./inspector.js";
import { initNotes, pollNow, setNotes, setOffline, showNotes, showTab, tickNotes } from "./notes.js";
import { Player } from "./player.js";
import { initStrip, showChords, showFacts, tickChords } from "./strip.js";
import { initTimeline, setRendering, showEnergy, showLoop, showTimeline, tickTimeline } from "./timeline.js";
import { initTracks, mutedTracks, showMuted, showTracks, tickMeters } from "./tracks.js";
import { initVariations, restoreVariations, showVariationsButton } from "./variations.js";
import { initVersions, playingVersion, showAB, showVersions } from "./versions.js";
import { initYamlEditor, showScoreText } from "./yaml_edit.js";
import { escapeHtml } from "./yaml_view.js";

const $ = (id) => document.getElementById(id);
const PALETTE = ["--c1", "--c2", "--c3", "--c4"];

const state = {
  presets: [],
  patches: null,
  info: null,
  session: null,
  score: null,          // {version, text, outline, problems, render_key}
  render: null,         // the render playing (its facts)
  selected: null,       // the selected track's name
  selectedSection: null,
  loop: null,           // the section looped, or null: the whole piece
  mute: new Set(),      // listening aid only: never written to the score
  solo: new Set(),
  narration: false,     // play under the narration sample (a listening aid too)
  rendering: false,
  wantAudio: false,
  seekAfter: null,      // a moment to play from once the next source is in
  time: 0,              // the moment of the piece shown
};

// ----- small helpers ----------------------------------------------------------------------

function clock(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function status(text, kind = "") {
  const el = $("status");
  el.textContent = text;
  el.className = `status ${kind}`;
}

let problemTimer = 0;
function problem(text) {
  const el = $("strip-problem");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(problemTimer);
  problemTimer = setTimeout(() => { el.hidden = true; }, 6000);
}

function colour(i) {
  return `var(${PALETTE[i % PALETTE.length]})`;
}

function storage(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch {
    return null;
  }
  return value;
}

const outline = () => state.score?.outline ?? null;

function sectionAt(seconds) {
  const sections = outline()?.sections || [];
  let found = sections[0];
  for (const s of sections) if (s.start <= seconds + 1e-6) found = s;
  return found;
}

// The section the strip's chords follow: the one looped, else the one under the playhead.
function activeSection() {
  const sections = outline()?.sections || [];
  return sections.find((s) => s.name === state.loop) || sectionAt(state.time);
}

// ----- theme ------------------------------------------------------------------------------

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  storage("vidgen-studio-theme", theme);
}

// ----- the preset picker ------------------------------------------------------------------

const picker = {
  open() {
    const list = $("preset-list");
    list.hidden = false;
    $("preset-button").setAttribute("aria-expanded", "true");
    const current = list.querySelector('[aria-selected="true"]') || list.firstElementChild;
    this.activate(current);
    list.focus();
  },
  close(focusButton = true) {
    $("preset-list").hidden = true;
    $("preset-button").setAttribute("aria-expanded", "false");
    if (focusButton) $("preset-button").focus();
  },
  activate(item) {
    if (!item) return;
    for (const li of $("preset-list").children) li.classList.toggle("active", li === item);
    $("preset-list").setAttribute("aria-activedescendant", item.id);
    item.scrollIntoView({ block: "nearest" });
  },
  fill(presets) {
    $("preset-list").innerHTML = presets
      .map((p) => `<li role="option" id="preset-${p.name}" data-name="${p.name}" aria-selected="false">
          <span class="name">${escapeHtml(p.name)}</span>
          <span class="facts">${escapeHtml(p.key)} · ${p.tempo} BPM · ${p.seconds.toFixed(0)} s</span>
          <span class="line">${escapeHtml(p.one_line)}</span></li>`)
      .join("");
  },
  mark(name) {
    for (const li of $("preset-list").children) li.setAttribute("aria-selected", String(li.dataset.name === name));
    $("preset-name").textContent = name || "—";
    const preset = state.presets.find((p) => p.name === name);
    $("preset-button").title = preset ? `${preset.one_line}. Use: ${preset.use}` : "";
  },
};

function wirePicker() {
  const list = $("preset-list");
  $("preset-button").addEventListener("click", () => (list.hidden ? picker.open() : picker.close()));
  list.addEventListener("click", (e) => {
    const li = e.target.closest("li");
    if (li) choosePreset(li.dataset.name);
  });
  list.addEventListener("mousemove", (e) => {
    const li = e.target.closest("li");
    if (li) picker.activate(li);
  });
  list.addEventListener("keydown", (e) => {
    const active = list.querySelector("li.active");
    if (e.key === "ArrowDown") picker.activate(active?.nextElementSibling || list.firstElementChild);
    else if (e.key === "ArrowUp") picker.activate(active?.previousElementSibling || list.lastElementChild);
    else if (e.key === "Enter" && active) choosePreset(active.dataset.name);
    else if (e.key === "Escape") picker.close();
    else return;
    e.preventDefault();
  });
  document.addEventListener("click", (e) => {
    if (!list.hidden && !e.target.closest(".picker")) picker.close(false);
  });
}

async function choosePreset(name) {
  picker.close();
  if (state.session && state.session.preset === name) return;
  player.stop();
  status(`loading ${name}…`, "busy");
  try {
    const doc = await api.load(name);
    resetListening();
    show(doc);
    await refreshAudio();
  } catch (err) {
    status(err.message, "error");
  }
}

// ----- showing the score ------------------------------------------------------------------

function show(doc, before = null) {
  state.session = doc.session;
  state.score = doc.score;
  const o = outline();
  picker.mark(state.session?.preset);
  showVersions();
  showExports();
  showCheckVersion();
  showVariationsButton();
  setNotes(doc);
  $("yaml-name").textContent = state.session ? `· ${state.session.title} · v${state.score?.version ?? "–"}` : "";
  if (o && !o.tracks.some((t) => t.name === state.selected)) state.selected = o.tracks[0]?.name ?? null;
  showFacts();
  showTimeline();
  showTracks();
  showInspector();
  showScoreText(state.score?.text || "", state.score?.problems || [], before);
  showNotes();
}

function selectTrack(name) {
  state.selected = name;
  for (const row of $("tracks").querySelectorAll(".track")) row.setAttribute("aria-selected", String(row.dataset.name === name));
  showInspector();
}

// ----- edits ------------------------------------------------------------------------------

let editChain = Promise.resolve();
let busyCount = 0;

// `data-busy` on <body> while an edit or a render is under way (tests and screenshots wait on it).
function busy(delta) {
  busyCount += delta;
  if (busyCount > 0) document.body.dataset.busy = "1";
  else delete document.body.dataset.busy;
}

// Commit `ops` as the next version (one at a time, each on the version before), show it and
// render it. Resolves to the server's answer: {ok, problems} when the edit has problems.
function commit(ops, label) {
  return commitWith((version) => api.edit(version, ops, label));
}

// Typed score text (the score file) as the next version, as an edit.
function commitText(text) {
  return commitWith((version) => api.text(version, text));
}

function commitWith(send) {
  const run = async () => {
    if (!state.score) return { ok: false, problems: [{ where: "", message: "no score open" }] };
    const before = state.score.text;
    try {
      const r = await send(state.score.version);
      if (!r.ok) {
        const p = r.problems[0];
        status(`not changed: ${p.where ? p.where + ": " : ""}${p.message}`, "error");
        return r;
      }
      if (r.unchanged) return r;
      state.ab.on = false; // a new version: B (it) plays
      state.variation = null;
      show(r, before);
      const version = r.session.versions.find((v) => v.number === r.score.version);
      status(`v${r.score.version} · ${version?.label || "edited"} · rendering…`, "busy");
      refreshAudio();
      return r;
    } catch (err) {
      status(err.message, "error");
      problem(err.message);
      return { ok: false, problems: [{ where: "", message: err.message }] };
    } finally {
      busy(-1);
    }
  };
  busy(1);
  editChain = editChain.then(run, run);
  return editChain;
}

// Check `ops` on the current version without keeping them: {ok, problems, outline}.
async function check(ops) {
  try {
    return await api.edit(state.score.version, ops, null, true);
  } catch (err) {
    return { ok: false, problems: [{ where: "", message: err.message }] };
  }
}

// ----- rendering and playback -------------------------------------------------------------

// Render what should play (the current version, the section looped, without the muted tracks)
// and switch to it at the same moment. Renders run one at a time; a newer wish replaces an
// older one that has not started.
async function refreshAudio() {
  state.wantAudio = true;
  if (state.rendering) return;
  state.rendering = true;
  busy(1);
  const badge = setTimeout(() => {
    $("render-badge").hidden = false;
    setRendering(true);
  }, 120);
  try {
    while (state.wantAudio) {
      state.wantAudio = false;
      if (!state.score || state.score.problems.length) break;
      const r = await api.render(playingVersion(), state.loop, mutedTracks(), state.narration, state.variation);
      if (state.wantAudio) continue;
      applyRender(r);
    }
  } catch (err) {
    // the player is left alone: the last good render keeps playing
    const keeps = player.url ? " · the last good render keeps playing" : "";
    status(`could not render: ${err.message}${keeps}`, "error");
  } finally {
    clearTimeout(badge);
    state.rendering = false;
    busy(-1);
    $("render-badge").hidden = true;
    setRendering(false);
  }
}

// What a render took, in words: the tracks rendered again (the others' stems were kept), a
// volume applied to a kept stem, the mix, a listening mix, the narration.
function howMade(r) {
  const t = r.timing || {};
  const parts = [];
  const tracks = Object.keys(t.tracks || {});
  if (tracks.length) parts.push(tracks.length > 3 ? `${tracks.length} tracks rendered` : `${tracks.join(", ")} rendered`);
  const scaled = Object.keys(t.scaled || {});
  if (scaled.length) parts.push(`${scaled.join(", ")} at the new volume`);
  if (!r.cached) parts.push(tracks.length || scaled.length ? "remixed" : "mixed");
  if (t.listening_mix) parts.push("listening mix");
  if (t.narration) parts.push("under narration");
  return parts.length ? `${parts.join(" + ")} in ${(t.total || 0).toFixed(1)} s` : "from the cache";
}

function renderStatus(r) {
  const where = r.section ? ` · looping ${r.section.name}` : "";
  const muted = r.muted?.length ? ` · without ${r.muted.join(", ")}` : "";
  const voice = r.narration ? " · under narration" : "";
  const level = typeof r.loudness === "number"
    ? ` · ${r.loudness.toFixed(1)} LUFS in a video, ${r.narration ? "here as in a video under the voice" : `plays at ${(r.loudness + r.audition_gain_db).toFixed(0)} here`}`
    : "";
  const what = r.variation ? `variation ${r.variation.split("/")[1]}` : `v${r.version}`;
  status(`${what} ${howMade(r)} · ${clock(r.seconds)}${where}${muted}${voice}${level}`);
}

function applyRender(r) {
  state.render = r;
  const at = state.seekAfter;
  state.seekAfter = null;
  player.setSource(r.url, { loop: r.section ? true : r.loop, offset: r.section ? r.section.start : 0, at });
  showEnergy();
  renderStatus(r);
  showAB();
  if (r.facts_pending) lateFacts(r);
  if (r.version === state.score?.version) requestCheck(r.version);
}

// The loudness, true peak and energy curve come a moment after the render plays (the server
// works them out when no render is under way).
async function lateFacts(r) {
  busy(1);
  try {
    const f = await api.facts(r.key);
    if (f.pending || state.render?.key !== r.key) return;
    for (const done of [r, state.render]) Object.assign(done, f, { facts_pending: false });
    showEnergy();
    if (state.render === r) renderStatus(r);
  } catch {
    // the facts are a nicety: playing goes on without them
  } finally {
    busy(-1);
  }
}

function setLoop(name) {
  state.loop = name || null;
  if (name) state.selectedSection = name;
  showLoop();
  showChords(activeSection());
  refreshAudio();
}

// Go to moment `seconds` of the piece; outside the section looped, the whole piece plays.
function seekTo(seconds) {
  const o = outline();
  if (!o) return;
  seconds = Math.max(0, Math.min(seconds, o.seconds));
  const looped = o.sections.find((s) => s.name === state.loop);
  if (looped && (seconds < looped.start || seconds >= looped.start + looped.bars * o.bar_seconds)) {
    state.seekAfter = seconds;
    setLoop(null);
    return;
  }
  player.seek(seconds);
}

function onTick(seconds) {
  state.time = seconds;
  const whole = state.render?.seconds || outline()?.seconds || 0;
  $("time").textContent = `${clock(seconds)} / ${clock(whole)}`;
  if (!seeking) $("seek").value = whole ? String(Math.round((seconds / whole) * 1000)) : "0";
  const section = sectionAt(seconds);
  tickTimeline(seconds, section);
  tickChords(activeSection(), seconds);
  tickMeters(seconds, section, player.playing);
  tickInspector(seconds, section, player.playing);
  tickCheck(seconds);
  tickNotes(seconds);
}

function onPlayState(playing) {
  $("play").setAttribute("aria-pressed", String(playing));
  $("play").setAttribute("aria-label", playing ? "Pause" : "Play");
  if (!playing) setTimeout(() => onTick(player.time), 0);
  if (!playing) fadeMeters();
}

function fadeMeters() {
  let frames = 30;
  const step = () => {
    tickMeters(state.time, sectionAt(state.time), false);
    if (--frames > 0 && !player.playing) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

const player = new Player($("audio"), onTick, onPlayState);
let seeking = false;

async function togglePlay() {
  if (player.playing) return player.pause();
  if (!player.url) await refreshAudio();
  return player.play();
}

function wireTransport() {
  $("play").addEventListener("click", togglePlay);
  $("stop").addEventListener("click", () => player.stop());
  $("loop").addEventListener("change", (e) => setLoop(e.target.value));
  $("narration").addEventListener("change", (e) => {
    state.narration = e.target.checked;
    refreshAudio();
  });
  const seek = $("seek");
  seek.addEventListener("input", () => {
    seeking = true;
    const whole = state.render?.seconds || 0;
    $("time").textContent = `${clock((seek.value / 1000) * whole)} / ${clock(whole)}`;
  });
  seek.addEventListener("change", () => {
    seeking = false;
    seekTo((seek.value / 1000) * (state.render?.seconds || 0));
  });
}

// ----- start --------------------------------------------------------------------------------

// Reopen an earlier session (from the version list).
async function openSession(id) {
  player.stop();
  status("opening the session…", "busy");
  try {
    const doc = await api.openSession(id);
    resetListening();
    show(doc);
    await refreshAudio();
  } catch (err) {
    status(err.message, "error");
  }
}

// A new piece: what was being listened to (loop, mutes, A/B) starts afresh.
function resetListening() {
  Object.assign(state, { render: null, loop: null, selectedSection: null, time: 0 });
  state.mute.clear();
  state.solo.clear();
  state.ab.on = false;
  state.ab.version = null;
  state.variation = null;
}

const ctx = {
  state, outline, commit, commitText, commitWith, check, status, problem, colour, clock, setLoop, seekTo, refreshAudio, selectTrack, activeSection,
  show, storage, openSession, player, playingVersion, play: () => player.play(), focusByPointer: () => focusByPointer(),
};

// ----- narrow windows: the inspector, score file and notes as tabs below the tracks ----------

function showPane(name) {
  $("work").dataset.pane = name;
  for (const b of document.querySelectorAll(".pane-tab")) b.setAttribute("aria-selected", String(b.dataset.pane === name));
  storage("vidgen-studio-pane", name);
}

function wirePanes() {
  $("pane-tabs").addEventListener("click", (e) => {
    const name = e.target.closest(".pane-tab")?.dataset.pane;
    if (name === "inspector") showPane(name);
    else if (name) showTab(name); // the score file / notes tabs, which show their pane
  });
  $("pane-tabs").addEventListener("keydown", (e) => {
    const tabs = [...document.querySelectorAll(".pane-tab")];
    const at = tabs.indexOf(document.activeElement);
    const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (at < 0 || !step) return;
    e.preventDefault();
    const next = tabs[(at + step + tabs.length) % tabs.length];
    next.focus();
    next.click();
  });
  const saved = storage("vidgen-studio-pane");
  showPane(saved === "yaml" || saved === "notes" ? saved : "inspector");
  ctx.showPane = showPane;
}

// ----- keyboard shortcuts, the help and the first-run hint ----------------------------------

const TYPING = "input, textarea, select, [contenteditable]";

function setHelp(open) {
  $("shortcuts").hidden = !open;
  $("help-btn").setAttribute("aria-expanded", String(open));
  if (open) $("shortcuts-close").focus();
}

// L: loop the section playing (again: the whole piece); M / S: mute / solo the selected track;
// V: variations of the version shown. True when the key was one of them.
function letterKey(key) {
  if (key === "l") {
    const section = state.loop ? null : sectionAt(state.time)?.name;
    setLoop(section);
    status(section ? `looping ${section} (L again: the whole piece)` : "playing the whole piece");
    return true;
  }
  if (key === "m" || key === "s") {
    const name = state.selected;
    if (!name || !outline()?.tracks.some((t) => t.name === name)) return true;
    const set = key === "m" ? state.mute : state.solo;
    if (set.has(name)) set.delete(name);
    else set.add(name);
    showMuted();
    refreshAudio();
    return true;
  }
  if (key === "v") {
    if (!$("variations-btn").disabled) $("variations-btn").click();
    return true;
  }
  return false;
}

function wireKeys() {
  $("help-btn").addEventListener("click", () => setHelp($("shortcuts").hidden));
  $("shortcuts-close").addEventListener("click", () => {
    setHelp(false);
    $("help-btn").focus();
  });
  document.addEventListener("keydown", (e) => {
    if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
    const el = e.target;
    if (e.key === "Escape" && !$("shortcuts").hidden) {
      setHelp(false);
      $("help-btn").focus();
      return;
    }
    if (el.closest?.(TYPING)) return;
    if (e.key === "?") {
      e.preventDefault();
      setHelp($("shortcuts").hidden);
    } else if (e.key === " " || e.code === "Space") {
      // A control reached with the keyboard keeps Space (it presses it); after a mouse click
      // Space plays and pauses, as in any player.
      const control = el.closest?.("button, [role=button], [role=tab], [role=option], [role=menuitem], [role=menuitemradio], .cell, [tabindex]");
      if (control && control !== document.body && !focusByPointer()) return;
      e.preventDefault();
      if (!e.repeat) togglePlay();
    } else if (!e.repeat && letterKey(e.key.toLowerCase())) e.preventDefault();
  });
  // a mouse-focused button would also be pressed by the Space's keyup
  document.addEventListener("keyup", (e) => {
    if ((e.key === " " || e.code === "Space") && !e.target.closest?.(TYPING) && focusByPointer()) e.preventDefault();
  });
  // how focus last moved: a pointer press, or the keyboard (Tab, arrows)
  document.addEventListener("pointerdown", () => (lastFocusBy = "pointer"), true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Tab" || e.key.startsWith("Arrow")) lastFocusBy = "keyboard";
  }, true);
}

let lastFocusBy = "pointer";

// Whether the focused control was reached with the mouse (Space then plays / pauses) rather than
// the keyboard (Space presses it). Chrome's :focus-visible turns on at any key, so it cannot tell.
function focusByPointer() {
  return lastFocusBy === "pointer";
}

const HINT_KEY = "vidgen-studio-hint-seen";

function wireHint() {
  const close = () => {
    $("hint").hidden = true;
    storage(HINT_KEY, "1");
  };
  $("hint-close").addEventListener("click", close);
  $("hint").addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
  });
  if (storage(HINT_KEY) !== "1") $("hint").hidden = false;
}

// ----- the server stopped: a banner, retries, and back to normal when it answers -------------

function wireConnection() {
  onConnection((up) => {
    $("offline").hidden = up;
    if (up) delete document.body.dataset.offline;
    else document.body.dataset.offline = "1";
    setOffline(!up);
    if (up) reconnect();
  });
  $("offline-retry").addEventListener("click", () => {
    status("trying the studio server again…", "busy");
    pollNow();
  });
}

// The server answers again. A studio started again has no session open: the page's own session
// (on disk) is reopened, so the piece carries on where it was.
async function reconnect() {
  if (!state.info) {
    location.reload(); // it never started: start now
    return;
  }
  status("the studio server answers again");
  try {
    const doc = await api.session();
    if (state.session && doc.session?.id !== state.session.id) {
      show(await api.openSession(state.session.id));
      await refreshAudio();
      status(`reconnected: ${state.session.title} · v${state.score?.version}`);
    }
  } catch (err) {
    status(err.message, "error");
  }
}

async function start() {
  setTheme(storage("vidgen-studio-theme") || "dark");
  wireKeys();
  wireHint();
  wireConnection();
  $("theme").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
  $("yaml-toggle").addEventListener("click", () => {
    const hidden = $("work").classList.toggle("no-yaml");
    $("yaml-toggle").setAttribute("aria-pressed", String(!hidden));
  });
  wirePicker();
  wireTransport();
  initStrip(ctx);
  initTimeline(ctx);
  initTracks(ctx);
  initInspector(ctx);
  initYamlEditor(ctx);
  initVersions(ctx);
  initCheck(ctx);
  initExports(ctx);
  initNotes(ctx);
  initVariations(ctx);
  wirePanes();
  status("starting…", "busy");
  busy(1);
  try {
    [state.info, state.presets, state.patches] = await Promise.all([api.info(), api.presets(), api.patches()]);
    picker.fill(state.presets);
    const doc = await api.session();
    if (doc.session) show(doc);
    else show(await api.load(state.info.default_preset));
    showMuted();
    restoreVariations();
    await refreshAudio();
  } catch (err) {
    status(err.message, "error");
  } finally {
    busy(-1);
  }
}

start();
