"""Unit tests for the TR7Cover entity logic.

These exercise the entity's pure properties and command handlers against a
lightweight fake coordinator — no running Home Assistant instance is required,
but the ``homeassistant`` package must be importable (installed via the dev
extra). Command handlers call ``async_write_ha_state``, which needs a real
hass; we replace it with a Mock so the handler logic can be tested in isolation.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

# These tests need Home Assistant importable; skip the whole module otherwise
# (e.g. an environment with only the hardware-free deps installed).
pytest.importorskip("homeassistant.components.cover")

# cover.py uses package-relative imports (``from .const import ...``), so it must
# be imported via its full package path with the repo root on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from homeassistant.components.cover import ATTR_POSITION

from custom_components.tr7_exalus_local.cover import TR7Cover
from custom_components.tr7_exalus_local.const import ATTR_DEVICE_GUID, DOMAIN

GUID = "aaaabbbb-cccc-dddd-eeee-ffffffffffff"


def make_coordinator(device_data: dict, *, last_update_success: bool = True):
    """Build a minimal stand-in for TR7DataUpdateCoordinator."""
    coord = Mock()
    coord.data = {GUID: device_data} if device_data is not None else {}
    coord.last_update_success = last_update_success
    coord.client = SimpleNamespace(host="192.168.1.50")
    coord.async_open_cover = AsyncMock(return_value=True)
    coord.async_close_cover = AsyncMock(return_value=True)
    coord.async_stop_cover = AsyncMock(return_value=True)
    coord.async_set_position = AsyncMock(return_value=True)
    return coord


def make_cover(device_data: dict, **kwargs) -> TR7Cover:
    coordinator = make_coordinator(device_data, **kwargs)
    cover = TR7Cover(coordinator, GUID, coordinator.data.get(GUID, {}))
    # Command handlers write state; without a hass we stub it out.
    cover.async_write_ha_state = Mock()
    return cover


# --- Naming (bug: duplicate friendly name) -----------------------------------


def test_primary_entity_has_no_name():
    cover = make_cover({"position": 50})
    assert cover._attr_name is None  # inherits the device name


def test_device_info_uses_device_name():
    cover = make_cover({"position": 50})
    info = cover.device_info
    assert info["name"] == f"Cover {GUID[:8]}"
    assert info["manufacturer"] == "Exalus"


# --- Position inversion (TR7 0=open/100=closed <-> HA 0=closed/100=open) ------


@pytest.mark.parametrize(
    "tr7_pos, ha_pos",
    [(0, 100), (100, 0), (30, 70), (51, 49)],
)
def test_current_position_inverts(tr7_pos, ha_pos):
    cover = make_cover({"position": tr7_pos})
    assert cover.current_cover_position == ha_pos


def test_current_position_none_when_unknown():
    cover = make_cover({"position": None})
    assert cover.current_cover_position is None


def test_is_closed_only_when_ha_position_zero():
    assert make_cover({"position": 100}).is_closed is True   # TR7 closed
    assert make_cover({"position": 0}).is_closed is False     # TR7 open
    assert make_cover({"position": None}).is_closed is None


# --- Movement direction (bug 4: external move shows opening) ------------------


def test_is_opening_for_unknown_direction_when_moving():
    cover = make_cover({"position": 50, "is_moving": True})
    # No HA-initiated direction (external trigger) -> optimistically opening.
    assert cover._movement_direction is None
    assert cover.is_opening is True
    assert cover.is_closing is False


def test_is_opening_when_direction_opening():
    cover = make_cover({"position": 50, "is_moving": True})
    cover._movement_direction = "opening"
    assert cover.is_opening is True
    assert cover.is_closing is False


def test_is_closing_when_direction_closing():
    cover = make_cover({"position": 50, "is_moving": True})
    cover._movement_direction = "closing"
    assert cover.is_closing is True
    assert cover.is_opening is False


def test_not_moving_reports_neither():
    cover = make_cover({"position": 50, "is_moving": False})
    cover._movement_direction = "opening"
    assert cover.is_opening is False
    assert cover.is_closing is False


# --- Availability ------------------------------------------------------------


def test_available_true_when_update_ok_and_known():
    assert make_cover({"position": 50}).available is True


def test_unavailable_when_last_update_failed():
    assert make_cover({"position": 50}, last_update_success=False).available is False


def test_unavailable_when_guid_missing():
    cover = make_cover({"position": 50})
    cover.coordinator.data = {}  # device dropped from the coordinator
    assert cover.available is False


# --- Extra state attributes --------------------------------------------------


def test_extra_attributes_always_include_guid():
    cover = make_cover({"position": 50})
    assert cover.extra_state_attributes[ATTR_DEVICE_GUID] == GUID


def test_extra_attributes_include_signal_when_present():
    cover = make_cover({"position": 50, "signal_strength": 85, "signal_quality": 1})
    attrs = cover.extra_state_attributes
    assert attrs["signal_strength"] == 85
    assert attrs["signal_quality"] == 1


def test_extra_attributes_omit_absent_fields():
    cover = make_cover({"position": 50})
    assert "signal_strength" not in cover.extra_state_attributes
    assert "open_time" not in cover.extra_state_attributes


# --- Command handlers --------------------------------------------------------


async def test_open_sets_direction_opening():
    cover = make_cover({"position": 50})
    await cover.async_open_cover()
    cover.coordinator.async_open_cover.assert_awaited_once_with(GUID)
    assert cover._movement_direction == "opening"
    cover.async_write_ha_state.assert_called_once()


async def test_close_sets_direction_closing():
    cover = make_cover({"position": 50})
    await cover.async_close_cover()
    assert cover._movement_direction == "closing"
    cover.async_write_ha_state.assert_called_once()


async def test_stop_clears_direction():
    cover = make_cover({"position": 50})
    cover._movement_direction = "opening"
    await cover.async_stop_cover()
    assert cover._movement_direction is None
    cover.async_write_ha_state.assert_called_once()


async def test_failed_command_leaves_direction_untouched():
    cover = make_cover({"position": 50})
    cover.coordinator.async_open_cover = AsyncMock(return_value=False)
    await cover.async_open_cover()
    assert cover._movement_direction is None
    cover.async_write_ha_state.assert_not_called()


async def test_set_position_converts_and_picks_direction_opening():
    cover = make_cover({"position": 70})  # HA current = 30
    await cover.async_set_cover_position(**{ATTR_POSITION: 80})  # target > current
    # HA 80 -> TR7 20
    cover.coordinator.async_set_position.assert_awaited_once_with(GUID, 20)
    assert cover._movement_direction == "opening"


async def test_set_position_picks_direction_closing():
    cover = make_cover({"position": 30})  # HA current = 70
    await cover.async_set_cover_position(**{ATTR_POSITION: 10})  # target < current
    cover.coordinator.async_set_position.assert_awaited_once_with(GUID, 90)
    assert cover._movement_direction == "closing"


# --- Coordinator update ------------------------------------------------------


def test_coordinator_update_clears_direction_when_stopped():
    cover = make_cover({"position": 50, "is_moving": False})
    cover._movement_direction = "closing"
    cover._handle_coordinator_update()
    assert cover._movement_direction is None
    cover.async_write_ha_state.assert_called_once()


def test_coordinator_update_keeps_direction_while_moving():
    cover = make_cover({"position": 50, "is_moving": True})
    cover._movement_direction = "closing"
    cover._handle_coordinator_update()
    assert cover._movement_direction == "closing"
