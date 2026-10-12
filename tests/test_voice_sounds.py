"""Step 99: non-speech voice sounds (``[gasp]``, ``[laugh]``...): marker parsing, what each
provider says (and pinned hashes of beats without markers), sound times, the viseme track around
a marker, captions / SRT / readback without markers, the screenplay rule, the speaker's face, and
one tiny render (generated breaths on the SFX track, a laugh's expression)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_cartoon_acting import CAST, VOICES, acting_project
from test_cartoon_stage import render_with_layout
from vidgen import extensions, sfx
from vidgen.cartoon.directing import project_directions
from vidgen.cartoon.visemes import REST, VisemeCue, VisemeTrack, beat_visemes, with_cues
from vidgen.config import BeatConfig, VoiceConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.voicesounds import (
    SOUND_GAIN_DB,
    VOICE_SOUNDS,
    VoiceSound,
    beat_sound_spans,
    is_voice_sound,
    sound_voicing,
    take_out_sounds,
)

# ----- markers (no manim) -------------------------------------------------------------------------


def test_markers_leave_the_text() -> None:
    cases = {
        "Oh no [gasp] it fell.": ("Oh no it fell.", [("gasp", 2)]),
        "[Laughs] That is funny.": ("That is funny.", [("laugh", 0)]),
        "Fine. [sigh]": ("Fine.", [("sigh", 1)]),
        "Wait [gasp], what?": ("Wait, what?", [("gasp", 1)]),
        "Hmm[hmm]ok": ("Hmm ok", [("hmm", 1)]),
        "Hello [cough] there [wave].": ("Hello [cough] there [wave].", []),   # other brackets stay
    }
    for written, (text, sounds) in cases.items():
        assert take_out_sounds(written) == (text, tuple(VoiceSound(k, w) for k, w in sounds)), written
    beat = BeatConfig(id="b", text="[giggle] You said *that*? [groans]")
    assert beat.text == "You said that?" and beat.marked_text == "You said *that*?"   # same words
    assert beat.voice_sounds == (VoiceSound("giggle", 0), VoiceSound("groan", 3))
    assert beat.model_copy(update={"actions": []}).voice_sounds == beat.voice_sounds   # with_auto_actions copies beats
    assert BeatConfig(id="b", text="Hello there.").voice_sounds == ()
    with pytest.raises(ValueError, match="only voice sounds"):
        BeatConfig(id="b", text="[laugh] [sigh]")
    assert is_voice_sound("laughs") and is_voice_sound(" Gasp ") and not is_voice_sound("cough")


def test_each_provider_says_the_sounds() -> None:
    kokoro, v2, v3 = VoiceConfig(provider="kokoro"), VoiceConfig(), VoiceConfig(model_id="eleven_v3")
    openrouter = VoiceConfig(provider="openrouter", model="some/tts")
    for voice in (kokoro, v2, openrouter):
        assert sound_voicing(voice, VoiceSound("laugh", 0), 3) == "Ha ha ha!"
        assert sound_voicing(voice, VoiceSound("hmm", 3), 3) == "Hmm."
        assert sound_voicing(voice, VoiceSound("gasp", 0), 3) is None   # a breath: generated before the line
        assert sound_voicing(voice, VoiceSound("sigh", 3), 3) is None   # ... or after it
        assert sound_voicing(voice, VoiceSound("gasp", 1), 3) == "Hah!"   # inside the line: no silence to fill
    assert sound_voicing(v3, VoiceSound("gasp", 0), 3) == "[gasps]" and sound_voicing(v3, VoiceSound("laugh", 2), 3) == "[laughs]"
    assert sound_voicing(v3, VoiceSound("hmm", 2), 3) == "Hmm."
    assert {k.sfx for k in VOICE_SOUNDS.values()} - {None} == {"gasp", "sigh"}
    for name in ("gasp", "sigh"):
        samples = sfx.synthesize(name)
        assert len(samples) == round(sfx.BUILTIN_SOUNDS[name].duration * sfx.RATE)
        assert sfx.loudness(samples) == pytest.approx(sfx.LOUDNESS_TARGET, abs=0.5) and samples[0] == samples[-1] == 0.0


def sounds_project(make_project, voice: dict[str, Any] | None = None, pronunciation: dict[str, str] | None = None, folder: str = "proj") -> Project:
    beats = [
        {"id": "plain", "text": "Hello there."},
        {"id": "laugh", "text": "[laugh] That is funny."},
        {"id": "mid", "text": "Oh no [gasp] it fell."},
        {"id": "edges", "text": "[gasp] Oh no. [sighs]"},
    ]
    config = minimal_config(scenes=[{"id": "intro", "type": "text_card", "params": {"text": "Hi"}, "beats": beats}])
    if voice is not None:
        config["voice"] = voice
    if pronunciation is not None:
        config["pronunciation"] = pronunciation
    return Project.load(make_project(config, folder=folder))


def test_spoken_texts_and_pinned_hashes(make_project) -> None:
    """What the TTS gets per provider; a beat without markers keeps its cache key (pinned in
    Step 91), a generated breath at the line's edges leaves the audio (and its hash) alone."""
    from vidgen import tts

    project = sounds_project(make_project, {"provider": "kokoro"})
    spoken = project.spoken_texts()
    assert spoken == {
        "plain": "Hello there.", "laugh": "Ha ha ha! That is funny.", "mid": "Oh no Hah! it fell.", "edges": "Oh no.",
    }
    kokoro = tts.get_provider(VoiceConfig(provider="kokoro"))
    assert kokoro.cache_key(spoken["plain"]) == "05cb88daec48cc27a4841b20f737de3c7cb847c4"
    assert tts.get_provider(VoiceConfig()).cache_key("Hello there.") == "e07179cc8214a9008a163a96e3ab594f0d3da455"
    assert kokoro.cache_key(spoken["edges"]) == kokoro.cache_key("Oh no.")
    v3 = sounds_project(make_project, {"model_id": "eleven_v3"}, folder="v3").spoken_texts()
    assert v3["laugh"] == "[laughs] That is funny." and v3["edges"] == "[gasps] Oh no. [sighs]" and v3["plain"] == "Hello there."

    # pronunciation rules apply to the written words only, never to a sound's words
    said = sounds_project(make_project, {"provider": "kokoro"}, {"funny": "fun knee", "ha": "hah hah"}, folder="pr")
    laugh = said.spoken(said.beat("laugh"))
    assert laugh.spoken == "Ha ha ha! That is fun knee." and laugh.text == "That is funny."
    assert laugh.word_groups() == [[3], [4], [5, 6]]   # "Ha ha ha!" belongs to no written word


def test_sound_times_and_the_mouth_around_them(make_project) -> None:
    project = sounds_project(make_project)   # no MP3s: estimated word times
    with_sound = beat_sound_spans(project, project.beat("mid"), 2.0)
    assert [(s.kind, s.word, s.generated) for s in with_sound] == [("gasp", 2, False)]
    gasp = with_sound[0]
    assert 0.0 < gasp.start < gasp.end < 2.0   # said "Hah!" between "no" and "it"
    mid = beat_visemes(project, "mid", 2.0)
    assert any(c.viseme != REST for c in mid.cues if gasp.start <= c.start < gasp.end)   # the mouth says it

    edges = beat_sound_spans(project, project.beat("edges"), 1.0)
    assert [(s.kind, s.generated) for s in edges] == [("gasp", True), ("sigh", True)]
    before, after = edges
    assert before.end < 0.0 and before.end - before.start == pytest.approx(sfx.BUILTIN_SOUNDS["gasp"].duration)
    assert after.start > 0.9 and after.end - after.start == pytest.approx(sfx.BUILTIN_SOUNDS["sigh"].duration)
    track = beat_visemes(project, "edges", 1.0)
    assert track.at(after.start + 0.1) == VOICE_SOUNDS["sigh"].viseme and track.duration == pytest.approx(after.end)
    assert beat_visemes(project, "plain", 1.0) == beat_visemes(project, "plain", 1.0)   # unchanged path

    laid = with_cues(VisemeTrack((VisemeCue(0.0, 0.5, "A"), VisemeCue(0.5, 1.0, "E"))), [(0.4, 0.6, "O"), (1.2, 1.5, "A")])
    assert laid.cues == (VisemeCue(0.0, 0.4, "A"), VisemeCue(0.4, 0.6, "O"), VisemeCue(0.6, 1.0, "E"), VisemeCue(1.0, 1.2, REST), VisemeCue(1.2, 1.5, "A"))


def test_captions_srt_and_readback_leave_the_sounds_out(make_project) -> None:
    from vidgen.readback import compare_beat
    from vidgen.speech import beat_word_times
    from vidgen.stt import Transcript
    from vidgen.subtitles import cues_from_timings
    from vidgen.voicesounds import heard_sound_words

    project = sounds_project(make_project)
    timings = {"scenes": [{"beats": [{"id": "laugh", "text": "That is funny.", "start": 0.0, "end": 2.0}]}]}
    spoken = {"laugh": project.spoken(project.beat("laugh"))}
    cues = cues_from_timings(timings, project.audio_dir, project.pronunciation, spoken=spoken)
    assert [c.text for c in cues] == ["That is funny."]
    beat = project.beat("laugh")
    words = beat_word_times(project.audio_dir, "laugh", beat.text, 0.0, 2.0, spoken["laugh"])
    assert [w.text for w in words] == ["That", "is", "funny."] and words[0].start > 0.5   # after the laugh
    heard = Transcript("Ha ha ha, that is funny.")
    said = project.pronunciation.apply(beat.text)
    assert compare_beat("intro", "laugh", said, heard, skip_heard=heard_sound_words(beat.voice_sounds)).edits == []
    assert compare_beat("intro", "laugh", said, heard).edits   # without the skip: extra words heard
    no = Transcript("Ha, no.")
    kept = compare_beat("intro", "x", project.pronunciation.apply("Ha, no."), no, skip_heard=frozenset({"ha"}))
    assert kept.edits == []   # a word the text says is never skipped


def test_screenplay_keeps_sound_markers_in_the_line() -> None:
    from vidgen.screenplay import parse_screenplay

    play = parse_screenplay("# Scene: yard\n\nKIT: Oh no [gasp] [Kit jumps] it fell! [laughs]\n\n[Pip sighs]\n\nPIP: Fine.\n")
    line, direction, _ = play.scenes[0].items
    assert line.text == "Oh no [gasp] it fell! [laughs]" and [d.text for d in line.directions] == ["Kit jumps"]
    assert direction.text == "Pip sighs"   # a direction on its own line stays one
    with pytest.raises(VidgenError, match="has nothing to say"):
        parse_screenplay("KIT: [laugh]\n")


def test_speakers_get_the_sound_s_face(make_project) -> None:
    project = acting_project(make_project, [
        {"text": "Oh no [gasp] it fell.", "voice": "pip_voice"},
        {"text": "[laugh] It is fine.", "voice": "kit_voice", "actions": [{"emote": "kit", "to": "sad"}]},   # the beat sets one
        {"text": "[hmm] Who knows.", "voice": "kit_voice"},
        {"text": "And so it ends."},
    ])
    with extensions.project_session(project):
        added = {d.beat: [a.shorthand() for a in d.actions] for d in project_directions(project).get("park", [])}
    assert set(added) == {"park_b1", "park_b3"}
    (react,) = added["park_b1"]
    assert react["react"] == "pip" and react["expression"] == "surprised" and 0.2 < react["at"] < 0.8
    assert added["park_b3"] == [{"react": "kit", "expression": "thinking"}]


# ----- render --------------------------------------------------------------------------------------


@pytest.mark.render
def test_breaths_play_and_laughs_show(make_project, tmp_path: Path) -> None:
    project = acting_project(make_project, [
        {"text": "Look at this.", "voice": "pip_voice"},
        {"text": "[gasp] Oh no! [sigh]", "voice": "kit_voice"},
        {"text": "[laugh] That is funny.", "voice": "pip_voice"},
    ])
    scene, _ = render_with_layout(project, "park", tmp_path / "media")
    starts = {t.beat_id: t.start for t in scene.beat_log}
    voiced = [(e.sound, e.beat, e.time, e.gain) for e in scene.sfx_log if e.sound in ("gasp", "sigh")]
    assert [(s, b, g) for s, b, _, g in voiced] == [("gasp", "park_b2", SOUND_GAIN_DB), ("sigh", "park_b2", SOUND_GAIN_DB)]
    assert voiced[0][2] < starts["park_b2"] < voiced[1][2]   # just before the line, then after it
    pip = scene.cast["pip"]
    assert pip.state().parts["mouth"] == pip.posed_state(expression="happy").parts["mouth"]   # still laughing (last beat)
