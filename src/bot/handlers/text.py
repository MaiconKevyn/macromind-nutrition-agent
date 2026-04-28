import re
import unicodedata
from datetime import UTC, datetime

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from src.agent.graph import run_meal_pipeline
from src.agent.schemas import MealType
from src.core.exceptions import (
    DatabaseError,
    ExtractionError,
    NutritionLookupError,
    UnauthorizedUserError,
)
from src.core.rate_limit import enforce_rate_limit

logger = structlog.get_logger(__name__)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    if not message or not message.text:
        return

    correlation_id = f"text-{message.chat_id}-{message.message_id}"

    with structlog.contextvars.bound_contextvars(
        correlation_id=correlation_id,
        user_id=user.id if user else None,
    ):
        _assert_authorized(update)
        assert user is not None

        transcription = message.text.strip()
        if not transcription:
            await message.reply_text("❌ Envie uma descrição da refeição em texto ou áudio.")
            return

        logger.info("text_received", chars=len(transcription))
        await message.reply_text("📝 Texto recebido. Processando refeição…")

        meal_type, extraction_text = _split_meal_type(transcription)
        if meal_type is not None:
            logger.info(
                "meal_type_detected",
                meal_type=meal_type,
                extraction_chars=len(extraction_text),
            )

        try:
            state = await run_meal_pipeline(
                user_id=user.id,
                user_name=user.full_name,
                source_message_id=message.message_id,
                audio_path=f"telegram:text:{message.message_id}",
                occurred_at=message.date or datetime.now(UTC),
                transcription=transcription,
                transcription_for_extraction=extraction_text,
                meal_type_override=meal_type,
            )
        except ExtractionError as exc:
            logger.error("extraction_failed", error=str(exc))
            await message.reply_text("❌ Não consegui identificar os alimentos. Tente reformular.")
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
            logger.exception("text_processing_unexpected_error", error=str(exc))
            await message.reply_text(
                "❌ Erro inesperado ao processar a refeição. "
                "Verifique os logs com o correlation_id."
            )
            return

        meal = state.get("extracted_meal")
        if not meal or not meal.items:
            await message.reply_text(
                "🤔 Não identifiquei nenhum alimento na mensagem. "
                "Exemplo: '200g de arroz, 150g de frango e 1 maçã'."
            )
            return

        reply = state.get("reply_text")
        if not reply:
            logger.warning("reply_missing")
            reply = "❌ O processamento terminou sem resposta formatada."
        await message.reply_text(reply, parse_mode="Markdown")


def _assert_authorized(update: Update) -> None:
    from src.core.config import get_settings

    settings = get_settings()
    user = update.effective_user
    if not user or user.id != settings.telegram_allowed_user_id:
        raise UnauthorizedUserError(f"Usuário {user.id if user else None} não autorizado")
    enforce_rate_limit(user.id)


_MEAL_TYPE_ALIASES: dict[str, MealType] = {
    "cafe da manha": MealType.cafe_da_manha,
    "cafe-da-manha": MealType.cafe_da_manha,
    "lanche": MealType.lanche,
    "pre treino": MealType.pre_treino,
    "pre-treino": MealType.pre_treino,
    "pos treino": MealType.pos_treino,
    "pos-treino": MealType.pos_treino,
    "janta": MealType.janta,
    "almoco": MealType.almoco,
    "jantar": MealType.jantar,
    "ceia": MealType.ceia,
}


def _split_meal_type(text: str) -> tuple[MealType | None, str]:
    lines = [line.strip() for line in text.splitlines()]
    non_empty = [line for line in lines if line]
    if len(non_empty) < 2:
        return None, text.strip()

    meal_type = _parse_meal_type(non_empty[0])
    if meal_type is None:
        return None, text.strip()

    remainder = "\n".join(non_empty[1:]).strip()
    remainder = re.sub(r"^[\s:.-]+", "", remainder)
    return meal_type, remainder


def _parse_meal_type(text: str) -> MealType | None:
    normalized = _normalize_meal_type(text)
    return _MEAL_TYPE_ALIASES.get(normalized)


def _normalize_meal_type(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower().strip()
    normalized = re.sub(r"[^a-z0-9\s-]", " ", normalized)
    normalized = normalized.replace("-", " ")
    return " ".join(normalized.split())
