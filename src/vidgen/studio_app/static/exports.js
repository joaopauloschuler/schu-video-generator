// Exports (DESIGN.md §94.15): the current version as its score file (YAML), as audio (WAV or MP3:
// once, N loops or N seconds; at a video's level or the listening level), or saved into the
// project's assets/music/<name>.yaml (then `music: <name>` plays it in a video). The server
// renders with vidgen's own renderer and writes into the session; the browser downloads it.

import { api } from "./api.js";
import { escapeHtml } from "./yaml_view.js";

const $ = (id) => document.getElementById(id);
let ctx = null;

function download(url, name) {
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.hidden = true;
  $("export-panel").append(a); // inside the panel: its click does not close it
  a.click();
  a.remove();
}

function note(id, html, kind = "") {
  const el = $(id);
  el.innerHTML = html;
  el.className = `ex-note ${kind}`;
  el.hidden = !html;
}

// The length choices, from the piece: a loop's one pass and its length, or a one-pass piece.
function fillLengths() {
  const o = ctx.outline();
  const loop = Boolean(o?.loop);
  const once = o ? `${loop ? "one loop" : "the whole piece"} (${ctx.clock(ctx.state.render?.seconds ?? o.seconds)})` : "once";
  const select = $("ex-length");
  const keep = select.value;
  select.innerHTML = `<option value="once">${escapeHtml(once)}</option>${loop ? '<option value="loops">N loops</option>' : ""}<option value="seconds">N seconds</option>`;
  select.value = [...select.options].some((x) => x.value === keep) ? keep : "once";
  showCount();
}

function showCount() {
  const length = $("ex-length").value;
  const count = $("ex-count");
  count.hidden = length === "once";
  $("ex-count-unit").hidden = length === "once";
  $("ex-count-unit").textContent = length === "loops" ? "loops" : "seconds";
  if (length === "loops" && (!count.value || Number(count.value) > 64)) count.value = "4";
  if (length === "seconds" && (!count.value || Number(count.value) < 5)) count.value = "60";
  count.max = length === "loops" ? "64" : "600";
}

function defaultName() {
  const s = ctx.state.session;
  const base = (s?.preset ? `${s.preset}_mine` : (s?.title || "my_theme")).toLowerCase().replace(/[^a-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "");
  return base || "my_theme";
}

function open() {
  const panel = $("export-panel");
  panel.hidden = false;
  $("export").setAttribute("aria-expanded", "true");
  fillLengths();
  $("ex-version").textContent = `v${ctx.state.score?.version ?? "–"}`;
  const project = ctx.state.info?.project;
  $("ex-save-form").hidden = !project;
  if (!project) {
    note("ex-save-note", `The studio was started without a project, so there is no <code>assets/music/</code> to save into. Start it in the project's folder
      (the one with <code>video.yaml</code>) or give it: <code>vidgen studio path/to/project</code>. Or download the YAML above and put it in the project's
      <code>assets/music/</code> yourself.`, "info");
  } else {
    $("ex-project").textContent = project;
    if (!$("ex-name").value) $("ex-name").value = defaultName();
    if ($("ex-save-note").classList.contains("info")) note("ex-save-note", "");
  }
  $("ex-yaml").focus();
}

function close() {
  $("export-panel").hidden = true;
  $("export").setAttribute("aria-expanded", "false");
}

async function busyWhile(button, words, work) {
  const label = button.textContent;
  button.disabled = true;
  button.textContent = words;
  document.body.dataset.exporting = "1";
  try {
    return await work();
  } finally {
    button.disabled = false;
    button.textContent = label;
    delete document.body.dataset.exporting;
  }
}

async function exportYaml() {
  try {
    const r = await api.exportFile(ctx.state.score.version, { format: "yaml" });
    download(r.url, r.name);
    note("ex-audio-note", `Downloaded <code>${escapeHtml(r.name)}</code>: the score file of v${r.version}, as written.`, "ok");
  } catch (err) {
    note("ex-audio-note", escapeHtml(err.message), "error");
  }
}

async function exportAudio() {
  const length = $("ex-length").value;
  const options = {
    format: $("ex-format").value,
    length,
    count: length === "once" ? null : Number($("ex-count").value),
    level: $("ex-level").value,
  };
  await busyWhile($("ex-audio"), "rendering…", async () => {
    try {
      const r = await api.exportFile(ctx.state.score.version, options);
      download(r.url, r.name);
      note("ex-audio-note", `Downloaded <code>${escapeHtml(r.name)}</code>: ${ctx.clock(r.seconds)}, ${r.loudness.toFixed(1)} LUFS, true peak ${r.true_peak.toFixed(1)} dBTP
        (rendered by vidgen in ${r.export_seconds.toFixed(1)} s).`, "ok");
    } catch (err) {
      note("ex-audio-note", escapeHtml(err.message), "error");
    }
  });
}

async function save(overwrite = false) {
  const name = $("ex-name").value.trim();
  await busyWhile($("ex-save"), "saving…", async () => {
    try {
      const r = await api.savePiece(ctx.state.score.version, name, overwrite);
      if (!r.saved && r.exists) {
        note("ex-save-note", `<code>${escapeHtml(r.path)}</code> exists already.
          <button class="btn small danger" id="ex-overwrite">Overwrite it with v${r.version}</button> <button class="btn small" id="ex-cancel">Cancel</button>`, "warn");
        $("ex-overwrite").addEventListener("click", () => save(true));
        $("ex-cancel").addEventListener("click", () => note("ex-save-note", ""));
        return;
      }
      note("ex-save-note", `Saved v${r.version} as <code>${escapeHtml(r.path)}</code>${r.exists ? " (overwritten)" : ""}. In <code>video.yaml</code>, play it with:
        <span class="snippet"><code id="ex-snippet">${escapeHtml(r.snippet)}</code> <button class="btn small" id="ex-copy">Copy</button></span>`, "ok");
      $("ex-copy").addEventListener("click", () => copy(r.snippet));
      ctx.status(`saved v${r.version} as ${r.path}`);
    } catch (err) {
      note("ex-save-note", escapeHtml(err.message), "error");
    }
  });
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    $("ex-copy").textContent = "Copied";
  } catch {
    const range = document.createRange();
    range.selectNodeContents($("ex-snippet"));
    getSelection().removeAllRanges();
    getSelection().addRange(range);
    $("ex-copy").textContent = "Selected: Ctrl+C";
  }
}

export function initExports(c) {
  ctx = c;
  const panel = $("export-panel");
  $("export").addEventListener("click", () => (panel.hidden ? open() : close()));
  $("ex-close").addEventListener("click", close);
  $("ex-length").addEventListener("change", showCount);
  $("ex-yaml").addEventListener("click", exportYaml);
  $("ex-audio").addEventListener("click", exportAudio);
  $("ex-save").addEventListener("click", () => save(false));
  $("ex-name").addEventListener("keydown", (e) => {
    if (e.key === "Enter") save(false);
  });
  panel.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      close();
      $("export").focus();
    }
  });
  document.addEventListener("click", (e) => {
    if (!panel.hidden && !e.composedPath().some((el) => el.classList?.contains("export-wrap"))) close();
  });
}

export function showExports() {
  $("export").disabled = !ctx.state.score;
  if (!$("export-panel").hidden) {
    fillLengths();
    $("ex-version").textContent = `v${ctx.state.score?.version ?? "–"}`;
  }
}
