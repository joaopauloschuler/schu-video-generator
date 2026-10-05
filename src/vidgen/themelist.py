"""``vidgen list-themes``: every theme preset (built-in and project) with its resolved values,
contrast check and palette distinctness, as text, JSON or a swatch sheet PNG (DESIGN.md §20)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from vidgen.config import ThemeConfig
from vidgen.lint.color import ACCENT_TOKENS, TEXT_TOKENS, hex_rgb, palette_distinctness, theme_contrast
from vidgen.scales import AUTO_SCALES, SCALE_TOKENS, TYPE_SCALES
from vidgen.sheets import load_font, wrap_text
from vidgen.theme import Theme

#: Swatch sheet width in pixels and height of one preset's row.
SWATCH_WIDTH = 1280
SWATCH_ROW = 190


def preset_entry(theme: Theme, name: str, selected: str | None) -> dict[str, Any]:
    """What selecting preset ``name`` gives in ``theme``'s project: its resolved values (with the
    project's registered defaults, in the theme's orientation), contrast and distinctness."""
    preset = theme.presets[name]
    resolved = theme.derive(ThemeConfig(preset=name))
    checks = theme_contrast(resolved)
    text_subjects = {f"colors.{t}" for t in TEXT_TOKENS}
    text = [c.ratio for c in checks if c.subject in text_subjects]
    graphic = [c.ratio for c in checks if c.subject not in text_subjects]
    return {
        "name": name,
        "origin": preset.origin,
        "base": preset.base,
        "description": preset.description,
        "selected": name == selected,
        "background": resolved.background,
        "font": resolved.font,
        "fonts": resolved.fonts,
        "code_style": resolved.code_style,
        "scale": resolved.scale_setting,
        "scale_resolved": resolved.scale,
        "colors": resolved.colors,
        "palette": resolved.palette,
        "sizes": resolved.sizes,
        "contrast": {
            "ok": all(c.ok for c in checks),
            "min_text_ratio": round(min(text), 2) if text else None,
            "min_graphic_ratio": round(min(graphic), 2) if graphic else None,
            "failures": [str(c) for c in checks if not c.ok],
        },
        "palette_distinctness": {k: round(v, 1) for k, v in palette_distinctness(resolved.palette).items()},
    }


def list_presets(theme: Theme) -> list[dict[str, Any]]:
    """:func:`preset_entry` for every preset ``theme`` knows (built-in first, then project)."""
    return [preset_entry(theme, name, theme.preset) for name in theme.presets]


def scales_json() -> dict[str, Any]:
    """The type scales and what ``auto`` means per orientation."""
    return {"scales": {name: dict(sizes) for name, sizes in TYPE_SCALES.items()}, "auto": dict(AUTO_SCALES)}


def summary_lines(entries: list[dict[str, Any]], orientation: str) -> list[str]:
    """Human-readable listing of :func:`list_presets` entries and the type scales."""
    width = max(len(e["name"]) for e in entries)
    lines: list[str] = []
    for e in entries:
        scale = e["scale"] if e["scale"] == e["scale_resolved"] else f"{e['scale']} = {e['scale_resolved']} here"
        marker = "  [selected]" if e["selected"] else ""
        lines.append(f"{e['name']:<{width}}  {e['origin']}  scale {scale}{marker}")
        if e["description"]:
            lines.append(f"    {e['description']}")
        c = e["colors"]
        lines.append(
            f"    background {e['background']}  surface {c.get('surface', '-')}  text {c.get('text', '-')}  dim {c.get('dim', '-')}"
        )
        lines.append("    " + "  ".join(f"{t} {c[t]}" for t in ACCENT_TOKENS if t in c))
        lines.append(f"    palette {' '.join(e['palette'])}  code_style {e['code_style']}  font {e['font']}")
        contrast = e["contrast"]
        verdict = "ok" if contrast["ok"] else f"{len(contrast['failures'])} too low"
        worst = min(e["palette_distinctness"].items(), key=lambda kv: kv[1])
        lines.append(
            f"    contrast {verdict} (text >= {contrast['min_text_ratio']}:1, accents >= {contrast['min_graphic_ratio']}:1); "
            f"palette min difference {worst[1]} ({worst[0]})"
        )
        lines.extend(f"      {failure}" for failure in contrast["failures"])
    lines.append("")
    lines.append(f"type scales ({', '.join(SCALE_TOKENS)}); auto = {AUTO_SCALES[orientation]} for this {orientation} video:")  # type: ignore[index]
    for name, sizes in TYPE_SCALES.items():
        lines.append(f"  {name:<9} {' '.join(str(sizes[t]) for t in SCALE_TOKENS)}")
    return lines


def _rgb(color: str) -> tuple[int, int, int]:
    r, g, b = hex_rgb(color)
    return (round(r * 255), round(g * 255), round(b * 255))


def render_swatches(entries: list[dict[str, Any]], path: Path) -> Path:
    """Write a PNG with one row per preset: its background with name and description in its
    text/dim colours, a ``surface`` panel, the accent chips and the palette as bars."""
    image = Image.new("RGB", (SWATCH_WIDTH, SWATCH_ROW * len(entries)), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    name_font, text_font, small_font = load_font(30, bold=True), load_font(20), load_font(16)
    pad = 20
    for row, e in enumerate(entries):
        top = row * SWATCH_ROW
        colors = e["colors"]
        draw.rectangle((0, top, SWATCH_WIDTH, top + SWATCH_ROW - 1), fill=_rgb(e["background"]))
        text, dim = _rgb(colors.get("text", "#888888")), _rgb(colors.get("dim", "#888888"))
        draw.text((pad, top + pad), e["name"], font=name_font, fill=text)
        for i, line in enumerate(wrap_text(text_font, e["description"], 610, 2)):
            draw.text((pad, top + pad + 42 + 24 * i), line, font=text_font, fill=dim)
        label = f"scale {e['scale_resolved']} · code {e['code_style']}"
        draw.text((pad, top + pad + 96), label, font=small_font, fill=dim)
        x = pad
        for token in ACCENT_TOKENS:
            if token in colors:
                draw.rounded_rectangle((x, top + 142, x + 40, top + 168), radius=6, fill=_rgb(colors[token]))
                x += 50
        panel = (660, top + pad, 900, top + SWATCH_ROW - pad)
        draw.rounded_rectangle(panel, radius=10, fill=_rgb(colors.get("surface", e["background"])))
        draw.text((panel[0] + 16, panel[1] + 14), "Aa Heading", font=name_font, fill=text)
        draw.text((panel[0] + 16, panel[1] + 60), "body text", font=text_font, fill=text)
        draw.text((panel[0] + 16, panel[1] + 96), "dim caption", font=small_font, fill=dim)
        bars = e["palette"]
        span = (SWATCH_WIDTH - pad - 930) / max(len(bars), 1)
        for i, color in enumerate(bars):
            height = (SWATCH_ROW - 2 * pad) * (0.45 + 0.55 * (i + 1) / len(bars))
            x0 = 930 + i * span
            draw.rectangle(
                (math.floor(x0 + 4), top + SWATCH_ROW - pad - height, math.floor(x0 + span - 4), top + SWATCH_ROW - pad),
                fill=_rgb(color),
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path
