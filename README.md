# TR7 Exalus Local — Home Assistant Integration

A custom Home Assistant integration for **local** control of Exalus Home roller blinds via the TR7 control unit. No cloud required.

## Features

- **Fully local communication** — no cloud dependency after setup
- **Precise position control** — 0–100%
- **Real-time updates** — instant status feedback via WebSocket push
- **Automatic reconnection** — robust error handling
- **Rich attributes** — position, state, battery level, signal strength, firmware
- **Multilingual UI** — German & English

## Installation

### Prerequisites

- Home Assistant 2026.4.4 or newer
- TR7 Exalus control unit reachable on your local network
- TR7 serial number and PIN (found on the device label)

### Method 1: HACS (recommended)

1. Open HACS
2. Click **Integrations**
3. Click the menu (⋮) in the top right → **Custom repositories**
4. Add: `https://github.com/IHR-USERNAME/tr7-exalus-local` — Category: **Integration**
5. Search for **TR7 Exalus Local** and install
6. Restart Home Assistant

### Method 2: Manual

1. Download this repository
2. Copy `custom_components/tr7_exalus_local/` into your `<config_dir>/custom_components/`
3. Restart Home Assistant

## Configuration

1. **Settings** → **Devices & Services** → **Add Integration**
2. Search for **TR7 Exalus**
3. Enter:
   - **Host**: IP address of the TR7 unit (e.g. `192.168.1.160`)
   - **Port**: `81` (default)
   - **Serial number**: from the label on the TR7 device
   - **PIN**: from the label on the TR7 device

## Finding Your TR7 IP Address

**Router admin panel**: look under *Connected devices* / *DHCP clients* for `TR7` or `Exalus`.

**Network scan**:
```bash
nmap -p 81 192.168.1.0/24
```

**Recommended**: assign a static DHCP reservation for the TR7's MAC address so the IP never changes.

## Usage

### Basic commands

```yaml
service: cover.open_cover
target:
  entity_id: cover.living_room_blind

service: cover.set_cover_position
target:
  entity_id: cover.living_room_blind
data:
  position: 50

service: cover.stop_cover
target:
  entity_id: cover.living_room_blind
```

### Automation example

```yaml
automation:
  - alias: "Open blinds at sunrise"
    trigger:
      - platform: sun
        event: sunrise
        offset: "00:30:00"
    action:
      - service: cover.open_cover
        target:
          entity_id:
            - cover.living_room_blind
            - cover.bedroom_blind

  - alias: "Sun protection above 28°C"
    trigger:
      - platform: numeric_state
        entity_id: sensor.outdoor_temperature
        above: 28
    condition:
      - condition: sun
        after: sunrise
        before: sunset
    action:
      - service: cover.set_cover_position
        target:
          entity_id: cover.south_blind
        data:
          position: 25
```

## Available Attributes

| Attribute | Description |
|-----------|-------------|
| `position` | Current position (0–100%) |
| `state` | `idle` / `opening` / `closing` / `stopped` / `error` |
| `device_guid` | Unique device ID |
| `battery_level` | Battery level (if available) |
| `signal_strength` | RSSI in dBm |
| `firmware` | Firmware version |

## Troubleshooting

**"Failed to connect"**: verify the IP with `ping <TR7_IP>` and the port with `nc -zv <TR7_IP> 81`. Restart the TR7 if needed.

**"Unauthorized"**: double-check the serial number (must be uppercase) and PIN on the device label.

**No devices found**: confirm the blinds are registered in the Exalus Home app, then reload the integration: **Integrations → TR7 Exalus → ⋮ → Reload**.

**Enable debug logging**:
```yaml
# configuration.yaml
logger:
  default: info
  logs:
    custom_components.tr7_exalus_local: debug
```

## Testing Without Home Assistant

```bash
pip install websockets
cp config.example.json config.json
# Edit config.json with your TR7 host, serial number, and PIN
python scripts/smoke_test.py
```

## Further Reading

- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) — WebSocket protocol reference
- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution guide and testing setup
- [FAQ.md](FAQ.md) — common questions

## License

MIT — see [LICENSE](LICENSE)

## Links

- [Home Assistant](https://www.home-assistant.io/)
- [Exalus Home System](https://www.tr7.pl/en/exalus-home-system/)
- [GitHub Issues](https://github.com/IHR-USERNAME/tr7-exalus-local/issues)

---

*Unofficial project — not affiliated with or endorsed by Exalus or TR7.*
