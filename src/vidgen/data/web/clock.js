// vidgen's virtual clock for a `web` scene (DESIGN.md §118.8). A fragment: web/page.py joins
// clock.js, media.js and runtime.js into one script that Chromium runs before any script of the
// page, with VIDGEN_SEED defined. Time stands at 0 ms until vidgen advances it to a frame's time.

const native = {
  Date: window.Date,
  setTimeout: window.setTimeout.bind(window),
  clearTimeout: window.clearTimeout.bind(window),
  fetch: window.fetch.bind(window),
  getRandomValues: crypto.getRandomValues.bind(crypto),
};
// Date.now() at t = 0 (2026-01-01T00:00:00Z); the page runs in the UTC time zone.
const EPOCH_MS = native.Date.UTC(2026, 0, 1);
// More timer callbacks than this before one frame is an error (a loop of timers).
const TIMER_CAP = 10000;
// The HTML rule: a timer set from a timer nested more than 5 deep waits at least 4 ms.
const NESTING_LIMIT = 5;
const NESTED_MIN_DELAY_MS = 4;

let nowMs = 0;

// ----- Date and performance -----------------------------------------------------------------

function VirtualDate(...args) {
  if (new.target === undefined) return new native.Date(EPOCH_MS + nowMs).toString();
  return Reflect.construct(native.Date, args.length ? args : [EPOCH_MS + nowMs], new.target);
}
VirtualDate.prototype = native.Date.prototype;
VirtualDate.now = () => Math.floor(EPOCH_MS + nowMs);
VirtualDate.parse = native.Date.parse;
VirtualDate.UTC = native.Date.UTC;
Object.defineProperty(native.Date.prototype, 'constructor', { value: VirtualDate, writable: true, configurable: true });
window.Date = VirtualDate;
Object.defineProperty(performance, 'now', { value: () => nowMs, writable: true, configurable: true });
Object.defineProperty(document.timeline, 'currentTime', { get: () => nowMs, configurable: true });

// ----- timers ---------------------------------------------------------------------------------

const timers = new Map();   // id -> {id, order, due, fn, args, interval, level}
let nextTimerId = 1;
let nextTimerOrder = 1;
let runningLevel = 0;       // nesting level of the timer callback running now (0: none)

function delayOf(delay, level) {
  let ms = Number(delay);
  if (!(ms >= 0)) ms = 0;
  return level > NESTING_LIMIT && ms < NESTED_MIN_DELAY_MS ? NESTED_MIN_DELAY_MS : ms;
}

function addTimer(handler, delay, args, repeat) {
  const fn = typeof handler === 'function' ? handler : () => (0, eval)(String(handler));
  const ms = delayOf(delay, runningLevel);
  const id = nextTimerId++;
  timers.set(id, { id, order: nextTimerOrder++, due: nowMs + ms, fn, args, interval: repeat ? ms : null, level: runningLevel + 1 });
  return id;
}

window.setTimeout = (handler, delay, ...args) => addTimer(handler, delay, args, false);
window.setInterval = (handler, delay, ...args) => addTimer(handler, delay, args, true);
window.clearTimeout = window.clearInterval = (id) => { timers.delete(Number(id)); };
window.requestIdleCallback = (fn) => addTimer(() => fn({ didTimeout: false, timeRemaining: () => 50 }), 0, [], false);
window.cancelIdleCallback = window.clearTimeout;

function nextDueTimer(targetMs) {
  let next = null;
  for (const timer of timers.values()) {
    if (timer.due <= targetMs && (next === null || timer.due < next.due || (timer.due === next.due && timer.order < next.order))) next = timer;
  }
  return next;
}

// ----- requestAnimationFrame -------------------------------------------------------------------

let animationFrames = new Map();   // id -> callback, for the next frame
let runningFrames = null;          // the round being run (a callback cancelled in it is skipped)
let nextFrameId = 1;
window.requestAnimationFrame = (fn) => { const id = nextFrameId++; animationFrames.set(id, fn); return id; };
window.cancelAnimationFrame = (id) => { animationFrames.delete(Number(id)); if (runningFrames) runningFrames.delete(Number(id)); };

// ----- random numbers, seeded from the scene id ------------------------------------------------

function sfc32(a, b, c, d) {
  return () => {
    a >>>= 0; b >>>= 0; c >>>= 0; d >>>= 0;
    const t = (a + b | 0) + d | 0;
    d = d + 1 | 0;
    a = b ^ b >>> 9;
    b = c + (c << 3) | 0;
    c = c << 21 | c >>> 11;
    c = c + t | 0;
    return (t >>> 0) / 4294967296;
  };
}
const nextRandom = sfc32(...VIDGEN_SEED.slice(0, 4));
const nextByte = (() => { const next = sfc32(...VIDGEN_SEED.slice(4, 8)); return () => Math.floor(next() * 256); })();
Math.random = nextRandom;
Object.defineProperty(crypto, 'getRandomValues', {
  value(array) {
    native.getRandomValues(array);   // its checks: an integer typed array, at most 65536 bytes
    const bytes = new Uint8Array(array.buffer, array.byteOffset, array.byteLength);
    for (let i = 0; i < bytes.length; i++) bytes[i] = nextByte();
    return array;
  }, writable: true, configurable: true,
});
Object.defineProperty(crypto, 'randomUUID', {
  value() {
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const hex = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }, writable: true, configurable: true,
});

// ----- loading the page started: fetch() and its bodies --------------------------------------

const loading = new Set();
function tracked(promise) {
  loading.add(promise);
  const done = () => loading.delete(promise);
  promise.then(done, done);
  return promise;
}
window.fetch = (...args) => tracked(native.fetch(...args));
for (const name of ['arrayBuffer', 'blob', 'formData', 'json', 'text', 'bytes']) {
  const method = Response.prototype[name];
  if (typeof method === 'function') Response.prototype[name] = function (...args) { return tracked(method.apply(this, args)); };
}

// ----- running the clock -----------------------------------------------------------------------

const hop = (() => {
  // One task later: the microtasks queued so far (and those they queue) have all run.
  const channel = new MessageChannel();
  const waiting = [];
  channel.port1.onmessage = () => waiting.shift()();
  return () => new Promise((resolve) => { waiting.push(resolve); channel.port2.postMessage(0); });
})();

// Runs, in order of due time (ties: in the order they were set), every timer due by targetMs,
// each at its own due time and followed by its microtasks and afterEach(); timers set by a timer
// run in the same call when due by then. Leaves the clock at targetMs.
async function runTimers(targetMs, afterEach, report) {
  let count = 0;
  for (let timer = nextDueTimer(targetMs); timer !== null; timer = nextDueTimer(targetMs)) {
    if (++count > TIMER_CAP) {
      timers.clear();
      throw new Error(`more than ${TIMER_CAP} timer callbacks before one frame (a setTimeout or setInterval loop?); vidgen cleared the timers`);
    }
    nowMs = Math.max(nowMs, timer.due);
    if (timer.interval === null) timers.delete(timer.id);
    runningLevel = timer.level;
    try {
      timer.fn.apply(window, timer.args);
    } catch (error) {
      report(error);
    } finally {
      runningLevel = 0;
    }
    if (timer.interval !== null && timers.has(timer.id)) {
      timer.due = nowMs + delayOf(timer.interval, timer.level);
      timer.order = nextTimerOrder++;
      timer.level += 1;
    }
    await hop();
    afterEach();
  }
  nowMs = Math.max(nowMs, targetMs);
}

// One round of animation-frame callbacks at the current time: those requested before the round,
// in the order requested, each followed by its microtasks; those requested during it wait.
async function runAnimationFrames(report) {
  runningFrames = animationFrames;
  animationFrames = new Map();
  for (const [id, fn] of runningFrames) {
    runningFrames.delete(id);
    try {
      fn(nowMs);
    } catch (error) {
      report(error);
    }
    await hop();
  }
  runningFrames = null;
}

// Waits until every fetch() the page started (and every body it reads) has settled.
async function settleLoading() {
  while (loading.size) {
    await Promise.allSettled([...loading]);
    await hop();
  }
}

const clock = { now: () => nowMs, runTimers, runAnimationFrames, settleLoading, hop, native };
