// The score file shown with highlighting and line numbers (DESIGN.md §94.5). Step 195 makes it
// editable both ways; here it shows the version's text as written, problems marked by line.

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
export const escapeHtml = (text) => String(text).replace(/[&<>"]/g, (c) => ESCAPES[c]);

// Where a comment starts in a line: a `#` at the start or after a space, outside quotes.
function commentStart(line) {
  let quote = null;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quote) {
      if (c === quote) quote = null;
    } else if (c === '"' || c === "'") {
      quote = c;
    } else if (c === "#" && (i === 0 || /\s/.test(line[i - 1]))) {
      return i;
    }
  }
  return -1;
}

const TOKEN = /("(?:[^"\\]|\\.)*"?|'[^']*'?)|(-?\b\d+(?:\.\d+)?\b)|([{}[\],|])|([A-Za-z_][\w-]*)(\s*:(?=\s|$))/g;

function highlightCode(code) {
  let out = "";
  let last = 0;
  for (const m of code.matchAll(TOKEN)) {
    out += escapeHtml(code.slice(last, m.index));
    if (m[1]) out += `<span class="s">${escapeHtml(m[1])}</span>`;
    else if (m[2]) out += `<span class="n">${m[2]}</span>`;
    else if (m[3]) out += `<span class="p">${escapeHtml(m[3])}</span>`;
    else out += `<span class="k">${escapeHtml(m[4])}</span><span class="p">${escapeHtml(m[5])}</span>`;
    last = m.index + m[0].length;
  }
  return out + escapeHtml(code.slice(last));
}

export function highlightLine(line) {
  const at = commentStart(line);
  const code = at < 0 ? line : line.slice(0, at);
  const comment = at < 0 ? "" : `<span class="c">${escapeHtml(line.slice(at))}</span>`;
  return highlightCode(code) + comment;
}

// The lines (1-based) of `text` that `before` did not have: what an edit changed.
export function changedLines(before, text) {
  if (!before) return new Set();
  const left = new Map();
  for (const line of before.split("\n")) left.set(line, (left.get(line) || 0) + 1);
  const out = new Set();
  text.split("\n").forEach((line, i) => {
    const n = left.get(line) || 0;
    if (n) left.set(line, n - 1);
    else if (line.trim()) out.add(i + 1);
  });
  return out;
}

// Show `text` in `pre`; `badLines` (1-based) are marked, `changed` lines flash and the first
// one is scrolled into view (the line a control just changed).
export function showYaml(pre, text, badLines = new Set(), changed = new Set()) {
  const lines = text.replace(/\n$/, "").split("\n");
  pre.innerHTML = lines
    .map((line, i) => {
      const cls = `ln${badLines.has(i + 1) ? " bad" : ""}${changed.has(i + 1) ? " changed" : ""}`;
      return `<span class="${cls}">${highlightLine(line) || " "}</span>`;
    })
    .join("");
  const first = pre.querySelector(".ln.changed");
  const panel = pre.parentElement;
  if (first && panel && panel.scrollHeight > panel.clientHeight) {
    // scroll the panel only (never the page, never sideways) so the changed line is in view
    const top = first.getBoundingClientRect().top - panel.getBoundingClientRect().top + panel.scrollTop;
    if (top < panel.scrollTop + 30 || top > panel.scrollTop + panel.clientHeight - 40) panel.scrollTop = Math.max(0, top - panel.clientHeight / 3);
  }
}
