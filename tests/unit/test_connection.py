"""Unit tests for TR7Client connection resilience.

Covers the heartbeat probe (zombie-session detection), teardown failing
pending requests, and the disconnect-callback contract. No hardware required.
"""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from tr7_api import TR7Client, TR7Method
from websockets.protocol import State


@pytest.fixture
def client():
    return TR7Client(host="127.0.0.1", port=81, email="installator@installator", password="DUMMY")


def _responsive_ws(client, status=0):
    """A mock ws that answers every request with the given Status."""
    async def fake_send(raw):
        msg = json.loads(raw)
        tid = msg.get("TransactionId")
        fut = client._pending_responses.get(tid)
        if fut and not fut.done():
            fut.set_result({"Status": status, "TransactionId": tid})

    ws = AsyncMock()
    ws.state = State.OPEN
    ws.send = fake_send
    return ws


def _silent_ws(client):
    """A mock ws that accepts sends but never answers (zombie session)."""
    ws = AsyncMock()
    ws.state = State.OPEN
    ws.send = AsyncMock()  # swallow; pending future never resolves
    return ws


async def test_session_age_none_before_login(client):
    assert client.session_age is None


async def test_login_sets_session_age(client):
    client._ws = _responsive_ws(client, status=0)
    assert await client.login() is True
    age = client.session_age
    assert age is not None and age >= 0


async def test_teardown_clears_session_age(client):
    client._ws = _responsive_ws(client, status=0)
    await client.login()
    assert client.session_age is not None
    await client._teardown()
    assert client.session_age is None


async def test_heartbeat_true_when_server_responds(client):
    client._ws = _responsive_ws(client, status=0)
    client._authenticated = True
    assert await client.async_heartbeat() is True


async def test_heartbeat_true_on_denied_response(client):
    # Liveness = "the controller answered". A denied request (Status 4) still
    # proves the session is alive, so it must count as a successful heartbeat.
    client._ws = _responsive_ws(client, status=4)
    client._authenticated = True
    assert await client.async_heartbeat() is True


async def test_has_pending_requests_tracks_inflight(client):
    assert client.has_pending_requests is False
    client._pending_responses["tid"] = asyncio.get_running_loop().create_future()
    assert client.has_pending_requests is True
    client._pending_responses.clear()
    assert client.has_pending_requests is False


async def test_renew_session_skips_reconnect_when_busy(client):
    client.connect = AsyncMock(return_value=True)
    client._pending_responses["tid"] = asyncio.get_running_loop().create_future()
    # A command is in flight — keep the current session, do NOT tear it down.
    assert await client.renew_session() is True
    client.connect.assert_not_awaited()


async def test_renew_session_reconnects_when_idle(client):
    client.connect = AsyncMock(return_value=True)
    assert await client.renew_session() is True
    client.connect.assert_awaited_once()


async def test_connect_tears_down_on_login_failure(client, monkeypatch):
    # Socket opens fine, but login fails (e.g. times out). connect() must NOT
    # leave an open, unauthenticated socket that is_connected reports as healthy.
    async def hanging_iter():
        await asyncio.sleep(3600)
        yield  # pragma: no cover

    fake_ws = AsyncMock()
    fake_ws.state = State.OPEN
    fake_ws.__aiter__ = lambda self=fake_ws: hanging_iter()

    async def fake_ws_connect(*args, **kwargs):
        return fake_ws

    monkeypatch.setattr("tr7_api.ws_connect", fake_ws_connect)
    client.login = AsyncMock(return_value=False)

    assert await client.connect() is False
    assert client._ws is None
    assert client.is_connected is False
    assert client.is_authenticated is False


async def test_heartbeat_false_when_not_connected(client):
    # No socket at all.
    assert await client.async_heartbeat() is False


async def test_heartbeat_false_on_timeout(client):
    client._ws = _silent_ws(client)
    client._authenticated = True
    # Short timeout so the zombie probe fails quickly.
    assert await client.async_heartbeat(timeout=0.05) is False


async def test_teardown_fails_pending_requests(client):
    client._ws = _silent_ws(client)
    client._authenticated = True

    # Start a request that will never get a response, then tear down underneath it.
    task = asyncio.ensure_future(
        client._send_request(resource="/x", method=TR7Method.GET, data={}, timeout=5)
    )
    await asyncio.sleep(0)  # let the request register its pending future
    assert client._pending_responses

    await client._teardown()

    with pytest.raises(ConnectionError):
        await task
    assert client._pending_responses == {}
    assert client._ws is None
    assert client._authenticated is False


async def test_disconnect_callback_fired_on_drop(client):
    fired = []
    client.set_disconnect_callback(lambda: fired.append(True))

    # Simulate the receive loop ending because the socket closed.
    async def closing_iter():
        import websockets.exceptions
        raise websockets.exceptions.ConnectionClosed(None, None)
        yield  # pragma: no cover

    ws = AsyncMock()
    ws.state = State.OPEN
    ws.__aiter__ = lambda self=ws: closing_iter()
    client._ws = ws

    await client._receive_loop()

    assert fired == [True]
    assert client._authenticated is False


async def test_disconnect_callback_not_fired_on_cancel(client):
    fired = []
    client.set_disconnect_callback(lambda: fired.append(True))

    async def hanging_iter():
        await asyncio.sleep(3600)
        yield  # pragma: no cover

    ws = AsyncMock()
    ws.state = State.OPEN
    ws.__aiter__ = lambda self=ws: hanging_iter()
    client._ws = ws

    task = asyncio.ensure_future(client._receive_loop())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Deliberate cancellation must NOT trigger a reconnect notification.
    assert fired == []
