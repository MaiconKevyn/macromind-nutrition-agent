from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str
    telegram_allowed_user_id: int

    # LLM (necessário a partir do Ckpt 2/3)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    # STT: "whisper" (OpenAI) ou "groq" (Groq Whisper, free tier)
    stt_provider: str = "groq"

    # Database (necessário a partir do Ckpt 5)
    database_url: str = ""

    # Observabilidade
    log_level: str = "INFO"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    sentry_dsn: str = ""

    # Storage
    audio_storage_path: str = "data/audio"

    # Hardening
    rate_limit_per_minute: int = 20
    healthcheck_port: int = 8081

    # Scheduler
    weekly_report_cron: str = "0 20 * * 0"
    weekly_report_timezone: str = "America/Sao_Paulo"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level deve ser um de {valid}")
        return upper

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if v and not v.startswith(("postgresql", "sqlite")):
            raise ValueError("database_url deve começar com postgresql ou sqlite")
        return v

    def require_openai_key(self) -> str:
        if not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY não configurada no .env")
        return self.openai_api_key

    def require_groq_key(self) -> str:
        if not self.groq_api_key:
            raise RuntimeError("GROQ_API_KEY não configurada no .env")
        return self.groq_api_key

    def require_anthropic_key(self) -> str:
        if not self.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY não configurada no .env")
        return self.anthropic_api_key

    def require_database_url(self) -> str:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL não configurada no .env")
        return self.database_url


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
