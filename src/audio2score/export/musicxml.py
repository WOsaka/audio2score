import re
from pathlib import Path

from music21 import stream

_DEFAULT_COMPOSER = re.compile(r'[ \t]*<creator type="composer">Music21</creator>\r?\n')


def write_musicxml(score: stream.Score, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    score.write("musicxml", fp=str(path))
    xml = path.read_text(encoding="utf-8")
    # music21 trägt "Music21" als Komponisten ein und markiert den Auftakt (Takt 0) nicht als
    # implicit; so stünde der Fantasie-Komponist im Titel und MuseScore zählte den Auftakt mit
    xml = _DEFAULT_COMPOSER.sub("", xml)
    xml = xml.replace('implicit="no" number="0"', 'implicit="yes" number="0"')
    path.write_text(xml, encoding="utf-8")
