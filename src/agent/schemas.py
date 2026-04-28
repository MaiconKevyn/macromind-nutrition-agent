from enum import StrEnum

from pydantic import BaseModel, Field


class MealItemUnit(StrEnum):
    g = "g"
    ml = "ml"
    unidade = "unidade"
    colher_sopa = "colher_sopa"
    colher_cha = "colher_cha"
    xicara = "xicara"
    porcao = "porcao"


class MealType(StrEnum):
    cafe_da_manha = "cafe_da_manha"
    almoco = "almoco"
    jantar = "jantar"
    lanche = "lanche"
    ceia = "ceia"
    pre_treino = "pre_treino"
    pos_treino = "pos_treino"
    janta = "janta"


class MealItem(BaseModel):
    food: str = Field(
        description="Nome do alimento normalizado em português, sem adjetivos redundantes"
    )
    quantity: float = Field(gt=0, description="Quantidade numérica")
    unit: MealItemUnit = Field(description="Unidade de medida")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confiança na extração (0=incerto, 1=certeza)"
    )
    raw_phrase: str = Field(description="Trecho exato da transcrição que originou este item")


class ExtractedMeal(BaseModel):
    items: list[MealItem] = Field(description="Lista de itens alimentares identificados")
    meal_type: MealType | None = Field(
        default=None, description="Tipo de refeição, se identificável"
    )
    notes: str | None = Field(
        default=None, description="Observações relevantes não capturadas nos itens"
    )
