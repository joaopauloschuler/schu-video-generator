# Signal Fire — an orchestral cue and the picture that follows it

A 27 s video with no narration: an original cinematic cue played by vidgen's own orchestra, and a
three.js night scene that reads the score while it plays. It puts four things of Phase AL
together (DESIGN §120): the orchestral instruments, expressive notes, the built-in music data of
`web` scenes and the finishing module `vidgen/three-finish`.

| file | what it shows |
|---|---|
| [assets/music/signal_fire.yaml](assets/music/signal_fire.yaml) | a score file, 90 BPM in C minor, 9 bars (24 s) and the last chord's ring: a solo violin slurred, with a glide up a sixth and a late vibrato; cellos changing stroke on one track (`[tremolo]`, `[spiccato]`, `[sustain]`); double basses, violins, four horns (`[fp <]`), trumpet (a slurred melody under a hairpin to `fff`), low brass (a swell into the hit), choir (a hum opening to "ooh", then "aah", `morph`), timpani (a roll growing into the hit on the same track), taikos, bass drum, snare roll, cymbal swell and crash, tam-tam; the end in C major |
| [extensions/signal_fire.js](extensions/signal_fire.js) | a ring of standing stones around a brazier at night. Every scene has `music_data` (only the tracks the page reads), so `ctx.music` gives it the score's events in song time and the measured mix: the violin's and the cellos' notes send up embers, the choir lights the sky, the timpani light a ring on the ground (a roll as loud as its hairpin has grown), taiko hits flash the stones and send shock rings, the trumpet's pitch sets a beam's height (gliding on slurred notes), the crash and the gong flash the frame; the camera follows the form, never a beat. Finished with `Finish`: bloom, ACES, a grade from cool to warm, vignette, grain, FXAA, depth of field on the brazier |
| [extensions/web_cut.py](extensions/web_cut.py) | the `web` scene without its fade-out (docs/EXTENDING.md, "A variant of the `web` type"), so the three scenes cut on bar lines while the music goes on |
| [video.yaml](video.yaml) | three scenes of 8, 8 and 11 s on one script; vidgen works out each scene's song time (`ctx.music.t0`: 0, 8, 16) |

```
vidgen validate examples/signal-fire
vidgen music render examples/signal-fire/assets/music/signal_fire.yaml --out signal_fire.wav   # about 50 s
vidgen still examples/signal-fire --scene fire --at 0.1 --at 3 --at 5.5 --size preview
vidgen render examples/signal-fire --draft      # then --preview, then the final render
```

Needs Chromium once: `python -m playwright install chromium` (Windows: `py -m playwright install
chromium`). Nothing generated is committed.

**Render cost** (2 cores, software WebGL; Step 351): the score about 50 s (once; `vidgen still`
and the render share it through `build/music`); the page 0.45 s a frame at 1280x720, so the
final render of 810 frames took about 8 minutes, and left 570 MB of lossless frames clips in
`build/final/web` (`--intermediate compact --clean-intermediates` keeps that small). `--draft`
drops the depth of field and draws the bloom smaller.

**Nobody has listened.** The cue was judged by measurement and a spectrogram (the glide, the
spiccato ostinato, the hit at 16 s and the C major end are where the score puts them); `vidgen
music check` calls its 32 dB from the quiet start to the hit "unsteady", which is right for a
piece without narration and wrong under a voice.
