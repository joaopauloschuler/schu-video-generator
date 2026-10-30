// Listening notes and "Ask an agent" (DESIGN.md §94.16). While listening (playing or paused), a
// click on the notes lane under the timeline, the "+ note" button or the N key pins a short note
// at that moment: the server records its bar, beat, section and the version heard. Notes show as
// pins on the lane and in the Notes tab (edit, resolve, delete; click to play from a little
// before). "Ask an agent" writes a hand-off into the session folder; an agent answers through
// schu-video-generator's MCP (the page polls the session and the proposal appears), a chat assistant through
// Copy prompt / Paste reply, or OpenRouter when a key is set. A proposal is a new version to A/B
// against the one it was made from, then keep or discard; one with problems can only be dismissed.

import { api } from "./api.js";
import { abWith, showVersions } from "./versions.js";
import { escapeHtml } from "./yaml_view.js";

const $ = (id) => document.getElementById(id);
const LEAD_SECONDS = 1.5;   // a note plays from this long before its moment
const POLL_MS = 1500;       // how often the page asks whether an agent proposed something
const OFFLINE_POLL_MS = 4000; // how often it looks for the server again while it does not answer
const MAX_CHARS = 500;

let ctx = null;
let editor = null;          // the note being written or edited: {id: null | "n3", seconds}
let polling = false;
let handoff = null;         // the last "Ask an agent" answer: {request, prompt, provider}
let handoffFor = undefined; // the session whose hand-off was looked for

// ----- where a moment is (as the server's notes.locate) ------------------------------------------

function whereAt(seconds) {
  const o = ctx.outline();
  if (!o?.sections?.length) return null;
  let found = o.sections[0];
  for (const s of o.sections) if (s.start <= seconds + 1e-6) found = s;
  const into = (seconds - found.start) / o.bar_seconds;
  const index = Math.min(Math.floor(into + 1e-9), found.bars - 1);
  const frac = Math.min(Math.max(into - index, 0), 0.999);
  const beats = Math.max(1, parseInt(String(o.time).split("/")[0], 10) || 4);
  return { bar: found.first_bar + index, beat: Math.min(beats, 1 + Math.floor(frac * beats)), section: found.name };
}

function sectionColour(name) {
  const i = (ctx.outline()?.sections || []).findIndex((s) => s.name === name);
  return i < 0 ? "var(--dim)" : ctx.colour(i);
}

const notes = () => ctx.state.notes || [];
const openCount = () => notes().filter((n) => n.status === "open").length;
const placeText = (at) => `bar ${at.bar} · beat ${at.beat} · ${at.section}`;

// ----- state from the server ---------------------------------------------------------------------

// Take the notes, proposals and revision of a server answer (every session state carries them).
export function setNotes(doc) {
  if (!doc) return;
  if (Array.isArray(doc.notes)) ctx.state.notes = doc.notes;
  if (Array.isArray(doc.proposals)) ctx.state.proposals = doc.proposals;
  if (typeof doc.revision === "number") ctx.state.revision = doc.revision;
}

export function showNotes() {
  drawPins();
  drawList();
  drawProposals();
  const count = openCount();
  $("notes-count").textContent = count ? String(count) : "";
  $("pane-notes-count").textContent = count ? String(count) : "";
  $("ask").disabled = !ctx.state.session;
  $("ask").textContent = count ? `Ask an agent about ${count} note${count > 1 ? "s" : ""}` : "Ask an agent";
  const sessionId = ctx.state.session?.id ?? null;
  if (handoffFor !== sessionId) {
    handoffFor = sessionId; // another piece (or the page just loaded): its last hand-off, if any
    handoff = null;
    drawHandoff();
    if (sessionId) loadHandoff(sessionId);
  } else if (handoff) askAgainLabel(); // the version shown changed: "Ask again about vN"
  const waiting = $("handoff").querySelector(".waiting");
  if (handoff && waiting && (ctx.state.proposals || []).some((x) => x.request === handoff.request.id)) {
    waiting.classList.add("done");
    waiting.textContent = "answered";
  }
}

// ----- pins on the lane --------------------------------------------------------------------------

function share(seconds) {
  const whole = ctx.outline()?.seconds || 0;
  return whole ? Math.min(1, Math.max(0, seconds / whole)) : 0;
}

function drawPins() {
  const lane = $("note-lane");
  for (const el of lane.querySelectorAll(".pin")) el.remove();
  const add = (cls, seconds, label, id) => {
    const pin = document.createElement("button");
    pin.className = `pin ${cls}`;
    pin.style.left = `${(share(seconds) * 100).toFixed(3)}%`;
    pin.title = label;
    pin.setAttribute("aria-label", label);
    if (id) pin.dataset.id = id;
    lane.appendChild(pin);
    return pin;
  };
  for (const n of notes()) {
    const answered = n.answers?.some((a) => a.status === "pending");
    const pin = add(`${n.status}${answered ? " answered" : ""}${editor?.id === n.id ? " editing" : ""}`, n.at.seconds,
      `${n.id} · ${placeText(n.at)}: ${n.text}${n.status === "resolved" ? " (resolved)" : ""}`, n.id);
    pin.style.setProperty("--pin", sectionColour(n.at.section));
  }
  if (editor && !editor.id) add("draft", editor.seconds, "the new note");
  lane.classList.toggle("empty", notes().length === 0 && !editor);
}

// The pins near the playhead light up as it passes them.
export function tickNotes(seconds) {
  for (const pin of $("note-lane").querySelectorAll(".pin[data-id]")) {
    const note = notes().find((n) => n.id === pin.dataset.id);
    pin.classList.toggle("now", Boolean(note) && ctx.player.playing && Math.abs(note.at.seconds - seconds) < 0.35);
  }
}

// ----- the note editor ---------------------------------------------------------------------------

function openEditor(id, seconds) {
  editor = { id, seconds };
  const note = id ? notes().find((n) => n.id === id) : null;
  const where = note ? note.at : whereAt(seconds);
  if (!where) return;
  const box = $("note-editor");
  box.hidden = false;
  box.innerHTML = `
    <div class="ne-head"><b>${note ? escapeHtml(note.id) : "New note"}</b>
      <span class="dim">${escapeHtml(placeText(where))} · ${ctx.clock(seconds)}${note ? ` · made on v${note.version}` : ` · v${ctx.playingVersion() ?? "–"}`}</span>
      <button class="btn icon small" data-act="close" aria-label="Close">×</button></div>
    ${note?.at.moved ? `<p class="ne-moved">${escapeHtml(note.at.moved)}</p>` : ""}
    <textarea id="note-text" class="field" rows="2" maxlength="${MAX_CHARS}" spellcheck="true"
      placeholder="What do you hear? e.g. this part drags · love this bell · goosebumps here"
      aria-label="The note">${escapeHtml(note?.text || "")}</textarea>
    <div class="ne-actions">
      <button class="btn small primary" data-act="save">${note ? "Save" : "Pin note"}</button>
      <span class="dim small">Enter keeps it · Esc closes</span>
      <span class="spacer"></span>
      ${note ? `<button class="btn small" data-act="play">▶ from here</button>
        <button class="btn small" data-act="resolve">${note.status === "open" ? "✓ Resolve" : "Reopen"}</button>
        <button class="btn small danger" data-act="delete">Delete</button>` : ""}
    </div>`;
  const left = share(seconds);
  box.style.left = `clamp(8px, calc(${(left * 100).toFixed(3)}% - 170px), calc(100% - 348px))`;
  drawPins();
  const text = $("note-text");
  text.focus();
  text.setSelectionRange(text.value.length, text.value.length);
}

function closeEditor() {
  editor = null;
  // focus leaves the editor for the page, so Space plays / pauses again at once
  if ($("note-editor").contains(document.activeElement)) document.activeElement.blur();
  $("note-editor").hidden = true;
  drawPins();
}

async function saveEditor() {
  if (!editor) return;
  const text = $("note-text").value.trim();
  if (!text) {
    if (!editor.id) closeEditor();
    else ctx.status("a note needs a few words (or delete it)", "error");
    return;
  }
  const mine = editor;
  const { id, seconds } = editor;
  try {
    const doc = id ? await api.updateNote(id, { text }) : await api.addNote(ctx.playingVersion(), seconds, text);
    if (editor === mine) closeEditor(); // the next note may already be being written
    applyState(doc);
    if (!id) ctx.status(`note ${doc.note} pinned at ${placeText(doc.notes.find((n) => n.id === doc.note).at)}`);
  } catch (err) {
    ctx.status(err.message, "error");
  }
}

// Pin a new note at moment `seconds` (default: the moment playing).
function pin(seconds = ctx.player.url ? ctx.player.time : ctx.state.time) {
  if (!ctx.state.score?.outline) return;
  openEditor(null, seconds);
}

async function noteAction(id, act) {
  const note = notes().find((n) => n.id === id);
  if (!note) return;
  try {
    if (act === "play") {
      ctx.seekTo(Math.max(0, note.at.seconds - LEAD_SECONDS));
      if (!ctx.player.playing) await ctx.play();
      highlight(id);
    } else if (act === "edit") {
      openEditor(id, note.at.seconds);
    } else if (act === "resolve") {
      applyState(await api.updateNote(id, { status: note.status === "open" ? "resolved" : "open" }));
      if (editor?.id === id) closeEditor();
    } else if (act === "delete") {
      if (editor?.id === id) closeEditor();
      applyState(await api.updateNote(id, { delete: true }));
      ctx.status(`note ${id} deleted`);
    }
  } catch (err) {
    ctx.status(err.message, "error");
  }
}

function highlight(id) {
  for (const li of $("note-list").querySelectorAll(".note")) li.classList.toggle("lit", li.dataset.id === id);
}

// ----- the Notes tab -----------------------------------------------------------------------------

function answerLine(a) {
  const words = { pending: `proposed in v${a.version}`, kept: `kept in v${a.version}`, discarded: "discarded" }[a.status] || a.status;
  return `<li class="ans ${escapeHtml(a.status)}"><span class="badge">${escapeHtml(words)}</span>
    <span class="by">${escapeHtml(a.by || "agent")}:</span> ${escapeHtml(a.text)}</li>`;
}

function drawList() {
  const list = $("note-list");
  const all = [...notes()].sort((a, b) => a.at.seconds - b.at.seconds); // in the piece's order
  $("notes-empty").hidden = all.length > 0;
  list.innerHTML = all.map((n) => `
    <li class="note ${escapeHtml(n.status)}" data-id="${escapeHtml(n.id)}">
      <button class="n-time" data-act="play" title="Play from ${LEAD_SECONDS} s before">▶ ${ctx.clock(n.at.seconds)}</button>
      <div class="n-body">
        <div class="n-where"><i class="dot"></i>${escapeHtml(n.id)} · ${escapeHtml(placeText(n.at))} <span class="dim">· made on v${n.version}</span></div>
        <div class="n-text" data-act="edit" title="Edit the note">${escapeHtml(n.text)}</div>
        ${n.at.moved ? `<div class="n-moved">${escapeHtml(n.at.moved)}</div>` : ""}
        ${n.answers?.length ? `<ul class="answers">${n.answers.map(answerLine).join("")}</ul>` : ""}
      </div>
      <div class="n-acts">
        <button class="v-act" data-act="resolve" aria-label="${n.status === "open" ? "Resolve" : "Reopen"} ${escapeHtml(n.id)}" title="${n.status === "open" ? "Resolve (done)" : "Reopen"}">${n.status === "open" ? "✓" : "↺"}</button>
        <button class="v-act" data-act="edit" aria-label="Edit ${escapeHtml(n.id)}" title="Edit">✎</button>
        <button class="v-act del" data-act="delete" aria-label="Delete ${escapeHtml(n.id)}" title="Delete">×</button>
      </div>
    </li>`).join("");
  for (const li of list.querySelectorAll(".note")) {
    const n = all.find((x) => x.id === li.dataset.id);
    li.querySelector(".dot").style.background = sectionColour(n.at.section);
  }
}

// ----- tabs: score file / notes ------------------------------------------------------------------

export function showTab(name) {
  const notesTab = name === "notes";
  $("tab-yaml").setAttribute("aria-selected", String(!notesTab));
  $("tab-notes").setAttribute("aria-selected", String(notesTab));
  $("yaml-panel").classList.toggle("on-notes", notesTab);
  $("notes-panel").hidden = !notesTab;
  ctx.showPane?.(notesTab ? "notes" : "yaml"); // narrow windows: the tab below the tracks
  if (notesTab) {
    $("work").classList.remove("no-yaml");
    $("yaml-toggle").setAttribute("aria-pressed", "true");
  }
  ctx.storage("vidgen-studio-tab", name);
}

// ----- Ask an agent ------------------------------------------------------------------------------

async function ask() {
  try {
    handoff = await api.ask(ctx.state.score?.version);
    drawHandoff();
    const n = handoff.request.notes.length;
    ctx.status(`hand-off ready for v${handoff.request.base} with ${n} note${n === 1 ? "" : "s"}: answer it through MCP, a chat assistant or OpenRouter`);
  } catch (err) {
    ctx.status(err.message, "error");
  }
}

// The session's last hand-off (kept in its folder), shown again after a reload.
async function loadHandoff(sessionId) {
  try {
    const found = await api.lastHandoff();
    if (found && handoffFor === sessionId && !handoff && found.request.session === sessionId) {
      handoff = found;
      drawHandoff();
    }
  } catch {
    // the card is a nicety: Ask an agent makes it again
  }
}

function drawHandoff() {
  const box = $("handoff");
  if (!handoff) {
    box.hidden = true;
    return;
  }
  const r = handoff.request;
  const p = handoff.provider;
  const answered = (ctx.state.proposals || []).some((x) => x.request === r.id);
  const kb = (new Blob([handoff.prompt]).size / 1024).toFixed(1);
  const why = !p.key_set ? `set ${p.key_env} (your OpenRouter key; vidgen never stores it) and start the studio again` : "";
  const made = typeof r.created === "string" ? r.created.slice(11, 16) : "";
  box.hidden = false;
  box.innerHTML = `
    <p class="ho-line">Hand-off for <b>v${r.base}</b>${made ? ` <span class="dim">made at ${escapeHtml(made)}</span>` : ""}: ${r.notes.length} open note${r.notes.length === 1 ? "" : "s"},
      ${r.check ? "the check" : "no check yet"}${r.diff ? `, the change from v${r.diff.parent}` : ""}.
      <button class="btn small" id="ask-again"></button>
      Answer it with:</p>
    <ol class="ways">
      <li><b>An agent through vidgen's MCP</b> (<code>vidgen mcp</code>): ask it to <i>answer my studio notes</i>; it uses
        <code>studio_read</code> and <code>studio_propose</code>, and the proposal appears above the tracks.
        <span class="waiting${answered ? " done" : ""}">${answered ? "answered" : "waiting for a proposal…"}</span></li>
      <li><b>Any chat assistant</b>: <button class="btn small" id="copy-prompt">Copy prompt</button> (${kb} KB), paste it there,
        then <button class="btn small" id="paste-open">Paste reply</button></li>
      <li><b>${escapeHtml(p.name)}</b> <span class="dim">(costs money)</span>:
        <input class="field model" id="provider-model" placeholder="vendor/model" spellcheck="false" autocomplete="off"
          value="${escapeHtml(ctx.storage("vidgen-studio-model") || p.model || "")}" aria-label="OpenRouter model" ${p.key_set ? "" : "disabled"}>
        <button class="btn small" id="provider-send" ${p.key_set ? "" : "disabled"} title="${escapeHtml(why || "Send the hand-off to OpenRouter")}">Send</button>
        ${why ? `<span class="why">${escapeHtml(why)}</span>` : ""}
        <span id="provider-confirm" hidden></span></li>
    </ol>
    <div class="paste-box" id="paste-box" hidden>
      <textarea class="field" id="paste-text" rows="6" spellcheck="false" placeholder="Paste the whole reply: the score in a yaml block and the n1: … lines"
        aria-label="The assistant's reply"></textarea>
      <div class="ne-actions"><button class="btn small primary" id="paste-make">Make the proposal</button><button class="btn small" id="paste-cancel">Cancel</button></div>
    </div>`;
  askAgainLabel();
}

function askAgainLabel() {
  const button = $("ask-again");
  if (!button || !handoff) return;
  const now = ctx.state.score?.version ?? "–";
  button.textContent = handoff.request.base !== now ? `Ask again about v${now}` : "Ask again";
  button.title = `Make the hand-off again from v${now} with the notes open now`;
}

async function copyPrompt() {
  const text = handoff?.prompt || "";
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  document.body.dataset.copied = String(text.length);
  ctx.status("prompt copied: paste it into a chat assistant, then Paste reply its answer");
}

async function makeFrom(call, words) {
  ctx.status(words, "busy");
  try {
    const doc = await call();
    applyState(doc);
    const made = (doc.proposals || []).find((x) => x.id === doc.proposal);
    if (made?.status === "invalid") ctx.status("the reply has problems (above the tracks): it cannot be kept", "error");
    else if (made) ctx.status(`proposal v${made.version} made: A/B it, then keep or discard it`);
    return true;
  } catch (err) {
    ctx.status(err.message, "error");
    return false;
  }
}

async function onHandoffClick(e) {
  const id = e.target.closest("button")?.id || e.target.id;
  if (id === "ask-again") ask();
  else if (id === "copy-prompt") copyPrompt();
  else if (id === "paste-open") {
    $("paste-box").hidden = false;
    $("paste-text").focus();
  } else if (id === "paste-cancel") $("paste-box").hidden = true;
  else if (id === "paste-make") {
    const reply = $("paste-text").value;
    if (!reply.trim()) return;
    if (await makeFrom(() => api.pasteReply(reply), "reading the reply…")) $("paste-box").hidden = true;
  } else if (id === "provider-send") {
    const model = $("provider-model").value.trim();
    const confirm = $("provider-confirm");
    confirm.hidden = false;
    confirm.innerHTML = `Sends the hand-off to ${escapeHtml(model || "?")} with your key: it costs money.
      <button class="btn small primary" id="provider-go" ${model ? "" : "disabled"}>Send now</button>
      <button class="btn small" id="provider-cancel">Cancel</button>`;
  } else if (id === "provider-cancel") $("provider-confirm").hidden = true;
  else if (id === "provider-go") {
    const model = $("provider-model").value.trim();
    ctx.storage("vidgen-studio-model", model);
    $("provider-confirm").hidden = true;
    document.body.dataset.asking = "1";
    try {
      await makeFrom(() => api.sendToProvider(model), `asking ${model}… (it can take a minute)`);
    } finally {
      delete document.body.dataset.asking;
    }
  }
}

// ----- proposals ---------------------------------------------------------------------------------

function sourceWords(p) {
  const via = { mcp: "through MCP", paste: "pasted", openrouter: "from OpenRouter" }[p.source] || p.source;
  return p.agent ? `${via} (${p.agent})` : via;
}

function drawProposals() {
  const bar = $("proposal-bar");
  const shown = (ctx.state.proposals || []).filter((p) => p.status === "pending" || p.status === "invalid").slice(-3).reverse();
  bar.hidden = shown.length === 0;
  const current = ctx.state.session?.current;
  const ab = ctx.state.ab || {};
  bar.innerHTML = shown.map((p) => {
    if (p.status === "invalid") {
      return `<div class="proposal invalid" data-id="${escapeHtml(p.id)}">
        <div class="p-head"><span class="p-icon" aria-hidden="true">!</span><b>A proposal ${escapeHtml(sourceWords(p))} has problems and cannot be kept</b>
          <span class="spacer"></span><button class="btn small" data-act="discard">Dismiss</button></div>
        <ul class="p-problems">${p.problems.slice(0, 6).map((x) => `<li>${x.where ? `<code>${escapeHtml(x.where)}</code> ` : ""}${escapeHtml(x.message)}${x.line ? ` <span class="dim">(line ${x.line})</span>` : ""}</li>`).join("")}</ul>
      </div>`;
    }
    const playing = ab.on && ab.version === p.version;
    const lines = Object.entries(p.explanations || {}).map(([id, text]) => {
      const note = notes().find((n) => n.id === id);
      const about = note ? `<span class="dim">${escapeHtml(placeText(note.at))} · “${escapeHtml(note.text)}”</span>` : '<span class="dim">(no such note)</span>';
      return `<li><b>${escapeHtml(id)}</b> ${about}<br>${escapeHtml(text)}</li>`;
    });
    const missing = notes().filter((n) => n.status === "open" && !(n.id in (p.explanations || {})) && n.created <= p.created).map((n) => n.id);
    return `<div class="proposal pending" data-id="${escapeHtml(p.id)}" data-version="${p.version}">
      <div class="p-head"><span class="p-icon" aria-hidden="true">✦</span>
        <b>An agent proposed v${p.version}</b><span class="dim">from v${p.base} · ${escapeHtml(sourceWords(p))}${p.summary ? ` · “${escapeHtml(p.summary)}”` : ""}</span>
        <span class="spacer"></span>
        <button class="btn small${playing ? " on" : ""}" data-act="ab" aria-pressed="${playing}" title="Hear v${p.version} (A) against v${current} (B) at the same moment; click again for v${current}">${playing ? `▶ hearing v${p.version} · back to v${current}` : `▶ A/B v${p.version} vs v${current}`}</button>
        <button class="btn small primary" data-act="keep">Keep v${p.version}</button>
        <button class="btn small danger" data-act="discard">Discard</button></div>
      ${lines.length ? `<ul class="p-lines">${lines.join("")}</ul>` : '<p class="dim p-none">No line per note came with it.</p>'}
      ${missing.length ? `<p class="dim p-none">No line for ${missing.map(escapeHtml).join(", ")}.</p>` : ""}
    </div>`;
  }).join("");
}

async function onProposalClick(e) {
  const button = e.target.closest("button[data-act]");
  if (!button) return;
  const box = button.closest(".proposal");
  const proposal = (ctx.state.proposals || []).find((p) => p.id === box.dataset.id);
  if (!proposal) return;
  const act = button.dataset.act;
  if (act === "ab") {
    const on = !(ctx.state.ab.on && ctx.state.ab.version === proposal.version);
    abWith(proposal.version, on);
    if (on && !ctx.player.playing) await ctx.play();
    return;
  }
  try {
    const wasA = ctx.state.ab.version === proposal.version;
    const doc = await api.decideProposal(proposal.id, act === "keep");
    if (wasA) {
      ctx.state.ab.on = false;
      ctx.state.ab.version = null;
    }
    if (act === "keep") {
      ctx.state.ab.on = false;
      ctx.show(doc);
      ctx.status(`kept v${proposal.version}: the notes it answered are resolved (reopen one if it is not)`);
      ctx.refreshAudio();
    } else {
      applyState(doc);
      ctx.status(proposal.status === "invalid" ? "dismissed" : `discarded v${proposal.version} (it stays in the version list)`);
      if (wasA) ctx.refreshAudio();
    }
  } catch (err) {
    ctx.status(err.message, "error");
  }
}

// ----- polling: what agents proposed -------------------------------------------------------------

// A session state from the server: the same version stays shown (only the version list, notes and
// proposals change); another current version is shown and rendered.
function applyState(doc) {
  if (!doc?.session) return;
  if (doc.score && doc.score.version !== ctx.state.score?.version) {
    ctx.show(doc);
    ctx.refreshAudio();
    return;
  }
  ctx.state.session = doc.session;
  setNotes(doc);
  showVersions();
  showNotes();
}

// The poll runs every POLL_MS while the tab is visible (every OFFLINE_POLL_MS while the server
// does not answer: it is also how the page notices the server is back), and not at all while the
// tab is hidden; showing the tab again polls at once.
let pollTimer = 0;
let offline = false;

function schedulePoll(ms = offline ? OFFLINE_POLL_MS : POLL_MS) {
  clearTimeout(pollTimer);
  if (!document.hidden) pollTimer = setTimeout(pollAndNext, ms);
}

async function pollAndNext() {
  await poll();
  schedulePoll();
}

// Poll now (the offline banner's Retry; the tab shown again).
export function pollNow() {
  clearTimeout(pollTimer);
  pollAndNext();
}

export function setOffline(value) {
  offline = value;
}

async function poll() {
  if (polling || document.hidden) return;
  if (!ctx.state.session) {
    if (offline) await api.info().catch(() => null); // only to learn whether the server is back
    return;
  }
  polling = true;
  try {
    const since = ctx.state.revision;
    const doc = await api.poll(since);
    if (doc.unchanged || doc.session?.id !== ctx.state.session?.id || (doc.revision ?? 0) <= (ctx.state.revision ?? -1)) return;
    applyState(doc);
    const made = (doc.proposals || []).filter((p) => (doc.made || []).includes(p.id));
    const fresh = made.find((p) => p.status === "pending");
    if (fresh) ctx.status(`an agent proposed v${fresh.version} (from v${fresh.base}): A/B it, then keep or discard it`);
    else if (made.length) ctx.status("an agent's proposal has problems: see above the tracks", "error");
  } catch {
    // the next poll tries again
  } finally {
    polling = false;
  }
}

// ----- wiring ------------------------------------------------------------------------------------

export function initNotes(context) {
  ctx = context;
  ctx.state.notes = [];
  ctx.state.proposals = [];
  ctx.state.revision = 0;
  ctx.onAB = drawProposals;
  $("note-lane").addEventListener("click", (e) => {
    const pinEl = e.target.closest(".pin");
    if (pinEl?.dataset.id) {
      const note = notes().find((n) => n.id === pinEl.dataset.id);
      if (note) {
        showTab("notes");
        highlight(note.id);
        openEditor(note.id, note.at.seconds);
      }
      return;
    }
    if (pinEl) return;
    const box = $("note-lane").getBoundingClientRect();
    pin(((e.clientX - box.left) / box.width) * (ctx.outline()?.seconds || 0));
  });
  $("add-note").addEventListener("click", () => pin());
  $("note-editor").addEventListener("click", (e) => {
    const act = e.target.closest("button[data-act]")?.dataset.act;
    if (act === "close") closeEditor();
    else if (act === "save") saveEditor();
    else if (act && editor?.id) noteAction(editor.id, act);
  });
  $("note-editor").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      saveEditor();
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeEditor();
    }
    e.stopPropagation();
  });
  $("note-list").addEventListener("click", (e) => {
    const act = e.target.closest("[data-act]")?.dataset.act;
    const id = e.target.closest(".note")?.dataset.id;
    if (act && id) noteAction(id, act);
  });
  $("tab-yaml").addEventListener("click", () => showTab("yaml"));
  $("tab-notes").addEventListener("click", () => showTab("notes"));
  $("ask").addEventListener("click", ask);
  $("handoff").addEventListener("click", onHandoffClick);
  $("proposal-bar").addEventListener("click", onProposalClick);
  document.addEventListener("keydown", (e) => {
    if (e.key.toLowerCase() !== "n" || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.target.closest?.("input, textarea, select, [contenteditable]")) return;
    e.preventDefault();
    pin();
  });
  showTab(ctx.storage("vidgen-studio-tab") === "notes" ? "notes" : "yaml");
  document.addEventListener("visibilitychange", () => (document.hidden ? clearTimeout(pollTimer) : pollNow()));
  schedulePoll();
}
