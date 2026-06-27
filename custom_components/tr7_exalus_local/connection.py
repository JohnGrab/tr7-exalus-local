"""Connection lifecycle manager for the TR7 client.

All (re)connection *policy* lives here, deliberately free of Home Assistant
dependencies so it can be unit-tested against a mock client. The coordinator
keeps only the HA glue (scheduling refreshes, marking entities unavailable).

The single decision method ``async_ensure_ready`` is called once per poll and
drives these transitions from the client's own state:

    not connected/authenticated   -> (re)connect + login
    authenticated, session aged    -> proactively re-login (renew), if idle
    authenticated, session fresh   -> trust it (a successful login just proved
                                      the link), unless a probe was forced
    authenticated, session mature  -> heartbeat-probe; reconnect if it's a
                                      'zombie' (socket open, session dead)
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tr7_api import TR7Client

_LOGGER = logging.getLogger(__name__)


class TR7Unavailable(Exception):
    """Raised when a live, authenticated session cannot be established."""


class ConnectionManager:
    """Owns the connect / renew / probe / reconnect decisions for a TR7Client."""

    def __init__(
        self,
        client: "TR7Client",
        *,
        renew_interval: float,
        update_interval: float,
    ) -> None:
        """Initialise the manager.

        renew_interval: re-login proactively once the session is this old.
        update_interval: the poll cadence; the 'trust a fresh login' window is
            twice this, so a just-authenticated session is not re-probed for a
            couple of cycles.
        """
        self._client = client
        self._renew_interval = renew_interval
        self._trust_window = 2 * update_interval
        self._force_probe = False

    def request_probe(self) -> None:
        """Force the next async_ensure_ready() to actively probe.

        Used after a command fails: the failure is stronger evidence than the
        session's age, so we must verify liveness even on a fresh session rather
        than trust-gate it away.
        """
        self._force_probe = True

    async def async_ensure_ready(self) -> None:
        """Ensure an authenticated, live session. Raise TR7Unavailable if not."""
        force = self._force_probe
        self._force_probe = False

        client = self._client

        # A bare open socket is not enough — a login that timed out leaves an
        # OPEN but unauthenticated socket. Require an authenticated session.
        if not (client.is_connected and client.is_authenticated):
            await self._reconnect("Connection to TR7 failed")
            return

        age = client.session_age

        if (
            age is not None
            and age >= self._renew_interval
            and not client.has_pending_requests
        ):
            # Pre-empt the controller's ~24h session expiry — but never while a
            # command is in flight. renew_session() re-checks for in-flight
            # requests just before it tears the socket down.
            _LOGGER.debug("TR7 session aged %.1f h — renewing if idle", age / 3600)
            if not await client.renew_session():
                raise TR7Unavailable("Session renewal failed")
            return

        # Trust a freshly (re)authenticated session unless a probe was forced:
        # the login already proved the link works. Skipping the heartbeat for the
        # first couple of cycles also bounds reconnect churn if the heartbeat
        # endpoint turns out to be unreliable on some firmware.
        if not force and age is not None and age < self._trust_window:
            return

        if not await client.async_heartbeat():
            _LOGGER.warning("TR7 not responding; reconnecting")
            await self._reconnect("Reconnection to TR7 failed")

    async def _reconnect(self, error: str) -> None:
        """(Re)connect or raise TR7Unavailable."""
        if not await self._client.connect():
            raise TR7Unavailable(error)