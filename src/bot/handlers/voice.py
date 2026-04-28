from pathlib import Path

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from src.agent.graph import run_meal_pipeline
from src.core.config import get_settings
from src.core.exceptions import (
    AudioTooLargeError,
    DatabaseError,
    ExtractionError,
    NutritionLookupError,
    STTError,
    UnauthorizedUserError,
)
from src.core.rate_limit import enforce_rate_limit

logger = structlog.get_logger(__name__)

_AUDIO_LIMIT_MB = 25.0


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    if not message:
        return

    chat_id = update.effective_chat.id if update.effective_chat else "chat"
    correlation_id = f"{chat_id}-{message.message_id}"

    with structlog.contextvars.bound_contextvars(
        correlation_id=correlation_id,
        user_id=user.id if user else None,
    ):
        _assert_authorized(update)
        assert user is not None

        voice = message.voice or message.audio
        if not voice:
            return

        size_mb = (voice.file_size or 0) / 1_048_576
        logger.info(
            "audio_received",
            size_mb=round(size_mb, 2),
            duration_s=getattr(voice, "duration", None),
        )

        if size_mb > _AUDIO_LIMIT_MB:
            raise AudioTooLargeError(size_mb=size_mb)

        await message.reply_text("🎙️ Áudio recebido. Processando refeição…")

        audio_path = await _download_audio(update, context, correlation_id)

        try:
            state = await run_meal_pipeline(
                user_id=user.id,
                user_name=user.full_name,
                source_message_id=message.message_id,
                audio_path=str(audio_path),
                occurred_at=message.date,
            )
        except STTError as exc:
            logger.error("stt_failed", error=str(exc))
            await message.reply_text("❌ Não consegui transcrever o áudio. Tente novamente.")
            return
        except ExtractionError as exc:
            logger.error("extraction_failed", error=str(exc))
            await message.reply_text("❌ Não consegui identificar os alimentos. Tente novamente.")
            return
        except NutritionLookupError as exc:
            logger.error("nutrition_failed", error=str(exc))
            await message.reply_text(f"❌ {exc}")
            return
        except DatabaseError as exc:
            logger.error("database_failed", error=str(exc))
            await message.reply_text("❌ Não consegui salvar a refeição no banco.")
            return
        except Exception as exc:
            logger.exception("voice_processing_unexpected_error", error=str(exc))
            await message.reply_text(
                "❌ Erro inesperado ao processar a refeição. "
                "Verifique os logs com o correlation_id."
            )
            return

        meal = state.get("extracted_meal")
        if not meal or not meal.items:
            await message.reply_text(
                "🤔 Não identifiquei nenhum alimento na descrição. "
                "Tente ser mais específico (ex: 'comi 200g de arroz e frango grelhado')."
            )
            return

        reply = state.get("reply_text")
        if not reply:
            logger.warning("reply_missing")
            reply = "❌ O processamento terminou sem resposta formatada."
        await message.reply_text(reply, parse_mode="Markdown")


async def _download_audio(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    correlation_id: str,
) -> Path:
    settings = get_settings()
    message = update.message
    assert message is not None

    voice = message.voice or message.audio
    assert voice is not None

    user_id = update.effective_user.id if update.effective_user else "unknown"
    storage_dir = Path(settings.audio_storage_path) / str(user_id)
    storage_dir.mkdir(parents=True, exist_ok=True)

    ext = ".ogg" if message.voice else ".mp3"
    dest = storage_dir / f"{correlation_id}{ext}"

    tg_file = await context.bot.get_file(voice.file_id)
    await tg_file.download_to_drive(dest)

    return dest


def _assert_authorized(update: Update) -> None:
    settings = get_settings()
    user = update.effective_user
    if not user or user.id != settings.telegram_allowed_user_id:
        user_id = user.id if user else None
        logger.warning("unauthorized_access", user_id=user_id)
        raise UnauthorizedUserError(f"Usuário {user_id} não autorizado")
    enforce_rate_limit(user.id)
