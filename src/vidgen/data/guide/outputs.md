<!-- topic: outputs (also: slides, export, gif, thumbnail, chapters, translations, translate, languages, licence, license, rights) -->
## Outputs: video, chapters, thumbnail, slides, GIFs, translations

- **Video and subtitles**: `vidgen render` writes `output/<output>.mp4` and `<output>.srt`
  (`--preview`: `<output>_preview.mp4`; `--draft`: `<output>_draft.mp4`; `--variant NAME`: `<output>_<variant>.mp4`). The
  chapter list and thumbnail go to `output/` too; `output_dir:` (relative to the project folder)
  or `--output-dir DIR` moves them. `build/` and `exports/` stay put.
- **Chapters**: with `chapter` cards or `chapter:` keys the MP4 gets chapter marks and
  `<output>_chapters.txt` the YouTube list (`0:00 Intro`...); `vidgen validate` warns when
  YouTube would ignore it (fewer than 3 chapters, one under 10 s). `metadata:` adds tags. The
  scenes' `references:` and `figure_credit:` are appended to that file as a numbered list.
- **Thumbnail**: a designed card reads best small. Keep its title ≤ 6 words. `vidgen render`
  writes it with the video, `vidgen thumbnail` alone; open the small copy it names
  (`build/.../thumbnail/<name>_small.png`, YouTube's 320 px) and fix the checks it prints. A
  frame of a scene works too: `vidgen thumbnail --scene results --beat 2`.
- **Audio only** (audiobooks, podcasts, the sound of a video): `vidgen render --audio-only`
  writes `output/<output>.wav` without rendering a scene (voices, music ducked under them,
  effects, stings, loudness). `audio_only: true` makes it the project's render; such a project
  may list `sections:` (`{id, title, voice, room, music, sfx, ambience, beats}`, `- pause: 2`
  between them) instead of scenes, and `vidgen story draft --audio` drafts one from a story. Lines are timed
  by their speech plus `pacing:` gaps (`speaker`, `scene`, `chapter`, `lead_in`, `tail`); a
  beat's `pause: 1.5` (or a `- pause: 1.5` item) is the silence after it, in videos too.
  `pacing: {timing: video}` keeps the video's timeline instead. Stage foley and ambience are
  left out (a warning says so) unless `audio: {scene_sounds: true}` (stage walks, doors, knocks,
  switches, set beds, a video_clip's sound; not levels, iso moves, vehicles, phones). The file:
  `audio_output: {format: mp3 | m4a | ogg | wav, bitrate, channels: mono, sample_rate,
  loudness: podcast | audiobook | broadcast | drama | custom}`; the render measures it against the
  preset and says PASS / FAIL (fix what it names: an `audiobook` wants 0.5-1 s of silence before
  the first sound, so no effect in the first half second). It also writes the transcript
  (`_transcript.txt` with speakers and chapters), `.srt`, `.vtt` and `_chapters.txt`.
  `vidgen audio check FILE` (MCP `audio_check`; `render` takes `audio_only`) measures any audio
  file. Settings: `docs/COOKBOOK-AUDIO.md`.
- **Stereo and rooms** (opt-in, videos too): `pan: left` (-1..1, `far_left`...`far_right`) on a
  voice of `voices:` or on a beat (`pan: {from: right, to: left}` moves it across the line);
  `audio: {follow_stage: true}` pans stage voices to where their characters stand; `room:
  small_office | corridor | hall | outdoors | car | phone | none` on a scene or section (or
  `audio.room` for all), the narrator dry unless `{use: hall, narrator: true}`;
  `audio.music_width: 0.7` narrows the music. The render prints a `mono:` check; keep
  `music_width` at 1 or less if it fails.
- **Sound design** (audio dramas; opt-in, videos too): `ambience: rain` (or a list, or `{beds:
  {room_tone: 4, rain: -14}, gain, width}`) on a scene or section plays beds under it that
  cross-fade at the change (`audio.ambience_crossfade: 3`); beds: rain, fire, birdsong, city,
  room_tone, crickets, hum, alarm. A beat's `ambience: {stop: rain, at: "@stopped", fade: 2.5}`
  (or `start:`) changes them on a word. Cues on words: `actions: [{sfx: step_wood, at:
  "@crossed", repeat: 7, every: 0.48, pan: {from: far_left, to: far_right}}]`; `room: phone` (or
  `true`, or `audio.sfx_room: true` for all) puts a cue in a room like a voice.
- **Music for dramas** (opt-in, videos too): `score: {themes: {main: love, tension: {source:
  enigma, volume: -1}}, crossfade: 4, duck: drama}` names themes (a bed, a project piece
  `assets/music/love.yaml`, a file); a scene's or section's `music: tension` plays one from there
  on, cross-fading at the change (the same theme plays on; `music: false` stops it); a pause
  swells under it (`duck: drama`: 18 dB under lines, 3 dB up in pauses; presets `light`,
  `standard`, `drama`, `deep`, on `music:` cues too). Variations: `{theme: love, variation:
  {section: b, transpose: 2, tempo: 60, tracks: [melody]}}`. A beat's `motif: {theme: love, at:
  "@remember", length: 7}` plays a theme briefly over the scene's (which dips); `sting: {kind:
  reveal, at: "@ticket"}` on a word. The render warns when music is under 15 LU below dense
  dialogue (`mix.music_check`).
- **Delivering a drama** (opt-in): `audio_output: {loudness: drama}` is podcast loudness plus
  checks: loudness range ≤ 10 LU, lines and voices even (6 / 4 LU), music ≥ 15 LU under them
  (`vidgen audio check PROJECT`; a quiet line or voice it names: raise its `emotion` gain or
  re-voice it). `split: chapters` writes one file per chapter (`_01_<title>`, each at the
  loudness, an `.m3u`, per-file transcripts). `credits: {speak: true}` adds closing credits from
  the cast ("Starring Bella as Mara ..."; `voiced_by: {mara: Ana}`, `lines`); `cold_open:
  [beat ids]` (or a section id) plays those lines first, before the title. Run `vidgen tts` after
  adding them (new beats; cold-open copies take the originals' audio). Craft notes:
  `docs/COOKBOOK-AUDIODRAMA.md`.

```yaml
thumbnail: {title: "77% of the model is dead weight", icon: brain-circuit, jpeg: true}
scenes:
  - id: intro
    type: title
    params: {title: "Pruning large models"}
    beats: [{text: "Most of a large model can go."}]
```

- **Slides**: `vidgen slides --final` writes a self-contained HTML deck to `exports/` (a slide
  per beat, the narration as speaker notes; `--audio` for a narrated deck); `--format pdf
  --notes` a PDF with notes pages. A video built with one reveal per beat
  is a good deck for free; check `--mode scene` for a compact one.
- **GIFs and clips**: `vidgen export gif --scene ID --max-mb 5` (a palette GIF within a size
  budget, for READMEs and chats), `vidgen export clip --scene ID --with-audio` (an MP4 part).
  Render the video first.
- **Translations**: add a variant with `language: pt-BR` and `translations:`, run
  `vidgen translate-template --variant pt`, fill in every `text:` of the file (keep it short:
  translations run longer), `vidgen validate` (lists what is still untranslated),
  `vidgen tts --variant pt` (voices only translated beats), then storyboard and lint the
  variant: longer text can overflow where the source fit.
- **Dubbing a cartoon**: the same variant. With Kokoro every speaker gets a voice of the
  language of the same kind automatically (`vidgen validate` prints `dub [pt]: ...` and warns
  when two speakers end up with one voice); name one with `dub: {pt: pm_alex}` on that voice in
  `voices:` (or on `voice:` for the narrator). Then `vidgen tts --all-languages`, `vidgen lint
  --all-languages` (timings, overlaps and text are checked in each language) and `vidgen render
  --preview --all-languages`. Example: `examples/cartoon-music-box` (variant `pt`).

```yaml
variants:
  pt:
    language: pt-BR
    translations: translations/pt.yaml
scenes:
  - id: intro
    type: title
    params: {title: "Hello"}
    beats: [{text: "Hello and welcome."}]
```

- **Generated pictures** (`image` `generate:`): `vidgen imagegen --dry-run` shows prompts and
  cost; placeholders render until you run `vidgen imagegen`. Describe a scene, never text,
  charts or logos (schu-video-generator draws those better), and set one `imagegen: {style: ...}` for the
  whole video.
- **Cartoon backgrounds** (`stage` `generate:`): see "The set" in `vidgen guide cartoons`.
- **Choosing an image provider**: `openai` (the default; `OPENAI_API_KEY`, gpt-image-1) is one
  good model at a known price. `imagegen: {provider: openrouter, model: author/name}`
  (`OPENROUTER_API_KEY`) reaches many models with one key — some cheaper per picture
  (e.g. `bytedance-seed/seedream-4.5` at ~$0.04, `black-forest-labs/flux.2-klein-4b` by the
  megapixel), some better at a style. Read the prices in `vidgen imagegen --dry-run` (its
  `price:` line says the basis; "price unknown" for models billed per token) and fix every
  `problem:` / `note:` it prints before a real run. Keep one provider and model per video so the
  pictures match; changing them makes every picture "missing" (new pictures, new cost). If the
  account requires Zero Data Retention, choose a model with a ZDR endpoint (e.g.
  `bytedance-seed/seedream-5-0-flash`); schu-video-generator's error lists them when a model is refused.
- **Vector (SVG) pictures** (`generate: {prompt, format: svg}` with `imagegen.svg_model`, e.g.
  `recraft/recraft-v4.1-vector`, ~$0.08; or an `.svg` file as `path`): drawn as shapes, so
  `draw: true` traces then fills them and `recolor: theme` paints them in the theme's colours.
  Worth it for flat illustrations, icons and diagram-like art (few flat colours; ask for
  "flat illustration, simple shapes, few colours"); not for photos or soft lighting (thousands
  of shapes, capped and thinned: worse than a PNG). Text in an SVG is removed — keep words in
  schu-video-generator's captions. No SVG model has a ZDR endpoint (2026-10-08).
- **Generated video shots** (a beat's `generated_shot: {kind: talking | action | establishing,
  model, prompt, setting, ...}`; `docs/COOKBOOK-3D-SCENE-TO-SEEDANCE.md`; `docs/COOKBOOK-DIRECTING-YOUR-AI.md` has the workflow as instructions a person gives an AI): a video model on OpenRouter
  makes the beat's picture; schu-video-generator keeps the timing, voices, captions, overlays and
  music (by default the model's own sound is not used; see **A model's own sound** below). Expensive (about $0.03-0.60 per second), so: a few
  shots that need real footage, the lowest resolution, 4-5 s. The order: `vidgen generate plan`
  (free) → `generate sheets --pay` → look, `approved: true` (or cut one sheet picture into named
  panels with `vidgen split-sheet`) → `vidgen tts` → `generate frames --pay` (a shot's `paint_first_frame:`,
  a starting picture from its 3D first frame and references; look at it before paying for a clip) →
  `generate inputs --guide` → `generate plan` (nothing blocked; tell the user the total) → `generate run --pay`
  (needs `videogen.budget_usd`; stops at the first failure, never retries, never pays twice) →
  `generate takes` (look at every contact sheet and QA finding) → `generate pick --shot ID
  --take N` → `vidgen render`. A take with QA errors (black, frozen) is not shown unless picked;
  `--take none` keeps vidgen's own picture. A new take needs a changed request (another `seed`).
  After any edit to the scene, the line or its MP3, `generate plan` blocks the shot ("inputs changed
  since they were cut") and `run --pay` refuses: run the command the plan names (`generate inputs`,
  free; `vidgen tts` first when the plan says so).
  Takes are paid footage: commit `takes/`. When the film shows takes, the description file says
  "Includes AI-generated footage (models)" and lint's `generated_footage` reminds you to mark the
  upload as altered or synthetic content. Video generation is not eligible for Zero Data
  Retention: send no private faces or material you may not share.
- **A model's own sound** (`generated_shot.sound: model`, or `videogen.models: {"author/name":
  {sound: model}}`, or `videogen.sound`; default `mix`): the job is sent with `generate_audio: true`
  and the clip keeps the model's sound. Different models can behave differently, so choose per
  model; the setting is part of the request, so changing it is a new paid clip. A model the list
  says cannot make sound is blocked; one it says nothing about gets a note and may come back silent.
  Bytedance Seedance 2.0 mini, given the beat's voice as a reference, made a sound the owner
  judged to be the same voice and matching the lips, but it is a new performance, up to about 0.9 s
  late against the voice file, so never lay the voice file over such a clip. A placed take always
  plays vidgen's mix. To hear the clip's sound, use `place: false` and put the take
  (`takes/<shot>/<n>.mp4`) in a `video_clip` scene: `{type: video_clip, params: {path:
  takes/<shot>/<n>.mp4, region: bleed}, beats: [], duration: <the clip's length>}` plays it at
  volume 1 (a `video_clip` with narration plays it at 0.25; `volume:` sets it). The limit: vidgen
  does not time captions or word-anchored actions from a clip's sound.
- **Painted starting pictures** (`generated_shot.paint_first_frame: {prompt, refs, seed, model,
  resolution}`, `vidgen generate frames [--pay] [--shot ID]`, dry run by default): `bytedance-seed/seedream-4.5`
  ($0.04 flat, `input_references`) paints from the beat's first frame (the layout, whose composition, camera and positions
  it must keep) and the reference pictures, into `assets/frames/<shot>_<key>.png`, inside `videogen.budget_usd`, never
  paid twice. A shot uses it with `first_frame: painted` (blocked until it exists). Leave `name:` off the stand-ins, or the name tags can become text in the picture.
  `vidgen split-sheet PICTURE --columns N [--rows N] [--gap PX] | --box X,Y,W,H ... --names a,b --scale 3 --out DIR` cuts one sheet into named panels.
  A file reference can say what it shows (`refs: [{file: path, shows: morag}]`); the role sentence names it in real order.
  `generate inputs --guide` also writes `overlay.last.png` (the starting picture over the guide's last frame, with whatever moved or appeared since the guide's first frame at full strength inside a magenta outline) so an object appearing later can be found and checked; both overlays are enlarged to 1600 pixels on the longer side.
  A film of picked takes with hard cuts: `place: false` on the shots, one `video_clip` per take (`path: takes/<shot>/<n>.mp4`, `fade: false`, `region: bleed`, no beats, `duration:` the take's length) in a separate `film.yaml` with its own `output:` name, then `vidgen render film.yaml --preview` (the description file and lint then carry the AI-generated disclosure). A beat lasts its voice plus `pause:` (or `narration.pad` without one), and the rendered scene about 0.5 s more, so the plan's shot window is shorter than the scene. An action shot sends no voice unless `audio: beat`; `vidgen generate plan` notes a shot with a line, `sound: model` and no voice input.
- **Voice and guide inputs** (talking shots, `audio:`, `guide:`): OpenRouter takes sound and
  video only as https URLs, so these shots stay blocked until the user opts in with
  `videogen: {host: quick_tunnel}` (default `none`). Then each paid shot shares only its own
  `audio.mp3` / `guide.mp4` (copies, random names, a secret path) through its own Cloudflare
  quick tunnel while its job runs, at most `host_max_minutes` (20), and closes it when the job
  ends, not when a file was fetched. Needs `cloudflared` (Windows `winget install Cloudflare.cloudflared`). Check it free
  first with `vidgen generate host-test`; `generate plan` lists exactly which files a run would
  share. Ask the user before turning the host on: the files are reachable on the public
  internet by anyone with the address for those minutes.
- **Your own GPU (ComfyUI, no money)**: `videogen: {provider: comfyui, comfyui: {colab: <session>}}`
  (a Colab session set up with `tools/colab/setup_session.py <session>`; always name it) or
  `{url: http://host:8188}` (any ComfyUI server), and `generated_shot.model: ltx-2.3-union-control`
  (LTX-2.3 + IC-LoRA union control: restyles the shot's `guide: canny`, `final` or `depth` video, optionally
  from its `first_frame:`; no references, 512p, 1-5 s parts, seed 42 unless `seed:`). vidgen fits the inputs (960x512 for
  16:9, 8k+1 frames at 24 fps), runs the job and keeps the clip as a normal take, with its GPU seconds and
  compute units (`videogen.comfyui.units_per_hour`, 1.94 for an L4, 11.2 for a G4) in the take's record. `generate run --pay` runs it
  ($0: no budget needed); an L4 job takes about 2-4 minutes of GPU. With `colab:` the job runs on that VM from this computer;
  vidgen run on that VM (`vidgen remote <session> ARGS`) uses its ComfyUI directly.
  The recommended shot and the commands: "Real footage from a web scene" below.
  `glint` removes edges in bright areas (a sun glint a model draws as foam); `false` keeps them.
- **Where the starting picture goes** (`first_frame_in: frame | guide`: `generated_shot`, then
  `videogen.models.<model>`, then `videogen`, default `frame`; `videogen.first_frame_dissolve`, default
  0.4 s): `guide` puts the shot's `first_frame:` picture into the guide video
  (`guide[.<pass>].opening.mp4`, made by `vidgen generate inputs --guide`, as long as the plain guide,
  the picture dissolving into the guide) and sends no first frame; the shot needs a `guide:` and a
  starting picture. Seedance (`bytedance/seedance-*`) takes a first frame or references, never both:
  a request with both silently loses the references (nothing downloaded, the no-reference price),
  so `generate plan` / `run` block such a shot (a shot already paid for gets a note), naming
  `first_frame_in: guide`; `videogen.models.<model>.first_frame_with_references: true` overrides it, and
  models vidgen has no evidence about are not blocked. With `first_frame_in: guide` on a model with a
  template (Seedance) the prompt starts with a role sentence (`@video1` opens on the starting
  picture, `@image1` and so on are who, `@audio1` is whose voice), built from the actual order of the
  inputs; shots with `first_frame_in: frame` keep their prompt exactly. Measured on seedance-2.0-mini: the
  opening is close to the picture (`opening match` 0.83-0.85), not exact, and the model sets its own speech timing.
  `first_frame: last_of:<shot id>` starts a shot from the last frame of the take that shot shows (either mode; `vidgen generate inputs` cuts
  `build/videogen/<shot>/last_of.<source>.<take>.png`): pick the take first, since another pick makes the next shot stale. A source with no take
  blocks the shot and a run never pays for both in one pass: pay, look at the clip, then the next. QA gives each take with a starting
  picture an `opening match` (SSIM of its first frame against the picture, in its record and on its contact sheet, a warning under 0.7, a rough guide).
  `vidgen generate inputs --guide` writes `build/videogen/<shot>/overlay.png` (the picture blended over the plain guide's first frame): open it to check the
  3D figures fit before paying. For takes that join with a plain cut, set `fade: false` on the `video_clip` scenes (no fade in, no 0.5 s fade-out). Where a take was made from the last frame of the take before (`first_frame: last_of:<shot>`), also set `match_previous: true` on its scene: the model draws that frame about 8 % darker, and this gives the clip's first frame the previous clip's brightness and colour, then eases back to the clip's own pixels within 1 s (`{seconds: 0.5}` changes the time; `{hold: true}` keeps the correction, which then adds up along a chain). Only when the user asks for it, or still sees a jump at the cut, add a dissolve: `match_previous: {dissolve: 3}` also blends the clip's first 3 frames (frames of the render being made, 12 at most) with the previous clip's last frame, 75 %, 50 % and 25 % of it, without adding frames or changing durations or sound; `{dissolve: 3, level: false}` blends without the brightness correction. `match_previous: true` never blends. Both scenes need `fade: false`, `region: bleed` and a cut between them; a pair that is not a continuation is left alone with a warning.
  After a hosted job vidgen compares what the provider `GET` from the tunnel with what it hosted and
  warns in the run output and the take's record; the warning is never an error.
- **A submit with no known outcome** (`vidgen generate plan` / `run` / `status` / `ledger` say
  "no known outcome"; vidgen was stopped or an answer was lost after a paid request was sent):
  it may have been charged, so vidgen will not pay for that shot again by itself and counts it
  at its estimate. Tell the user; do not guess. They check their OpenRouter activity, then
  `vidgen generate resolve --intent ID --not-charged | --job JOB_ID | --charged [--cost USD]`.
- **A 3D scene as the guide** (`guide: depth | outline | mask`, only on a `3d` scene; `guide:
  true` = `render`, the normal view): the clip follows the 3D layout and camera, the model draws
  the look. `depth` suits most shots; `mask` keeps objects apart (the prompt lists the
  stand-ins' colours); `outline` for edge guides. The first frame (`first_frame: render`) stays
  the normal view. It is a video input, so it needs the quick tunnel too. Models may ignore
  guides: try one cheap shot first. With any guide (also `guide: true`) the prompt leaves the
  framing to it: a talking shot says "Ana, speaking" instead of "Talking close-up of Ana, facing
  the camera, speaking", and framing instructions in the sheet text are left out of the prompt
  (the plan's `note:` quotes them; a clause that also describes clothes or hair stays whole). The sheet
  pictures are unchanged. A guided shot paid for under the earlier wording is blocked, not paid
  again; `seed:` or `prompt:` on the shot asks for a new take with the new wording.
- **The finished render as the guide** (`guide: final`, any scene type): the beat's finished
  render (full size, the scene's own look, no overlays or placed takes) for the model to remake as
  real camera footage, keeping its layout, motion and timing; `audio: mix` adds the film's own sound
  over the shot (voice and music) as the audio reference. `vidgen render` first, then `vidgen generate
  inputs --guide`. Not yet tried with a real model: make one cheap clip and look at it before more.
  OpenRouter refuses a Seedance job with a reference video (HTTP 402) when the account's credits are
  under its own worst-case cost, even when vidgen's estimate is far lower: $3.57 was not enough for a
  $0.38 clip.
- **A web scene's depth as the guide** (`guide: depth` on a `space` scene, or a `web` scene drawn
  through `vidgen/three-finish`): the scene's exact depth from three.js, drawn with the finished
  render (same size, frames and camera), grey as 1 / distance: near white, far dark, sky black, one
  range for the shot, no film effects. For depth-control video models (an IC-LoRA's depth control).
  An orbital scene in depth slices (`vidgen/space-scale`'s default) is not drawn right yet.
  A page that draws its picture another way (its own `EffectComposer`) draws just the depth frames
  through one: in `frame(t, ctx)`, `if (ctx.draw_mode === "depth") { (depth ??= new Finish(renderer,
  scene, camera, ctx)).render(t); return; }` (`import {Finish} from "vidgen/three-finish"`).
- **Which guide on `ltx-2.3-union-control`** (`guide: canny | final | depth`, each with or without a
  sheet, at 12 or 24 fps): change the line, `generate plan` shows the shot's new `guide:` input as not
  made yet (only that shot), `generate inputs --guide --shot ID` cuts it from the same render. One test
  (an 8 s escapement shot with a sheet, one seed): `final` (the colour render) kept the parts and the
  lighting best and moved with the camera from frame 0, but kept some of the render's look (its flash,
  its regular patterns); `depth` invented surfaces where the render had texture; `canny` invented the
  most and held the camera still for up to 2 s at the start.
- **An open model instead of Seedance**: LTX-2.3 in ComfyUI on a Colab L4,
  docs/COOKBOOK-3D-SCENE-TO-LTX-ON-COLAB.md in the repository (scripts in `tools/colab/`;
  `python tools/colab/setup_session.py <name>` creates or reuses the session and sets it up). Its rule,
  measured once on one 4 s shot (stills only): give LTX a starting picture and a stylesheet and **no
  guide**; a depth guide sets the place and overrides both (the picture is dropped after frame 0). That
  job is built by hand with `tools/colab/build_noguide_workflow.py` (vidgen's `ltx-2.3-union-control`
  requires a guide); make 2-3 takes with different seeds and pick from stills. A blockout `type: 3d`
  scene as `guide: depth` stays the way to fix the layout and camera exactly. Ask the user before
  starting a Colab GPU; reuse a running session between experiments; stop it when the user says so.

### Real footage from a web scene

A `space` or `web` scene rendered, then remade as real camera footage by LTX-2.3 on your own GPU
(a Colab session, next section). Add to the beat:

```yaml
videogen: {provider: comfyui, comfyui: {colab: ltx}}
scenes:
  - id: chase
    type: text_card            # your space or web scene
    params: {text: "Glider"}
    beats:
      - text: "Low over the open sea, the glider leans into a gentle turn."
        generated_shot:
          kind: establishing
          model: ltx-2.3-union-control
          prompt: "a grey glider flies low over a rough open sea; real 35 mm aerial footage"
          guide: canny           # edges of the finished render; canny: {low: 92, high: 200, glint: 150}
          first_frame: restyled  # the render's first frame made photoreal (Qwen-Image-Edit-2511)
          place: true            # the picked takes replace the beat in the film
          # first_frame_prompt: "..."   # replaces the default edit instruction
```

```
vidgen remote ltx render                                      # the finished render (the guide's source)
vidgen remote ltx generate inputs --guide --shot chase_b1_p1  # canny guide + restyled frame; look at them
vidgen remote ltx generate run --pay --shot chase_b1_p1       # $0, about 2-4 min of L4 GPU
vidgen generate pick --shot chase_b1_p1 --take N              # after looking at the take
vidgen remote ltx generate inputs --guide --shot chase_b1_p2  # its first frame: p1's last
vidgen remote ltx generate run --pay --shot chase_b1_p2
vidgen generate pick --shot chase_b1_p2 --take N
vidgen remote ltx render                                      # the film with the takes
```

A beat longer than 5 s is split into parts (`<beat>_p1`, `_p2`...): part 1 starts from
`first_frame:`, every later part from the last frame of the part before it, so make them in order.
At the cut between two placed parts the later one is colour-matched to the earlier one's last frame.

### Use a Colab session: render on a GPU VM

Heavy commands (`render`, `storyboard`, `tts`, `generate`) can run on a Google Colab VM while you
work here, over SSH (the key `~/.ssh/colab_ed25519`; setup creates it when missing). Ask the user
before starting a Colab GPU (it bills by the hour). Every command names its session; nothing falls
back to Colab, and nothing here stops a session.

```
python tools/colab/setup_session.py NAME        # from vidgen's source folder: create or reuse NAME, install ComfyUI + vidgen
python tools/colab/setup_session.py NAME --vidgen-only   # after code changes: reinstall just vidgen
cd my-project
vidgen remote NAME render                          # sync up, render there, bring back the MP4
vidgen remote NAME generate inputs --guide         # guides and restyled frames on the VM's GPU
vidgen remote NAME generate run --pay --shot ID    # the clip on the VM's ComfyUI; the take comes back
colab stop -s NAME                                 # only when the user says so
```

- For no GPU work (renders, ffmpeg), a CPU high-RAM session: `setup_session.py NAME --gpu CPU --high-mem --vidgen-only`.
- `setup_session.py NAME --no-comfy-compiler` starts ComfyUI with its model compiler off (the node LTX Multi
  IC-LoRA stalls with it on); run again without it to switch back. A running ComfyUI with the other setting is
  restarted (a job running on it is lost).
- The comfyui provider with `comfyui: {colab: NAME}` runs `vidgen generate run --pay` here and the job on that VM.
- Synced to `/content/projects/<folder name>/` on the VM with rsync: files deleted here are deleted
  there; `build/`, `output/`, `exports/`, `media/` are never sent (`--exclude DIR` before NAME
  leaves out more).
- Brought back: the files the command's JSON document names, the files the run made or changed
  (takes, picks, ledgers), and `build/` without the render caches (scenes, frames, media, web clips,
  audio). So inputs made on the VM (`generate inputs --guide`) count here too.
- Without a local `rsync` (Windows) it syncs with tar: nothing is deleted there and `build/` stays
  there, so make a shot's inputs and its clip on the same machine.
- After vidgen's code changes, `vidgen remote` stops and prints the `--vidgen-only` setup command.
- On a GPU session, `3d` and `web` scenes draw WebGL on the GPU (`VIDGEN_WEBGL=gpu`, set by the setup); the pixels differ slightly from a local render, so they are their own build: a scene rendered with one backend is drawn again with the other (its render records which). `VIDGEN_WEBGL=swiftshader vidgen remote NAME ...` runs that command with software WebGL on the VM.
- Several sessions can run at once, each under its own name; run one `vidgen remote` at a time per project.

### Stylesheets: one look for a subject across shots

LTX-2.3 (`ltx-2.3-union-control`) can follow the canny guide and a stylesheet picture in one run:
the guide gives shapes and motion, the sheet the look (panels of the subject from a few sides and the
place). Without a sheet each shot invents its own subject; `generate plan` warns about such shots.
The sheets are made by an image model and approved before any video work:

1. `subjects:` in `video.yaml`: each subject or location once, with its `look` and its views; a shot
   names them in `subjects:`. Write each view as a `prompt:`: the picture in words. The image model
   invents the look from the words alone (no picture of yours goes in), and the panel then guides the
   video model. Describe the whole picture, light and style ("cinematic film still, dramatic low
   sunlight, deep space").
2. `vidgen remote NAME generate subjects`: Z-Image-Turbo draws each `prompt:` view
   (`sheets/<subject>/<view>.png`, 1440x768, a `.json` record beside it), all in one batch on the
   session's ComfyUI, then unloads the model. On an L4: about 25 s a panel, plus about 70 s for the
   first (loading the model). Only panels whose prompt, look, text or seed changed are made again
   (`--force --subject NAME`: all of that subject); for another picture from the same words, change
   the subject's `seed:`.
3. Look at each `sheets/<subject>/contact.png` (the panels with their view names).
4. `vidgen generate subjects --approve NAME` (or `--approve-all`; `--view VIEW` for one panel;
   `--reject NAME` takes it back). A panel made again is not approved any more; only current panels
   can be approved. `generate plan` lists each panel `approved` / `not approved` and blocks a shot
   until all its panels are approved, with the command to run.
5. `vidgen remote NAME generate inputs --guide`: the canny guide, the first frame and the shot's sheet
   `build/videogen/<shot>/sheet.png` (the panels in a grid at the clip's size, on its
   `sheet_background:`, below).
6. `vidgen remote NAME generate run --pay --shot ID`: the clip; a blocked shot is never paid for.

```
subjects:
  glider:
    look: "a grey jet glider with delta wings and red wing tips"
    views:
      - prompt: "a grey jet glider with delta wings and red wing tips seen from behind and above, cinematic film still"
      - {prompt: "the same grey jet glider in side view, nose to the left, cinematic film still", text: "in side view"}
  sea: {look: "a rough open sea", location: true, views: [{prompt: "a rough open sea from low over the water, late afternoon sun, cinematic film still"}]}
...
        generated_shot:
          kind: establishing
          model: ltx-2.3-union-control
          prompt: "a grey glider flies low over a rough open sea and banks gently, the chase camera following close behind"
          guide: canny
          first_frame: restyled
          subjects: [glider, sea]   # at most 4 panels in all
          size: 768x448             # the clip (multiples of 64); default 960x512 for 16:9
          duration: 5               # seconds: 5 = 121 frames, 1 = 25; default the part's length
          # fps: 12                 # generate at 12 fps (2, 4, 6, 8, 10 s; 8 s = 97 frames), doubled to 24 fps by RIFE
```

- Use a G4 session with ComfyUI's compiler off: `python tools/colab/setup_session.py NAME --gpu G4
  --no-comfy-compiler` (it restarts a running ComfyUI whose compiler is on); `generate run --pay`
  refuses a sheet shot otherwise. On a G4, a 5 s clip with a sheet takes about 80 s door to door
  (53 s in ComfyUI) and peaks at 42.7 GB of VRAM with the text encoder on the GPU. A G4 bills about 11.2 compute units an hour: set
  `videogen.comfyui.units_per_hour: 11.2` so the takes record the right units. The text encoder runs on the
  CPU and in RAM (`videogen.comfyui.text_encoder: cpu`, the default); `text_encoder: gpu` puts it in VRAM.
- **On an L4** (cheaper, 22.5 GB): `python tools/colab/setup_session.py NAME --gpu L4 --no-comfy-compiler
  --reserve-vram 10` (ComfyUI also gets `--disable-dynamic-vram --reserve-vram 10`; a running ComfyUI with
  other flags is restarted). Make sheet clips of 97 frames: `duration: 4` (24 fps) or `duration: 8` with
  `fps: 12`. Measured: peak 19.2 GB, about 26 s a step, the text step on the CPU about 150 s, about 7 min a
  clip; without the flags the first step runs out of memory. A G4 needs none of this.
  Render the web scenes with software WebGL on the L4: `VIDGEN_WEBGL=swiftshader vidgen remote NAME generate
  inputs --guide ...` (`vidgen remote` passes this computer's `VIDGEN_WEBGL` to the run, over the VM's `gpu`):
  the L4's GPU WebGL left black holes in gilded and reflective parts (seen 2026-11-26). A render made with
  the other backend is drawn again, not reused.
- **The sheet's background** (`sheet_background:` on the shot, or `videogen.sheet_background:` for all):
  LTX carries the sheet's overall brightness into the clip.
  - `black` (the default): right for outdoor daylight, sea and sky shots and for dark scenes (space,
    night). On the glider over the sea, `location` made the clip hazy and washed out (brightness 126
    instead of 68), with a second sun and a stray line.
  - `location`: the shot's location panel, blurred, a little brighter and tinted with its own
    average colour, fills the sheet and the panels sit on it (the sheet prompt adds "the panels sit on
    a softly blurred <location>"). Use it for indoor, lamp- or candle-lit scenes: on black, the
    Orrery's candle-lit workshop turned dark grey after the first frame (brightness 54, then 25-37);
    with `location` the same shot stayed warm and bright (67-72) with no jump. It needs a location
    subject among the shot's `subjects:`.
  - a colour `"#3a2a1a"` or a picture file (relative to the project, scaled to fill the sheet).
  Changing it composes the sheet again (free, `generate inputs`); the panels and their approval stay.
- First frame: with a sheet, prefer `first_frame: none`: the clip takes its look from the sheet and
  the guide, with no jump at frame 1. A restyled first frame (`first_frame: restyled`) whose
  brightness differs from what the clip becomes makes a visible jump after frame 0 (darker frame:
  the clip lifts; brighter: it drops). `first_frame_prompt:` may stay on the shot while
  `first_frame: none` (the plan notes it is not used). `first_frame_in: guide` runs with a sheet but
  opened on an over-exposed frame in the one test.
- Describe the light and look in the subjects' `look:` and the shot's `prompt:` ("bright warm
  candlelight", "plank wall glowing orange"): the sheet prompt repeats the looks, so "at night, deep
  shadows" in a location's look pulls the clip darker. Prompt words alone did not fix a dark sheet.
- The guide's edges become the clip's details: in the 3D scene, keep geometry clean (no broken edges,
  they turn into loose pins) and the background's edges sparse (dust dots and many plank edges turn
  into stars and line patterns).
- Keep your own sheets and pictures outside `assets/`: any file there counts as a change of every
  scene, so every shot's inputs read out of date.
- A second take of an unchanged shot is the first one again (`generate run` says the request is
  unchanged): set or change the shot's `seed:` for a new take (it also restyles a restyled first
  frame with that seed).
- One 5 s clip per beat: a beat longer than the model's longest clip (5 s) is split into parts.
  With silent shots, time the beat with a one-word placeholder and `pause:`, e.g. `text: "Gears."`
  with `pause: 4.6` makes exactly 5.00 s; `generate plan` prints each shot's length and frames.
- **Up to 10 s in one clip: `fps: 12`.** The limit is 121 generated frames. With `fps: 12` the clip is
  generated at 12 fps (the guide fitted at 12 fps) and doubled to 24 fps by RIFE in the same ComfyUI
  job, so the take is 24 fps like any other: `duration:` 2, 4, 6, 8 or 10 (`duration x 12 + 1` must be
  8k+1; 8 s = 97 frames, the GPU time of a 4 s clip at 24 fps, stored as 193). A beat is split over
  10 s at 12 fps. For an 8 s shot: `text: "Tick."`, `pause: 7.6`, `duration: 8`, `fps: 12` (the plan
  shows 8.00 s). Good for slow, steady moves over a long beat (on the L4 test the 8 s clip held its
  look); the cost: each tick or sudden step is spread over 2 frames (a made-up in-between frame).
  Keep `fps: 24` (the default) for fast, finely detailed motion. The RIFE weights come with
  `tools/colab/setup.sh`.
- A panel from a still instead of a prompt: `from: {scene, at}` (a frame of your render, `crop:
  [x, y, w, h]` in its pixels) or `image: FILE` (a picture file such as a `vidgen still` from another
  camera; never a video model's frame), with `text:` saying what it shows. Qwen-Image-Edit repaints it as
  a clean panel (the object on plain black, or the place itself; about 10 s a panel on a G4) and the
  contact picture shows the still under it. It keeps your render's shapes, and also its computer-made
  look. A view has exactly one of `prompt:`, `from:` and `image:`.
- A sheet you made yourself instead of `subjects:`: `sheet: FILE` (the clip's aspect ratio; it is scaled,
  never cropped) with `sheet_prompt:` describing its panels (the prompt starts `Reference sheet:
  <sheet_prompt>. Generated video: `). It needs no approval: you supplied it.

### Long films: one agent per phase

A film with generated shots takes hours, and one agent's context fills with logs until it slows
and forgets. Run one fresh agent per phase, with the project's `NOTES.md` as the handoff:

1. story and `video.yaml`, then the computer render (`vidgen render`, looked at);
2. the shots (`vidgen generate inputs --guide`, `generate run`);
3. reviewing the takes: pick, regenerate the bad ones (at most once each), place;
4. the final film: transitions, reveal, cards, sound, `vidgen render`.

Each agent reads `NOTES.md` first and appends its decisions, the files it made, what failed and
a timing table (step, wall time, GPU time).

### Your content and third-party services

- The MIT licence covers the software, not the videos you make or the files you add.
- Use only images, clips, screenshots, music and quotes you own or have permission to use
  (screenshots of other products may also show their trademarks).
- ElevenLabs narration and OpenAI pictures are subject to those providers' terms (e.g. plan
  limits on commercial use; cloning a voice requires the speaker's consent). Pictures made
  through OpenRouter, and narration voiced through it, are subject to OpenRouter's terms and to
  those of the model's provider.
- The built-in fonts (SIL OFL), Lucide icons (ISC), Natural Earth map data, sound effects and
  music beds may be used in your videos, including commercially, with no attribution required
  in the video (Natural Earth asks for none; the OFL and ISC notices concern redistributing the
  files themselves). So may composed music played with the default GeneralUser GS SoundFont (no
  attribution required; a credit in the description is welcome: `vidgen soundfont info` prints
  one); with your own `soundfont:` its licence applies.

