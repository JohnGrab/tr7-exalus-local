"""Unit tests for ConnectionManager — the reconnection *policy*.

These run against a mock client with no Home Assistant and no network, which is
exactly the coverage the policy lacked while it lived inside the coordinator.
Each test pins one transition: connect / renew / trust / probe / reconnect.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from connection import ConnectionManager, TR7Unavailable

RENEW = 12 * 60 * 60
INTERVAL = 30
TRUST = 2 * INTERVAL  # sessions younger than this are trusted (no probe)


def make_client(
    *,
    connected=True,
    authed=True,
    age=120.0,
    pending=False,
    connect=True,
    renew=True,
    heartbeat=True,
):
    c = Mock()
    c.is_connected = connected
    c.is_authenticated = authed
    c.session_age = age
    c.has_pending_requests = pending
    c.connect = AsyncMock(return_value=connect)
    c.renew_session = AsyncMock(return_value=renew)
    c.async_heartbeat = AsyncMock(return_value=heartbeat)
    return c


def manager(client):
    return ConnectionManager(client, renew_interval=RENEW, update_interval=INTERVAL)


async def test_reconnects_when_not_connected():
    c = make_client(connected=False)
    await manager(c).async_ensure_ready()
    c.connect.assert_awaited_once()
    c.async_heartbeat.assert_not_awaited()


async def test_reconnects_when_connected_but_unauthenticated():
    # An open-but-unauthenticated socket (login timed out) must reconnect.
    c = make_client(connected=True, authed=False)
    await manager(c).async_ensure_ready()
    c.connect.assert_awaited_once()


async def test_connect_failure_raises_unavailable():
    c = make_client(connected=False, connect=False)
    with pytest.raises(TR7Unavailable):
        await manager(c).async_ensure_ready()


async def test_renews_aged_idle_session():
    c = make_client(age=RENEW + 1, pending=False)
    await manager(c).async_ensure_ready()
    c.renew_session.assert_awaited_once()
    c.async_heartbeat.assert_not_awaited()


async def test_aged_busy_session_probes_instead_of_renewing():
    # Renewing would abort the in-flight command, so probe (not renew) when busy.
    c = make_client(age=RENEW + 1, pending=True)
    await manager(c).async_ensure_ready()
    c.renew_session.assert_not_awaited()
    c.async_heartbeat.assert_awaited_once()


async def test_renew_failure_raises_unavailable():
    c = make_client(age=RENEW + 1, pending=False, renew=False)
    with pytest.raises(TR7Unavailable):
        await manager(c).async_ensure_ready()


async def test_trusts_fresh_session():
    c = make_client(age=10)  # < TRUST
    await manager(c).async_ensure_ready()
    c.connect.assert_not_awaited()
    c.renew_session.assert_not_awaited()
    c.async_heartbeat.assert_not_awaited()


async def test_request_probe_forces_heartbeat_on_fresh_session():
    c = make_client(age=10)
    m = manager(c)
    m.request_probe()
    await m.async_ensure_ready()
    c.async_heartbeat.assert_awaited_once()


async def test_request_probe_is_one_shot():
    c = make_client(age=10)
    m = manager(c)
    m.request_probe()
    await m.async_ensure_ready()        # consumes the forced probe
    c.async_heartbeat.reset_mock()
    await m.async_ensure_ready()        # fresh again, no longer forced
    c.async_heartbeat.assert_not_awaited()


async def test_mature_live_session_probes_and_stays():
    c = make_client(age=120, heartbeat=True)  # > TRUST
    await manager(c).async_ensure_ready()
    c.async_heartbeat.assert_awaited_once()
    c.connect.assert_not_awaited()


async def test_zombie_session_reconnects():
    c = make_client(age=120, heartbeat=False)
    await manager(c).async_ensure_ready()
    c.async_heartbeat.assert_awaited_once()
    c.connect.assert_awaited_once()


async def test_zombie_reconnect_failure_raises():
    c = make_client(age=120, heartbeat=False, connect=False)
    with pytest.raises(TR7Unavailable):
        await manager(c).async_ensure_ready()