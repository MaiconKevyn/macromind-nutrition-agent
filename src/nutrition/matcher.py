from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from src.nutrition.models import FoodEntry

_STOPWORDS = {
    "de",
    "da",
    "do",
    "com",
    "sem",
    "ao",
    "a",
    "o",
    "uma",
    "um",
    "cozido",
    "cozida",
    "grelhado",
    "grelhada",
    "refogado",
    "refogada",
}

_ALIASES = {
    "arroz": "arroz branco cozido",
    "feijao": "feijão carioca cozido",
    "feijao cozido": "feijão carioca cozido",
    "frango grelhado": "frango peito grelhado",
    "frango": "frango peito grelhado",
    "bife": "carne bovina grelhada",
    "tilapia grelhada": "filé de tilápia grelhado",
    "tilapia": "filé de tilápia grelhado",
    "salmao grelhado": "filé de salmão grelhado",
    "maca": "maçã com casca",
    "banana": "banana prata",
    "cafe": "café sem açúcar",
    "pao integral": "pão de forma integral",
    "pasta de amendoim": "pasta de amendoim integral",
    "farofa": "farofa de mandioca",
    "sassami": "filé de frango sassami",
    "frango sassami": "filé de frango sassami",
    "filezinho sassami": "filé de frango sassami",
    "filezinho sassami sadia": "filé de frango sassami sadia",
}


def normalize_food_name(text: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    cleaned = re.sub(r"[^a-z0-9\s]", " ", ascii_text)
    tokens = [token for token in cleaned.split() if token and token not in _STOPWORDS]
    normalized = " ".join(tokens)
    return _ALIASES.get(normalized, normalized)


@dataclass(frozen=True)
class MatchCandidate:
    entry: FoodEntry
    score: float


def rank_food_matches(query: str, entries: list[FoodEntry], limit: int = 5) -> list[MatchCandidate]:
    normalized_query = normalize_food_name(query)
    candidates: list[MatchCandidate] = []

    for entry in entries:
        exact_bonus = 20 if normalize_food_name(entry.name) == normalized_query else 0
        score = max(
            fuzz.token_set_ratio(normalized_query, normalize_food_name(entry.name)),
            fuzz.partial_ratio(normalized_query, normalize_food_name(entry.name)),
        )
        score = min(score + exact_bonus, 100)
        candidates.append(MatchCandidate(entry=entry, score=score))

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates[:limit]
