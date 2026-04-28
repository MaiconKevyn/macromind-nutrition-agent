from pathlib import Path

import structlog
from groq import AsyncGroq
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import get_settings
from src.core.exceptions import STTError
from src.stt.base import Transcription

logger = structlog.get_logger(__name__)

_MODEL = "whisper-large-v3"
_PROMPT = (
    "Transcrição de relato de refeição em português brasileiro. "
    "Pode conter alimentos, quantidades, unidades de medida como gramas, "
    "colheres, xícaras, porções, unidades."
)


class GroqWhisperSTT:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncGroq(api_key=settings.require_groq_key())

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def transcribe(self, audio_path: Path) -> Transcription:
        if not audio_path.exists():
            raise STTError(f"Arquivo de áudio não encontrado: {audio_path}")

        size_mb = audio_path.stat().st_size / 1_048_576
        logger.info("stt_start", provider="groq", path=audio_path.name, size_mb=round(size_mb, 2))

        try:
            with audio_path.open("rb") as f:
                response = await self._client.audio.transcriptions.create(
                    model=_MODEL,
                    file=(audio_path.name, f, "audio/ogg"),
                    language="pt",
                    prompt=_PROMPT,
                    response_format="verbose_json",
                )
        except Exception as exc:
            raise STTError(f"Falha na transcrição Groq Whisper: {exc}") from exc

        duration_s: float | None = getattr(response, "duration", None)
        text = response.text.strip()

        logger.info("stt_done", provider="groq", chars=len(text), duration_s=duration_s)

        return Transcription(
            text=text,
            language="pt",
            duration_s=duration_s,
            cost_usd=0.0,  # free tier
        )
