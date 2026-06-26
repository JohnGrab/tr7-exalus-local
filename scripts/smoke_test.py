#!/usr/bin/env python3
"""Smoke test: connect, authenticate, then run a position sequence on a fixed blind.

Requires:
  config.json        — connection credentials (see config.example.json)
  scripts/smoke_test_config.json  — target blind GUID (see smoke_test_config.example.json):
    { "device_guid": "YOUR-BLIND-GUID" }

If smoke_test_config.json is absent or device_guid is missing the test lists all
discovered blinds and exits without running the position sequence.
"""

import asyncio
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "custom_components" / "tr7_exalus_local"))
from tr7_api import TR7Client  # noqa: E402

POSITION_TOLERANCE = 3   # percent — TR7 may stop within ±3% of target
STARTING_POSITION = 30   # percent — known baseline before test sequence begins


# ── helpers ───────────────────────────────────────────────────────────────────

# TR7 protocol: only 2 BlindPosition frames per movement:
#   1. ~200 ms after command  → current (pre-movement) position  [redundant, skipped by TR7Client]
#   2. ~100 ms after tasks=[] → final reached position
# Motor state is signalled via /info/devices/tasks (is_moving flag on device dict).
_MOTOR_START_WINDOW = 3.0   # seconds to wait for motor-started signal before assuming already at target


async def _wait_for_settled(client: TR7Client, device_guid: str,
                            timeout: float = 60.0) -> int | None:
    """Wait until the blind motor stops; return final position.

    Uses the is_moving flag (derived from /info/devices/tasks events) to detect
    motor start and stop.  Phase 1 waits up to _MOTOR_START_WINDOW seconds for
    the motor to start; if no task appears the blind was already at the target.
    Phase 2 waits for the motor to stop, then reads the final position.
    """
    motor_started = asyncio.Event()
    motor_stopped = asyncio.Event()
    last_pos: list[int | None] = [None]

    def on_update(guid: str, data: dict) -> None:
        if guid != device_guid:
            return
        pos = data.get("position")
        if pos is not None:
            if pos != last_pos[0]:
                print(f"    position: {pos}%")
            last_pos[0] = pos
        is_moving = data.get("is_moving")
        if is_moving is True:
            motor_started.set()
        elif is_moving is False:
            motor_stopped.set()

    client.register_callback(on_update)
    try:
        # Bootstrap: the tasks event often fires during set_position's own await, so
        # is_moving may already be set before _wait_for_settled is entered.
        status = await client.get_device_status(device_guid)
        if status:
            if status.get("is_moving") is True:
                motor_started.set()
            elif "is_moving" in status and not status["is_moving"]:
                motor_started.set()
                motor_stopped.set()

        # Phase 1: did the motor actually start?
        try:
            await asyncio.wait_for(motor_started.wait(), timeout=_MOTOR_START_WINDOW)
        except asyncio.TimeoutError:
            # No task → blind was already at target; return cached position.
            status = await client.get_device_status(device_guid)
            return status.get("position") if status else last_pos[0]

        # Phase 2: wait for motor to stop.
        if not motor_stopped.is_set():
            remaining = timeout - _MOTOR_START_WINDOW
            try:
                await asyncio.wait_for(motor_stopped.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                pass

        # Allow ~0.5 s for the final BlindPosition frame to arrive after tasks clear.
        await asyncio.sleep(0.5)
        status = await client.get_device_status(device_guid)
        return status.get("position") if status else last_pos[0]
    finally:
        client.unregister_callback(on_update)


# ── main ──────────────────────────────────────────────────────────────────────

async def run() -> None:
    with open(REPO_ROOT / "config.json") as f:
        cfg = json.load(f)["tr7"]

    smoke_cfg_path = REPO_ROOT / "scripts" / "smoke_test_config.json"
    device_guid = ""
    if smoke_cfg_path.exists():
        with open(smoke_cfg_path) as f:
            device_guid = json.load(f).get("device_guid", "").strip()

    serial = cfg["serial_number"].strip().upper()
    password = f"{serial}{cfg['pin'].strip()}"

    print("=" * 60)
    print("TR7 EXALUS — SMOKE TEST")
    print("=" * 60)
    print(f"  Host:   {cfg['host']}:{cfg.get('port', 81)}")
    print(f"  Serial: {serial}")

    client = TR7Client(
        host=cfg["host"],
        port=cfg.get("port", 81),
        email="installator@installator",
        password=password,
    )

    try:
        # ── Step 1: Connect ────────────────────────────────────────────────
        print(f"\nConnecting to ws://{cfg['host']}:{cfg.get('port', 81)}/api ...")
        if not await client.connect():
            print("  ✗ Connection / authentication failed")
            return
        print("  ✓ Connected and authenticated\n")

        # ── Step 2: Discover devices ───────────────────────────────────────
        print("Step 2: Discovering devices")
        await asyncio.sleep(3)   # let the initial state-changed flood arrive

        blinds = [d for d in await client.get_all_devices() if d.get("position") is not None]
        print(f"  Found {len(blinds)} blind(s):")
        for d in blinds:
            g = d["DeviceGuid"]
            marker = " ← target" if g == device_guid else ""
            print(f"    {g}  pos={d.get('position')}%{marker}")

        if not device_guid:
            print("\n  No smoke_test_config.json — create it to run position tests:")
            print("    cp scripts/smoke_test_config.example.json scripts/smoke_test_config.json")
            print('  Then set "device_guid" to one of the GUIDs above.')
            _summary(passed=0, failed=0, skipped=1)
            return

        if not any(d["DeviceGuid"] == device_guid for d in blinds):
            print(f"\n  ✗ device_guid {device_guid!r} not found in discovered devices.")
            _summary(passed=0, failed=1, skipped=0)
            return

        # ── Step 3: Position sequence ──────────────────────────────────────
        print(f"\nStep 3: Position sequence on {device_guid}")
        passed = failed = 0

        # Setup: move to a known starting position before the test sequence.
        status = await client.get_device_status(device_guid)
        current = status.get("position") if status else "?"
        print(f"\n  Setup) Current position: {current}%  →  moving to {STARTING_POSITION}% ...")
        await client.set_position(device_guid, STARTING_POSITION)
        pos = await _wait_for_settled(client, device_guid, timeout=90)
        ok = pos is not None and abs(pos - STARTING_POSITION) <= POSITION_TOLERANCE
        _check(f"starting position ≈ {STARTING_POSITION}%  (got {pos}%, ±{POSITION_TOLERANCE}%)", ok)
        if not ok:
            print("  Aborting — blind did not reach starting position.")
            _summary(passed=0, failed=1, skipped=0)
            return

        # 3a: move to 0% (open)
        print("\n  3a) Move to 0% (open) ...")
        await client.set_position(device_guid, 0)
        pos = await _wait_for_settled(client, device_guid, timeout=60)
        ok = pos is not None and abs(pos - 0) <= POSITION_TOLERANCE
        _check(f"position ≈ 0%  (got {pos}%, ±{POSITION_TOLERANCE}%)", ok)
        passed += ok; failed += not ok

        # 3b: move to 75% and stop mid-way
        print("\n  3b) Move to 75% ...")
        await client.set_position(device_guid, 75)
        stop_delay = random.uniform(1, 10)
        print(f"  3c) Stop mid-way after {stop_delay:.1f}s ...")
        await asyncio.sleep(stop_delay)

        await client.stop_cover(device_guid)
        pos = await _wait_for_settled(client, device_guid, timeout=15)
        ok = pos is not None and 0 < pos < 75
        _check(f"0 < position < 75  (got {pos}%)", ok)
        passed += ok; failed += not ok

        if pos is None:
            print("  Aborting — could not confirm stopped position.")
            _summary(passed, failed + 1, skipped=0)
            return
        print(f"    confirmed stopped at {pos}%")

        # 3d: move to 25%
        print("\n  3d) Move to 25% ...")
        await client.set_position(device_guid, 25)
        pos = await _wait_for_settled(client, device_guid, timeout=90)
        ok = pos is not None and abs(pos - 25) <= POSITION_TOLERANCE
        _check(f"position ≈ 25%  (got {pos}%, ±{POSITION_TOLERANCE}%)", ok)
        passed += ok; failed += not ok

        # 3e: move to 50%
        print("\n  3e) Move to 50% ...")
        await client.set_position(device_guid, 50)
        pos = await _wait_for_settled(client, device_guid, timeout=60)
        ok = pos is not None and abs(pos - 50) <= POSITION_TOLERANCE
        _check(f"position ≈ 50%  (got {pos}%, ±{POSITION_TOLERANCE}%)", ok)
        passed += ok; failed += not ok

        _summary(passed, failed, skipped=0)

    except Exception as exc:
        import traceback
        print(f"\n✗ Error: {exc}")
        traceback.print_exc()
    finally:
        await client.disconnect()
        print("Disconnected.")


def _check(label: str, ok: bool) -> None:
    print(f"  {'✓' if ok else '✗'} {label}")


def _summary(passed: int, failed: int, skipped: int) -> None:
    print("\n" + "=" * 60)
    if skipped:
        print(f"  Skipped {skipped} test(s) — see above")
    else:
        status = "PASSED" if failed == 0 else "FAILED"
        print(f"  {status}: {passed} passed, {failed} failed")
    print("=" * 60)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
