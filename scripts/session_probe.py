#!/usr/bin/env python3
"""Measure how long a TR7 authenticated session stays alive.

This answers the open question behind the "works fine, dead on the second day"
bug: does the TR7 drop the session on a fixed ~24 h TTL, or after a period of
inactivity (idle timeout)?

It logs in once, then sends a lightweight application-level request every
--interval seconds and records, for each probe, the elapsed time since login and
whether the controller answered. When a probe gets no response the session has
died — the script prints the measured session lifetime.

Run two experiments:

  # Active keepalive: probe every 30 s. If the session survives well past 24 h,
  # a periodic app-level request keeps it alive (idle-timeout hypothesis).
  python scripts/session_probe.py --interval 30

  # Sparse probing: probe rarely so the keepalive effect is minimal. If it still
  # dies at ~24 h, the expiry is a fixed absolute TTL (re-login is required).
  python scripts/session_probe.py --interval 1800

Add --reconnect to verify recovery: on a dead probe the script re-logs in and
keeps going, logging whether the reconnect succeeded.

Requires config.json in the repo root (see config.example.json).
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "custom_components" / "tr7_exalus_local"))
from tr7_api import TR7Client, TR7Method  # noqa: E402


def _fmt(seconds: float) -> str:
    """Format a duration as e.g. '1d 3h 12m 05s'."""
    td = timedelta(seconds=int(seconds))
    days, rem = divmod(td.total_seconds(), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{int(days)}d")
    parts.append(f"{int(hours)}h")
    parts.append(f"{int(minutes)}m")
    parts.append(f"{int(secs):02d}s")
    return " ".join(parts)


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


async def _probe(client: TR7Client, timeout: float) -> tuple[bool, float, object]:
    """Send one liveness request. Returns (alive, round_trip_seconds, status).

    Probes /devices/ — a cheap config endpoint that returns a transaction-matched
    response (Status 4 at installator level). Unlike /devices/channels/states it
    returns a real ack, so a response proves the session is alive regardless of
    the status value.
    """
    start = time.monotonic()
    try:
        response = await client._send_request(
            resource="/devices/",
            method=TR7Method.GET,
            data={},
            timeout=timeout,
        )
    except (TimeoutError, ConnectionError):
        return False, time.monotonic() - start, None
    return True, time.monotonic() - start, response.get("Status")


async def run(args: argparse.Namespace) -> None:
    with open(REPO_ROOT / "config.json") as f:
        cfg = json.load(f)["tr7"]

    serial = cfg["serial_number"].strip().upper()
    password = f"{serial}{cfg['pin'].strip()}"

    client = TR7Client(
        host=cfg["host"],
        port=cfg.get("port", 81),
        email="installator@installator",
        password=password,
    )

    _log(f"Connecting to ws://{cfg['host']}:{cfg.get('port', 81)}/api ...")
    if not await client.connect():
        _log("ERROR: connect/login failed — check config.json")
        return

    login_time = time.monotonic()
    _log(
        f"Logged in. Probing every {args.interval}s "
        f"(probe timeout {args.timeout}s, reconnect={'on' if args.reconnect else 'off'}). "
        f"Ctrl-C to stop."
    )

    probe_count = 0
    try:
        while True:
            await asyncio.sleep(args.interval)
            probe_count += 1
            alive, rtt, status = await _probe(client, args.timeout)
            age = time.monotonic() - login_time

            if alive:
                _log(f"#{probe_count}  ALIVE  session_age={_fmt(age)}  rtt={rtt * 1000:.0f}ms  status={status}")
            else:
                _log(f"#{probe_count}  DEAD   session DIED after {_fmt(age)} (no response in {args.timeout}s)")
                if not args.reconnect:
                    _log("Stopping. Re-run with --reconnect to measure repeated cycles.")
                    break
                _log("Reconnecting...")
                if await client.connect():
                    login_time = time.monotonic()
                    _log("Reconnect OK — session renewed, continuing.")
                else:
                    _log("Reconnect FAILED — retrying on next interval.")

            if args.max_hours and age >= args.max_hours * 3600:
                _log(f"Reached --max-hours={args.max_hours}; session still alive. Stopping.")
                break
    except KeyboardInterrupt:
        _log("Interrupted by user.")
    finally:
        await client.disconnect()
        _log("Disconnected.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=float, default=30.0,
                        help="seconds between probes (default 30; use a large value to test idle timeout)")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="seconds to wait for a probe response before calling the session dead (default 10)")
    parser.add_argument("--reconnect", action="store_true",
                        help="on a dead probe, re-login and keep measuring instead of stopping")
    parser.add_argument("--max-hours", type=float, default=0.0,
                        help="stop after this many hours even if still alive (0 = run until dead/Ctrl-C)")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
