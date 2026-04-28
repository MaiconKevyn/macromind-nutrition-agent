from datetime import UTC, datetime
from pathlib import Path

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, ToolChoiceToolParam, ToolParam
from tenacity import retry, stop_after_attempt, wait_exponential

from src.agent.formatters import format_extraction_reply
from src.agent.schemas import ExtractedMeal
from src.agent.state import AgentState
from src.core.config import get_settings
from src.core.exceptions import ExtractionError, NutritionLookupError, STTError
from src.db.repository import persist_meal
from src.nutrition.repository import get_nutrition_repository
from src.reports.formatters import format_registered_meal_reply
from src.stt.factory import get_stt_provider

logger = structlog.get_logger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "extract_meal.md"
_TOOL_NAME = "extract_meal"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_tool_definition() -> ToolParam:
    schema = ExtractedMeal.model_json_schema()
    return ToolParam(
        name=_TOOL_NAME,
        description="Extrai itens alimentares de uma transcrição de refeição em PT-BR.",
        input_schema=schema,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def _call_extraction_llm(transcription: str) -> ExtractedMeal:
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.require_anthropic_key())

    messages: list[MessageParam] = [{"role": "user", "content": transcription}]
    tool_choice = ToolChoiceToolParam(type="tool", name=_TOOL_NAME)
    response = await client.messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        system=_load_system_prompt(),
        tools=[_build_tool_definition()],
        tool_choice=tool_choice,
        messages=messages,
    )

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        raise ExtractionError("LLM não retornou tool_use")

    try:
        meal = ExtractedMeal.model_validate(tool_block.input)
    except Exception as exc:
        raise ExtractionError(f"Resposta do LLM inválida: {exc}") from exc

    logger.info(
        "extraction_done",
        items=len(meal.items),
        meal_type=meal.meal_type,
        avg_confidence=round(
            sum(i.confidence for i in meal.items) / max(len(meal.items), 1), 2
        ),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    return meal


async def transcribe_audio(state: AgentState) -> AgentState:
    raw_transcription = state.get("transcription")
    existing_transcription = raw_transcription.strip() if raw_transcription else ""
    if existing_transcription:
        logger.info("transcription_reused", chars=len(existing_transcription))
        return {**state, "transcription": existing_transcription, "error": None}

    audio_path_raw = state.get("audio_path")
    if not audio_path_raw:
        return {**state, "error": "Áudio ausente"}

    audio_path = Path(audio_path_raw)
    try:
        stt_result = await get_stt_provider().transcribe(audio_path)
    except STTError as exc:
        raise STTError(f"Falha ao transcrever áudio '{audio_path.name}': {exc}") from exc

    return {**state, "transcription": stt_result.text, "error": None}


async def extract_meal_items(state: AgentState) -> AgentState:
    transcription = (
        state.get("transcription_for_extraction")
        or state.get("transcription", "")
    ).strip()
    if not transcription:
        return {**state, "error": "Transcrição vazia"}

    logger.info("extraction_start", chars=len(transcription), model=get_settings().llm_model)

    try:
        meal = await _call_extraction_llm(transcription)
    except Exception as exc:
        raise ExtractionError(f"Falha na chamada ao LLM: {exc}") from exc

    meal_type_override = state.get("meal_type_override")
    if meal_type_override is not None:
        meal = meal.model_copy(update={"meal_type": meal_type_override})

    return {**state, "extracted_meal": meal, "error": None}


async def resolve_nutrition(state: AgentState) -> AgentState:
    meal = state.get("extracted_meal")
    if meal is None:
        return {**state, "error": "Refeição não extraída"}

    try:
        resolved = get_nutrition_repository().resolve_meal(meal)
    except NutritionLookupError as exc:
        raise NutritionLookupError(f"Falha ao calcular macros: {exc}") from exc

    return {
        **state,
        "resolved_macros": resolved.macros,
        "resolved_pairs": list(resolved.resolved_pairs),
        "missing_items": resolved.missing_items,
        "error": None,
    }


async def persist_meal_node(state: AgentState) -> AgentState:
    meal = state.get("extracted_meal")
    macros = state.get("resolved_macros")
    resolved_pairs = state.get("resolved_pairs")
    if meal is None or macros is None or not resolved_pairs:
        return {**state, "error": "Não há refeição resolvida para persistir"}

    persisted = persist_meal(
        telegram_user_id=state["user_id"],
        user_name=state.get("user_name"),
        source_message_id=state["source_message_id"],
        raw_audio_path=state["audio_path"],
        transcription=state.get("transcription", ""),
        extracted_meal=meal,
        macros=macros,
        resolved_pairs=resolved_pairs,
        occurred_at=state.get("occurred_at", datetime.now(UTC)),
    )

    return {**state, "persisted_meal": persisted, "error": None}


async def format_meal_reply(state: AgentState) -> AgentState:
    meal = state.get("extracted_meal")
    macros = state.get("resolved_macros")
    persisted = state.get("persisted_meal")
    if meal is None or macros is None or persisted is None:
        return {**state, "reply_text": format_extraction_reply(meal) if meal else None}

    reply = format_registered_meal_reply(
        meal_type=persisted.meal_type,
        macros=macros,
        missing_items=state.get("missing_items", ()),
        duplicated=not persisted.created,
    )
    return {**state, "reply_text": reply, "error": None}
