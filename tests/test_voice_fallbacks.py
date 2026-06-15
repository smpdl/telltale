from telltale.models.stt import STTRuntime
from telltale.models.tts import TTSRuntime


def test_tts_disabled_returns_text_only_result():
    result = TTSRuntime(enabled=False).synthesize("Keep the line clean.", "ace")

    assert result.disabled is True
    assert result.audio_path is None
    assert result.error is None


def test_stt_disabled_is_structured_and_non_throwing():
    result = STTRuntime(enabled=False).transcribe(b"audio")

    assert result.disabled is True
    assert result.text == ""
    assert result.error == "speech input is disabled"
