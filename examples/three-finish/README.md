# A still life in metal — finishing a three.js scene

One silent `web` scene of 6 s that shows what vidgen's finishing module `vidgen/three-finish`
does to a three.js picture (`vidgen guide web`, "Finishing three.js scenes"; the reference is
[docs/CONFIG.md](../../docs/CONFIG.md#web), "Finishing three.js scenes").

| file | what it shows |
|---|---|
| [extensions/still_life.js](extensions/still_life.js) | brass gears and five spheres (chrome, gold, brushed steel, copper, black lacquer) on slate, lit by `studioEnvironment` (soft boxes baked through PMREM) and one key light with `softShadows`; circular graining and brushing from `surfaceFinish`; the focus pulled from the front sphere to the gears at the back between 1.5 s and 4 s (`dof` as a function of `t` with `focusDistance`); the small gear in front spins at nearly 4 turns a second and is blurred by `motionBlur` (6 sub-frames over a 180° shutter, through the page's `update(t)`); default bloom on the lamp and the highlights, ACES, a grade that cools over the shot, vignette, grain, FXAA |

```
vidgen validate examples/three-finish
vidgen still examples/three-finish --scene still_life --at 0.5 --at 3 --at 5.5
vidgen render examples/three-finish --draft      # 426x240 at 8 fps: about 40 s here
vidgen render examples/three-finish --preview    # then the final render
```

Needs Chromium once: `python -m playwright install chromium` (Windows: `py -m playwright install
chromium`). Nothing generated is committed.

**Render cost** (2 cores, software WebGL, 1280x720; Step 350): the plain `renderer.render` of this
scene takes about 0.47 s a frame; with the whole finish about 3.0–3.3 s, of which motion blur's six
drawings of the scene are about 2.6 s. So the final render of the 6 s (180 frames) takes about
10 minutes. Turn motion blur off or down (`samples: 3`) while working, or use `--draft`.

**Comparing stills.** The page reads `ctx.data.off` (a list of `bloom`, `dof`, `motion`, `grade`,
`vignette`, `grain`, `fxaa`, `tone`) and `ctx.data.finish` (options laid over its own), so a copy
of the scene with `params: {script: extensions/still_life.js, data: {off: [dof, motion]}}` shows the
picture without those two.
