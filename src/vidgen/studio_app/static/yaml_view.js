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

// Show `text` in `pre`; `badLines` (1-based) are marked.
export function showYaml(pre, text, badLines = new Set()) {
  const lines = text.replace(/\n$/, "").split("\n");
  pre.innerHTML = lines
    .map((line, i) => `<span class="ln${badLines.has(i + 1) ? " bad" : ""}">${highlightLine(line) || " "}</span>`)
    .join("");
}
