// The inspector (DESIGN.md §94.13): the selected track's instrument (a change keeps what it can and
// says what changes), its settings as sliders generated from the patch catalogue (ranges, units,
// defaults, reset, help), octave / transpose / accent / play mode, its effects as chips, its step
// grid (synced both ways with the steps text) and, per section, whether it plays and what changes
// there. "Edit for" picks the whole track or one section: in a section every control writes that
// section's changes (`sections: {lift: {...}}`) and shows the track's own values where it has none.
// Every committed change is one version; a slider drag commits once, on release.

import { cellKind, gridHtml, readSteps, replaceCell, resample, writeBars } from "./stepgrid.js";
import { escapeHtml } from "./yaml_view.js";

let ctx = null;
const ui = {
  scope: null,        // the section edited, or null: the whole track
  effect: null,       // the effect chip opened
  brush: "x",         // what a click on a step writes
  steps: null,        // {key, text}: the steps being edited (before they are a version)
  change: null,       // a previewed instrument change {instrument, notes, ok}
};
const sliders = new Map();  // slider id → {field, value, commit(value), reset()}
const KINDS = [["drum", "drums and noises"], ["note", "notes"], ["pad", "pads"]];
const EFFECTS = ["echo", "reverb", "duck", "gate", "lowpass", "highpass", "width", "spread", "volume"];
const LABEL = { volume: "volume curve" };
const CURVES = ["lowpass", "highpass", "width", "volume"];
const OFF = new Set(["none", "off"]);
const ACCENTS = ["3+3+2", "3+3+3+3+2+2", "4+4+2+3+3", "4", "2", "3+3+2+3+3+2"];
const DRUM_BRUSHES = ["x", "X", "o", "-", "."];
const NOTE_BRUSHES = ["x", "*", "1", "2", "3", "4", "5", "6", "7", "8", "9", "-", "."];
const BRUSH_WORDS = {
  x: "a hit (pitched: the chord's bass note)", X: "an accented hit", o: "a soft hit", "-": "hold the step before one step longer",
  ".": "a rest", "*": "the whole chord", 8: "the root an octave up", 9: "the ninth",
};

const $ = (id) => document.getElementById(id);
const isMap = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const isOff = (v) => v === false || v === null || OFF.has(v);
const num = (v) => typeof v === "number" && Number.isFinite(v);

export function initInspector(context) {
  ctx = context;
  const box = $("inspector");
  box.addEventListener("input", onInput);
  box.addEventListener("change", onChange);
  box.addEventListener("click", onClick);
  box.addEventListener("keydown", onKey);
  box.addEventListener("pointerdown", onPointerDown);
  box.addEventListener("pointerover", onPointerOver);
  box.addEventListener("mouseover", showHelp);
  box.addEventListener("focusin", showHelp);
  document.addEventListener("pointerup", endPaint);
}

// ----- the track and its values ---------------------------------------------------------------

const current = () => ctx.outline()?.tracks.find((t) => t.name === ctx.state.selected) || null;
const specOf = (t) => (isMap(t?.spec) ? t.spec : {});
const patchOf = (t) => ctx.state.patches?.instruments.find((p) => p.name === t.instrument) || null;
const effectOf = (name) => ctx.state.patches?.effects.find((e) => e.name === name) || null;

function overrideOf(t, section) {
  const all = specOf(t).sections;
  return isMap(all) && isMap(all[section]) ? all[section] : null;
}

// The path the controls write to: the track, or its changes for the section edited.
const base = (t) => (ui.scope ? `tracks.${t.name}.sections.${ui.scope}` : `tracks.${t.name}`);
const baseDepth = () => (ui.scope ? 4 : 2);
const own = (t) => (ui.scope ? overrideOf(t, ui.scope) || {} : specOf(t));

// A key's value where the controls are: the section's own, else the track's.
function value(t, key) {
  const o = ui.scope ? overrideOf(t, ui.scope) : null;
  return o && key in o ? o[key] : specOf(t)[key];
}

const isOwn = (t, key) => key in own(t);

function settingValue(t, key, fallback) {
  const o = ui.scope ? overrideOf(t, ui.scope) : null;
  if (o && isMap(o.settings) && key in o.settings) return o.settings[key];
  const s = specOf(t).settings;
  return isMap(s) && key in s ? s[key] : fallback;
}

function trackSetting(t, key, fallback) {
  const s = specOf(t).settings;
  return isMap(s) && key in s ? s[key] : fallback;
}

const settingOwn = (t, key) => isMap(own(t).settings) && key in own(t).settings;

function stepsText(v) {
  if (Array.isArray(v)) return v.map(String).join(" | ");
  return typeof v === "string" ? v : null;
}

// ----- numbers and sliders --------------------------------------------------------------------

function niceStep(x) {
  const p = 10 ** Math.floor(Math.log10(x));
  const m = x / p;
  return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p;
}

const clean = (v) => Number(Number(v).toPrecision(12));

function niceValue(f, v) {
  v = Math.min(f.high, Math.max(f.low, v));
  if (f.integer) return Math.round(v);
  if (f.scale === "log") return clean(Number(v.toPrecision(v >= 100 ? 3 : 2)));
  const step = niceStep((f.high - f.low) / 200);
  return clean(Math.round(v / step) * step);
}

function toPos(f, v) {
  if (!num(v)) return 0;
  const p = f.scale === "log" ? Math.log(v / f.low) / Math.log(f.high / f.low) : (v - f.low) / (f.high - f.low);
  return Math.round(1000 * Math.min(1, Math.max(0, p)));
}

function fromPos(f, p) {
  const share = p / 1000;
  return niceValue(f, f.scale === "log" ? f.low * (f.high / f.low) ** share : f.low + (f.high - f.low) * share);
}

function show(v) {
  return num(v) ? String(clean(v)) : String(v);
}

// A value with its unit for reading: 3200 Hz is "3.2 kHz".
function withUnit(v, unit) {
  if (!num(v)) return String(v);
  if (unit === "Hz" && Math.abs(v) >= 1000) return `${clean(Math.round(v / 100) / 10)} kHz`;
  return unit ? `${clean(v)} ${unit}` : String(clean(v));
}

// A slider row: `id`, its catalogue field {low, high, default, unit, scale, integer, words}, the
// value shown, whether it is written here, and the help shown on hover.
function sliderHtml(id, label, f, v, { written, help, resetTitle }) {
  const unit = f.unit || "";
  const range = `${withUnit(f.low, unit)} to ${withUnit(f.high, unit)}`;
  const helpText = `${help ? help + " · " : ""}${range}${num(f.default) ? ` · default ${withUnit(f.default, unit)}` : ""}`;
  return `<div class="slider-row${written ? " written" : ""}" data-help="${escapeHtml(helpText)}">
    <label for="${id}">${escapeHtml(label)}</label>
    <span class="range-wrap"><input type="range" id="${id}" min="0" max="1000" step="1" value="${toPos(f, v)}" aria-valuetext="${escapeHtml(withUnit(v, unit))}"><i class="def" aria-hidden="true"></i></span>
    <input class="num field" id="${id}-num" value="${escapeHtml(num(v) ? show(v) : "")}" inputmode="decimal" aria-label="${escapeHtml(label)} (${escapeHtml(range)})">
    <span class="unit">${escapeHtml(unit)}</span>
    <button type="button" class="reset" data-reset="${id}" title="${escapeHtml(resetTitle || "back to the default")}" aria-label="Reset ${escapeHtml(label)}"${written ? "" : " hidden"}>↺</button>
  </div>`;
}

function register(id, entry) {
  sliders.set(id, entry);
}

// ----- drawing --------------------------------------------------------------------------------

export function showInspector() {
  const box = $("inspector");
  const t = current();
  $("inspector-track").textContent = t ? `· ${t.name} (${t.instrument})` : "";
  sliders.clear();
  if (!t) {
    box.innerHTML = '<p class="placeholder">Select a track to see its instrument and settings.</p>';
    return;
  }
  const o = ctx.outline();
  if (ui.scope && !o.sections.some((s) => s.name === ui.scope)) ui.scope = null;
  if (ui.steps && ui.steps.key !== stepsKey(t)) ui.steps = null;
  const focused = document.activeElement?.id;
  box.style.setProperty("--tc", ctx.colour(o.tracks.indexOf(t)));
  const rests = ui.scope && !t.sections.includes(ui.scope);
  box.innerHTML = [
    headHtml(t),
    scopeHtml(t, o),
    rests ? restHtml(t) : [soundHtml(t), notesHtml(t), stepsHtml(t), effectsHtml(t)].join(""),
    sectionsHtml(t, o),
  ].join("");
  dress(box, o);
  if (focused && $(focused) && box.contains($(focused))) $(focused).focus();
}

function headHtml(t) {
  const patch = patchOf(t);
  const options = KINDS.map(([kind, words]) => {
    const items = (ctx.state.patches?.instruments || []).filter((p) => p.kind === kind)
      .map((p) => `<option value="${p.name}"${p.name === t.instrument ? " selected" : ""}>${escapeHtml(p.name)}</option>`).join("");
    return `<optgroup label="${words}">${items}</optgroup>`;
  }).join("");
  const change = ui.change && ui.change.track === t.name ? changeHtml(t) : "";
  return `<div class="insp-head">
    <label class="label" for="insp-instrument">Instrument</label>
    <select class="field" id="insp-instrument" title="Change the instrument: the settings it also has are kept">${options}</select>
    <p class="words">${patch ? escapeHtml(patch.words) : ""}</p>
    ${change}
  </div>`;
}

function changeHtml(t) {
  const c = ui.change;
  const notes = c.notes.length ? `<ul>${c.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>` : "<p>Nothing else changes.</p>";
  const problem = c.ok ? "" : `<p class="problem">${escapeHtml(c.problem)}</p>`;
  return `<div class="change-card" role="group" aria-label="Instrument change">
    <p><b>${escapeHtml(t.instrument)} → ${escapeHtml(c.instrument)}</b> <span class="dim">${escapeHtml(c.words || "")}</span></p>
    ${notes}${problem}
    <div class="actions"><button type="button" class="btn small primary" id="insp-change-ok"${c.ok ? "" : " disabled"}>Change to ${escapeHtml(c.instrument)}</button>
    <button type="button" class="btn small" id="insp-change-cancel">Keep ${escapeHtml(t.instrument)}</button></div>
  </div>`;
}

function scopeHtml(t, o) {
  const tabs = [`<button type="button" role="tab" class="scope-tab" data-scope="" aria-selected="${!ui.scope}">Whole track</button>`];
  o.sections.forEach((s, i) => {
    const rests = !t.sections.includes(s.name);
    const changed = overrideOf(t, s.name) ? " changed" : "";
    tabs.push(`<button type="button" role="tab" class="scope-tab sec${rests ? " rests" : ""}${changed}" data-scope="${s.name}" data-index="${i}" aria-selected="${ui.scope === s.name}"
      title="${rests ? `${t.name} rests in ${s.name}` : `Change ${t.name} in ${s.name} only`}${changed ? " (has changes here)" : ""}">${escapeHtml(s.name)}</button>`);
  });
  const banner = ui.scope
    ? `<p class="scope-banner" data-index="${o.sections.findIndex((s) => s.name === ui.scope)}"><b>${escapeHtml(ui.scope)} only</b> — what you change here is written as ${escapeHtml(ui.scope)}'s change (<code>sections: {${escapeHtml(ui.scope)}: …}</code>); values in colour are ${escapeHtml(ui.scope)}'s own, the others the track's (↺ goes back to them).</p>`
    : "";
  return `<div class="scope" role="tablist" aria-label="Edit for">${tabs.join("")}</div>${banner}`;
}

function restHtml(t) {
  return `<div class="rest-card"><p><b>${escapeHtml(t.name)}</b> rests in <b>${escapeHtml(ui.scope)}</b>: it plays nothing there.</p>
    <button type="button" class="btn small" data-plays="${ui.scope}" data-on="1">Play in ${escapeHtml(ui.scope)}</button></div>`;
}

function group(id, title, body, extra = "") {
  return `<section class="group" id="g-${id}" aria-labelledby="g-${id}-title">
    <h3 id="g-${id}-title">${title}${extra}</h3>${body}
    <p class="problem" id="pb-${id}" role="alert" hidden></p></section>`;
}

function soundHtml(t) {
  const patch = patchOf(t);
  if (!patch) return "";
  const rows = Object.entries(patch.settings).map(([key, f]) => {
    const id = `set-${key}`;
    const v = settingValue(t, key, f.default);
    const written = settingOwn(t, key);
    const path = `${base(t)}.settings.${key}`;
    register(id, {
      field: f,
      commit: (x) => [[{ op: "set", path, value: x }], `${t.name}${ui.scope ? " in " + ui.scope : ""}: ${key} ${x}${f.unit ? " " + f.unit : ""}`],
      reset: () => [[{ op: "unset", path, keep: baseDepth() }], `${t.name}${ui.scope ? " in " + ui.scope : ""}: ${key} back to ${ui.scope ? "the track's" : "the default"}`],
    });
    const resetTitle = ui.scope ? `back to the track's (${withUnit(trackSetting(t, key, f.default), f.unit)})` : `back to the default (${withUnit(f.default, f.unit)})`;
    return sliderHtml(id, key, f, v, { written, help: f.words, resetTitle });
  });
  const mix = mixRows(t);
  return group("sound", "Sound", `${rows.join("")}<div class="divider"></div>${mix}<p class="help" id="help-sound">Hover a setting to see what it does.</p>`,
    ` <small>${escapeHtml(t.instrument)}</small>`);
}

function mixRows(t) {
  const out = [];
  const vol = value(t, "volume");
  const volField = { low: -36, high: 12, default: 0, unit: "dB", scale: "linear", integer: false };
  if (vol === undefined || num(vol)) {
    register("mix-volume", {
      field: { ...volField, low: -60, high: 24 },
      commit: (x) => [[{ op: "set", path: `${base(t)}.volume`, value: x }], `${t.name}${ui.scope ? " in " + ui.scope : ""}: volume ${x} dB`],
      reset: () => [[{ op: "unset", path: `${base(t)}.volume`, keep: baseDepth() }], `${t.name}${ui.scope ? " in " + ui.scope : ""}: volume back`],
      shown: volField,
    });
    out.push(sliderHtml("mix-volume", "volume", volField, num(vol) ? vol : 0, { written: isOwn(t, "volume"), help: "the track's level (0 = the instrument's normal level)", resetTitle: ui.scope ? "back to the track's volume" : "back to 0 dB" }));
  } else {
    out.push(`<p class="hint-row"><span class="label">volume</span> a curve — open the <b>volume curve</b> effect below</p>`);
  }
  const pan = value(t, "pan");
  const panField = { low: -1, high: 1, default: 0, unit: "", scale: "linear", integer: false };
  register("mix-pan", {
    field: panField,
    commit: (x) => [[{ op: "set", path: `${base(t)}.pan`, value: x }], `${t.name}${ui.scope ? " in " + ui.scope : ""}: pan ${x}`],
    reset: () => [[{ op: "unset", path: `${base(t)}.pan`, keep: baseDepth() }], `${t.name}${ui.scope ? " in " + ui.scope : ""}: pan back`],
  });
  out.push(sliderHtml("mix-pan", "pan", panField, num(pan) ? pan : 0, { written: isOwn(t, "pan"), help: "where the track sits: -1 left, 0 centre, 1 right", resetTitle: ui.scope ? "back to the track's pan" : "back to the centre" }));
  return out.join("");
}

function notesHtml(t) {
  const patch = patchOf(t);
  const drum = t.kind === "drum";
  const parts = [];
  if (!drum) {
    const oct = value(t, "octave");
    const fallback = ui.scope && num(specOf(t).octave) ? `the track's (${specOf(t).octave})` : `default (${patch?.octave ?? "–"})`;
    const options = [`<option value="">${fallback}</option>`]
      .concat([0, 1, 2, 3, 4, 5, 6, 7, 8].map((n) => `<option value="${n}"${isOwn(t, "octave") && oct === n ? " selected" : ""}>${n}</option>`)).join("");
    parts.push(`<span class="ctl${isOwn(t, "octave") ? " written" : ""}" data-help="The octave the notes sit in: the chord's root in that octave (C4 is middle C)">
      <label for="insp-octave">octave</label><select class="field" id="insp-octave">${options}</select></span>`);
    const tr = value(t, "transpose");
    parts.push(`<span class="ctl${isOwn(t, "transpose") ? " written" : ""}" data-help="Semitones up (or down, negative) from where the notes are written: -36 to 36">
      <label for="insp-transpose">transpose</label><input class="field num" id="insp-transpose" type="number" min="-36" max="36" step="1" value="${num(tr) ? tr : 0}"><span class="unit">st</span></span>`);
  }
  const acc = value(t, "accent");
  const list = ACCENTS.map((a) => `<option value="${a}"></option>`).join("");
  parts.push(`<span class="ctl${isOwn(t, "accent") ? " written" : ""}" data-help="Accent groups: step counts joined by +, repeated over each bar (3+3+2: accents on steps 1, 4 and 7 of every 8). Empty: none">
    <label for="insp-accent">accent</label><input class="field" id="insp-accent" list="insp-accents" value="${escapeHtml(acc === undefined ? "" : String(acc))}" placeholder="none" spellcheck="false" autocomplete="off"><datalist id="insp-accents">${list}</datalist></span>`);
  if (t.kind === "pad" && !ui.scope) {
    const chords = specOf(t).play === "chords";
    parts.push(`<span class="ctl" data-help="A pad holds the progression's chords (cross-faded), or plays steps like any other track">
      <span class="label">play</span><span class="seg" role="group" aria-label="Play mode">
      <button type="button" class="seg-btn" data-mode="chords" aria-pressed="${chords}">chords</button><button type="button" class="seg-btn" data-mode="steps" aria-pressed="${!chords}">steps</button></span></span>`);
  }
  return group("notes", drum ? "Rhythm" : "Notes", `<div class="ctl-row">${parts.join("")}</div><p class="help" id="help-notes"></p>`);
}

const stepsKey = (t) => `${ctx.state.score?.version}:${t.name}:${ui.scope || ""}`;

function currentSteps(t) {
  if (ui.steps && ui.steps.key === stepsKey(t)) return ui.steps.text;
  return stepsText(value(t, "steps"));
}

function stepsHtml(t) {
  if (specOf(t).play === "chords" && !(ui.scope && isOwn(t, "steps"))) {
    return group("steps", "Steps", `<p class="dim">Holds the progression's chords, cross-faded from one to the next. ${t.kind === "pad" && !ui.scope ? "Switch <b>play</b> to steps to write a rhythm." : ""}</p>`);
  }
  const text = currentSteps(t);
  if (text === null) {
    const sections = Object.keys(isMap(specOf(t).sections) ? specOf(t).sections : {}).join(", ");
    return group("steps", "Steps", `<p class="dim">No steps for the whole track: each section (${escapeHtml(sections)}) writes its own. Pick one above.</p>`);
  }
  const pitched = t.kind !== "drum";
  const brushes = (pitched ? NOTE_BRUSHES : DRUM_BRUSHES).map((b) =>
    `<button type="button" class="brush${b === ui.brush ? " on" : ""}" data-brush="${escapeHtml(b)}" aria-pressed="${b === ui.brush}" title="${escapeHtml(brushTitle(b))}">${escapeHtml(b)}</button>`).join("");
  const other = pitched
    ? `<input class="field brush-other" id="insp-brush" value="${escapeHtml((pitched ? NOTE_BRUSHES : DRUM_BRUSHES).includes(ui.brush) ? "" : ui.brush)}" placeholder="A4, 5', v2…" spellcheck="false" autocomplete="off" aria-label="Paint with another symbol: a note (A4), a degree an octave up (5'), a voicing note (v2), notes together (C4+E4)" title="Another symbol: a note (A4, C#5), a degree an octave up or down (5', 3,), a voicing note (v1-v9), notes together (C4+E4+G4)">`
    : "";
  const read = readSteps(text);
  const inherited = ui.scope && !isOwn(t, "steps");
  const where = inherited ? `<p class="scope-note">The track's steps — painting here gives ${escapeHtml(ui.scope)} its own.</p>` : "";
  const o = ctx.outline();
  const timeBeats = Number(String(o.time).split("/")[0]) || 4;
  const grid = read.error
    ? `<p class="problem">${escapeHtml(read.error)} — fix the text below</p>`
    : `<div class="grid" id="insp-grid" role="group" aria-label="Steps of ${escapeHtml(t.name)}: arrow keys move, type a symbol to write it">${gridHtml(read, { beats: timeBeats, accent: value(t, "accent"), pitched, idPrefix: "cell" })}</div>`;
  const bars = read.bars?.length || 0;
  const span = ui.scope ? o.sections.find((s) => s.name === ui.scope)?.bars : null;
  const loopNote = bars ? `${bars} bar${bars > 1 ? "s" : ""}${span ? `, repeated over ${escapeHtml(ui.scope)}'s ${span}` : ", repeated over each section it plays in"}` : "";
  return group("steps", "Steps", `${where}
    <div class="palette" role="toolbar" aria-label="Paint with">${brushes}${other}</div>
    ${grid}
    <div class="grid-tools">
      <button type="button" class="btn small" id="insp-add-bar" title="Add a bar (a copy of the last)">+ bar</button>
      <button type="button" class="btn small" id="insp-del-bar" title="Remove the last bar"${bars > 1 ? "" : " disabled"}>− bar</button>
      <span class="dim">${loopNote}</span>
    </div>
    <input class="field steps-text" id="insp-steps" value="${escapeHtml(text)}" spellcheck="false" autocomplete="off" aria-label="Steps of ${escapeHtml(t.name)} as text">`,
  ` <small>${pitched ? "x X o hits · 1-9 degrees · notes · * chord · - hold · . rest" : "x hit · X accent · o soft · - hold · . rest"}</small>`);
}

function brushTitle(b) {
  if (BRUSH_WORDS[b]) return BRUSH_WORDS[b];
  return /^[1-7]$/.test(b) ? `degree ${b} of the chord (${["", "root", "2nd", "3rd", "4th", "5th", "6th", "7th"][b]})` : b;
}

// ----- effects ----------------------------------------------------------------------------------

function effectPresent(t, name) {
  const v = value(t, name);
  if (v === undefined || isOff(v)) return false;
  return name === "volume" ? !num(v) : true;
}

function asFields(name, v) {
  if (isMap(v)) return { ...v };
  if (name === "duck") return { to: v === true ? "kick" : String(v) };
  if (name === "gate") return { steps: String(v) };
  if (name === "echo") return num(v) ? { delay: v } : {};
  if (name === "reverb") return num(v) ? { mix: v } : {};
  return {};
}

function curveText(v, unit) {
  if (num(v)) return withUnit(v, unit);
  if (isMap(v)) {
    const [a, b] = [withUnit(v.from, unit), withUnit(v.to, unit)];
    const [ua, ub] = [a.split(" ")[1], b.split(" ")[1]];
    return ua && ua === ub ? `${a.split(" ")[0]}→${b}` : `${a}→${b}`;
  }
  if (Array.isArray(v)) return `${v.length} points`;
  return String(v);
}

function summary(name, v) {
  if (CURVES.includes(name)) return curveText(v, name === "volume" ? "dB" : name === "width" ? "" : "Hz");
  if (name === "spread") return String(v);
  const f = asFields(name, v);
  if (name === "echo") return `${f.delay ?? 0.75} beat ×${f.repeats ?? 2}`;
  if (name === "reverb") return `${f.size ?? 1.8} s · ${Math.round((f.mix ?? 0.2) * 100)} %`;
  if (name === "duck") return `→ ${f.to ?? "kick"} ${Math.round((f.depth ?? 0.45) * 100)} %`;
  if (name === "gate") return String(f.steps ?? "").slice(0, 10);
  return "";
}

function effectsHtml(t) {
  const present = EFFECTS.filter((n) => effectPresent(t, n));
  if (ui.effect && !present.includes(ui.effect)) ui.effect = null;
  const offHere = ui.scope ? EFFECTS.filter((n) => isOwn(t, n) && isOff(own(t)[n])) : [];
  const chips = present.map((n) => {
    const mine = !ui.scope || isOwn(t, n);
    return `<span class="fx${mine ? "" : " inherited"}${ui.effect === n ? " open" : ""}">
      <button type="button" class="fx-open" data-fx="${n}" aria-expanded="${ui.effect === n}" title="${mine ? "Edit" : `The track's ${LABEL[n] || n}: editing gives ${ui.scope} its own`}">${escapeHtml(LABEL[n] || n)} <small>${escapeHtml(summary(n, value(t, n)))}</small></button>
      <button type="button" class="fx-x" data-remove="${n}" aria-label="Remove ${escapeHtml(LABEL[n] || n)}" title="${ui.scope && specOf(t)[n] !== undefined && !isOff(specOf(t)[n]) ? `Switch it off in ${ui.scope}` : "Remove"}">×</button></span>`;
  });
  for (const n of offHere) {
    chips.push(`<span class="fx off"><span class="fx-open">${escapeHtml(LABEL[n] || n)} <small>off here</small></span>
      <button type="button" class="fx-x" data-restore="${n}" aria-label="Use the track's ${escapeHtml(n)} in ${escapeHtml(ui.scope)}" title="Use the track's ${escapeHtml(n)} again">↺</button></span>`);
  }
  const addable = EFFECTS.filter((n) => !present.includes(n) && !offHere.includes(n));
  const add = `<select class="field add-fx" id="insp-add-fx" aria-label="Add an effect"><option value="">+ effect</option>${addable
    .map((n) => `<option value="${n}">${escapeHtml(LABEL[n] || n)}</option>`).join("")}</select>`;
  const editor = ui.effect ? effectEditor(t, ui.effect) : "";
  const none = present.length || offHere.length ? "" : '<span class="dim">none</span>';
  return group("effects", "Effects", `<div class="fx-row">${chips.join("")}${none}${add}</div>${editor}<p class="help" id="help-effects"></p>`);
}

function effectEditor(t, name) {
  const effect = effectOf(name);
  const words = effect ? `<p class="fx-words">${escapeHtml(effect.words)}</p>` : "";
  if (CURVES.includes(name)) return `<div class="fx-editor">${words}${curveEditor(t, name)}</div>`;
  if (name === "spread") {
    const f = { ...effect.fields.value, unit: "", scale: "linear", integer: false };
    register("fx-spread", {
      field: f,
      commit: (x) => [[{ op: "set", path: `${base(t)}.spread`, value: x }], `${t.name}${scopeWords()}: spread ${x}`],
    });
    return `<div class="fx-editor">${words}${sliderHtml("fx-spread", "spread", f, value(t, "spread"), { written: false, help: effect.fields.value.words })}</div>`;
  }
  const fields = asFields(name, value(t, name));
  const rows = [];
  for (const [key, f] of Object.entries(effect.fields)) {
    const v = key in fields ? fields[key] : f.default;
    const written = key in fields && isMap(own(t)[name]);
    if (f.low !== null && f.low !== undefined) {
      const id = `fx-${name}-${key}`;
      register(id, {
        field: f,
        commit: (x) => [fieldOps(t, name, key, x), `${t.name}${scopeWords()}: ${name} ${key} ${x}`],
        reset: () => [[{ op: "unset", path: `${base(t)}.${name}.${key}`, keep: baseDepth() + 1 }], `${t.name}${scopeWords()}: ${name} ${key} default`],
      });
      rows.push(sliderHtml(id, key, f, v, { written, help: f.words, resetTitle: `back to the default (${withUnit(f.default, f.unit)})` }));
    } else if (key === "to") {
      const tracks = ctx.outline().tracks.map((x) => x.name).filter((n) => n !== t.name);
      const options = [...tracks, "beat"].map((n) => `<option value="${n}"${n === v ? " selected" : ""}>${n === "beat" ? "every beat" : escapeHtml(n)}</option>`).join("");
      rows.push(`<div class="field-row" data-help="${escapeHtml(f.words)}"><label for="fx-duck-to">under</label><select class="field" id="fx-duck-to">${options}</select></div>`);
    } else if (typeof f.default === "boolean") {
      rows.push(`<div class="field-row" data-help="${escapeHtml(f.words)}"><label class="check-label"><input type="checkbox" id="fx-${name}-${key}" data-fx-bool="${name}.${key}"${v ? " checked" : ""}> ${escapeHtml(key)}</label></div>`);
    } else if (key === "steps") {
      rows.push(gateSteps(t, String(v ?? "")));
    }
  }
  return `<div class="fx-editor">${words}${rows.join("")}</div>`;
}

function gateSteps(t, text) {
  const read = readSteps(text);
  const cells = read.error ? `<p class="problem">${escapeHtml(read.error)}</p>`
    : `<div class="grid mini" id="gate-grid">${read.bars.map((bar, b) => `<div class="cells">${bar.map((c, k) => {
      const { kind } = cellKind(c.text);
      return `<button type="button" class="cell ${kind}" data-gate="${b}-${k}" title="gate step ${k + 1}: ${escapeHtml(c.text)} (click: open / closed)" aria-label="gate bar ${b + 1} step ${k + 1}: ${escapeHtml(c.text)}"><span></span></button>`;
    }).join("")}</div>`).join("")}</div>`;
  return `<div class="field-row gate-row" data-help="The gate's pattern: x or X opens it fully, o halfway, - keeps it open a step longer, . closed">
    <label for="fx-gate-steps">pattern</label>${cells}
    <input class="field steps-text" id="fx-gate-steps" value="${escapeHtml(text)}" spellcheck="false" autocomplete="off"></div>`;
}

const scopeWords = () => (ui.scope ? ` in ${ui.scope}` : "");

// The edits that set effect `name`'s field `key`: in place when the effect is written as a
// mapping here, else the whole effect (the shorthand, or the track's copied into the section).
function fieldOps(t, name, key, x) {
  const mine = own(t)[name];
  if (isMap(mine)) return [{ op: "set", path: `${base(t)}.${name}.${key}`, value: x }];
  const fields = asFields(name, value(t, name));
  fields[key] = x;
  return [{ op: "set", path: `${base(t)}.${name}`, value: fields }];
}

function curveEditor(t, name) {
  const effect = effectOf(name);
  const f = { ...effect.fields.value };
  if (name === "volume") Object.assign(f, { unit: "dB", scale: "linear", integer: false, default: 0 });
  if (name === "width") Object.assign(f, { unit: "", scale: "linear", integer: false });
  const v = value(t, name);
  const mode = num(v) ? "fixed" : isMap(v) ? "ramp" : "points";
  const modes = ["fixed", "ramp", "points"].filter((m) => name !== "volume" || m !== "fixed")
    .map((m) => `<button type="button" class="seg-btn" data-curve="${name}" data-mode="${m}" aria-pressed="${m === mode}">${m === "ramp" ? "ramp over the section" : m === "points" ? "points" : "fixed"}</button>`).join("");
  let body = "";
  const path = `${base(t)}.${name}`;
  const label = (x) => `${t.name}${scopeWords()}: ${LABEL[name] || name} ${curveText(x, f.unit)}`;
  if (mode === "fixed") {
    register(`fx-${name}`, { field: f, commit: (x) => [[{ op: "set", path, value: x }], label(x)] });
    body = sliderHtml(`fx-${name}`, name, f, v, { written: false, help: f.words });
  } else if (mode === "ramp") {
    for (const end of ["from", "to"]) {
      register(`fx-${name}-${end}`, {
        field: f,
        commit: (x) => {
          const next = { from: v.from, to: v.to, [end]: x };
          return [[isMap(own(t)[name]) ? { op: "set", path: `${path}.${end}`, value: x } : { op: "set", path, value: next }], label(next)];
        },
      });
      body += sliderHtml(`fx-${name}-${end}`, end, f, v[end], { written: false, help: end === "from" ? "at the section's start" : "at the section's end" });
    }
  } else {
    const text = JSON.stringify(v).replace(/,/g, ", ").replace(/\[\[/, "[[");
    body = `<div class="field-row" data-help="[bar, value] points: bars from the section's start (fractions allowed), straight between them"><label for="fx-${name}-points">points</label>
      <input class="field steps-text" id="fx-${name}-points" data-points="${name}" value="${escapeHtml(text)}" spellcheck="false" autocomplete="off"></div>`;
  }
  const preview = mode === "fixed" ? "" : curveSvg(v, f);
  return `<div class="seg curve-modes" role="group" aria-label="${escapeHtml(name)}: how it moves">${modes}</div>${preview}${body}`;
}

// A small drawing of a ramp or points curve over the section (bars along, the value up; a
// frequency in octaves).
function curveSvg(v, f) {
  const section = ui.scope ? ctx.outline().sections.find((s) => s.name === ui.scope) : null;
  let points = isMap(v) ? [[0, v.from], [section?.bars || 1, v.to]] : Array.isArray(v) ? v.filter((p) => Array.isArray(p) && p.length === 2) : [];
  points = points.filter((p) => num(p[0]) && num(p[1]));
  if (points.length < 2) return "";
  const span = Math.max(section?.bars || 0, points.at(-1)[0], 1);
  const y = (val) => {
    const share = f.scale === "log" ? Math.log(val / f.low) / Math.log(f.high / f.low) : (val - f.low) / (f.high - f.low);
    return (28 - 26 * Math.min(1, Math.max(0, share))).toFixed(2);
  };
  const xs = (bar) => ((100 * bar) / span).toFixed(2);
  const line = [[0, points[0][1]], ...points, [span, points.at(-1)[1]]].map(([b, val]) => `${xs(b)},${y(val)}`).join(" ");
  const label = `${points.map(([b, val]) => `bar ${b}: ${withUnit(val, f.unit)}`).join(", ")}`;
  return `<svg class="curve-preview" viewBox="0 0 100 30" preserveAspectRatio="none" role="img" aria-label="${escapeHtml(label)}"><polyline points="${line}"></polyline></svg>
    <p class="curve-axis"><span>bar 0</span><span>${escapeHtml(label)}</span><span>bar ${span}</span></p>`;
}

// The value an effect starts with when added.
function effectDefault(t, name) {
  const o = ctx.outline();
  const beats = Number(String(o.time).split("/")[0]) || 4;
  const vol = num(value(t, "volume")) ? value(t, "volume") : 0;
  const kick = o.tracks.find((x) => x.name !== t.name && x.instrument === "kick");
  return {
    echo: { delay: 0.75, feedback: 0.35, repeats: 2 },
    reverb: { size: 1.8, mix: 0.2 },
    duck: { to: kick ? kick.name : "beat", depth: 0.45, release: 0.15 },
    gate: { steps: Array(beats).fill("x.x.").join(" "), duty: 0.55 },
    lowpass: 2000,
    highpass: 200,
    width: 1.4,
    spread: 0.25,
    volume: { from: vol - 12, to: vol },
  }[name];
}

function curveEnd(v) {
  if (num(v)) return v;
  if (isMap(v)) return v.to;
  if (Array.isArray(v) && v.length) return v.at(-1)[1];
  return 0;
}

function removeOps(t, name) {
  const path = `${base(t)}.${name}`;
  const inherited = ui.scope && specOf(t)[name] !== undefined && !isOff(specOf(t)[name]);
  if (name === "volume") return [{ op: "set", path, value: curveEnd(value(t, name)) }];
  if (inherited) return [{ op: "set", path, value: "none" }];
  return [{ op: "unset", path, keep: baseDepth() }];
}

// ----- the sections table -----------------------------------------------------------------------

function changesText(change) {
  return Object.entries(change).map(([k, v]) => {
    if (k === "settings" && isMap(v)) return Object.keys(v).join(", ");
    if (k === "steps") return "own steps";
    if (isOff(v)) return `no ${k}`;
    if (CURVES.includes(k)) return `${k} ${curveText(v, k === "volume" ? "dB" : k === "width" ? "" : "Hz")}`;
    return k;
  }).join(" · ");
}

function sectionsHtml(t, o) {
  const listed = specOf(t).only !== undefined ? "only" : "rest";
  const rows = o.sections.map((s, i) => {
    const plays = t.sections.includes(s.name);
    const change = overrideOf(t, s.name);
    const text = !plays ? '<span class="dim">rests</span>' : change ? escapeHtml(changesText(change)) : '<span class="dim">as the whole track</span>';
    return `<tr data-row="${s.name}" class="${ui.scope === s.name ? "current" : ""}${plays ? "" : " resting"}">
      <th scope="row"><i class="dot" data-index="${i}"></i>${escapeHtml(s.name)} <small>${s.bars} bar${s.bars > 1 ? "s" : ""}</small></th>
      <td><label class="switch" title="${plays ? `Rest in ${s.name}` : `Play in ${s.name}`}"><input type="checkbox" data-plays="${s.name}"${plays ? " checked" : ""} aria-label="${escapeHtml(t.name)} plays in ${escapeHtml(s.name)}"><span></span></label></td>
      <td class="changes">${text}</td>
      <td class="row-actions">${change ? `<button type="button" class="icon-btn" data-clear="${s.name}" title="Remove ${escapeHtml(s.name)}'s changes" aria-label="Remove the changes in ${escapeHtml(s.name)}">×</button>` : ""}
        <button type="button" class="btn small" data-scope="${s.name}"${plays ? "" : " disabled"}>${ui.scope === s.name ? "editing" : "edit"}</button></td></tr>`;
  });
  return group("sections", "Per section", `<table class="sec-table"><thead><tr><th>Section</th><th>Plays</th><th>Changes there</th><th></th></tr></thead><tbody>${rows.join("")}</tbody></table>
    <p class="dim small">A section switched off is a rest (written as <code>${listed}:</code>). <b>edit</b> changes the track in that section only.</p>`);
}

// After drawing: what CSS cannot be given inline (the page's CSP): default ticks and colours.
function dress(box, o) {
  for (const [id, s] of sliders) {
    const tick = $(id)?.parentElement?.querySelector(".def");
    const f = s.shown || s.field;
    if (tick && f.default !== null && f.default !== undefined && num(f.default)) tick.style.left = `${toPos(f, f.default) / 10}%`;
    else if (tick) tick.hidden = true;
  }
  for (const el of box.querySelectorAll(".scope-tab.sec, .dot, .scope-banner")) {
    const index = Number(el.dataset.index);
    if (Number.isInteger(index) && index >= 0) el.style.setProperty("--sec", ctx.colour(index));
  }
}

// ----- events ---------------------------------------------------------------------------------

function problemAt(groupId, r) {
  const el = $(`pb-${groupId}`);
  if (!el) return;
  if (r.ok) {
    el.hidden = true;
    return;
  }
  const p = r.problems?.[0] || { message: "not changed" };
  el.textContent = `${p.where ? p.where + ": " : ""}${p.message}`;
  el.hidden = false;
}

// Commit `ops` as one version; a problem is shown in the group the control is in (and the
// controls go back to the version's values).
async function send(ops, label, from) {
  const groupId = from?.closest?.(".group")?.id?.slice(2) || null;
  const r = await ctx.commit(ops, label);
  if (!r.ok) {
    showInspector();
    if (groupId) problemAt(groupId, r);
  }
  return r;
}

const timers = new Map();

function onInput(e) {
  const el = e.target;
  if (el.type === "range" && sliders.has(el.id)) {
    const s = sliders.get(el.id);
    const v = fromPos(s.shown || s.field, Number(el.value));
    $(`${el.id}-num`).value = show(v);
    el.setAttribute("aria-valuetext", withUnit(v, s.field.unit));
    el.closest(".slider-row")?.classList.add("moving");
  } else if (el.id === "insp-steps") {
    previewSteps(el.value);
  }
}

function onChange(e) {
  const el = e.target;
  const t = current();
  if (!t) return;
  if (el.type === "range" && sliders.has(el.id)) {
    // one version per drag (the release), and keyboard steps a moment after the last one
    clearTimeout(timers.get(el.id));
    timers.set(el.id, setTimeout(() => commitSlider(el.id, fromPos(sliders.get(el.id).shown || sliders.get(el.id).field, Number(el.value)), el), 350));
    return;
  }
  if (el.classList.contains("num") && el.id.endsWith("-num") && sliders.has(el.id.slice(0, -4))) {
    const v = Number(el.value.replace(",", "."));
    if (el.value.trim() === "" || !Number.isFinite(v)) {
      problemAt(el.closest(".group").id.slice(2), { ok: false, problems: [{ where: "", message: `${el.value || "nothing"} is not a number` }] });
      return;
    }
    commitSlider(el.id.slice(0, -4), v, el);
    return;
  }
  if (el.id === "insp-instrument") return previewInstrument(t, el.value);
  if (el.id === "insp-octave") {
    const ops = el.value === "" ? [{ op: "unset", path: `${base(t)}.octave`, keep: baseDepth() }] : [{ op: "set", path: `${base(t)}.octave`, value: Number(el.value) }];
    return send(ops, `${t.name}${scopeWords()}: octave ${el.value || "default"}`, el);
  }
  if (el.id === "insp-transpose") {
    const v = Number(el.value);
    const ops = el.value === "" || (v === 0 && !ui.scope) ? [{ op: "unset", path: `${base(t)}.transpose`, keep: baseDepth() }] : [{ op: "set", path: `${base(t)}.transpose`, value: v }];
    return send(ops, `${t.name}${scopeWords()}: transpose ${el.value || 0}`, el);
  }
  if (el.id === "insp-accent") {
    const text = el.value.trim();
    const ops = text === "" ? [{ op: "unset", path: `${base(t)}.accent`, keep: baseDepth() }] : [{ op: "set", path: `${base(t)}.accent`, value: text }];
    return send(ops, `${t.name}${scopeWords()}: accent ${text || "none"}`, el);
  }
  if (el.id === "insp-steps") return commitSteps(t, el.value.trim(), el);
  if (el.id === "insp-brush") {
    const sym = el.value.trim();
    const read = readSteps(sym);
    if (!sym) return;
    if (read.error || read.bars.length !== 1 || read.bars[0].length !== 1) {
      problemAt("steps", { ok: false, problems: [{ where: "", message: `'${sym}' is not one step: a note (A4), a degree (5', 3,), a voicing note (v2) or notes joined by + (C4+E4)` }] });
      return;
    }
    ui.brush = sym;
    for (const b of document.querySelectorAll("#inspector .brush")) b.classList.remove("on");
    problemAt("steps", { ok: true });
    return;
  }
  if (el.id === "insp-add-fx" && el.value) {
    const name = el.value;
    ui.effect = name;
    return send([{ op: "set", path: `${base(t)}.${name}`, value: effectDefault(t, name) }], `${t.name}${scopeWords()}: + ${LABEL[name] || name}`, el);
  }
  if (el.id === "fx-duck-to") return send(fieldOps(t, "duck", "to", el.value), `${t.name}${scopeWords()}: duck under ${el.value}`, el);
  if (el.dataset.fxBool) {
    const [name, key] = el.dataset.fxBool.split(".");
    return send(fieldOps(t, name, key, el.checked), `${t.name}${scopeWords()}: ${name} ${key} ${el.checked}`, el);
  }
  if (el.id === "fx-gate-steps") return send(fieldOps(t, "gate", "steps", el.value.trim()), `${t.name}${scopeWords()}: gate pattern`, el);
  if (el.dataset.points) {
    let points;
    try {
      points = JSON.parse(el.value);
    } catch {
      problemAt("effects", { ok: false, problems: [{ where: "", message: "write the points as [[bar, value], ...], e.g. [[0, 800], [8, 3200]]" }] });
      return;
    }
    return send([{ op: "set", path: `${base(t)}.${el.dataset.points}`, value: points }], `${t.name}${scopeWords()}: ${el.dataset.points} points`, el);
  }
  if (el.dataset.plays) return send([{ op: "section_plays", track: t.name, section: el.dataset.plays, plays: el.checked }], null, el);
  if (el.classList.contains("count")) return resizeBar(t, Number(el.dataset.bar), Number(el.value), el);
}

function commitSlider(id, v, el) {
  const s = sliders.get(id);
  if (!s) return;
  const [ops, label] = s.commit(v);
  send(ops, label, el);
}

function onClick(e) {
  const t = current();
  if (!t) return;
  const el = e.target.closest("button");
  if (!el || el.disabled) return;
  if (el.dataset.reset && sliders.get(el.dataset.reset)?.reset) {
    const [ops, label] = sliders.get(el.dataset.reset).reset();
    return send(ops, label, el);
  }
  if (el.dataset.scope !== undefined && el.dataset.scope !== null && (el.classList.contains("scope-tab") || el.closest(".sec-table"))) {
    ui.scope = el.dataset.scope || null;
    ui.steps = null;
    showInspector();
    if (ui.scope && ctx.state.loop !== ui.scope) ctx.status(`editing ${t.name} in ${ui.scope} only · click ${ui.scope} on the timeline to loop it`);
    return;
  }
  if (el.id === "insp-change-ok") {
    const name = ui.change.instrument;
    ui.change = null;
    return send([{ op: "change_instrument", track: t.name, instrument: name }], null, el);
  }
  if (el.id === "insp-change-cancel") {
    ui.change = null;
    return showInspector();
  }
  if (el.dataset.mode && el.closest("#g-notes")) {
    return send([{ op: "play_mode", track: t.name, mode: el.dataset.mode }], null, el);
  }
  if (el.dataset.curve) return switchCurve(t, el.dataset.curve, el.dataset.mode, el);
  if (el.dataset.brush !== undefined) {
    ui.brush = el.dataset.brush;
    for (const b of document.querySelectorAll("#inspector .brush")) {
      b.classList.toggle("on", b === el);
      b.setAttribute("aria-pressed", String(b === el));
    }
    const other = $("insp-brush");
    if (other) other.value = "";
    return;
  }
  if (el.dataset.gate) return toggleGate(t, el);
  if (el.id === "insp-add-bar" || el.id === "insp-del-bar") return changeBars(t, el.id === "insp-add-bar", el);
  if (el.dataset.fx) {
    ui.effect = ui.effect === el.dataset.fx ? null : el.dataset.fx;
    return showInspector();
  }
  if (el.dataset.remove) {
    const name = el.dataset.remove;
    if (ui.effect === name) ui.effect = null;
    return send(removeOps(t, name), `${t.name}${scopeWords()}: − ${LABEL[name] || name}`, el);
  }
  if (el.dataset.restore) return send([{ op: "unset", path: `${base(t)}.${el.dataset.restore}`, keep: baseDepth() }], `${t.name}${scopeWords()}: the track's ${el.dataset.restore}`, el);
  if (el.dataset.clear) return send([{ op: "unset", path: `tracks.${t.name}.sections.${el.dataset.clear}` }], `${t.name}: no changes in ${el.dataset.clear}`, el);
  if (el.dataset.plays) return send([{ op: "section_plays", track: t.name, section: el.dataset.plays, plays: el.dataset.on === "1" }], null, el);
}

function showHelp(e) {
  const row = e.target.closest?.("[data-help]");
  const g = e.target.closest?.(".group");
  if (!row || !g) return;
  const help = g.querySelector(".help");
  if (help) help.textContent = row.dataset.help;
}

// ----- the instrument -------------------------------------------------------------------------

async function previewInstrument(t, name) {
  const r = await ctx.check([{ op: "change_instrument", track: t.name, instrument: name }]);
  const patch = ctx.state.patches?.instruments.find((p) => p.name === name);
  const p = r.problems?.[0];
  ui.change = { track: t.name, instrument: name, words: patch?.words, notes: r.notes || [], ok: r.ok, problem: p ? `${p.where ? p.where + ": " : ""}${p.message}` : "" };
  showInspector();
  $("insp-change-ok")?.focus();
}

// ----- curves -----------------------------------------------------------------------------------

function switchCurve(t, name, mode, el) {
  const v = value(t, name);
  const start = num(v) ? v : isMap(v) ? v.from : Array.isArray(v) && v.length ? v[0][1] : 0;
  const end = curveEnd(v);
  const bars = ui.scope ? ctx.outline().sections.find((s) => s.name === ui.scope)?.bars || 4 : 4;
  const next = mode === "fixed" ? end : mode === "ramp" ? { from: start, to: end } : [[0, start], [bars, end]];
  return send([{ op: "set", path: `${base(t)}.${name}`, value: next }], `${t.name}${scopeWords()}: ${LABEL[name] || name} ${mode}`, el);
}

function toggleGate(t, el) {
  const [b, k] = el.dataset.gate.split("-").map(Number);
  const text = String(asFields("gate", value(t, "gate")).steps || "");
  const read = readSteps(text);
  if (read.error) return;
  const cell = read.bars[b][k];
  const next = replaceCell(text, cell, cell.text === "." || cell.text === "-" ? "x" : ".");
  return send(fieldOps(t, "gate", "steps", next), `${t.name}${scopeWords()}: gate pattern`, el);
}

// ----- the step grid --------------------------------------------------------------------------

const paint = { on: false, symbol: null, text: null, t: null };

function workingText(t) {
  return currentSteps(t) ?? "";
}

// Show `text` in the grid (and the text field) without making a version yet.
function setWorking(t, text) {
  ui.steps = { key: stepsKey(t), text };
  const grid = $("insp-grid");
  const read = readSteps(text);
  if (grid && !read.error) {
    const focused = document.activeElement?.id;
    const beats = Number(String(ctx.outline().time).split("/")[0]) || 4;
    grid.innerHTML = gridHtml(read, { beats, accent: value(t, "accent"), pitched: t.kind !== "drum", idPrefix: "cell" });
    if (focused && $(focused)) $(focused).focus();
    rove(focused && $(focused)?.classList.contains("cell") ? $(focused) : grid.querySelector(".cell"));
  }
  const field = $("insp-steps");
  if (field && document.activeElement !== field) field.value = text;
}

function previewSteps(text) {
  const t = current();
  if (!t) return;
  const read = readSteps(text.trim());
  ui.steps = { key: stepsKey(t), text: text.trim() };
  if (read.error) {
    problemAt("steps", { ok: false, problems: [{ where: "", message: read.error }] });
    return;
  }
  problemAt("steps", { ok: true });
  setWorking(t, text.trim());
}

async function commitSteps(t, text, el) {
  const before = stepsText(value(t, "steps"));
  if (text === before && (!ui.scope || isOwn(t, "steps"))) {
    ui.steps = null;
    return;
  }
  const r = await send([{ op: "set", path: `${base(t)}.steps`, value: text }], `${t.name}${scopeWords()}: steps`, el);
  if (!r.ok) {
    ui.steps = null;
    showInspector();
    problemAt("steps", r);
  }
}

function cellAt(t, el) {
  const read = readSteps(workingText(t));
  if (read.error) return null;
  return read.bars[Number(el.dataset.bar)]?.[Number(el.dataset.step)] || null;
}

function onPointerDown(e) {
  const el = e.target.closest(".cell[data-bar]");
  const t = current();
  if (!el || !t || e.button !== 0) return;
  e.preventDefault();
  const cell = cellAt(t, el);
  if (!cell) return;
  paint.on = true;
  paint.t = t;
  paint.symbol = cell.text === ui.brush ? "." : ui.brush;
  paint.text = workingText(t);
  paintCell(el);
  el.focus();
}

function onPointerOver(e) {
  if (!paint.on) return;
  const el = e.target.closest(".cell[data-bar]");
  if (el) paintCell(el);
}

function paintCell(el) {
  const t = paint.t;
  const cell = cellAt(t, el);
  if (!cell || cell.text === paint.symbol) return;
  setWorking(t, replaceCell(workingText(t), cell, paint.symbol));
}

function endPaint() {
  if (!paint.on) return;
  paint.on = false;
  const t = paint.t;
  const text = workingText(t);
  if (text !== paint.text) commitSteps(t, text, $("insp-grid"));
}

// Arrow keys move between cells (one tab stop: the grid), a symbol key writes it; the edits of a
// burst of keys become one version 0.7 s after the last.
let keyTimer = 0;
function onKey(e) {
  const el = e.target;
  if (!el.classList?.contains("cell") || !el.dataset.bar) return;
  const t = current();
  const b = Number(el.dataset.bar);
  const k = Number(el.dataset.step);
  const move = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] }[e.key];
  if (move) {
    e.preventDefault();
    let target = $(`cell-${b + move[0]}-${move[0] ? 0 : k + move[1]}`);
    if (move[0] && target) target = $(`cell-${b + move[0]}-${Math.min(k, target.parentElement.children.length - 1)}`);
    if (!target && move[1]) target = move[1] > 0 ? $(`cell-${b + 1}-0`) : el.parentElement.closest(".bar-row")?.previousElementSibling?.querySelector(".cell:last-child");
    if (target) rove(target, true);
    return;
  }
  let symbol = null;
  if (e.key === "Backspace" || e.key === "Delete") symbol = ".";
  else if (e.key === "Enter" || e.key === " ") symbol = cellAt(t, el)?.text === ui.brush ? "." : ui.brush;
  else if (/^[xXo.\-*]$/.test(e.key) || (t.kind !== "drum" && /^[1-9]$/.test(e.key))) symbol = e.key;
  if (symbol === null) return;
  e.preventDefault();
  const cell = cellAt(t, el);
  if (!cell) return;
  setWorking(t, replaceCell(workingText(t), cell, symbol));
  const next = $(`cell-${b}-${k + 1}`) || $(`cell-${b + 1}-0`);
  if (next && symbol !== ui.brush) rove(next, true);
  clearTimeout(keyTimer);
  keyTimer = setTimeout(() => commitSteps(t, workingText(t), $("insp-grid")), 700);
}

function rove(cell, focus = false) {
  if (!cell) return;
  for (const c of document.querySelectorAll("#insp-grid .cell[tabindex='0']")) c.tabIndex = -1;
  cell.tabIndex = 0;
  if (focus) cell.focus();
}

function barsOf(t) {
  const read = readSteps(workingText(t));
  return read.error ? null : read.bars.map((bar) => bar.map((c) => c.text));
}

function changeBars(t, add, el) {
  const bars = barsOf(t);
  if (!bars) return;
  const text = workingText(t);
  if (add) {
    const last = text.lastIndexOf("|");
    const lastBar = (last < 0 ? text : text.slice(last + 1)).trim();
    return commitSteps(t, `${text.trimEnd()} | ${lastBar}`, el);
  }
  if (bars.length < 2) return;
  return commitSteps(t, text.slice(0, text.lastIndexOf("|")).trimEnd(), el);
}

function resizeBar(t, b, count, el) {
  const bars = barsOf(t);
  if (!bars || !bars[b] || bars[b].length === count) return;
  const sustain = t.kind !== "drum" || ["riser", "static"].includes(t.instrument);
  const beats = Number(String(ctx.outline().time).split("/")[0]) || 4;
  const read = readSteps(workingText(t));
  const text = workingText(t);
  // only this bar is rewritten; the rest of the text stays as written
  const first = read.bars[b][0].start;
  const end = read.bars[b].at(-1).end;
  const bar = writeBars([resample(bars[b], count, sustain)], beats);
  return commitSteps(t, text.slice(0, first) + bar + text.slice(end), el);
}

// ----- the playhead in the grid -----------------------------------------------------------------

let lastNow = null;
export function tickInspector(seconds, section, playing) {
  const t = current();
  const grid = $("insp-grid");
  let id = null;
  if (playing && t && grid && section && t.sections.includes(section.name)) {
    const showsHere = ui.scope ? ui.scope === section.name : !(overrideOf(t, section.name) && "steps" in overrideOf(t, section.name));
    const read = showsHere ? readSteps(workingText(t)) : { error: true };
    if (!read.error) {
      const o = ctx.outline();
      const into = Math.max(0, seconds - section.start) / o.bar_seconds;
      const bar = Math.floor(into) % read.bars.length;
      const step = Math.floor((into - Math.floor(into)) * read.bars[bar].length);
      id = `cell-${bar}-${step}`;
    }
  }
  const now = id ? $(id) : null;
  if (id === lastNow && (!now || now.classList.contains("now"))) return;
  for (const el of document.querySelectorAll("#insp-grid .cell.now")) el.classList.remove("now");
  now?.classList.add("now");
  lastNow = id;
}

