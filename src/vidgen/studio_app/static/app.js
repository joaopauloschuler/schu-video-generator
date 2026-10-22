// vidgen studio, the page (DESIGN.md §94.5): the top bar's preset picker, the song strip and
// transport, the timeline, the track list, the inspector (read-only until Step 195), the score
// file and the status line. State lives on the server (the session); this file shows it.

import { api } from "./api.js";
import { Player } from "./player.js";
import { escapeHtml, showYaml } from "./yaml_view.js";

const $ = (id) => document.getElementById(id);
const PALETTE = ["--c1", "--c2", "--c3", "--c4"];

const state = {
  presets: [],
  patches: null,
  info: null,
  session: null,
  score: null,     // {version, text, outline, problems, render_key}
  render: null,    // the last render's result
  selected: null,  // the selected track's name
  rendering: null, // the promise of a render in progress
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
    show(await api.load(name));
    await renderCurrent();
  } catch (err) {
    status(err.message, "error");
  }
}

// ----- showing the score ------------------------------------------------------------------

function show(doc) {
  state.session = doc.session;
  state.score = doc.score;
  const outline = state.score?.outline;
  picker.mark(state.session?.preset);
  $("version-name").textContent = state.score ? `v${state.score.version}` : "v–";
  $("yaml-name").textContent = state.session ? `· ${state.session.title} · v${state.score?.version ?? "–"}` : "";
  showFacts(outline);
  showTimeline(outline);
  if (outline && !outline.tracks.some((t) => t.name === state.selected)) state.selected = outline.tracks[0]?.name ?? null;
  showTracks(outline);
  showInspector();
  const bad = new Set((state.score?.problems || []).map((p) => p.line).filter(Boolean));
  showYaml($("yaml"), state.score?.text || "", bad);
}

function showFacts(outline) {
  $("f-key").textContent = outline ? outline.key : "–";
  $("f-tempo").textContent = outline ? `${outline.tempo} BPM` : "–";
  $("f-time").textContent = outline ? outline.time : "–";
  $("f-seed").textContent = outline ? outline.seed : "–";
  $("f-bars").textContent = outline ? `${outline.bars} · ${clock(outline.seconds)}` : "–";
  $("f-roman").textContent = outline?.progression || "";
  showChords(0);
}

function sectionAt(seconds) {
  const sections = state.score?.outline?.sections || [];
  let found = sections[0];
  for (const s of sections) if (s.start <= seconds) found = s;
  return found;
}

function showChords(seconds) {
  const section = sectionAt(seconds);
  if (!section) {
    $("f-chords").textContent = "";
    return;
  }
  const names = section.chords.filter((c, i) => i === 0 || c !== section.chords[i - 1]);
  const text = names.join(" ");
  if ($("f-chords").textContent !== text) $("f-chords").textContent = state.score.outline.progression ? `(${text})` : text;
}

function showTimeline(outline) {
  const timeline = $("timeline");
  for (const el of timeline.querySelectorAll(".section, .empty")) el.remove();
  const loop = $("loop");
  loop.innerHTML = '<option value="">whole</option>';
  if (!outline) {
    timeline.insertAdjacentHTML("afterbegin", '<span class="empty">pick a preset</span>');
    return;
  }
  outline.sections.forEach((s, i) => {
    const el = document.createElement("div");
    el.className = "section";
    el.dataset.name = s.name;
    el.style.flexGrow = String(s.bars);
    el.style.flexBasis = "0";
    el.style.setProperty("--sec", colour(i));
    el.title = `${s.name}: bars ${s.first_bar}–${s.first_bar + s.bars - 1}, ${s.key}, from ${clock(s.start)}`;
    el.innerHTML = `<span class="name">${escapeHtml(s.name)}</span><span class="bars">${s.bars} bars · ${escapeHtml(s.key)}</span>`;
    timeline.insertBefore(el, $("playhead"));
    loop.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(s.name)}" disabled>${escapeHtml(s.name)} (Step 194)</option>`);
  });
}

function volumeShare(volume) {
  if (typeof volume !== "number") return 0.6;
  return Math.max(0.05, Math.min(1, (volume + 30) / 36)); // -30 dB .. +6 dB
}

function showTracks(outline) {
  const list = $("tracks");
  if (!outline) {
    list.innerHTML = '<p class="placeholder">No score open.</p>';
    return;
  }
  list.innerHTML = "";
  outline.tracks.forEach((t, i) => {
    const row = document.createElement("div");
    row.className = "track";
    row.setAttribute("role", "listitem");
    row.tabIndex = 0;
    row.dataset.name = t.name;
    row.setAttribute("aria-selected", String(t.name === state.selected));
    row.style.setProperty("--tc", colour(i));
    const pan = typeof t.pan === "number" ? t.pan : 0;
    row.innerHTML = `
      <span class="dot" aria-hidden="true"></span>
      <span class="name">${escapeHtml(t.name)}<small>${t.instrument === t.name ? "&nbsp;" : escapeHtml(t.instrument)}</small></span>
      <span class="ms"><button disabled title="Mute (Step 194)">M</button><button disabled title="Solo (Step 194)">S</button></span>
      <span class="vol" title="volume ${typeof t.volume === "number" ? t.volume + " dB" : "(a curve)"}"><i></i></span>
      <span class="pan" title="pan ${pan}"><i></i></span>
      <span class="pattern" title="${escapeHtml(t.steps)}">${escapeHtml(t.steps)}</span>`;
    row.querySelector(".vol i").style.width = `${Math.round(volumeShare(t.volume) * 100)}%`;
    row.querySelector(".pan i").style.transform = `rotate(${Math.round(pan * 135)}deg)`;
    list.appendChild(row);
  });
}

function selectTrack(name) {
  state.selected = name;
  for (const row of $("tracks").children) row.setAttribute("aria-selected", String(row.dataset.name === name));
  showInspector();
}

function showInspector() {
  const box = $("inspector");
  const track = state.score?.outline?.tracks.find((t) => t.name === state.selected);
  $("inspector-track").textContent = track ? `· ${track.name}` : "";
  if (!track) {
    box.innerHTML = '<p class="placeholder">Select a track to see its instrument and settings.</p>';
    return;
  }
  const index = state.score.outline.tracks.indexOf(track);
  box.style.setProperty("--tc", colour(index));
  const patch = state.patches?.instruments.find((p) => p.name === track.instrument);
  const written = track.settings || {};
  const settings = patch
    ? Object.entries(patch.settings)
        .map(([name, s]) => {
          const value = written[name] ?? s.default;
          return `<div class="setting" title="${escapeHtml(s.words)}">
            <label for="set-${name}">${escapeHtml(name)}</label>
            <input type="range" id="set-${name}" min="${s.low}" max="${s.high}" step="any" value="${value}" disabled>
            <output>${value}</output></div>`;
        })
        .join("")
    : "";
  const effects = track.effects.length ? track.effects.map((e) => `<span class="chip">${escapeHtml(e)}</span>`).join("") : '<span class="dim">none</span>';
  box.innerHTML = `
    <dl>
      <dt>instrument</dt><dd><b>${escapeHtml(track.instrument)}</b>${patch ? ` <span class="dim">— ${escapeHtml(patch.words)}</span>` : ""}</dd>
      <dt>plays</dt><dd>${track.plays === "chords" ? "the chords (held)" : `<span class="mono">${escapeHtml(track.steps)}</span>`}</dd>
      <dt>sections</dt><dd>${track.sections.map(escapeHtml).join(", ")}</dd>
      <dt>effects</dt><dd class="chips">${effects}</dd>
    </dl>
    ${settings}
    <p class="note">Editing the settings, octave, accent, effects and steps comes in Step 195.</p>`;
}

// ----- rendering and playback -------------------------------------------------------------

async function renderCurrent() {
  if (!state.score || state.score.problems.length) return null;
  if (state.rendering) return state.rendering;
  const version = state.score.version;
  status(`rendering v${version}…`, "busy");
  state.rendering = api
    .render(version)
    .then((r) => {
      state.render = r;
      player.setSource(r.url, r.loop);
      const how = r.cached ? "from the cache" : `rendered in ${r.render_seconds.toFixed(1)} s`;
      status(`v${r.version} ${how} · ${clock(r.seconds)} · ${r.loudness.toFixed(1)} LUFS in a video, plays at ${(r.loudness + r.audition_gain_db).toFixed(0)} here`);
      return r;
    })
    .catch((err) => {
      status(err.message, "error");
      return null;
    })
    .finally(() => {
      state.rendering = null;
    });
  return state.rendering;
}

function onTick(seconds) {
  const duration = player.duration || state.render?.seconds || state.score?.outline?.seconds || 0;
  $("time").textContent = `${clock(seconds)} / ${clock(duration)}`;
  if (!seeking) $("seek").value = duration ? String(Math.round((seconds / duration) * 1000)) : "0";
  const piece = state.score?.outline?.seconds || duration;
  const share = piece ? Math.min(1, (seconds % (piece + 1e-9)) / piece) : 0;
  $("playhead").style.left = `calc(${(share * 100).toFixed(3)}% - 1px)`;
  const section = sectionAt(seconds);
  for (const el of $("timeline").querySelectorAll(".section")) el.classList.toggle("current", el.dataset.name === section?.name);
  showChords(seconds);
}

function onPlayState(playing) {
  $("play").setAttribute("aria-pressed", String(playing));
  $("play").setAttribute("aria-label", playing ? "Pause" : "Play");
}

const player = new Player($("audio"), onTick, onPlayState);
let seeking = false;

async function togglePlay() {
  if (player.playing) return player.pause();
  if (!player.url) await renderCurrent();
  return player.play();
}

function wireTransport() {
  $("play").addEventListener("click", togglePlay);
  $("stop").addEventListener("click", () => player.stop());
  const seek = $("seek");
  seek.addEventListener("input", () => {
    seeking = true;
    const duration = player.duration || state.render?.seconds || 0;
    $("time").textContent = `${clock((seek.value / 1000) * duration)} / ${clock(duration)}`;
  });
  seek.addEventListener("change", () => {
    seeking = false;
    player.seek((seek.value / 1000) * (player.duration || 0));
  });
  $("timeline").addEventListener("click", (e) => {
    const box = $("timeline").getBoundingClientRect();
    const share = (e.clientX - box.left) / box.width;
    player.seek(share * (state.score?.outline?.seconds || 0));
  });
  $("tracks").addEventListener("click", (e) => {
    const row = e.target.closest(".track");
    if (row) selectTrack(row.dataset.name);
  });
  $("tracks").addEventListener("keydown", (e) => {
    const row = e.target.closest(".track");
    if (!row) return;
    if (e.key === "Enter" || e.key === " ") selectTrack(row.dataset.name);
    else if (e.key === "ArrowDown") row.nextElementSibling?.focus();
    else if (e.key === "ArrowUp") row.previousElementSibling?.focus();
    else return;
    e.preventDefault();
  });
}

// ----- start --------------------------------------------------------------------------------

async function start() {
  setTheme(storage("vidgen-studio-theme") || "dark");
  $("theme").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
  $("yaml-toggle").addEventListener("click", () => {
    const hidden = $("work").classList.toggle("no-yaml");
    $("yaml-toggle").setAttribute("aria-pressed", String(!hidden));
  });
  wirePicker();
  wireTransport();
  status("starting…", "busy");
  try {
    [state.info, state.presets, state.patches] = await Promise.all([api.info(), api.presets(), api.patches()]);
    picker.fill(state.presets);
    const doc = await api.session();
    if (doc.session) show(doc);
    else show(await api.load(state.info.default_preset));
    await renderCurrent();
  } catch (err) {
    status(err.message, "error");
  }
}

start();
