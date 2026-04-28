from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from eval.metrics import compute_item_f1
from src.agent.graph import run_extraction
from src.nutrition.repository import get_nutrition_repository


async def main() -> None:
    parser = argparse.ArgumentParser(description="Roda eval simples de extração e matching.")
    parser.add_argument(
        "--dataset",
        default="eval/datasets/meals_ptbr.jsonl",
        help="Caminho do dataset jsonl.",
    )
    parser.add_argument(
        "--output",
        default="eval/results/latest.md",
        help="Arquivo markdown de saída.",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    extraction_scores: list[float] = []
    matching_hits = 0
    matching_total = 0
    lines = ["# Eval MacroMind", ""]

    for raw_line in dataset_path.read_text(encoding="utf-8").splitlines():
        sample = json.loads(raw_line)
        state = await run_extraction(sample["transcription"])
        meal = state.get("extracted_meal")
        predicted_items = [item.food for item in meal.items] if meal else []

        metrics = compute_item_f1(sample["expected_items"], predicted_items)
        extraction_scores.append(metrics.f1)

        repo = get_nutrition_repository()
        for expected in sample["expected_items"]:
            matching_total += 1
            candidates = repo._load_entries(Path("data/taco_br.csv"))
            top = max(
                candidates,
                key=lambda entry: 100
                if expected.lower() in entry.name.lower()
                else 0,
            )
            if expected.lower() in top.name.lower():
                matching_hits += 1

        lines.append(f"## Caso {sample['id']}")
        lines.append(f"- Transcrição: {sample['transcription']}")
        lines.append(f"- Esperado: {', '.join(sample['expected_items'])}")
        lines.append(f"- Predito: {', '.join(predicted_items) if predicted_items else '(nenhum)'}")
        lines.append(f"- F1: {metrics.f1:.2f}")
        lines.append("")

    avg_f1 = sum(extraction_scores) / max(len(extraction_scores), 1)
    matching_acc = matching_hits / max(matching_total, 1)
    summary = [
        "# Resumo",
        "",
        f"- F1 médio de extração: {avg_f1:.2f}",
        f"- Matching top-1 aproximado: {matching_acc:.2f}",
        "",
    ]

    output_path.write_text("\n".join(summary + lines), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
