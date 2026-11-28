<!-- topic: pacing (also: story, storytelling, text, narration, beats) -->
## Storytelling and pacing

**Structure.** Hook (0–5 s) → context (why it matters) → 3 to 5 ideas, one scene each →
recap → call to action. A video over 2 minutes gets **chapters** (`chapter` cards or a scene's
`chapter:` key; at least 3, each ≥ 10 s, so YouTube lists them) and a `progress_bar` overlay.

**The hook.** The first beat earns the next 30 seconds. Open on the most surprising fact, a
question the viewer wants answered, or the end result ("This chart took 4 seconds to make").
`stat`, `text_card` and a short `title` work; a silent intro card or a logo does not.

**Beats.** One beat = one thought the viewer hears while one thing happens on screen.
- 1–2 sentences, 6–15 words. schu-video-generator times beats from their word count until the audio exists
  (`narration.words_per_second`, 2.6), and lint's `narration_speed` expects 1.8–3.5 words/s
  (English; other languages have their own range).
- A beat over ~20 words is two beats: split it, and give each half its own reveal.
- Write for the ear: short words, active voice, no parentheses, no "e.g." or "i.e.", no
  "as you can see". Numbers as people say them ("about a third" beats "33.3%").
- Spell out what the voice should say only through `pronunciation:` (`vidgen guide audio`),
  so the subtitles keep the written form.

**A visual change every 3–6 s.** Every built-in scene reveals one step per beat (an item, a
bar, a node, an event). With short beats that gives a change every few seconds for free. A
long beat over a finished picture is dead air: split it, or add an action (`highlight`,
`callout`, `zoom`) in the middle (`at: 0.5`).

**On-screen text.**
- The screen carries **keywords**, the voice carries **sentences**. A bullet is a label
  ("Same accuracy"), not the sentence being spoken ("The model reaches the same accuracy").
- Never put the narration on screen verbatim (captions are the exception, and they are an
  overlay: `vidgen guide social`).
- Limits: title ≤ 7 words; heading ≤ 5; list items ≤ 6 words, ≤ 5 items; labels 1–3 words;
  ≤ ~20 words visible at once. More content → more scenes.
- Numbers on screen get a unit and a comparison (`stat` `comparison`, a chart `caption` with
  the source).

**Progressive reveal.** Item *i* appears at beat *i*, so the newest element is what the voice
talks about. Keep the default step-by-step reveal of lists, grids, timelines, diagrams and
processes; use
`dim_previous: true` on `bullets` for long lists; `groups` on `icon_grid` to bring related
items together. `reveal: all` only when the whole picture is the point (a chart's bars).

**Endings.** Recap the 3 takeaways in one scene (each a beat), then an `end_card` with one
call to action (a link, "try it", "subscribe"), narrated in one short beat.

