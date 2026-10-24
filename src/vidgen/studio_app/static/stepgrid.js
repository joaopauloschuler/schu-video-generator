// The step grid (DESIGN.md §94.13): a track's steps text read into bars of cells and edited cell
// by cell. The text stays the source: a cell's edit replaces only that cell's characters, so the
// spaces, `|` and everything else stay as written. Bars may have different step counts.

import { escapeHtml } from "./yaml_view.js";

// The step symbols of vidgen.studio.patterns (one regex, tried at each position).
const TOKEN = /(\|)|([A-G][#b]?\d[!?]?)|([1-9][',]*[!?]?)|(v[1-9][',]*[!?]?)|([xXo*.\-][',]*[!?]?)|(\+)|(\s+)/y;

// `text` as bars of cells {start, end, text}; {error, at} when a symbol is unknown.
export function readSteps(text) {
  const bars = [[]];
  let pos = 0;
  let joining = false;
  while (pos < text.length) {
    TOKEN.lastIndex = pos;
    const m = TOKEN.exec(text);
    if (!m) return { error: `unknown symbol '${text[pos]}' at ${pos + 1}`, at: pos };
    pos = TOKEN.lastIndex;
    if (m[7]) continue;
    if (m[1]) {
      bars.push([]);
      continue;
    }
    if (m[6]) {
      if (!bars.at(-1).length) return { error: `'+' at ${pos} joins two notes`, at: pos - 1 };
      joining = true;
      continue;
    }
    const bar = bars.at(-1);
    if (joining) {
      const last = bar.at(-1);
      last.end = pos;
      last.text = text.slice(last.start, pos);
      joining = false;
    } else {
      bar.push({ start: m.index, end: pos, text: m[0] });
    }
  }
  if (bars.some((b) => !b.length)) return { error: "an empty bar (two '|' in a row, or one at an end)", at: text.length };
  return { bars };
}

// What a cell shows: {kind, label}.
export function cellKind(token) {
  const t = token.replace(/[!?]$/, "");
  if (t === ".") return { kind: "rest", label: "" };
  if (t === "-") return { kind: "hold", label: "" };
  if (t.startsWith("*")) return { kind: "chord", label: "✱" };
  if (/^[xXo]/.test(t)) return { kind: t[0] === "X" ? "accent" : t[0] === "o" ? "soft" : "hit", label: t.length > 1 ? t.slice(1) : "" };
  if (t.includes("+")) return { kind: "stack", label: t.split("+").length + "♪" };
  if (/^[A-G]/.test(t)) return { kind: "note", label: t };
  return { kind: "degree", label: t };
}

// `text` with cell `cell` replaced by `symbol`.
export function replaceCell(text, cell, symbol) {
  return text.slice(0, cell.start) + symbol + text.slice(cell.end);
}

// The tokens of one bar written back: grouped by beat when every token is one character.
export function writeBar(tokens, beats) {
  const per = tokens.length % beats === 0 ? tokens.length / beats : 0;
  if (tokens.some((t) => t.length > 1) || per <= 1) return tokens.join(" ");
  const groups = [];
  for (let i = 0; i < tokens.length; i += per) groups.push(tokens.slice(i, i + per).join(""));
  return groups.join(" ");
}

// One bar's tokens at another step count: a step that starts on the new grid keeps its symbol, a
// new step inside a sounding one holds it (`-`, `sustain`) or rests; a hold after a rest rests.
export function resample(tokens, count, sustain) {
  const out = [];
  const old = tokens.length;
  for (let i = 0; i < count; i++) {
    const at = (i * old) / count;
    const j = Math.floor(at + 1e-9);
    if (Math.abs(at - j) < 1e-9) out.push(tokens[j]);
    else out.push(sustain && tokens[j] !== "." ? "-" : ".");
  }
  for (let i = 1; i < out.length; i++) if (out[i] === "-" && out[i - 1] === ".") out[i] = ".";
  return out;
}

// The text of `bars` (token lists) joined by " | ".
export function writeBars(bars, beats) {
  return bars.map((b) => writeBar(b, beats)).join(" | ");
}

// The accented steps of a bar of `steps` steps for accent groups like "3+3+2" (null: none fit).
export function accentSteps(accent, steps) {
  if (!accent) return null;
  const groups = String(accent).replace(/\s/g, "").split("+").map(Number);
  if (!groups.length || groups.some((g) => !Number.isInteger(g) || g < 1)) return null;
  const cycle = groups.reduce((a, b) => a + b, 0);
  if (steps % cycle) return null;
  const out = new Set();
  for (let c = 0; c < steps; c += cycle) {
    let s = 0;
    for (const g of groups) {
      out.add(c + s);
      s += g;
    }
  }
  return out;
}

// The grid's HTML for `read` (readSteps' result): one row per bar, cells sized by their share of
// the bar, grouped by beat; `accent` marks accented steps.
export function gridHtml(read, { beats, accent, pitched, idPrefix }) {
  return read.bars
    .map((bar, b) => {
      const accents = accentSteps(accent, bar.length);
      const per = bar.length % beats === 0 ? bar.length / beats : 0;
      const counts = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32];
      if (!counts.includes(bar.length)) counts.push(bar.length);
      counts.sort((x, y) => x - y);
      const cells = bar
        .map((cell, k) => {
          const { kind, label } = cellKind(cell.text);
          const beat = per > 1 && k % per === 0 && k > 0 ? " beat" : "";
          const acc = accents?.has(k) ? " acc" : "";
          const title = `bar ${b + 1}, step ${k + 1}: ${cell.text}`;
          return `<button type="button" class="cell ${kind}${beat}${acc}" id="${idPrefix}-${b}-${k}" data-bar="${b}" data-step="${k}" tabindex="-1"
            aria-label="${escapeHtml(title)}" title="${escapeHtml(title)}"><span>${escapeHtml(label)}</span></button>`;
        })
        .join("");
      const options = counts.map((n) => `<option value="${n}"${n === bar.length ? " selected" : ""}>${n}</option>`).join("");
      return `<div class="bar-row" data-bar="${b}">
        <span class="bar-no">${b + 1}</span>
        <div class="cells${pitched ? " pitched" : ""}">${cells}</div>
        <select class="count" data-bar="${b}" aria-label="Steps in bar ${b + 1}" title="Steps in bar ${b + 1} (changing it keeps the notes where they fall)">${options}</select>
      </div>`;
    })
    .join("");
}
