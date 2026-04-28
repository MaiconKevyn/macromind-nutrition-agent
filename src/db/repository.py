from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Select, desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from src.agent.schemas import ExtractedMeal, MealItem
from src.core.exceptions import DatabaseError
from src.db.models import DailyGoal, Meal, MealItemRecord, User
from src.db.session import session_scope
from src.nutrition.models import MacroResult, MealMacros


@dataclass(frozen=True)
class GoalSnapshot:
    kcal: float | None
    protein_g: float | None
    carb_g: float | None
    fat_g: float | None
    fiber_g: float | None


@dataclass(frozen=True)
class DaySummary:
    target_date: date
    meals_count: int
    macros: MealMacros
    goal: GoalSnapshot | None


@dataclass(frozen=True)
class HistoryDay:
    target_date: date
    meals_count: int
    total_kcal: float
    total_protein_g: float
    total_carb_g: float
    total_fat_g: float


@dataclass(frozen=True)
class PersistedMeal:
    id: int
    created: bool
    macros: MealMacros
    meal_type: str | None
    occurred_at: datetime


def _utc_day_bounds(target_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(target_date, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)
    return start, end


def _get_or_create_user(session: Session, telegram_id: int, name: str | None) -> User:
    user = session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is not None:
        if name and user.name != name:
            user.name = name
        return user

    user = User(telegram_id=telegram_id, name=name)
    session.add(user)
    session.flush()
    return user


def _meal_to_macros(meal: Meal) -> MealMacros:
    items = [
        MacroResult(
            food_name=item.food_name,
            quantity_g=item.quantity_g,
            energy_kcal=item.kcal,
            protein_g=item.protein_g,
            carb_g=item.carb_g,
            fat_g=item.fat_g,
            fiber_g=item.fiber_g,
            source=item.source,
            confidence=item.confidence,
            matched_name=item.matched_food_name,
        )
        for item in meal.items
    ]
    return MealMacros.from_items(items)


def persist_meal(
    *,
    telegram_user_id: int,
    user_name: str | None,
    source_message_id: int,
    raw_audio_path: str,
    transcription: str,
    extracted_meal: ExtractedMeal,
    macros: MealMacros,
    resolved_pairs: list[tuple[MealItem, MacroResult]],
    occurred_at: datetime,
) -> PersistedMeal:
    try:
        with session_scope() as session:
            user = _get_or_create_user(session, telegram_user_id, user_name)

            existing = session.scalar(
                select(Meal)
                .options(selectinload(Meal.items))
                .where(Meal.user_id == user.id, Meal.source_message_id == source_message_id)
            )
            if existing is not None:
                return PersistedMeal(
                    id=existing.id,
                    created=False,
                    macros=_meal_to_macros(existing),
                    meal_type=existing.meal_type,
                    occurred_at=existing.occurred_at,
                )

            avg_confidence = sum(item.confidence for item in extracted_meal.items) / max(
                len(extracted_meal.items), 1
            )
            meal = Meal(
                user_id=user.id,
                source_message_id=source_message_id,
                raw_audio_path=raw_audio_path,
                transcription=transcription,
                meal_type=extracted_meal.meal_type.value if extracted_meal.meal_type else None,
                confidence=avg_confidence,
                occurred_at=occurred_at,
            )
            session.add(meal)
            session.flush()

            for extracted_item, macro_item in resolved_pairs:
                session.add(
                    MealItemRecord(
                        meal_id=meal.id,
                        food_name=macro_item.food_name,
                        quantity=extracted_item.quantity,
                        unit=extracted_item.unit.value,
                        quantity_g=macro_item.quantity_g,
                        matched_food_name=macro_item.matched_name,
                        source=macro_item.source,
                        confidence=macro_item.confidence,
                        kcal=macro_item.energy_kcal,
                        protein_g=macro_item.protein_g,
                        carb_g=macro_item.carb_g,
                        fat_g=macro_item.fat_g,
                        fiber_g=macro_item.fiber_g,
                        raw_phrase=extracted_item.raw_phrase,
                    )
                )

            return PersistedMeal(
                id=meal.id,
                created=True,
                macros=macros,
                meal_type=meal.meal_type,
                occurred_at=meal.occurred_at,
            )
    except SQLAlchemyError as exc:
        raise DatabaseError(f"Falha ao persistir refeição: {exc}") from exc


def _meals_for_range(
    session: Session,
    telegram_user_id: int,
    start: datetime,
    end: datetime,
) -> list[Meal]:
    query: Select[tuple[Meal]] = (
        select(Meal)
        .join(User, User.id == Meal.user_id)
        .options(selectinload(Meal.items))
        .where(
            User.telegram_id == telegram_user_id,
            Meal.occurred_at >= start,
            Meal.occurred_at < end,
        )
        .order_by(Meal.occurred_at.asc())
    )
    return list(session.scalars(query))


def _sum_meals(meals: list[Meal]) -> MealMacros:
    items: list[MacroResult] = []
    for meal in meals:
        items.extend(_meal_to_macros(meal).items)
    return MealMacros.from_items(items)


def get_active_goal(telegram_user_id: int, target_date: date) -> GoalSnapshot | None:
    with session_scope() as session:
        start, _ = _utc_day_bounds(target_date)
        goal = session.scalar(
            select(DailyGoal)
            .join(User, User.id == DailyGoal.user_id)
            .where(User.telegram_id == telegram_user_id, DailyGoal.valid_from <= start)
            .order_by(DailyGoal.valid_from.desc())
        )
        if goal is None:
            return None

        return GoalSnapshot(
            kcal=goal.kcal,
            protein_g=goal.protein_g,
            carb_g=goal.carb_g,
            fat_g=goal.fat_g,
            fiber_g=goal.fiber_g,
        )


def set_daily_goal(
    *,
    telegram_user_id: int,
    user_name: str | None,
    kcal: float | None,
    protein_g: float | None,
    carb_g: float | None,
    fat_g: float | None,
    fiber_g: float | None,
    valid_from: datetime | None = None,
) -> GoalSnapshot:
    with session_scope() as session:
        user = _get_or_create_user(session, telegram_user_id, user_name)
        goal = DailyGoal(
            user_id=user.id,
            kcal=kcal,
            protein_g=protein_g,
            carb_g=carb_g,
            fat_g=fat_g,
            fiber_g=fiber_g,
            valid_from=valid_from or datetime.now(UTC),
        )
        session.add(goal)
        return GoalSnapshot(
            kcal=goal.kcal,
            protein_g=goal.protein_g,
            carb_g=goal.carb_g,
            fat_g=goal.fat_g,
            fiber_g=goal.fiber_g,
        )


def get_daily_summary(telegram_user_id: int, target_date: date) -> DaySummary:
    with session_scope() as session:
        start, end = _utc_day_bounds(target_date)
        meals = _meals_for_range(session, telegram_user_id, start, end)
        return DaySummary(
            target_date=target_date,
            meals_count=len(meals),
            macros=_sum_meals(meals),
            goal=get_active_goal(telegram_user_id, target_date),
        )


def get_history(telegram_user_id: int, days: int) -> list[HistoryDay]:
    today = datetime.now(UTC).date()
    history: list[HistoryDay] = []
    for offset in range(days):
        target_date = today - timedelta(days=offset)
        summary = get_daily_summary(telegram_user_id, target_date)
        if summary.meals_count == 0:
            continue
        history.append(
            HistoryDay(
                target_date=target_date,
                meals_count=summary.meals_count,
                total_kcal=summary.macros.total_energy_kcal,
                total_protein_g=summary.macros.total_protein_g,
                total_carb_g=summary.macros.total_carb_g,
                total_fat_g=summary.macros.total_fat_g,
            )
        )
    return history


def undo_last_meal(telegram_user_id: int) -> PersistedMeal | None:
    with session_scope() as session:
        meal = session.scalar(
            select(Meal)
            .join(User, User.id == Meal.user_id)
            .options(selectinload(Meal.items))
            .where(User.telegram_id == telegram_user_id)
            .order_by(desc(Meal.occurred_at), desc(Meal.id))
        )
        if meal is None:
            return None

        macros = _meal_to_macros(meal)
        persisted = PersistedMeal(
            id=meal.id,
            created=False,
            macros=macros,
            meal_type=meal.meal_type,
            occurred_at=meal.occurred_at,
        )
        session.delete(meal)
        return persisted


def list_active_user_ids() -> list[int]:
    with session_scope() as session:
        return list(session.scalars(select(User.telegram_id).order_by(User.telegram_id.asc())))
