"""Thin async client for the nRF905 fan HTTP API.

This mirrors the two endpoints used by the original ``nrf905_api.py`` script:

* status : GET /api/test/fan/querydevice.json      (HTTP basic auth)
* set    : GET /api/v2/fan/setspeed.json?speed=... (optionally &timer=<min>)
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from aiohttp import BasicAuth

REQUEST_TIMEOUT = 10

STATUS_PATH = "/api/test/fan/querydevice.json"
SETSPEED_PATH = "/api/v2/fan/setspeed.json"


class Nrf905ApiError(Exception):
    """Generic error talking to the device."""


class Nrf905ConnectionError(Nrf905ApiError):
    """The device could not be reached."""


class Nrf905AuthError(Nrf905ApiError):
    """Authentication was rejected by the device."""


class Nrf905Api:
    """Minimal HTTP client for the ventilation controller."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._host = host
        self._username = username
        self._password = password

    @property
    def base_url(self) -> str:
        return f"http://{self._host}"

    @property
    def _auth(self) -> BasicAuth:
        return BasicAuth(self._username, self._password)

    async def _get(self, url: str) -> Any:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.get(url, auth=self._auth) as resp:
                    if resp.status in (401, 403):
                        raise Nrf905AuthError(f"Authentication failed ({resp.status})")
                    resp.raise_for_status()
                    # Some firmwares return JSON with a wrong content-type header.
                    return await resp.json(content_type=None)
        except Nrf905AuthError:
            raise
        except aiohttp.ClientResponseError as err:
            if err.status in (401, 403):
                raise Nrf905AuthError(str(err)) from err
            raise Nrf905ApiError(str(err)) from err
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise Nrf905ConnectionError(str(err)) from err

    async def async_get_status(self) -> dict[str, Any]:
        """Return the first device object from querydevice.json."""
        data = await self._get(f"{self.base_url}{STATUS_PATH}")
        devices = []
        if isinstance(data, dict):
            devices = list((data.get("devices") or {}).values())
        if not devices:
            raise Nrf905ApiError("No devices returned by querydevice.json")
        return devices[0]

    async def async_set_speed(self, speed: str, timer: int | None = None) -> Any:
        """Set the ventilation speed, optionally with an auto-revert timer."""
        url = f"{self.base_url}{SETSPEED_PATH}?speed={speed}"
        if timer:
            url += f"&timer={timer}"
        return await self._get(url)
