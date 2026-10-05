# vidgen task list — features for AI-authored videos

Legend: `- [ ]` not done · `- [~]` partially done · `- [x]` done

Guiding idea: the AI author cannot watch the video. Prioritise features that let it see its own
output, catch its own mistakes, and build from tested parts instead of raw Manim.

Suggested first three: storyboard + lint, icon library + layout regions, theme presets.

## 1. Let the AI see what it made (feedback loop)

- [ ] `vidgen storyboard`: one still per beat (end of beat, optionally several points through it)
      in a labelled contact-sheet PNG (`s3_b2 @ 4.1s`) with the narration text under each frame
- [ ] `vidgen lint` (layout checks): text off the frame, overlapping objects, text too small for
      the resolution, poor contrast against the background, too many words on screen at once;
      JSON report `{scene, beat, issue, object, bbox}`
- [ ] Timing checks: beats read too fast/slow, dead air (no motion for more than N seconds),
      animations that keep going after the narration ends
- [ ] `--json` output on every command (`validate`, `list-scenes`, `render`)
- [ ] JSON Schema export for `video.yaml` and for each scene type's `Params`
- [ ] Readback check: speech-to-text on the TTS output compared with the beat text (catches
      mispronounced acronyms, numbers, LaTeX-like text)

## 2. Ready-made building blocks (less hand-written Manim)

- [ ] Layout system: named regions and grids (`left/right`, `2x2`, `hero + caption`) and
      `place(obj, region)` with automatic fit-to-region scaling
- [ ] Per-beat animation vocabulary in YAML: `reveal`, `highlight`, `zoom`, `transform`, `dim`

New scene types:

- [ ] `diagram` / `flowchart` (nodes and edges, auto-layout, step-by-step reveal)
- [ ] `timeline`
- [ ] `comparison` / split screen (before vs after)
- [ ] `table` (row and cell highlights)
- [ ] `stat` / big number (counter with context)
- [ ] `process` / pipeline
- [ ] `map`
- [ ] `code_walkthrough` (scroll and highlight lines in sync with beats)
- [ ] `equation_derivation` (step-by-step transforms)
- [ ] `scatter`
- [ ] `pie` / `donut`
- [ ] `histogram`
- [ ] `heatmap`
- [~] `network` / neural-net diagram (building blocks exist: `helpers.column`, `helpers.edges`)
- [ ] `screenshot` with callouts (arrows, boxes, magnifier)
- [ ] `video_clip` (B-roll, screen recordings)
- [ ] `chapter` / section divider

Overlays any scene can use:

- [ ] Lower thirds
- [ ] Progress bar / chapter indicator
- [ ] Logo watermark
- [ ] Burned-in captions styled by the theme, incl. word-by-word karaoke for vertical formats
- [ ] Callout arrows and annotation boxes

## 3. Assets

- [ ] Icon library: bundled open-licensed SVG set (e.g. Lucide/Tabler/Phosphor), usable by name
      (`icon: database`), recolored by the theme
- [~] Theme presets: 6–10 contrast-checked themes (dark tech, light academic, warm editorial,
      high-contrast, brand-neutral) with palettes, font pairings and type scales
      (today: one default theme, overridable per project)
- [ ] Bundled open-licensed fonts (sans, serif, mono) for identical renders on every machine
- [ ] Royalty-free background music beds with automatic ducking under narration
- [ ] Sound-effects set (whoosh, pop, click, tick) triggerable from animations
- [ ] Transitions between scenes: crossfade, push, wipe, match-cut
- [ ] Optional generated images (image-generation API), cached by hash like TTS audio

## 4. Help the AI make good decisions

- [ ] AI author guide (`vidgen guide` or `AGENTS.md`): pacing rules (~2.5 words/s, a visual change
      every 3–6 s), max on-screen text, which scene type when, good vs bad examples
- [ ] `vidgen plan`: script/outline in, draft `video.yaml` (scene types + beats) out
- [~] Gallery of tested scenes: one rendered clip + YAML per scene type and variant
      (today: `examples/minimal` covers every built-in, without rendered clips)
- [ ] Project-level pronunciation dictionary applied before TTS
- [ ] MCP server for vidgen: validate, render, storyboard, lint as agent tools

## 5. Output formats

- [ ] Slides from the same config: HTML/PDF deck, one slide per scene, narration as speaker notes
- [ ] Chapters in MP4 metadata and as a YouTube chapter list
- [ ] Auto-generated thumbnail
- [ ] GIF / short clip export
- [ ] Per-scene voice overrides (multiple speakers / dialogue)
- [~] Multi-language variants reusing the visuals with new narration and subtitles
      (today: variants can change voice and beat texts, with separate `audio/<variant>/`)
