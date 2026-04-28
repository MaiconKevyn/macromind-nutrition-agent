from datetime import datetime
from typing import TypedDict

from src.agent.schemas import ExtractedMeal, MealItem, MealType
from src.db.repository import PersistedMeal
from src.nutrition.models import MacroResult, MealMacros


class AgentState(TypedDict, total=False):
    user_id: int
    user_name: str | None
    source_message_id: int
    audio_path: str
    occurred_at: datetime
    transcription: str
    transcription_for_extraction: str | None
    meal_type_override: MealType | None
    extracted_meal: ExtractedMeal | None
    resolved_macros: MealMacros | None
    resolved_pairs: list[tuple[MealItem, MacroResult]]
    persisted_meal: PersistedMeal | None
    missing_items: tuple[str, ...]
    reply_text: str | None
    error: str | None
