from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

from src.agent.schemas import ExtractedMeal, MealItem
from src.core.exceptions import NutritionLookupError
from src.nutrition.models import FoodEntry, MacroResult, MealMacros
from src.nutrition.openfoodfacts import (
    OpenFoodFactsClient,
    OpenFoodFactsProduct,
    score_product_match,
)
from src.nutrition.unit_converter import to_grams

_OPENFOODFACTS_MATCH_THRESHOLD = 60
_MEASUREMENT_PATTERN = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:g|gr|grama|gramas|kg|ml|l|un|unidade|unidades|"
    r"colher|colheres|xicara|xicaras|porcao|porcoes)\b",
    flags=re.IGNORECASE,
)
_NOISE_PATTERN = re.compile(r"\b(?:de|da|do|com|e)\b", flags=re.IGNORECASE)
_PREPARATION_PATTERN = re.compile(
    r"\b(?:cozido|cozida|grelhado|grelhada|refogado|refogada|assado|assada)\b",
    flags=re.IGNORECASE,
)
logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ResolvedMeal:
    macros: MealMacros
    resolved_pairs: tuple[tuple[MealItem, MacroResult], ...]
    missing_items: tuple[str, ...]


class NutritionRepository:
    def __init__(self) -> None:
        self._openfoodfacts = OpenFoodFactsClient()

    def resolve_item(self, item: MealItem) -> MacroResult:
        quantity_g = round(to_grams(item.food, item.quantity, item.unit), 1)
        logger.info(
            "nutrition_lookup_start",
            food=item.food,
            raw_phrase=item.raw_phrase,
            quantity=item.quantity,
            unit=item.unit.value,
            quantity_g=quantity_g,
        )
        off_result = self._resolve_with_openfoodfacts(item, quantity_g)
        if off_result is None:
            logger.warning(
                "nutrition_lookup_not_found",
                food=item.food,
                raw_phrase=item.raw_phrase,
            )
            raise NutritionLookupError(
                f"Não encontrei produto confiável no Open Food Facts para '{item.food}'"
            )
        logger.info(
            "nutrition_lookup_resolved",
            food=item.food,
            matched_name=off_result.matched_name,
            source=off_result.source,
            quantity_g=off_result.quantity_g,
            kcal=off_result.energy_kcal,
            protein_g=off_result.protein_g,
            carb_g=off_result.carb_g,
            fat_g=off_result.fat_g,
        )
        return off_result

    def _build_macro_result(
        self,
        item: MealItem,
        quantity_g: float,
        entry: FoodEntry,
        match_confidence: float,
    ) -> MacroResult:
        factor = quantity_g / 100.0
        confidence = min(1.0, round((match_confidence + item.confidence) / 2, 2))
        return MacroResult(
            food_name=item.food,
            quantity_g=quantity_g,
            energy_kcal=round(entry.energy_kcal * factor, 1),
            protein_g=round(entry.protein_g * factor, 1),
            carb_g=round(entry.carb_g * factor, 1),
            fat_g=round(entry.fat_g * factor, 1),
            fiber_g=round(entry.fiber_g * factor, 1),
            source=entry.source,
            confidence=confidence,
            matched_name=entry.name,
        )

    def _resolve_with_openfoodfacts(
        self,
        item: MealItem,
        quantity_g: float,
    ) -> MacroResult | None:
        queries = self._build_queries(item)
        seen_queries: set[str] = set()
        best_product: OpenFoodFactsProduct | None = None
        best_score = 0.0

        for query in queries:
            normalized_query = " ".join(query.split()).strip()
            if not normalized_query or normalized_query in seen_queries:
                continue
            seen_queries.add(normalized_query)

            try:
                products = self._openfoodfacts.search_products(normalized_query)
            except Exception as exc:
                logger.warning(
                    "openfoodfacts_query_failed",
                    food=item.food,
                    query=normalized_query,
                    error=str(exc),
                )
                continue
            logger.info(
                "openfoodfacts_query_results",
                food=item.food,
                query=normalized_query,
                results=len(products),
            )
            for product in products:
                score = max(
                    score_product_match(item.raw_phrase, product),
                    score_product_match(item.food, product),
                    score_product_match(normalized_query, product),
                )
                logger.info(
                    "openfoodfacts_candidate_scored",
                    food=item.food,
                    query=normalized_query,
                    candidate_name=product.name,
                    candidate_brand=product.brand,
                    score=round(score, 2),
                )
                if score > best_score:
                    best_product = product
                    best_score = score

        if best_product is None or best_score < _OPENFOODFACTS_MATCH_THRESHOLD:
            logger.warning(
                "openfoodfacts_best_match_rejected",
                food=item.food,
                best_score=round(best_score, 2),
                threshold=_OPENFOODFACTS_MATCH_THRESHOLD,
                matched_name=best_product.name if best_product is not None else None,
            )
            return None

        return self._build_macro_result(
            item,
            quantity_g,
            best_product.entry,
            best_score / 100.0,
        )

    def _build_queries(self, item: MealItem) -> list[str]:
        raw_phrase = item.raw_phrase.strip()
        food = item.food.strip()
        stripped_raw = _strip_measurements(raw_phrase)
        stripped_food = _strip_measurements(food)

        queries = [
            raw_phrase,
            food,
            stripped_raw,
            stripped_food,
            _compact_query(raw_phrase),
            _compact_query(food),
            _compact_query(stripped_raw),
            _compact_query(stripped_food),
        ]

        if stripped_raw and stripped_food and stripped_food not in stripped_raw:
            queries.append(f"{stripped_food} {stripped_raw}")

        return [query for query in queries if query]

    def resolve_meal(self, meal: ExtractedMeal) -> ResolvedMeal:
        items: list[MacroResult] = []
        resolved_pairs: list[tuple[MealItem, MacroResult]] = []
        missing_items: list[str] = []

        for item in meal.items:
            try:
                result = self.resolve_item(item)
                items.append(result)
                resolved_pairs.append((item, result))
            except NutritionLookupError:
                missing_items.append(item.food)
            except Exception as exc:
                logger.exception(
                    "nutrition_lookup_unexpected_error",
                    food=item.food,
                    raw_phrase=item.raw_phrase,
                    error=str(exc),
                )
                missing_items.append(item.food)

        if not items:
            raise NutritionLookupError(
                "Nenhum item da refeição pôde ser resolvido no Open Food Facts: "
                + ", ".join(missing_items)
            )

        return ResolvedMeal(
            macros=MealMacros.from_items(items),
            resolved_pairs=tuple(resolved_pairs),
            missing_items=tuple(missing_items),
        )


_repository: NutritionRepository | None = None


def get_nutrition_repository() -> NutritionRepository:
    global _repository
    if _repository is None:
        _repository = NutritionRepository()
    return _repository


def _strip_measurements(text: str) -> str:
    without_measures = _MEASUREMENT_PATTERN.sub(" ", text)
    without_lonely_numbers = re.sub(r"\b\d+(?:[.,]\d+)?\b", " ", without_measures)
    return " ".join(without_lonely_numbers.split())


def _compact_query(text: str) -> str:
    text = _strip_measurements(text)
    text = _PREPARATION_PATTERN.sub(" ", text)
    text = _NOISE_PATTERN.sub(" ", text)
    return " ".join(text.split())
