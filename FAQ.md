# Frequently Asked Questions

## General

### What is TR7 Exalus Local?

A custom Home Assistant integration for **local** control of Exalus Home roller blinds via the TR7 control unit — no cloud needed for day-to-day operation.

### Is an internet connection required?

**For initial setup**: the TR7 must have been configured via the Exalus Home app at least once, and the blinds must be paired.

**For daily use**: no. After setup, everything works locally. The TR7 can be blocked from internet access entirely.

### What hardware is required?

- TR7 Exalus control unit (connected via LAN)
- EX-BIDI or SSR-BIDI roller motors (868 MHz bidirectional)
- Home Assistant instance on the same network

### Does it work with other Exalus motors?

Designed for **EX-BIDI** motors. SSR-BIDI likely works too. Unidirectional 433 MHz motors are not compatible.

---

## Installation & Setup

### How do I find my TR7 IP address?

**Router admin**: look under *Connected devices* / *DHCP clients* for `TR7` or `Exalus`.

**Network scan**:
```bash
nmap -p 81 192.168.1.0/24
```

**Tip**: assign a static DHCP reservation so the IP never changes.

### Why isn't my TR7 found?

1. **Wrong IP** — try `ping <TR7_IP>`
2. **Port blocked** — try `nc -zv <TR7_IP> 81`
3. **Different network segment** — HA and TR7 must be on the same subnet (or routed)
4. **TR7 offline** — check the LAN cable and restart the device

---

## Authentication

### What credentials does the integration use?

The integration uses the **installator account**, not your Exalus cloud account. You only need the **serial number** and **PIN** from the label on the TR7 device. The integration derives the credentials automatically — you never enter an email or password.

### Do I need an Exalus Home cloud account?

Not for daily use. The TR7 must have been provisioned once with the Exalus Home app, but after that the integration operates entirely locally using the installator account (serial + PIN).

### Are my credentials stored securely?

Yes — Home Assistant stores config entry data encrypted. The serial number and PIN are not written in plain text anywhere.

---

## Control & Features

### What commands are supported?

- Open (100%) / Close (0%)
- Set position to any value 0–100%
- Stop
- Real-time status (position, state, battery, signal strength)

### How fast does control respond?

WebSocket push means command-to-motor latency is typically under 1 second. Status updates arrive immediately after movement.

### Can I control multiple TR7 units?

Yes — add multiple instances of the integration, each with its own IP.

### Are device groups supported?

Use Home Assistant's built-in cover group:
```yaml
cover:
  - platform: group
    name: "Ground floor blinds"
    entities:
      - cover.living_room_blind
      - cover.kitchen_blind
```

---

## Attributes & Automations

### How do I use attributes in automations?

```yaml
automation:
  - alias: "Battery warning"
    trigger:
      - platform: template
        value_template: >
          {{ state_attr('cover.living_room_blind', 'battery_level') | int < 20 }}
    action:
      - service: notify.notify
        data:
          message: "Blind battery low!"
```

### How do I expose battery as a sensor?

```yaml
template:
  - sensor:
      - name: "Living room blind battery"
        state: "{{ state_attr('cover.living_room_blind', 'battery_level') | int }}"
        unit_of_measurement: "%"
        device_class: battery
```

### Time-based automation example

```yaml
automation:
  - alias: "Open blinds at 7:00"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: cover.open_cover
        target:
          entity_id: cover.bedroom_blind
```

---

## Privacy & Security

### Is any data sent to the cloud?

No. All commands go directly from Home Assistant to the TR7 on your LAN. The integration never contacts any external server.

### How do I block the TR7 from internet access?

After initial provisioning you can firewall the TR7 completely:
- **Router firewall**: block outbound traffic from the TR7's IP to WAN
- **VLAN isolation**: put the TR7 on an IoT VLAN with no internet route
- **Pi-hole**: block `*.tr7.pl`

---

## Troubleshooting

### "Cannot connect"

```bash
ping <TR7_IP>
nc -zv <TR7_IP> 81
```

If ping works but port 81 is refused: restart the TR7 (unplug, wait 10 s, replug).

### "Authentication failed"

- Verify serial number and PIN on the TR7 device label
- Serial number is used **uppercase**; PIN is numeric only
- Run `python scripts/smoke_test.py` from the repo root for a detailed diagnostic

### No devices appear

1. Check that blinds are paired in the Exalus Home app
2. Reload the integration: **Settings → Devices & Services → TR7 Exalus → ⋮ → Reload**
3. Check logs: **Settings → Logs**

### Connection drops frequently

- Assign a static IP to the TR7 (DHCP reservation)
- Check DHCP lease time: increase to 86400 s (24 h) if it's short
- Verify network stability: `ping -c 600 <TR7_IP>` — packet loss should be 0%

---

## Updates

### How do I update the integration?

**Via HACS**: HACS → Integrations → TR7 Exalus Local → Update → restart HA.

**Manually**: replace `custom_components/tr7_exalus_local/` with the new version → restart HA.

Config entries and device assignments are preserved across updates.

---

## Further Questions?

→ [GitHub Discussions](https://github.com/JohnGrab/tr7-exalus-local/discussions)
