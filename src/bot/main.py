import structlog
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from src.bot.handlers import commands, text, voice
from src.core.config import get_settings
from src.core.exceptions import AudioTooLargeError, RateLimitError, UnauthorizedUserError
from src.core.health import HealthcheckServer
from src.core.logging import configure_logging
from src.db.session import init_db
from src.scheduler.jobs import build_scheduler

logger = structlog.get_logger(__name__)


async def _error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    err = context.error

    if isinstance(err, UnauthorizedUserError):
        if isinstance(update, Update) and update.message:
            await update.message.reply_text("⛔ Acesso não autorizado.")
        return

    if isinstance(err, AudioTooLargeError):
        if isinstance(update, Update) and update.message:
            await update.message.reply_text(
                f"❌ Áudio muito grande ({err.size_mb:.0f} MB). "
                f"O limite é {err.limit_mb:.0f} MB."
            )
        return

    if isinstance(err, RateLimitError):
        if isinstance(update, Update) and update.message:
            await update.message.reply_text(
                "⏱️ Muitas requisições seguidas. Tente novamente em instantes."
            )
        return

    logger.error("unhandled_error", exc_info=err)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            "❌ Ocorreu um erro inesperado. Tente novamente em instantes."
        )


async def _post_init(application: Application) -> None:  # type: ignore[type-arg]
    settings = get_settings()
    init_db()
    scheduler = build_scheduler(application)
    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    health_server = HealthcheckServer(settings.healthcheck_port)
    health_server.start()
    application.bot_data["health_server"] = health_server


async def _post_shutdown(application: Application) -> None:  # type: ignore[type-arg]
    scheduler = application.bot_data.get("scheduler")
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    health_server = application.bot_data.get("health_server")
    if health_server is not None:
        health_server.stop()


def build_app() -> Application:  # type: ignore[type-arg]
    settings = get_settings()

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", commands.start))
    app.add_handler(CommandHandler("ajuda", commands.ajuda))
    app.add_handler(CommandHandler("daily", commands.daily))
    app.add_handler(CommandHandler("weekly", commands.weekly))
    app.add_handler(CommandHandler("meta", commands.meta))
    app.add_handler(CommandHandler("historico", commands.historico))
    app.add_handler(CommandHandler("desfazer", commands.desfazer))

    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice.handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text.handle_text))
    app.add_handler(MessageHandler(filters.COMMAND, commands.unknown_command))

    app.add_error_handler(_error_handler)

    return app


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    logger.info("bot_starting", user_id=settings.telegram_allowed_user_id)
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
