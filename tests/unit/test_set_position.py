"""Unit tests for TR7Client.set_position — verifies correct WebSocket message format.

No hardware required. The WebSocket is mocked: send() captures the outgoing message
and immediately resolves the pending future so set_position does not time out.
"""

import json
import time
from unittest.mock import AsyncMock
import pytest

from tr7_api import TR7Client
from websockets.protocol import State


@pytest.fixture
def client():
    return TR7Client(host="127.0.0.1", port=81, email="installator@installator", password="SERIAL1234")


def _mock_ws(client):
    """Return a mock WebSocket that captures sent messages and auto-resolves futures."""
    sent = []

    async def fake_send(raw):
        msg = json.loads(raw)
        sent.append(msg)
        tid = msg.get("TransactionId")
        if tid and tid in client._pending_responses:
            client._pending_responses[tid].set_result({"Status": 0, "TransactionId": tid})

    ws = AsyncMock()
    ws.state = State.OPEN
    ws.send = fake_send
    return ws, sent


async def test_set_position_sends_correct_message(client):
    ws, sent = _mock_ws(client)
    client._ws = ws
    client._authenticated = True

    success = await client.set_position("device-guid-abc", 75)

    assert success is True
    assert len(sent) == 1
    msg = sent[0]
    assert msg["Resource"] == "/devices/device/control"
    assert msg["Method"] == 1                        # POST
    assert msg["Data"]["ControlFeature"] == 3
    assert msg["Data"]["SequnceExecutionOrder"] == 0  # firmware typo
    assert msg["Data"]["Data"] == 75
    assert msg["Data"]["DeviceGuid"] == "device-guid-abc"
    assert msg["Data"]["Channel"] == 1


async def test_set_position_rejects_out_of_range(client):
    with pytest.raises(ValueError):
        await client.set_position("guid", 101)
    with pytest.raises(ValueError):
        await client.set_position("guid", -1)


async def test_open_cover_sends_correct_message(client):
    ws, sent = _mock_ws(client)
    client._ws = ws
    client._authenticated = True

    success = await client.open_cover("device-guid-abc")

    assert success is True
    msg = sent[0]
    assert msg["Resource"] == "/devices/device/control"
    assert msg["Data"]["ControlFeature"] == 3
    assert msg["Data"]["Data"] == 0          # open = position 0
    assert msg["Data"]["DeviceGuid"] == "device-guid-abc"


async def test_close_cover_sends_correct_message(client):
    ws, sent = _mock_ws(client)
    client._ws = ws
    client._authenticated = True

    success = await client.close_cover("device-guid-abc")

    assert success is True
    msg = sent[0]
    assert msg["Data"]["ControlFeature"] == 3
    assert msg["Data"]["Data"] == 100        # close = position 100


async def test_move_up_sends_correct_message(client):
    ws, sent = _mock_ws(client)
    client._ws = ws
    client._authenticated = True

    success = await client.move_up("device-guid-abc")

    assert success is True
    msg = sent[0]
    assert msg["Resource"] == "/devices/device/control"
    assert msg["Data"]["ControlFeature"] == 3
    assert msg["Data"]["SequnceExecutionOrder"] == 0
    assert msg["Data"]["Data"] == 101
    assert msg["Data"]["DeviceGuid"] == "device-guid-abc"


async def test_move_down_sends_correct_message(client):
    ws, sent = _mock_ws(client)
    client._ws = ws
    client._authenticated = True

    success = await client.move_down("device-guid-abc")

    assert success is True
    msg = sent[0]
    assert msg["Resource"] == "/devices/device/control"
    assert msg["Data"]["ControlFeature"] == 3
    assert msg["Data"]["SequnceExecutionOrder"] == 0
    assert msg["Data"]["Data"] == 102
    assert msg["Data"]["DeviceGuid"] == "device-guid-abc"


async def test_stop_cover_sends_correct_message(client):
    ws, sent = _mock_ws(client)
    client._ws = ws
    client._authenticated = True

    await client.stop_cover("device-guid-abc")

    msg = sent[0]
    assert msg["Resource"] == "/devices/device/control"
    assert msg["Method"] == 1                        # POST
    assert msg["Data"]["ControlFeature"] == 3
    assert msg["Data"]["SequnceExecutionOrder"] == 0
    assert msg["Data"]["Data"] == 103                # stop command
    assert msg["Data"]["DeviceGuid"] == "device-guid-abc"
    assert msg["Data"]["Channel"] == 1


# --- Echo-suppression timer contract -----------------------------------------
# A position/open/close/move command records a timestamp so the redundant
# pre-movement BlindPosition frame can be filtered; stop clears it so the
# stopped-at frame is accepted immediately.


async def test_set_position_records_echo_timer(client):
    ws, sent = _mock_ws(client)
    client._ws = ws
    client._authenticated = True

    assert "device-guid-abc" not in client._last_command_time
    await client.set_position("device-guid-abc", 40)
    assert "device-guid-abc" in client._last_command_time


@pytest.mark.parametrize("call", ["open_cover", "close_cover", "move_up", "move_down"])
async def test_commands_record_echo_timer(client, call):
    ws, sent = _mock_ws(client)
    client._ws = ws
    client._authenticated = True

    await getattr(client, call)("device-guid-abc")
    assert "device-guid-abc" in client._last_command_time


async def test_stop_cover_clears_echo_timer(client):
    ws, sent = _mock_ws(client)
    client._ws = ws
    client._authenticated = True

    # Simulate a prior command having set the suppression window.
    client._last_command_time["device-guid-abc"] = time.monotonic()

    await client.stop_cover("device-guid-abc")

    assert "device-guid-abc" not in client._last_command_time
