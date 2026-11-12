// A rain gauge filling up, drawn on the canvas of a `script:` scene. frame(t, ctx) draws the
// whole picture from t alone (rain streaks loop, the level follows the narration), so any frame
// can be drawn on its own. The text is drawn on the canvas, which lint cannot read: layout(t, ctx)
// declares it (where, how big, which colours), so lint checks it like the page's own text.
// The rain starts on the word "shower" (ctx.beats' word times) and the "about an inch" line comes
// in on the third beat. ctx.data: {total_mm, scale_mm}.

let drops = [];

export function load(ctx) {
  // Math.random is seeded from the scene id: the same streaks on every render.
  drops = Array.from({length: 90}, () => ({x: Math.random(), y: Math.random(), speed: 0.7 + 0.6 * Math.random(), len: 0.5 + Math.random()}));
}

// The time a word of beat `index` is said (seconds from the scene's start), else the beat's start.
function wordTime(ctx, index, word) {
  const beat = ctx.beats[index];
  if (!beat) return 0;
  const found = beat.words.find((w) => w.text.toLowerCase().replace(/[^a-z]/g, "") === word);
  return found ? found.start : beat.start;
}

const ease = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : 1 - Math.pow(1 - x, 3));

// Where everything goes, for this page size: the gauge and the reading side by side in a wide
// video, the reading under the gauge in a tall one.
function plan(ctx) {
  const {width: w, height: h} = ctx;
  const sizes = ctx.theme.sizes;
  const tall = ctx.orientation === "portrait";
  const gauge = tall
    ? {w: Math.min(w * 0.3, h * 0.17), h: h * 0.46}
    : {w: Math.min(w * 0.16, h * 0.36), h: h * 0.8};
  gauge.x = tall ? (w - gauge.w) / 2 : w * 0.3 - gauge.w / 2;
  gauge.y = tall ? h * 0.04 : (h - gauge.h) / 2;
  // the reading's card is as tall as its three lines (the last one is kept free until it shows)
  const cardW = tall ? w * 0.86 : w * 0.4;
  const big = Math.min(sizes.title * 1.5, cardW / 4.6), small = sizes.caption, mid = sizes.body;
  const pad = big * 0.35;
  const cardH = 2 * pad + big * 1.1 + small * 1.5 + mid * 1.5;
  const card = {w: cardW, h: cardH, x: tall ? w * 0.07 : w * 0.5, y: tall ? gauge.y + gauge.h + h * 0.06 : (h - cardH) / 2};
  const lines = {reading: card.y + pad + big * 0.55, unit: card.y + pad + big * 1.1 + small * 0.75, inch: card.y + pad + big * 1.1 + small * 1.5 + mid * 0.75};
  return {w, h, tall, gauge, card, lines, big, small, mid};
}

function level(t, ctx) {
  const start = wordTime(ctx, 1, "shower");
  const end = ctx.beats[2] ? ctx.beats[2].start + 1.2 : ctx.duration - 0.5;
  return ctx.data.total_mm * ease((t - start) / Math.max(0.5, end - start));
}

function texts(t, ctx, p) {
  const {colors, fonts} = ctx.theme;
  const cx = p.card.x + p.card.w / 2;
  const items = [
    {id: "reading", text: `${level(t, ctx).toFixed(1)} mm`, size: p.big, weight: 700, color: colors.text, y: p.lines.reading},
    {id: "unit", text: "of rain in the gauge", size: p.small, weight: 400, color: colors.dim, y: p.lines.unit},
  ];
  if (ctx.beats[2] && t >= ctx.beats[2].start) {
    items.push({id: "inch", text: "about one inch", size: p.mid, weight: 700, color: colors.highlight, y: p.lines.inch});
  }
  return items.map((item) => ({...item, x: cx, font: `${item.weight} ${item.size}px ${fonts.heading}`}));
}

export function frame(t, ctx) {
  const c = ctx.canvas.getContext("2d");
  const p = plan(ctx);
  const {colors} = ctx.theme;
  c.clearRect(0, 0, p.w, p.h);   // transparent: the video's background shows

  // rain over the gauge (and beside it), fading in at the top
  const rainOn = t >= wordTime(ctx, 1, "shower");
  if (rainOn) {
    c.strokeStyle = colors.primary;
    c.lineCap = "round";
    c.lineWidth = Math.max(1.5, p.h * 0.004);
    const span = p.tall ? p.card.y : p.h;
    for (const d of drops) {
      const y = ((d.y + t * d.speed * 0.9) % 1) * span;
      const x = p.tall ? p.w * (0.08 + 0.84 * d.x) : p.gauge.x - p.gauge.w * 0.9 + d.x * p.gauge.w * 2.6;
      c.globalAlpha = 0.65 * Math.min(1, y / (span * 0.25));
      c.beginPath();
      c.moveTo(x, y);
      c.lineTo(x - p.h * 0.004, y + p.h * 0.03 * d.len);
      c.stroke();
    }
    c.globalAlpha = 1;
  }

  // the gauge: a glass tube with a funnel, a scale every 5 mm, the water at its level
  const g = p.gauge;
  const tube = {x: g.x + g.w * 0.2, y: g.y + g.h * 0.16, w: g.w * 0.6, h: g.h * 0.84};
  const fill = level(t, ctx) / ctx.data.scale_mm;
  const top = tube.y + tube.h * (1 - fill);
  c.fillStyle = colors.surface;
  c.fillRect(tube.x, tube.y, tube.w, tube.h);
  c.fillStyle = colors.primary;
  c.beginPath();
  c.moveTo(tube.x, top);
  for (let i = 0; i <= 16; i++) {   // a small wave on the surface while the rain falls
    const x = tube.x + (tube.w * i) / 16;
    c.lineTo(x, top + (rainOn && fill > 0 ? Math.sin(i * 1.3 + t * 7) * g.h * 0.004 : 0));
  }
  c.lineTo(tube.x + tube.w, tube.y + tube.h);
  c.lineTo(tube.x, tube.y + tube.h);
  c.closePath();
  c.fill();
  const depth = c.createLinearGradient(0, top, 0, tube.y + tube.h);   // deeper water looks darker
  depth.addColorStop(0, "rgba(0, 0, 0, 0)");
  depth.addColorStop(1, "rgba(0, 0, 0, 0.35)");
  c.fillStyle = depth;
  c.fill();
  c.strokeStyle = colors.dim;
  c.lineWidth = Math.max(2, g.w * 0.03);
  c.strokeRect(tube.x, tube.y, tube.w, tube.h);
  c.beginPath();   // the funnel
  c.moveTo(g.x, g.y);
  c.lineTo(tube.x, tube.y);
  c.moveTo(g.x + g.w, g.y);
  c.lineTo(tube.x + tube.w, tube.y);
  c.stroke();
  c.lineWidth = Math.max(1, g.w * 0.015);
  for (let mm = 5; mm < ctx.data.scale_mm; mm += 5) {
    const y = tube.y + tube.h * (1 - mm / ctx.data.scale_mm);
    c.beginPath();
    c.moveTo(tube.x, y);
    c.lineTo(tube.x + tube.w * (mm % 10 === 0 ? 0.35 : 0.2), y);
    c.stroke();
  }

  // the reading, on a card
  c.fillStyle = colors.surface;
  c.beginPath();
  c.roundRect(p.card.x, p.card.y, p.card.w, p.card.h, p.h * 0.03);
  c.fill();
  c.textAlign = "center";
  c.textBaseline = "middle";
  for (const item of texts(t, ctx, p)) {
    c.font = item.font;
    c.fillStyle = item.color;
    c.fillText(item.text, item.x, item.y);
  }
}

// What text the canvas shows at t, for lint: boxes in page pixels, measured with the same font.
export function layout(t, ctx) {
  const p = plan(ctx);
  const c = ctx.canvas.getContext("2d");
  return texts(t, ctx, p).map((item) => {
    c.font = item.font;
    const width = c.measureText(item.text).width;
    return {id: item.id, text: item.text, box: {x: item.x - width / 2, y: item.y - item.size * 0.6, width, height: item.size * 1.2},
            size: item.size, font: item.font, color: item.color, background: ctx.theme.colors.surface};
  });
}
