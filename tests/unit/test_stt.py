"""Testes unitários do módulo STT (sem chamadas reais à API)."""

import dataclasses
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.stt.base import STTProvider, Transcription


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "42")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("DATABASE_URL", "")
    import src.core.config as cfg
    cfg._settings = None


def test_transcription_is_frozen() -> None:
    t = Transcription(text="arroz e feijão", language="pt", duration_s=5.0, cost_usd=0.0005)
    with pytest.raises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
        t.text = "outro"  # type: ignore[misc]


def test_whisper_implements_protocol() -> None:
    from src.stt.whisper import WhisperSTT

    with patch("src.stt.whisper.AsyncOpenAI"):
        stt = WhisperSTT()
    assert isinstance(stt, STTProvider)


@pytest.mark.asyncio
async def test_whisper_transcribe_success() -> None:
    from src.stt.whisper import WhisperSTT

    fake_response = MagicMock()
    fake_response.text = "  comi 200g de arroz e frango  "
    fake_response.duration = 8.0
    fake_response.language = "pt"

    mock_client = AsyncMock()
    mock_client.audio.transcriptions.create = AsyncMock(return_value=fake_response)

    with patch("src.stt.whisper.AsyncOpenAI", return_value=mock_client):
        stt = WhisperSTT()
        stt._client = mock_client

    audio_file = Path("tests/fixtures/fake_audio.ogg")
    audio_file.parent.mkdir(parents=True, exist_ok=True)
    audio_file.write_bytes(b"fake ogg content")

    try:
        result = await stt.transcribe(audio_file)
    finally:
        audio_file.unlink(missing_ok=True)

    assert result.text == "comi 200g de arroz e frango"  # strip aplicado
    assert result.language == "pt"
    assert result.duration_s == 8.0
    assert result.cost_usd is not None
    assert result.cost_usd > 0


@pytest.mark.asyncio
async def test_whisper_transcribe_file_not_found() -> None:
    from src.core.exceptions import STTError
    from src.stt.whisper import WhisperSTT

    with patch("src.stt.whisper.AsyncOpenAI"):
        stt = WhisperSTT()

    with pytest.raises(STTError, match="não encontrado"):
        await stt.transcribe(Path("nao_existe.ogg"))


@pytest.mark.asyncio
async def test_whisper_transcribe_api_error_raises_stt_error() -> None:
    from src.core.exceptions import STTError
    from src.stt.whisper import WhisperSTT

    mock_client = AsyncMock()
    mock_client.audio.transcriptions.create = AsyncMock(
        side_effect=Exception("API down")
    )

    with patch("src.stt.whisper.AsyncOpenAI", return_value=mock_client):
        stt = WhisperSTT()
        stt._client = mock_client

    audio_file = Path("tests/fixtures/fake_audio2.ogg")
    audio_file.parent.mkdir(parents=True, exist_ok=True)
    audio_file.write_bytes(b"fake")

    try:
        with pytest.raises(STTError, match="Falha na transcrição"):
            await stt.transcribe(audio_file)
    finally:
        audio_file.unlink(missing_ok=True)
