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

vidgen bundles icons from **Lucide** (https://lucide.dev) as package data in
`src/vidgen/data/icons/lucide/` (the SVG files unmodified, each keeps its `@license` comment),
obtained from the npm package `lucide-static` 1.52.0. Lucide is under the **ISC License**,
© Lucide Icons and Contributors; the icons Lucide derived from Feather are also under the
**MIT License**, © 2013-present Cole Bemis. Both licence texts, and the list of the
Feather-derived icons, are in `src/vidgen/data/icons/lucide/LICENSE`. The icon names, categories,
search tags and aliases are in `src/vidgen/data/icons/manifest.json` (tags from Lucide's
`tags.json` plus some added by vidgen; aliases are Lucide's old names of renamed icons plus a few
vidgen synonyms); `tools/vendor_icons.py` re-creates the folder (200 icons) and the catalogue
`docs/ICONS.md` from `tools/icon_set.json`.

## World map

The `map` scene draws countries from `src/vidgen/data/geo/world-110m.json`, made by
`tools/make_world_map.py` from:

- **Natural Earth** 1:110m Cultural Vectors, Admin 0 – Countries (https://www.naturalearthdata.com).
  Natural Earth data is in the **public domain**; no permission is needed to use, modify or
  redistribute it. "Made with Natural Earth" is appreciated. Country borders are Natural Earth's
  *de facto* representation; vidgen takes no position on disputed boundaries.
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

## Sound effects and music beds

The built-in sound effects and the three music beds are synthesised by vidgen's own code (no
recordings or samples); they are free to use in your videos, including commercially, with no
attribution needed.

## Dependencies (not bundled)

schu-video-generator's dependencies are installed by pip, not shipped in this package, and keep
their own licences. Notably:

- **PyAV** (`av`): its binary wheels bundle FFmpeg builds that include GPL/LGPL components
  (e.g. libx264/libx265). Using vidgen as installed is unaffected, but redistributing a frozen or
  bundled application (PyInstaller and the like) that includes these wheels inherits their
  GPL/LGPL obligations.
- **fpdf2** (optional `pdf` extra, PDF slide decks) is under the **LGPL-3.0**.

## Online services (optional, your own account)

vidgen bundles no client library or content from these services; it calls their web APIs with
your key only when you run the paid commands, and what they return is subject to their terms:
ElevenLabs (narration, speech to text), OpenAI (Images API) and OpenRouter (image models of
several providers, e.g. Black Forest Labs, ByteDance, Google, OpenAI, Recraft, and
text-to-speech models, e.g. Mistral, Kokoro, Google, ElevenLabs, Microsoft — each model's
provider terms apply too). The list of OpenRouter's TTS models, voices and prices bundled for
offline checks (`vidgen/data/openrouter/tts_models.json`) is facts read from its public model
list on the date it names. Requests to OpenRouter carry vidgen's optional app identification
(`HTTP-Referer`: the project's repository URL, `X-OpenRouter-Title`: `schu-video-generator`).

## Repository-only content (not in the pip package)

- **kphi3 narration** (`examples/kphi3/audio/*.mp3`): generated with ElevenLabs (premade voice
  "Brian", voice id `nPczCjzI2devNBz1zQrb`, model `eleven_multilingual_v2`) under the author's
  paid plan. These MP3s are **not** covered by the repository's MIT licence; they are provided
  only so the example can be rendered without an API key, and are not part of the pip package.
