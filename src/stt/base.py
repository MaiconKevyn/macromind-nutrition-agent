from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Transcription:
    text: str
    language: str
    duration_s: float | None
    cost_usd: float | None  # None quando não aplicável (ex.: modelo local)


@runtime_checkable
class STTProvider(Protocol):
    async def transcribe(self, audio_path: Path) -> Transcription: ...
