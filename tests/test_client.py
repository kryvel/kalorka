from __future__ import annotations

import json
import re
from datetime import date

import pytest
import responses

from kalorka.client import Client
from kalorka.const import BASE_URL
from kalorka.exceptions import APIError, AuthenticationError, NotFoundError
from kalorka.models import MealTime

from .conftest import load_fixture


def _diary_url(date_str: str = "23.05.2026") -> str:
    return f"{BASE_URL}/user/diary/{date_str}/get"


def _summary_url(date_str: str = "23.05.2026") -> str:
    return f"{BASE_URL}/user/diary/summary/{date_str}/get"


class TestLogin:
    def test_login_hashes_password(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        client.login(force=True)
        login_call = next(
            call for call in mocked_responses.calls if "/login/create" in call.request.url
        )
        body = json.loads(login_call.request.body or "{}")
        assert body["password"] != "hunter2"
        assert len(body["password"]) == 32

    def test_login_fails_on_bad_credentials(
        self, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.get(
            re.compile(r".+/user/diary/summary/.+/get"), status=302, headers={"Location": "/login"}
        )
        mocked_responses.get(f"{BASE_URL}/login", status=200, body="")
        mocked_responses.post(
            f"{BASE_URL}/login/create",
            json={"code": 1, "message": "Bad password"},
        )
        c = Client(email="x@y.z", password="wrong", session_cache=_DummyCache())
        with pytest.raises(AuthenticationError, match="Bad password"):
            c.login(force=True)

    def test_logout_clears_state(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        client.login()
        client.logout()
        # After logout, calling an endpoint forces a fresh login
        mocked_responses.get(_diary_url(), json=load_fixture("diary.json"))
        client.get_diary("23.05.2026")
        assert any(
            "/login/create" in call.request.url
            for call in mocked_responses.calls
        )


class TestGetters:
    def test_get_diary(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.get(_diary_url(), json=load_fixture("diary.json"))
        diary = client.get_diary("23.05.2026")
        assert diary.total_kcal == 530
        assert diary.items[MealTime.LUNCH][0].title == "Test Bowl"

    def test_get_diary_accepts_date_object(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.get(_diary_url(), json=load_fixture("diary.json"))
        diary = client.get_diary(date(2026, 5, 23))
        assert diary.date == "23.05.2026"

    def test_get_diary_accepts_iso(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.get(_diary_url(), json=load_fixture("diary.json"))
        diary = client.get_diary("2026-05-23")
        assert diary.date == "23.05.2026"

    def test_get_summary(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.get(_summary_url(), json=load_fixture("summary.json"))
        summary = client.get_summary("23.05.2026")
        assert summary.kcal_actual == 530
        assert summary.kcal_goal == 1924

    def test_get_drink_regime(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.get(_summary_url(), json=load_fixture("summary.json"))
        drink = client.get_drink_regime("23.05.2026")
        assert drink is not None
        assert drink.liters_goal == pytest.approx(2.95)

    def test_get_weight(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.get(_summary_url(), json=load_fixture("summary.json"))
        weight = client.get_weight("23.05.2026")
        assert weight is not None
        assert weight.current_kg == pytest.approx(73.8)

    def test_search_food(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.get(
            f"{BASE_URL}/autocomplete/foodstuff-meal", json=load_fixture("search.json")
        )
        results = client.search_food("omeleta", limit=10)
        assert len(results) == 2
        assert results[0].brand == "Sample Brand"

    def test_search_empty_query_returns_empty(self, client: Client) -> None:
        assert client.search_food("   ") == []

    def test_get_diary_range(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.get(
            re.compile(r".+/user/diary/(?:21|22|23)\.05\.2026/get"),
            json=load_fixture("diary.json"),
        )
        result = client.get_diary_range("2026-05-21", "2026-05-23")
        assert list(result.keys()) == ["21.05.2026", "22.05.2026", "23.05.2026"]

    def test_get_diary_range_rejects_inverted(self, client: Client) -> None:
        with pytest.raises(ValueError, match="end must be"):
            client.get_diary_range("2026-05-23", "2026-05-21")


class TestWriters:
    def test_add_food_sends_macros(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.post(f"{BASE_URL}/user/foodstuff/add", json={"code": 0, "message": "ok"})
        client.add_food(
            date="23.05.2026", meal="obed", name="Salmon", kcal=420, protein=35, fat=22, carbs=18
        )
        call = mocked_responses.calls[-1]
        body = json.loads(call.request.body or "{}")
        assert body["title"] == "Salmon"
        assert body["energy"] == 420
        assert body["protein"] == 35
        assert body["diaryTimeGuid"] == "3"
        assert body["detailValues"] is True

    def test_add_food_without_macros_uses_basic_payload(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.post(f"{BASE_URL}/user/foodstuff/add", json={"code": 0})
        client.add_food(date="23.05.2026", meal=MealTime.DINNER, name="Mystery", kcal=300)
        body = json.loads(mocked_responses.calls[-1].request.body or "{}")
        assert body["detailValues"] is False
        assert "protein" not in body

    def test_add_drink(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.post(f"{BASE_URL}/user/foodstuff/add", json={"code": 0})
        client.add_drink(date="23.05.2026", milliliters=500)
        body = json.loads(mocked_responses.calls[-1].request.body or "{}")
        assert body["multiplier"] == 500
        assert body["guid"]  # water guid

    def test_add_drink_rejects_zero(self, client: Client) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            client.add_drink(date="23.05.2026", milliliters=0)

    def test_add_weight(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.post(f"{BASE_URL}/user/weight/add", json={"code": 0})
        client.add_weight(date="23.05.2026", kilograms=74.2)
        body = json.loads(mocked_responses.calls[-1].request.body or "{}")
        assert body == {"value": 74.2, "date": "23.05.2026"}

    def test_add_weight_rejects_negative(self, client: Client) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            client.add_weight(date="23.05.2026", kilograms=-5)

    def test_delete_entry(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.get(
            f"{BASE_URL}/user/diary/foodstuff/delete/abc123", json={"code": 0}
        )
        client.delete_entry("abc123")

    def test_delete_entry_requires_id(self, client: Client) -> None:
        with pytest.raises(ValueError, match="entry_id is required"):
            client.delete_entry("")


class TestErrorHandling:
    def test_not_found_raises(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.get(_diary_url("01.01.1999"), status=404, body="missing")
        with pytest.raises(NotFoundError):
            client.get_diary("01.01.1999")

    def test_api_error_on_500(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.get(_diary_url(), status=500, body="boom")
        with pytest.raises(APIError):
            client.get_diary("23.05.2026")

    def test_api_error_on_code_nonzero(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        mocked_responses.post(
            f"{BASE_URL}/user/foodstuff/add",
            json={"code": 99, "message": "blocked"},
        )
        with pytest.raises(APIError, match="blocked"):
            client.add_food(date="23.05.2026", meal="obed", name="x", kcal=1)

    def test_get_raises_on_envelope_code(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        # GET responses also use {"code": ..., "message": ...} envelopes;
        # a non-zero code must raise rather than silently return empty data.
        mocked_responses.get(_diary_url(), json={"code": 42, "message": "stale"})
        with pytest.raises(APIError, match="stale"):
            client.get_diary("23.05.2026")

    def test_relogins_on_session_expiry(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        # First call returns a 302 -> /login redirect (session expired).
        # Client should re-login and retry the request, which then succeeds.
        mocked_responses.get(
            _diary_url(),
            status=302,
            headers={"Location": "/login"},
        )
        mocked_responses.get(_diary_url(), json=load_fixture("diary.json"))
        diary = client.get_diary("23.05.2026")
        assert diary.total_kcal == 530
        login_calls = [c for c in mocked_responses.calls if "/login/create" in c.request.url]
        assert len(login_calls) >= 1


class TestSearchShapes:
    def test_search_handles_wrapped_payload(
        self, client: Client, mocked_responses: responses.RequestsMock
    ) -> None:
        # Upstream usually returns a bare list, but the code accepts a
        # {"data": [...]} envelope too. Cover that branch.
        mocked_responses.get(
            f"{BASE_URL}/autocomplete/foodstuff-meal",
            json={"data": load_fixture("search.json")},
        )
        results = client.search_food("omeleta")
        assert len(results) == 2


class _DummyCache:
    def load(self) -> None:
        return None

    def save(self, cookies: dict[str, str]) -> None:
        return None

    def clear(self) -> None:
        return None
