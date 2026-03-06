# Comma4-UI-Streamer

Stream your comma 4's live sunnypilot/openpilot UI to any browser on your local network via MJPEG.

![comma 4](https://img.shields.io/badge/comma-4-blue) ![openpilot](https://img.shields.io/badge/openpilot-compatible-blue) ![sunnypilot](https://img.shields.io/badge/sunnypilot-compatible-green)

![Screenshot](screenshot.png)

## What you get

Open `http://<comma-ip>:8082` on your phone, infotainment screen, or any browser — and see the comma UI live with full HUD overlay (lane lines, lead car, speed, alerts).

**Endpoints:**
- `/` — fullscreen viewer page
- `/stream` — raw MJPEG stream
- `/snapshot` — grab a single frame

---

## Setup

sunnypilot already has the stream hook built into `system/ui/lib/application.py` — you just need to drop in the stream server and enable it.

### Step 1 — SSH into your comma

```bash
ssh comma@<your-comma-ip>
```

### Step 2 — Download the stream server

```bash
curl -sL https://raw.githubusercontent.com/peterclampton/Comma4-UI-Streamer/main/ui_stream.py -o /data/ui_stream.py
```

### Step 3 — Enable on boot

Add to `/data/openpilot/launch_env.sh`:

```bash
export STREAM=1
```

### Step 4 — Reboot and view

```bash
sudo reboot
```

Then open in your browser:

```
http://<comma-ip>:8082
```

That's it. No patching required — sunnypilot's UI framework automatically imports `/data/ui_stream.py` when `STREAM=1` is set.

---

## Configuration

Set these environment variables in `launch_env.sh`:

| Variable | Default | Description |
|----------|---------|-------------|
| `STREAM` | off | Set to `1` to enable streaming |
| `STREAM_PORT` | `8082` | HTTP port for the stream server |
| `STREAM_QUALITY` | `50` | JPEG quality (1–95) |
| `STREAM_FPS` | `20` | Target frame rate |

Example with all options:

```bash
export STREAM=1
export STREAM_PORT=8082
export STREAM_QUALITY=60
export STREAM_FPS=15
```

---

## Performance Notes

The stream captures frames from the raylib render texture inside the UI process. On the comma 4 (Snapdragon 845):

- **Parked:** Works great, no issues
- **Onroad:** May cause "driving model lagging" warnings at higher frame rates due to CPU contention with the driving model. If you see this, lower `STREAM_FPS` to 5–10 or disable streaming while driving

The stream has zero overhead when `STREAM=1` is not set.

---

## How it works

```
sunnypilot UI (raylib) → render texture → RGBA readback → JPEG encode → MJPEG HTTP
```

1. `application.py` checks for `STREAM=1` at startup and imports `ui_stream.py` from `/data/`
2. Each render frame, `capture_frame()` reads the raylib render texture
3. Converts RGBA → RGB JPEG at the configured quality
4. Pushes to connected MJPEG clients via HTTP multipart stream

---

## Compatibility

- **Hardware:** comma 4 (Snapdragon 845)
- **Software:** sunnypilot and openpilot — both use the same `pyray`-based UI framework
- **Browsers:** Safari (iOS), Chrome, Firefox — any browser that supports MJPEG

## Tested on

- comma 4
- sunnypilot staging (March 2026)
- 2017 Lexus RX350 (TSS-P)

## License

MIT
