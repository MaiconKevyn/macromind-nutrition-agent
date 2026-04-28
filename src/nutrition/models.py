from dataclasses import dataclass


@dataclass(frozen=True)
class FoodEntry:
    id: int
    name: str
    category: str
    energy_kcal: float
    protein_g: float
    carb_g: float
    fat_g: float
    fiber_g: float
    sodium_mg: float
    source: str = "taco"


@dataclass(frozen=True)
class MacroResult:
    food_name: str
    quantity_g: float
    energy_kcal: float
    protein_g: float
    carb_g: float
    fat_g: float
    fiber_g: float
    source: str
    confidence: float
    matched_name: str  # nome na base que foi encontrado


@dataclass(frozen=True)
class MealMacros:
    items: tuple[MacroResult, ...]
    total_energy_kcal: float
    total_protein_g: float
    total_carb_g: float
    total_fat_g: float
    total_fiber_g: float

    @classmethod
    def from_items(cls, items: list[MacroResult]) -> "MealMacros":
        return cls(
            items=tuple(items),
            total_energy_kcal=round(sum(i.energy_kcal for i in items), 1),
            total_protein_g=round(sum(i.protein_g for i in items), 1),
            total_carb_g=round(sum(i.carb_g for i in items), 1),
            total_fat_g=round(sum(i.fat_g for i in items), 1),
            total_fiber_g=round(sum(i.fiber_g for i in items), 1),
        )
