"""Step 136: voices with feeling, part 2 (``emotion:`` for ElevenLabs and OpenRouter, DESIGN.md §73).

Every request is mocked (``urllib.request.urlopen`` replaced by the fakes of ``test_tts`` and
``test_tts_openrouter``); the request bodies are checked. One OpenRouter test re-encodes a 1 s
tone with ffmpeg."""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_tts import FakeAPI
from test_tts import KEY as ELEVENLABS_KEY
from test_tts_openrouter import KEY as OPENROUTER_KEY
from test_tts_openrouter import MODEL, VOICE, FakeOpenRouter, make_audio
from vidgen import tts
from vidgen.cli import main, validate_warnings
from vidgen.config import EmotionConfig, VoiceConfig
from vidgen.emotions import EMOTION_NAMES, EMOTIONS, NAMED_CUES, named_cues, prosody
from vidgen.project import Project
from vidgen.readback import compare_beat
from vidgen.sfx import decode_audio
from vidgen.speech import audio_duration
from vidgen.stt import Transcript
from vidgen.tts.elevenlabs import ElevenLabsProvider
from vidgen.tts.openrouter import OpenRouterTTSProvider

PLAIN_ELEVENLABS_KEY = "e07179cc8214a9008a163a96e3ab594f0d3da455"   # pinned (Step 135): VoiceConfig(), "Hello there."
PLAIN_OPENROUTER_KEY = "ed12a9d42adbd729f424fb9c6b73f406f5b27aaa"   # pinned (Step 135): VOICE, "Hello there."
INSTRUCTED = {"provider": "openrouter", "model": "openai/gpt-4o-mini-tts", "voice": "alloy"}


@pytest.fixture
def eleven(monkeypatch: pytest.MonkeyPatch) -> FakeAPI:
    fake = FakeAPI()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setenv("ELEVENLABS_API_KEY", ELEVENLABS_KEY)
    return fake


@pytest.fixture
def routed(monkeypatch: pytest.MonkeyPatch) -> FakeOpenRouter:
    fake = FakeOpenRouter()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", OPENROUTER_KEY)
    return fake


def with_emotions(voice: dict[str, Any] | None = None, **emotions: Any) -> dict[str, Any]:
    """The minimal config with ``emotion`` set on the beats named (intro_b1, intro_b2, custom)."""
    data = minimal_config(voice=voice) if voice is not None else minimal_config()
    beats = {"intro_b1": data["scenes"][0]["beats"][0], "intro_b2": data["scenes"][0]["beats"][1], "custom": data["scenes"][1]["beats"][0]}
    for beat_id, emotion in emotions.items():
        beats[beat_id]["emotion"] = emotion
    return data


# ----- the table (pure) ---------------------------------------------------------------------------


def test_every_emotion_has_named_cues() -> None:
    assert set(NAMED_CUES) == set(EMOTION_NAMES) - {"neutral"}
    for cues in NAMED_CUES.values():
        assert cues.tag.startswith("[") and cues.tag.endswith("]") and " " not in cues.tag
        assert -0.5 <= cues.stability <= 0.5 and 0 <= cues.style <= 0.5 and cues.instruction.endswith(".")
    # strong feelings are less stable and more stylised than calm ones
    assert NAMED_CUES["shout"].stability < NAMED_CUES["happy"].stability < 0 < NAMED_CUES["calm"].stability
    assert named_cues(None) is None and named_cues(prosody(EmotionConfig(gain=3))) is None   # like: neutral
    assert named_cues(prosody(EmotionConfig(like="sad", pitch=-2))) == NAMED_CUES["sad"]   # the name counts


# ----- ElevenLabs: voice settings, or an audio tag on eleven_v3 -----------------------------------


def test_elevenlabs_settings_change_with_the_emotion(eleven: FakeAPI) -> None:
    plain = tts.get_provider(VoiceConfig())
    assert plain.cache_key("Hello there.") == PLAIN_ELEVENLABS_KEY
    assert tts.get_provider(VoiceConfig(), EMOTIONS["neutral"]).cache_key("Hello there.") == PLAIN_ELEVENLABS_KEY
    excited = tts.get_provider(VoiceConfig(), EMOTIONS["excited"])
    assert excited.cache_key("Hello there.") != PLAIN_ELEVENLABS_KEY
    assert excited.synthesize("Hello there.") == b"MP3:Hello there."   # the text is not changed
    calm = ElevenLabsProvider(VoiceConfig(settings={"stability": 0.9, "style": 0.1}), emotion=EMOTIONS["calm"])
    calm.synthesize("Easy now.")
    shout = ElevenLabsProvider(VoiceConfig(settings={"stability": 0.2}), emotion=EMOTIONS["shout"])
    shout.synthesize("Run!")
    settings = [eleven.body(i)["voice_settings"] for i in range(3)]
    assert settings[0] == {"stability": 0.3, "similarity_boost": 0.75, "style": 0.45, "use_speaker_boost": True}
    assert (settings[1]["stability"], settings[1]["style"]) == (1.0, 0.1)   # kept in 0-1
    assert (settings[2]["stability"], settings[2]["style"]) == (0.0, 0.5)
    assert eleven.texts() == ["Hello there.", "Easy now.", "Run!"]
    # only the name counts here: numbers changed from a row give the same settings and hash
    tweaked = tts.get_provider(VoiceConfig(), prosody(EmotionConfig(like="excited", pitch=1)))
    assert tweaked.cache_key("Hi") == excited.cache_key("Hi")


def test_eleven_v3_gets_the_audio_tag_before_the_line(make_project, eleven: FakeAPI, capsys: pytest.CaptureFixture[str]) -> None:
    v3 = {"model_id": "eleven_v3", "context": False}
    root = make_project(with_emotions(v3, intro_b1="excited", custom={"like": "whisper", "gain": -6}))
    project = Project.load(root)
    spoken = project.spoken(project.beat("intro_b1"))
    assert (spoken.text, spoken.spoken) == ("Hello there.", "[excited] Hello there.")
    assert project.spoken(project.beat("intro_b2")).spoken == "Second beat."
    assert main(["tts", str(root)]) == 0
    assert eleven.texts() == ["[excited] Hello there.", "Second beat.", "[whispers] One two three four."]
    assert {str(eleven.body(i)["voice_settings"]) for i in range(3)} == {str(VoiceConfig().settings.model_dump())}   # v3: the tag only
    # a beat without an emotion keeps its hash; the tagged ones are up to date after the run
    assert (root / "audio" / "intro_b2.hash").read_text(encoding="utf-8") == tts.get_provider(VoiceConfig(**v3)).cache_key("Second beat.")
    assert {s.state for s in tts.audio_status(Project.load(root))} == {"ok"}
    capsys.readouterr()
    # other models never get the tag in their text
    other = Project.load(make_project(with_emotions(intro_b1="excited"), folder="v2"))
    assert other.spoken(other.beat("intro_b1")).spoken == "Hello there."


def test_eleven_v3_tag_comes_before_a_voice_sound_and_readback_ignores_tags(make_project) -> None:
    data = with_emotions({"model_id": "eleven_v3"}, intro_b1="sad")
    data["scenes"][0]["beats"][0]["text"] = "[sigh] Hello there."
    project = Project.load(make_project(data))
    spoken = project.spoken(project.beat("intro_b1"))
    assert spoken.spoken == "[sad] [sighs] Hello there." and spoken.text == "Hello there."
    report = compare_beat("intro", "intro_b1", spoken, Transcript("Hello there."))
    assert report.edits == [] and report.words == 2


def test_beat_providers_per_emotion_for_elevenlabs(make_project) -> None:
    project = Project.load(make_project(with_emotions(intro_b1="sad")))
    providers = tts.beat_providers(project)
    assert providers["intro_b1"] is not providers["intro_b2"] and providers["intro_b2"] is providers["custom"]
    assert providers["intro_b2"].cache_key("Hello there.") == PLAIN_ELEVENLABS_KEY
    assert providers["intro_b1"].cache_key("Hello there.") != PLAIN_ELEVENLABS_KEY


# ----- OpenRouter: instructions, or the audio changed afterwards -----------------------------------


def test_openrouter_instructions_carry_the_emotion(routed: FakeOpenRouter) -> None:
    plain = OpenRouterTTSProvider(VoiceConfig(**INSTRUCTED, instructions="Warm narrator"))
    sad = OpenRouterTTSProvider(VoiceConfig(**INSTRUCTED, instructions="Warm narrator"), emotion=EMOTIONS["sad"])
    bare = OpenRouterTTSProvider(VoiceConfig(**INSTRUCTED), emotion=EMOTIONS["whisper"])
    for provider in (plain, sad, bare):
        provider.synthesize("Hello there.")
    bodies = routed.bodies()
    assert bodies[0]["instructions"] == "Warm narrator"
    assert bodies[1]["instructions"] == f"Warm narrator. {NAMED_CUES['sad'].instruction}"
    assert bodies[2]["instructions"] == NAMED_CUES["whisper"].instruction
    assert [b["input"] for b in bodies] == ["Hello there."] * 3   # the text is not changed
    assert plain.spec()["instructions"] == sad.spec()["instructions"] == "Warm narrator"
    assert sad.spec()["emotion"] == {"name": "sad", "instruction": NAMED_CUES["sad"].instruction}
    assert sad.cache_key("Hi") != plain.cache_key("Hi")
    # the audio is as sent (no post-processing) and the numbers of a row change nothing here
    tweaked = OpenRouterTTSProvider(VoiceConfig(**INSTRUCTED, instructions="Warm narrator"), emotion=prosody(EmotionConfig(like="sad", pitch=-3)))
    assert tweaked.cache_key("Hi") == sad.cache_key("Hi")
    neutral = OpenRouterTTSProvider(VoiceConfig(**INSTRUCTED), emotion=prosody(EmotionConfig(gain=3)))
    assert neutral.emotion is None and neutral.instructions is None


def test_openrouter_without_instructions_changes_the_audio(routed: FakeOpenRouter, tmp_path: Path) -> None:
    assert tts.get_provider(VoiceConfig(**VOICE)).cache_key("Hello there.") == PLAIN_OPENROUTER_KEY
    pauses_only = tts.get_provider(VoiceConfig(**VOICE), prosody(EmotionConfig(pauses=1.5)))
    assert pauses_only.cache_key("Hello there.") == PLAIN_OPENROUTER_KEY   # nothing it can change
    tone = make_audio("mp3", 1.0)
    routed.speech = [tone, tone]
    plain = tts.get_provider(VoiceConfig(**VOICE)).synthesize("Hello there.")
    sad = tts.get_provider(VoiceConfig(**VOICE, instructions="calm"), EMOTIONS["sad"])
    changed = sad.synthesize("Hello there.")
    assert plain == tone
    assert routed.bodies()[1]["instructions"] == "calm"   # the voice's own, unchanged
    assert sad.spec()["emotion"] == {"name": "sad", "speed": 0.86, "pitch": -1.5, "gain": -3.0}
    (tmp_path / "plain.mp3").write_bytes(plain)
    (tmp_path / "sad.mp3").write_bytes(changed)
    seconds = audio_duration(tmp_path / "plain.mp3"), audio_duration(tmp_path / "sad.mp3")
    assert seconds[1] == pytest.approx(seconds[0] / 0.86, rel=0.06)   # slower
    rms = [float(np.sqrt(np.mean(decode_audio(tmp_path / f"{n}.mp3", mono=True) ** 2))) for n in ("plain", "sad")]
    assert 20 * np.log10(rms[1] / rms[0]) == pytest.approx(-3.0, abs=0.7)   # 3 dB quieter


# ----- validate -----------------------------------------------------------------------------------


def test_validate_warns_only_about_what_is_not_spoken(make_project) -> None:
    named = Project.load(make_project(with_emotions(intro_b1="sad", custom="excited")))
    assert tts.emotion_warnings(named) == []
    tweaked = Project.load(make_project(with_emotions(intro_b1={"like": "sad", "pitch": -2}, custom={"gain": 3}), folder="t"))
    warning = (
        "emotion: ElevenLabs voices and OpenRouter models with instructions speak an emotion by its name only; "
        "the numbers given for intro_b1, custom are ignored (Kokoro uses them)"
    )
    assert warning in validate_warnings(tweaked)
    plain_model = Project.load(make_project(with_emotions(dict(VOICE), intro_b2="sad"), folder="o"))
    assert tts.emotion_warnings(plain_model) == [
        f"emotion: {MODEL} takes no instructions, so the emotion of intro_b2 changes only the speed, pitch and loudness "
        "of the audio, not its tone or pauses"
    ]
    assert tts.emotion_warnings(Project.load(make_project(with_emotions(dict(INSTRUCTED), intro_b2="sad"), folder="i"))) == []
