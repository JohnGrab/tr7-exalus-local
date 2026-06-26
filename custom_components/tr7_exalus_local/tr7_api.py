"""TR7 Exalus WebSocket API client."""

import asyncio
import inspect
import json
import logging
import time
import uuid
from typing import Any, Callable, Optional
from enum import Enum

from websockets.asyncio.client import ClientConnection, connect as ws_connect
from websockets.protocol import State
import websockets.exceptions

_LOGGER = logging.getLogger(__name__)


class TR7Method(Enum):
    """HTTP-style method codes used by the TR7 API."""
    GET = 0
    POST = 1
    PUT = 2
    LOGIN = 3


class TR7Client:
    """WebSocket client for the TR7 Exalus system."""

    def __init__(
        self,
        host: str,
        port: int = 81,
        email: str = "",
        password: str = "",
        use_ssl: bool = False,
    ):
        """Initialise the TR7 client."""
        self.host = host
        self.port = port
        self.email = email
        self.password = password
        self.use_ssl = use_ssl

        self._ws: Optional[ClientConnection] = None
        self._authenticated = False
        self._devices: dict[str, dict] = {}
        self._callbacks: list[Callable] = []
        self._pending_responses: dict[str, asyncio.Future] = {}
        self._receive_task: Optional[asyncio.Task] = None
        self._last_command_time: dict[str, float] = {}

    @property
    def uri(self) -> str:
        """WebSocket URI."""
        protocol = "wss" if self.use_ssl else "ws"
        return f"{protocol}://{self.host}:{self.port}/api"

    @property
    def is_connected(self) -> bool:
        """Return True if the connection is active."""
        if self._ws is None:
            return False
        return self._ws.state == State.OPEN

    @property
    def is_authenticated(self) -> bool:
        """Return True if authenticated."""
        return self._authenticated

    @property
    def devices(self) -> dict[str, dict]:
        """Return all known devices."""
        return self._devices

    async def connect(self) -> bool:
        """Establish a WebSocket connection and authenticate.

        Returns True on success, False on failure.
        """
        try:
            _LOGGER.info("Connecting to TR7 at %s", self.uri)
            self._ws = await ws_connect(
                self.uri,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10,
            )
            _LOGGER.info("Connected")

            self._receive_task = asyncio.create_task(self._receive_loop())

            await asyncio.sleep(0.1)

            if self.email and self.password:
                return await self.login()

            return True

        except Exception as e:
            _LOGGER.error("Connection error: %s", e)
            return False

    async def disconnect(self) -> None:
        """Close the connection cleanly."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            await self._ws.close()
            self._ws = None

        self._authenticated = False
        _LOGGER.info("Disconnected")

    async def login(self) -> bool:
        """Authenticate with the TR7 system.

        Returns True on success.
        """
        try:
            response = await self._send_request(
                resource="/users/user/login",
                method=TR7Method.LOGIN,
                data={"EMail": self.email, "Password": self.password},
            )

            if response.get("Status") == 0:
                self._authenticated = True
                _LOGGER.info("Login successful")
                await self._request_device_states()
                return True
            else:
                _LOGGER.error("Login failed: status %s", response.get("Status"))
                return False

        except Exception as e:
            _LOGGER.error("Login error: %s", e)
            return False

    async def _request_device_states(self) -> None:
        """Request the current state of all devices."""
        try:
            await self._send_request(
                resource="/devices/channels/states",
                method=TR7Method.GET,
                data={},
            )
            _LOGGER.debug("Device states requested")
        except Exception as e:
            _LOGGER.error("Error requesting device states: %s", e)

    def _record_command(self, device_guid: str) -> None:
        """Record the timestamp of an outgoing control command for echo suppression."""
        self._last_command_time[device_guid] = time.monotonic()

    async def set_position(self, device_guid: str, position: int, channel: int = 1) -> bool:
        """Set blind position (0–100%).

        0 = open/extended, 100 = closed/retracted.
        """
        self._record_command(device_guid)
        if not 0 <= position <= 100:
            raise ValueError("Position must be between 0 and 100")

        response = await self._send_request(
            resource="/devices/device/control",
            method=TR7Method.POST,
            data={
                "DeviceGuid": device_guid,
                "Channel": channel,
                "ControlFeature": 3,
                "SequnceExecutionOrder": 0,  # firmware typo — must match exactly
                "Data": position,
            },
        )

        return response.get("Status") == 0

    async def open_cover(self, device_guid: str, channel: int = 1) -> bool:
        """Open the blind (position 0 = open/extended)."""
        return await self.set_position(device_guid, 0, channel)

    async def close_cover(self, device_guid: str, channel: int = 1) -> bool:
        """Close the blind (position 100 = closed/retracted)."""
        return await self.set_position(device_guid, 100, channel)

    async def move_up(self, device_guid: str, channel: int = 1) -> bool:
        """Start continuous upward movement (Data=101)."""
        self._record_command(device_guid)
        response = await self._send_request(
            resource="/devices/device/control",
            method=TR7Method.POST,
            data={
                "DeviceGuid": device_guid,
                "Channel": channel,
                "ControlFeature": 3,
                "SequnceExecutionOrder": 0,
                "Data": 101,
            },
        )
        return response.get("Status") == 0

    async def move_down(self, device_guid: str, channel: int = 1) -> bool:
        """Start continuous downward movement (Data=102)."""
        self._record_command(device_guid)
        response = await self._send_request(
            resource="/devices/device/control",
            method=TR7Method.POST,
            data={
                "DeviceGuid": device_guid,
                "Channel": channel,
                "ControlFeature": 3,
                "SequnceExecutionOrder": 0,
                "Data": 102,
            },
        )
        return response.get("Status") == 0

    async def stop_cover(self, device_guid: str, channel: int = 1) -> bool:
        """Stop the blind at its current position (Data=103).

        Uses the same control endpoint as position commands.
        /devices/device/stop always returns status=4 during active tasks.
        Clears the echo-suppression timer so the stopped-at BlindPosition frame
        is accepted immediately rather than being filtered as a redundant echo.
        """
        self._last_command_time.pop(device_guid, None)
        response = await self._send_request(
            resource="/devices/device/control",
            method=TR7Method.POST,
            data={
                "DeviceGuid": device_guid,
                "Channel": channel,
                "ControlFeature": 3,
                "SequnceExecutionOrder": 0,
                "Data": 103,
            },
        )
        return response.get("Status") == 0

    async def get_device_names(self) -> dict[str, str]:
        """Fetch device names from the controller.

        Returns a {DeviceGuid: name} dict, empty if the endpoint is unavailable.
        """
        try:
            response = await self._send_request(
                resource="/devices/",
                method=TR7Method.GET,
                data={},
            )
            names: dict[str, str] = {}
            items = response.get("Data") or []
            if isinstance(items, list):
                for item in items:
                    guid = item.get("DeviceGuid") or item.get("Guid")
                    name = item.get("Name") or item.get("DeviceName")
                    if guid and name:
                        names[guid] = name
                        if guid in self._devices:
                            self._devices[guid]["name"] = name
            return names
        except Exception as e:
            _LOGGER.debug("Device names not available: %s", e)
            return {}

    async def get_device_status(self, device_guid: str) -> Optional[dict]:
        """Return the cached status dict for a device, or None."""
        return self._devices.get(device_guid)

    async def get_all_devices(self) -> list[dict]:
        """Return a list of all cached device dicts."""
        return list(self._devices.values())

    def register_callback(self, callback: Callable) -> None:
        """Register a callback for real-time status updates."""
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable) -> None:
        """Remove a previously registered callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def _send_request(
        self,
        resource: str,
        method: TR7Method,
        data: dict[str, Any],
    ) -> dict:
        """Send a request and wait for the matching response.

        Raises ConnectionError if not connected, TimeoutError on no response.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected")

        transaction_id = str(uuid.uuid4())

        message = {
            "TransactionId": transaction_id,
            "Data": data,
            "Resource": resource,
            "Method": method.value,
        }

        future = asyncio.Future()
        self._pending_responses[transaction_id] = future

        try:
            await self._ws.send(json.dumps(message))
            _LOGGER.debug(">>> SEND: %s", message)

            response = await asyncio.wait_for(future, timeout=10.0)
            return response

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout for transaction %s", transaction_id)
            raise TimeoutError("No response from server")

        finally:
            self._pending_responses.pop(transaction_id, None)

    async def _receive_loop(self) -> None:
        """Receive and dispatch messages from the server."""
        try:
            async for message in self._ws:
                try:
                    _LOGGER.debug("<<< RAW: %s", message)
                    data = json.loads(message)
                    _LOGGER.debug("<<< PARSED: %s", data)

                    transaction_id = data.get("TransactionId")
                    if transaction_id and transaction_id in self._pending_responses:
                        future = self._pending_responses[transaction_id]
                        if not future.done():
                            future.set_result(data)
                        continue

                    resource = data.get("Resource")
                    if resource == "/info/devices/device/state/changed":
                        await self._handle_status_update(data)
                    elif resource == "/info/devices/tasks":
                        await self._handle_tasks_update(data)

                except json.JSONDecodeError:
                    _LOGGER.warning("Invalid JSON message: %s", message)
                except Exception as e:
                    _LOGGER.error("Error processing message: %s", e)

        except websockets.exceptions.ConnectionClosed:
            _LOGGER.warning("Connection closed")
            self._authenticated = False
        except Exception as e:
            _LOGGER.error("Receive loop error: %s", e)

    async def _handle_status_update(self, data: dict) -> None:
        """Process a state-changed push notification from the server."""
        update_data = data.get("Data", {})
        device_guid = update_data.get("DeviceGuid")
        data_type = update_data.get("DataType")
        state = update_data.get("state", {})

        if device_guid:
            if device_guid not in self._devices:
                self._devices[device_guid] = {
                    "DeviceGuid": device_guid,
                    "position": None,
                    "signal_strength": None,
                    "channel": None,
                }

            device = self._devices[device_guid]

            if data_type == "BlindPosition":
                elapsed = time.monotonic() - self._last_command_time.get(device_guid, 0.0)
                if elapsed < 0.5:
                    # TR7 sends the current (pre-movement) position ~200 ms after every command.
                    # Skip it — value is already cached and firing a callback would cause
                    # unnecessary HA state writes with no new information.
                    _LOGGER.debug(
                        "Skipping redundant BlindPosition for %s (Position=%s, %.0f ms after command)",
                        device_guid, state.get("Position"), elapsed * 1000,
                    )
                    return
                device["position"] = state.get("Position")
                device["raw_position"] = state.get("RawPosition")
                device["channel"] = state.get("Channel", 1)
                device["reliability"] = state.get("StateReliability")
            elif data_type == "SignalStrength":
                # Real field is Percentage (0-100), not Value (old docs were wrong).
                device["signal_strength"] = state.get("Percentage")
                device["signal_quality"] = state.get("Quality")
                device["last_task_succeeded"] = state.get("DidLastTaskSucceded")
            elif data_type == "BlindOpenCloseTime":
                # Values are in milliseconds; convert to seconds for display.
                open_ms = state.get("OpenTime")
                close_ms = state.get("CloseTime")
                device["open_time"] = round(open_ms / 1000, 1) if open_ms is not None else None
                device["close_time"] = round(close_ms / 1000, 1) if close_ms is not None else None
            elif data_type == "BlindCalibration":
                device["calibration_status"] = state.get("CalibrationStatus")
            elif data_type == "ConfigurationState":
                device["config_state"] = state.get("Configuration")

            for callback in self._callbacks:
                try:
                    if inspect.iscoroutinefunction(callback):
                        await callback(device_guid, device)
                    else:
                        callback(device_guid, device)
                except Exception as e:
                    _LOGGER.error("Callback error: %s", e)

    async def _handle_tasks_update(self, data: dict) -> None:
        """Process a /info/devices/tasks push — updates is_moving on each affected device."""
        tasks = data.get("Data") or []
        active_guids: set[str] = set()
        for task_str in tasks:
            guid = task_str.split(";")[0]
            if guid:
                active_guids.add(guid)

        for guid, device in self._devices.items():
            was_moving = device.get("is_moving", False)
            is_now_moving = guid in active_guids
            if was_moving == is_now_moving:
                continue
            device["is_moving"] = is_now_moving
            _LOGGER.debug("Motor %s for %s", "started" if is_now_moving else "stopped", guid)
            for callback in self._callbacks:
                try:
                    if inspect.iscoroutinefunction(callback):
                        await callback(guid, device)
                    else:
                        callback(guid, device)
                except Exception as e:
                    _LOGGER.error("Callback error: %s", e)
