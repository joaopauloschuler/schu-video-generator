# Cookbook: generated video shots

Some beats want real-looking footage: a face saying the line, two people acting, a harbour at
dawn. schu-video-generator can have a video model on OpenRouter make those shots while it keeps
everything else: the story and timing, the voices, captions, overlays, titles, music and the
final assembly. The model's own sound is never used (every job is sent with
`generate_audio: false`). Reference: [CONFIG.md, Generated video](CONFIG.md#generated-video-videogen-vidgen-generate).

## 1. When it is worth it

Generated video costs money (about $0.03-0.60 per second of clip, per take) and can fail
(frozen faces, flicker, a cut in the middle, the wrong person). Use it for a few shots that need
footage vidgen cannot draw; keep diagrams, text, charts and explanations as scenes. Three kinds:

| kind | model (examples) | inputs | good for |
|---|---|---|---|
| `talking` | `heygen/avatar-iv` ($0.05/s) | a portrait (the speaker's sheet) + the beat's own voice | a lip-synced close-up of a line |
| `action` | `bytedance/seedance-2.0-fast` | the characters' sheets, the style frame, the voice, a guide render | people doing something |
| `establishing` | `google/veo-3.1-lite` (4/6/8 s) | words (+ an optional first frame) | a place, a mood, a transition |

## 2. Cost control

- Set a hard cap: `videogen: {budget_usd: 2.0}`. Nothing is paid without it, and nothing without
  `--pay` (`generate_run` over MCP: `dry_run: false` and `confirm_cost: true`).
- Every job is in `videogen-ledger.jsonl` (estimate when submitted, reported cost when done; a
  job without a reported cost counts at its estimate). `vidgen generate ledger` shows it.
- Before paying, vidgen estimates each clip from OpenRouter's model list (the highest price
  that could apply) and refuses a run whose ready shots are above what the budget has left.
- Same request, same clip: the cache (`assets/generated_video/`) and the ledger make sure a
  request is never paid twice; a job still running when vidgen stops waiting is polled by the next
  run, never submitted again. No paid job is retried automatically; the first failure stops a run.
- Ask for the lowest resolution the model lists and the shortest length it allows (vidgen does
  both by default; the clip is trimmed to the beat). A Short at 480p-720p looks fine on a phone.
- Draft first: try one shot (`--shot ID`) with the cheapest model before the whole video.
- `videogen: {provider: mock}` runs the whole flow (takes, QA, render) with a fake API and
  synthetic clips: free, for trying a project's timing and layout.

## 3. Privacy (Zero Data Retention)

Video generation on OpenRouter is **not eligible for Zero Data Retention**: the provider keeps the
output for a while so it can be downloaded, and inputs (portraits, voices, renders) go to the
model's provider. Do not send faces or voices of real people without their consent, private
material, or anything you may not share. The key is read from `OPENROUTER_API_KEY` only when a
paid request is made and is never stored or logged (or set `videogen.key_via_proxy: true` when a
network proxy adds it).

## 4. The workflow

```yaml
title: The Early Ferry
format: {width: 1080, height: 1920, fps: 30}
voice: {provider: kokoro, voice: bf_emma}
voices: {theo_voice: {voice: am_michael, label: Theo}}
videogen: {provider: openrouter, budget_usd: 2.0, inline_media: all}
style_sheet: {palette: [slate blue, sea green, warm orange], lens: "35 mm", notes: "soft overcast light", frames: 1, frame_prompt: "a foggy harbour"}
characters:
  - name: theo
    voice: theo_voice
    reference_sheet: {prompt: "a man in his twenties, curly red hair, round glasses, green cardigan"}
scenes:
  - id: closeup
    type: stage
    set: beach
    params: {characters: [{name: theo}]}
    beats:
      - text: "It is not late. It is early for being on time."
        voice: theo_voice
        generated_shot: {kind: talking, model: heygen/avatar-iv, setting: the ferry quay in the fog}
```

```bash
vidgen generate plan                 # free: every shot, its inputs, length, estimate, the budget
vidgen generate sheets --pay         # the reference pictures (look at them in assets/sheets/)
#   set approved: true on each sheet you like (no shot uses a sheet before)
vidgen tts                           # the voices (the talking shot is lip-synced to them)
vidgen generate inputs --guide       # cuts each shot's voice, guide render and first frame
vidgen generate plan                 # nothing blocked? tell whoever pays the total
vidgen generate run --pay            # the clips, each kept as a take with QA and a contact sheet
vidgen generate takes                # look at every contact sheet and QA finding
vidgen generate pick --shot closeup_b1 --take 1
vidgen render --preview              # the takes laid into the film
```

The scene under a generated shot still matters: it is what shows when no take is picked, what
the guide render shows the model, and what the take fades from and to. A stage scene with the
characters in place is a good fallback.

## 5. Takes, QA and picking

Each clip becomes `takes/<shot>/<n>.mp4` with `<n>.json` (model, cost, QA) and
`<n>.contact.png`. QA checks the length, the aspect ratio and size, black and frozen stretches,
flicker and abrupt cuts. A take with QA errors (all black, nothing moving) is not shown unless you
pick it; warnings are for you to judge on the contact sheet. To get another take, change the
request (another `seed`, a clearer prompt, another model): the same request is never paid again.
`--take none` keeps vidgen's own picture for that beat. Commit `takes/` (paid footage).

## 6. In the film

The shown take covers its beat (from the beat's start to the next beat's; the last beat of a
scene keeps it to the scene's end), scaled and cropped to the format (`fit: cover`, or `contain`
with black bars), at the video's frame rate, lightly colour matched (`videogen.color_match`),
fading from and to vidgen's picture of the beat (`crossfade`; a cut at scene edges and between
two takes). Captions, overlays and titles are drawn on top; the voice, music and effects are
vidgen's mix.

## 7. Publishing

When the film shows takes, the description file ends with "Includes AI-generated footage
(models)." and `vidgen lint` notes each scene (`generated_footage`). Platforms ask you to disclose
realistic AI-generated footage: tick YouTube's "Altered or synthetic content" when uploading, and
use TikTok's AI-generated content label. The models' and OpenRouter's terms apply to the clips.
