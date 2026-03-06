---
name: petcam
description: "Control Bryan's pet camera on the Raspberry Pi. Usage: /petcam [on|off|status]"
user-invokable: true
argument-hint: "[on|off|status]"
metadata:
  {
    "openclaw":
      {
        "emoji": "📷",
        "requires": { "bins": ["curl"] },
      },
  }
---

# Petcam Control

You control Bryan's pet camera. Execute the appropriate curl command immediately — do not ask for confirmation.

## Action: on (or no argument)

Run this, then report "Pet cam started ✓" or "Pet cam is already running":

```bash
curl -s -X POST http://localhost:8082/start
```

## Action: off

Run this, then report "Pet cam stopped ✓":

```bash
curl -s -X POST http://localhost:8082/stop
```

## Action: status

Run this, then report running state in plain English ("Pet cam is running" / "Pet cam is off"):

```bash
curl -s http://localhost:8082/status
```

The response JSON is `{"running": true/false, "active_state": "active|inactive|failed"}`.

## Notes
- GoPro Hero 12 via USB. If unplugged, service starts but waits — tell Bryan to plug in the GoPro.
- Live stream: http://bryanfoslerpi5.local:8080 (login required).
- Motion alerts go to Bryan's phone via ntfy.sh when running.
