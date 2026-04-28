from __future__ import annotations

from datetime import date

from src.db.repository import DaySummary, GoalSnapshot, HistoryDay
from src.nutrition.models import MealMacros

_MEAL_TYPE_LABELS = {
    "cafe_da_manha": "café da manhã",
    "almoco": "almoço",
    "jantar": "jantar",
    "lanche": "lanche",
    "ceia": "ceia",
    "pre_treino": "pré-treino",
    "pos_treino": "pós-treino",
    "janta": "janta",
}


def _format_meal_type(meal_type: str) -> str:
    return _MEAL_TYPE_LABELS.get(meal_type, meal_type.replace("_", " "))


def _pct(value: float, goal: float | None) -> str:
    if not goal:
        return "n/d"
    return f"{round((value / goal) * 100):.0f}%"


def _goal_line(label: str, value: float, goal: float | None) -> str:
    goal_label = "-" if goal is None else f"{goal:.0f}"
    return f"• {label}: {value:.1f} / {goal_label} ({_pct(value, goal)})"


def format_registered_meal_reply(
    *,
    meal_type: str | None,
    macros: MealMacros,
    missing_items: tuple[str, ...] = (),
    duplicated: bool = False,
) -> str:
    header = "🍽️ *Refeição já registrada*" if duplicated else "🍽️ *Refeição registrada*"
    if meal_type:
        header = f"{header} ({_format_meal_type(meal_type)})"

    lines = [header, "━━━━━━━━━━━━━━━━━━━━━"]
    for item in macros.items:
        lines.append(
            f"• {item.food_name.capitalize()} — {item.quantity_g:.0f}g "
            f"({_format_macro_item(item.energy_kcal, item.protein_g, item.carb_g, item.fat_g)})"
        )

    lines.extend(
        [
            "━━━━━━━━━━━━━━━━━━━━━",
            f"📊 *Total:* {macros.total_energy_kcal:.0f} kcal",
            (
                f"   P: {macros.total_protein_g:.1f}g  "
                f"C: {macros.total_carb_g:.1f}g  "
                f"G: {macros.total_fat_g:.1f}g  "
                f"Fib: {macros.total_fiber_g:.1f}g"
            ),
        ]
    )

    if missing_items:
        joined = ", ".join(missing_items)
        lines.append("")
        lines.append(f"⚠️ Itens sem correspondência no Open Food Facts: {joined}.")

    return "\n".join(lines)


def _format_macro_item(kcal: float, protein_g: float, carb_g: float, fat_g: float) -> str:
    return f"{kcal:.0f} kcal, P {protein_g:.1f}g, C {carb_g:.1f}g, G {fat_g:.1f}g"


def format_daily_summary(summary: DaySummary) -> str:
    lines = [
        f"📊 *Resumo diário* ({summary.target_date.isoformat()})",
        f"• Refeições registradas: {summary.meals_count}",
        f"• Energia total: {summary.macros.total_energy_kcal:.0f} kcal",
        f"• Proteína: {summary.macros.total_protein_g:.1f}g",
        f"• Carboidratos: {summary.macros.total_carb_g:.1f}g",
        f"• Gorduras: {summary.macros.total_fat_g:.1f}g",
        f"• Fibras: {summary.macros.total_fiber_g:.1f}g",
    ]

    if summary.goal is not None:
        lines.append("")
        lines.append("🎯 *Metas*")
        lines.append(_goal_line("Kcal", summary.macros.total_energy_kcal, summary.goal.kcal))
        lines.append(_goal_line("Proteína", summary.macros.total_protein_g, summary.goal.protein_g))
        lines.append(_goal_line("Carbo", summary.macros.total_carb_g, summary.goal.carb_g))
        lines.append(_goal_line("Gordura", summary.macros.total_fat_g, summary.goal.fat_g))
        if summary.goal.fiber_g is not None:
            lines.append(_goal_line("Fibra", summary.macros.total_fiber_g, summary.goal.fiber_g))

    return "\n".join(lines)


def format_goal_snapshot(goal: GoalSnapshot) -> str:
    return "\n".join(
        [
            "🎯 *Metas atualizadas*",
            f"• Kcal: {_fmt_goal(goal.kcal)}",
            f"• Proteína: {_fmt_goal(goal.protein_g)}g",
            f"• Carboidratos: {_fmt_goal(goal.carb_g)}g",
            f"• Gorduras: {_fmt_goal(goal.fat_g)}g",
            f"• Fibras: {_fmt_goal(goal.fiber_g)}g",
        ]
    )


def _fmt_goal(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def format_history(history: list[HistoryDay]) -> str:
    if not history:
        return "📅 Nenhum registro encontrado no período."

    lines = ["📅 *Histórico recente*"]
    for day in history:
        lines.append(
            f"• {day.target_date.isoformat()} — {day.total_kcal:.0f} kcal "
            f"(P {day.total_protein_g:.1f}g / C {day.total_carb_g:.1f}g "
            f"/ G {day.total_fat_g:.1f}g, "
            f"{day.meals_count} refeição(ões))"
        )
    return "\n".join(lines)


def format_undo_result(target_date: date, macros: MealMacros) -> str:
    return (
        f"↩️ Última refeição removida de {target_date.isoformat()}.\n"
        f"Impacto: {macros.total_energy_kcal:.0f} kcal, "
        f"P {macros.total_protein_g:.1f}g, C {macros.total_carb_g:.1f}g, "
        f"G {macros.total_fat_g:.1f}g."
    )
