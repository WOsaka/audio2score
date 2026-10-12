from audio2score.transcribe.base import Transcriber


def _bytedance(**options) -> Transcriber:
    from audio2score.transcribe.bytedance import ByteDanceTranscriber

    return ByteDanceTranscriber(**options)


def _basic_pitch(**options) -> Transcriber:
    from audio2score.transcribe.basic_pitch import BasicPitchTranscriber

    return BasicPitchTranscriber()  # keine Optionen: Modell liegt im Paket


# Backends werden lazy importiert; das erste ist der Standard
_REGISTRY = {"bytedance": _bytedance, "basic-pitch": _basic_pitch}


def available_backends() -> list[str]:
    return list(_REGISTRY)


def get_transcriber(name: str, **options) -> Transcriber:
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Unbekanntes Backend '{name}'. Verfügbar: {', '.join(_REGISTRY)}"
        ) from None
    return factory(**options)
