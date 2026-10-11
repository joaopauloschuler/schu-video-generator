# Cookbook examples

Helper modules, example custom scenes and starter configs that go with the
[video cookbook](../../docs/COOKBOOK.md). Copy the files you need into a project. Nothing here is
imported by vidgen itself.

## Files

| file | what it is | needs |
|---|---|---|
| [`fx.py`](fx.py) | palette constants, `glow`, `glow_dot`, `neuron` / `light`, `plane` / `stack` (depth), `dust` (live background), `pill`, `heading`, `flow`, `picture`, `run` | — |
| [`science_helpers.py`](science_helpers.py) | `load_picture`, `glow_dot`, `star_field` + `twinkle`, `rough_blob`, diatom shapes, `run` | — |
| [`vertical.py`](vertical.py) | `VScene`, a 9:16 scene base with a caption-safe content band (`top`, `bottom`, `mid`), `big`, `plate`, `chip`, `credit`, idle "breathing"; plus `cover`, `glow`, `glow_dot`, `star_field` | — |
| [`scene_skeleton.py`](scene_skeleton.py) | `my_scene`: a minimal custom scene with comments on the patterns that matter | `fx.py` |
| [`cold_open_photo.py`](cold_open_photo.py) | `cold_open`: photo + push-in + glowing streak + title + second line + boxed tag (4 beats) | `science_helpers.py` |
| [`software_scenes.py`](software_scenes.py) | `dataflow_hook` (3 beats), `stack_collapse` (2), `orbit_arch` (1), `finale` (2), from a software showcase, 16:9 | `fx.py` |
| [`paper_scenes.py`](paper_scenes.py) | `edx_probe` (3 beats), `nitrogen_clock` (4), `isotope_range` (3), from a paper explainer, 16:9 | `science_helpers.py` |
| [`vertical_scenes.py`](vertical_scenes.py) | `short_hook` and `short_end` (1 beat each) for 9:16 shorts | `vertical.py` |
| [`video.template.yaml`](video.template.yaml) | a starter 16:9 config: theme, voice, pronunciation, music, SFX, overlays, the cold open, chapter, sources and credits cards | `cold_open_photo.py`, `science_helpers.py` |
| [`short.template.yaml`](short.template.yaml) | a starter 9:16 short: karaoke captions with `lift`, tight pacing, hook and end scenes | `vertical.py`, `vertical_scenes.py` |
| [`whisper_check.py`](whisper_check.py) | stand-alone pronunciation check with faster-whisper (an optional fallback for `vidgen readback`) | `pip install faster-whisper` |

## Using them in a project

```bash
vidgen init my-video
cd my-video
cp <repo>/examples/cookbook/video.template.yaml video.yaml      # or merge it into yours
cp <repo>/examples/cookbook/{science_helpers,cold_open_photo}.py extensions/
# add your picture as assets/hook.jpg, then:
vidgen validate
vidgen storyboard
```

- **Imports.** vidgen imports every `*.py` file in `extensions/` as one package, so the example files
  import each other with relative imports (`from .fx import ...`, `from .science_helpers import
  ...`, `from .vertical import ...`). Keep the helper next to the scenes that need it (see the
  "needs" column). Renaming a helper means updating those imports.
- **Scene names must be unique** in a project. All the example files can be copied together; if you
  copy a scene to modify it, rename its `@scene("...")` name too.
- **`beat_count`** is checked: a scene's beats in `video.yaml` must match it (`vidgen validate`
  says so when they don't).
- **Assets** are resolved from the project root: write `assets/x.png` in `video.yaml`.
- **Every on-screen string is a param.** The defaults in `software_scenes.py` are placeholders
  (`<surprise>?`), and the ones in `paper_scenes.py` are a worked example's numbers with their source
  in `caption`. Set your own values in `video.yaml` (`vidgen list-scenes` shows every param).
- The 16:9 example scenes use fixed coordinates; for shorts, build on `VScene` from `vertical.py`.
- **Do not copy `whisper_check.py` into `extensions/`.** It is a command-line tool: run it from the
  project folder with `python whisper_check.py audio/*.mp3`.

## Keys

No file here contains a key. ElevenLabs reads `ELEVENLABS_API_KEY` from the environment (and
OpenRouter `OPENROUTER_API_KEY`); Kokoro runs locally and needs none. Never print or commit a key.
