"""Unit tests for TR7Client state-update parsing.

These tests call _handle_status_update() directly with captured JSON frames
and assert that the in-memory device map is updated correctly.
No WebSocket connection is required.
"""

import json
import time
from pathlib import Path

import pytest

from tr7_api import TR7Client

FIXTURES = Path(__file__).parent / "fixtures" / "state_changed.json"
GUID_A = "aaaabbbb-cccc-dddd-eeee-ffffffffffff"
GUID_B = "11112222-3333-4444-5555-666677778888"


@pytest.fixture
def client():
    return TR7Client(host="127.0.0.1", port=81, email="installator@installator", password="DUMMY")


@pytest.fixture
def messages():
    return json.loads(FIXTURES.read_text())


async def test_blind_position_parsed(client, messages):
    await client._handle_status_update(messages[0])

    device = client.devices[GUID_A]
    assert device["position"] == 26
    assert device["raw_position"] == 18
    assert device["channel"] == 1
    assert device["reliability"] == 0


async def test_signal_strength_parsed(client, messages):
    await client._handle_status_update(messages[0])  # initialise device
    await client._handle_status_update(messages[1])  # SignalStrength

    device = client.devices[GUID_A]
    assert device["signal_strength"] == 85        # Percentage field
    assert device["signal_quality"] == 1
    assert device["last_task_succeeded"] is True


async def test_open_close_time_parsed(client, messages):
    await client._handle_status_update(messages[0])  # initialise device
    await client._handle_status_update(messages[2])  # BlindOpenCloseTime

    device = client.devices[GUID_A]
    # Values are converted from milliseconds to seconds.
    assert device["open_time"] == 11.2
    assert device["close_time"] == 11.4


def _state_changed(data_type: str, state: dict) -> dict:
    return {
        "Resource": "/info/devices/device/state/changed",
        "Data": {"DeviceGuid": GUID_A, "DataType": data_type, "state": state},
    }


async def test_calibration_status_parsed(client):
    await client._handle_status_update(
        _state_changed("BlindCalibration", {"CalibrationStatus": 2, "Channel": 1})
    )
    assert client.devices[GUID_A]["calibration_status"] == 2


async def test_configuration_state_parsed(client):
    await client._handle_status_update(
        _state_changed("ConfigurationState", {"Configuration": 3, "Channel": 0})
    )
    assert client.devices[GUID_A]["config_state"] == 3


async def test_unknown_data_type_is_ignored(client):
    # An unrecognised DataType must still register the device but add no fields.
    await client._handle_status_update(_state_changed("SomethingNew", {"Foo": 1}))
    assert GUID_A in client.devices
    assert "Foo" not in client.devices[GUID_A]


async def test_multiple_devices_tracked(client, messages):
    for msg in messages:
        await client._handle_status_update(msg)

    assert len(client.devices) == 2
    assert client.devices[GUID_A]["position"] == 26
    assert client.devices[GUID_B]["position"] == 0


async def test_device_initialised_on_first_update(client, messages):
    assert GUID_A not in client.devices
    await client._handle_status_update(messages[0])
    assert GUID_A in client.devices
    assert client.devices[GUID_A]["DeviceGuid"] == GUID_A


async def test_subsequent_updates_preserve_existing_fields(client, messages):
    await client._handle_status_update(messages[0])  # sets position
    await client._handle_status_update(messages[1])  # sets signal_strength only

    device = client.devices[GUID_A]
    assert device["position"] == 26        # must not be overwritten
    assert device["signal_strength"] == 85


async def test_callback_invoked_on_update(client, messages):
    calls = []

    def on_update(device_guid, device_data):
        calls.append((device_guid, device_data))

    client.register_callback(on_update)
    await client._handle_status_update(messages[0])

    assert len(calls) == 1
    assert calls[0][0] == GUID_A


async def test_unregistered_callback_not_called(client, messages):
    calls = []

    def on_update(device_guid, device_data):
        calls.append(device_guid)

    client.register_callback(on_update)
    client.unregister_callback(on_update)
    await client._handle_status_update(messages[0])

    assert calls == []


async def test_blind_position_echo_within_window_is_suppressed(client, messages):
    calls = []
    client.register_callback(lambda guid, data: calls.append(guid))

    # Simulate a command having just been sent for GUID_A.
    client._last_command_time[GUID_A] = time.monotonic()

    await client._handle_status_update(messages[0])  # BlindPosition for GUID_A

    # The bogus echo must be dropped: position not written, callback not fired.
    assert client.devices[GUID_A].get("position") is None
    assert calls == []


async def test_blind_position_outside_window_is_accepted(client, messages):
    calls = []
    client.register_callback(lambda guid, data: calls.append(guid))

    # Simulate a command sent 1 s ago — outside the 500 ms suppression window.
    client._last_command_time[GUID_A] = time.monotonic() - 1.0

    await client._handle_status_update(messages[0])  # BlindPosition for GUID_A

    assert client.devices[GUID_A]["position"] == 26
    assert calls == [GUID_A]
