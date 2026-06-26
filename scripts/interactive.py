#!/usr/bin/env python3
"""Interactive CLI for manually driving TR7 roller blinds.

Run from the repo root or from inside scripts/:
  python scripts/interactive.py

Requires config.json — see config.example.json.

Every session writes a timestamped log to logs/session_YYYYMMDD_HHMMSS.log.
Share that file for debugging.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# ── Path setup ───────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "custom_components" / "tr7_exalus_local"))
from tr7_api import TR7Client  # noqa: E402


# ── Session logging ───────────────────────────────────────────────────────────
def _setup_logging() -> Path:
    """Configure DEBUG file logging + WARNING console logging. Returns log path."""
    log_dir = REPO_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    fmt = logging.Formatter("%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s | %(message)s",
                            datefmt="%H:%M:%S")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    return log_path


_SESSION_LOG = logging.getLogger("session")


def _log_action(action: str, detail: str = ""):
    msg = f"ACTION: {action}"
    if detail:
        msg += f" | {detail}"
    _SESSION_LOG.info(msg)


def _log_result(label: str, result, detail: str = ""):
    msg = f"RESULT: {label} = {result!r}"
    if detail:
        msg += f" | {detail}"
    _SESSION_LOG.info(msg)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _await_motor_done(client: TR7Client, guid: str, max_wait: float = 90.0) -> None:
    """Block until the motor for *guid* stops (or *max_wait* seconds pass).

    Uses the is_moving flag set by /info/devices/tasks events.  Returns
    immediately if no motor task appears within 3 s (blind was already at
    target).
    """
    motor_started = asyncio.Event()
    motor_stopped = asyncio.Event()

    def _cb(device_guid: str, data: dict) -> None:
        if device_guid != guid:
            return
        is_moving = data.get("is_moving")
        if is_moving is True:
            motor_started.set()
        elif is_moving is False:
            motor_stopped.set()

    client.register_callback(_cb)
    try:
        # Bootstrap: the tasks event often arrives while set_position is still awaiting
        # its response, so is_moving may already be set before we registered _cb.
        status = await client.get_device_status(guid)
        if status:
            if status.get("is_moving") is True:
                motor_started.set()
            elif "is_moving" in status and not status["is_moving"]:
                # Motor started AND stopped before we arrived — treat as done.
                motor_started.set()
                motor_stopped.set()

        try:
            await asyncio.wait_for(motor_started.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            return  # no task → blind already at target

        if not motor_stopped.is_set():
            try:
                await asyncio.wait_for(motor_stopped.wait(), timeout=max_wait)
            except asyncio.TimeoutError:
                print("  (Timed out waiting for motor to stop)")

        # Brief pause so the final BlindPosition frame can arrive after tasks clear.
        await asyncio.sleep(0.5)
    finally:
        client.unregister_callback(_cb)


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    log_path = _setup_logging()
    print(f"\nSession log: {log_path}")
    _SESSION_LOG.info("=" * 60)
    _SESSION_LOG.info("Session started")

    with open(REPO_ROOT / "config.json") as f:
        cfg = json.load(f)["tr7"]

    _SESSION_LOG.info("Config: host=%s port=%s serial=%s",
                      cfg["host"], cfg.get("port", 81), cfg["serial_number"])

    email = "installator@installator"
    password = f"{cfg['serial_number'].upper().strip()}{cfg['pin'].strip()}"

    print("=" * 70)
    print("TR7 Exalus — Interactive Blind Control")
    print("=" * 70)
    print(f"Host: {cfg['host']}:{cfg.get('port', 81)}")
    print("=" * 70)

    client = TR7Client(
        host=cfg["host"],
        port=cfg.get("port", 81),
        email=email,
        password=password,
    )

    try:
        print("\nConnecting to TR7 ...")
        _log_action("connect", f"ws://{cfg['host']}:{cfg.get('port', 81)}/api")
        connected = await client.connect()
        _log_result("connect", connected)

        if not connected:
            print("Connection failed. Check host, serial number, and PIN.")
            return

        print("Connected and authenticated.\n")

        print("Collecting device information ...")
        await asyncio.sleep(3)

        # Try to fetch human-readable names from the controller
        device_names = await client.get_device_names()
        _SESSION_LOG.info("Device names: %s", device_names)

        devices = [d for d in await client.get_all_devices() if d.get("position") is not None]
        _SESSION_LOG.info("Devices found: %d  |  all devices: %s",
                          len(devices), json.dumps(list(client.devices.values()), indent=2))

        if not devices:
            print("No blinds with position data found.")
            print("Verify devices are paired in the Exalus Home app.")
            return

        _CAL_MAP = {0: "Uncalibrated", 1: "Calibrating", 2: "Calibrated"}

        def _display_name(device: dict) -> str:
            g = device.get("DeviceGuid", "")
            return device.get("name") or device_names.get(g) or g

        def _blind_info_lines(device: dict, indent: str = "  ") -> list[str]:
            """Return formatted info lines for a blind (overview and menu header)."""
            lines = []
            pos     = device.get("position")
            moving  = device.get("is_moving")
            sig     = device.get("signal_strength")
            sig_q   = device.get("signal_quality")
            last_ok = device.get("last_task_succeeded")
            open_t  = device.get("open_time")
            close_t = device.get("close_time")
            cal     = device.get("calibration_status")
            ch      = device.get("channel", 1)

            pos_str = f"{pos}%" if pos is not None else "?"
            if moving:
                pos_str += "  [moving]"
            lines.append(f"{indent}Position:       {pos_str}  (channel {ch})")

            if sig is not None:
                q_str = f"  quality {sig_q}" if sig_q is not None else ""
                ok_str = f"  last task {'OK' if last_ok else 'FAILED'}" if last_ok is not None else ""
                lines.append(f"{indent}Signal:         {sig}%{q_str}{ok_str}")

            if open_t is not None or close_t is not None:
                lines.append(f"{indent}Travel time:    ↑{open_t}s  ↓{close_t}s")

            if cal is not None:
                lines.append(f"{indent}Calibration:    {_CAL_MAP.get(cal, str(cal))}")

            return lines

        print(f"\n{'='*70}")
        print(f"Found {len(devices)} blind(s):")
        print(f"{'='*70}\n")

        for i, device in enumerate(devices, 1):
            name = _display_name(device)
            print(f"  [{i}] {name}")
            if name != device.get("DeviceGuid"):
                print(f"       GUID: {device.get('DeviceGuid')}")
            for line in _blind_info_lines(device, indent="       "):
                print(line)
            print()

        # Device selection
        while True:
            try:
                sel = input(f"Select blind (1–{len(devices)}) or 'q' to quit: ").strip()
                if sel.lower() == "q":
                    return
                idx = int(sel)
                if 1 <= idx <= len(devices):
                    selected = devices[idx - 1]
                    break
                print(f"  Enter a number between 1 and {len(devices)}")
            except ValueError:
                print("  Invalid input")

        guid = selected["DeviceGuid"]
        last_pos = selected.get("position")
        _log_action("select_device", f"guid={guid} position={last_pos}%")

        def on_update(device_guid, data):
            nonlocal last_pos
            _SESSION_LOG.info("CALLBACK: guid=%s data=%s", device_guid, json.dumps(data))
            if device_guid == guid:
                new_pos = data.get("position")
                if new_pos is not None and new_pos != last_pos:
                    print(f"  → Position: {last_pos}% → {new_pos}%")
                    last_pos = new_pos

        client.register_callback(on_update)

        # Control loop
        while True:
            current = client.devices.get(guid, {"DeviceGuid": guid})
            blind_label = _display_name(current)
            print(f"\n{'='*70}")
            print(f"Blind: {blind_label}")
            if blind_label != guid:
                print(f"  GUID: {guid}")
            for line in _blind_info_lines(current):
                print(line)
            print(f"  {'─'*66}")
            print("  [1] Open (0%)    [2] Close (100%)")
            print("  [3] Set position")
            print("  [4] Move up      [5] Move down")
            print("  [6] Stop         [7] Select different blind")
            print("  [q] Quit")
            print(f"{'='*70}")

            choice = input("Option: ").strip().lower()
            _log_action("menu_choice", choice)

            if choice == "q":
                break
            elif choice == "1":
                _log_action("open_cover", f"guid={guid}")
                result = await client.open_cover(guid)
                _log_result("open_cover", result)
                if result:
                    print("  Open command sent (→ 0%). Waiting for motor ...")
                    await _await_motor_done(client, guid)
                else:
                    print("  Command failed.")
            elif choice == "2":
                _log_action("close_cover", f"guid={guid}")
                result = await client.close_cover(guid)
                _log_result("close_cover", result)
                if result:
                    print("  Close command sent (→ 100%). Waiting for motor ...")
                    await _await_motor_done(client, guid)
                else:
                    print("  Command failed.")
            elif choice == "3":
                try:
                    raw = input("  Target position (0–100): ").strip()
                    target = int(raw)
                    if 0 <= target <= 100:
                        _log_action("set_position", f"guid={guid} target={target}")
                        result = await client.set_position(guid, target)
                        _log_result("set_position", result, f"target={target}")
                        if result:
                            print(f"  Position set to {target}%. Waiting for motor ...")
                            await _await_motor_done(client, guid)
                        else:
                            print("  Command failed.")
                    else:
                        print("  Position must be 0–100.")
                except ValueError:
                    print("  Invalid input.")
            elif choice == "4":
                _log_action("move_up", f"guid={guid}")
                result = await client.move_up(guid)
                _log_result("move_up", result)
                if result:
                    print("  Moving up ... (send Stop [6] to halt)")
                else:
                    print("  Command failed.")
            elif choice == "5":
                _log_action("move_down", f"guid={guid}")
                result = await client.move_down(guid)
                _log_result("move_down", result)
                if result:
                    print("  Moving down ... (send Stop [6] to halt)")
                else:
                    print("  Command failed.")
            elif choice == "6":
                _log_action("stop_cover", f"guid={guid}")
                result = await client.stop_cover(guid)
                _log_result("stop_cover", result)
                if result:
                    print("  Stopped.")
                else:
                    print("  Nothing to stop.")
            elif choice == "7":
                for i, d in enumerate(devices, 1):
                    current_d = client.devices.get(d["DeviceGuid"], d)
                    marker = "→" if d["DeviceGuid"] == guid else " "
                    pos_d = current_d.get("position", "?")
                    print(f"  {marker} [{i}] {_display_name(d)}  {pos_d}%")
                try:
                    sel = input(f"  Select (1–{len(devices)}): ").strip()
                    idx = int(sel)
                    if 1 <= idx <= len(devices):
                        selected = devices[idx - 1]
                        guid = selected["DeviceGuid"]
                        last_pos = client.devices.get(guid, selected).get("position")
                        _log_action("select_device", f"guid={guid} position={last_pos}%")
                except ValueError:
                    print("  Invalid input.")
            else:
                print("  Unknown option.")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        _SESSION_LOG.info("Session interrupted by user")
    except Exception as exc:
        import traceback
        _SESSION_LOG.exception("Unhandled exception: %s", exc)
        print(f"\nError: {exc}")
        traceback.print_exc()
    finally:
        await client.disconnect()
        _SESSION_LOG.info("Session ended")
        _SESSION_LOG.info("=" * 60)
        print(f"Disconnected.\n")
        print(f"Log saved to: {log_path}")


if __name__ == "__main__":
    asyncio.run(main())
