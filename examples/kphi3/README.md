# kphi3: a paper video built with vidgen extensions

"Saving 77% of the Parameters in Large Language Models" (3:51, 1920x1080 @ 30 fps), ported from
a one-off Manim project. All eight scenes are **custom scene types** in `extensions/`, written
with nothing but `vidgen.api`; vidgen itself knows nothing about this video. The narration
MP3s are committed in `audio/`, so you can render it without an ElevenLabs key.

The paper: João Paulo Schwarz Schuler and Alejandra Rojas Gómez, *Saving 77% of the Parameters
in Large Language Models* (technical report). Code and trained models:
github.com/joaopauloschuler/less-parameters-llm and huggingface.co/schuler.

**Narration licence**: the MP3s in `audio/` were generated with ElevenLabs (premade voice
"Brian", voice id `nPczCjzI2devNBz1zQrb`, model `eleven_multilingual_v2`) under the author's
paid plan. They are not covered by the repository's MIT licence, are provided only so this
example can be rendered, and are not part of the pip package (see `THIRD_PARTY_NOTICES.md`).

## Re-rendering

```
vidgen validate examples/kphi3            # config, scene params, audio: 27 ok
vidgen tts examples/kphi3 --dry-run       # 0 beats to generate (the MP3s are up to date)
vidgen render examples/kphi3 --preview    # 854x480 @ 15 fps, about 1 min with --jobs 2
vidgen render examples/kphi3 --jobs 2     # final 1080p -> kphi3_video.mp4 + .srt
vidgen render examples/kphi3 --scene params   # re-render one scene and re-join
```

Edit a beat's `text` in `video.yaml` and run `vidgen tts examples/kphi3` (needs
`ELEVENLABS_API_KEY`): only that beat is re-voiced. On-screen text and numbers are in each
scene's `params`; `vidgen list-scenes examples/kphi3` lists them with their beat counts.
The text uses the Inter font.

## How it maps to the original project

| original | here |
|---|---|
| `script.json` (voice, scenes, beats) | `video.yaml`: same voice, model and voice settings, the same 27 beat ids and texts; scene classes became `type: kphi_*` scenes with `params` |
| `audio/*.mp3`, `*.hash` | `audio/`, copied unchanged (vidgen accepts the old hash format, so nothing is regenerated) |
| `common.py`: colors, font | `theme:` in `video.yaml` (`base`, `k2`, `k3` model colors, `highlight` = gold, `accent`, `palette` = group colors) |
| `common.py`: `T`, `MT`, `column`, `edges`, `dense_pairs`, `grouped_pairs`, `counter` | the same helpers from `vidgen.api` (colors as theme tokens) |
| `common.py`: `NarratedScene`, `narrate()` | vidgen's `NarratedScene` (`with self.narrate(0) as d:` takes a beat index) |
| `scenes.py`: `mini_net`, `decoder_layer`, `loss_panel` | `extensions/common.py` |
| `scenes.py`: `S1Title` ... `S8Conclusion` | `extensions/s1_title.py` ... `s8_conclusion.py` (`kphi_title`, `kphi_sparsity`, `kphi_equivalence`, `kphi_method`, `kphi_setup`, `kphi_params`, `kphi_loss`, `kphi_conclusion`) |
| `render.py` | `vidgen render` (per-scene worker processes, `--preview`, `--scene`, `--jobs`, subtitles) |
| `tts_elevenlabs.py` | `vidgen tts` (cache by hash, retries, `--dry-run`) |

The animations are unchanged: same layout, colors, text, animation order and `run_time`
fractions of the beat length `d` (apart from the small legibility fixes of the Step 22 review,
listed at the end of [REGRESSION.md](REGRESSION.md), which make `vidgen lint examples/kphi3`
clean). Each scene type declares `beat_count`, so `vidgen validate`
reports a missing or extra beat before rendering.

The schematic scenes (`kphi_equivalence`, and `kphi_method` except its closing line) keep
their diagram labels in code; the title card, synapse numbers, dataset facts, parameter bars,
losses and takeaways are params.

## Differences from the original render

See [REGRESSION.md](REGRESSION.md). In short: the frames match the original (72 of 81 sampled
frames are bit-identical, the rest differ only by encoder noise at ≥ 75 dB PSNR), but each beat
ends on the nearest frame (the original truncated), so the video is 12 frames (0.4 s) longer,
and the narration is in sync to within 1 ms (the original lagged by 20 to 60 ms).
