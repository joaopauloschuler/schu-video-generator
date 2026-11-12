// vidgen's part of a `web` scene's page (DESIGN.md §118.3, §118.8). A fragment joined after
// clock.js and media.js: it records the page's uncaught errors, runs the page's hooks
// (window.vidgen.load and .frame; a `script:` module's exports are put there) and, for each frame,
// moves the clock and the page's animations to the frame's time.
const errors = [];
const describe = (error) => {
  if (error instanceof Error) return { message: `${error.name}: ${error.message}`, stack: error.stack || '' };
  return { message: String(error), stack: '' };
};
const report = (error) => errors.push(describe(error));
window.addEventListener('error', (event) => {
  if (event instanceof ErrorEvent) {
    const described = event.error !== undefined && event.error !== null ? describe(event.error) : { message: event.message, stack: '' };
    errors.push({ ...described, file: event.filename || '', line: event.lineno || 0, column: event.colno || 0 });
  } else if (event.target instanceof HTMLScriptElement) {
    const src = event.target.src;
    errors.push({ message: src ? `the script ${src} did not load` : 'a module script did not load (a file it imports is missing or refused)', file: src, line: 0, column: 0, stack: '' });
  }
}, true);
window.addEventListener('unhandledrejection', (event) => {
  const described = describe(event.reason);
  errors.push({ message: `unhandled promise rejection: ${described.message}`, stack: described.stack });
});

// The page's hook `name`, or undefined; a value that is not a function is an error.
function hookOf(name) {
  const hook = (window.vidgen || {})[name];
  if (hook !== undefined && typeof hook !== 'function') {
    errors.push({ message: `TypeError: window.vidgen.${name} is a ${typeof hook}, not a function`, stack: '' });
    return undefined;
  }
  return hook;
}

async function callHook(name, ...args) {
  const hook = hookOf(name);
  if (hook === undefined) return;
  try {
    await hook(...args);
  } catch (error) {
    report(error);
  }
}

// The page's fonts: every font face declared and not loaded yet (the theme's among them) is
// loaded before frame 0, so text shown later is not first drawn in a fallback font.
async function settleFonts() {
  await Promise.allSettled([...document.fonts].filter((face) => face.status === 'unloaded').map((face) => face.load()));
  await document.fonts.ready;
}

// The narration beat of frame n: the last beat starting at or before it (-1 before the first).
function beatOf(n) {
  let index = -1;
  ctx.beats.forEach((beat, i) => { if (Math.round(beat.start * ctx.fps) <= n) index = i; });
  return index;
}

// data-beat and data-beat-index on <body> follow the beat of frame n; a `vidgen-beat` event
// (bubbling from <body>) is dispatched when frame n's beat is not the one announced last.
let shownBeat = -1;
let announcedBeat = -1;
function showBeat(n, announce) {
  const index = beatOf(n);
  const body = document.body;
  if (index < 0 || body === null) return;
  const beat = ctx.beats[index];
  if (index !== shownBeat) {
    body.dataset.beat = beat.id;
    body.dataset.beatIndex = String(index);
    shownBeat = index;
  }
  if (announce && index !== announcedBeat) {
    const previous = announcedBeat >= 0 ? ctx.beats[announcedBeat] : null;
    announcedBeat = index;
    body.dispatchEvent(new CustomEvent('vidgen-beat', { bubbles: true, detail: { beat, index, previous, t: n / ctx.fps } }));
  }
}

let ctx = null;
const run = {
  errors,
  ready: false,
  // The page's ctx (for vidgen's layout reader, data/web/layout.js, which passes it to layout(t, ctx)).
  get ctx() { return ctx; },
  // After the page loaded, before frame 0 (the clock at 0): data-beat of frame 0, fonts,
  // pictures and videos, then load(ctx). Returns the errors so far.
  async start(info) {
    ctx = { ...info, canvas: document.getElementById('vidgen-canvas') };
    showBeat(0, false);
    await settleFonts();
    await media.decodeImages();
    await clock.settleLoading();
    await media.placeMedia();
    await callHook('load', ctx);
    await clock.settleLoading();
    await settleFonts();
    await media.decodeImages();
    await media.placeMedia();
    return errors.splice(0);
  },
  // Frame n, before its screenshot: the clock moves to n / fps; the timers due by then run;
  // data-beat follows the frame's beat (and `vidgen-beat` is dispatched when it changed); the
  // page's loading settles, animations, SVGs and videos are set to the time, one round of
  // animation-frame callbacks runs, then frame(t, ctx); what that started is set to the time too.
  // Returns the errors since the last call.
  async frame(n) {
    const ms = n * 1000 / ctx.fps;
    try {
      await clock.runTimers(ms, media.discoverMedia, report);
    } catch (error) {
      report(error);
    }
    showBeat(n, true);
    await clock.hop();
    await clock.settleLoading();
    await document.fonts.ready;
    await media.decodeImages();
    await media.placeMedia();
    await clock.runAnimationFrames(report);
    await callHook('frame', n / ctx.fps, ctx);
    await clock.settleLoading();
    await document.fonts.ready;
    await media.decodeImages();
    await media.placeMedia();
    return errors.splice(0);
  },
};
Object.defineProperty(window, '__vidgen', { value: run });
