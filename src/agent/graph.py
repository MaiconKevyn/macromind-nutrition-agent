from datetime import datetime

from langgraph.graph import END, START, StateGraph

from src.agent.nodes import (
    extract_meal_items,
    format_meal_reply,
    persist_meal_node,
    resolve_nutrition,
    transcribe_audio,
)
from src.agent.schemas import MealType
from src.agent.state import AgentState


def build_graph() -> StateGraph:  # type: ignore[type-arg]
    g: StateGraph = StateGraph(AgentState)  # type: ignore[type-arg]
    g.add_node("transcribe_audio", transcribe_audio)
    g.add_node("extract_meal_items", extract_meal_items)
    g.add_node("resolve_nutrition", resolve_nutrition)
    g.add_node("persist_meal", persist_meal_node)
    g.add_node("format_meal_reply", format_meal_reply)
    g.add_edge(START, "transcribe_audio")
    g.add_edge("transcribe_audio", "extract_meal_items")
    g.add_edge("extract_meal_items", "resolve_nutrition")
    g.add_edge("resolve_nutrition", "persist_meal")
    g.add_edge("persist_meal", "format_meal_reply")
    g.add_edge("format_meal_reply", END)
    return g


# grafo compilado — reutilizado entre chamadas
_compiled = build_graph().compile()


async def run_extraction(transcription: str) -> AgentState:
    extraction_graph: StateGraph = StateGraph(AgentState)  # type: ignore[type-arg]
    extraction_graph.add_node("extract_meal_items", extract_meal_items)
    extraction_graph.add_edge(START, "extract_meal_items")
    extraction_graph.add_edge("extract_meal_items", END)
    compiled = extraction_graph.compile()
    result: AgentState = await compiled.ainvoke({"transcription": transcription})  # type: ignore[assignment]
    return result


async def run_meal_pipeline(
    *,
    user_id: int,
    user_name: str | None,
    source_message_id: int,
    audio_path: str,
    occurred_at: datetime,
    transcription: str | None = None,
    transcription_for_extraction: str | None = None,
    meal_type_override: MealType | None = None,
) -> AgentState:
    payload: AgentState = {
        "user_id": user_id,
        "user_name": user_name,
        "source_message_id": source_message_id,
        "audio_path": audio_path,
        "occurred_at": occurred_at,
    }
    if transcription is not None:
        payload["transcription"] = transcription
    if transcription_for_extraction is not None:
        payload["transcription_for_extraction"] = transcription_for_extraction
    if meal_type_override is not None:
        payload["meal_type_override"] = meal_type_override

    result: AgentState = await _compiled.ainvoke(payload)  # type: ignore[assignment]
    return result
