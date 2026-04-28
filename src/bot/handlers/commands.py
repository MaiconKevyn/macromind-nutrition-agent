from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import structlog
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.core.exceptions import UnauthorizedUserError
from src.core.rate_limit import enforce_rate_limit
from src.db.repository import get_daily_summary, get_history, set_daily_goal, undo_last_meal
from src.reports.formatters import (
    format_daily_summary,
    format_goal_snapshot,
    format_history,
    format_undo_result,
)
from src.reports.weekly import build_weekly_summary, format_weekly_summary, render_weekly_chart

logger = structlog.get_logger(__name__)

_WELCOME = (
    "👋 Olá! Sou o *MacroMind*, seu agente nutricional.\n\n"
    "Manda um *áudio* descrevendo o que você comeu e eu calculo os macros na hora.\n\n"
    "*Comandos disponíveis:*\n"
    "• /daily — resumo nutricional de hoje\n"
    "• /weekly — relatório da semana\n"
    "• /meta — define suas metas diárias\n"
    "• /historico — histórico dos últimos dias\n"
    "• /desfazer — remove a última refeição\n"
    "• /ajuda — mostra esta mensagem"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_command(update, context, "start", _handle_start)


async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_command(update, context, "ajuda", _handle_ajuda)


async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_command(update, context, "daily", _handle_daily)


async def weekly(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_command(update, context, "weekly", _handle_weekly)


async def meta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_command(update, context, "meta", _handle_meta)


async def historico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_command(update, context, "historico", _handle_historico)


async def desfazer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_command(update, context, "desfazer", _handle_desfazer)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _assert_authorized(update)
    if update.message and update.message.text:
        logger.info("unknown_command_received", command_text=update.message.text)
        await update.message.reply_text(
            "❓ Comando não reconhecido. Use /ajuda para ver os comandos disponíveis."
        )


async def _run_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    command_name: str,
    callback: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]],
) -> None:
    _assert_authorized(update)
    user = update.effective_user
    logger.info(
        "command_received",
        command=command_name,
        args=context.args or [],
        user_id=user.id if user else None,
    )

    try:
        await callback(update, context)
        logger.info("command_finished", command=command_name, user_id=user.id if user else None)
    except ValueError as exc:
        logger.warning("command_invalid_args", command=command_name, error=str(exc))
        if update.message:
            await update.message.reply_text(
                f"❌ Argumentos inválidos para /{command_name}. "
                "Verifique o formato e tente novamente."
            )
    except Exception as exc:
        logger.exception("command_failed", command=command_name, error=str(exc))
        if update.message:
            await update.message.reply_text(
                f"❌ Falha ao executar /{command_name}. Verifique os logs."
            )


async def _reply_markdown(update: Update, text: str) -> None:
    if not update.message:
        return
    try:
        await update.message.reply_text(text, parse_mode="Markdown")
    except BadRequest as exc:
        logger.warning("markdown_reply_failed", error=str(exc))
        await update.message.reply_text(text)


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await _reply_markdown(update, _WELCOME)


async def _handle_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await _reply_markdown(update, _WELCOME)


async def _handle_daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if update.message and user is not None:
        target_date = datetime.now(UTC).date()
        if context.args:
            target_date = datetime.strptime(context.args[0], "%Y-%m-%d").date()
        logger.info("command_db_start", command="daily", target_date=target_date.isoformat())
        summary = get_daily_summary(user.id, target_date)
        logger.info(
            "command_db_done",
            command="daily",
            meals_count=summary.meals_count,
            total_kcal=summary.macros.total_energy_kcal,
        )
        await _reply_markdown(update, format_daily_summary(summary))


async def _handle_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if update.message and user is not None:
        weeks_ago = int(context.args[0]) if context.args else 0
        logger.info("command_db_start", command="weekly", weeks_ago=weeks_ago)
        summary = build_weekly_summary(user.id, weeks_ago=weeks_ago)
        logger.info(
            "command_db_done",
            command="weekly",
            meals_count=summary.meals_count,
            days_with_logs=summary.total_days_with_logs,
        )
        await _reply_markdown(update, format_weekly_summary(summary))
        if summary.current_by_day:
            logger.info("command_chart_start", command="weekly")
            chart_path = render_weekly_chart(summary, user.id)
            logger.info("command_chart_done", command="weekly", chart_path=str(chart_path))
            with chart_path.open("rb") as handle:
                await update.message.reply_photo(handle)


async def _handle_meta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if update.message and user is not None:
        pairs = {}
        for raw_arg in context.args or []:
            if "=" not in raw_arg:
                continue
            key, value = raw_arg.split("=", 1)
            pairs[key.strip().lower()] = float(value)

        logger.info("command_db_start", command="meta", fields=sorted(pairs.keys()))
        goal = set_daily_goal(
            telegram_user_id=user.id,
            user_name=user.full_name,
            kcal=pairs.get("kcal"),
            protein_g=pairs.get("p"),
            carb_g=pairs.get("c"),
            fat_g=pairs.get("g"),
            fiber_g=pairs.get("f"),
        )
        logger.info("command_db_done", command="meta")
        await _reply_markdown(update, format_goal_snapshot(goal))


async def _handle_historico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if update.message and user is not None:
        days = int(context.args[0]) if context.args else 7
        logger.info("command_db_start", command="historico", days=days)
        history = get_history(user.id, days)
        logger.info("command_db_done", command="historico", days=days, returned=len(history))
        await _reply_markdown(update, format_history(history))


async def _handle_desfazer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if update.message and user is not None:
        logger.info("command_db_start", command="desfazer")
        meal = undo_last_meal(user.id)
        logger.info("command_db_done", command="desfazer", found=meal is not None)
        if meal is None:
            await update.message.reply_text("↩️ Nenhuma refeição registrada para remover.")
            return
        await _reply_markdown(update, format_undo_result(meal.occurred_at.date(), meal.macros))


def _assert_authorized(update: Update) -> None:
    from src.core.config import get_settings

    settings = get_settings()
    user = update.effective_user
    if not user or user.id != settings.telegram_allowed_user_id:
        raise UnauthorizedUserError(f"Usuário {user.id if user else None} não autorizado")
    enforce_rate_limit(user.id)
