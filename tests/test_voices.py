from audio2score.rhythm.quantize import QNote
from audio2score.score.voices import single_voice


def q(pitch, start, dur, vel=80):
    return QNote(pitch, start, dur, vel)


def test_same_pitch_on_same_position_is_merged_with_longest_duration_and_loudest_velocity():
    out = single_voice([q(60, 0, 2, 50), q(60, 0, 5, 90)])
    assert out == [q(60, 0, 5, 90)]


def test_same_onset_forms_a_chord_with_the_longest_duration():
    out = single_voice([q(60, 0, 2), q(64, 0, 6), q(67, 0, 4)])
    assert out == [q(60, 0, 6), q(64, 0, 6), q(67, 0, 6)]


def test_duration_is_cut_at_the_next_onset_of_the_hand():
    out = single_voice([q(60, 0, 6), q(64, 0, 2), q(62, 4, 4)])
    assert out == [q(60, 0, 4), q(64, 0, 4), q(62, 4, 4)]


def test_overlapping_melody_notes_are_cut_one_by_one():
    out = single_voice([q(60, 0, 10), q(62, 3, 10), q(64, 5, 1)])
    assert [(x.start, x.duration) for x in out] == [(0, 3), (3, 2), (5, 1)]


def test_last_group_keeps_its_duration():
    assert single_voice([q(60, 0, 2), q(62, 8, 7)])[-1] == q(62, 8, 7)


def test_empty_and_unsorted_input():
    assert single_voice([]) == []
    out = single_voice([q(62, 4, 4), q(60, 0, 8)])
    assert out == [q(60, 0, 4), q(62, 4, 4)]


def test_chord_members_keep_their_own_velocity():
    out = single_voice([q(60, 0, 2, 40), q(64, 0, 2, 100)])
    assert [x.velocity for x in out] == [40, 100]
