"""The ``effect`` beat action (DESIGN.md §69.40): a symbol over a character's head (a sweat drop,
an anger mark, an idea bulb, a question or exclamation mark, sleepy Zs, hearts, dizzy stars, a
sparkle, a tear). Written against ``vidgen.api`` only, like project actions.

Each symbol is an :class:`EffectSymbol` of its own, never added to the character (a character's
parts never change, §69.22): it follows the head on every frame (walks, jumps, turns, shots), pops
in with a little bounce, keeps moving (a drip, a pulse, rising Zs...) and shrinks away when the
effect ends: at the next beat, or at its ``until`` beat. It is not graded by the stage's light (it
is not marked lit, like speech bubbles) and keeps clear of a speech bubble on screen; a bubble
drawn later keeps clear of it.
"""

from typing import Any, Literal

from vidgen.api import *

from .acting import _Acting, _characters


class EffectAppear(Animation):
    """Plays while a symbol pops in (``leave=False``) or shrinks away (``leave=True``, then removed
    from the scene): the symbol draws itself from its own updater, which keeps running."""

    def __init__(self, symbol: EffectSymbol, *, leave: bool = False, **kwargs: Any) -> None:
        super().__init__(symbol, suspend_mobject_updating=False, introducer=not leave, remover=leave, **kwargs)

    def create_starting_mobject(self) -> Mobject:
        """No copy of the symbol: nothing interpolates from it."""
        return Mobject()

    def interpolate_mobject(self, alpha: float) -> None:
        """Nothing: the symbol's updater draws it."""


def speech_bubble_boxes(scene: NarratedScene) -> list[tuple[float, float, float, float]]:
    """The boxes ``(left, bottom, right, top)`` of the speech bubbles on screen."""
    return [
        (float(m.get_left()[0]), float(m.get_bottom()[1]), float(m.get_right()[0]), float(m.get_top()[1]))
        for m in scene.mobjects if getattr(m, "speech_bubble_of", None) is not None
    ]


def show_symbol(scene: NarratedScene, character: Character, kind: str, color: Any) -> tuple[EffectSymbol, Animation]:
    """A symbol ``kind`` in ``color`` following ``character``'s head, in front of what is on
    screen (clear of the speech bubbles there), and the animation that pops it in."""
    symbol = EffectSymbol(kind, color=color, character_height=character.character_height)
    symbol.follow(character, avoid=speech_bubble_boxes(scene))
    top = max((m.z_index for m in scene.get_mobject_family_members()), default=0)
    symbol.set_z_index(top + 1)
    return symbol, EffectAppear(symbol)


def hide_symbol(symbol: EffectSymbol) -> Animation:
    """The animation that shrinks ``symbol`` away (removed from the scene at its end)."""
    symbol.leaving = symbol.age
    return EffectAppear(symbol, leave=True)


@action("effect")
class Effect(_Acting):
    """A symbol over the target character's head (``to``): sweat (a drop at the back of the head),
    anger (a mark on its top corner), idea (a bulb above it), question, exclaim (a mark above it),
    sleep (Zs rising in front), hearts (above), stars (circling the head), sparkle (in front) or
    tear (running down from the eye). It pops in, follows the character and lasts until the next
    beat starts (``until: <beat>``: until that beat starts). With foley a sound goes with most
    symbols (``sound: false``: none)."""

    class Options(ActionOptions):
        to: Literal[EFFECT_KINDS]
        """The symbol: sweat, anger, idea, question, exclaim, sleep, hearts, stars, sparkle or tear."""
        color: ThemeColor | None = None
        """Fill of the symbol (theme token or hex); default: the symbol's own (sweat, tear, sleep primary; anger, exclaim, hearts accent; idea, stars, sparkle highlight; question secondary)."""
        sound: bool = True
        """false: no sound for this symbol, even with foley on."""

    run_time = EFFECT_SECONDS
    reversible = True
    until_next_beat = True
    #: It draws over the character without changing it, so it plays with the character's other
    #: actions due with it (a react, a walk) instead of after them.
    alters_targets = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._target_characters(scene_cls, params)[1]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A symbol on each character, in front of what is on screen (under a later bubble)."""
        kind = self.options.to
        color = effect_color(kind, self.options.color, scene.theme.color)
        self.symbols: list[EffectSymbol] = []
        anims: list[Animation] = []
        for character in _characters(scene, targets, "effect"):
            symbol, appear = show_symbol(scene, character, kind, color)
            self.symbols.append(symbol)
            anims.append(appear)
        return anims

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Shrink the symbols away (removed from the scene at the end)."""
        anims = [hide_symbol(symbol) for symbol in getattr(self, "symbols", [])]
        self.symbols = []
        return anims
