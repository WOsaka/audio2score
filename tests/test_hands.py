from audio2score.rhythm.quantize import QNote
from audio2score.score.hands import split_hands


def q(pitch, start, dur=2):
    return QNote(pitch, start, dur, 80)


def pitches(notes):
    return [x.pitch for x in notes]


def test_clear_registers_split_at_middle_c_with_hysteresis():
    notes = [q(72, 0), q(48, 0), q(65, 4), q(55, 4)]
    right, left = split_hands(notes)
    assert pitches(right) == [72, 65]
    assert pitches(left) == [48, 55]


def test_empty_input_and_empty_hand():
    assert split_hands([]) == ([], [])
    right, left = split_hands([q(70, 0), q(75, 2)])
    assert pitches(right) == [70, 75] and left == []


def test_without_history_the_split_point_decides():
    right, left = split_hands([q(60, 0)])
    assert pitches(right) == [60] and left == []
    right, left = split_hands([q(59, 0)])
    assert pitches(left) == [59] and right == []


def test_ambiguous_note_follows_the_hand_that_played_nearby():
    history = [q(66, 0), q(64, 2), q(63, 4), q(45, 0), q(48, 2), q(47, 4)]
    right, left = split_hands([*history, q(58, 6)])  # unter dem Split, aber nahe der rechten Hand
    assert 58 in pitches(right)
    assert 58 not in pitches(left)


def test_ambiguous_note_above_split_can_go_left():
    history = [q(52, 0), q(55, 2), q(56, 4), q(80, 0), q(78, 2), q(76, 4)]
    right, left = split_hands([*history, q(62, 6)])
    assert 62 in pitches(left)


def test_span_limit_moves_the_inner_note_to_the_other_hand():
    notes = [q(52, 0), q(66, 0), q(81, 0)]  # rechts wäre 66–81 = 15 Halbtöne
    right, left = split_hands(notes)
    assert pitches(right) == [81]
    assert pitches(left) == [52, 66]


def test_span_limit_is_not_enforced_when_the_other_hand_cannot_take_the_note():
    notes = [q(40, 0), q(66, 0), q(81, 0)]
    right, left = split_hands(notes)
    assert pitches(right) == [66, 81]
    assert pitches(left) == [40]


def test_result_is_sorted_by_start_then_pitch_and_notes_are_unchanged():
    notes = [q(76, 4, 3), q(70, 0, 5), q(72, 0, 1)]
    right, _ = split_hands(notes)
    assert right == [q(70, 0, 5), q(72, 0, 1), q(76, 4, 3)]
