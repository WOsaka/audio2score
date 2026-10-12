from audio2score.rhythm.base import BeatTracker


def _beat_this(**options) -> BeatTracker:
    from audio2score.rhythm.beat_this import BeatThisTracker

    return BeatThisTracker(**options)


# Tracker werden lazy importiert; der erste ist der Standard
_REGISTRY = {"beat_this": _beat_this}


def get_beat_tracker(name: str = "beat_this", **options) -> BeatTracker:
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Unbekannter Beat-Tracker '{name}'. Verfügbar: {', '.join(_REGISTRY)}"
        ) from None
    return factory(**options)
