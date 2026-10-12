from collections import deque
from itertools import groupby

from audio2score.rhythm.quantize import QNote

SPLIT = 60  # mittleres C
HYSTERESIS = 5
MAX_SPAN = 14  # Halbtöne, die eine Hand in einer Gruppe höchstens greift
HISTORY = 8  # so viele zuletzt gespielte Noten zählen für den gleitenden Mittelwert


def _order(note: QNote) -> tuple[int, int]:
    return note.start, note.pitch


def _span(pitches: list[int]) -> int:
    return max(pitches) - min(pitches) if pitches else 0


def _choose(pitch: int, right: deque, left: deque) -> bool:
    """True = rechte Hand."""
    if pitch >= SPLIT + HYSTERESIS:
        return True
    if pitch <= SPLIT - HYSTERESIS:
        return False
    if right and left:
        d_right = abs(pitch - sum(right) / len(right))
        d_left = abs(pitch - sum(left) / len(left))
        if d_right != d_left:
            return d_right < d_left
    return pitch >= SPLIT


def _limit_span(right: list[QNote], left: list[QNote]) -> None:
    """Hält die Spannweite jeder Hand: die mittelnächste Note wandert zur anderen Hand."""
    while _span([n.pitch for n in right]) > MAX_SPAN:
        inner = min(right, key=lambda n: n.pitch)
        if _span([n.pitch for n in left] + [inner.pitch]) > MAX_SPAN:
            break
        right.remove(inner)
        left.append(inner)
    while _span([n.pitch for n in left]) > MAX_SPAN:
        inner = max(left, key=lambda n: n.pitch)
        if _span([n.pitch for n in right] + [inner.pitch]) > MAX_SPAN:
            break
        left.remove(inner)
        right.append(inner)


def split_hands(notes: list[QNote]) -> tuple[list[QNote], list[QNote]]:
    """Naive Handtrennung am mittleren C mit Hysterese und Spannweitenlimit → (rechts, links)."""
    right_out: list[QNote] = []
    left_out: list[QNote] = []
    right_hist: deque[int] = deque(maxlen=HISTORY)
    left_hist: deque[int] = deque(maxlen=HISTORY)
    ordered = sorted(notes, key=_order)
    for _, group in groupby(ordered, key=lambda n: n.start):
        right: list[QNote] = []
        left: list[QNote] = []
        for note in group:
            (right if _choose(note.pitch, right_hist, left_hist) else left).append(note)
        _limit_span(right, left)
        right_hist.extend(n.pitch for n in right)
        left_hist.extend(n.pitch for n in left)
        right_out.extend(right)
        left_out.extend(left)
    return sorted(right_out, key=_order), sorted(left_out, key=_order)
