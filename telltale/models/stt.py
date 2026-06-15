from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class STTResult:
    text: str = ""
    confidence: float | None = None
    disabled: bool = True
    error: str | None = None


class STTRuntime:
    """Optional local speech-to-text wrapper. Typed table talk remains primary."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def transcribe(self, audio: bytes | str | None) -> STTResult:
        if not self.enabled:
            return STTResult(disabled=True, error="speech input is disabled")
        if not audio:
            return STTResult(disabled=False, error="empty audio")
        return STTResult(disabled=False, error="local STT runtime is not configured")
