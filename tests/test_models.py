from __future__ import annotations

import pytest

from kalorka.models import (
    DiaryEntry,
    DrinkRegime,
    FoodSearchResult,
    MacroSummary,
    MealTime,
    WeightTarget,
)

from .conftest import load_fixture


class TestMealTime:
    def test_parses_enum_value(self) -> None:
        assert MealTime.parse(MealTime.LUNCH) is MealTime.LUNCH

    @pytest.mark.parametrize(
        ("input_value", "expected"),
        [
            ("snidane", MealTime.BREAKFAST),
            ("Snídaně", MealTime.BREAKFAST),
            ("breakfast", MealTime.BREAKFAST),
            ("obed", MealTime.LUNCH),
            ("lunch", MealTime.LUNCH),
            ("vecere", MealTime.DINNER),
            ("3", MealTime.LUNCH),
            ("dop_svacina", MealTime.MORNING_SNACK),
            ("druhá večeře", MealTime.LATE_SNACK),
        ],
    )
    def test_parses_aliases(self, input_value: str, expected: MealTime) -> None:
        assert MealTime.parse(input_value) is expected

    def test_unknown_alias_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown meal time"):
            MealTime.parse("midnight_snack")


class TestDiaryEntry:
    def test_parses_full_day(self) -> None:
        raw = load_fixture("diary.json")
        entry = DiaryEntry.from_api("23.05.2026", raw["data"])
        assert entry.date == "23.05.2026"
        assert entry.total_kcal == 530
        assert entry.slot_kcal(MealTime.LUNCH) == 530
        assert entry.slot_kcal(MealTime.DINNER) == 0
        assert len(entry.items[MealTime.LUNCH]) == 2
        assert entry.items[MealTime.LUNCH][0].title == "Test Bowl"
        assert len(entry.activities) == 1
        assert entry.activities[0].kcal == 240

    def test_handles_missing_optional_fields(self) -> None:
        entry = DiaryEntry.from_api("01.01.2026", {})
        assert entry.total_kcal == 0
        assert entry.activities == []
        for items in entry.items.values():
            assert items == []

    def test_skips_unknown_meal_slots(self) -> None:
        # If the upstream ever adds a new slot id we don't know about, the
        # diary parser should drop that slot instead of raising.
        raw = {
            "times": [
                {"id": "99", "title": "Future meal", "foodstuff": [
                    {"id": "x", "title": "Mystery", "energy": "100"},
                ]},
                {"id": "3", "title": "Oběd", "foodstuff": []},
            ],
        }
        entry = DiaryEntry.from_api("01.01.2026", raw)
        assert entry.total_kcal == 0
        for items in entry.items.values():
            assert items == []


class TestMacroSummary:
    def test_parses_czech_numbers(self) -> None:
        raw = load_fixture("summary.json")
        summary = MacroSummary.from_api(raw["data"])
        assert summary.kcal_actual == 530
        assert summary.kcal_goal == 1924
        assert summary.kcal_percent == 28
        assert summary.fat_goal == pytest.approx(67.3)
        assert summary.protein_actual == 24


class TestDrinkRegime:
    def test_from_summary(self) -> None:
        raw = load_fixture("summary.json")
        drink = DrinkRegime.from_summary(raw["data"])
        assert drink is not None
        assert drink.liters_actual == pytest.approx(0.25)
        assert drink.liters_goal == pytest.approx(2.95)

    def test_returns_none_when_missing(self) -> None:
        assert DrinkRegime.from_summary({"items": []}) is None


class TestWeightTarget:
    def test_from_summary(self) -> None:
        raw = load_fixture("summary.json")
        weight = WeightTarget.from_summary(raw["data"])
        assert weight is not None
        assert weight.current_kg == pytest.approx(73.8)
        assert weight.target_kg == 72


class TestFoodSearchResult:
    def test_from_api(self) -> None:
        raw = load_fixture("search.json")
        results = [FoodSearchResult.from_api(item) for item in raw]
        assert len(results) == 2
        assert results[0].brand == "Sample Brand"
        assert results[0].energy_per_100g == 212
        assert results[1].brand is None

    def test_zero_energy_is_preserved(self) -> None:
        # A real 0 kcal item (water, diet drinks) must not collapse to None.
        result = FoodSearchResult.from_api(
            {"id": "x", "title": "Voda", "energy": 0, "unit": "g"}
        )
        assert result.energy_per_100g == 0.0

    def test_falls_back_to_value_when_energy_missing(self) -> None:
        result = FoodSearchResult.from_api(
            {"id": "x", "title": "Legacy", "value": 150, "unit": "g"}
        )
        assert result.energy_per_100g == 150
