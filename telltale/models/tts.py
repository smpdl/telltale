from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path


@dataclass(frozen=True)
class TTSResult:
    text: str
    voice_id: str
    audio_path: str | None = None
    mime_type: str | None = None
    duration_seconds: float | None = None
    cache_hit: bool = False
    disabled: bool = True
    error: str | None = None


class TTSRuntime:
    """Text-first TTS wrapper. Local synthesis can be plugged in without affecting gameplay."""

    def __init__(self, enabled: bool = False, cache_dir: str | Path = "runs/tts_cache"):
        self.enabled = enabled
        self.cache_dir = Path(cache_dir)

    def synthesize(self, text: str, voice_id: str) -> TTSResult:
        normalized = text.strip()
        if not normalized:
            return TTSResult(text=text, voice_id=voice_id, error="empty text")
        if not self.enabled:
            return TTSResult(text=normalized, voice_id=voice_id, disabled=True)
        digest = hashlib.sha256(f"{voice_id}:{normalized}".encode("utf-8")).hexdigest()[:16]
        path = self.cache_dir / f"{digest}.wav"
        if path.exists():
            return TTSResult(
                text=normalized,
                voice_id=voice_id,
                audio_path=str(path),
                mime_type="audio/wav",
                cache_hit=True,
                disabled=False,
            )
        return TTSResult(
            text=normalized,
            voice_id=voice_id,
            disabled=False,
            error="local TTS runtime is not configured",
        )
