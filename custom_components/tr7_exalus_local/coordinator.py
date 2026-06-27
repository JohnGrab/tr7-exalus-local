"""Data update coordinator for TR7 Exalus."""

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .connection import ConnectionManager, TR7Unavailable
from .const import DOMAIN, SESSION_RENEW_INTERVAL, UPDATE_INTERVAL
from .tr7_api import TR7Client

_LOGGER = logging.getLogger(__name__)


class TR7DataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for TR7 data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        email: str,
        password: str,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

        self.client = TR7Client(
            host=host,
            port=port,
            email=email,
            password=password,
        )

        self._connection = ConnectionManager(
            self.client,
            renew_interval=SESSION_RENEW_INTERVAL,
            update_interval=UPDATE_INTERVAL,
        )

        self.client.register_callback(self._handle_status_update)
        self.client.set_disconnect_callback(self._handle_disconnect)

        self._devices: dict[str, dict] = {}
        self._last_refresh_request: float = 0.0

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch current data; the poll doubles as a connection heartbeat.

        A TR7 session can silently expire while the socket stays open (commands
        then time out). The ConnectionManager actively verifies/reconnects the
        session; we surface its failure as UpdateFailed so entities go
        unavailable and the framework logs it once rather than spamming.
        """
        try:
            await self._connection.async_ensure_ready()

            devices = await self.client.get_all_devices()

            self._devices = {
                device["DeviceGuid"]: device
                for device in devices
                if "DeviceGuid" in device and device.get("position") is not None
            }

            return self._devices

        except TR7Unavailable as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"Update failed: {err}") from err

    @callback
    def _handle_disconnect(self) -> None:
        """Receive-loop reported a drop — reconnect promptly, but throttle flaps.

        We allow one immediate refresh, then suppress further ones for an
        interval: a single drop recovers instantly, while a flapping link can't
        hammer the controller (the regular poll still recovers it).
        """
        now = time.monotonic()
        if now - self._last_refresh_request < UPDATE_INTERVAL:
            return
        self._last_refresh_request = now
        self.hass.async_create_task(
            self.async_request_refresh(), name="tr7_exalus reconnect"
        )

    async def _handle_status_update(self, device_guid: str, data: dict) -> None:
        """Handle real-time status updates from the TR7 system."""
        _LOGGER.debug("Status update for %s: %s", device_guid, data)

        if device_guid not in self._devices:
            return

        self._devices[device_guid].update(data)
        self.async_set_updated_data(self._devices)

    async def _command_failed(self, action: str, err: Exception) -> bool:
        """Log a failed command and schedule a refresh to detect/repair a drop."""
        _LOGGER.error("Error %s: %s", action, err)
        # A timeout usually means the session died; force the next refresh to
        # actually probe/reconnect even within the session's "trust" window.
        self._connection.request_probe()
        await self.async_request_refresh()
        return False

    async def async_set_position(self, device_guid: str, position: int) -> bool:
        """Set the position of a device."""
        try:
            return await self.client.set_position(device_guid, position)
        except Exception as err:
            return await self._command_failed("setting position", err)

    async def async_open_cover(self, device_guid: str) -> bool:
        """Open a cover."""
        try:
            return await self.client.open_cover(device_guid)
        except Exception as err:
            return await self._command_failed("opening cover", err)

    async def async_close_cover(self, device_guid: str) -> bool:
        """Close a cover."""
        try:
            return await self.client.close_cover(device_guid)
        except Exception as err:
            return await self._command_failed("closing cover", err)

    async def async_stop_cover(self, device_guid: str) -> bool:
        """Stop a cover."""
        try:
            return await self.client.stop_cover(device_guid)
        except Exception as err:
            return await self._command_failed("stopping cover", err)

    async def async_shutdown(self) -> None:
        """Shut down the coordinator cleanly."""
        await self.client.disconnect()
