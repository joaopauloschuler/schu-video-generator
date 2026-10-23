// The track list (DESIGN.md §94.12): per track mute / solo (a listening aid: what plays, never
// the score), a volume bar and a pan knob (they edit the score), the steps text edited in place
// with its problems shown under it, a level meter while playing, delete; [+ track] with an
// instrument picker.

import { escapeHtml } from "./yaml_view.js";

const VOLUME_LOW = -30;  // dB at the bar's left end
const VOLUME_HIGH = 6;   // dB at its right end
const PAN_STEP = 0.05;

let ctx = null;
const meters = new Map(); // track name → shown level (0..1), smoothed

export function initTracks(context) {
  ctx = context;
  const list = document.getElementById("tracks");
  list.addEventListener("click", onClick);
  list.addEventListener("keydown", onKey);
  list.addEventListener("pointerdown", onPointerDown);
  list.addEventListener("dblclick", (e) => {
    const pan = e.target.closest(".pan");
    if (pan) commitPan(pan.closest(".track").dataset.name, 0);
  });
  wireInstrumentMenu();
}

const track = (name) => ctx.outline()?.tracks.find((t) => t.name === name);

// The tracks left out of what plays: the muted ones, and with any solo every track not soloed.
export function mutedTracks() {
  const names = (ctx.outline()?.tracks || []).map((t) => t.name);
  const { mute, solo } = ctx.state;
  return names.filter((n) => mute.has(n) || (solo.size > 0 && !solo.has(n)));
}

// ----- drawing -------------------------------------------------------------------------------

function volumeShare(volume) {
  return Math.max(0, Math.min(1, (volume - VOLUME_LOW) / (VOLUME_HIGH - VOLUME_LOW)));
}

const dB = (v) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(Number.isInteger(v) ? 0 : 1)} dB`;
const panText = (p) => (Math.abs(p) < 1e-9 ? "centre" : `${Math.round(Math.abs(p) * 100)} % ${p < 0 ? "left" : "right"}`);

export function showTracks() {
  const outline = ctx.outline();
  const list = document.getElementById("tracks");
  if (list.querySelector(".pattern-input")) return; // never under a person typing; shown after
  if (!outline) {
    list.innerHTML = '<p class="placeholder">No score open.</p>';
    return;
  }
  const names = new Set(outline.tracks.map((t) => t.name));
  for (const set of [ctx.state.mute, ctx.state.solo]) for (const n of [...set]) if (!names.has(n)) set.delete(n);
  list.innerHTML = "";
  outline.tracks.forEach((t, i) => {
    const row = document.createElement("div");
    row.className = "track";
    row.setAttribute("role", "listitem");
    row.tabIndex = 0;
    row.dataset.name = t.name;
    row.setAttribute("aria-selected", String(t.name === ctx.state.selected));
    row.style.setProperty("--tc", ctx.colour(i));
    const curve = typeof t.volume !== "number";
    const volume = curve ? 0 : t.volume;
    const pan = typeof t.pan === "number" ? t.pan : 0;
    const chords = t.plays === "chords";
    row.innerHTML = `
      <span class="meter" aria-hidden="true"><i></i></span>
      <span class="name">${escapeHtml(t.name)}<small>${escapeHtml(t.instrument)}</small></span>
      <span class="ms">
        <button class="mute" aria-pressed="${ctx.state.mute.has(t.name)}" aria-label="Mute ${escapeHtml(t.name)}" title="Mute: leave ${escapeHtml(t.name)} out of what plays (the score keeps it)">M</button>
        <button class="solo" aria-pressed="${ctx.state.solo.has(t.name)}" aria-label="Solo ${escapeHtml(t.name)}" title="Solo: play only the soloed tracks (the score keeps them all)">S</button>
      </span>
      <span class="vol${curve ? " curve" : ""}" role="slider" tabindex="${curve ? -1 : 0}" aria-label="Volume of ${escapeHtml(t.name)}"
        aria-valuemin="${VOLUME_LOW}" aria-valuemax="${VOLUME_HIGH}" aria-valuenow="${volume}" aria-valuetext="${curve ? "a volume curve" : dB(volume)}"
        ${curve ? 'aria-disabled="true" title="The volume changes over time (a curve): edit it in the score file"' : `title="Volume ${dB(volume)}: drag, or arrow keys"`}><i></i><b>${curve ? "curve" : dB(volume)}</b></span>
      <span class="pan" role="slider" tabindex="0" aria-label="Pan of ${escapeHtml(t.name)}" aria-valuemin="-1" aria-valuemax="1" aria-valuenow="${pan}"
        aria-valuetext="${panText(pan)}" title="Pan ${panText(pan)}: drag up or down, arrow keys; double-click for the centre"><i></i></span>
      <span class="pattern${chords ? " chords" : ""}" ${chords ? 'title="Holds the chords (play: chords)"' : `role="button" tabindex="0" title="${escapeHtml(t.steps)} — click to edit the steps"`}>${chords ? "holds the chords" : escapeHtml(t.steps)}</span>
      <button class="del" aria-label="Delete track ${escapeHtml(t.name)}" title="Delete the track (a new version; the old one stays)"${outline.tracks.length < 2 ? " disabled" : ""}>×</button>
      <span class="problem" role="alert" hidden></span>`;
    row.querySelector(".vol i").style.width = `${(volumeShare(volume) * 100).toFixed(1)}%`;
    row.querySelector(".pan i").style.transform = `rotate(${Math.round(pan * 135)}deg)`;
    list.appendChild(row);
  });
  showMuted();
}

export function showMuted() {
  const muted = new Set(mutedTracks());
  for (const row of document.getElementById("tracks").querySelectorAll(".track")) {
    const name = row.dataset.name;
    row.classList.toggle("muted", muted.has(name));
    row.querySelector(".mute").setAttribute("aria-pressed", String(ctx.state.mute.has(name)));
    row.querySelector(".solo").setAttribute("aria-pressed", String(ctx.state.solo.has(name)));
  }
  document.getElementById("mute-note").textContent = muted.size ? `· listening without ${[...muted].join(", ")} (the score keeps ${muted.size > 1 ? "them" : "it"})` : "";
}

// ----- clicks and keys -----------------------------------------------------------------------

function onClick(e) {
  const row = e.target.closest(".track");
  if (!row || e.target.closest(".pattern-input")) return;
  const name = row.dataset.name;
  if (e.target.closest(".mute") || e.target.closest(".solo")) {
    const set = e.target.closest(".mute") ? ctx.state.mute : ctx.state.solo;
    if (set.has(name)) set.delete(name);
    else set.add(name);
    showMuted();
    ctx.refreshAudio();
    return;
  }
  if (e.target.closest(".del")) {
    ctx.commit([{ op: "delete_track", name }]);
    return;
  }
  ctx.selectTrack(name);
  const pattern = e.target.closest(".pattern");
  if (pattern && !pattern.classList.contains("chords")) editPattern(row);
}

function onKey(e) {
  if (e.target.closest(".pattern-input")) return;
  const row = e.target.closest(".track");
  if (!row) return;
  const name = row.dataset.name;
  if (e.target.closest(".vol") && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) {
    const t = track(name);
    if (typeof t?.volume !== "number") return;
    e.preventDefault();
    e.stopPropagation();
    nudge(row, "vol", t.volume + (["ArrowRight", "ArrowUp"].includes(e.key) ? 1 : -1));
    return;
  }
  if (e.target.closest(".pan") && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) {
    const t = track(name);
    e.preventDefault();
    e.stopPropagation();
    nudge(row, "pan", (Number(t?.pan) || 0) + (["ArrowRight", "ArrowUp"].includes(e.key) ? 0.1 : -0.1));
    return;
  }
  if (e.target.closest(".pattern") && (e.key === "Enter" || e.key === " ")) {
    e.preventDefault();
    ctx.selectTrack(name);
    if (!e.target.closest(".pattern").classList.contains("chords")) editPattern(row);
    return;
  }
  if (e.target !== row) return;
  if (e.key === "Enter" || e.key === " ") ctx.selectTrack(name);
  else if (e.key === "ArrowDown") row.nextElementSibling?.focus();
  else if (e.key === "ArrowUp") row.previousElementSibling?.focus();
  else if (e.key === "Delete") ctx.commit([{ op: "delete_track", name }]);
  else return;
  e.preventDefault();
}

// Keyboard steps: shown at once, written 0.6 s after the last key.
const pending = new Map();
function nudge(row, what, value) {
  const name = row.dataset.name;
  if (what === "vol") value = Math.max(VOLUME_LOW, Math.min(VOLUME_HIGH, Math.round(value)));
  else value = roundPan(value);
  drawControl(row, what, value);
  clearTimeout(pending.get(row.dataset.name + what));
  pending.set(name + what, setTimeout(() => (what === "vol" ? commitVolume(name, value) : commitPan(name, value)), 600));
}

const roundPan = (p) => Number(Math.max(-1, Math.min(1, Math.round(p / PAN_STEP) * PAN_STEP)).toFixed(2)) || 0;

function drawControl(row, what, value) {
  if (what === "vol") {
    const vol = row.querySelector(".vol");
    vol.querySelector("i").style.width = `${(volumeShare(value) * 100).toFixed(1)}%`;
    vol.querySelector("b").textContent = dB(value);
    vol.setAttribute("aria-valuenow", String(value));
    vol.setAttribute("aria-valuetext", dB(value));
  } else {
    const pan = row.querySelector(".pan");
    pan.querySelector("i").style.transform = `rotate(${Math.round(value * 135)}deg)`;
    pan.setAttribute("aria-valuenow", String(value));
    pan.setAttribute("aria-valuetext", panText(value));
    pan.dataset.value = panText(value);
  }
}

function commitVolume(name, value) {
  const t = track(name);
  if (!t || t.volume === value) return;
  ctx.commit([{ op: "set", path: `tracks.${name}.volume`, value }], `${name}: volume ${dB(value)}`);
}

function commitPan(name, value) {
  const t = track(name);
  if (!t || Number(t.pan || 0) === value) return;
  ctx.commit([{ op: "set", path: `tracks.${name}.pan`, value }], `${name}: pan ${panText(value)}`);
}

// ----- dragging the volume bar and the pan knob ----------------------------------------------

function onPointerDown(e) {
  const control = e.target.closest(".vol:not(.curve), .pan");
  if (!control || e.button !== 0) return;
  e.preventDefault();
  const row = control.closest(".track");
  const name = row.dataset.name;
  const isVol = control.classList.contains("vol");
  const t = track(name);
  const start = { x: e.clientY, value: isVol ? t.volume : Number(t.pan) || 0 };
  let value = start.value;
  const box = control.getBoundingClientRect();
  const at = (ev) => {
    if (isVol) return Math.round(2 * (VOLUME_LOW + ((ev.clientX - box.left) / box.width) * (VOLUME_HIGH - VOLUME_LOW))) / 2;
    return roundPan(start.value - (ev.clientY - start.x) / 80);
  };
  const move = (ev) => {
    value = isVol ? Math.max(VOLUME_LOW, Math.min(VOLUME_HIGH, at(ev))) : at(ev);
    drawControl(row, isVol ? "vol" : "pan", value);
  };
  if (isVol) move(e);
  control.setPointerCapture(e.pointerId);
  control.classList.add("active");
  control.addEventListener("pointermove", move);
  const end = () => {
    control.removeEventListener("pointermove", move);
    control.classList.remove("active");
    if (value !== start.value) (isVol ? commitVolume : commitPan)(name, value);
  };
  control.addEventListener("pointerup", end, { once: true });
  control.addEventListener("pointercancel", end, { once: true });
}

// ----- the steps text, edited in place ---------------------------------------------------------

function editPattern(row) {
  const name = row.dataset.name;
  const t = track(name);
  const cell = row.querySelector(".pattern");
  if (!t || row.querySelector(".pattern-input")) return;
  const input = document.createElement("input");
  input.className = "field pattern-input";
  input.value = t.steps;
  input.spellcheck = false;
  input.autocomplete = "off";
  input.setAttribute("aria-label", `Steps of ${name}`);
  cell.replaceWith(input);
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
  const problem = row.querySelector(".problem");
  let valid = true;
  let timer = 0;
  let check = Promise.resolve();
  const ops = () => [{ op: "set", path: `tracks.${name}.steps`, value: input.value.trim() }];
  const showProblem = (r) => {
    valid = r.ok;
    const p = r.problems?.[0];
    problem.hidden = r.ok;
    problem.textContent = r.ok ? "" : `${p.where ? p.where + ": " : ""}${p.message}`;
    input.setAttribute("aria-invalid", String(!r.ok));
  };
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => { check = ctx.check(ops()).then(showProblem); }, 250);
  });
  let done = false;
  const finish = async (keep) => {
    if (done) return;
    done = true;
    clearTimeout(timer);
    const text = input.value.trim();
    if (keep && text !== t.steps) {
      const r = await ctx.commit(ops(), `${name}: steps`);
      if (!r.ok) {
        done = false;
        showProblem(r);
        input.focus();
        return;
      }
    }
    problem.hidden = true;
    input.replaceWith(cell);
    showTracks();
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      check.then(() => finish(true));
    } else if (e.key === "Escape") {
      e.preventDefault();
      finish(false);
    }
  });
  input.addEventListener("blur", () => setTimeout(() => {
    if (done || document.activeElement === input) return;
    if (!valid) {
      ctx.status(`${name}: the steps were not kept (they have a problem); the last good ones play`, "error");
      finish(false);
    } else {
      finish(true);
    }
  }, 120));
}

// ----- meters ----------------------------------------------------------------------------------

// A rough level from the score (Step 196 measures the stems): the step under the playhead, its
// gain (accents louder), decaying after the hit, times the track's volume.
function levelAt(t, outline, section, seconds) {
  if (!section || !t.sections.includes(section.name)) return 0;
  const volume = typeof t.volume === "number" ? t.volume : 0;
  const gain = Math.min(1, 10 ** (volume / 40));
  const levels = t.levels?.[section.name];
  if (!levels) return 0.55 * gain; // a pad holding the chords
  const bar = outline.bar_seconds;
  const into = Math.max(0, seconds - section.start);
  const index = Math.floor(into / bar);
  const steps = levels[index % levels.length];
  const pos = ((into / bar) - index) * steps.length;
  let k = Math.floor(pos);
  while (k >= 0 && steps[k] === -1) k--;
  if (k < 0 || steps[k] === 0) return 0;
  const since = ((pos - k) * bar) / steps.length;
  const tau = t.kind === "drum" ? 0.11 : 0.32;
  return Math.min(1, 0.8 * steps[k] * gain * Math.exp(-since / tau));
}

export function tickMeters(seconds, section, playing) {
  const outline = ctx.outline();
  if (!outline) return;
  const muted = new Set(mutedTracks());
  for (const row of document.getElementById("tracks").querySelectorAll(".track")) {
    const t = track(row.dataset.name);
    if (!t) continue;
    const target = playing && !muted.has(t.name) ? levelAt(t, outline, section, seconds) : 0;
    const shown = meters.get(t.name) || 0;
    const level = target > shown ? target : shown * 0.86 + target * 0.14;
    meters.set(t.name, level < 0.01 ? 0 : level);
    row.querySelector(".meter i").style.height = `${(level * 100).toFixed(1)}%`;
  }
}

// ----- [+ track] -------------------------------------------------------------------------------

const KIND_WORDS = { drum: "drums and hits", note: "notes", pad: "pads (hold the chords)" };

function wireInstrumentMenu() {
  const button = document.getElementById("add-track");
  const list = document.getElementById("instrument-list");
  const open = () => {
    fillInstruments();
    // fixed, above the button: the track list's panel scrolls and would clip it
    const box = button.getBoundingClientRect();
    list.style.left = `${Math.max(8, Math.min(box.left, window.innerWidth - Math.min(620, window.innerWidth * 0.94) - 8))}px`;
    const above = box.top > window.innerHeight / 2;
    list.style.top = above ? "auto" : `${box.bottom + 4}px`;
    list.style.bottom = above ? `${window.innerHeight - box.top + 4}px` : "auto";
    list.style.maxHeight = `${Math.max(200, (above ? box.top : window.innerHeight - box.bottom) - 16)}px`;
    list.hidden = false;
    button.setAttribute("aria-expanded", "true");
    activate(list.querySelector("li"));
    list.focus();
  };
  const close = (focus = true) => {
    list.hidden = true;
    button.setAttribute("aria-expanded", "false");
    if (focus) button.focus();
  };
  const choose = (li) => {
    close();
    const instrument = li.dataset.name;
    ctx.commit([{ op: "add_track", instrument }]).then((r) => {
      if (r.ok) ctx.selectTrack(r.score.outline.tracks.at(-1).name);
    });
  };
  const activate = (li) => {
    if (!li) return;
    for (const item of list.querySelectorAll("li[role=option]")) item.classList.toggle("active", item === li);
    list.setAttribute("aria-activedescendant", li.id);
    li.scrollIntoView({ block: "nearest" });
  };
  button.addEventListener("click", () => (list.hidden ? open() : close()));
  list.addEventListener("click", (e) => {
    const li = e.target.closest("li[role=option]");
    if (li) choose(li);
  });
  list.addEventListener("mousemove", (e) => activate(e.target.closest("li[role=option]")));
  list.addEventListener("keydown", (e) => {
    const items = [...list.querySelectorAll("li[role=option]")];
    const k = items.indexOf(list.querySelector("li.active"));
    if (e.key === "ArrowDown") activate(items[(k + 1) % items.length]);
    else if (e.key === "ArrowUp") activate(items[(k - 1 + items.length) % items.length]);
    else if (e.key === "Enter" && k >= 0) choose(items[k]);
    else if (e.key === "Escape") close();
    else return;
    e.preventDefault();
  });
  document.addEventListener("click", (e) => {
    if (!list.hidden && !e.target.closest(".add-wrap")) close(false);
  });
}

function fillInstruments() {
  const list = document.getElementById("instrument-list");
  if (list.children.length) return;
  const instruments = ctx.state.patches?.instruments || [];
  let html = "";
  for (const kind of ["drum", "note", "pad"]) {
    html += `<li class="group" role="presentation">${KIND_WORDS[kind]}</li>`;
    for (const p of instruments.filter((i) => i.kind === kind)) {
      html += `<li role="option" id="instrument-${p.name}" data-name="${p.name}" aria-selected="false">
        <span class="name">${escapeHtml(p.name)}</span><span class="line">${escapeHtml(p.words)}</span></li>`;
    }
  }
  list.innerHTML = html;
}
