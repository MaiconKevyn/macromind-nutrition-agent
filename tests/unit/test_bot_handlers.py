"""Testes unitários dos handlers do bot."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import UnauthorizedUserError


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "42")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("DATABASE_URL", "")
    # reset singleton entre testes
    import src.core.config as cfg

    cfg._settings = None


def _make_update(user_id: int, has_message: bool = True) -> MagicMock:
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    if has_message:
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()
        update.message.voice = None
        update.message.audio = None
    else:
        update.message = None
    return update


@pytest.mark.asyncio
async def test_start_authorized() -> None:
    from src.bot.handlers.commands import start

    update = _make_update(user_id=42)
    await start(update, MagicMock())
    update.message.reply_text.assert_called_once()
    args = update.message.reply_text.call_args[0][0]
    assert "MacroMind" in args


@pytest.mark.asyncio
async def test_start_unauthorized() -> None:
    from src.bot.handlers.commands import start

    update = _make_update(user_id=999)
    with pytest.raises(UnauthorizedUserError):
        await start(update, MagicMock())


@pytest.mark.asyncio
async def test_voice_unauthorized() -> None:
    from src.bot.handlers.voice import handle_voice

    update = _make_update(user_id=999)
    with pytest.raises(UnauthorizedUserError):
        await handle_voice(update, MagicMock())


@pytest.mark.asyncio
async def test_voice_too_large() -> None:
    from src.bot.handlers.voice import handle_voice
    from src.core.exceptions import AudioTooLargeError

    update = _make_update(user_id=42)
    voice_mock = MagicMock()
    voice_mock.file_size = 30 * 1_048_576  # 30 MB
    voice_mock.duration = 120
    update.message.voice = voice_mock
    update.message.audio = None

    with pytest.raises(AudioTooLargeError) as exc_info:
        await handle_voice(update, MagicMock())

    assert exc_info.value.size_mb > 25


@pytest.mark.asyncio
async def test_voice_valid_downloads_and_transcribes() -> None:
    from src.bot.handlers.voice import handle_voice

    update = _make_update(user_id=42)
    voice_mock = MagicMock()
    voice_mock.file_size = 500_000  # 0.5 MB
    voice_mock.duration = 10
    voice_mock.file_id = "fake-file-id"
    update.message.voice = voice_mock
    update.message.audio = None

    fake_file = AsyncMock()
    fake_file.download_to_drive = AsyncMock()

    context = MagicMock()
    context.bot = AsyncMock()
    context.bot.get_file = AsyncMock(return_value=fake_file)

    fake_state = {
        "extracted_meal": MagicMock(items=[MagicMock()]),
        "reply_text": "🍽️ *Refeição registrada*\n• Arroz — 200g",
    }

    with (
        patch.object(Path, "mkdir"),
        patch(
            "src.bot.handlers.voice.run_meal_pipeline",
            AsyncMock(return_value=fake_state),
        ),
    ):
        await handle_voice(update, context)

    context.bot.get_file.assert_called_once_with("fake-file-id")
    fake_file.download_to_drive.assert_called_once()
    assert update.message.reply_text.call_count == 2
    final_reply = update.message.reply_text.call_args_list[1][0][0]
    assert "Arroz" in final_reply


@pytest.mark.asyncio
async def test_text_unauthorized() -> None:
    from src.bot.handlers.text import handle_text

    update = _make_update(user_id=999)
    update.message.text = "200g de arroz"
    with pytest.raises(UnauthorizedUserError):
        await handle_text(update, MagicMock())


@pytest.mark.asyncio
async def test_text_valid_skips_stt_and_processes_meal() -> None:
    from src.bot.handlers.text import handle_text

    update = _make_update(user_id=42)
    update.message.text = "200g de arroz e 150g de frango"
    update.message.message_id = 123

    context = MagicMock()
    fake_state = {
        "extracted_meal": MagicMock(items=[MagicMock()]),
        "reply_text": "🍽️ *Refeição registrada*\n• Arroz — 200g",
    }

    with patch(
        "src.bot.handlers.text.run_meal_pipeline",
        AsyncMock(return_value=fake_state),
    ) as pipeline_mock:
        await handle_text(update, context)

    pipeline_mock.assert_awaited_once()
    kwargs = pipeline_mock.await_args.kwargs
    assert kwargs["transcription"] == "200g de arroz e 150g de frango"
    assert kwargs["audio_path"] == "telegram:text:123"
    assert update.message.reply_text.call_count == 2
    final_reply = update.message.reply_text.call_args_list[1][0][0]
    assert "Arroz" in final_reply


@pytest.mark.asyncio
async def test_text_parses_meal_type_header_and_forwards_clean_text() -> None:
    from src.agent.schemas import MealType
    from src.bot.handlers.text import handle_text

    update = _make_update(user_id=42)
    update.message.text = "café da manhã\n3 ovos caipira, 1 pão francês"
    update.message.message_id = 456

    context = MagicMock()
    fake_state = {
        "extracted_meal": MagicMock(items=[MagicMock()]),
        "reply_text": "🍽️ *Refeição registrada*",
    }

    with patch(
        "src.bot.handlers.text.run_meal_pipeline",
        AsyncMock(return_value=fake_state),
    ) as pipeline_mock:
        await handle_text(update, context)

    kwargs = pipeline_mock.await_args.kwargs
    assert kwargs["transcription"] == "café da manhã\n3 ovos caipira, 1 pão francês"
    assert kwargs["transcription_for_extraction"] == "3 ovos caipira, 1 pão francês"
    assert kwargs["meal_type_override"] == MealType.cafe_da_manha
