# API reference

This document describes the public `kalorka` Python API and the upstream HTTP endpoints
it talks to. Anything not listed here is private and may change without notice.

## Authentication

Credentials are resolved by `kalorka.auth.load_credentials()`, which tries (in order):

1. `Credentials(email, password)` passed to `Client(...)`.
2. `KALORKA_EMAIL` / `KALORKA_PASSWORD` environment variables.
3. macOS Keychain entries: service names `kalorka-email` and `kalorka-password`,
   account name `$USER`.
4. A config file at `$XDG_CONFIG_HOME/kalorka/credentials` (or
   `~/.config/kalorka/credentials`): two bare lines, no `key=` prefix -
   email on line 1, password on line 2. The file must be mode 0600.

The password is MD5-hashed before being sent to `POST /login/create` - this is what the
upstream API expects, not a security claim by us. Session cookies are cached at
`$XDG_STATE_HOME/kalorka/session.json` (or `~/.local/state/kalorka/session.json`) with a
3-day TTL so the client doesn't log in on every call.

## Client

```python
from kalorka import Client
client = Client()
```

### Constructor

```python
Client(
    *,
    email: str | None = None,
    password: str | None = None,
    base_url: str = "https://www.kaloricketabulky.cz",
    timeout: tuple[float, float] = (5.0, 15.0),  # (connect, read)
    user_agent: str = "...",
    session: requests.Session | None = None,
    session_cache: SessionCache | None = None,
    min_request_interval: float = 5.0,  # seconds between API calls
    request_jitter: float = 5.0,        # plus uniform [0, jitter) on top
)
```

Inject a `requests.Session` to share connection pooling or a `SessionCache` stub to disable
the on-disk cache in tests.

### Methods

| Method | Returns | Notes |
|---|---|---|
| `login(*, force=False)` | `None` | Idempotent; called automatically on first request. `force=True` re-authenticates even if a cached session looks valid. |
| `logout()` | `None` | Drops the local session cache. Does not invalidate the remote session. |
| `get_diary(date)` | `DiaryEntry` | All food/drink/activity entries for `date`. |
| `get_summary(date)` | `MacroSummary` | Daily macro totals + goals. |
| `get_drink_regime(date)` | `DrinkRegime \| None` | Hydration progress; `None` if not tracked yet. |
| `get_weight(date)` | `WeightTarget \| None` | Current vs goal weight; `None` if not tracked. |
| `get_diary_range(start, end)` | `dict[str, DiaryEntry]` | Inclusive range, keyed by `DD.MM.YYYY`. |
| `search_food(query, *, limit=20)` | `list[FoodSearchResult]` | Autocomplete on the upstream food database. |
| `add_food(...)` | `None` | Adds a custom diary entry. Required: `date`, `meal`, `name`, `kcal`. Optional macros: `protein`, `carbs`, `fat`, `fiber`, `sugar`, `salt`, `saturated_fat`. |
| `add_drink(*, date, milliliters)` | `None` | Logs plain water. Internally a food entry against the stock water `guid`. |
| `add_weight(*, date, kilograms)` | `None` | Records a weight measurement. |
| `delete_entry(entry_id)` | `None` | Removes a food/drink entry by its `id` from `get_diary(...)`. |

### Date arguments

Anywhere a method takes `date`, you can pass:

- A `datetime.date` or `datetime.datetime` instance.
- A `DD.MM.YYYY` string (Czech format).
- A `YYYY-MM-DD` string (ISO).

The client always sends `DD.MM.YYYY` on the wire.

### Meal arguments

`meal` accepts a `MealTime` enum value or a string. Recognised strings:

| Czech | English | Enum |
|---|---|---|
| `snidane`, `snídaně` | `breakfast` | `MealTime.BREAKFAST` |
| `dopoledni_svacina`, `dopolední svačina` | `morning_snack` | `MealTime.MORNING_SNACK` |
| `obed`, `oběd` | `lunch` | `MealTime.LUNCH` |
| `odpoledni_svacina`, `odpolední svačina` | `afternoon_snack` | `MealTime.AFTERNOON_SNACK` |
| `vecere`, `večeře` | `dinner` | `MealTime.DINNER` |
| `druha_vecere`, `druhá večeře` | `late_snack` | `MealTime.LATE_SNACK` |

Numeric ids (`"1"`-`"6"`) also work.

## Models

All models are frozen dataclasses. Each one keeps the raw API dict on `.raw` so power users
can fish out fields the library doesn't expose.

### `DiaryEntry`

| Field | Type |
|---|---|
| `date` | `str` (DD.MM.YYYY) |
| `items` | `dict[MealTime, list[DiaryItem]]` (always all six slots, possibly empty) |
| `activities` | `list[Activity]` |
| `total_kcal` | `float` (property) |
| `slot_kcal(meal)` | `float` |

### `DiaryItem`

| Field | Type |
|---|---|
| `id` | `str` - pass to `delete_entry()` |
| `title` | `str` |
| `kcal` | `float` |
| `protein`, `carbohydrate`, `fat`, `fiber`, `sugar`, `salt` | `float \| None` |
| `unit` | `str \| None` |

### `Activity`

| Field | Type |
|---|---|
| `id`, `title` | `str` |
| `kcal` | `float` (energy burned) |

Activities are read-only. The upstream service does not accept activity writes from the web
API; they only enter the system via the iOS app's Apple Health bridge.

### `MacroSummary`

`kcal_actual`, `kcal_goal`, `kcal_percent`, plus `protein_*`, `carbs_*`, `fat_*`, `fiber_*`
(each with `_actual` and `_goal` fields, all floats; percent is int).

### `DrinkRegime`

`liters_actual`, `liters_goal`, `percent`.

### `WeightTarget`

`current_kg`, `target_kg`, `percent`.

### `FoodSearchResult`

`id`, `title`, `brand` (optional), `energy_per_100g` (optional), `unit` (optional).

## Exceptions

All exceptions inherit from `KalorkaError`:

- `ConfigError` - credentials are missing or unreadable.
- `AuthenticationError` - login was rejected by the server.
- `APIError(status, body, message=None)` - a non-2xx response, or a 2xx response with a
  non-zero `code` field.
- `NotFoundError` - 404. Subclass of `APIError`.

## Wire format

These are the upstream endpoints. They are documented here so you can audit what the
library does without reading the source. All paths are relative to
`https://www.kaloricketabulky.cz`.

### `POST /login/create?format=json`

Request:
```json
{"email": "you@example.com", "password": "<md5-hex of plaintext>"}
```

Response on success: `{"code": 0, ...}`. On failure: `{"code": <nonzero>, "message": "..."}`.

Sets session cookies on the `.kaloricketabulky.cz` domain.

### `GET /user/diary/{DD.MM.YYYY}/get?format=json`

Returns the full day's diary. Relevant top-level shape:
```json
{
  "data": {
    "times": [
      {"id": "1", "title": "Snídaně", "foodstuff": [<items>], "energyTotal": "..."},
      ...
    ],
    "activities": [
      {"id": "...", "title": "...", "energy": "..."}
    ]
  }
}
```

### `GET /user/diary/summary/{DD.MM.YYYY}/get?format=json`

Returns macro totals, hydration, and weight. The interesting fields:

- `data.items[]` - has an entry with `code: "total"` for kcal totals, plus
  `title: "Pitný režim"` for water and `title: "Cílová hmotnost"` for weight.
- `data.itemsDynamic[0]` - list of macro entries keyed by `code`: `protein`,
  `carbohydrate`, `fat`, `fiber`.

Numbers are Czech-formatted (`"1 924"`, `"73,8"`); the client parses them.

### `POST /user/foodstuff/add?format=json`

Adds a food entry. Two shapes:

**Stock food (by guid)** - the autocomplete endpoint returns these:
```json
{
  "guid": "<food-guid>",
  "diaryTimeGuid": "3",
  "date": "23.05.2026",
  "multiplier": 150,
  "unitGuid": "g"
}
```

**Custom food (free-form name + macros)** - what `Client.add_food` sends:
```json
{
  "guid": "0",
  "title": "Salmon bowl",
  "diaryTimeGuid": "3",
  "date": "23.05.2026",
  "energy": 420,
  "energyUnit": "kcal",
  "detailValues": true,
  "protein": 35, "carbohydrate": 18, "fat": 22
}
```

`detailValues: true` when any macro field is present; `false` for kcal-only entries.

### Water entries

Water is logged as a food entry against the stock water `guid` (`73a02350d55a3f8f`):
```json
{
  "guid": "73a02350d55a3f8f",
  "diaryTimeGuid": "1",
  "date": "23.05.2026",
  "multiplier": 500,
  "unitGuid": "g"
}
```

The meal slot doesn't matter - hydration totals are computed across the whole day.

### `POST /user/weight/add?format=json`

```json
{"value": 74.2, "date": "23.05.2026"}
```

### `GET /user/diary/foodstuff/delete/{id}?format=json`

Removes an entry by id. Yes, it's a `GET` - that's how the upstream API was designed.

### `GET /autocomplete/foodstuff-meal?query=<text>&format=json`

Returns a bare list (not wrapped in `{data: [...]}`) of search results:
```json
[
  {"id": "...", "title": "...", "brandName": "...", "energy": 212, "unit": "g"},
  ...
]
```

## CLI

See [README.md](../README.md#cli) for the user-facing command reference. The CLI is a thin
wrapper around `Client` - if you want to script things, prefer the library API.
