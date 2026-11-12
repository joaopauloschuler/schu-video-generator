# Third-party notices

schu-video-generator (the `vidgen` command and Python package) itself is MIT-licensed (see
`LICENSE`). It bundles the following fonts as package data in
`src/vidgen/data/fonts/`, each under the **SIL Open Font License 1.1**; the full licence text is
in the `OFL.txt` next to each family's files. The fonts are distributed unmodified (Inter and
JetBrains Mono NL were decompressed from WOFF2 to TTF, a lossless format conversion). They may be
used, embedded in rendered videos and redistributed with schu-video-generator under the OFL's terms; they may
not be sold on their own.

| Family (Pango name) | Files | Version | Copyright | Obtained from |
|---|---|---|---|---|
| Inter (`Inter`) | `Inter/Inter-Regular.ttf`, `Inter-Bold.ttf`, `Inter-Italic.ttf` (~0.98 MB) | 4.001 | © 2016-2018 The Inter Project Authors (me@rsms.me; https://github.com/rsms/inter) | npm package `inter-ui` 4.1.1 (`web/*.woff2`) |
| Source Serif 4 (`Source Serif 4`) | `SourceSerif4/SourceSerif4-Regular.ttf`, `-Bold.ttf`, `-It.ttf` (~0.72 MB) | 4.005 | © 2014–2023 Adobe (http://www.adobe.com/), with Reserved Font Name ‘Source’ | npm package `source-serif` 4.5.1 (Adobe's release, `TTF/`) |
| JetBrains Mono NL (`JetBrains Mono NL`) | `JetBrainsMono/JetBrainsMonoNL-Regular.ttf`, `-Bold.ttf` (~0.29 MB) | 2.242 | © 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono) | npm package `jetbrains-mono` 1.0.6 (`fonts/webfonts/*.woff2`); licence text from `@fontsource/jetbrains-mono` 5.3.0 |

JetBrains Mono NL is the variant of JetBrains Mono without coding ligatures, so code listings
show exactly the characters that were typed.

## Icons

schu-video-generator bundles icons from **Lucide** (https://lucide.dev) as package data in
`src/vidgen/data/icons/lucide/` (the SVG files unmodified, each keeps its `@license` comment),
obtained from the npm package `lucide-static` 1.52.0. Lucide is under the **ISC License**,
© Lucide Icons and Contributors; the icons Lucide derived from Feather are also under the
**MIT License**, © 2013-present Cole Bemis. Both licence texts, and the list of the
Feather-derived icons, are in `src/vidgen/data/icons/lucide/LICENSE`. The icon names, categories,
search tags and aliases are in `src/vidgen/data/icons/manifest.json` (tags from Lucide's
`tags.json` plus some added by schu-video-generator; aliases are Lucide's old names of renamed icons plus a few
schu-video-generator synonyms); `tools/vendor_icons.py` re-creates the folder (200 icons) and the catalogue
`docs/ICONS.md` from `tools/icon_set.json`.

## World map

The `map` scene draws countries from `src/vidgen/data/geo/world-110m.json`, made by
`tools/make_world_map.py` from:

- **Natural Earth** 1:110m Cultural Vectors, Admin 0 – Countries (https://www.naturalearthdata.com).
  Natural Earth data is in the **public domain**; no permission is needed to use, modify or
  redistribute it. "Made with Natural Earth" is appreciated. Country borders are Natural Earth's
  *de facto* representation; schu-video-generator takes no position on disputed boundaries.
- obtained as TopoJSON from the npm package **`world-atlas`** 2.0.2 (`countries-110m.json`),
  © 2013-2019 Michael Bostock, **ISC License**:

  > Permission to use, copy, modify, and/or distribute this software for any purpose with or
  > without fee is hereby granted, provided that the above copyright notice and this permission
  > notice appear in all copies. THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL
  > WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
  > FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR
  > CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS,
  > WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
  > CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

- ISO 3166-1 alpha-2 / alpha-3 codes and English country names and aliases from the npm package
  **`i18n-iso-countries`** 7.14.0, © 2016 widdix GmbH, **MIT License**:

  > Permission is hereby granted, free of charge, to any person obtaining a copy of this software
  > and associated documentation files (the "Software"), to deal in the Software without
  > restriction, including without limitation the rights to use, copy, modify, merge, publish,
  > distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
  > Software is furnished to do so, subject to the following conditions: The above copyright
  > notice and this permission notice shall be included in all copies or substantial portions of
  > the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  > IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
  > PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
  > LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
  > OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
  > DEALINGS IN THE SOFTWARE.

The geometry was converted (antimeridian cuts, ring orientation, coordinates rounded to 0.01°)
and label points and aliases were added; the `source` entry of the file records this. The same
notices ship with the data as `src/vidgen/data/geo/LICENSE`.

## three.js

The `3d` scene type draws with **three.js** (https://threejs.org), bundled as package data in
`src/vidgen/data/three/`: `three.module.js` and `three.core.js` unmodified from the npm package
`three` 0.186.1 (`build/`; SHA-256 `9052042d676cb0fdc1ddfefe193053f34b7ac0513a616fdac4535d49987812ea`
and `9edde002b066a9a05676a6127f67735b62baf399bdea529f2f7e31657da769e6`), under the **MIT
License**, © 2010-2026 three.js authors; the licence text is `src/vidgen/data/three/LICENSE`.
The page loads them from the package, never from the network. A chosen set of three.js add-ons
for `web` scenes is bundled in `src/vidgen/data/three/addons/`: 23 files copied unmodified from
`examples/jsm/` of the same npm package (same version, same MIT licence, a copy of which is
`src/vidgen/data/three/addons/LICENSE`); `loaders/SVGLoader.js` contains a number parser that its
comment says comes from svg-numbers (https://github.com/ppvg/svg-numbers, MIT License). **Playwright** (optional `3d`
extra; Apache-2.0, © Microsoft) drives the headless Chromium it downloads with
`playwright install chromium` (Chromium: BSD-style licence and its third-party notices); neither
is bundled.

## Animation and chart libraries for `web` scenes

A `web` scene's page can import five JavaScript libraries bundled as package data in
`src/vidgen/data/web/libs/<package>/`. Each is one build file copied unmodified from the npm
package (the registry's tarball, its `dist.integrity` sha512 checked), with the package's licence
file beside it as `LICENSE`:

| Package | File (in the package) | Bytes | SHA-256 | Licence | Copyright |
|---|---|---|---|---|---|
| animejs 4.5.0 | `anime.esm.min.js` (`dist/bundles/`) | 118 678 | `a19015a1a92d52025a2fb6703b6d67eadd1cc2aeaf880770e96e04cf6aa07be1` | MIT | © 2025 Julian Garnier |
| motion 14.12.0 | `motion.js` (`dist/`) | 188 678 | `a18fc08eb11c67658b34270bb71bc4ba806c87dbc1b720d7acd38c437844eee7` | MIT | © 2024 Motion B.V. |
| d3 7.9.2 | `d3.min.js` (`dist/`) | 280 622 | `912111098ea99503a6f4967361d2bbdc9dbf58cf9c678c8e27e5b02d1a07f0c1` | ISC | © 2010-2026 Mike Bostock |
| chart.js 4.6.1 | `chart.umd.min.js` (`dist/`) | 210 082 | `87364cc2b2a76a6684929e7d6b80b18a897794db38400caff1fcf1791c6925d2` | MIT | © 2014-2024 Chart.js Contributors |
| lottie-web 5.13.0 | `lottie.min.js` (`build/player/esm/`) | 589 019 | `61cd35a14b6519b7b6073a32e1bb037dab613c2033a3141fc2611295acf6c18e` | MIT | © 2015 Bodymovin |

Three of these files contain the code of other npm packages; the licence files of those packages
are joined in `LICENSES-bundled.txt` beside the file (read from each package's latest version on
the npm registry on 2026-11-12; the bundle may contain an earlier version):

- `d3.min.js`: the 30 `d3-*` modules (ISC, © Mike Bostock; `d3-ease` BSD-3-Clause, with easing
  equations © 2001 Robert Penner; `d3-scale-chromatic` includes ColorBrewer colours, © 2002
  Cynthia Brewer, Mark Harrower and The Pennsylvania State University, Apache-style licence;
  `d3-geo`'s licence file includes GeographicLib's, © 2008-2012 Charles Karney, MIT; `d3-delaunay` ISC, © Observable, Inc.
  and Mapbox), `delaunator` (ISC, © Mapbox), `robust-predicates` (Unlicense, public domain) and
  `internmap` (ISC, © Mike Bostock);
- `chart.umd.min.js`: `@kurkle/color` (MIT, © 2018-2024 Jukka Kurkela);
- `motion.js`: `framer-motion` (MIT, © 2018 Framer B.V.), `motion-dom` and `motion-utils` (MIT,
  © 2024 Motion B.V.); the licence of `tslib` (0BSD, © Microsoft Corporation), a dependency the
  package declares, is included too, though none of its helpers was found in the file.

`lottie.min.js` keeps the notice of the seeded random generator it contains (seedrandom,
© 2014 David Bau, MIT). `index.js` beside the d3, chart.js and motion files is written by
schu-video-generator (an ES module that runs the package's UMD file and exports its names).

**GSAP** (GreenSock) is not shipped and not bundled: the files of the npm package `gsap` 3.15.1
carry "Copyright 2026, GreenSock. All rights reserved. Subject to the terms at
https://gsap.com/standard-license" and the package has no licence file, so it cannot be
redistributed under an open-source licence. A project may use its own copy under GSAP's terms.

## Sound effects and music beds

The built-in sound effects and the three music beds are synthesised by schu-video-generator's own code (no
recordings or samples); they are free to use in your videos, including commercially, with no
attribution needed.

## Dependencies (not bundled)

schu-video-generator's dependencies are installed by pip, not shipped in this package, and keep
their own licences. Notably:

- **PyAV** (`av`): its binary wheels bundle FFmpeg builds that include GPL/LGPL components
  (e.g. libx264/libx265). Using schu-video-generator as installed is unaffected, but redistributing a frozen or
  bundled application (PyInstaller and the like) that includes these wheels inherits their
  GPL/LGPL obligations.
- **fpdf2** (PDF slide decks) is under the **LGPL-3.0**.
- **Kokoro** (installed on Python 3.10-3.12, local narration): the `kokoro` and `misaki` packages by
  hexgrad are under the **Apache-2.0** licence; they pull in PyTorch (BSD-style), spaCy (MIT),
  phonemizer-fork (GPL-3.0) and `espeakng-loader`, whose wheels bundle the espeak-ng library and
  data (**GPL-3.0**). Using them as installed is unaffected; redistributing a bundled application
  that includes them inherits those licences.
- **Kokoro-82M model weights and voices** (`hexgrad/Kokoro-82M` on Hugging Face,
  `kokoro-v1_0.pth` and `voices/*.pt`): **Apache-2.0**, by hexgrad. They are **not bundled**:
  the `kokoro` package downloads them from Hugging Face on first use into the user's Hugging Face
  cache. The model card states that its training data was permissive / non-copyrighted audio
  (incl. CC BY audio from the Koniwa and SIWIS corpora, credited there); the licence sets no
  conditions on the audio you generate with it. schu-video-generator's bundled list of its voice names and grades
  (`vidgen/data/kokoro/voices.json`) is facts read from the model's repository on the date it names.

- **symusic** (composed music; https://github.com/Yikai-Liao/symusic),
  version 0.5.9: **MIT License**, © 2023 the symusic authors. Its SoundFont renderer is
  **Prestosynth** (https://github.com/lzqlzzq/prestosynth), compiled into symusic: **MIT
  License**, © 2024 the Prestosynth authors. symusic's wheels also bundle two command-line
  programs from the abcMIDI package, `abc2midi` and `midi2abc` (in `symusic/bin/`; their licence
  was not verified and is believed to be the GPL); schu-video-generator never runs them, and redistributing a
  bundled application that includes symusic's wheels should check their terms.
- **GeneralUser GS 2.0.3** (the SoundFont composed music is played with by default), by
  S. Christian Collins (https://www.schristiancollins.com/generaluser), **GeneralUser GS License
  v2.0**: it may
  be used "without restriction for your own music creation, private or commercial", the samples
  allow full use in music production including profit from the recordings, and no attribution is
  required. It is **not bundled**: schu-video-generator downloads it on first use from the author's GitHub
  repository (`mrbumpy409/GeneralUser-GS`, `GeneralUser-GS.sf2`, 32,319,396 bytes, SHA-256
  `9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe`) into vidgen's cache folder
  and checks it before use. The author asks that websites featuring it link to his website, not to
  his download files. Suggested courtesy credit for a video: "Music rendered with the GeneralUser
  GS SoundFont by S. Christian Collins (https://www.schristiancollins.com/generaluser)."

## Online services (optional, your own account)

schu-video-generator bundles no client library or content from these services; it calls their web APIs with
your key only when you run the paid commands, and what they return is subject to their terms:
ElevenLabs (narration, speech to text), OpenAI (Images API) and OpenRouter (image models of
several providers, e.g. Black Forest Labs, ByteDance, Google, OpenAI, Recraft, and
text-to-speech models, e.g. Mistral, Kokoro, Google, ElevenLabs, Microsoft — each model's
provider terms apply too). The list of OpenRouter's TTS models, voices and prices bundled for
offline checks (`vidgen/data/openrouter/tts_models.json`) is facts read from its public model
list on the date it names. Requests to OpenRouter carry schu-video-generator's optional app identification
(`HTTP-Referer`: the project's repository URL, `X-OpenRouter-Title`: `schu-video-generator`).

## Repository-only content (not in the pip package)

- **kphi3 narration** (`examples/kphi3/audio/*.mp3`): generated with ElevenLabs (premade voice
  "Brian", voice id `nPczCjzI2devNBz1zQrb`, model `eleven_multilingual_v2`) under the author's
  paid plan. These MP3s are **not** covered by the repository's MIT licence; they are provided
  only so the example can be rendered without an API key, and are not part of the pip package.
