"""Tests for the Journiv API client."""

from collections.abc import Awaitable, Callable

import pytest
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.journiv.api import (
    JournivApi,
    JournivAuthenticationError,
    JournivConnectionError,
    normalize_host,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

HOST = "https://journiv.example.com"
ACCESS_TOKEN = "access-token"
REFRESH_TOKEN = "refresh-token"


@pytest.mark.parametrize(
    ("raw_host", "expected"),
    [
        pytest.param(" https://journiv.example.com/ ", HOST, id="normalized"),
        pytest.param("http://localhost:8080", "http://localhost:8080", id="http"),
        pytest.param("journiv.example.com", None, id="missing-scheme"),
        pytest.param("ftp://journiv.example.com", None, id="invalid-scheme"),
        pytest.param("https://", None, id="missing-host"),
        pytest.param("https://user@example.com", None, id="userinfo"),
        pytest.param("https://example.com/path", None, id="path"),
        pytest.param("https://example.com?query=yes", None, id="query"),
        pytest.param("https://example.com#fragment", None, id="fragment"),
        pytest.param("https://[invalid", None, id="malformed"),
    ],
)
def test_normalize_host(raw_host: str, expected: str | None) -> None:
    """Test host URL normalization and validation."""
    assert normalize_host(raw_host) == expected


async def test_invalid_host(hass: HomeAssistant) -> None:
    """Test an invalid host is rejected by the client."""
    with pytest.raises(ValueError, match="Invalid Journiv host URL"):
        JournivApi(async_get_clientsession(hass), "not-a-url")


async def test_authenticate(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test authentication stores the returned tokens."""
    aioclient_mock.post(
        f"{HOST}/api/v1/auth/login",
        json={"access_token": ACCESS_TOKEN, "refresh_token": REFRESH_TOKEN},
    )
    api = JournivApi(async_get_clientsession(hass), HOST)

    data = await api.authenticate("test@example.com", "password")

    assert data["access_token"] == ACCESS_TOKEN
    assert api.access_token == ACCESS_TOKEN
    assert api.refresh_token == REFRESH_TOKEN


async def test_refresh_access_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test refreshing an access token."""
    aioclient_mock.post(
        f"{HOST}/api/v1/auth/refresh", json={"access_token": ACCESS_TOKEN}
    )
    api = JournivApi(async_get_clientsession(hass), HOST)

    await api.refresh_access_token(REFRESH_TOKEN)

    assert api.access_token == ACCESS_TOKEN
    assert api.refresh_token == REFRESH_TOKEN


@pytest.mark.parametrize(
    ("method", "path", "response"),
    [
        pytest.param(
            "get_current_user",
            "/api/v1/users/me",
            {"id": "user-id", "email": "test@example.com"},
            id="user",
        ),
        pytest.param("get_journals", "/api/v1/journals/", [], id="journals"),
        pytest.param(
            "get_writing_analytics",
            "/api/v1/analytics/writing-streak",
            {"current_streak": 1},
            id="writing",
        ),
        pytest.param(
            "get_mood_statistics",
            "/api/v1/moods/analytics/statistics",
            {"total_logs": 1},
            id="mood-statistics",
        ),
        pytest.param(
            "get_mood_streak",
            "/api/v1/moods/analytics/streak",
            {"current_streak": 1},
            id="mood-streak",
        ),
    ],
)
async def test_authenticated_getters(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    method: str,
    path: str,
    response: object,
) -> None:
    """Test authenticated API getters."""
    aioclient_mock.get(f"{HOST}{path}", json=response)
    api = JournivApi(async_get_clientsession(hass), HOST)
    api.access_token = ACCESS_TOKEN

    result = await getattr(api, method)()

    assert result == response


@pytest.mark.parametrize(
    "method",
    [
        "get_current_user",
        "get_journals",
        "get_writing_analytics",
        "get_mood_statistics",
        "get_mood_streak",
    ],
)
async def test_getters_require_authentication(hass: HomeAssistant, method: str) -> None:
    """Test authenticated getters reject missing access tokens."""
    api = JournivApi(async_get_clientsession(hass), HOST)

    with pytest.raises(JournivAuthenticationError, match="Not authenticated"):
        await getattr(api, method)()


@pytest.mark.parametrize(
    ("http_method", "path", "call"),
    [
        pytest.param(
            "post",
            "/api/v1/auth/login",
            lambda api: api.authenticate("test@example.com", "password"),
            id="login",
        ),
        pytest.param(
            "post",
            "/api/v1/auth/refresh",
            lambda api: api.refresh_access_token(REFRESH_TOKEN),
            id="refresh",
        ),
        pytest.param(
            "get", "/api/v1/users/me", lambda api: api.get_current_user(), id="user"
        ),
        pytest.param(
            "get", "/api/v1/journals/", lambda api: api.get_journals(), id="journals"
        ),
        pytest.param(
            "get",
            "/api/v1/analytics/writing-streak",
            lambda api: api.get_writing_analytics(),
            id="analytics",
        ),
    ],
)
@pytest.mark.parametrize(
    ("status", "exception"),
    [
        pytest.param(401, JournivAuthenticationError, id="unauthorized"),
        pytest.param(500, JournivConnectionError, id="server-error"),
    ],
)
async def test_request_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    http_method: str,
    path: str,
    call: Callable[[JournivApi], Awaitable[object]],
    status: int,
    exception: type[Exception],
) -> None:
    """Test authentication and connection errors are mapped."""
    getattr(aioclient_mock, http_method)(f"{HOST}{path}", status=status)
    api = JournivApi(async_get_clientsession(hass), HOST)
    api.access_token = ACCESS_TOKEN

    with pytest.raises(exception):
        await call(api)
