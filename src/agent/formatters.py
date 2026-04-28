from src.agent.schemas import ExtractedMeal, MealItemUnit, MealType

_MEAL_EMOJI = {
    MealType.cafe_da_manha: "☕",
    MealType.almoco: "🍽️",
    MealType.jantar: "🌙",
    MealType.lanche: "🍎",
    MealType.ceia: "🌛",
}

_UNIT_LABEL = {
    MealItemUnit.g: "g",
    MealItemUnit.ml: "ml",
    MealItemUnit.unidade: "un",
    MealItemUnit.colher_sopa: "col. sopa",
    MealItemUnit.colher_cha: "col. chá",
    MealItemUnit.xicara: "xícara",
    MealItemUnit.porcao: "porção",
}


def format_extraction_reply(meal: ExtractedMeal) -> str:
    emoji = _MEAL_EMOJI.get(meal.meal_type, "🍴") if meal.meal_type else "🍴"
    label = meal.meal_type.value.replace("_", " ").title() if meal.meal_type else "Refeição"

    low_confidence = [i for i in meal.items if i.confidence < 0.6]

    lines = [f"{emoji} *{label}*", "━━━━━━━━━━━━━━━━━━"]

    for item in meal.items:
        unit = _UNIT_LABEL[item.unit]
        qty = int(item.quantity) if item.quantity == int(item.quantity) else item.quantity
        confidence_flag = " ⚠️" if item.confidence < 0.6 else ""
        lines.append(f"• {item.food.capitalize()} — {qty} {unit}{confidence_flag}")

    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("_Calculando macros… (em breve no Ckpt 4/5)_")

    if low_confidence:
        lines.append("")
        lines.append("⚠️ _Itens marcados têm quantidade estimada. Confirme se necessário._")

    if meal.notes:
        lines.append(f"\n📝 _{meal.notes}_")

    return "\n".join(lines)
