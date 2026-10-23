// The studio's JSON API (DESIGN.md §94.2): every call returns `result` or throws an Error whose
// message is the server's (a score's problems, a bad request...). When the server does not answer
// at all (stopped, or the computer slept), the error says so and the page hears about it through
// `onConnection` (Step 200: the "not answering" banner and its retry).

const listeners = new Set();
let online = true;

// Call `fn(online)` whenever the server stops or starts answering again.
export function onConnection(fn) {
  listeners.add(fn);
}

function setOnline(value) {
  if (value === online) return;
  online = value;
  for (const fn of listeners) fn(value);
}

export const OFFLINE_MESSAGE = "the studio server is not answering (was vidgen studio stopped?)";

async function call(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    setOnline(false);
    throw new Error(OFFLINE_MESSAGE);
  }
  setOnline(true);
  let doc;
  try {
    doc = await response.json();
  } catch {
    throw new Error(`${path}: HTTP ${response.status}`);
  }
  if (!doc.ok) throw new Error(doc.error || `${path}: HTTP ${response.status}`);
  return doc.result;
}

export const api = {
  info: () => call("GET", "/api/info"),
  presets: () => call("GET", "/api/presets"),
  patches: () => call("GET", "/api/patches"),
  session: () => call("GET", "/api/session"),
  score: (version) => call("GET", `/api/score?version=${encodeURIComponent(version)}`),
  load: (preset) => call("POST", "/api/load", { preset }),
  loadText: (text) => call("POST", "/api/load", { text }),
  validate: (text) => call("POST", "/api/validate", { text }),
  render: (version, section, mute, narration = false, variation = null) =>
    call("POST", "/api/render", { version, section: section || null, mute: mute || [], narration: Boolean(narration), variation: variation || null }),
  facts: (key) => call("GET", `/api/facts?key=${encodeURIComponent(key)}`),
  edit: (version, ops, label, dryRun = false) => call("POST", "/api/edit", { version, ops, label: label || null, dry_run: dryRun }),
  text: (version, text) => call("POST", "/api/text", { version, text }),
  undo: () => call("POST", "/api/undo", {}),
  redo: () => call("POST", "/api/redo", {}),
  setCurrent: (version) => call("POST", "/api/current", { version }),
  updateVersion: (version, changes) => call("POST", "/api/version", { version, ...changes }),
  sessions: () => call("GET", "/api/sessions"),
  openSession: (session) => call("POST", "/api/open", { session }),
  check: (version, wait = 0) => call("POST", "/api/check", { version, wait }),
  applyCheck: (version, key, edit) => call("POST", "/api/check/apply", { version, key, edit }),
  exportFile: (version, options) => call("POST", "/api/export", { version, ...options }),
  savePiece: (version, name, overwrite = false) => call("POST", "/api/save", { version, name, overwrite }),
  poll: (since) => call("GET", `/api/session?since=${encodeURIComponent(since ?? 0)}`),
  addNote: (version, seconds, text) => call("POST", "/api/notes", { version, seconds, text }),
  updateNote: (id, changes) => call("POST", "/api/notes/update", { id, ...changes }),
  ask: (version) => call("POST", "/api/ask", { version }),
  pasteReply: (reply) => call("POST", "/api/proposal/paste", { reply }),
  sendToProvider: (model) => call("POST", "/api/proposal/send", { model }),
  decideProposal: (id, keep) => call("POST", "/api/proposal/decide", { id, keep }),
  variations: (request) => call("POST", "/api/variations", request),
  variationBatch: (batch) => call("GET", `/api/variations?batch=${encodeURIComponent(batch)}`),
  keepVariation: (batch, letter) => call("POST", "/api/variations/keep", { batch, letter }),
  variationBatches: () => call("GET", "/api/variations"),
  lastHandoff: () => call("GET", "/api/ask"),
  disk: () => call("GET", "/api/disk"),
  cleanUp: () => call("POST", "/api/cleanup", {}),
};
