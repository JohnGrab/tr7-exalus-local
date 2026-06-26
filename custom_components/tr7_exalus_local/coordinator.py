"""Data update coordinator for TR7 Exalus."""

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL
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

        self.client.register_callback(self._handle_status_update)

        self._devices: dict[str, dict] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch current data from the TR7 system."""
        try:
            if not self.client.is_connected:
                if not await self.client.connect():
                    raise UpdateFailed("Connection to TR7 failed")

            devices = await self.client.get_all_devices()

            self._devices = {
                device["DeviceGuid"]: device
                for device in devices
                if "DeviceGuid" in device and device.get("position") is not None
            }

            return self._devices

        except Exception as err:
            _LOGGER.error("Error updating data: %s", err)
            raise UpdateFailed(f"Update failed: {err}") from err

    async def _handle_status_update(self, device_guid: str, data: dict) -> None:
        """Handle real-time status updates from the TR7 system."""
        _LOGGER.debug("Status update for %s: %s", device_guid, data)

        if device_guid not in self._devices:
            return

        self._devices[device_guid].update(data)
        self.async_set_updated_data(self._devices)

    async def async_set_position(self, device_guid: str, position: int) -> bool:
        """Set the position of a device."""
        try:
            return await self.client.set_position(device_guid, position)
        except Exception as err:
            _LOGGER.error("Error setting position: %s", err)
            return False

    async def async_open_cover(self, device_guid: str) -> bool:
        """Open a cover."""
        try:
            return await self.client.open_cover(device_guid)
        except Exception as err:
            _LOGGER.error("Error opening cover: %s", err)
            return False

    async def async_close_cover(self, device_guid: str) -> bool:
        """Close a cover."""
        try:
            return await self.client.close_cover(device_guid)
        except Exception as err:
            _LOGGER.error("Error closing cover: %s", err)
            return False

    async def async_stop_cover(self, device_guid: str) -> bool:
        """Stop a cover."""
        try:
            return await self.client.stop_cover(device_guid)
        except Exception as err:
            _LOGGER.error("Error stopping cover: %s", err)
            return False

    async def async_shutdown(self) -> None:
        """Shut down the coordinator cleanly."""
        await self.client.disconnect()
