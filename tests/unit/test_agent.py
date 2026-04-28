"""Testes unitários do agente de extração (sem chamadas reais ao LLM)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.schemas import ExtractedMeal, MealItem, MealItemUnit, MealType


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "42")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fake")
    monkeypatch.setenv("DATABASE_URL", "")
    import src.core.config as cfg
    cfg._settings = None


def _make_meal(*items: tuple[str, float, MealItemUnit]) -> ExtractedMeal:
    return ExtractedMeal(
        items=[
            MealItem(food=f, quantity=q, unit=u, confidence=0.9, raw_phrase=f)
            for f, q, u in items
        ],
        meal_type=MealType.almoco,
    )


# ── schemas ────────────────────────────────────────────────────────────────

def test_meal_item_unit_enum() -> None:
    assert MealItemUnit.g == "g"
    assert MealItemUnit.porcao == "porcao"


def test_extracted_meal_valid() -> None:
    meal = _make_meal(("arroz branco cozido", 200, MealItemUnit.g))
    assert len(meal.items) == 1
    assert meal.items[0].food == "arroz branco cozido"
    assert meal.meal_type == MealType.almoco


def test_meal_item_confidence_bounds() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MealItem(food="arroz", quantity=100, unit=MealItemUnit.g,
                 confidence=1.5, raw_phrase="arroz")
    with pytest.raises(ValidationError):
        MealItem(food="arroz", quantity=100, unit=MealItemUnit.g,
                 confidence=-0.1, raw_phrase="arroz")


def test_meal_item_quantity_positive() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MealItem(food="arroz", quantity=0, unit=MealItemUnit.g,
                 confidence=0.9, raw_phrase="arroz")


# ── formatters ─────────────────────────────────────────────────────────────

def test_format_extraction_reply_basic() -> None:
    from src.agent.formatters import format_extraction_reply

    meal = _make_meal(
        ("arroz branco cozido", 200, MealItemUnit.g),
        ("frango grelhado", 150, MealItemUnit.g),
    )
    text = format_extraction_reply(meal)
    assert "Arroz branco cozido" in text
    assert "Frango grelhado" in text
    assert "200" in text
    assert "150" in text


def test_format_shows_warning_for_low_confidence() -> None:
    from src.agent.formatters import format_extraction_reply

    meal = ExtractedMeal(
        items=[MealItem(food="feijoada", quantity=1, unit=MealItemUnit.porcao,
                        confidence=0.4, raw_phrase="uma feijoada")],
        meal_type=MealType.almoco,
    )
    text = format_extraction_reply(meal)
    assert "⚠️" in text


# ── extraction node ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_meal_items_success() -> None:
    from src.agent.nodes import extract_meal_items

    fake_meal = _make_meal(
        ("arroz branco cozido", 200, MealItemUnit.g),
        ("frango grelhado", 150, MealItemUnit.g),
    )

    fake_block = MagicMock()
    fake_block.type = "tool_use"
    fake_block.input = fake_meal.model_dump()

    fake_response = MagicMock()
    fake_response.content = [fake_block]
    fake_response.usage.input_tokens = 120
    fake_response.usage.output_tokens = 80

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=fake_response)

    with patch("src.agent.nodes.AsyncAnthropic", return_value=mock_client):
        state = await extract_meal_items({"transcription": "comi arroz e frango"})

    assert state.get("error") is None
    meal = state.get("extracted_meal")
    assert meal is not None
    assert len(meal.items) == 2


@pytest.mark.asyncio
async def test_extract_meal_items_empty_transcription() -> None:
    from src.agent.nodes import extract_meal_items

    state = await extract_meal_items({"transcription": ""})
    assert state.get("error") == "Transcrição vazia"
    assert state.get("extracted_meal") is None


@pytest.mark.asyncio
async def test_extract_meal_items_llm_error() -> None:
    from src.agent.nodes import extract_meal_items
    from src.core.exceptions import ExtractionError

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("timeout"))

    with (
        patch("src.agent.nodes.AsyncAnthropic", return_value=mock_client),
        pytest.raises(ExtractionError, match="Falha na chamada"),
    ):
        await extract_meal_items({"transcription": "comi arroz"})
