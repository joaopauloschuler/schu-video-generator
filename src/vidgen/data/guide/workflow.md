<!-- topic: workflow (also: loop, commands, iterate) -->
## The loop: plan, write, look, fix

1. **Plan** (in your head or a scratch file, not in YAML yet): the one-sentence takeaway, the
   audience, the length (60–90 s for social, 2–6 min for an explainer), then a list of scenes,
   each one idea with its scene type (see `vidgen guide scenes`). **Starting from an outline or
   a script?** Write it as Markdown (headings, short paragraphs, lists, tables, code, `$$maths$$`,
   images, quotes, `A -> B -> C` lines) and run `vidgen plan outline.md --json` (`--language
   pt-BR`, `--format 9:16` as needed): it writes a draft project with a scene type per block,
   the prose cut into beats of 6–15 words, compressed on-screen texts, chapters for long videos,
   a `# plan:` comment on every scene (why that type) and `# TODO:`s (what to check). It is a
   draft, not a video: work through every TODO, rewrite the narration for the ear (placeholder
   beats repeat their labels), make on-screen texts keywords, then go on with step 3.
2. **Write `video.yaml`**: narration as beats, content as params. Keep beat `id`s stable once
   audio exists (an edited beat keeps its id; only that beat is re-voiced).
3. **`vidgen validate --json`**: fix every entry of `problems` (`location` is a config path such
   as `scenes[2].params.items`, `message` says what is wrong and usually the fix: did-you-mean
   names, known values). Read `warnings` too (unused pronunciations, missing pictures,
   chapters YouTube would ignore). Repeat until `ok` is true.
4. **`vidgen storyboard`**: renders the preview (timed from word counts until audio exists) and
   writes contact sheets to `build/preview/storyboard/` (`video-1.png`, ...; one per scene in
   `scenes/<id>-1.png`; `--json` lists the paths). **Open the PNGs and look.** Each still is the
   end of a beat, labelled `beat @ time` with its narration underneath. Ask of every still:
   - Is it obvious what to look at? Is the newest element the most prominent?
   - Does the picture match the words under it (and not repeat them)?
   - Is anything cut off, crowded, tiny, or overlapping? Is a frame mostly empty?
   - Does the scene look like its neighbours (same header band, same colours)?
   Use `--scene ID` to look closer and `--per-beat 3` to see animations and actions mid-beat.
5. **`vidgen lint --json`**: every finding has `scene`, `beat`, `rule`, `severity`, `message`
   (with the measured `value` and the `limit`) and `still` (the PNG to open). Fix the cause,
   not the symptom (see `vidgen guide troubleshooting`); use a scene's `lint_ignore` only for a
   finding you mean to have, with a YAML comment saying why. `ok: false` means a finding at or
   above `fail_on` (default `error`); aim for zero findings.
6. **Fix and repeat** 3–5 until the storyboard reads well and lint is clean. Re-runs are cheap:
   only changed scenes are rendered again. Check every variant you ship
   (`vidgen lint --variant vertical`).
7. **`vidgen tts --dry-run`**: what would be sent to the voice service, per beat, with the
   pronunciation applied (`says: ...`) and the character count (what is billed). Read it:
   numbers, acronyms and names are where voices go wrong.
8. **`vidgen tts`**: voices only new or changed beats (needs `ELEVENLABS_API_KEY`; costs money).
9. **`vidgen render`** (`--preview` first): now timed by the real audio. Beats change length,
   so run `vidgen storyboard` and `vidgen lint` again: `narration_speed` and `dead_air` now
   measure the real speech. `vidgen render --draft` is faster still (240p at about 8 fps, at the
   video's shape, in its own `build/draft`): `<output>_draft.mp4`, to watch the timing and staging
   before a preview. It pays most for a cartoon (no idle motion, wind, shadows, particles or light
   grade; every timing, position, action and the lip sync kept) and for a video with `web` scenes
   (the page is drawn that small: 2 to 3 times faster than a preview, `vidgen guide web`).
   `vidgen animatic` is quicker still once the storyboard's stills are current (seconds, no
   rendering): `<output>_animatic.mp4`, those stills held in time with the narration, with the
   audio and the subtitles, to check the pacing.
10. **`vidgen readback`**: speech-to-text of the MP3s against
    your texts; it names misheard terms and suggests a pronunciation entry, and lists the
    **words to check**: heard with low confidence or after an odd pause inside a sentence, with
    their time in the beat and in the video. Fix, `vidgen tts`, and `vidgen lint` again (its
    `readback` rule reads the cached transcripts; `vidgen lint --readback` also reports the words
    to check, rule `unclear_speech`).
11. **Final**: `vidgen render` (the full-size `format`, 1920x1080 by default) and a last
    `vidgen lint --final`.

```text
vidgen validate --json
vidgen storyboard --json          # then open the PNGs it lists
vidgen lint --json
vidgen tts --dry-run
vidgen tts
vidgen render --preview
vidgen lint --fail-on warning
vidgen render
```

**Costs.** `vidgen tts` (ElevenLabs or OpenRouter, per character; `voice.provider: kokoro` is local and
free), `vidgen imagegen` (OpenAI Images or OpenRouter, per picture) and `vidgen readback` with
`stt: {provider: elevenlabs}` cost money; everything else is local and free. Always run `vidgen tts --dry-run` / `vidgen imagegen --dry-run` first, finish the
layout on the word-count-timed preview, and commit `audio/` and `assets/generated/` (they cannot
be made again identically). Renders are slow but free: `storyboard`, `lint` and `render` re-render
only the scenes that changed (`render` reuses the storyboard's renders of the same format;
`--force` renders everything, e.g. after editing a file outside `assets/`); `--jobs N` renders
several at once, and `--jobs auto` picks N from the available memory (1.5 GB per job) and the CPU
cores and prints why; never run two vidgen commands at once, and run Kokoro `tts` alone; preview
while iterating. Under a time limit per command, `render --max-scenes N` renders N scenes and
stops (not joined while more are left); run it again until it joins — finished scenes are kept,
also when a run is interrupted.

**JSON everywhere.** Every command but `mcp` takes `--json` (`validate`, `list-scenes`,
`schema`, `storyboard`, `lint`, `render`, `tts`, `imagegen`, `plan`, `init`, ...): one document on
stdout, `{version, ok, warnings, ..., error?}`, exit code 0 exactly when `ok`. `vidgen tts
--dry-run --json` lists every beat to voice with its characters; `vidgen imagegen --dry-run
--json` every picture with its prompt and estimated cost.

**Through MCP.** When your client has the vidgen MCP server (`vidgen mcp --root DIR`), the same
commands are tools with the same JSON documents: `guide`, `plan`, `init`, `validate`, `schema`,
`list_scenes`, `list_icons`, `list_themes`, `list_sfx`, `list_music`, `music_preview`, `music_template`, `music_patches`, `music_render`, `music_check`, `audio_check`,
`storyboard`, `lint`, `render`, `tts`, `imagegen`, `readback`, `slides`, `thumbnail`, `export`, `gallery`,
`translate_template`, `character_sheet`, `direct`, `screenplay`, `cast`, `animatic`, and `studio_sessions`, `studio_read`,
`studio_check`, `studio_variations`, `studio_propose` for music a person hands you from `vidgen studio`, and
`generate_plan`, `generate_run`, `generate_status`, `generate_takes`, `generate_pick`, `generate_host_test` for generated video shots (options in snake_case: `per_beat`,
`fail_on`). Paths are
relative to the server's root folder. `storyboard` returns the contact sheets as images (look at
them; page with `image_offset`), `thumbnail`, `gallery`, `character_sheet` and `generate_takes` their pictures. `render` previews by default. `tts`,
`imagegen` and `generate_run` are dry runs unless you pass `dry_run: false` and `confirm_cost: true`: run the dry
run, tell the user what it will cost, and confirm only after they agree.

