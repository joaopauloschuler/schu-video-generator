// vidgen's layout reader for a `web` scene (DESIGN.md §118.12). web/page.py evaluates this function
// after a frame's screenshot, never before one, so reading changes nothing drawn. It returns the
// text the page shows and where, in page pixels: one item per element that holds visible text
// (its text nodes and those of its inline children; an SVG <text> with its <tspan>s), plus what the
// page declares with window.vidgen.layout(t, ctx) (text drawn on a canvas cannot be read).
async (t) => {
  const W = window.innerWidth;
  const H = window.innerHeight;
  const styles = new Map();
  const style = (el) => {
    let s = styles.get(el);
    if (s === undefined) { s = getComputedStyle(el); styles.set(el, s); }
    return s;
  };
  const probe = document.createElement('canvas').getContext('2d');

  // [r, g, b, a] (0..255, alpha 0..1) of a CSS colour, or null for none / a paint server.
  function rgba(css) {
    if (typeof css !== 'string' || css === '' || css === 'none' || css.startsWith('url(')) return null;
    let m = /^rgba?\(([^)]*)\)$/.exec(css.trim());
    if (m === null) {
      probe.fillStyle = '#000';
      probe.fillStyle = css;
      const v = probe.fillStyle;
      if (/^#[0-9a-f]{6}$/i.test(v)) return [parseInt(v.slice(1, 3), 16), parseInt(v.slice(3, 5), 16), parseInt(v.slice(5, 7), 16), 1];
      m = /^rgba?\(([^)]*)\)$/.exec(v);
      if (m === null) return null;
    }
    const parts = m[1].split(/[\s,/]+/).filter((p) => p !== '').map(Number);
    if (parts.length < 3 || parts.some((p) => Number.isNaN(p))) return null;
    return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1];
  }
  const hex = (c) => '#' + c.slice(0, 3).map((v) => Math.round(Math.min(Math.max(v, 0), 255)).toString(16).padStart(2, '0')).join('').toUpperCase();
  const over = (top, under) => [0, 1, 2].map((i) => top[i] * top[3] + under[i] * (1 - top[3])).concat([1]);

  // Opacity through the element's ancestors.
  const opacities = new Map();
  function opacityOf(el) {
    if (el === null || !(el instanceof Element)) return 1;
    let o = opacities.get(el);
    if (o === undefined) { o = parseFloat(style(el).opacity) * opacityOf(el.parentElement); opacities.set(el, o); }
    return o;
  }

  // How much the element is scaled on screen (CSS transforms, `scale`, `zoom`), through its ancestors.
  const scales = new Map();
  const det = (m) => Math.sqrt(Math.abs(m.a * m.d - m.b * m.c));
  function scaleOf(el) {
    if (el === null || !(el instanceof Element)) return 1;
    if (el instanceof SVGElement && !(el instanceof SVGSVGElement) && typeof el.getScreenCTM === 'function') {
      const m = el.getScreenCTM();   // user units to the viewport, the page's CSS transforms included
      if (m !== null) return det(m);
    }
    let k = scales.get(el);
    if (k === undefined) {
      const s = style(el);
      k = 1;
      if (s.transform && s.transform !== 'none') { try { k *= det(new DOMMatrixReadOnly(s.transform)); } catch (e) { /* not a matrix */ } }
      if (s.scale && s.scale !== 'none') {
        const v = s.scale.split(/\s+/).map(Number);
        k *= Math.sqrt(Math.abs(v[0] * (v.length > 1 ? v[1] : v[0])));
      }
      const zoom = parseFloat(s.zoom);
      if (zoom > 0) k *= zoom;
      k *= scaleOf(el.parentElement);
      scales.set(el, k);
    }
    return k;
  }

  // The cap height of a font in em (canvas text metrics of "H"); 0.7 when the font gives none.
  const caps = new Map();
  function capRatio(font) {
    let r = caps.get(font);
    if (r === undefined) {
      probe.font = font;
      const m = probe.measureText('H');
      r = m.actualBoundingBoxAscent > 0 ? m.actualBoundingBoxAscent / 100 : 0.7;
      caps.set(font, r);
    }
    return r;
  }
  const fontOf = (s) => `${s.fontStyle} ${s.fontWeight} 100px ${s.fontFamily}`;

  // A short CSS-like path naming an element (its data-vidgen-id when it has one).
  function segment(el) {
    if (el.dataset && el.dataset.vidgenId) return `[${el.dataset.vidgenId}]`;
    const tag = el.tagName.toLowerCase();
    if (el.id) return `${tag}#${el.id}`;
    let s = tag + (el.classList && el.classList.length ? '.' + el.classList[0] : '');
    const parent = el.parentElement;
    if (parent !== null && [...parent.children].filter((c) => c.tagName === el.tagName).length > 1) {
      s += `:nth-child(${[...parent.children].indexOf(el) + 1})`;
    }
    return s;
  }
  function nameOf(el) {
    if (el.dataset && el.dataset.vidgenId) return el.dataset.vidgenId;
    const parts = [];
    for (let a = el; a !== null && a !== document.body && a !== document.documentElement && parts.length < 3; a = a.parentElement) {
      parts.unshift(segment(a));
      if ((a.dataset && a.dataset.vidgenId) || a.id) break;
    }
    return parts.join(' > ') || el.tagName.toLowerCase();
  }

  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'TITLE', 'TEXTAREA', 'OPTION']);
  const isInline = (el) => {
    if (el instanceof SVGElement) return el.tagName !== 'text';
    const d = style(el).display;
    return d === 'inline' || d === 'contents';
  };
  // The element a text node's line belongs to: its nearest ancestor that is not inline.
  function holderOf(node) {
    let el = node.parentElement;
    if (el === null || el.closest('script, style, noscript, template, title, textarea, option') !== null) return null;
    if (el instanceof SVGElement) return el.closest('text');
    while (el !== null && el !== document.body && isInline(el)) el = el.parentElement;
    return el;
  }

  const unionBox = (boxes) => boxes.length === 0 ? null : [Math.min(...boxes.map((b) => b[0])), Math.min(...boxes.map((b) => b[1])),
    Math.max(...boxes.map((b) => b[2])), Math.max(...boxes.map((b) => b[3]))];
  const meet = (a, b) => [Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.min(a[2], b[2]), Math.min(a[3], b[3])];
  const rectBox = (r) => [r.left, r.top, r.right, r.bottom];
  function beyond(box, clip) {
    const sides = {};
    const px = { left: clip[0] - box[0], top: clip[1] - box[1], right: box[2] - clip[2], bottom: box[3] - clip[3] };
    for (const side in px) if (px[side] > 0.5) sides[side] = Math.round(px[side] * 10) / 10;
    return Object.keys(sides).length ? sides : null;
  }

  // The boxes that clip the holder's text: its own and its ancestors' with overflow other than
  // visible, as far up as they contain it (an absolutely placed box escapes ancestors below its
  // containing block, a fixed one all but transformed ones); the viewport is applied apart.
  function clipsOf(holder) {
    const out = [];
    const add = (a) => {
      const s = style(a);
      if (s.overflowX === 'visible' && s.overflowY === 'visible') return;
      const r = a.getBoundingClientRect();
      const k = a instanceof HTMLElement && a.offsetWidth > 0 ? r.width / a.offsetWidth : 1;
      out.push({ el: a, box: [r.left + parseFloat(s.borderLeftWidth) * k, r.top + parseFloat(s.borderTopWidth) * k,
        r.right - parseFloat(s.borderRightWidth) * k, r.bottom - parseFloat(s.borderBottomWidth) * k] });
    };
    add(holder);
    let el = holder;
    for (;;) {
      const position = style(el).position;
      let a = el.parentElement;
      while (a !== null && a !== document.body && a !== document.documentElement) {
        const s = style(a);
        if (position === 'fixed' ? s.transform !== 'none' : position !== 'absolute' || s.position !== 'static' || s.transform !== 'none') break;
        a = a.parentElement;
      }
      if (a === null || a === document.body || a === document.documentElement) break;
      add(a);
      el = a;
    }
    return out;
  }

  // What is behind a point of the holder's text: the colour (#RRGGBB, layers blended down to the
  // theme's background for a transparent page), or why it is not known (a picture, a gradient).
  const themeBackground = rgba((window.__vidgen.ctx && window.__vidgen.ctx.theme && window.__vidgen.ctx.theme.background) || '#000000') || [0, 0, 0, 1];
  const PICTURES = { IMG: 'picture', CANVAS: 'canvas', VIDEO: 'video', IFRAME: 'frame', OBJECT: 'picture', EMBED: 'picture', image: 'picture' };
  const SHAPES = new Set(['rect', 'circle', 'ellipse', 'path', 'polygon', 'polyline', 'line', 'use']);
  function backgroundAt(holder, x, y) {
    const stack = x >= 0 && y >= 0 && x < W && y < H ? document.elementsFromPoint(x, y) : [];
    let i = stack.findIndex((e) => e === holder || e.contains(holder));
    let below = i >= 0 ? stack.slice(i) : [];
    if (below.length === 0) { for (let a = holder; a !== null; a = a.parentElement) below.push(a); }
    const layers = [];
    for (const e of below) {
      if (e !== holder && holder.contains(e)) continue;
      const kind = PICTURES[e.tagName];
      if (kind !== undefined && !e.contains(holder)) return { unknown: kind };
      const s = style(e);
      let paint = null;
      if (e instanceof SVGElement && SHAPES.has(e.tagName)) {
        if (s.fill.startsWith('url(')) return { unknown: 'gradient' };
        paint = rgba(s.fill);
        if (paint !== null) paint[3] *= parseFloat(s.fillOpacity);
      } else if (!(e instanceof SVGElement) || e instanceof SVGSVGElement) {
        if (s.backgroundImage && s.backgroundImage !== 'none') return { unknown: s.backgroundImage.includes('gradient') ? 'gradient' : 'picture' };
        paint = rgba(s.backgroundColor);
      }
      if (paint === null || paint[3] <= 0) continue;
      paint[3] *= opacityOf(e);
      layers.push(paint);
      if (paint[3] >= 0.999) break;
    }
    let color = themeBackground;
    for (let k = layers.length - 1; k >= 0; k--) color = over(layers[k], color);
    return { color: hex(color) };
  }

  // ----- the page's text ----------------------------------------------------------------------
  const runs = new Map();   // holder -> its text nodes, in document order
  const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    if (!/\S/.test(node.data)) continue;
    const holder = holderOf(node);
    if (holder === null || SKIP.has(holder.tagName)) continue;
    if (!runs.has(holder)) runs.set(holder, []);
    runs.get(holder).push(node);
  }
  const range = document.createRange();
  const texts = [];
  let hidden = 0;
  const names = new Map();
  for (const [holder, nodes] of runs) {
    const seen = [];
    for (const node of nodes) {
      const el = node.parentElement;
      const s = style(el);
      if (s.visibility !== 'visible' || opacityOf(el) < 0.01) continue;
      let boxes;
      if (holder instanceof SVGElement) {
        boxes = [rectBox(el.getBoundingClientRect())];
      } else {
        range.selectNodeContents(node);
        boxes = [...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0).map(rectBox);
      }
      const box = unionBox(boxes.filter((b) => b[2] > b[0] && b[3] > b[1]));
      if (box === null) continue;
      const svg = el instanceof SVGElement;
      const fill = svg ? s.fill : (s.webkitTextFillColor || s.color);
      const color = rgba(fill);
      const clipText = !svg && (s.webkitBackgroundClip === 'text' || s.backgroundClip === 'text');
      if (color !== null && color[3] <= 0 && !clipText) continue;   // transparent text draws nothing
      const k = scaleOf(el);
      const size = parseFloat(s.fontSize) * k;
      seen.push({ text: node.data, box, size, cap: size * capRatio(fontOf(s)), color: clipText || color === null ? null : color,
        opacity: opacityOf(el) * (svg ? parseFloat(s.fillOpacity) : 1), chars: node.data.replace(/\s+/g, '').length });
    }
    if (seen.length === 0) { hidden += 1; continue; }
    const box = unionBox(seen.map((r) => r.box));
    let visible = meet(box, [0, 0, W, H]);
    let clipped = null;
    for (const clip of clipsOf(holder)) {
      const sides = beyond(box, clip.box);
      if (sides !== null && clipped === null) clipped = { by: nameOf(clip.el), overflow: style(clip.el).overflowX === style(clip.el).overflowY ? style(clip.el).overflowX : `${style(clip.el).overflowX} ${style(clip.el).overflowY}`, sides };
      visible = meet(visible, clip.box);
    }
    if (visible[2] - visible[0] <= 0.5 || visible[3] - visible[1] <= 0.5) { hidden += 1; continue; }
    const main = seen.reduce((a, b) => (b.chars > a.chars ? b : a));
    const colors = [...new Set(seen.filter((r) => r.color !== null).map((r) => hex(r.color)))];
    const behind = backgroundAt(holder, (visible[0] + visible[2]) / 2, (visible[1] + visible[3]) / 2);
    let name = nameOf(holder);
    const count = (names.get(name) || 0) + 1;
    names.set(name, count);
    if (count > 1) name = `${name} (${count})`;
    const opted = holder.closest('[data-vidgen-lint]');
    texts.push({
      name, tag: holder.tagName.toLowerCase(), source: holder instanceof SVGElement ? 'svg' : 'html',
      text: seen.map((r) => r.text).join('').replace(/\s+/g, ' ').trim(),
      box, visible, font_px: main.size, cap_px: main.cap,
      color: main.color === null ? null : hex(main.color), colors,
      opacity: main.opacity * (main.color === null ? 1 : main.color[3]),
      background: behind.color || null, background_unknown: behind.unknown || null,
      clipped, cut: beyond(box, [0, 0, W, H]),
      lint: opted === null ? null : opted.dataset.vidgenLint,
    });
  }

  // ----- what the page declares (text on a canvas) --------------------------------------------
  let declared = [];
  const hooks = window.vidgen || {};
  if (typeof hooks.layout === 'function') {
    const given = await hooks.layout(t, window.__vidgen.ctx);
    if (!Array.isArray(given)) throw new TypeError('window.vidgen.layout(t, ctx) must return an array of {id, text, box: {x, y, width, height}, size, color, background}');
    declared = given.map((item) => {
      const out = { ...item };
      if (item && typeof item === 'object') {
        for (const key of ['color', 'background']) {
          if (typeof item[key] === 'string') { const c = rgba(item[key]); out[key] = c === null ? item[key] : hex(c); out[key + '_alpha'] = c === null ? null : c[3]; }
        }
        if (typeof item.size === 'number') out.cap = item.size * capRatio(`normal 400 100px ${item.font || 'sans-serif'}`);
      }
      return out;
    });
  }
  return { width: W, height: H, texts, declared, hidden, canvases: document.querySelectorAll('canvas').length };
}
