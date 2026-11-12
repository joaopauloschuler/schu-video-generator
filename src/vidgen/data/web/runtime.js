// vidgen's part of a `web` scene's page (DESIGN.md §118). Run by Chromium before any script of
// the page: it records the page's uncaught errors and, before each screenshot, calls the page's
// frame(t, ctx) hook (window.vidgen.frame; a `script:` module's exported frame is put there).
(() => {
  if (window.top !== window) return;
  const errors = [];
  const describe = (error) => {
    if (error instanceof Error) return { message: `${error.name}: ${error.message}`, stack: error.stack || '' };
    return { message: String(error), stack: '' };
  };
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
  let ctx = null;
  const run = {
    errors,
    ready: false,
    // After the page loaded: the context every hook is given (Steps 329-330 add to it).
    async start(info) {
      await document.fonts.ready;
      ctx = { ...info, canvas: document.getElementById('vidgen-canvas') };
      return errors.splice(0);
    },
    // Before the screenshot of the frame at t seconds; returns the errors since the last call.
    async frame(t) {
      const hook = (window.vidgen || {}).frame;
      if (hook !== undefined && typeof hook !== 'function') {
        errors.push({ message: `TypeError: window.vidgen.frame is a ${typeof hook}, not a function`, stack: '' });
      } else if (hook !== undefined) {
        try {
          await hook(t, ctx);
        } catch (error) {
          errors.push(describe(error));
        }
      }
      return errors.splice(0);
    },
  };
  Object.defineProperty(window, '__vidgen', { value: run });
})();
