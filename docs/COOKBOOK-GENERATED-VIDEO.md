# Cookbook: generated video shots

Some beats want real-looking footage: a face saying the line, two people acting, a harbour at
dawn. schu-video-generator can have a video model on OpenRouter make those shots while it keeps
everything else: the story and timing, the voices, captions, overlays, titles, music and the
final assembly. By default the model's own sound is not used (every job is sent with
`generate_audio: false`); section 8 says how to keep it. Reference: [CONFIG.md, Generated video](CONFIG.md#generated-video-videogen-vidgen-generate).

**The rule: a 3D guide and a starting picture for every shot.** No shot goes to a video model
without both a 3D guide video (`guide: depth`, `outline`, `mask` or `true`, from a `type: 3d` scene
built for that shot: section 6) and at least the starting picture of the scene (`first_frame:`).
Words and reference pictures alone do not say where anyone stands or which way they move: a model
cannot guess whether a character runs from far to near or from near to far, and shots made
separately will not agree with each other. Build one world for all the shots, look at the guides
(`vidgen generate inputs --guide`), and only then pay. A picture file of the shot is the best
starting picture; `first_frame: render` is the plain 3D view and can pull the clip towards that
look. A model that takes no video guide or no first frame cannot be used for a shot. vidgen does
not enforce this rule: `vidgen generate plan` does not block a shot without them, so check each
shot's inputs in the plan.

**Some models take a first frame or references, never both.** Seedance (`bytedance/seedance-*`) has
two separate modes: a first-frame job, or a reference job (pictures, a video and audio). A request
with both runs as a first-frame job and leaves the references out with no error: the provider never
downloads the voice or the guide, and it bills the no-reference price. On such a model the rule is
met with `first_frame_in: guide`: the starting picture becomes the first frame of the guide video, dissolving
into it, so the guide and the references all go in one reference job and no first frame is sent. The
setting is `generated_shot.first_frame_in`, `videogen.models.<model>.first_frame_in` or
`videogen.first_frame_in` (`frame` by default); `videogen.first_frame_dissolve` sets the dissolve
(0.4 s by default, always inside the guide's own length). `vidgen generate plan` and `run` block a
shot that sends a first frame and references to a model known to do this (a shot already paid for
is only noted), naming `first_frame_in: guide`; models with no evidence are not blocked.
`videogen.models.<model>.first_frame_with_references: true` overrides the block. After each hosted job, vidgen compares
what the provider actually downloaded (`GET`s in the ledger) with what it hosted, and warns in the
run output and the take's record: "the provider never downloaded the voice and the guide" means
that the clip was made without them.

## Plan the shots first

A video model paints what you tell it; it does not understand the story or the place. Plan in this
order and look at each step before you pay for the next.

1. **Write a story the viewer can follow without a mental map.** Everyone does what they do for a
   reason a viewer gets at once.
2. **Build one 3D world per location.** Every shot in that place is a camera placed in the same
   `type: 3d` world, so positions and distances always agree. Reuse the worlds and the character
   sheets across a film; they are built once.
3. **Keep the geography clear** (see below), with one scene per shot.
4. **Look at each scene as its own video in the normal coloured 3D view** (`vidgen render
   --preview`). The depth guide is what the model gets, but it is hard for people to read.
5. **Paint the starting picture of each shot and approve it** (see below).
6. **Only then pay for video** (section 4).

**Geography.** The camera may go anywhere; what the viewer must not lose is where things are and
which way people are going. In the one Short we tried with many camera positions and no guides, the
view turned around between shots, so a run away from the ferry and a run towards it looked the same
and the film made no sense. This guidance is standard film practice; it has not been tested on a
video model across many shots:

- Open each location with a wide shot that shows where everything is.
- Keep the camera on one side of the action (the 180-degree rule): if she runs left to right in one
  shot, she keeps running left to right in the next. To change sides, show the camera moving or cut
  away first.
- Each clip gets one camera position or one simple move, set by its 3D guide. A camera that never
  moves is an option for a very short film or a single gag, not a rule for a long one.

**The starting picture.** vidgen has no command that paints one, so it is a manual step: give an
image model that takes input pictures (OpenRouter's `bytedance-seed/seedream-4.5`, about $0.04 a
picture) a still of the 3D view as its first reference, plus crops of the character sheet, and put
the result under `assets/` for `first_frame:`. Leave `name:` off the stand-ins for that still, or
the name tags can turn into text in the picture. The model takes the 3D view as a suggestion, not as
geometry: check that what the story needs is still in the picture (an edge to fall off, room to walk
into), and repaint if not.

**Prompts and sound.** One clear action and at most one speaker per clip. Say in words which way
people move and that the camera stays still, if it does. For lip sync, use `sound: model` with the
beat's voice as the reference (section 8): the model keeps the voice and matches the lips, but it
speaks later than the voice file, up to about 0.9 s in our runs, so keep lines short and leave room.

**Traps.**

- A beat needs text, and a shot's length is that text's voice plus the beat's `pause:`. A silent
  shot therefore has placeholder text: set `audio: none` and `line: false` on it, or the placeholder
  goes into the prompt as a spoken line.
- A portrait project needs its own `preview: {width: 480, height: 854, fps: 24}`: the default preview
  is landscape at 15 fps.
- A `video_clip` scene fades in and spends its last 0.5 s fading out. For takes that must join with a
  plain cut, set `fade: false` on each `video_clip` (with `transition: cut`, the default): the clip is on
  screen from the first frame and the scene ends with its last narrated frame, so no fade or black
  gap comes between the takes.

**What it costs.** Measured on `bytedance/seedance-2.0-mini` at 480p: a 5 s clip cost $0.177 without
a guide and $0.191 with one, and listed prices at 720p are more than double. A 10-minute film is
about 120 clips of 5 s: roughly $23 for one take of each, plus about $5 for starting pictures, before
any retake. Decide the budget and how many retakes you can afford before you start.

**What was measured** (paid runs on `bytedance/seedance-2.0-mini`). A first frame together with
references runs as a first frame only: nothing is downloaded, and the job costs $0.177 instead of
$0.191 for 5 s. With `first_frame_in: guide` the provider downloads the voice and the guide (billed
$0.191), and the cut between two shots made this way was judged very good by the owner. The limits:
the opening is close to the picture, not exact (SSIM 0.87-0.88; a true first frame gave 0.81-0.98);
the model sets its own speech timing (a word expected at the start came at 3.16 s); it is still
unproven that the guide steers big movements; and clear file names on the hosted files did not
change what was downloaded. **Limits per request, from third-party pages, not official: 9 images,
3 videos, 3 audio files.**

**A recipe for one shot after another.**

1. Make the starting picture (above) of the first shot.
2. Fit the 3D figures to it: in the `type: 3d` scene, move the stand-ins until a draft of the scene lines up with
   the picture, so the guide agrees with what the picture shows. `vidgen generate inputs --guide` writes
   `build/videogen/<shot>/overlay.png`: the starting picture blended half and half over the first frame of the
   plain guide. Open it and check that the figures sit on what the picture shows; this costs nothing. (With
   `first_frame_in: guide` the overlay uses the plain guide, not the combined one, whose first frame is the picture.)
3. Make the shot with `guide: depth`, `first_frame: <the picture>` and `first_frame_in: guide`. Check the take: its
   QA lines and contact sheet give `opening match` (how close its first frame is to the starting picture, SSIM from 0
   to 1). Under 0.7 is a warning, a rough guide only: real clips measured 0.81 and 0.98 with a true first frame,
   0.87 and 0.88 with the picture in the guide.
4. Start the next shot from that shot's last frame: `first_frame: last_of:<shot id>` on the next shot, in either
   `first_frame_in` mode. `vidgen generate inputs` cuts the last frame of the take that shot shows (the picked take, or
   the newest without QA errors, the rule of `vidgen generate status`) into
   `build/videogen/<next shot>/last_of.<shot>.<take>.png`. Pick the take you want first: picking another take afterwards
   makes the next shot stale, and it cannot be paid for until you run `vidgen generate inputs` again. Go back to step 2.
   A shot whose source has no take is blocked, and vidgen never pays for the two in one run, so you can look at each
   clip before you pay for the next: `vidgen generate run --pay --shot <shot>`, look at the take, `generate pick`, cut, then run
   the next one.

## 1. When it is worth it

Generated video costs money (about $0.03-0.60 per second of clip, per take) and can fail
(frozen faces, flicker, a cut in the middle, the wrong person). Use it for a few shots that need
footage vidgen cannot draw; keep diagrams, text, charts and explanations as scenes. Three kinds:

| kind | model (examples) | inputs | good for |
|---|---|---|---|
| `talking` | `bytedance/seedance-2.0-mini` | a 3D guide opening on the starting picture (`first_frame_in: guide`) + the speaker's sheet + the beat's own voice (hosted) | a lip-synced line (the guide sets the framing: section 6) |
| `action` | `bytedance/seedance-2.0-fast` | a 3D guide opening on the starting picture (`first_frame_in: guide`) + the characters' sheets, the style frame (+ the voice, hosted) | people doing something |
| `establishing` | `google/veo-3.1-lite` (4/6/8 s; check `vidgen generate models` for what it accepts) | a first frame + a 3D guide + words | a place, a mood, a transition |

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
- A submit that is cut off (Ctrl+C, a crash or a lost answer after the request was sent) may still
  have been accepted and charged. vidgen wrote a `submit_intent` line to the ledger before sending,
  so the next run does not pay for that shot again by itself: `generate plan`, `run`, `status` and
  `ledger` show "no known outcome", and the shot's error tells you what to run. Look at your
  OpenRouter account's activity, then `vidgen generate resolve --intent ID` with `--not-charged`
  (the next run pays), `--job JOB_ID` (the next run polls and downloads it, free) or
  `--charged [--cost USD]` (the next run pays again, knowingly). Until then the intent counts
  against the budget at its estimate, because the money may be gone.
- Ask for the lowest resolution the model lists and the shortest length it allows (vidgen does
  both by default; the clip is trimmed to the beat). A Short at 480p-720p looks fine on a phone.
- Draft first: try one shot (`--shot ID`) with the cheapest model before the whole video.
- `videogen: {provider: mock}` runs the whole flow (takes, QA, render) with a fake API and
  synthetic clips: free, for trying a project's timing and layout. Nothing is shared: voice and
  guide files get fake addresses, no `cloudflared` is started, whatever `videogen.host` says.

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
    type: 3d
    params:
      floor: {size: 14, color: "#2b3242"}
      camera: {position: [0, 1.5, 3.5], look_at: [0, 1.4, 0], fov: 40}
      objects:
        - {id: theo, shape: standin, name: Theo, color: primary, position: [0, 0.8, 0]}
    beats:
      - text: "It is not late. It is early for being on time."
        voice: theo_voice
        generated_shot: {kind: talking, model: bytedance/seedance-2.0-mini, setting: the ferry quay in the fog, guide: depth, first_frame: render, first_frame_in: guide}
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
the guide render shows the model, and what the take fades from and to. Under the rule above it is a `3d` scene with the
characters in place.

**After an edit, cut again.** `vidgen generate inputs` records what each file in
`build/videogen/<shot>/` was cut from (`inputs.json`). If you then change the scene, the beat's text
or timing, the narration MP3 or the draft size, `vidgen generate plan` blocks the shot:

```text
  blocked: inputs changed since they were cut (guide.mp4: the scene changed (its config, a beat's text, voice or timing, assets, or vidgen)): run `vidgen generate inputs --guide` (free) before paying
```

`vidgen generate run --pay` refuses to start while a shot is blocked this way, so a run never pays
to send an old voice or guide. Cutting again is free (`--guide` renders the draft, which can take a
while). When the words of a line changed, run `vidgen tts` first: the plan says so. Inputs cut by an
older vidgen have no record and are blocked the same way. Not a change: picking a take (except for a
shot that starts from it with `first_frame: last_of:`), or editing the shot's own `prompt`, `model` or `seed`. Making new sheet pictures or adding files under
`assets/` does count for guides, because a render depends on `assets/`. A shot whose clip was
already paid for is reused free with a note, even after an edit; a new cut is a new request, paid
again.

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
5. checks the tunnel is still open with enough time left (otherwise nothing is sent or paid),
   sends the job with the secret addresses, and closes everything again as soon as the job is
   finished or failed (before the clip is downloaded), or after 20 minutes at most, whichever
   comes first. Ctrl+C or an error closes it too. Closing stops `cloudflared`, stops the server
   and deletes the copies. If vidgen is killed outright (Task Manager, `kill -9`, closing the
   terminal), a tiny watcher process stops `cloudflared` and deletes the copies at once. Only if
   the watcher is killed too or the computer loses power can copies stay on disk; the next
   tunnel you open deletes them, and a `cloudflared` left running then can be stopped by hand
   (it serves nothing: the local server ended with vidgen).

**It stays open for the whole job on purpose.** The tunnel no longer closes when the provider
has downloaded every file: some providers check the file when the job is submitted and download
it again when the job leaves the queue, and closing early would lose a job already paid for.
The price is a tunnel that can stay open for the job's whole wait, at most the limit below.

Each shot gets its own tunnel and its own secret, so no file stays reachable while other shots
are made. **What this means for you:** for those few minutes, anyone who has the full address
could download that shot's voice or guide clip; the address is random, never printed and never
written to disk, and it stops working when the tunnel closes. Do not turn the host on for
recordings you would not send to the video provider anyway. Settings: `host_max_minutes` (20,
the hard limit; 5-120; it must leave room for `poll_timeout`, or such shots are blocked with
the numbers to change: a smaller `poll_timeout` is how to keep the tunnel short on purpose,
vidgen then stops waiting sooner and a later run polls the job), `tunnel_protocol` (`http2`,
works on most networks; `quic` or `auto` otherwise), `cloudflared` (the program's path, when
it is not found).

**What the ledger records** (`videogen-ledger.jsonl`, next to the paid jobs): `host_open` with
the tunnel's host name and each shared file's name, size and SHA-256 fingerprint (never the
secret address); `host_fetch` for every download of a shared file (which file, GET or HEAD,
the answer and the bytes sent; vidgen's own check is one of them); `host_close` with the reason
(`done`: the job ended; `max lifetime`; `error: ...`; `interrupted`),
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
   sharing 1 file(s) (34 bytes) through a Cloudflare quick tunnel for at most 20 min; starting cloudflared
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
     would share through a public Cloudflare quick tunnel, only while this shot's job runs (at most 20 min; copies under random names behind a secret path; pictures are not shared, they go inline):
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
   `host_fetch` (vidgen's own check, `HEAD`), `submit_intent`, `submit`, a `host_fetch` for each download by the
   provider (usually one `GET` of the whole file), `host_close` with `reason: done`, and the
   job's `completed` line with its cost. No provider download recorded means the provider did
   not fetch the voice through the tunnel: tell the developers (DESIGN §115). If the provider refuses the job, the tunnel is closed
   the same way and the error is shown with the secret part replaced by `<secret>`, everywhere
   vidgen shows or stores it (also when a later run polls a job that failed).

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
the pass: a grey or flat-coloured first picture would push the model towards that look. With
`first_frame_in: guide` that picture opens the guide video (`guide.<pass>.opening.mp4`). The
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
          first_frame: render                   # the starting picture (better: a picture file of the shot)
          first_frame_in: guide                 # Seedance takes a first frame or references, never both: the picture opens the guide
```

The same project is in `examples/3d-to-video/video.yaml`.

**The order of commands:**

```bash
vidgen validate                      # the 3D scene and the shot (a misspelt guide: gets a did-you-mean)
vidgen render --preview              # optional: look at the 3D scene first (add --guide-passes depth to see the pass)
vidgen generate sheets --pay         # Ana's and Ben's reference pictures, then set approved: true on each
vidgen tts                           # optional here (the shot sends no voice); it fixes the beat's timing
vidgen generate inputs --guide       # draft render + its depth pass, cut to the beat, with the starting picture spliced in: build/videogen/walk/guide.depth.opening.mp4
vidgen generate plan                 # "guide: build/videogen/walk/guide.depth.opening.mp4 (depth pass of the beat's 3D scene, opening on first frame of the beat's render, ...)"
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
- **The guide decides the framing.** A shot with any guide (also `guide: true`) does not ask for
  it in words. A `talking` shot's prompt starts "Ana, speaking." instead of "Talking close-up of
  Ana, facing the camera, speaking", and the framing instructions in the character's sheet text
  (centred, whole body, front view...) are left out of the prompt under `Characters:`; the plan's
  `note:` quotes what was left out and why. A clause that also describes the character (clothes,
  hair, ...) stays whole, so write framing in sentences of its own. The sheet picture is
  unchanged, and unguided shots keep their wording exactly. A guided shot paid for before this wording changed is
  blocked, not paid again: its take stays in the film; set or change `seed:` on the shot (or its
  `prompt:`) to pay for a new take with the new wording.
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
vidgen's mix, even with `sound: model` below.

**A model's own sound.** `generated_shot.sound: model` (or `videogen.models:
{"author/name": {sound: model}}` per model, or `videogen.sound` for the whole project) sends
`generate_audio: true` and keeps the clip's own sound. It is off by default (`mix`), and `vidgen
generate plan` shows the value for each shot. It is a different request, so it is paid again, and
a model the list says cannot make sound is blocked. On Seedance 2.0 mini the sound followed the
beat's voice reference and the lips, but it was a new performance, up to about 0.9 s later than the
voice file, so laying the voice file over the clip cannot sync.

To play it: set `place: false` and put the take in a `video_clip` scene, with no beats so that nothing
else is mixed over it:

```yaml
- id: clip
  type: video_clip
  params: {path: takes/line/2.mp4, region: bleed}
  duration: 5
```

It plays at volume 1 (`volume:` changes it; a `video_clip` scene with narration plays the clip's
sound at 0.25). vidgen does not time captions or word-anchored actions from the clip's sound.

## 9. Publishing

When the film shows takes, the description file ends with "Includes AI-generated footage
(models)." and `vidgen lint` notes each scene (`generated_footage`). Platforms ask you to disclose
realistic AI-generated footage: tick YouTube's "Altered or synthetic content" when uploading, and
use TikTok's AI-generated content label. The models' and OpenRouter's terms apply to the clips.
