"""Unit tests for TR7Client._handle_tasks_update — the is_moving tracking.

The /info/devices/tasks push carries a list of "<DeviceGuid>;<channel>;" strings
for motors that are currently running. _handle_tasks_update flips each device's
is_moving flag and fires callbacks only on a state transition. No hardware needed.
"""

import pytest

from tr7_api import TR7Client

GUID_A = "aaaabbbb-cccc-dddd-eeee-ffffffffffff"
GUID_B = "11112222-3333-4444-5555-666677778888"


@pytest.fixture
def client():
    c = TR7Client(host="127.0.0.1", port=81, email="installator@installator", password="DUMMY")
    # Pre-populate two known devices (as an initial state dump would).
    c._devices[GUID_A] = {"DeviceGuid": GUID_A, "position": 50}
    c._devices[GUID_B] = {"DeviceGuid": GUID_B, "position": 0}
    return c


def _tasks(*guids: str) -> dict:
    return {"Resource": "/info/devices/tasks", "Data": [f"{g};1;" for g in guids]}


async def test_motor_start_sets_is_moving_and_fires_callback(client):
    calls = []
    client.register_callback(lambda guid, data: calls.append((guid, data["is_moving"])))

    await client._handle_tasks_update(_tasks(GUID_A))

    assert client.devices[GUID_A]["is_moving"] is True
    assert client.devices[GUID_B].get("is_moving", False) is False
    assert calls == [(GUID_A, True)]


async def test_motor_stop_sets_is_moving_false_and_fires_callback(client):
    client._devices[GUID_A]["is_moving"] = True
    calls = []
    client.register_callback(lambda guid, data: calls.append((guid, data["is_moving"])))

    # Empty task list = nothing moving.
    await client._handle_tasks_update(_tasks())

    assert client.devices[GUID_A]["is_moving"] is False
    assert calls == [(GUID_A, False)]


async def test_no_transition_does_not_fire_callback(client):
    client._devices[GUID_A]["is_moving"] = True
    calls = []
    client.register_callback(lambda guid, data: calls.append(guid))

    # Still moving -> no state change -> no callback.
    await client._handle_tasks_update(_tasks(GUID_A))

    assert client.devices[GUID_A]["is_moving"] is True
    assert calls == []


async def test_only_listed_device_marked_moving(client):
    calls = []
    client.register_callback(lambda guid, data: calls.append(guid))

    await client._handle_tasks_update(_tasks(GUID_B))

    assert client.devices[GUID_B]["is_moving"] is True
    assert client.devices[GUID_A].get("is_moving", False) is False
    assert calls == [GUID_B]


async def test_guid_parsed_from_task_string(client):
    # The channel/trailing segments must be stripped, leaving the bare GUID.
    await client._handle_tasks_update({"Data": [f"{GUID_A};2;"]})
    assert client.devices[GUID_A]["is_moving"] is True


async def test_missing_data_key_stops_all(client):
    client._devices[GUID_A]["is_moving"] = True
    client._devices[GUID_B]["is_moving"] = True

    # A malformed/empty payload (no Data) must be treated as "nothing moving".
    await client._handle_tasks_update({})

    assert client.devices[GUID_A]["is_moving"] is False
    assert client.devices[GUID_B]["is_moving"] is False


async def test_unknown_guid_in_tasks_is_ignored(client):
    # A task for a device we have never seen must not crash or create an entry.
    await client._handle_tasks_update(_tasks("ffffffff-0000-0000-0000-000000000000"))

    assert "ffffffff-0000-0000-0000-000000000000" not in client.devices
    assert client.devices[GUID_A].get("is_moving", False) is False
