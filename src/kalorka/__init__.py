"""kalorka - Python client for kaloricketabulky.cz (dine4fit)."""
from kalorka.client import Client
from kalorka.exceptions import (
    APIError,
    AuthenticationError,
    ConfigError,
    KalorkaError,
    NotFoundError,
)
from kalorka.models import (
    DiaryEntry,
    DiaryItem,
    DrinkRegime,
    FoodSearchResult,
    MacroSummary,
    MealTime,
    WeightTarget,
)

__all__ = [
    "APIError",
    "AuthenticationError",
    "Client",
    "ConfigError",
    "DiaryEntry",
    "DiaryItem",
    "DrinkRegime",
    "FoodSearchResult",
    "KalorkaError",
    "MacroSummary",
    "MealTime",
    "NotFoundError",
    "WeightTarget",
]
__version__ = "0.1.0"
