from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.schemas import ExtractedMeal, MealItem, MealItemUnit, MealType
from src.core.exceptions import NutritionLookupError
from src.db.repository import get_daily_summary
from src.nutrition.models import FoodEntry
from src.stt.base import Transcription


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "42")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fake")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")

    import src.core.config as cfg
    import src.db.session as db_session

    cfg._settings = None
    db_session._engine = None
    db_session._session_factory = None


def _build_meal() -> ExtractedMeal:
    return ExtractedMeal(
        items=[
            MealItem(
                food="arroz branco cozido",
                quantity=200,
                unit=MealItemUnit.g,
                confidence=0.95,
                raw_phrase="200 gramas de arroz",
            ),
            MealItem(
                food="frango grelhado",
                quantity=150,
                unit=MealItemUnit.g,
                confidence=0.92,
                raw_phrase="150 gramas de frango",
            ),
        ],
        meal_type=MealType.almoco,
    )


def _mock_off_product(
    *,
    name: str,
    kcal: float,
    protein_g: float,
    carb_g: float,
    fat_g: float,
    fiber_g: float = 0.0,
) -> MagicMock:
    mock_product = MagicMock()
    mock_product.name = name
    mock_product.entry.name = name
    mock_product.entry.energy_kcal = kcal
    mock_product.entry.protein_g = protein_g
    mock_product.entry.carb_g = carb_g
    mock_product.entry.fat_g = fat_g
    mock_product.entry.fiber_g = fiber_g
    mock_product.entry.source = "openfoodfacts"
    mock_product.brand = None
    return mock_product


@pytest.mark.asyncio
async def test_meal_pipeline_persists_and_is_idempotent(tmp_path: Path) -> None:
    from src.agent.graph import run_meal_pipeline

    audio_path = tmp_path / "meal.ogg"
    audio_path.write_bytes(b"fake-audio")

    fake_stt = AsyncMock()
    fake_stt.transcribe = AsyncMock(
        return_value=Transcription(
            text="comi 200g de arroz e 150g de frango grelhado",
            language="pt",
            duration_s=5.0,
            cost_usd=0.0,
        )
    )

    with (
        patch("src.agent.nodes.get_stt_provider", return_value=fake_stt),
        patch("src.agent.nodes._call_extraction_llm", AsyncMock(return_value=_build_meal())),
        patch(
            "src.nutrition.openfoodfacts.OpenFoodFactsClient.search_products",
            return_value=[
                _mock_off_product(
                    name="Arroz branco cozido",
                    kcal=128.0,
                    protein_g=2.5,
                    carb_g=28.1,
                    fat_g=0.2,
                    fiber_g=1.6,
                ),
                _mock_off_product(
                    name="Frango grelhado",
                    kcal=165.0,
                    protein_g=31.0,
                    carb_g=0.0,
                    fat_g=3.6,
                ),
            ],
        ),
    ):
        first = await run_meal_pipeline(
            user_id=42,
            user_name="Macro User",
            source_message_id=1001,
            audio_path=str(audio_path),
            occurred_at=datetime.now(UTC),
        )
        second = await run_meal_pipeline(
            user_id=42,
            user_name="Macro User",
            source_message_id=1001,
            audio_path=str(audio_path),
            occurred_at=datetime.now(UTC),
        )

    assert first["persisted_meal"].created is True
    assert second["persisted_meal"].created is False
    assert "Total" in first["reply_text"]

    summary = get_daily_summary(42, datetime.now(UTC).date())
    assert summary.meals_count == 1
    assert summary.macros.total_energy_kcal > 0


def _make_update() -> MagicMock:
    update = MagicMock()
    update.effective_user = SimpleNamespace(id=42, full_name="Macro User")
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.reply_photo = AsyncMock()
    return update


def _make_context(args: list[str] | None = None) -> MagicMock:
    context = MagicMock()
    context.args = args or []
    return context


def _seed_meal() -> None:
    from src.db.repository import persist_meal
    from src.nutrition.repository import get_nutrition_repository

    meal = _build_meal()
    with patch(
        "src.nutrition.openfoodfacts.OpenFoodFactsClient.search_products",
        return_value=[
            _mock_off_product(
                name="Arroz branco cozido",
                kcal=128.0,
                protein_g=2.5,
                carb_g=28.1,
                fat_g=0.2,
                fiber_g=1.6,
            ),
            _mock_off_product(
                name="Frango grelhado",
                kcal=165.0,
                protein_g=31.0,
                carb_g=0.0,
                fat_g=3.6,
            ),
        ],
    ):
        resolved = get_nutrition_repository().resolve_meal(meal)
    persist_meal(
        telegram_user_id=42,
        user_name="Macro User",
        source_message_id=2001,
        raw_audio_path="data/audio/42/2001.ogg",
        transcription="comi 200g de arroz e 150g de frango grelhado",
        extracted_meal=meal,
        macros=resolved.macros,
        resolved_pairs=list(resolved.resolved_pairs),
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_commands_daily_meta_history_and_undo() -> None:
    from src.bot.handlers import commands

    _seed_meal()
    update = _make_update()

    await commands.meta(update, _make_context(["kcal=2200", "p=160", "c=220", "g=70"]))
    meta_reply = update.message.reply_text.call_args_list[-1][0][0]
    assert "Metas atualizadas" in meta_reply

    await commands.daily(update, _make_context())
    daily_reply = update.message.reply_text.call_args_list[-1][0][0]
    assert "Resumo diário" in daily_reply
    assert "Energia total" in daily_reply

    await commands.historico(update, _make_context(["7"]))
    history_reply = update.message.reply_text.call_args_list[-1][0][0]
    assert "Histórico recente" in history_reply

    await commands.desfazer(update, _make_context())
    undo_reply = update.message.reply_text.call_args_list[-1][0][0]
    assert "Última refeição removida" in undo_reply


@pytest.mark.asyncio
async def test_weekly_command_returns_summary_and_chart() -> None:
    from src.bot.handlers import commands

    _seed_meal()
    update = _make_update()

    await commands.weekly(update, _make_context())

    weekly_reply = update.message.reply_text.call_args_list[-1][0][0]
    assert "Resumo semanal" in weekly_reply
    update.message.reply_photo.assert_awaited()


def test_openfoodfacts_fallback_resolves_branded_food() -> None:
    from src.nutrition.repository import NutritionRepository

    meal_item = MealItem(
        food="filé de frango sassami",
        quantity=100,
        unit=MealItemUnit.g,
        confidence=0.92,
        raw_phrase="100g filezinho sassami sadia",
    )
    mock_product = _mock_off_product(
        name="Filé de frango sassami Sadia",
        kcal=180.0,
        protein_g=24.5,
        carb_g=0.0,
        fat_g=9.0,
    )

    repository = NutritionRepository()
    with patch.object(
        repository._openfoodfacts,
        "search_products",
        return_value=[mock_product],
    ):
        result = repository.resolve_item(meal_item)

    assert result.source == "openfoodfacts"
    assert result.matched_name == "Filé de frango sassami Sadia"
    assert result.energy_kcal == 180.0


def test_openfoodfacts_scales_macros_for_non_100g_quantity() -> None:
    from src.nutrition.repository import NutritionRepository

    meal_item = MealItem(
        food="pasta de amendoim growth",
        quantity=20,
        unit=MealItemUnit.g,
        confidence=0.95,
        raw_phrase="20g pasta de amendoim growth",
    )
    mock_product = _mock_off_product(
        name="Pasta de Amendoim Growth",
        kcal=600.0,
        protein_g=25.0,
        carb_g=20.0,
        fat_g=50.0,
        fiber_g=6.0,
    )

    repository = NutritionRepository()
    with patch.object(
        repository._openfoodfacts,
        "search_products",
        return_value=[mock_product],
    ):
        result = repository.resolve_item(meal_item)

    assert result.quantity_g == 20.0
    assert result.energy_kcal == 120.0
    assert result.protein_g == 5.0
    assert result.carb_g == 4.0
    assert result.fat_g == 10.0


def test_repository_builds_queries_without_quantity_noise() -> None:
    from src.nutrition.repository import NutritionRepository

    item = MealItem(
        food="arroz cozido tio jao",
        quantity=100,
        unit=MealItemUnit.g,
        confidence=0.9,
        raw_phrase="100g arroz cozido tio jao",
    )

    repository = NutritionRepository()
    queries = repository._build_queries(item)

    assert "100g arroz cozido tio jao" in queries
    assert "arroz cozido tio jao" in queries
    assert "arroz tio jao" in queries


def test_resolve_meal_keeps_successful_items_and_marks_missing() -> None:
    from src.nutrition.repository import NutritionRepository

    repository = NutritionRepository()
    meal = ExtractedMeal(
        items=[
            MealItem(
                food="sassami sadia",
                quantity=100,
                unit=MealItemUnit.g,
                confidence=0.95,
                raw_phrase="100g sassami sadia",
            ),
            MealItem(
                food="arroz cozido tio joão",
                quantity=100,
                unit=MealItemUnit.g,
                confidence=0.9,
                raw_phrase="100g arroz cozido tio joão",
            ),
        ]
    )

    with patch.object(
        repository,
        "resolve_item",
        side_effect=[
            repository._build_macro_result(
                meal.items[0],
                100.0,
                FoodEntry(
                    id=0,
                    name="Sassami Sadia",
                    category="branded_food",
                    energy_kcal=106.0,
                    protein_g=23.0,
                    carb_g=0.0,
                    fat_g=1.5,
                    fiber_g=0.0,
                    sodium_mg=0.0,
                    source="openfoodfacts",
                ),
                0.95,
            ),
            NutritionLookupError("missing"),
        ],
    ):
        resolved = repository.resolve_meal(meal)

    assert len(resolved.macros.items) == 1
    assert resolved.macros.items[0].matched_name == "Sassami Sadia"
    assert resolved.missing_items == ("arroz cozido tio joão",)
