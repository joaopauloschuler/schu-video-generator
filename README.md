# vidgen

Generate narrated, animated explainer videos from a project folder: scenes are drawn with
[Manim](https://www.manim.community/), narration comes from ElevenLabs, and ffmpeg joins
everything into one MP4 with SRT subtitles. Projects can add their own scene types and hooks in
an `extensions/` folder.

## Requirements

- Python 3.10+, `pip install -e .` (installs Manim, pydantic, PyYAML, PyAV)
- ffmpeg on PATH (Windows: `winget install ffmpeg`; macOS: `brew install ffmpeg`)
- An ElevenLabs API key in `ELEVENLABS_API_KEY` for narration
  (Windows: `setx ELEVENLABS_API_KEY your_key`, then open a new terminal)

## Quick start

```
vidgen init my_video            # scaffold video.yaml, extensions/, assets/
cd my_video
vidgen validate                 # check the config, scene types and audio status
vidgen tts                      # generate narration MP3s (only new/changed beats)
vidgen render --preview         # fast low-resolution check -> my_video_preview.mp4
vidgen render                   # final render -> my_video.mp4 + my_video.srt
```

Useful options: `vidgen render --scene ID` re-renders one scene and re-joins the video,
`--variant NAME` renders a named variant (e.g. a vertical 1080x1920 version), `--no-audio`
renders without narration, `--keep-going` continues past a failing scene, `--jobs N` renders
N scenes in parallel. `vidgen list-scenes` shows the available scene types.

Docs: [DESIGN.md](DESIGN.md) (architecture), [docs/CONFIG.md](docs/CONFIG.md) (config
reference), [docs/EXTENDING.md](docs/EXTENDING.md) (writing project extensions).
