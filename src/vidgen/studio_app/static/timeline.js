// The timeline (DESIGN.md §94.12): the sections coloured and sized by their bars, the playhead,
// the energy curve (the render's loudness bar by bar), a section's right edge dragged to change
// its bars, a section's name clicked to loop it, and the section bar below it (rename, bars,
// its own chords, add, remove).

import { escapeHtml } from "./yaml_view.js";

const MAX_BARS = 64; // the most bars a drag or the bars field gives one section

let ctx = null;
let drag = null; // {section, index, startX, startBars, pxPerBar, bars}

export function initTimeline(context) {
  ctx = context;
  const timeline = document.getElementById("timeline");
  timeline.addEventListener("click", (e) => {
    if (drag || e.target.closest(".edge")) return;
    const name = e.target.closest(".sec-name");
    if (name) {
      const section = name.closest(".section").dataset.name;
      ctx.state.selectedSection = section;
      ctx.setLoop(ctx.state.loop === section ? null : section);
      showSectionBar();
      return;
    }
    const box = timeline.getBoundingClientRect();
    ctx.seekTo(((e.clientX - box.left) / box.width) * (ctx.outline()?.seconds || 0));
  });
  timeline.addEventListener("pointerdown", startDrag);
  timeline.addEventListener("keydown", (e) => {
    const edge = e.target.closest(".edge");
    if (!edge || !["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    e.preventDefault();
    const s = sectionOf(edge);
    if (s) setBars(s.index, s.section.bars + (e.key === "ArrowRight" ? 1 : -1));
  });
  document.getElementById("section-bar").addEventListener("change", onSectionBarChange);
  document.getElementById("section-bar").addEventListener("click", onSectionBarClick);
}

function sectionOf(el) {
  const name = el.closest(".section")?.dataset.name;
  const sections = ctx.outline()?.sections || [];
  const index = sections.findIndex((s) => s.name === name);
  return index < 0 ? null : { section: sections[index], index };
}

function barsPath(index) {
  return ctx.outline().sections_written ? `sections[${index}].bars` : "bars";
}

function setBars(index, bars) {
  const section = ctx.outline().sections[index];
  bars = Math.max(1, Math.min(MAX_BARS, Math.round(bars)));
  if (!section || bars === section.bars) return;
  ctx.commit([{ op: "set", path: barsPath(index), value: bars }], `section ${section.name}: ${section.bars} → ${bars} bars`);
}

// ----- dragging an edge ----------------------------------------------------------------------

function startDrag(e) {
  const edge = e.target.closest(".edge");
  if (!edge || e.button !== 0) return;
  const s = sectionOf(edge);
  if (!s) return;
  e.preventDefault();
  const timeline = document.getElementById("timeline");
  const pxPerBar = timeline.getBoundingClientRect().width / ctx.outline().bars;
  drag = { ...s, startX: e.clientX, startBars: s.section.bars, pxPerBar, bars: s.section.bars, el: edge.closest(".section") };
  edge.setPointerCapture(e.pointerId);
  timeline.classList.add("dragging");
  edge.addEventListener("pointermove", moveDrag);
  edge.addEventListener("pointerup", endDrag, { once: true });
  edge.addEventListener("pointercancel", endDrag, { once: true });
}

function moveDrag(e) {
  if (!drag) return;
  const bars = Math.max(1, Math.min(MAX_BARS, Math.round(drag.startBars + (e.clientX - drag.startX) / drag.pxPerBar)));
  if (bars === drag.bars) return;
  drag.bars = bars;
  drag.el.style.flexGrow = String(bars);
  drag.el.querySelector(".bars").textContent = `${bars} bars`;
  drag.el.dataset.drag = `${bars} bars`;
}

function endDrag(e) {
  const edge = e.target.closest(".edge");
  edge?.removeEventListener("pointermove", moveDrag);
  document.getElementById("timeline").classList.remove("dragging");
  const done = drag;
  setTimeout(() => { drag = null; }, 0); // the click that ends a drag is not a seek
  if (!done) return;
  delete done.el.dataset.drag;
  if (done.bars !== done.startBars) setBars(done.index, done.bars);
}

// ----- drawing -------------------------------------------------------------------------------

export function showTimeline() {
  const outline = ctx.outline();
  const timeline = document.getElementById("timeline");
  for (const el of timeline.querySelectorAll(".section, .empty")) el.remove();
  const loop = document.getElementById("loop");
  loop.innerHTML = '<option value="">whole</option>';
  if (!outline) {
    timeline.insertAdjacentHTML("afterbegin", '<span class="empty">pick a preset</span>');
    showSectionBar();
    return;
  }
  const names = outline.sections.map((s) => s.name);
  if (ctx.state.loop && !names.includes(ctx.state.loop)) ctx.state.loop = null;
  if (ctx.state.selectedSection && !names.includes(ctx.state.selectedSection)) ctx.state.selectedSection = null;
  outline.sections.forEach((s, i) => {
    const el = document.createElement("div");
    el.className = i === outline.sections.length - 1 ? "section last" : "section";
    el.dataset.name = s.name;
    el.style.flexGrow = String(s.bars);
    el.style.setProperty("--sec", ctx.colour(i));
    const own = s.own_progression && s.progression ? `<span class="own" title="This section's own chords">${escapeHtml(s.progression.chords.map((c) => c.numeral).join(" "))}</span>` : "";
    el.innerHTML = `
      <div class="sec-head"><button class="sec-name" aria-pressed="false" title="Loop ${escapeHtml(s.name)} (bars ${s.first_bar}–${s.first_bar + s.bars - 1}); click again for the whole piece">${escapeHtml(s.name)}</button>
      <span class="bars">${s.bars} bars${s.key !== outline.key ? ` · ${escapeHtml(s.key)}` : ""}</span></div>${own}
      <span class="edge" tabindex="0" role="slider" aria-label="Length of ${escapeHtml(s.name)} in bars: drag, or arrow keys"
        aria-valuemin="1" aria-valuemax="${MAX_BARS}" aria-valuenow="${s.bars}" title="Drag to change the length of ${escapeHtml(s.name)} (bars)"></span>`;
    timeline.insertBefore(el, document.getElementById("energy"));
    loop.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(s.name)}">${escapeHtml(s.name)}</option>`);
  });
  loop.value = ctx.state.loop || "";
  showLoop();
  showEnergy();
  showSectionBar();
}

export function showLoop() {
  const timeline = document.getElementById("timeline");
  timeline.classList.toggle("looping", Boolean(ctx.state.loop));
  for (const el of timeline.querySelectorAll(".section")) {
    const looped = el.dataset.name === ctx.state.loop;
    el.classList.toggle("looped", looped);
    el.querySelector(".sec-name").setAttribute("aria-pressed", String(looped));
    el.classList.toggle("selected", el.dataset.name === ctx.state.selectedSection);
  }
  document.getElementById("loop").value = ctx.state.loop || "";
}

// The energy curve: the render's loudness bar by bar (LUFS), the loudest bar at the top and
// 30 LU below it at the bottom of the curve's band.
export function showEnergy() {
  const svg = document.getElementById("energy");
  const energy = ctx.state.render?.energy;
  const outline = ctx.outline();
  const pending = Boolean(ctx.state.render?.facts_pending);
  svg.classList.toggle("stale", pending && !energy?.length);
  if (!energy?.length || !outline) {
    if (!pending) svg.innerHTML = ""; // a new render's curve comes a moment later: the last one stays, dimmed
    return;
  }
  const bars = Math.min(energy.length, outline.bars);
  const shown = energy.slice(0, bars);
  const hi = Math.max(...shown);
  const lo = Math.min(hi - 6, Math.max(Math.min(...shown) - 2, hi - 24)); // at least 6 LU, at most 24 LU tall
  const y = (v) => (100 - 6 - (86 * Math.max(0, v - lo)) / (hi - lo)).toFixed(2);
  const points = [];
  for (let i = 0; i < bars; i++) points.push(`${(i + 0.5).toFixed(2)},${y(energy[i])}`);
  const line = `M0,${y(energy[0])} L${points.join(" L")} L${bars},${y(energy[bars - 1])}`;
  svg.setAttribute("viewBox", `0 0 ${bars} 100`);
  svg.innerHTML = `<path class="area" d="${line} L${bars},100 L0,100 Z"/><path class="line" d="${line}" vector-effect="non-scaling-stroke"/>`;
  svg.dataset.bars = String(bars);
  document.getElementById("timeline").title = `Energy: loudness per bar, ${lo.toFixed(0)} to ${hi.toFixed(0)} LUFS (in a video's mix)`;
}

export function tickTimeline(seconds, section) {
  const outline = ctx.outline();
  const piece = outline?.seconds || 0;
  const share = piece ? Math.min(1, Math.max(0, seconds) / piece) : 0;
  document.getElementById("playhead").style.left = `calc(${(share * 100).toFixed(3)}% - 1px)`;
  for (const el of document.getElementById("timeline").querySelectorAll(".section")) el.classList.toggle("current", el.dataset.name === section?.name);
}

export function setRendering(on) {
  document.getElementById("timeline").classList.toggle("rendering", on);
}

// ----- the section bar -----------------------------------------------------------------------

export function showSectionBar() {
  const bar = document.getElementById("section-bar");
  const outline = ctx.outline();
  if (bar.contains(document.activeElement) && document.activeElement.tagName === "INPUT") return;
  const index = outline ? outline.sections.findIndex((s) => s.name === ctx.state.selectedSection) : -1;
  if (!outline) {
    bar.innerHTML = "";
    return;
  }
  const written = outline.sections_written;
  const noList = written ? "" : ' disabled title="This score gives its length as bars, not a list of sections"';
  if (index < 0) {
    bar.innerHTML = `<span class="hint">Click a section's name to loop it and edit it here · drag a section's right edge to change its length</span>
      <span class="spacer"></span><button class="btn small" data-act="add"${noList}>+ section</button>`;
    return;
  }
  const s = outline.sections[index];
  const hasTop = Boolean(outline.progression);
  let chords;
  if (s.own_progression) {
    chords = `<span class="dim">own chords</span> <b class="mono">${escapeHtml(s.progression?.text || "")}</b>
      <button class="btn small" data-act="shared"${hasTop ? "" : ' disabled title="The score has no progression of its own to use"'}>use the score's</button>`;
  } else {
    chords = `<span class="dim">the score's chords</span>
      <button class="btn small" data-act="own"${written && s.progression ? "" : " disabled"} title="Give ${escapeHtml(s.name)} chords of its own (a copy to change)">own chords</button>`;
  }
  bar.innerHTML = `
    <span class="sec-dot" aria-hidden="true"></span>
    <label class="sec-field">name <input class="field" id="sec-name" value="${escapeHtml(s.name)}" spellcheck="false" autocomplete="off"${written ? "" : " disabled"}></label>
    <label class="sec-field">bars <input class="field num" id="sec-bars" type="number" min="1" max="${MAX_BARS}" step="1" value="${s.bars}"></label>
    <span class="sec-facts dim">bars ${s.first_bar}–${s.first_bar + s.bars - 1} · ${ctx.clock(s.start)}–${ctx.clock(s.start + s.bars * outline.bar_seconds)}</span>
    <span class="sec-chords">${chords}</span>
    <span class="spacer"></span>
    <button class="btn small" data-act="loop" aria-pressed="${ctx.state.loop === s.name}">⟳ loop</button>
    <button class="btn small" data-act="add"${noList}>+ section after</button>
    <button class="btn small danger" data-act="remove"${written && outline.sections.length > 1 ? "" : " disabled"}>remove</button>`;
  bar.querySelector(".sec-dot").style.background = ctx.colour(index);
}

function onSectionBarChange(e) {
  const outline = ctx.outline();
  const index = outline.sections.findIndex((s) => s.name === ctx.state.selectedSection);
  if (index < 0) return;
  const s = outline.sections[index];
  if (e.target.id === "sec-bars") {
    const bars = Number(e.target.value);
    if (!Number.isInteger(bars) || bars < 1 || bars > MAX_BARS) {
      ctx.problem(`bars: a whole number from 1 to ${MAX_BARS}`);
      e.target.value = s.bars;
      return;
    }
    setBars(index, bars);
  } else if (e.target.id === "sec-name") {
    const to = e.target.value.trim();
    if (to === s.name) return;
    const looped = ctx.state.loop === s.name;
    ctx.commit([{ op: "rename_section", name: s.name, to }], `section ${s.name} → ${to}`).then((r) => {
      if (r.ok) {
        ctx.state.selectedSection = to;
        if (looped) ctx.setLoop(to);
        showTimeline();
      } else {
        e.target.value = s.name;
      }
    });
  }
}

function onSectionBarClick(e) {
  const button = e.target.closest("button[data-act]");
  if (!button || button.disabled) return;
  const outline = ctx.outline();
  const index = outline.sections.findIndex((s) => s.name === ctx.state.selectedSection);
  const s = outline.sections[index];
  const act = button.dataset.act;
  if (act === "loop" && s) {
    ctx.setLoop(ctx.state.loop === s.name ? null : s.name);
    showSectionBar();
  } else if (act === "add") {
    const after = index < 0 ? outline.sections.length - 1 : index;
    ctx.commit([{ op: "add_section", after, bars: 4 }]).then((r) => {
      if (r.ok) {
        ctx.state.selectedSection = r.score.outline.sections[after + 1]?.name ?? null;
        showTimeline();
      }
    });
  } else if (act === "remove" && s) {
    ctx.commit([{ op: "remove_section", name: s.name }]).then((r) => {
      if (r.ok) {
        ctx.state.selectedSection = null;
        showTimeline();
      }
    });
  } else if (act === "own" && s) {
    ctx.commit([{ op: "set", path: `sections[${index}].progression`, value: s.progression.text }], `${s.name} gets its own chords`);
  } else if (act === "shared" && s) {
    ctx.commit([{ op: "delete", path: `sections[${index}].progression` }], `${s.name} plays the score's chords`);
  }
}
