// vidgen/title-cards: an opening title and a matching end card for films. Part
// of schu-video-generator (MIT licence); imported by a page as "vidgen/title-cards".
//
//   const title = await titleCard(ctx, {title: "ESCAPEMENT", subtitle: "a clockwork film in D minor"});
//   const end = await endCard(ctx, {title: "ESCAPEMENT", subtitle: "made with ...", lines: ["..."], start: 8});
//   title.update(t); end.update(t);          // in frame(t, ctx): the opacity at time t (0..1)
//
// HTML text over the page (crisp at any size, not drawn by WebGL), laid out as "Escapement"'s
// (examples/escapement): a small title with wide letter spacing in the left or right third, a thin
// rule, one quiet subtitle; the end card the same type, smaller, on the other side, with a few
// small lines under it. A soft dark gradient behind the block keeps the text on quiet space. The
// opacity is a function of t alone (fade in, hold, fade out), and the letter spacing opens a
// little while the card shows: the same t, the same picture. Sizes follow the frame: k is 1% of
// the width of a 16:9 frame (the height x 16/9 when the frame is wider), 1.7% of the width in a
// portrait frame, where the block sits in the lower part (or the top) rather than a third.
// Plain JavaScript and the DOM: no three.js, so it works on any `web` page.

export const VERSION = 1;

const PREFIX = "vidgen/title-cards";
const SIDES = ["left", "right", "top", "bottom"];
const ALIGNS = ["left", "right"];

// ---------- defaults: "Escapement"'s opening and end card ----------
const COMMON = {
  title: null, subtitle: "", side: "left", align: "left", y: null,
  start: 2, fadeIn: 2, hold: 8, fadeOut: 2,
  size: 3.9, tracking: 0.26, settle: 0.03, subSize: 1.15, subTracking: 0.42, uppercase: true,
  font: null, subFont: null, color: "#f3ede2", subColor: "#aab4c8", accent: "#d9b46a",
  glow: "rgba(150,180,255,.35)", rule: true, shade: 0.45, id: "title-card",
};
/** The opening card's options and their defaults. */
export const TITLE_DEFAULTS = Object.freeze({...COMMON});
/** The end card's options and their defaults (hold: Infinity = until the scene ends). */
export const END_DEFAULTS = Object.freeze({
  ...COMMON, side: "right", start: 1, fadeIn: 2.5, hold: Infinity, fadeOut: 0,
  size: 2.7, tracking: 0.3, subColor: "#c9bda9", glow: "rgba(255,200,120,.3)", id: "end-card",
  lines: [], link: "", lineFont: null, linkFont: null, lineColor: "#d8ccb8", linkColor: "#fff3df", lineSize: 1.5, linkSize: 1.22,
});

// ---------- options ----------
function distance(a, b) {
  const d = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = d[0]; d[0] = i;
    for (let j = 1; j <= b.length; j++) { const cur = d[j]; d[j] = Math.min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = cur; }
  }
  return d[b.length];
}
const fail = (msg) => new Error(`${PREFIX}: ${msg}`);
function unknown(fn, key, known) {
  const best = known.map((k) => [distance(key.toLowerCase(), k.toLowerCase()), k]).sort((x, y) => x[0] - y[0])[0];
  const hint = best && best[0] <= Math.max(2, key.length / 3) ? ` (did you mean "${best[1]}"?)` : "";
  return fail(`${fn}: unknown option "${key}"${hint}; known: ${known.join(", ")}`);
}
function number(fn, key, v, lo, hi) {
  if (typeof v !== "number" || Number.isNaN(v) || v < lo || v > hi) throw fail(`${fn}: ${key} must be a number from ${lo} to ${hi}, got ${JSON.stringify(v)}`);
  return v;
}
function text(fn, key, v, required = false) {
  if (typeof v !== "string" || (required && !v.trim())) throw fail(`${fn}: ${key} must be ${required ? "a non-empty" : "a"} string, got ${JSON.stringify(v)}`);
  return v;
}
function choice(fn, key, v, list) {
  if (!list.includes(v)) throw fail(`${fn}: ${key} must be one of ${list.map((x) => JSON.stringify(x)).join(", ")}, got ${JSON.stringify(v)}`);
  return v;
}

/** The options of `titleCard` ("title") or `endCard` ("end") with their defaults filled in,
 * checked: an unknown name or a wrong value throws an Error naming it (with a "did you mean"). */
export function cardOptions(kind, options = {}) {
  const fn = kind === "end" ? "endCard" : "titleCard", defaults = kind === "end" ? END_DEFAULTS : TITLE_DEFAULTS;
  if (options === null || typeof options !== "object" || Array.isArray(options)) throw fail(`${fn}: options must be an object, got ${JSON.stringify(options)}`);
  const known = Object.keys(defaults);
  for (const key of Object.keys(options)) if (!known.includes(key)) throw unknown(fn, key, known);
  const o = {...defaults, ...options};
  text(fn, "title", o.title ?? undefined, true); text(fn, "subtitle", o.subtitle);
  choice(fn, "side", o.side, SIDES); choice(fn, "align", o.align, ALIGNS);
  if (o.y !== null) number(fn, "y", o.y, 0.05, 0.95);
  number(fn, "start", o.start, -1e6, 1e6); number(fn, "fadeIn", o.fadeIn, 0, 600); number(fn, "fadeOut", o.fadeOut, 0, 600);
  if (o.hold !== Infinity) number(fn, "hold", o.hold, 0, 1e6);
  number(fn, "size", o.size, 0.5, 20); number(fn, "subSize", o.subSize, 0.3, 10);
  number(fn, "tracking", o.tracking, -0.1, 2); number(fn, "subTracking", o.subTracking, -0.1, 2); number(fn, "settle", o.settle, 0, 1);
  for (const key of ["font", "subFont"]) if (o[key] !== null) text(fn, key, o[key], true);
  for (const key of ["color", "subColor", "accent"]) text(fn, key, o[key], true);
  if (o.glow !== false) text(fn, "glow", o.glow, true);
  if (typeof o.rule !== "boolean") throw fail(`${fn}: rule must be true or false, got ${JSON.stringify(o.rule)}`);
  if (typeof o.uppercase !== "boolean") throw fail(`${fn}: uppercase must be true or false, got ${JSON.stringify(o.uppercase)}`);
  if (o.shade === true) o.shade = defaults.shade || COMMON.shade;
  if (o.shade !== false) number(fn, "shade", o.shade, 0, 1);
  text(fn, "id", o.id, true);
  if (kind === "end") {
    if (!Array.isArray(o.lines)) throw fail(`endCard: lines must be a list of strings, got ${JSON.stringify(o.lines)}`);
    o.lines.forEach((line, i) => text(fn, `lines[${i}]`, line));
    text(fn, "link", o.link);
    for (const key of ["lineFont", "linkFont"]) if (o[key] !== null) text(fn, key, o[key], true);
    for (const key of ["lineColor", "linkColor"]) text(fn, key, o[key], true);
    number(fn, "lineSize", o.lineSize, 0.3, 10); number(fn, "linkSize", o.linkSize, 0.3, 10);
  }
  return o;
}

// ---------- time ----------
const smooth = (u) => { u = Math.min(1, Math.max(0, u)); return u * u * (3 - 2 * u); };
/** The card's opacity at time t (0..1): a smooth fade in over fadeIn from start, hold, a smooth
 * fade out over fadeOut (none while hold is Infinity). */
export function cardAlpha(t, {start, fadeIn, hold, fadeOut}) {
  const inA = fadeIn > 0 ? smooth((t - start) / fadeIn) : (t >= start ? 1 : 0);
  if (hold === Infinity) return inA;
  const out = start + fadeIn + hold;
  return inA * (fadeOut > 0 ? 1 - smooth((t - out) / fadeOut) : (t < out ? 1 : 0));
}
/** How far the title's letter spacing has opened at time t (0..1): from the start of the fade in
 * to the end of the fade out (to 8 s after the fade in when the card holds to the end). */
export function cardSettle(t, {start, fadeIn, hold, fadeOut}) {
  const span = hold === Infinity ? fadeIn + 8 : fadeIn + hold + fadeOut;
  return span > 0 ? smooth((t - start) / span) : 1;
}

// ---------- layout ----------
/** Where the block goes in a frame width x height (CSS pixels): `k` (the size unit), `x` (left
 * edge), `width` (the widest a line may be), `y` (the block's vertical centre), `align`, `portrait`,
 * `side` (as placed: a portrait frame puts "left" / "right" at the bottom) and `shade` (the
 * gradient's direction in degrees: it is darkest at the block's edge of the frame). */
export function cardLayout(width, height, {side = "left", align = "left", y = null} = {}) {
  const portrait = height > width;
  const k = portrait ? 0.017 * width : 0.01 * Math.min(width, height * 16 / 9);
  let place = side, x, w, cy;
  if (portrait && (side === "left" || side === "right")) place = "bottom";
  if (place === "left") { x = 0.055 * width; w = 0.4 * width; cy = 0.46; }
  else if (place === "right") { x = 0.51 * width; w = 0.435 * width; cy = 0.45; }
  else { const m = portrait ? 0.08 : 0.055; x = m * width; w = (1 - 2 * m) * width; cy = place === "top" ? 0.24 : (portrait ? 0.64 : 0.7); }
  const shade = {left: 90, right: 270, top: 180, bottom: 0}[place];
  return {k, x, width: w, y: (y ?? cy) * height, align, portrait, side: place, shade};
}

// ---------- the cards ----------
const family = (name, generic) => (name ? `"${name}", ${generic}` : generic);
function themeFonts(ctx) {
  const f = (ctx && ctx.theme && ctx.theme.fonts) || {};
  return {serif: f.serif || null, sans: f.body || f.sans || null, mono: f.mono || null};
}
const STYLE_ID = "vidgen-title-cards";
const CSS = `
.vg-card{position:fixed;left:0;top:0;width:100vw;height:100vh;pointer-events:none;z-index:20;display:none}
.vg-card-shade{position:absolute;left:0;top:0;width:100%;height:100%}
.vg-card-block{position:absolute;display:flex;flex-direction:column;transform:translateY(-50%)}
.vg-card-block>div{white-space:nowrap}
.vg-card-block>.vg-card-line{white-space:normal}`;

async function makeCard(kind, ctx, options) {
  const o = cardOptions(kind, options);
  if (typeof document === "undefined") throw fail(`${kind === "end" ? "endCard" : "titleCard"} needs a page (document)`);
  const fonts = themeFonts(ctx);
  const titleFont = o.font ? family(o.font, "Georgia, serif") : family(fonts.serif, "Georgia, serif");
  const subFont = o.subFont ? family(o.subFont, "sans-serif") : family(fonts.sans, "sans-serif");
  const lineFont = o.lineFont ? family(o.lineFont, "Georgia, serif") : titleFont;
  const linkFont = o.linkFont ? family(o.linkFont, "monospace") : family(fonts.mono, "monospace");
  try {
    const wanted = [`500 40px ${titleFont}`, `400 40px ${subFont}`];
    if (kind === "end") wanted.push(`italic 400 40px ${lineFont}`, `400 40px ${linkFont}`);
    for (const f of wanted) await document.fonts.load(f);
  } catch (e) { /* the fallback font is used */ }
  if (!document.getElementById(STYLE_ID)) { const s = document.createElement("style"); s.id = STYLE_ID; s.textContent = CSS; document.head.append(s); }

  const W = window.innerWidth, H = window.innerHeight, L = cardLayout(W, H, o), k = L.k;
  const el = (cls, parent, txt) => { const d = document.createElement("div"); d.className = cls; if (txt) d.textContent = txt; parent.append(d); return d; };
  const root = el("vg-card", document.body);
  root.dataset.vidgenId = o.id; root.dataset.vidgenLint = "off:min_font";      // small type on purpose
  if (o.shade !== false) {
    const s = o.shade, sh = el("vg-card-shade", root);
    sh.style.background = `linear-gradient(${L.shade}deg, rgba(0,0,0,${s}) 0%, rgba(0,0,0,${(0.55 * s).toFixed(3)}) 32%, rgba(0,0,0,0) ${L.portrait || L.side === "top" || L.side === "bottom" ? 55 : 62}%)`;
  }
  const block = el("vg-card-block", root);
  Object.assign(block.style, {left: `${L.x}px`, top: `${L.y}px`, width: `${L.width}px`, alignItems: o.align === "right" ? "flex-end" : "flex-start", textAlign: o.align});
  const px = (v) => `${(v * k).toFixed(3)}px`;
  const title = el("vg-card-title", block, o.title);
  Object.assign(title.style, {fontFamily: titleFont, fontWeight: "500", fontSize: px(o.size), lineHeight: "1.1", color: o.color,
    letterSpacing: `${o.tracking}em`, textShadow: o.glow === false ? "none" : `0 0 ${px(0.36 * o.size)} ${o.glow}`});
  // the letter spacing's last em hangs after the last letter: pull it back so the block's edge is the letters'
  title.style.marginRight = o.align === "right" ? `-${o.tracking + o.settle}em` : "0";
  let below = 0.75 * o.size;
  if (o.rule) {
    const r = el("vg-card-rule", block), line = Math.max(1, Math.round(H / 720));
    Object.assign(r.style, {width: px(9), height: `${line}px`, marginTop: px(below), background: `linear-gradient(${o.align === "right" ? 270 : 90}deg, ${o.accent}, transparent)`});
    below = 1.7;
  }
  const lines = [];
  const sub = (txt, cls, font, size, color, tracking, upper, gap, extra = {}) => {
    const d = el(cls, block, txt);
    Object.assign(d.style, {fontFamily: font, fontSize: px(size), lineHeight: "1.1", color, letterSpacing: `${tracking}em`,
      textTransform: upper ? "uppercase" : "none", marginTop: px(gap), ...extra});
    if (o.align === "right") d.style.marginRight = `-${tracking}em`;
    lines.push(d); return d;
  };
  if (o.subtitle) { sub(o.subtitle, "vg-card-sub", subFont, o.subSize, o.subColor, o.subTracking, o.uppercase, below); below = 1.65; }
  if (kind === "end") {
    if (o.link) { sub(o.link, "vg-card-link", linkFont, o.linkSize, o.linkColor, 0.01, false, below); below = 1.65; }
    o.lines.forEach((txt, i) => sub(txt, "vg-card-line", lineFont, o.lineSize, o.lineColor, 0, false, i === 0 ? below + 2.45 : 0,
      {fontStyle: "italic", lineHeight: "1.65", maxWidth: `${L.width}px`}));
  }
  // too wide for its side (a long title, a narrow frame): that line is set smaller until it fits
  root.style.display = "block"; root.style.visibility = "hidden";
  title.style.letterSpacing = `${o.tracking + o.settle}em`;
  for (const d of [title, ...lines.filter((d) => !d.classList.contains("vg-card-line"))]) {
    const w = d.scrollWidth;
    if (w > L.width) d.style.fontSize = `${(parseFloat(d.style.fontSize) * L.width / w * 0.995).toFixed(3)}px`;
  }
  root.style.display = "none"; root.style.visibility = "";

  const card = {
    element: root, options: o, layout: L,
    /** Show the card as it is at time t (the clock `start` is on); returns its opacity. */
    update(t) {
      const a = cardAlpha(t, o);
      root.style.opacity = a.toFixed(3); root.style.display = a > 0.002 ? "block" : "none";
      title.style.letterSpacing = `${(o.tracking + o.settle * cardSettle(t, o)).toFixed(4)}em`;
      return a;
    },
  };
  card.update(-Infinity);
  return card;
}

/** An opening title: `await titleCard(ctx, {title, subtitle, side, start, fadeIn, hold, fadeOut, ...})`
 * in load, then `.update(t)` in frame. Options and defaults: TITLE_DEFAULTS (docs/CONFIG.md). */
export function titleCard(ctx, options) { return makeCard("title", ctx, options); }
/** An end card in the same type: `await endCard(ctx, {title, subtitle, link, lines: [...], side, start, ...})`
 * in load, then `.update(t)` in frame. Options and defaults: END_DEFAULTS (docs/CONFIG.md). */
export function endCard(ctx, options) { return makeCard("end", ctx, options); }
