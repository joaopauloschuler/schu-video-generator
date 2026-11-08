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
| `talking` | `heygen/avatar-iv` ($0.05/s) | a portrait (the speaker's sheet) + the beat's own voice (hosted) | a lip-synced close-up of a line |
| `action` | `bytedance/seedance-2.0-fast` | the characters' sheets, the style frame (+ the voice and a guide render, hosted) | people doing something |
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

**Account settings.** With "ZDR endpoints only" turned on in the OpenRouter account's privacy
settings, every video model is refused with HTTP 404 "ZDR violation (account settings)" (seen on
2026-11-07, nothing charged). Turn that setting off for the key that makes video. A free check of
what the settings allow: `GET https://openrouter.ai/api/v1/models` returns fewer models with the
key than without it when the privacy settings filter them out (compare the two counts). That list
has only text models, though, and `GET /api/v1/videos/models` (what `vidgen generate models`
reads) is **not** filtered by the key: a video model listed there may still be refused for your
account.

**Inputs must be URLs for sound and video.** OpenRouter accepts pictures inline (data URLs) but
refuses inline audio and video: HTTP 400 "Invalid reference URL: input_references[1].audio_url.url:
Only HTTPS URLs are allowed". The beat's voice (`audio:`, and every talking shot) and the guide
render (`guide:`) therefore need a hosted https URL. vidgen can share them for you through a
short-lived Cloudflare quick tunnel once you turn it on (`videogen: {host: quick_tunnel}`; see
[section 5](#5-sharing-voice-and-video-inputs-safely)). Without it those shots are blocked
(`inline_media: images`) or have a problem (`inline_media: all`), and `run --pay` refuses them
before anything is sent. Shots made only from words and pictures (establishing shots, action
shots without `audio:` / `guide:`) need no host.

**Picture sizes.** Sheet pictures are large (2048x3642, 5-7 MB each); six of them made a 48 MB
request, more than the 21 MB vidgen sends. vidgen now sends each picture as a smaller copy
(longest side 1280 px, JPEG quality 90; PNG only with transparency) cached in
`build/videogen/pictures/`; the files in `assets/sheets/` stay as they are. `vidgen generate plan`
prints each ready shot's request size.

## 4. The workflow

```yaml
title: The Early Ferry
format: {width: 1080, height: 1920, fps: 30}
voice: {provider: kokoro, voice: bf_emma}
voices: {theo_voice: {voice: am_michael, label: Theo}}
videogen: {provider: openrouter, budget_usd: 2.0, host: quick_tunnel}   # host: shares the talking shot's voice (section 5)
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
vidgen generate plan                 # nothing blocked? it also lists the files a run would share
vidgen generate run --pay            # the clips, each kept as a take with QA and a contact sheet
vidgen generate takes                # look at every contact sheet and QA finding
vidgen generate pick --shot closeup_b1 --take 1
vidgen render --preview              # the takes laid into the film
```

Sheet prompts: vidgen asks for clean model-sheet pictures (one person, full body, a plain grey
backdrop, nothing else, no text or props) and treats the style sheet's palette as colours only.
Describe a character by looks and clothes; a role ("sells tickets") is said as who the person is,
but words naming objects can still turn into objects, so keep them out of `reference_sheet.prompt`.
The printed and recorded cost of each picture is OpenRouter's reported `usage.cost`, or the
estimate marked "estimated" when it reports none.

The scene under a generated shot still matters: it is what shows when no take is picked, what
the guide render shows the model, and what the take fades from and to. A stage scene with the
characters in place is a good fallback.

## 5. Sharing voice and video inputs safely

**Why it is needed.** A talking shot is lip-synced to the beat's own voice, and a guide render
shows the model how the scene moves. OpenRouter will only take sound and video as a web address
(https), not as a file inside the request. So for those shots the files have to be reachable on
the internet for a moment, long enough for the video provider to download them.

**How vidgen does it.** It is off until you write `videogen: {host: quick_tunnel}` in
`video.yaml`. Then, for each paid shot that has a voice or guide, `vidgen generate run --pay`:

1. copies **only that shot's** `audio.mp3` / `guide.mp4` into a new temporary folder outside
   your project, under random names (nothing else of your project, its `build/` folder or your
   computer is ever reachable; pictures still go inside the request, not through the tunnel);
2. starts a tiny web server on your own computer that answers only those exact addresses, which
   contain a long random secret part; anything else gets "not found";
3. starts Cloudflare's free `cloudflared` program, which gives the server a temporary public
   address such as `https://some-random-words.trycloudflare.com` (no Cloudflare account needed);
4. checks through that public address that the files arrive whole; if not, it stops and closes
   everything, and nothing is sent to OpenRouter or paid;
5. sends the job with the secret addresses, and closes everything again as soon as the job is
   finished or failed (before the clip is downloaded), or 30 seconds after the provider fetched
   every file, or after 15 minutes at most, whichever comes first. Ctrl+C or an error closes it
   too. Closing stops `cloudflared`, stops the server and deletes the copies.

Each shot gets its own tunnel and its own secret, so no file stays reachable while other shots
are made. **What this means for you:** for those few minutes, anyone who has the full address
could download that shot's voice or guide clip; the address is random, never printed and never
written to disk, and it stops working when the tunnel closes. Do not turn the host on for
recordings you would not send to the video provider anyway. Settings: `host_max_minutes` (15,
the hard limit), `host_grace_seconds` (30), `tunnel_protocol` (`http2`, works on most
networks; `quic` or `auto` otherwise), `cloudflared` (the program's path, when it is not
found).

**What the ledger records** (`videogen-ledger.jsonl`, next to the paid jobs): `host_open` with
the tunnel's host name and each shared file's name, size and SHA-256 fingerprint (never the
secret address); `host_fetch` for every download of a shared file (which file, GET or HEAD,
the answer and the bytes sent; vidgen's own check is one of them); `host_close` with the reason
(`done`: the job ended; `all files fetched`; `max lifetime`; `error: ...`; `interrupted`),
how long it was open and whether the copies were deleted. No addresses of who downloaded are
kept.

### Test on Windows

1. Install `cloudflared` (free), then **open a new terminal** so it is found:

   ```bash
   winget install Cloudflare.cloudflared
   cloudflared --version
   ```

2. Check the tunnel alone. This is free: it shares one tiny text file vidgen makes up, fetches
   it back through the public address and closes; nothing goes to OpenRouter.

   ```bash
   vidgen generate host-test
   ```

   OK looks like this (the address differs every time):

   ```text
   sharing 1 file(s) (34 bytes) through a Cloudflare quick tunnel for at most 15 min; starting cloudflared
   public address some-random-words.trycloudflare.com (the files' paths have a secret part); checking it serves the files
     ok   public address answers HEAD with the file's length (some-random-words.trycloudflare.com)
     ok   GET through the tunnel returns the same bytes (HTTP 200, 34 bytes)
     ok   the address without the secret answers 404 (HTTP 404)
     ok   a wrong secret answers 404 (HTTP 404)
   quick tunnel closed (done); temporary copies deleted
   host test OK: some-random-words.trycloudflare.com served the file and refused other paths; closed (done)
   ```

   `vidgen generate host-test --keep 60` keeps it open a minute and prints the full address, to
   open in a browser. If it fails: "cloudflared was not found" means a new terminal is needed
   (or set `videogen: {cloudflared: "C:/Program Files (x86)/cloudflared/cloudflared.exe"}`);
   "stopped without a quick tunnel address" or "never served" usually means a firewall,
   antivirus or company network blocks Cloudflare (try `tunnel_protocol: quic` or `auto`, or
   another network). Run it again before deciding: a brand new address sometimes needs a few
   seconds more.

3. See what a run would share, without paying. In your project, with `host: quick_tunnel` set,
   the voices made (`vidgen tts`) and the inputs cut (`vidgen generate inputs`):

   ```bash
   vidgen generate plan --shot closeup_b1
   ```

   The shot is no longer blocked, and it lists exactly the files it would share:

   ```text
     audio: build/videogen/closeup_b1/audio.mp3 (the beat's voice, 3.43 s)
     would share through a public Cloudflare quick tunnel, only while this shot's job runs (at most 15 min; copies under random names behind a secret path; pictures are not shared, they go inline):
       build/videogen/closeup_b1/audio.mp3 (55,214 bytes)
   ```

4. One paid talking shot (heygen/avatar-iv, about $0.05 per second: a 4 s line is about $0.20;
   it needs `budget_usd`):

   ```bash
   vidgen generate run --pay --shot closeup_b1
   vidgen generate ledger
   ```

   It prints the sharing lines as in step 2, then `quick tunnel closed (done)` once the job is
   finished, then the new take. In `videogen-ledger.jsonl` you find, in order: `host_open`, a
   `host_fetch` (vidgen's own check, `HEAD`), `submit`, a `host_fetch` for each download by the
   provider (usually one `GET` of the whole file), `host_close` with `reason: done`, and the
   job's `completed` line with its cost. No provider download recorded means the provider did
   not fetch the voice through the tunnel: tell the developers (DESIGN §115). If the provider refuses the job, the tunnel is closed
   the same way and the error is shown with the secret part replaced by `<secret>`.

## 6. From a 3D scene to a generated clip

**The idea.** A `3d` scene ([COOKBOOK-3D.md](COOKBOOK-3D.md)) gives you exact control over the
layout: where the box stands, where each person walks, how the camera moves and when. A video
model gives you the look: real people, light, textures. A generated shot on a 3D scene can send
the model a plain "map" of the 3D picture as its guide video, so the clip keeps your layout and
camera while the model paints the rest. Your 3D scene stays in the film as the fallback (no take
picked) and as what the take fades from and to.

**Which guide to send** (`guide:` of the beat's `generated_shot`):

| `guide:` | what the model gets | choose it when |
|---|---|---|
| `true` (= `render`) | the normal 3D view, as a silent draft | the colours and shapes of your scene should show through |
| `depth` | grey by distance: near white, far dark, the background black | most shots: it carries the layout, the shapes and the camera move without your placeholder colours |
| `outline` | white edges on black, like a line drawing | the model takes edge or line-art guides, or the shapes' contours matter most |
| `mask` | each object one flat colour of its own on black | you want the model to keep each object apart (who is where); the prompt lists the stand-ins' colours by name |

`depth`, `outline` and `mask` work only when the beat's scene is `type: 3d` (`vidgen validate`
says so otherwise). The first frame (`first_frame: render`) is always the normal 3D view, never
the pass: a grey or flat-coloured first picture would push the model towards that look. The
characters still come from their reference sheets.

```yaml
title: Ana looks inside the crate
format: {width: 1080, height: 1920, fps: 30}
voices:
  ana: {}
videogen: {provider: openrouter, budget_usd: 2.0, host: quick_tunnel}   # host: the guide is a video, it needs https (section 5)
style_sheet: {palette: [warm sand, deep teal], notes: "soft late-afternoon light", frames: 1, frame_prompt: "a quiet town square"}
characters:
  - name: ana
    voice: ana
    reference_sheet: {prompt: "a woman in her thirties, short black hair, red jacket, dark trousers"}
  - name: ben
    reference_sheet: {prompt: "a tall man in his fifties, grey beard, blue work coat"}
scenes:
  - id: square
    type: 3d
    params:
      floor: {size: 14, color: "#2b3242"}
      camera: {position: [0, 3.0, 5.5], look_at: [0, 0.7, -0.5], fov: 56}
      objects:
        - {id: crate, shape: box, size: 0.9, position: [0, 0.45, -1.2], color: accent}
        - {id: ana, shape: standin, name: Ana, color: primary, position: [-1.7, 0.8, 1], rotation: [0, 90, 0]}
        - {id: ben, shape: standin, name: Ben, color: secondary, position: [1.7, 0.8, -0.4], rotation: [0, -90, 0]}
    beats:
      - id: walk
        voice: ana
        text: "I'll walk over to the crate and look inside."
        actions:
          - {object_walk: ana, at: "@walk", to: crate}
          - {object_face: ben, at: "@crate", to: ana}
          - {action: camera_dolly, by: 0.8, at: "@look"}
        generated_shot:
          kind: action
          model: bytedance/seedance-2.0-fast
          prompt: she walks to the wooden crate and lifts its lid while he turns to watch her
          setting: a quiet town square at the end of the afternoon
          characters: [ana, ben]                # their reference sheets go in as pictures
          guide: depth                          # the depth pass of the beat, not the normal 3D view
```

The same project is in `examples/3d-to-video/video.yaml`.

**The order of commands:**

```bash
vidgen validate                      # the 3D scene and the shot (a misspelt guide: gets a did-you-mean)
vidgen render --preview              # optional: look at the 3D scene first (add --guide-passes depth to see the pass)
vidgen generate sheets --pay         # Ana's and Ben's reference pictures, then set approved: true on each
vidgen tts                           # optional here (the shot sends no voice); it fixes the beat's timing
vidgen generate inputs --guide       # draft render + its depth pass, cut to the beat: build/videogen/walk/guide.depth.mp4
vidgen generate plan                 # "guide: build/videogen/walk/guide.depth.mp4 (depth pass of the beat's 3D scene, ...)"
vidgen generate host-test            # free: checks the quick tunnel works on this computer
vidgen generate run --pay --shot walk
```

`vidgen generate inputs --guide` renders the scene as a draft with the passes the shots need
(the 3D frames are reused when nothing changed), takes exactly the beat's part (the same start,
length, size and frame rate as `guide.mp4` would have) and converts the lossless pass to the
MP4 the provider gets (H.264, yuv420p). The plan names the pass in the shot's `guide:` line and,
with `host: quick_tunnel`, in the "would share" list; changing `guide:` is a new request (a new
clip and a new price), never the cached one. The prompt gets one sentence about the guide, for
example "The guide video is a depth map (near is white, far is dark): follow its layout and
camera motion."; a mask guide adds "Mask colours: Ana #ff8ce2, Ben #8cffd4." (up to four
stand-ins).

**Limits:**

- **It needs a host.** OpenRouter takes video inputs only as https addresses, so a guide (any
  kind) needs `videogen: {host: quick_tunnel}` (section 5). Without it the shot is blocked.
- **Depth contrast.** One depth range covers the whole shot. A camera that flies in close and
  pulls far back within one beat leaves the objects in a narrow band of greys; keep big camera
  moves for separate beats, or set the scene's `depth_range: [near, far]`.
- **Mask colours are close, not exact, in the MP4.** Inside each object the colour stays within
  a few levels of the table (`build/draft/three_d/<scene>.mask-colors.json`); along object edges
  the MP4's halved colour resolution blends neighbouring colours over a pixel or two. The
  lossless `.mkv` beside it is exact.
- **Models may ignore a guide.** Not every model or provider uses video references
  (BytePlus Seedance 2 and newer do; others may ignore them without saying so), and none
  promises to follow a guide exactly. Try one cheap shot first and look at the take.
- Labels and name tags are never in a pass (only the 3D shapes), and the guide is the draft's
  low resolution: it is for layout and motion, not detail.

## 7. Takes, QA and picking

Each clip becomes `takes/<shot>/<n>.mp4` with `<n>.json` (model, cost, QA) and
`<n>.contact.png`. QA checks the length, the aspect ratio and size, black and frozen stretches,
flicker and abrupt cuts. A take with QA errors (all black, nothing moving) is not shown unless you
pick it; warnings are for you to judge on the contact sheet. To get another take, change the
request (another `seed`, a clearer prompt, another model): the same request is never paid again.
`--take none` keeps vidgen's own picture for that beat. Commit `takes/` (paid footage).

## 8. In the film

The shown take covers its beat (from the beat's start to the next beat's; the last beat of a
scene keeps it to the scene's end), scaled and cropped to the format (`fit: cover`, or `contain`
with black bars), at the video's frame rate, lightly colour matched (`videogen.color_match`),
fading from and to vidgen's picture of the beat (`crossfade`; a cut at scene edges and between
two takes). Captions, overlays and titles are drawn on top; the voice, music and effects are
vidgen's mix.

## 9. Publishing

When the film shows takes, the description file ends with "Includes AI-generated footage
(models)." and `vidgen lint` notes each scene (`generated_footage`). Platforms ask you to disclose
realistic AI-generated footage: tick YouTube's "Altered or synthetic content" when uploading, and
use TikTok's AI-generated content label. The models' and OpenRouter's terms apply to the clips.
