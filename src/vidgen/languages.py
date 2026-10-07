"""Languages of a video (DESIGN.md §54): BCP-47 tags and the per-language rules that depend on them.

A video's ``language:`` (``en``, ``pt-BR``...; top level or per variant) chooses:

- how captions and the SRT cut a beat into cues (:mod:`vidgen.cues`): the words a phrase starts
  with (conjunctions, prepositions) and the words that lean on the next one (articles,
  prepositions) are listed per language for English, Portuguese, Spanish, French, German and
  Italian; any other language is cut at punctuation only (a neutral rule set);
- how word times are estimated (:func:`vidgen.speech.syllables`: a silent final ``e`` only in
  English and French);
- the narration speed ``vidgen lint`` accepts (words per second per language, or characters per
  second for languages without a word range);
- the ``language_code`` sent to ElevenLabs for models that accept one;
- the language tag of the final MP4's audio stream (ISO 639-2).

A video without ``language:`` follows the English rules (what vidgen did before languages
existed) and sends no language to the TTS. No manim import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A BCP-47 language tag as accepted in the config: a 2-3 letter language, then subtags
#: (script, region, variants) separated by ``-`` (``pt-BR``, ``zh-Hant-TW``, ``en``).
LANGUAGE_TAG_PATTERN = r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8})*$"
_TAG = re.compile(LANGUAGE_TAG_PATTERN)

#: ElevenLabs models that accept a ``language_code`` (ISO 639-1); for others the API returns an
#: error when one is sent, so ``voice.language_code`` (auto) sends it only to these.
LANGUAGE_CODE_MODELS: frozenset[str] = frozenset({"eleven_turbo_v2_5", "eleven_flash_v2_5"})

#: Characters (letters and digits) per second of speech accepted by ``narration_speed`` for a
#: language without a words-per-second range (about 1.8-3.5 words of 4.5-5 letters).
CHARACTER_RATE: tuple[float, float] = (8.0, 17.0)


def normalize_language(tag: str) -> str:
    """``tag`` in the usual case: language lower case, a 4-letter script title case, a 2-letter
    region upper case (``PT-br`` → ``pt-BR``). Raises ``ValueError`` for a malformed tag."""
    if not _TAG.match(tag):
        raise ValueError(f"{tag!r} is not a language tag (BCP-47, e.g. en, pt-BR, es-419, zh-Hant)")
    parts = tag.split("-")
    out = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 4 and part.isalpha():
            out.append(part.title())
        elif len(part) == 2 and part.isalpha():
            out.append(part.upper())
        else:
            out.append(part.lower() if part.isalpha() else part)
    return "-".join(out)


def primary_language(tag: str | None) -> str:
    """The language subtag of ``tag`` in lower case (``pt-BR`` → ``pt``); ``en`` for ``None``
    (a video without ``language:`` follows the English rules)."""
    return "en" if tag is None else tag.split("-")[0].lower()


def language_matches(entry: str, video: str | None) -> bool:
    """Whether a rule for language ``entry`` applies to a video in ``video``: the same language
    with every subtag ``entry`` gives (``pt`` matches ``pt-BR`` and ``pt-PT``; ``pt-BR`` only
    ``pt-BR``). A video without a language is English."""
    have = (video or "en").lower().split("-")
    want = entry.lower().split("-")
    return have[: len(want)] == want


@dataclass(frozen=True)
class LanguageRules:
    """What vidgen knows of a language: ``name`` (for messages), the words a phrase starts with
    (``conjunctions``, ``prepositions``: a cue may begin there), the words that lean on the next
    one (``clinging``: a cue should not end there), the narration speed range in words per second
    (``None``: measured in characters per second), whether a final ``e`` is silent, the ISO
    639-2 code of the MP4 audio tag (``None``: none written) and the ``abbreviations`` whose
    period does not end a sentence (lower case, without the final period: ``e.g``, ``dr``;
    used by :func:`vidgen.prose.split_sentences`)."""

    code: str
    name: str
    conjunctions: frozenset[str] = frozenset()
    prepositions: frozenset[str] = frozenset()
    clinging: frozenset[str] = frozenset()
    words_per_second: tuple[float, float] | None = None
    silent_final_e: bool = False
    iso639_2: str | None = None
    abbreviations: frozenset[str] = frozenset()

    @property
    def known(self) -> bool:
        """True when vidgen has word lists for the language (else only punctuation counts)."""
        return bool(self.clinging)


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


_RULES: dict[str, LanguageRules] = {
    "en": LanguageRules(
        "en",
        "English",
        _words("and but or nor so yet because which that who whom whose when where while if then although though unless until since whereas"),
        _words("of in on at to for with from by into onto over under about than as like after before between through during without"),
        _words("a an the of in on at to for with from by into onto my your his her its our their this that these those is are was were be very not no"),
        (1.8, 3.5),
        True,
        "eng",
        _words(
            "mr mrs ms dr prof sr jr st vs etc e.g i.e cf fig no nos approx dept est inc ltd co corp jan feb mar apr jun "
            "jul aug sep sept oct nov dec a.m p.m u.s u.k ph.d vol eq al"
        ),
    ),
    "pt": LanguageRules(
        "pt",
        "Portuguese",
        _words("e mas ou nem porque pois que quando enquanto se embora porém contudo todavia então portanto como onde quem cujo cuja conforme caso"),
        _words("de do da dos das em no na nos nas por pelo pela pelos pelas para com sem sobre sob entre até após desde contra perante a ao aos à às num numa"),
        _words(
            "o a os as um uma uns umas de do da dos das em no na nos nas por pelo pela pelos pelas para com sem sobre sob entre até "
            "ao aos à às num numa meu minha meus minhas seu sua seus suas nosso nossa este esta estes estas esse essa esses essas "
            "aquele aquela isto isso é são foi era muito não mais"
        ),
        (1.7, 3.4),
        False,
        "por",
        _words("sr sra srta dr dra prof profa etc ex p.ex pág págs nº n.º vs av ltda cia aprox obs tel fig cap séc e.g i.e eq al"),
    ),
    "es": LanguageRules(
        "es",
        "Spanish",
        _words("y e o u ni pero sino porque pues que cuando mientras si aunque como donde quien cuyo cuya entonces luego"),
        _words("de del en por para con sin sobre bajo entre hasta desde hacia contra según tras a al ante"),
        _words(
            "el la los las un una unos unas lo de del en por para con sin sobre bajo entre hasta desde hacia a al mi tu su mis "
            "tus sus nuestro nuestra este esta estos estas ese esa esos esas aquel aquella es son fue era muy no más"
        ),
        (1.8, 3.6),
        False,
        "spa",
        _words("sr sra srta dr dra prof etc ej p.ej pág núm vs av ud uds aprox cía fig"),
    ),
    "fr": LanguageRules(
        "fr",
        "French",
        _words("et mais ou ni car donc or que qui quand lorsque pendant si comme où dont puisque parce"),
        _words("de du des en dans par pour avec sans sur sous entre jusqu depuis vers chez contre selon après avant à au aux"),
        _words(
            "le la les un une des du de au aux à en dans par pour avec sans sur sous entre vers chez mon ma mes ton ta tes son sa "
            "ses notre votre leur leurs ce cet cette ces est sont était très ne pas plus"
        ),
        (1.8, 3.6),
        True,
        "fra",
        _words("m mme mlle dr pr etc ex p.ex cf vs av env fig"),
    ),
    "de": LanguageRules(
        "de",
        "German",
        _words("und aber oder denn sondern weil dass wenn als ob obwohl während damit sodass bevor nachdem"),
        _words("von vom in im an am auf aus bei mit nach seit zu zum zur für durch gegen ohne um über unter vor hinter neben zwischen"),
        _words(
            "der die das den dem des ein eine einen einem einer eines von vom in im an am auf aus bei mit nach seit zu zum zur für "
            "durch gegen ohne um über unter vor hinter neben zwischen mein meine dein sein seine ihr ihre unser unsere dieser diese "
            "dieses ist sind war sehr nicht kein keine"
        ),
        (1.5, 3.1),
        False,
        "deu",
        _words("hr fr dr prof bzw ca usw z.b d.h u.a evtl ggf nr vs str abb"),
    ),
    "it": LanguageRules(
        "it",
        "Italian",
        _words("e ed o od ma né perché poiché che quando mentre se sebbene benché come dove chi cui allora quindi"),
        _words("di del della dei degli delle a al alla ai agli alle da dal dalla in nel nella nei con su sul sulla per tra fra"),
        _words(
            "il lo la i gli le un uno una di del della dei degli delle a al alla ai agli alle da dal dalla in nel nella nei con su "
            "sul sulla per tra fra mio mia suo sua nostro questo questa quello quella è sono era molto non più"
        ),
        (1.8, 3.5),
        False,
        "ita",
        _words("sig sig.ra dott prof ecc es p.es vs ca pag fig"),
    ),
}

#: ISO 639-2 (bibliographic-free, "T") codes of languages without their own rules, for the MP4 tag.
_ISO639_2: dict[str, str] = {
    "ar": "ara", "bg": "bul", "ca": "cat", "cs": "ces", "da": "dan", "el": "ell", "fi": "fin", "he": "heb",
    "hi": "hin", "hr": "hrv", "hu": "hun", "id": "ind", "ja": "jpn", "ko": "kor", "ms": "msa", "nb": "nob",
    "nl": "nld", "no": "nor", "pl": "pol", "ro": "ron", "ru": "rus", "sk": "slk", "sv": "swe", "ta": "tam",
    "th": "tha", "tr": "tur", "uk": "ukr", "vi": "vie", "zh": "zho",
}


def language_rules(tag: str | None) -> LanguageRules:
    """The rules for language ``tag`` (English for ``None``); a language without word lists gets
    a neutral set: cues cut at punctuation only, narration speed in characters per second."""
    code = primary_language(tag)
    rules = _RULES.get(code)
    if rules is not None:
        return rules
    iso = _ISO639_2.get(code, code if len(code) == 3 else None)
    return LanguageRules(code, tag or code, iso639_2=iso)


def known_languages() -> list[str]:
    """Language subtags with word lists (``en``, ``pt``...)."""
    return list(_RULES)


def elevenlabs_language_code(setting: str | bool | None, model_id: str, language: str | None) -> str | None:
    """The ``language_code`` to send to ElevenLabs: ``setting`` when it is a code, nothing for
    ``false``; for ``None`` (auto) the video ``language``'s ISO 639-1 subtag when the model is one
    of :data:`LANGUAGE_CODE_MODELS` (other models reject the field)."""
    if isinstance(setting, str):
        return setting.lower()
    if setting is False or language is None or model_id not in LANGUAGE_CODE_MODELS:
        return None
    code = primary_language(language)
    return code if len(code) == 2 else None
