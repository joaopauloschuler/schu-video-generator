// The studio's JSON API (DESIGN.md §94.2): every call returns `result` or throws an Error whose
// message is the server's (a score's problems, a bad request...).

async function call(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
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
  render: (version, section, mute, narration = false) =>
    call("POST", "/api/render", { version, section: section || null, mute: mute || [], narration: Boolean(narration) }),
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
};
