"""HTTP client for kaloricketabulky.cz (dine4fit)."""
from __future__ import annotations

import hashlib
import logging
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any

import requests

from kalorka.auth import Credentials, SessionCache, load_credentials, state_dir
from kalorka.const import (
    BASE_URL,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    SESSION_TTL_SECONDS,
    WATER_FOODSTUFF_GUID,
)
from kalorka.exceptions import APIError, AuthenticationError, NotFoundError
from kalorka.models import (
    DiaryEntry,
    DrinkRegime,
    FoodSearchResult,
    MacroSummary,
    MealTime,
    WeightTarget,
)

logger = logging.getLogger("kalorka")

DateLike = str | date_cls | datetime


class Client:
    """A session-aware client for the dine4fit web API.

    Typical use::

        client = Client()
        client.add_food(date="23.05.2026", meal="lunch", name="Salmon bowl", kcal=420,
                       protein=35, carbs=18, fat=22)
        diary = client.get_diary("23.05.2026")
        print(diary.total_kcal)

    Credentials default to the env vars / Keychain / config file (see
    ``auth.load_credentials``). Pass ``email``/``password`` to override.
    """

    def __init__(
        self,
        *,
        email: str | None = None,
        password: str | None = None,
        base_url: str = BASE_URL,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        session: requests.Session | None = None,
        session_cache: SessionCache | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._credentials_override = (
            Credentials(email, password) if email and password else None
        )
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Language": "cs,en;q=0.8",
            }
        )
        self._session_cache = session_cache or SessionCache(
            state_dir() / "session.json", SESSION_TTL_SECONDS
        )
        self._restore_session()
        self._logged_in_checked = False

    # ----- session management ------------------------------------------------

    def _restore_session(self) -> None:
        cookies = self._session_cache.load()
        if not cookies:
            return
        for name, value in cookies.items():
            self._session.cookies.set(name, value, domain=".kaloricketabulky.cz")

    def _persist_session(self) -> None:
        relevant = {
            c.name: c.value
            for c in self._session.cookies
            if c.value is not None and c.domain and "kaloricketabulky.cz" in c.domain
        }
        if relevant:
            self._session_cache.save(relevant)

    def _is_logged_in(self) -> bool:
        # Probes a cheap endpoint that returns JSON when authenticated and a
        # redirect to /login otherwise. Uses today's date so the request stays
        # plausibly fresh if the upstream ever rejects very old dates.
        today = date_cls.today().strftime("%d.%m.%Y")
        url = f"{self.base_url}/user/diary/summary/{today}/get?format=json"
        try:
            r = self._session.get(url, allow_redirects=False, timeout=self.timeout)
        except requests.RequestException:
            return False
        return r.status_code == 200 and "application/json" in r.headers.get("Content-Type", "")

    def login(self, *, force: bool = False) -> None:
        """Authenticate, refreshing the session cookie. Idempotent."""
        if not force and self._logged_in_checked:
            return
        if not force and self._is_logged_in():
            self._logged_in_checked = True
            return

        credentials = self._credentials_override or load_credentials()
        # Prime CSRF / locale cookies. Errors here are non-fatal.
        try:
            self._session.get(f"{self.base_url}/login", timeout=self.timeout)
        except requests.RequestException as exc:
            logger.debug("Pre-login GET failed (ignored): %s", exc)

        md5_pw = hashlib.md5(credentials.password.encode("utf-8")).hexdigest()
        r = self._session.post(
            f"{self.base_url}/login/create?=&format=json&voucher=",
            json={"email": credentials.email, "password": md5_pw},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise AuthenticationError(f"Login HTTP {r.status_code}: {r.text[:200]}")
        body = r.json()
        if body.get("code") != 0:
            raise AuthenticationError(f"Login refused: {body.get('message') or body}")
        if not self._is_logged_in():
            raise AuthenticationError("Login appeared to succeed but session is not valid")
        self._persist_session()
        self._logged_in_checked = True

    def logout(self) -> None:
        """Drop the local session cache. The remote session is not invalidated."""
        self._session.cookies.clear()
        self._session_cache.clear()
        self._logged_in_checked = False

    # ----- transport ---------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        self.login()
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("headers", {}).setdefault("X-Requested-With", "XMLHttpRequest")
        # Without this, requests follows the upstream's session-expiry redirect to
        # /login and the retry branch below sees a 200 HTML page instead of a 302.
        kwargs.setdefault("allow_redirects", False)
        r = self._session.request(method, url, **kwargs)
        if r.status_code == 401 or (
            r.status_code in (302, 303) and "/login" in r.headers.get("Location", "")
        ):
            self._logged_in_checked = False
            self.login(force=True)
            r = self._session.request(method, url, **kwargs)
        if r.status_code == 404:
            raise NotFoundError(r.status_code, r.text)
        if not r.ok:
            raise APIError(r.status_code, r.text)
        return r

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._request("POST", path, json=payload)
        body: dict[str, Any] = _decode_json(r)
        _raise_for_envelope_code(r, body)
        return body

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        r = self._request("GET", path, params=params)
        body = _decode_json(r)
        # Read endpoints use the same {"code": ..., "message": ...} envelope as
        # writes. List responses (autocomplete) skip the envelope entirely.
        if isinstance(body, dict):
            _raise_for_envelope_code(r, body)
        return body

    # ----- read --------------------------------------------------------------

    def get_diary(self, date: DateLike) -> DiaryEntry:
        """Fetch all food/drink/activity entries for ``date``."""
        date_str = _format_date(date)
        body = self._get_json(f"/user/diary/{date_str}/get", {"format": "json"})
        return DiaryEntry.from_api(date_str, body.get("data") or {})

    def get_summary(self, date: DateLike) -> MacroSummary:
        """Daily macro totals + targets."""
        body = self._get_json(
            f"/user/diary/summary/{_format_date(date)}/get", {"format": "json"}
        )
        return MacroSummary.from_api(body.get("data") or {})

    def get_drink_regime(self, date: DateLike) -> DrinkRegime | None:
        """Hydration totals for ``date`` (``None`` if not tracked yet)."""
        body = self._get_json(
            f"/user/diary/summary/{_format_date(date)}/get", {"format": "json"}
        )
        return DrinkRegime.from_summary(body.get("data") or {})

    def get_weight(self, date: DateLike) -> WeightTarget | None:
        """Current vs goal weight for ``date``."""
        body = self._get_json(
            f"/user/diary/summary/{_format_date(date)}/get", {"format": "json"}
        )
        return WeightTarget.from_summary(body.get("data") or {})

    def search_food(self, query: str, *, limit: int = 20) -> list[FoodSearchResult]:
        """Search the upstream food database (autocomplete endpoint)."""
        if not query.strip():
            return []
        raw = self._get_json("/autocomplete/foodstuff-meal", {"query": query, "format": "json"})
        rows = raw if isinstance(raw, list) else raw.get("data") or []
        return [FoodSearchResult.from_api(r) for r in rows[:limit]]

    def get_diary_range(
        self, start: DateLike, end: DateLike
    ) -> dict[str, DiaryEntry]:
        """Fetch diary entries for an inclusive date range, keyed by 'DD.MM.YYYY'."""
        start_d = _coerce_date(start)
        end_d = _coerce_date(end)
        if end_d < start_d:
            raise ValueError("end must be >= start")
        out: dict[str, DiaryEntry] = {}
        cur = start_d
        while cur <= end_d:
            label = cur.strftime("%d.%m.%Y")
            out[label] = self.get_diary(cur)
            cur += timedelta(days=1)
        return out

    # ----- write -------------------------------------------------------------

    def add_food(
        self,
        *,
        date: DateLike,
        meal: MealTime | str,
        name: str,
        kcal: float,
        protein: float | None = None,
        carbs: float | None = None,
        fat: float | None = None,
        fiber: float | None = None,
        sugar: float | None = None,
        salt: float | None = None,
        saturated_fat: float | None = None,
    ) -> None:
        """Create a custom diary entry. Use this for restaurant meals, homemade dishes, etc."""
        meal_enum = MealTime.parse(meal)
        detail_filled = any(
            v is not None for v in (protein, carbs, fat, fiber, sugar, salt, saturated_fat)
        )
        payload: dict[str, Any] = {
            "guid": "0",
            "title": name,
            "diaryTimeGuid": meal_enum.value,
            "date": _format_date(date),
            "energy": kcal,
            "energyUnit": "kcal",
            "detailValues": detail_filled,
        }
        if protein is not None:
            payload["protein"] = protein
        if carbs is not None:
            payload["carbohydrate"] = carbs
        if fat is not None:
            payload["fat"] = fat
        if fiber is not None:
            payload["fiber"] = fiber
        if sugar is not None:
            payload["sugar"] = sugar
        if salt is not None:
            payload["salt"] = salt
        if saturated_fat is not None:
            payload["saturatedFattyAcid"] = saturated_fat
        self._post_json("/user/foodstuff/add?format=json&=", payload)

    def add_drink(self, *, date: DateLike, milliliters: float) -> None:
        """Log a plain-water entry. Adds to the day's hydration regime."""
        if milliliters <= 0:
            raise ValueError("milliliters must be > 0")
        payload = {
            "guid": WATER_FOODSTUFF_GUID,
            "diaryTimeGuid": MealTime.BREAKFAST.value,  # slot doesn't matter for water totals
            "date": _format_date(date),
            "multiplier": milliliters,
            "unitGuid": "g",  # millilitre == gram for water in the upstream model
        }
        self._post_json("/user/foodstuff/add?format=json&=", payload)

    def add_weight(self, *, date: DateLike, kilograms: float) -> None:
        """Record a weight measurement (kg) for ``date``."""
        if kilograms <= 0:
            raise ValueError("kilograms must be > 0")
        self._post_json(
            "/user/weight/add?format=json&=",
            {"value": kilograms, "date": _format_date(date)},
        )

    def delete_entry(self, entry_id: str) -> None:
        """Remove a food/drink entry by its id (from :meth:`get_diary`)."""
        if not entry_id:
            raise ValueError("entry_id is required")
        self._get_json(f"/user/diary/foodstuff/delete/{entry_id}", {"format": "json"})


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _format_date(value: DateLike) -> str:
    """Always emit the Czech ``DD.MM.YYYY`` format the API requires."""
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, date_cls):
        return value.strftime("%d.%m.%Y")
    text = str(value).strip()
    # Accept ISO ('2026-05-23') as a convenience.
    if len(text) == 10 and text[4] == "-":
        return datetime.strptime(text, "%Y-%m-%d").strftime("%d.%m.%Y")
    return text


def _coerce_date(value: DateLike) -> date_cls:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_cls):
        return value
    text = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {value!r}")


def _decode_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise APIError(response.status_code, response.text, "Response is not JSON") from exc


def _raise_for_envelope_code(response: requests.Response, body: dict[str, Any]) -> None:
    """Raise ``APIError`` if a JSON envelope's ``code`` field is non-zero."""
    code = body.get("code")
    if code in (0, None):
        return
    raise APIError(response.status_code, response.text, body.get("message"))
