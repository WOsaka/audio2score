from pathlib import Path

import pretty_midi

from audio2score.model import NoteList


def write_midi(nl: NoteList, path: Path) -> None:
    """Schreibt eine MIDI-Spur (Acoustic Grand) mit Tasten-Offsets und Sustain-Pedal (CC64)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    midi = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0, name="Piano")
    for n in nl.notes:
        inst.notes.append(
            pretty_midi.Note(velocity=n.velocity, pitch=n.pitch, start=n.onset, end=n.offset)
        )
    for p in nl.pedals:
        inst.control_changes.append(pretty_midi.ControlChange(64, 127, p.onset))
        inst.control_changes.append(pretty_midi.ControlChange(64, 0, p.offset))
    midi.instruments.append(inst)
    midi.write(str(path))
