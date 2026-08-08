"""Tests for the thin nRF905 HTTP client."""

from __future__ import annotations

from unittest.mock import Mock

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nrf905_vmc.api import (
    SETSPEED_PATH,
    STATUS_PATH,
    Nrf905Api,
    Nrf905ApiError,
    Nrf905AuthError,
    Nrf905ConnectionError,
)

HOST = "192.168.1.50"
STATUS_URL = f"http://{HOST}{STATUS_PATH}"
SETSPEED_URL = f"http://{HOST}{SETSPEED_PATH}"


def _api(hass: HomeAssistant) -> Nrf905Api:
    return Nrf905Api(async_get_clientsession(hass), HOST, "user", "pass")


async def test_base_url(hass: HomeAssistant) -> None:
    """The base URL is derived from the configured host."""
    assert _api(hass).base_url == f"http://{HOST}"


async def test_get_status_returns_first_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The first entry of the `devices` mapping is returned."""
    aioclient_mock.get(
        STATUS_URL,
        json={"devices": {"0": {"speed": "medium", "timer": False}}},
    )

    assert await _api(hass).async_get_status() == {"speed": "medium", "timer": False}


async def test_get_status_sends_basic_auth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Credentials are sent along with the status request."""
    aioclient_mock.get(STATUS_URL, json={"devices": {"0": {"speed": "low"}}})

    await _api(hass).async_get_status()

    assert aioclient_mock.call_count == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"devices": {}},
        {"devices": None},
        {},
        [],
        "not json at all",
    ],
)
async def test_get_status_without_devices(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, payload: object
) -> None:
    """A payload without any device is an API error."""
    aioclient_mock.get(STATUS_URL, json=payload)

    with pytest.raises(Nrf905ApiError):
        await _api(hass).async_get_status()


@pytest.mark.parametrize("status", [401, 403])
async def test_get_status_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    """401/403 are surfaced as an authentication error."""
    aioclient_mock.get(STATUS_URL, status=status)

    with pytest.raises(Nrf905AuthError):
        await _api(hass).async_get_status()


async def test_get_status_server_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Other HTTP errors are surfaced as a generic API error."""
    aioclient_mock.get(STATUS_URL, status=500)

    with pytest.raises(Nrf905ApiError) as err:
        await _api(hass).async_get_status()

    assert not isinstance(err.value, (Nrf905AuthError, Nrf905ConnectionError))


@pytest.mark.parametrize("status", [401, 403])
async def test_response_error_with_auth_status(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    """A ClientResponseError carrying 401/403 is still an auth error."""
    aioclient_mock.get(
        STATUS_URL,
        exc=aiohttp.ClientResponseError(
            request_info=Mock(real_url=STATUS_URL), history=(), status=status
        ),
    )

    with pytest.raises(Nrf905AuthError):
        await _api(hass).async_get_status()


@pytest.mark.parametrize(
    "exc",
    [aiohttp.ClientError("boom"), TimeoutError()],
)
async def test_get_status_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, exc: Exception
) -> None:
    """Transport failures and timeouts are surfaced as connection errors."""
    aioclient_mock.get(STATUS_URL, exc=exc)

    with pytest.raises(Nrf905ConnectionError):
        await _api(hass).async_get_status()


async def test_set_speed_without_timer(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """No timer parameter is sent when no timer is requested."""
    aioclient_mock.get(SETSPEED_URL, json={"status": "ok"})

    assert await _api(hass).async_set_speed("medium") == {"status": "ok"}

    url = aioclient_mock.mock_calls[0][1]
    assert url.query["speed"] == "medium"
    assert "timer" not in url.query


@pytest.mark.parametrize("timer", [None, 0])
async def test_set_speed_falsy_timer_is_omitted(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, timer: int | None
) -> None:
    """A zero/None timer means "no auto-revert"."""
    aioclient_mock.get(SETSPEED_URL, json={})

    await _api(hass).async_set_speed("low", timer)

    assert "timer" not in aioclient_mock.mock_calls[0][1].query


async def test_set_speed_with_timer(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The auto-revert delay is passed as a query parameter."""
    aioclient_mock.get(SETSPEED_URL, json={"status": "ok"})

    await _api(hass).async_set_speed("high", 30)

    url = aioclient_mock.mock_calls[0][1]
    assert url.query["speed"] == "high"
    assert url.query["timer"] == "30"


async def test_set_speed_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Rejected credentials also raise on the write endpoint."""
    aioclient_mock.get(SETSPEED_URL, status=401)

    with pytest.raises(Nrf905AuthError):
        await _api(hass).async_set_speed("high")
