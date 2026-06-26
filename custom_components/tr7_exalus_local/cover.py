"""Cover platform for the TR7 Exalus Local integration."""

import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_BATTERY_LEVEL,
    ATTR_CALIBRATION_STATUS,
    ATTR_CLOSE_TIME,
    ATTR_DEVICE_GUID,
    ATTR_FIRMWARE,
    ATTR_LAST_TASK_SUCCEEDED,
    ATTR_OPEN_TIME,
    ATTR_SIGNAL_QUALITY,
    ATTR_SIGNAL_STRENGTH,
    DOMAIN,
)
from .coordinator import TR7DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TR7 cover entities from a config entry.

    Devices can appear after setup (their first state may arrive only after the
    initial refresh), so we add entities for any newly-seen GUID on every
    coordinator update rather than only once here.
    """
    coordinator: TR7DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    known_guids: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        new_guids = [guid for guid in coordinator.data if guid not in known_guids]
        if not new_guids:
            return
        known_guids.update(new_guids)
        _LOGGER.info("Adding %d TR7 cover entity/entities", len(new_guids))
        async_add_entities(
            TR7Cover(coordinator, guid, coordinator.data[guid]) for guid in new_guids
        )

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class TR7Cover(CoordinatorEntity[TR7DataUpdateCoordinator], CoverEntity):
    """Cover entity for a TR7 Exalus roller blind."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.SHUTTER

    def __init__(
        self,
        coordinator: TR7DataUpdateCoordinator,
        device_guid: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialise the cover entity."""
        super().__init__(coordinator)

        self._device_guid = device_guid
        self._attr_unique_id = f"{DOMAIN}_{device_guid}"
        self._device_name = device_data.get("Name", f"Cover {device_guid[:8]}")
        # Primary entity of the device: name is None so it inherits the device
        # name instead of producing a duplicated "<device> <entity>" friendly name.
        self._attr_name = None
        self._movement_direction: str | None = None

        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        device_data = self.coordinator.data.get(self._device_guid, {})

        return DeviceInfo(
            identifiers={(DOMAIN, self._device_guid)},
            name=self._device_name,
            manufacturer="Exalus",
            model="TR7 Rollomotor",
            sw_version=device_data.get(ATTR_FIRMWARE, "Unknown"),
            via_device=(DOMAIN, self.coordinator.client.host),
        )

    @property
    def available(self) -> bool:
        """Return True if the device is available."""
        return (
            self.coordinator.last_update_success
            and self._device_guid in self.coordinator.data
        )

    @property
    def current_cover_position(self) -> int | None:
        """Return current position in HA convention (0=closed, 100=open)."""
        device_data = self.coordinator.data.get(self._device_guid, {})
        tr7_pos = device_data.get("position")
        return 100 - tr7_pos if tr7_pos is not None else None

    @property
    def is_closed(self) -> bool | None:
        """Return True if the cover is closed."""
        position = self.current_cover_position
        return position == 0 if position is not None else None

    @property
    def is_opening(self) -> bool:
        """Return True if the cover is opening.

        For externally triggered moves (e.g. a wall switch) the firmware reports
        motion but no direction, so _movement_direction is None. In that case we
        optimistically report opening so the UI shows movement; a HA-initiated
        close is still reported correctly via is_closing.
        """
        device_data = self.coordinator.data.get(self._device_guid, {})
        return (
            device_data.get("is_moving") is True
            and self._movement_direction in (None, "opening")
        )

    @property
    def is_closing(self) -> bool:
        """Return True if the cover is closing."""
        device_data = self.coordinator.data.get(self._device_guid, {})
        return device_data.get("is_moving") is True and self._movement_direction == "closing"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        device_data = self.coordinator.data.get(self._device_guid, {})

        attributes: dict[str, Any] = {
            ATTR_DEVICE_GUID: self._device_guid,
        }

        if ATTR_BATTERY_LEVEL in device_data:
            attributes[ATTR_BATTERY_LEVEL] = device_data[ATTR_BATTERY_LEVEL]

        if device_data.get(ATTR_SIGNAL_STRENGTH) is not None:
            attributes[ATTR_SIGNAL_STRENGTH] = device_data[ATTR_SIGNAL_STRENGTH]

        if device_data.get(ATTR_SIGNAL_QUALITY) is not None:
            attributes[ATTR_SIGNAL_QUALITY] = device_data[ATTR_SIGNAL_QUALITY]

        if device_data.get(ATTR_LAST_TASK_SUCCEEDED) is not None:
            attributes[ATTR_LAST_TASK_SUCCEEDED] = device_data[ATTR_LAST_TASK_SUCCEEDED]

        if device_data.get(ATTR_OPEN_TIME) is not None:
            attributes[ATTR_OPEN_TIME] = device_data[ATTR_OPEN_TIME]

        if device_data.get(ATTR_CLOSE_TIME) is not None:
            attributes[ATTR_CLOSE_TIME] = device_data[ATTR_CLOSE_TIME]

        if device_data.get(ATTR_CALIBRATION_STATUS) is not None:
            attributes[ATTR_CALIBRATION_STATUS] = device_data[ATTR_CALIBRATION_STATUS]

        if ATTR_FIRMWARE in device_data:
            attributes[ATTR_FIRMWARE] = device_data[ATTR_FIRMWARE]

        return attributes

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        _LOGGER.debug("Opening cover %s", self._device_guid)
        success = await self.coordinator.async_open_cover(self._device_guid)
        if success:
            self._movement_direction = "opening"
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to open cover %s", self._device_guid)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        _LOGGER.debug("Closing cover %s", self._device_guid)
        success = await self.coordinator.async_close_cover(self._device_guid)
        if success:
            self._movement_direction = "closing"
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to close cover %s", self._device_guid)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        _LOGGER.debug("Stopping cover %s", self._device_guid)
        success = await self.coordinator.async_stop_cover(self._device_guid)
        if success:
            self._movement_direction = None
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to stop cover %s", self._device_guid)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set cover position."""
        ha_position = kwargs[ATTR_POSITION]          # HA: 0=closed, 100=open
        tr7_position = 100 - ha_position             # TR7: 0=open, 100=closed
        _LOGGER.debug("Setting position of %s to %d%% (TR7: %d%%)",
                      self._device_guid, ha_position, tr7_position)

        current = self.current_cover_position
        direction = "opening" if current is None or ha_position > current else "closing"

        success = await self.coordinator.async_set_position(
            self._device_guid, tr7_position
        )
        if success:
            self._movement_direction = direction
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set position of cover %s", self._device_guid)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        device_data = self.coordinator.data.get(self._device_guid, {})
        if not device_data.get("is_moving"):
            self._movement_direction = None
        self.async_write_ha_state()
