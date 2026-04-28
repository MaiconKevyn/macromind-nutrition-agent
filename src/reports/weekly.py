from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.models import Meal, User
from src.db.repository import GoalSnapshot
from src.db.session import session_scope
from src.nutrition.models import MealMacros


@dataclass(frozen=True)
class WeeklySummary:
    week_start: date
    week_end: date
    meals_count: int
    average_kcal: float
    average_protein_g: float
    average_carb_g: float
    average_fat_g: float
    average_fiber_g: float
    top_foods: tuple[tuple[str, int], ...]
    adherence_days: int
    total_days_with_logs: int
    current_by_day: tuple[tuple[date, float], ...]
    previous_average_kcal: float | None


def _week_bounds(weeks_ago: int) -> tuple[datetime, datetime]:
    today = datetime.now(UTC).date()
    week_start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks_ago)
    start = datetime.combine(week_start, time.min, tzinfo=UTC)
    end = start + timedelta(days=7)
    return start, end


def _goal_hit(macros: MealMacros, goal: GoalSnapshot | None) -> bool:
    if goal is None or goal.kcal is None:
        return False
    min_kcal = goal.kcal * 0.9
    max_kcal = goal.kcal * 1.1
    return min_kcal <= macros.total_energy_kcal <= max_kcal


def _meal_macros(meal: Meal) -> MealMacros:
    from src.db.repository import _meal_to_macros

    return _meal_to_macros(meal)


def build_weekly_summary(telegram_user_id: int, *, weeks_ago: int = 0) -> WeeklySummary:
    start, end = _week_bounds(weeks_ago)
    prev_start = start - timedelta(days=7)
    prev_end = start

    with session_scope() as session:
        meals = list(
            session.scalars(
                select(Meal)
                .join(User, User.id == Meal.user_id)
                .options(selectinload(Meal.items))
                .where(
                    User.telegram_id == telegram_user_id,
                    Meal.occurred_at >= start,
                    Meal.occurred_at < end,
                )
            )
        )
        prev_meals = list(
            session.scalars(
                select(Meal)
                .join(User, User.id == Meal.user_id)
                .options(selectinload(Meal.items))
                .where(
                    User.telegram_id == telegram_user_id,
                    Meal.occurred_at >= prev_start,
                    Meal.occurred_at < prev_end,
                )
            )
        )

    day_buckets: dict[date, list[MealMacros]] = {}
    top_counts: dict[str, int] = {}

    for meal in meals:
        day = meal.occurred_at.date()
        macros = _meal_macros(meal)
        day_buckets.setdefault(day, []).append(macros)
        for item in meal.items:
            top_counts[item.food_name] = top_counts.get(item.food_name, 0) + 1

    daily_totals: list[tuple[date, MealMacros]] = []
    for day, bucket in sorted(day_buckets.items()):
        items = [item for macros in bucket for item in macros.items]
        daily_totals.append((day, MealMacros.from_items(items)))

    total_days = len(daily_totals)
    if total_days == 0:
        return WeeklySummary(
            week_start=start.date(),
            week_end=(end - timedelta(days=1)).date(),
            meals_count=0,
            average_kcal=0.0,
            average_protein_g=0.0,
            average_carb_g=0.0,
            average_fat_g=0.0,
            average_fiber_g=0.0,
            top_foods=(),
            adherence_days=0,
            total_days_with_logs=0,
            current_by_day=(),
            previous_average_kcal=None,
        )

    goal = None
    from src.db.repository import get_active_goal

    adherence_days = 0
    for day, macros in daily_totals:
        goal = get_active_goal(telegram_user_id, day)
        if _goal_hit(macros, goal):
            adherence_days += 1

    average_kcal = sum(macros.total_energy_kcal for _, macros in daily_totals) / total_days
    average_protein = sum(macros.total_protein_g for _, macros in daily_totals) / total_days
    average_carb = sum(macros.total_carb_g for _, macros in daily_totals) / total_days
    average_fat = sum(macros.total_fat_g for _, macros in daily_totals) / total_days
    average_fiber = sum(macros.total_fiber_g for _, macros in daily_totals) / total_days

    prev_average_kcal: float | None = None
    if prev_meals:
        prev_items = [_meal_macros(meal) for meal in prev_meals]
        prev_average_kcal = round(
            sum(item.total_energy_kcal for item in prev_items) / len(prev_items),
            1,
        )

    return WeeklySummary(
        week_start=start.date(),
        week_end=(end - timedelta(days=1)).date(),
        meals_count=len(meals),
        average_kcal=round(average_kcal, 1),
        average_protein_g=round(average_protein, 1),
        average_carb_g=round(average_carb, 1),
        average_fat_g=round(average_fat, 1),
        average_fiber_g=round(average_fiber, 1),
        top_foods=tuple(sorted(top_counts.items(), key=lambda item: item[1], reverse=True)[:10]),
        adherence_days=adherence_days,
        total_days_with_logs=total_days,
        current_by_day=tuple((day, macros.total_energy_kcal) for day, macros in daily_totals),
        previous_average_kcal=prev_average_kcal,
    )


def render_weekly_chart(summary: WeeklySummary, telegram_user_id: int) -> Path:
    output_dir = Path("data/reports") / str(telegram_user_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"weekly_{summary.week_start.isoformat()}.png"

    labels = [day.strftime("%d/%m") for day, _ in summary.current_by_day]
    kcal = [value for _, value in summary.current_by_day]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(labels, kcal, color="#2f855a")
    ax.set_title("Kcal por dia")
    ax.set_ylabel("kcal")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)

    return output_path


def format_weekly_summary(summary: WeeklySummary) -> str:
    trend = "n/d"
    if summary.previous_average_kcal is not None:
        delta = summary.average_kcal - summary.previous_average_kcal
        arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
        trend = f"{arrow} {delta:+.0f} kcal"

    lines = [
        f"📈 *Resumo semanal* ({summary.week_start.isoformat()} a {summary.week_end.isoformat()})",
        f"• Dias com registros: {summary.total_days_with_logs}",
        f"• Refeições registradas: {summary.meals_count}",
        f"• Média kcal/dia: {summary.average_kcal:.0f}",
        f"• Média proteína/dia: {summary.average_protein_g:.1f}g",
        f"• Média carbo/dia: {summary.average_carb_g:.1f}g",
        f"• Média gordura/dia: {summary.average_fat_g:.1f}g",
        f"• Média fibra/dia: {summary.average_fiber_g:.1f}g",
        f"• Tendência vs semana anterior: {trend}",
        f"• Aderência calórica: {summary.adherence_days}/{summary.total_days_with_logs} dias",
    ]

    if summary.top_foods:
        foods = ", ".join(f"{name} ({count}x)" for name, count in summary.top_foods[:5])
        lines.append(f"• Top alimentos: {foods}")

    return "\n".join(lines)
