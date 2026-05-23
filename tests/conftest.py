from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
import responses

from kalorka.auth import SessionCache
from kalorka.client import Client
from kalorka.const import BASE_URL

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def mocked_responses() -> responses.RequestsMock:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


@pytest.fixture
def session_cache(tmp_path: Path) -> SessionCache:
    return SessionCache(tmp_path / "session.json", ttl_seconds=3600)


@pytest.fixture
def stub_login(mocked_responses: responses.RequestsMock) -> str:
    """Register the login endpoint so any call to ``Client.login`` succeeds."""
    # The session-check endpoint hit before login returns 200 only when authed,
    # so first time it's not authenticated -> we return 302. After login it's 200.
    state = {"authed": False}

    def session_check(_request: Any) -> tuple[int, dict[str, str], str]:
        if state["authed"]:
            return 200, {"Content-Type": "application/json"}, json.dumps({"data": {}})
        return 302, {"Location": "/login"}, ""

    mocked_responses.add_callback(
        responses.GET,
        re.compile(r"^https://www\.kaloricketabulky\.cz/user/diary/summary/.+/get"),
        callback=session_check,
    )
    mocked_responses.get(f"{BASE_URL}/login", status=200, body="<html></html>")

    def login_callback(request: Any) -> tuple[int, dict[str, str], str]:
        body = json.loads(request.body or "{}")
        # Verify the client is sending an MD5 hash, not plain text.
        expected = hashlib.md5(b"hunter2").hexdigest()
        if body.get("password") == expected:
            state["authed"] = True
            return 200, {"Content-Type": "application/json"}, json.dumps({"code": 0})
        return 200, {"Content-Type": "application/json"}, json.dumps({"code": 1, "message": "bad"})

    mocked_responses.add_callback(
        responses.POST,
        f"{BASE_URL}/login/create",
        callback=login_callback,
    )
    return "hunter2"


@pytest.fixture
def client(session_cache: SessionCache, stub_login: str) -> Client:
    return Client(
        email="test@example.com",
        password=stub_login,
        session_cache=session_cache,
        timeout=(1.0, 1.0),
        # Disable throttling in tests; real-life pacing is verified in
        # test_client.py::TestThrottle.
        min_request_interval=0.0,
        request_jitter=0.0,
    )
