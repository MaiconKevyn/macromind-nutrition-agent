from src.core.config import get_settings
from src.stt.base import STTProvider


def get_stt_provider() -> STTProvider:
    settings = get_settings()
    provider = settings.stt_provider.lower()

    if provider == "groq":
        from src.stt.groq_whisper import GroqWhisperSTT
        return GroqWhisperSTT()

    if provider == "whisper":
        from src.stt.whisper import WhisperSTT
        return WhisperSTT()

    raise ValueError(f"STT provider desconhecido: '{provider}'. Use 'groq' ou 'whisper'.")
