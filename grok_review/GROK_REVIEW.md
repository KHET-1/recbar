# RecBar — Code Review Briefing for Grok 4.2 (Round 2)

## What Is This?

**RecBar** is a lightweight desktop indicator bar for OBS Studio on Linux. It sits at the bottom (or top) of your screen and shows recording status, real-time mic levels, scene switching, chapter marks, and more. It also serves a mobile web remote so you can control OBS from your phone.

**This tool is novel.** No existing open-source project combines a desktop indicator bar + real-time mic VU + chapter marks + auto-scene switching + mobile web remote + reaction overlays into a single lightweight companion.

**Origin:** Built by Claude Opus 4.6 in a single session, then modularized and hardened based on your first review.

---

## What Changed Since Your Review

| Your Item | What We Did |
|-----------|-------------|
| Single persistent WebSocket | New `obs_connection.py` — 1 shared connection with requestId matching + event callback routing. VolumeMeter is now a 38-line callback handler, not a thread. |
| Split `bar.py` paintEvent | 220-line method → 18-line orchestrator + 8 named helpers (`_draw_rec_zone`, `_draw_mic_zone`, etc.) |
| File IPC → Unix socket | New `ipc.py` — `SOCK_DGRAM` Unix socket. 50-command stress test proves zero message loss. Legacy file fallback preserved. |
| Web remote auth | Random token on launch (`secrets.token_urlsafe`), all requests require `?token=XXX`, 403 without it. |
| pytest tests | 19 tests covering config, chapters, IPC. All passing in 0.23s. |

---

## Architecture Overview (Updated)

```
recbar/
├── __init__.py          9 lines   Package metadata
├── __main__.py         72 lines   Entry point, startup banner
├── config.py           92 lines   Config loading, all derived constants
├── state.py            36 lines   OBSState (shared mutable) + SignalBridge
├── obs_connection.py  167 lines   NEW — single persistent WebSocket, message routing
├── obs_client.py       20 lines   SIMPLIFIED — fire-and-forget via shared connection
├── ipc.py              99 lines   NEW — Unix SOCK_DGRAM IPC server/client
├── poller.py           88 lines   UPDATED — uses shared connection, not own WS
├── volume_meter.py     38 lines   SIMPLIFIED — callback handler, no thread
├── auto_scene.py       47 lines   AutoSceneSwitcher (xdotool)
├── chapters.py         74 lines   ChapterManager + markdown export
├── overlay.py         230 lines   ReactionOverlay + checklist (X11 click-through)
├── web_remote.py      226 lines   UPDATED — mobile remote + token auth
├── bar.py             613 lines   UPDATED — paintEvent split into 8 helpers
├── ctl.py             100 lines   UPDATED — Unix socket with file fallback
└── test_suite.py      105 lines   Visual test suite (14-step checklist)
                     ─────────
                      2,016 source + 256 tests = 2,272 total
```

### Dependency Graph (Updated)

```
config.py (standalone)
state.py (standalone)
obs_connection.py ← config
obs_client.py ← obs_connection (singleton pattern)
ipc.py (standalone)
poller.py ← config, obs_connection
volume_meter.py ← config (callback handler, no thread)
auto_scene.py ← config, obs_client
chapters.py ← config
overlay.py (standalone — PyQt6 only)
web_remote.py ← config, ipc
bar.py ← ALL of the above (sink node)
__main__.py ← config, bar
ctl.py ← ipc (standalone CLI)
test_suite.py (standalone — IPC only)
```

**No circular imports.** Strict DAG. Two new leaf nodes (`obs_connection.py`, `ipc.py`).

---

## Technical Decisions & Rationale

### 1. Single Persistent WebSocket (`obs_connection.py`)

One connection handles everything:
- **Poller** calls `conn.request("GetRecordStatus")` — blocks on `threading.Event`, woken by reader thread when matching requestId arrives
- **VolumeMeter** is registered as `event_callback` — reader thread calls `on_event()` for every op:5 message
- **obs_cmd()** calls `conn.send()` — fire-and-forget, no response wait
- **Auto-reconnect** with exponential backoff (1s → 2s → 4s → 10s cap)

Thread safety: `_send_lock` guards ws.send(), `_pending` dict maps requestId → Event for response routing.

**Trade-off:** If the poller sends a request while a volume event arrives, the reader thread handles both — events go to callback, responses wake the waiting Event. No message can be misrouted because requestIds are unique monotonic counters.

### 2. Unix Socket IPC (`ipc.py`)

`SOCK_DGRAM` Unix domain socket at `/tmp/recbar.sock`:
- **Server** (bar): non-blocking `recv()` called in animation loop, `recv_all()` drains queue
- **Client** (ctl/web): `sendto()` fire-and-forget, returns False if bar isn't running
- **Cleanup**: socket file removed on stop, stale file removed on start

**Why SOCK_DGRAM over SOCK_STREAM:** Each command is an atomic datagram — no framing, no partial reads, no connection management. Perfect for short command strings.

**Legacy fallback:** `ctl.py` tries Unix socket first, falls back to writing `/tmp/obs_bar_cmd` for old obs-bar-ctl users.

### 3. paintEvent Split

The orchestrator is now 18 lines:
```python
def paintEvent(self, event):
    ...setup...
    self._draw_background(painter, w, h, gw_base)
    self._draw_rec_zone(painter, zones["rec"], font, h)
    self._draw_mic_zone(painter, zones["mic"], sm, fs, h)
    self._draw_scene_name(painter, zones["scene"], font, h)
    self._draw_scene_buttons(painter, zones["scenes"], h)
    self._draw_time_zone(painter, zones["time"], font, fs, h)
    self._draw_controls(painter, zones["ctrl"], sm, fs, h)
    self._draw_rec_dot(painter, zones["rec"], h)
    painter.end()
```

Each helper is self-contained with a docstring. `_draw_rec_dot` is drawn last for Z-order (pops above glow effects).

### 4. Token Auth

```python
AUTH_TOKEN = secrets.token_urlsafe(16)  # generated once per launch
```

- Printed to console on startup as part of the full remote URL
- JavaScript extracts token from `?token=` query param and passes it on all fetch calls
- Handler checks token before processing any GET or POST
- 403 response on mismatch

### 5. 100% Custom Painting (unchanged rationale)

Still using QPainter for everything — no QWidgets. Proportional zones guarantee pixel-perfect layout across 32px/64px/128px presets.

### 6. X11 XShape for Click-Through Overlay (unchanged)

ctypes → XShapeCombineRectangles with 0 rectangles. X11-only, Wayland falls back to Qt-level passthrough.

---

## What Each Module Does

### obs_connection.py (NEW — 167 lines)
- `OBSConnection`: single persistent WebSocket with auto-reconnect
- Reader thread routes op:7 → `_pending[requestId].set()`, op:5 → `event_callback()`
- `request(req_type, data)`: blocking call with requestId matching, 3s timeout
- `send(req_type, data)`: fire-and-forget, no response wait
- `_next_id()`: monotonic counter for unique requestIds
- Exponential backoff on reconnect (1s → 10s cap)

### ipc.py (NEW — 99 lines)
- `IPCServer`: binds SOCK_DGRAM at `/tmp/recbar.sock`, non-blocking recv
- `send_command(cmd, path)`: client-side fire-and-forget via sendto
- `check_legacy_cmd_file()`: reads old `/tmp/obs_bar_cmd` for backward compat
- Socket permissions set to 0o666 so any user can send commands

### obs_client.py (SIMPLIFIED — 20 lines)
- `set_connection(conn)`: called once at startup to register shared connection
- `obs_cmd(req_type, data)`: delegates to `conn.send()` — one-liner

### volume_meter.py (SIMPLIFIED — 38 lines)
- No longer a thread — just a callback handler
- `on_event(event_data)`: filters for InputVolumeMeters, extracts peak level
- Registered as `event_callback` on OBSConnection

### poller.py (UPDATED — 88 lines)
- Now takes `connection` parameter, calls `conn.request()` instead of managing own WebSocket
- Waits for `conn.connected` before polling
- Recording transition detection unchanged

### web_remote.py (UPDATED — 226 lines)
- Added `AUTH_TOKEN`, `_check_auth()`, `_clean_path` property
- JavaScript extracts token from URL params, passes on all requests
- `get_remote_url()` returns full authenticated URL for console output
- Commands now sent via `send_command()` (Unix socket) instead of file write

### ctl.py (UPDATED — 100 lines)
- `_send_unix(cmd)`: primary — Unix socket sendto
- `_send_file(cmd)`: fallback — legacy file write
- Tries socket first, falls back to file, prints error if neither works

### bar.py (UPDATED — 613 lines)
- `__init__`: creates `IPCServer`, `OBSConnection`, `VolumeMeter` callback, wires everything
- `_check_commands()`: calls `self.ipc.recv_all()` + `check_legacy_cmd_file()`
- `paintEvent()`: 18-line orchestrator calling 8 helpers
- `closeEvent()`: stops connection, IPC server, overlay

### All other modules unchanged from first review.

---

## Test Suite

```
tests/
├── test_config.py      5 tests — defaults, file loading, malformed JSON, zone math, presets
├── test_chapters.py    7 tests — add/format/export/reset, not-recording guard
└── test_ipc.py         7 tests — send/recv, drain, empty, cleanup, nonexistent, message loss
                      ─────
                       19 tests, 0.23s
```

Key test: `test_no_message_loss` — sends 50 rapid-fire commands via Unix socket, verifies all 50 received in order. This directly proves the file-based IPC bug is fixed.

---

## Known Issues (Updated)

1. ~~File IPC message loss~~ **FIXED** — Unix socket
2. ~~3 WebSocket connections~~ **FIXED** — single shared connection
3. ~~No authentication~~ **FIXED** — token auth
4. ~~No tests~~ **FIXED** — 19 pytest tests
5. ~~Monolithic paintEvent~~ **FIXED** — 8 helpers
6. **No config hot-reload** — still requires restart after editing config.json
7. **X11-only features** — XShape passthrough and xdotool don't work on Wayland
8. **Hardcoded font** — JetBrains Mono / Noto Color Emoji, no fallback
9. **No systemd/autostart** — no .desktop file or systemd unit
10. **bar.py still 613 lines** — helpers helped, but it's still the biggest file

---

## Questions for Round 2

1. **OBSConnection thread safety** — Is the requestId matching pattern sound? Any race between `_pending` dict writes and reader thread reads?
2. **Unix socket vs D-Bus** — Was SOCK_DGRAM the right call, or should this be on D-Bus for better Linux integration?
3. **paintEvent granularity** — 8 helpers right, or should some be merged/split further?
4. **Token in URL** — Sufficient for LAN-only tool? Or should I use cookies/Authorization headers?
5. **What's still missing** before you'd recommend this to real users?

---

## File Listing

```
~/projects/recbar/
├── .gitignore
├── LICENSE                   MIT
├── README.md                 User-facing docs
├── config.example.json       Example config
├── install.sh                Installer
├── pyproject.toml            Packaging
├── GROK_REVIEW.md            This file (root copy)
├── grok_review/              Flat review folder (all files)
├── recbar/                   Package (16 modules)
└── tests/                    pytest suite (19 tests)
```

---

*Round 2 review. All 5 items from your first review addressed. Code on GitHub: https://github.com/KHET-1/recbar*
