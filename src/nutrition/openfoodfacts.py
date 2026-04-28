from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import httpx
from rapidfuzz import fuzz

from src.nutrition.models import FoodEntry

_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
_USER_AGENT = "MacroMindNutritionAgent/0.1 (+https://github.com/openai)"


@dataclass(frozen=True)
class OpenFoodFactsProduct:
    code: str
    name: str
    brand: str | None
    entry: FoodEntry


class OpenFoodFactsClient:
    def __init__(self, timeout_s: float = 5.0) -> None:
        self._timeout_s = timeout_s

    def search_products(self, query: str) -> list[OpenFoodFactsProduct]:
        params: dict[str, str | int] = {
            "search_terms": query,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "nocache": 1,
            "page_size": 20,
            "lc": "pt",
            "fields": (
                "code,product_name,brands,nutriments,"
                "nutriscore_data,quantity,product_quantity,serving_quantity"
            ),
        }
        headers = {"User-Agent": _USER_AGENT}

        with httpx.Client(timeout=self._timeout_s, headers=headers) as client:
            response = client.get(_SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        products = payload.get("products", [])
        parsed_products: list[OpenFoodFactsProduct] = []
        for product in products:
            parsed = self._parse_product(product)
            if parsed is not None:
                parsed_products.append(parsed)
        return parsed_products

    def _parse_product(self, product: dict[str, object]) -> OpenFoodFactsProduct | None:
        nutriments = product.get("nutriments")
        product_name = product.get("product_name")
        code = product.get("code")

        if not isinstance(nutriments, dict):
            return None
        if not isinstance(product_name, str) or not product_name.strip():
            return None
        if not isinstance(code, str) or not code.strip():
            return None

        kcal = _to_float(nutriments.get("energy-kcal_100g"))
        protein = _to_float(nutriments.get("proteins_100g"))
        carbs = _to_float(nutriments.get("carbohydrates_100g"))
        fat = _to_float(nutriments.get("fat_100g"))
        fiber = _to_float(nutriments.get("fiber_100g")) or 0.0
        sodium = _to_float(nutriments.get("sodium_100g")) or 0.0

        if kcal is None or protein is None or carbs is None or fat is None:
            return None

        entry = FoodEntry(
            id=0,
            name=product_name.strip(),
            category="branded_food",
            energy_kcal=kcal,
            protein_g=protein,
            carb_g=carbs,
            fat_g=fat,
            fiber_g=fiber,
            sodium_mg=sodium * 1000.0,
            source="openfoodfacts",
        )
        brand = product.get("brands")
        return OpenFoodFactsProduct(
            code=code.strip(),
            name=product_name.strip(),
            brand=brand.strip() if isinstance(brand, str) and brand.strip() else None,
            entry=entry,
        )


def _to_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def score_product_match(query: str, product: OpenFoodFactsProduct) -> float:
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return 0.0

    product_text = product.name
    if product.brand:
        product_text = f"{product.name} {product.brand}"
    normalized_product = _normalize_text(product_text)

    query_tokens = _normalize_tokens(normalized_query)
    product_tokens = _normalize_tokens(normalized_product)
    if not query_tokens or not product_tokens:
        return 0.0

    overlap = len(set(query_tokens) & set(product_tokens))
    coverage = overlap / len(set(query_tokens))
    extra_tokens = max(0, len(set(product_tokens) - set(query_tokens)))

    base_score = max(
        fuzz.ratio(normalized_query, normalized_product),
        fuzz.token_sort_ratio(normalized_query, normalized_product),
    )
    score = (base_score * 0.7) + (coverage * 100 * 0.3) - (extra_tokens * 2)
    return max(0.0, min(100.0, score))


def _normalize_text(text: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    cleaned = re.sub(r"[^a-z0-9\s]", " ", ascii_text)
    return " ".join(cleaned.split())


def _normalize_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for token in text.split():
        if len(token) > 4 and token.endswith("s"):
            token = token[:-1]
        tokens.append(token)
    return tokens
