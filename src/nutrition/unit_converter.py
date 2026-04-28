from src.agent.schemas import MealItemUnit

# gramas por unidade padrão para alimentos específicos
_FOOD_UNIT_OVERRIDES: dict[str, dict[MealItemUnit, float]] = {
    "ovo": {MealItemUnit.unidade: 50.0},
    "banana": {MealItemUnit.unidade: 100.0},
    "maçã": {MealItemUnit.unidade: 130.0},
    "laranja": {MealItemUnit.unidade: 150.0},
    "manga": {MealItemUnit.unidade: 200.0},
    "pão francês": {MealItemUnit.unidade: 50.0},
    "fatia de pão": {MealItemUnit.unidade: 25.0},
    "biscoito": {MealItemUnit.unidade: 10.0},
    "fatia": {MealItemUnit.unidade: 30.0},
}

# padrões gerais por categoria de unidade (gramas)
_DEFAULT_GRAMS: dict[MealItemUnit, float] = {
    MealItemUnit.g: 1.0,
    MealItemUnit.ml: 1.0,       # aprox. para a maioria dos líquidos
    MealItemUnit.unidade: 100.0,
    MealItemUnit.colher_sopa: 15.0,
    MealItemUnit.colher_cha: 5.0,
    MealItemUnit.xicara: 200.0,
    MealItemUnit.porcao: 100.0,
}

# overrides por tipo de alimento + unidade colher_sopa (gramas)
_COLHER_SOPA_OVERRIDES: dict[str, float] = {
    "arroz": 25.0,
    "feijão": 20.0,
    "farinha": 10.0,
    "açúcar": 12.0,
    "mel": 20.0,
    "azeite": 13.0,
    "óleo": 13.0,
    "manteiga": 15.0,
    "pasta de amendoim": 32.0,
    "requeijão": 30.0,
}


def to_grams(food_name: str, quantity: float, unit: MealItemUnit) -> float:
    food_lower = food_name.lower()

    if unit == MealItemUnit.g or unit == MealItemUnit.ml:
        return quantity

    # overrides específicos por alimento
    for key, overrides in _FOOD_UNIT_OVERRIDES.items():
        if key in food_lower and unit in overrides:
            return quantity * overrides[unit]

    # override de colher de sopa por tipo de alimento
    if unit == MealItemUnit.colher_sopa:
        for key, grams in _COLHER_SOPA_OVERRIDES.items():
            if key in food_lower:
                return quantity * grams

    return quantity * _DEFAULT_GRAMS[unit]
