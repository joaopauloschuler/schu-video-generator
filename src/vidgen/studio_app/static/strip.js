// The song strip (DESIGN.md §94.12): key, tempo and seed edited in place, the chord progression
// as Roman numerals with each chord's name (the chord playing lit), for the section looped or
// under the playhead: its own progression when it has one, else the score's. Clicking the
// chords edits them as text, with the names shown live while typing.

import { escapeHtml } from "./yaml_view.js";

const TONICS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
const MODES = ["major", "minor", "dorian", "phrygian", "lydian", "mixolydian"];

let ctx = null;
let shownSection = null; // the section whose chords the strip shows
let editing = false;

export function initStrip(context) {
  ctx = context;
  const tonic = document.getElementById("f-tonic");
  const mode = document.getElementById("f-mode");
  tonic.innerHTML = TONICS.map((t) => `<option>${t}</option>`).join("");
  mode.innerHTML = MODES.map((m) => `<option>${m}</option>`).join("");
  const setKey = () => commitField(`key ${tonic.value} ${mode.value}`, "key", `${tonic.value} ${mode.value}`);
  tonic.addEventListener("change", setKey);
  mode.addEventListener("change", setKey);
  for (const [id, path, low, high] of [["f-tempo", "tempo", 40, 240], ["f-seed", "seed", 0, 2 ** 31 - 1]]) {
    const input = document.getElementById(id);
    input.addEventListener("change", () => {
      const value = Number(input.value);
      if (input.value.trim() === "" || !Number.isFinite(value) || value < low || value > high || (path === "seed" && !Number.isInteger(value))) {
        ctx.problem(`${path}: ${path === "seed" ? "a whole number" : "a number"} from ${low} to ${high}`);
        showFacts();
        return;
      }
      commitField(`${path} ${value}`, path, value);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") input.blur();
    });
  }
  const chords = document.getElementById("chords");
  chords.addEventListener("click", editChords);
  chords.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      editChords();
    }
  });
}

function commitField(label, path, value) {
  ctx.commit([{ op: "set", path, value }], label).then((r) => {
    if (!r.ok) showFacts();
  });
}

export function showFacts() {
  const outline = ctx.outline();
  const tonic = document.getElementById("f-tonic");
  const mode = document.getElementById("f-mode");
  for (const el of [tonic, mode, document.getElementById("f-tempo"), document.getElementById("f-seed")]) el.disabled = !outline;
  document.getElementById("f-time").textContent = outline ? outline.time : "–";
  document.getElementById("f-bars").textContent = outline ? `${outline.bars} · ${ctx.clock(outline.seconds)}` : "–";
  if (!outline) return;
  const [t, m] = outline.key.split(" ");
  if (![...tonic.options].some((o) => o.value === t)) tonic.insertAdjacentHTML("beforeend", `<option>${escapeHtml(t)}</option>`);
  tonic.value = t;
  mode.value = m;
  const tempo = document.getElementById("f-tempo");
  if (document.activeElement !== tempo) tempo.value = String(outline.tempo);
  const seed = document.getElementById("f-seed");
  if (document.activeElement !== seed) seed.value = String(outline.seed);
  shownSection = null;
  showChords(ctx.activeSection(), true);
}

// ----- the chords ------------------------------------------------------------------------------

function progressionOf(section) {
  const outline = ctx.outline();
  if (section?.progression) return section.progression;
  return outline?.progression || null;
}

function chips(progression) {
  if (!progression) return '<span class="dim">no chords (drums only) — click to add a progression</span>';
  return progression.chords
    .map((c, i) => `<span class="chord" data-i="${i}" title="${escapeHtml(c.symbol)}"><b>${escapeHtml(c.numeral)}</b><small>${escapeHtml(c.name)}</small></span>`)
    .join("");
}

// Show the chords of `section` (when it changed, or `force`).
export function showChords(section, force = false) {
  if (editing || (!force && section?.name === shownSection)) return;
  shownSection = section?.name ?? null;
  const outline = ctx.outline();
  const label = document.getElementById("chords-label");
  const hint = document.getElementById("chords-hint");
  const box = document.getElementById("chords");
  if (!outline) {
    box.innerHTML = "";
    label.textContent = "Chords";
    hint.textContent = "";
    return;
  }
  const own = Boolean(section?.own_progression);
  label.innerHTML = own ? `Chords <span class="sec-tag">${escapeHtml(section.name)}</span>` : "Chords";
  box.innerHTML = chips(progressionOf(section));
  box.classList.toggle("own", own);
  if (own) {
    hint.textContent = `${section.name}'s own chords`;
  } else {
    const others = outline.sections.filter((s) => s.own_progression).map((s) => s.name);
    hint.textContent = others.length ? `${others.join(", ")} ${others.length > 1 ? "have their own — loop one" : "has its own — loop it"} to see` : "";
  }
  hint.classList.remove("error");
}

// Light the chord playing at moment `seconds` of `section`.
export function tickChords(section, seconds) {
  showChords(section);
  if (editing || !section) return;
  const progression = progressionOf(section);
  if (!progression) return;
  let into = seconds - section.start;
  let slot = 0;
  for (const length of section.chord_seconds) {
    if (into < length) break;
    into -= length;
    slot += 1;
  }
  const now = slot % progression.chords.length;
  for (const chip of document.getElementById("chords").children) chip.classList.toggle("now", Number(chip.dataset.i) === now);
}

function editChords() {
  const outline = ctx.outline();
  if (!outline || editing) return;
  const section = ctx.activeSection();
  const own = Boolean(section?.own_progression);
  const index = outline.sections.indexOf(section);
  const path = own && outline.sections_written ? `sections[${index}].progression` : "progression";
  const progression = progressionOf(section);
  const box = document.getElementById("chords");
  const input = document.getElementById("chords-input");
  const hint = document.getElementById("chords-hint");
  editing = true;
  box.hidden = true;
  input.hidden = false;
  input.value = progression?.text || "";
  input.focus();
  const voicings = progression?.written === "voicings";
  const baseHint = voicings ? "typing replaces the written voicings (notes, bass) with plain chords" : "Roman numerals of the key (i VI III VII) or chord names (Am F C G)";
  hint.textContent = baseHint;
  let valid = true;
  let timer = 0;
  let check = Promise.resolve();
  const ops = () => (input.value.trim() ? [{ op: "set", path, value: input.value.trim() }] : [{ op: "delete", path }]);
  const preview = (r) => {
    valid = r.ok;
    input.setAttribute("aria-invalid", String(!r.ok));
    hint.classList.toggle("error", !r.ok);
    if (!r.ok) {
      const p = r.problems[0];
      hint.textContent = `${p.where ? p.where + ": " : ""}${p.message}`;
      return;
    }
    const s = r.outline.sections[index] ?? r.outline.sections[0];
    const p = (own ? s?.progression : r.outline.progression) || s?.progression;
    hint.textContent = p ? `→ ${p.chords.map((c) => c.name).join("  ")}` : baseHint;
  };
  const onInput = () => {
    clearTimeout(timer);
    timer = setTimeout(() => { check = ctx.check(ops()).then(preview); }, 200);
  };
  let done = false;
  const finish = async (keep) => {
    if (done) return;
    done = true;
    clearTimeout(timer);
    if (keep && input.value.trim() !== (progression?.text || "")) {
      const r = await ctx.commit(ops(), own ? `${section.name}: chords ${input.value.trim()}` : `chords ${input.value.trim()}`);
      if (!r.ok) {
        done = false;
        preview(r);
        input.focus();
        return;
      }
    }
    input.removeEventListener("input", onInput);
    input.removeEventListener("keydown", onKey);
    input.removeEventListener("blur", onBlur);
    input.hidden = true;
    box.hidden = false;
    editing = false;
    showChords(ctx.activeSection(), true);
    box.focus();
  };
  const onKey = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      check.then(() => finish(true));
    } else if (e.key === "Escape") {
      e.preventDefault();
      finish(false);
    }
  };
  const onBlur = () => setTimeout(() => {
    if (done || document.activeElement === input) return;
    if (!valid) ctx.status("the chords were not kept (they have a problem); the last good ones play", "error");
    finish(valid);
  }, 120);
  input.addEventListener("input", onInput);
  input.addEventListener("keydown", onKey);
  input.addEventListener("blur", onBlur);
}
