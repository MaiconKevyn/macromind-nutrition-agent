"""Testes de smoke — verifica que imports e config básica funcionam."""

import os

import pytest


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "12345")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test")


def test_settings_loads() -> None:
    from src.core.config import Settings

    s = Settings()  # type: ignore[call-arg]
    assert s.telegram_allowed_user_id == 12345
    assert s.llm_model == "claude-haiku-4-5-20251001"
    assert s.log_level == "INFO"


def test_settings_singleton() -> None:
    import sys

    if "src.core.config" in sys.modules:
        del sys.modules["src.core.config"]

    from src.core.config import get_settings

    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "fake-token")
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_exceptions_importable() -> None:
    from src.core.exceptions import (
        AudioTooLargeError,
        DatabaseError,
        ExtractionError,
        MacroMindError,
        NutritionLookupError,
        STTError,
        UnauthorizedUserError,
    )

    err = AudioTooLargeError(size_mb=30.0)
    assert "30.0" in str(err)
    assert issubclass(AudioTooLargeError, MacroMindError)
    assert issubclass(STTError, MacroMindError)
    assert issubclass(ExtractionError, MacroMindError)
    assert issubclass(NutritionLookupError, MacroMindError)
    assert issubclass(DatabaseError, MacroMindError)
    assert issubclass(UnauthorizedUserError, MacroMindError)


def test_logging_configures() -> None:
    from src.core.logging import configure_logging

    configure_logging("WARNING")  # não deve lançar exceção


def test_asyncpg_database_url_is_normalized() -> None:
    import sys

    if "src.db.session" in sys.modules:
        del sys.modules["src.db.session"]

    from src.db.session import _normalize_database_url

    normalized = _normalize_database_url(
        "postgresql+asyncpg://user:pass@localhost:5432/macromind"
    )
    assert normalized == "postgresql+psycopg://user:pass@localhost:5432/macromind"
