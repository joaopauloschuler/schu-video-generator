# Handoff log

Each implementation step appends a section here. Read all previous sections before starting.

## Step 0 — Design spec
- Added `DESIGN.md` (architecture and contracts), `CLAUDE.md` (conventions), this file, and
  `.gitattributes`.
- Plan of steps:
  1. Foundation: package, CLI skeleton, config models, project loading, theme, errors, tests.
  2. Extension system + scene base: runtime context, registry, extension discovery, hooks,
     `NarratedScene`/`narrate()`, helpers, `vidgen.api`, `list-scenes`/`validate`.
  3. ElevenLabs TTS with caching (`vidgen tts`).
  4. Render pipeline: worker subprocess, padding, concat, preview, `--scene`, variants, timings, SRT.
  5. Built-in scene library.
  6. Migrate kphi3 to `examples/kphi3` (custom scenes as extensions) + regression comparison.
  7. Independent review, docs, fixes.
