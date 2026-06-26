# TR7 Exalus — WebSocket API Reference

This documentation is based on **live tests** against a real TR7 system.

## Connection

### WebSocket Endpoint
```
ws://<TR7_IP>:81/api
```

> **Important:** The endpoint is `/api`, not just `/`.

### Authentication

Local API access uses the installator account, not your Exalus cloud account:

```json
{
  "TransactionId": "uuid-v4",
  "Resource": "/users/user/login",
  "Method": 3,
  "Data": {
    "EMail": "installator@installator",
    "Password": "<SERIAL_UPPERCASE><PIN>"
  }
}
```

**Password format:** serial number in uppercase + PIN, no spaces.  
Example: serial `TR7ABC` + PIN `1234` → password `TR7ABC1234`

**Success response:**
```json
{
  "Resource": "/users/user/login",
  "Data": null,
  "Status": 0,
  "Method": 3,
  "TransactionId": "..."
}
```

`Status: 0` = success.

---

## Message Structure

### Request
```json
{
  "TransactionId": "uuid-v4",
  "Resource": "/path/to/resource",
  "Method": 0,
  "Data": {}
}
```

### Method Codes
| Value | Meaning |
|-------|---------|
| `0` | GET |
| `1` | POST |
| `2` | PUT |
| `3` | LOGIN |

### Response
```json
{
  "Resource": "/path/to/resource",
  "Data": {},
  "Status": 0,
  "Method": 0,
  "TransactionId": "..."
}
```

### Status Codes
| Value | Meaning |
|-------|---------|
| `0` | Success |
| `4` | Error / invalid (e.g. STOP when nothing is moving) |

---

## Fetching Devices

### Request
```json
{
  "TransactionId": "uuid-v4",
  "Resource": "/devices/channels/states",
  "Method": 0,
  "Data": {}
}
```

### Response
There is **no** direct response with a device list. Instead the server pushes **multiple** asynchronous messages, one per device-attribute combination:

```json
{
  "Resource": "/info/devices/device/state/changed",
  "Data": {
    "DeviceGuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "DataType": "BlindPosition",
    "state": {
      "Position": 50,
      "RawPosition": 512,
      "Channel": 1,
      "StateReliability": 1
    }
  },
  "Status": 0,
  "Method": 0,
  "TransactionId": "..."
}
```

### DataTypes

Each device emits **multiple messages** with different `DataType` values:

#### `BlindPosition`
```json
{
  "DataType": "BlindPosition",
  "state": {
    "Position": 50,        // 0 = closed, 100 = open
    "RawPosition": 512,    // Raw encoder value
    "Channel": 1,
    "StateReliability": 1  // 0=Unknown, 1=Reliable, 2=Estimated
  }
}
```

#### `SignalStrength`
```json
{
  "DataType": "SignalStrength",
  "state": {
    "Value": 85
  }
}
```

#### `BlindOpenCloseTime`
```json
{
  "DataType": "BlindOpenCloseTime",
  "state": {
    "UpTime": 30,    // Seconds to open fully
    "DownTime": 32   // Seconds to close fully
  }
}
```

#### `BlindCalibration`
Blind calibration data.

#### `ConfigurationState`
Device configuration state.

---

## Device Control

### Open
```json
{
  "TransactionId": "uuid-v4",
  "Resource": "/devices/device/control",
  "Method": 1,
  "Data": {
    "DeviceGuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "Command": "Open",
    "Channel": 1
  }
}
```

### Close
```json
{
  "TransactionId": "uuid-v4",
  "Resource": "/devices/device/control",
  "Method": 1,
  "Data": {
    "DeviceGuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "Command": "Close",
    "Channel": 1
  }
}
```

### Set Position
```json
{
  "TransactionId": "uuid-v4",
  "Resource": "/devices/device/control",
  "Method": 1,
  "Data": {
    "DeviceGuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "Command": "Position",
    "Position": 50,
    "Channel": 1
  }
}
```

### Stop
```json
{
  "TransactionId": "uuid-v4",
  "Resource": "/devices/device/stop",
  "Method": 1,
  "Data": {
    "DeviceGuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "Channel": 1
  }
}
```

`Status: 0` = success (blind was moving)  
`Status: 4` = nothing to stop

---

## Real-Time Updates

After any command the server automatically pushes position updates:

```json
{
  "Resource": "/info/devices/device/state/changed",
  "Data": {
    "DeviceGuid": "...",
    "DataType": "BlindPosition",
    "state": { "Position": 75 }
  }
}
```

---

## Key Findings

1. Endpoint is `/api` — not `/`.
2. Installator account required — cloud credentials do **not** work locally.
3. No direct device list — state arrives as a stream of async messages.
4. Multiple `DataType` messages per device — position, signal, timing, etc.
5. `Status: 0` means success — different semantics from HTTP status codes.
6. Some devices send no `BlindPosition` — they may be a different device type.
