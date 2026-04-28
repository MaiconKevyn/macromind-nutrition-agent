class MacroMindError(Exception):
    """Base para todas as exceções do MacroMind."""


class STTError(MacroMindError):
    """Falha na transcrição de áudio."""


class ExtractionError(MacroMindError):
    """Falha na extração de itens da refeição pelo LLM."""


class NutritionLookupError(MacroMindError):
    """Item alimentar não encontrado em nenhuma fonte nutricional."""


class DatabaseError(MacroMindError):
    """Falha de persistência."""


class UnauthorizedUserError(MacroMindError):
    """Usuário não autorizado tentou interagir com o bot."""


class RateLimitError(MacroMindError):
    """Usuário excedeu o limite configurado de requisições."""


class AudioTooLargeError(MacroMindError):
    """Áudio excede o limite suportado pela API de STT."""

    def __init__(self, size_mb: float, limit_mb: float = 25.0) -> None:
        self.size_mb = size_mb
        self.limit_mb = limit_mb
        super().__init__(f"Áudio de {size_mb:.1f} MB excede o limite de {limit_mb:.0f} MB")
