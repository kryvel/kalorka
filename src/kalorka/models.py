"""Lightweight dataclasses for API responses.

These are intentionally minimal: they capture the fields the library actually
uses, not the full shape of the upstream JSON. ``raw`` is kept around so power
users can dig deeper without re-parsing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MealTime(StrEnum):
    """Slots a diary entry can be filed under. Values are the upstream API ids."""

    BREAKFAST = "1"
    MORNING_SNACK = "2"
    LUNCH = "3"
    AFTERNOON_SNACK = "4"
    DINNER = "5"
    LATE_SNACK = "6"

    @classmethod
    def parse(cls, value: str | MealTime) -> MealTime:
        """Accept ids ('3'), enum names ('LUNCH'), and common aliases ('obed')."""
        if isinstance(value, cls):
            return value
        v = value.strip().lower()
        if v in _MEAL_ALIASES:
            return _MEAL_ALIASES[v]
        # Numeric id passed as string
        for m in cls:
            if m.value == v:
                return m
        raise ValueError(f"Unknown meal time: {value!r}")


# Czech + English aliases. Czech first because the upstream site is Czech.
_MEAL_ALIASES: dict[str, MealTime] = {
    "snidane": MealTime.BREAKFAST,
    "snídaně": MealTime.BREAKFAST,
    "breakfast": MealTime.BREAKFAST,
    "dop_svacina": MealTime.MORNING_SNACK,
    "dopoledni_svacina": MealTime.MORNING_SNACK,
    "dopolední svačina": MealTime.MORNING_SNACK,
    "morning_snack": MealTime.MORNING_SNACK,
    "obed": MealTime.LUNCH,
    "oběd": MealTime.LUNCH,
    "lunch": MealTime.LUNCH,
    "odp_svacina": MealTime.AFTERNOON_SNACK,
    "odpoledni_svacina": MealTime.AFTERNOON_SNACK,
    "odpolední svačina": MealTime.AFTERNOON_SNACK,
    "afternoon_snack": MealTime.AFTERNOON_SNACK,
    "vecere": MealTime.DINNER,
    "večeře": MealTime.DINNER,
    "dinner": MealTime.DINNER,
    "druha_vecere": MealTime.LATE_SNACK,
    "druhá večeře": MealTime.LATE_SNACK,
    "late_snack": MealTime.LATE_SNACK,
}


MEAL_TIME_CZECH_NAMES: dict[MealTime, str] = {
    MealTime.BREAKFAST: "Snídaně",
    MealTime.MORNING_SNACK: "Dopolední svačina",
    MealTime.LUNCH: "Oběd",
    MealTime.AFTERNOON_SNACK: "Odpolední svačina",
    MealTime.DINNER: "Večeře",
    MealTime.LATE_SNACK: "Druhá večeře",
}


@dataclass(frozen=True)
class DiaryItem:
    """A single food/drink entry inside a meal slot."""

    id: str
    title: str
    kcal: float
    protein: float | None = None
    carbohydrate: float | None = None
    fat: float | None = None
    fiber: float | None = None
    sugar: float | None = None
    salt: float | None = None
    unit: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> DiaryItem:
        return cls(
            id=data["id"],
            title=data["title"],
            kcal=_to_float(data.get("energy")) or 0.0,
            protein=_to_float(data.get("protein")),
            carbohydrate=_to_float(data.get("carbohydrate")),
            fat=_to_float(data.get("fat")),
            fiber=_to_float(data.get("fiber")),
            sugar=_to_float(data.get("sugar")),
            salt=_to_float(data.get("salt")),
            unit=data.get("unit"),
            raw=data,
        )


@dataclass(frozen=True)
class Activity:
    """An activity entry (e.g. an Apple Health workout that was synced in)."""

    id: str
    title: str
    kcal: float
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Activity:
        return cls(
            id=data["id"],
            title=data["title"],
            kcal=_to_float(data.get("energy")) or 0.0,
            raw=data,
        )


@dataclass(frozen=True)
class DiaryEntry:
    """A full day: all six meal slots plus activities, keyed by ``MealTime``."""

    date: str
    items: dict[MealTime, list[DiaryItem]]
    activities: list[Activity]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, date: str, data: dict[str, Any]) -> DiaryEntry:
        items: dict[MealTime, list[DiaryItem]] = {m: [] for m in MealTime}
        for slot in data.get("times", []) or []:
            try:
                meal = MealTime(slot["id"])
            except ValueError:
                # Upstream introduced a new slot id we don't know about yet;
                # skip rather than crash the whole diary parse.
                continue
            items[meal] = [DiaryItem.from_api(it) for it in (slot.get("foodstuff") or [])]
        activities = [Activity.from_api(a) for a in (data.get("activities") or [])]
        return cls(date=date, items=items, activities=activities, raw=data)

    @property
    def total_kcal(self) -> float:
        return sum(item.kcal for slot in self.items.values() for item in slot)

    def slot_kcal(self, meal: MealTime) -> float:
        return sum(item.kcal for item in self.items[meal])


@dataclass(frozen=True)
class MacroSummary:
    """Daily targets and actual intake for the four headline macros."""

    kcal_actual: float
    kcal_goal: float
    kcal_percent: int
    protein_actual: float
    protein_goal: float
    carbs_actual: float
    carbs_goal: float
    fat_actual: float
    fat_goal: float
    fiber_actual: float
    fiber_goal: float
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> MacroSummary:
        total_item = _find_by_code(data.get("items"), "total") or {}
        macros = (data.get("itemsDynamic") or [[]])[0]
        macro_lookup = {m.get("code"): m for m in macros if isinstance(m, dict)}
        protein = macro_lookup.get("protein", {})
        carbs = macro_lookup.get("carbohydrate", {})
        fat = macro_lookup.get("fat", {})
        fiber = macro_lookup.get("fiber", {})
        return cls(
            kcal_actual=_parse_cz_number(total_item.get("actual")),
            kcal_goal=_parse_cz_number(total_item.get("goal")),
            kcal_percent=int(total_item.get("percent") or 0),
            protein_actual=_parse_cz_number(protein.get("actual")),
            protein_goal=_parse_cz_number(protein.get("goal")),
            carbs_actual=_parse_cz_number(carbs.get("actual")),
            carbs_goal=_parse_cz_number(carbs.get("goal")),
            fat_actual=_parse_cz_number(fat.get("actual")),
            fat_goal=_parse_cz_number(fat.get("goal")),
            fiber_actual=_parse_cz_number(fiber.get("actual")),
            fiber_goal=_parse_cz_number(fiber.get("goal")),
            raw=data,
        )


@dataclass(frozen=True)
class DrinkRegime:
    """Hydration progress as shown on the diary page."""

    liters_actual: float
    liters_goal: float
    percent: int

    @classmethod
    def from_summary(cls, data: dict[str, Any]) -> DrinkRegime | None:
        item = _find_by_title(data.get("items"), "Pitný režim")
        if not item:
            return None
        return cls(
            liters_actual=_parse_cz_number(item.get("actual")),
            liters_goal=_parse_cz_number(item.get("goal")),
            percent=int(item.get("percent") or 0),
        )


@dataclass(frozen=True)
class WeightTarget:
    """Current weight and goal weight, as reported by the summary endpoint."""

    current_kg: float
    target_kg: float
    percent: int

    @classmethod
    def from_summary(cls, data: dict[str, Any]) -> WeightTarget | None:
        item = _find_by_title(data.get("items"), "Cílová hmotnost")
        if not item:
            return None
        return cls(
            current_kg=_parse_cz_number(item.get("actual")),
            target_kg=_parse_cz_number(item.get("goal")),
            percent=int(item.get("percent") or 0),
        )


@dataclass(frozen=True)
class FoodSearchResult:
    """A single row from the autocomplete endpoint."""

    id: str
    title: str
    brand: str | None
    energy_per_100g: float | None
    unit: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> FoodSearchResult:
        # Prefer ``energy`` but accept ``value`` as a legacy fallback. Use an
        # explicit ``is None`` check so a real 0 kcal item (water, diet sodas)
        # doesn't get silently rewritten as "unknown".
        energy = data.get("energy")
        if energy is None:
            energy = data.get("value")
        return cls(
            id=data["id"],
            title=data["title"],
            brand=data.get("brandName"),
            energy_per_100g=_to_float(energy),
            unit=data.get("unit"),
            raw=data,
        )


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_cz_number(value: Any) -> float:
    """Parse Czech-formatted numbers ('1 924', '73,8') into float.

    Returns 0.0 for missing/garbage values so callers don't have to guard every
    macro field that might not have been filled in upstream.
    """
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _find_by_code(items: list[dict[str, Any]] | None, code: str) -> dict[str, Any] | None:
    for item in items or []:
        if isinstance(item, dict) and item.get("code") == code:
            return item
    return None


def _find_by_title(items: list[dict[str, Any]] | None, title: str) -> dict[str, Any] | None:
    for item in items or []:
        if isinstance(item, dict) and item.get("title") == title:
            return item
    return None
