from pathlib import Path

import structlog
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import get_settings
from src.core.exceptions import STTError
from src.stt.base import Transcription

logger = structlog.get_logger(__name__)

# $0.006 por minuto (whisper-1, abril 2024)
_COST_PER_MINUTE_USD = 0.006
_MODEL = "whisper-1"
# Prompt de contexto melhora acurácia de termos nutricionais em PT-BR
_PROMPT = (
    "Transcrição de relato de refeição em português brasileiro. "
    "Pode conter alimentos, quantidades, unidades de medida como gramas, "
    "colheres, xícaras, porções, unidades."
)


class WhisperSTT:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.require_openai_key())

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def transcribe(self, audio_path: Path) -> Transcription:
        if not audio_path.exists():
            raise STTError(f"Arquivo de áudio não encontrado: {audio_path}")

        size_mb = audio_path.stat().st_size / 1_048_576
        logger.info("stt_start", path=audio_path.name, size_mb=round(size_mb, 2))

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
            raise STTError(f"Falha na transcrição Whisper: {exc}") from exc

        duration_s: float | None = getattr(response, "duration", None)
        cost = (duration_s / 60.0) * _COST_PER_MINUTE_USD if duration_s else None

        text = response.text.strip()
        logger.info(
            "stt_done",
            chars=len(text),
            duration_s=duration_s,
            cost_usd=round(cost, 5) if cost else None,
        )

        return Transcription(
            text=text,
            language=getattr(response, "language", "pt") or "pt",
            duration_s=duration_s,
            cost_usd=cost,
        )
