from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

from src.core.config import get_settings
from src.db.repository import list_active_user_ids
from src.reports.weekly import build_weekly_summary, format_weekly_summary, render_weekly_chart


async def send_weekly_reports(application: Application) -> None:  # type: ignore[type-arg]
    for telegram_user_id in list_active_user_ids():
        summary = build_weekly_summary(telegram_user_id)
        text = format_weekly_summary(summary)
        chart_path = render_weekly_chart(summary, telegram_user_id)
        await application.bot.send_message(
            chat_id=telegram_user_id,
            text=text,
            parse_mode="Markdown",
        )
        if chart_path.exists():
            with chart_path.open("rb") as handle:
                await application.bot.send_photo(chat_id=telegram_user_id, photo=handle)


def build_scheduler(application: Application) -> AsyncIOScheduler:  # type: ignore[type-arg]
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.weekly_report_timezone)
    scheduler.add_job(
        send_weekly_reports,
        CronTrigger.from_crontab(
            settings.weekly_report_cron,
            timezone=settings.weekly_report_timezone,
        ),
        kwargs={"application": application},
        id="weekly_report",
        replace_existing=True,
    )
    return scheduler
