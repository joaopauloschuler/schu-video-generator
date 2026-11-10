# Cookbook: directing your AI to make a film

schu-video-generator is used by AI agents, not typed by hand. This cookbook holds the instructions
from the tutorial video "How to direct your AI to make a film", in the order the video gives them,
as text you can copy without pausing. Each card is exactly what the video shows, word for word:
paste it to your AI. You never type a command yourself; the "AI does" lines tell you what to expect.

The example is "Get It All In": a 20-second portrait film (`bytedance/seedance-2.0-mini` through
OpenRouter, 480p, `sound: model`). Measured figures are in [What it cost](#what-it-cost-and-what-is-measured);
the mechanics behind every card are in [COOKBOOK-GENERATED-VIDEO.md](COOKBOOK-GENERATED-VIDEO.md).

**What you need:** an AI coding agent that can run commands on your computer (such as Claude),
an OpenRouter account with a little credit, and `cloudflared`. The commands used here (`vidgen generate frames`,
`vidgen split-sheet`, `first_frame_in`, `first_frame: last_of:`, `overlay.last.png`) exist from Step 319 on: if a card fails because of a missing command,
your copy of the tool is older than this guide.

**Say the cards in order.** Do not skip a "you check" line, and give your go before anything is paid.
Replace `[...]` with your own details; `shot1`, `take N` are examples.

**Disclosure.** All the footage is AI-generated. Disclose it when you publish, and do not use the faces or voices of real people.

## 1. Get set up

**Card 1**

```text
Install schu-video-generator from https://github.com/joaopauloschuler/schu-video-generator . Clone the repository so that its docs folder is on this computer, and install it in a Python 3.10, 3.11 or 3.12 virtual environment (the kokoro extra does not install on 3.13) with the extras 3d, kokoro and music. Install the Chromium browser that its 3D scenes need. Then check that vidgen generate --help lists the action frames, and tell me. If it does not, stop and tell me.
```

AI does: clones the repository, installs it with its extras on Python 3.10-3.12 (`pyproject.toml` limits the `kokoro` extra to Python below 3.13), installs Chromium, runs `vidgen generate --help`.
You check: the AI says `frames` is listed.

**Card 2**

```text
Install cloudflared on this computer. Then run the free tunnel test, vidgen generate host-test, and show me its last line. Tell me in one sentence what the tunnel shares and for how long.
```

AI does: installs `cloudflared`, runs `vidgen generate host-test` (free).
You check: `host test OK`. What the tunnel exposes: [section 5](COOKBOOK-GENERATED-VIDEO.md#5-sharing-voice-and-video-inputs-safely) of the generated video cookbook.

On the OpenRouter website (only you can do this):

- Create a key and give it a spending limit.
- If "ZDR endpoints only" is on in your account, turn it off for the key that makes video: with it on every video model is refused.
- Read [section 3](COOKBOOK-GENERATED-VIDEO.md#3-privacy-zero-data-retention) of the generated video cookbook: video generation cannot use Zero Data Retention, and what you send goes to the model's provider. Send no real people's faces or voices and nothing private.

**Card 3**

```text
I will not give you my API key. Tell me how to set my OpenRouter key as the environment variable OPENROUTER_API_KEY on this computer, so that it is visible to the shell your commands run in. When I say it is set, confirm that with a test that answers only yes or no, without showing its value. Never read it, print it or write it to a file, and do not ask me to paste it into this chat.
```

AI does: tells you how to set the variable where its own shell can see it (one set in another terminal is not visible to an AI that was already running: restart the AI afterwards), then reports the result of a yes-or-no test such as `[ -n "$OPENROUTER_API_KEY" ] && echo yes || echo no`. It does not touch the key.
You check: you set it yourself; the key never appeared in the chat; the AI answered only yes or no.

**Card 4**

```text
Create a new project folder for this film with a video.yaml for a portrait video: format 1080x1920 at 30 fps, preview 480x854 at 24 fps. Under videogen set provider openrouter, budget_usd 3, host quick_tunnel and sound model. Add no scenes yet; the file will not pass vidgen validate until it has scenes. The shots will use the model bytedance/seedance-2.0-mini at 480p. Read docs/COOKBOOK-GENERATED-VIDEO.md and docs/COOKBOOK-DIRECTING-YOUR-AI.md first, and tell me the two rules you must follow before any money is spent.
```

AI does: creates the project with `videogen: {provider: openrouter, budget_usd: 3, host: quick_tunnel, sound: model}` and no scenes, reads the cookbooks. A file with no scenes fails `vidgen validate` ("scenes: Field required"): that is expected until Card 9. Choosing voices waits for Card 9.
You check: it names both rules: no shot without a 3D guide and a starting picture; and this model takes a first frame or references, never both.

## 2. The rule that comes first

Our first film, "No Rush", used words and character pictures with no 3D guide and no starting picture. It cost $0.71 for four clips and, in the director's words, "The video makes absolutely no sense": "The video model is not able to guess from where the character should run (far to near, near to far)".

**Card 5**

```text
Standing rules for this project. No shot goes to a video model without a 3D guide video and a starting picture. vidgen does not enforce this, so check each shot's inputs in vidgen generate plan. Never run a command with --pay until I say go for that one shot. After each paid clip, stop and show it to me.
```

AI does: keeps the rules for the whole project.
You check: it repeats them in its own words.

## 3. The look and the story

If you have a style sheet picture (your characters and place side by side, made with any image tool; made-up characters only):

**Card 6**

```text
Here is my style sheet picture: [file name]. It has [number] panels side by side. Measure the gap between the panels in pixels, then cut the picture into one reference picture per panel with vidgen split-sheet, at scale 3, into assets/refs, and name each panel for what it shows, for example woman_full, woman_face, harbour. Show me the panels.
```

If you do not have one (the film did not use this route, so check the price and the result):

**Card 7**

```text
I have no style sheet. In video.yaml set imagegen to provider openrouter with the model bytedance-seed/seedream-4.5. For my two made-up stylised characters, write a reference_sheet prompt each, and write a style_sheet with one frame of the place. Do not base them on real people. Run vidgen generate sheets without --pay and tell me the price, then stop. After my go, pay, show me each picture, and set approved: true only on the ones I accept.
```

AI does: measures the gap between panels and runs `vidgen split-sheet` with `--columns`, `--gap`, `--names`, `--scale 3`, `--out assets/refs`, or sets `imagegen: {provider: openrouter, model: bytedance-seed/seedream-4.5}` (the default, `openai gpt-image-1`, needs a different key), writes the sheet entries and runs `vidgen generate sheets`.
You check: clean panels, nothing cut off, useful names.

**Card 8**

```text
Write a story for a 20-second film. One place. Two characters. Four shots of about 5 seconds each, with one fixed camera position for all of them. One clear action in each shot, and at most one short spoken line. A viewer must understand why everyone does what they do, even with the sound off. Give it to me as a table of shots before doing anything else, and wait for my go.
```

AI does: writes a table of shots and stops.
You check: read it as a viewer who knows nothing. The director rejected a story about a man proposing to a boat; keep it simple.

## 4. A 3D model for every shot

**Card 9**

```text
Build the film as crude 3D, one type: 3d scene per shot, with the same camera in all four and the same world (write the same objects into every scene), boxes for the buildings and stand-ins for the people. Leave name: off the stand-ins. Give each scene one beat whose id is the shot's id, so that --shot shot1 works, with the shot's line, and choose Kokoro voices, one per character. Add a generated_shot to each beat as shown under "A complete shot" in docs/COOKBOOK-DIRECTING-YOUR-AI.md, for now with kind, model, resolution, sound, audio and prompt. On every shot with speech set audio: beat. A shot with no speech needs audio: none and line: false; its beat's text is still voiced by vidgen tts as a placeholder, so it is heard in the preview and counts towards the length. Run vidgen tts, measure each voice, then set each beat's pause: so that the shot lasts about 5 seconds: a beat lasts its voice plus pause: (without pause:, plus narration.pad, 0.35 s), and the rendered scene is about 0.5 s longer, its fade-out, so the plan's shot window is shorter than the scene. Render a preview and show me each scene as its own video, build/preview/scenes/<shot>.mp4, in the normal coloured view, and judge where everyone ends up before the fade. Do not pay for anything.
```

AI does: one `type: 3d` scene per shot with the same camera and the same objects written out in each one (there is no shared world object; repeat them), stand-ins and boxes, one `generated_shot` per beat as in [A complete shot](#a-complete-shot), `vidgen tts`, each voice measured and each `pause:` set, `vidgen render --preview`. Each scene is at `build/preview/scenes/<shot>.mp4`.
You check: where everyone stands, the direction of movement, and where later things appear, before each scene's fade-out at the end. Moving a box is free; a clip is not.

## 5. The starting picture

**Card 10**

```text
Paint the starting picture of shot 1. On that shot add paint_first_frame with a prompt that says what the picture shows, and the reference pictures from assets/refs, each with a shows: label saying who or what it shows. Set first_frame: painted, and put the same reference pictures with the same shows: labels in generated_shot refs as well, so that they also go with the clip. Run vidgen generate frames without --pay and show me the layout and the price, then stop. When I say go, run vidgen generate frames --pay --shot shot1 and show me the picture. If it is missing what the story needs, repaint with another seed, but ask me first.
```

AI does: `paint_first_frame` with labelled references (`refs: [{file, shows}]`), the same `refs` on `generated_shot.refs` so they also go with the clip, `first_frame: painted`, a dry run of `vidgen generate frames`, then `--pay --shot shot1` after your go ($0.04 a picture on `bytedance-seed/seedream-4.5`; the same request is never paid twice).
You check: it has what the story needs; no text; faces right; another seed if not.

**Be aware:** the starting picture of "Get It All In" was painted by an earlier script doing the same job. `vidgen generate frames` has made a real picture ($0.04, coherent), but no clip has yet been made from a picture it painted.

## 6. What the provider really downloaded

**Card 11**

```text
After every paid shot, read videogen-ledger.jsonl and tell me which hosted files the provider really downloaded (host_fetch lines with method GET), and what the job cost. If a voice or guide I sent was not downloaded, stop and tell me.
```

Why: with `bytedance/seedance-2.0-mini`, a first frame together with references silently runs as a first-frame job. In the film's first test, the provider never downloaded the voice or the guide (the ledger shows only vidgen's own `HEAD` checks, no `GET`) and billed $0.177 instead of $0.191. No error is returned. Clear file names did not change what was downloaded. The same limit is reported by third-party docs and OpenRouter's Seedance 2.5 review; the limits of 9 images, 3 videos and 3 audio files per request come from third-party pages only, not official documents. vidgen now blocks such a shot on this model and warns when a hosted file was never downloaded.

## 7. The picture inside the guide

**Card 12**

```text
On shot 1 only, set guide: depth and first_frame_in: guide, so that the starting picture goes inside the guide video and no first frame is sent, and keep its refs so that the reference pictures go with the clip. Run vidgen generate inputs --guide --shot shot1 and show me build/videogen/shot1/overlay.png and overlay.last.png. Move the 3D stand-ins until they sit on what the picture shows, then show me again. All of this is free.
```

AI does: `guide: depth` and `first_frame_in: guide` on shot 1 only (the next shots get theirs in Card 14, when each has a starting picture), keeping its `refs`, `vidgen generate inputs --guide --shot shot1` (writes `guide.depth.opening.mp4`, `overlay.png`, `overlay.last.png`), moves the stand-ins.
You check: in `overlay.png` the 3D figures sit on the picture. Free.

**Card 13**

```text
Show me what vidgen generate plan says for shot 1: its inputs (an audio: line if it has a spoken line, and every reference picture with its label), its estimate and the budget left. Nothing may be blocked. Stop and wait for my go. When I say go, run vidgen generate run --pay --shot shot1. Then show me the clip, its contact sheet, its opening match and your ledger check, and stop again. Do not touch any other shot.
```

AI does: the plan, your go, `vidgen generate run --pay --shot shot1`, the clip, its contact sheet, its opening match, the ledger check.
You check: the plan shows the guide opening on your picture, an `audio:` line (the beat's voice) for every shot with a spoken line, and the reference pictures named (`reference: assets/refs/...`, showing their `shows:` labels), nothing blocked; then look at every second of the clip yourself.

**Close, not exact:** a true first frame scored `opening match` 0.98 and 0.985; the picture in the guide scored 0.83-0.86. In "Get It All In" only shots 2-4 used the picture in the guide; shot 1 used a true first frame and its voice and guide were ignored. The model sets its own speech timing; voice identity follows the file when it was downloaded, by the director's ear.

## 8. One shot leads to the next

**Card 14**

```text
I approve shot 1, take N. Pick it with vidgen generate pick. Now shot 2: set guide: depth, first_frame: last_of:shot1 and first_frame_in: guide on it, give it its reference pictures with shows: labels as on shot 1, run vidgen generate inputs --guide --shot shot2, and show me overlay.png and overlay.last.png. After my go, do the same plan, pay and show loop for this shot. Repeat this for each following shot, always one shot per go.
```

AI does: `vidgen generate pick --shot shot1 --take N`, `guide: depth`, `first_frame: last_of:shot1`, `first_frame_in: guide` and the labelled `refs` on shot 2, `vidgen generate inputs --guide --shot shot2` (cuts `last_of.shot1.N.png`), the overlays, then the loop of Card 13.
You check: the people are in the same places as at the end of the previous clip; the plan is not blocked. Picking another take later blocks the next shot until the inputs are cut again.

## 9. The final-frame check

**Card 15**

```text
Before paying for a shot where something appears later than its first frame, open overlay.last.png for that shot, which outlines in magenta what moved or appeared by the end, and also show me the last frame in the normal coloured 3D view. Tell me where each late object ends up and what it is touching, and if you cannot find the object, say so rather than inventing an answer. If it is in the wrong place, move it in the 3D scene, cut the inputs again with vidgen generate inputs --guide, and show me the overlay again. Say in the prompt where it must be too.
```

AI does: reads `build/videogen/<shot>/overlay.last.png` (the starting picture over the guide's last frame, with what changed since the guide's first frame at full strength inside a magenta outline), shows the last frame of the coloured preview too, moves the late object in the 3D scene, cuts the inputs again.
You check: the late object sits on the right material, in the overlay and in the coloured frame.

In the film, the arm that rises out of the water was placed in the 3D scene on the pier's edge, and came up through the concrete in the clip. Moving it into the water, and saying in the prompt "clear of the concrete and with water all around it", fixed the next take (paid again: $0.191). Both changed together, so this is the best evidence that the guide steers motion, not proof. Do not assume the AI follows the 3D model exactly.

## 10. Assembly, music, publishing

**Card 16**

```text
Assemble the film. Write a film.yaml beside video.yaml with the same format, output: <film name> so that it does not overwrite the 3D preview, and one video_clip scene per picked take: path takes/<shot>/<take>.mp4, region: bleed, fit: cover, fade: false, no beats, duration set to the take's length from ffprobe. Run vidgen render film.yaml --preview and show me the result and the frames around each cut. Do not make the final render until I approve the preview.
```

AI does: `film.yaml` with its own `output:` name and one `video_clip` per take (`region: bleed`, `fit: cover`, `fade: false`, no beats, `duration` from `ffprobe`), `vidgen render film.yaml --preview`. The description file and `vidgen lint` then say the footage is AI-generated. Details: [section 8](COOKBOOK-GENERATED-VIDEO.md#8-in-the-film) of the generated video cookbook.
You check: no dark frames at the cuts; the sound in step; clips in order.

**Card 17**

```text
Add background music to film.yaml: pick a built-in bed with vidgen list-music that suits the story, set it with music: {source: <bed>, volume: 6}, and render a new preview. Volume 6 is only a start: the music drops 12 dB for the whole of every clip that has sound, not under each spoken line, so at volume 0 it would sit about 20 dB under the characters' voices. Show it to me, and tell me which bed you chose and why.
```

AI does: `vidgen list-music`, `music: {source: <bed>, volume: 6}` in `film.yaml`, a new preview. Our film used only the model's own sound. By default the music ducks 12 dB for the whole of every clip with sound (`duck.clips`), with no per-word ducking; a test render confirmed volume 6 is a reasonable start: on the takes measured here the clips' voices are about -20 LUFS and the bed at volume 0 ducked is about -40 LUFS.
You check: your own ears.

**Card 18**

```text
Write the description for this film. It must say plainly that the footage is AI-generated. Then make the final render with vidgen render film.yaml and tell me the file's path.
```

AI does: writes the description, runs `vidgen render film.yaml`.
You check: tick the platform's AI label when you upload: "Altered or synthetic content" on YouTube, the AI-generated label on TikTok.

## A complete shot

What Card 9 and the later cards build, in one place. The beat's `id` is the shot's id (a beat without `id` gets `<scene>_b1`), so `--shot shot1` selects it. `sound: model` can stay on `videogen` (Card 4) instead of each shot; `place: false` keeps the take out of vidgen's own video (`film.yaml` of Card 16 plays it).

```yaml
scenes:
  - id: shot1
    type: 3d
    params:
      camera: {position: [0, 1.65, 6.4], look_at: [0, 1.4, -3], fov: 50}
      floor: {size: 40, color: "#20303a"}
      objects:   # write the same objects (and camera) into every scene: there is no shared world
        - {id: pier, shape: box, size: [3, 1, 34], position: [0, 0.5, -13], color: "#9aa0a6"}
        - {id: woman, shape: standin, color: "#e3b13a", position: [-0.8, 1.0, 0.2]}
    beats:
      - id: shot1   # the beat's id: `vidgen generate plan --shot shot1`, `run --pay --shot shot1`
        voice: woman
        text: "Get the whole ferry in!"
        pause: 2.4   # silence after the line, instead of narration.pad
        generated_shot:
          kind: action
          model: bytedance/seedance-2.0-mini
          resolution: 480p
          sound: model
          audio: beat   # the beat's voice goes in; an action shot has none by default
          prompt: "She poses on the pier and calls to the man behind the camera."
          place: false
          guide: depth   # with a starting picture and first_frame_in: guide, the depth pass opens on it
          first_frame: painted   # shot 1; later shots: last_of:shot1
          first_frame_in: guide
          paint_first_frame:
            prompt: "A woman in a yellow jacket stands on the left of a concrete pier."
            refs:
              - {file: assets/refs/woman_full.png, shows: the woman}
              - {file: assets/refs/harbour.png, shows: the pier and the harbour}
          refs:   # the same pictures go with the clip too
            - {file: assets/refs/woman_full.png, shows: the woman}
            - {file: assets/refs/harbour.png, shows: the pier and the harbour}
  - id: shot3
    type: 3d
    params: {}   # the same camera and objects as shot1, repeated
    beats:
      - id: shot3
        text: "Placeholder for the silent shot"   # still voiced by vidgen tts, heard in the preview
        pause: 3
        generated_shot:
          kind: action
          model: bytedance/seedance-2.0-mini
          resolution: 480p
          audio: none   # no speech: no voice input ...
          line: false   # ... and the placeholder text is left out of the prompt
          prompt: "He loses his footing and falls backwards off the edge."
```

## How to work with your AI

- Set a budget before anything else, and decide how far you will go.
- Approve each clip before paying for the next one.
- Make your AI show you the 3D scenes before any money is spent.
- Ask what really happened (the download log, the price), not what should have happened.
- Trust your own eyes and ears over the AI's checks: the automatic checks had nothing to say about the arm in the concrete.

The director's rule: "no shot can be sent to a video model without a 3D model video and at least the starting shot of each scene".

## What it cost and what is measured

| | US dollars |
|---|---|
| The whole film project, every attempt (`videogen-ledger.jsonl`) | 2.217 |
| of which the four clips in the film (0.177 + 3 x 0.191) | 0.75 |
| the film's starting picture | 0.04 |
| Separate earlier research runs, not in the 2.217 | 0.843 |

Clips are 496x864 pixels: soft next to full-size slides, and best shown small. The model is `bytedance/seedance-2.0-mini`, 480p, `sound: model`, through OpenRouter.

What is not shown to work: it has not been proven that the guide steers motion, and the model does not follow the 3D model exactly.
