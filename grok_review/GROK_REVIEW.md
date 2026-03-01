# RecBar — Code Review Briefing for Grok 4.2

## What Is This?

**RecBar** is a lightweight desktop indicator bar for OBS Studio on Linux. It sits at the bottom (or top) of your screen and shows recording status, real-time mic levels, scene switching, chapter marks, and more. It also serves a mobile web remote so you can control OBS from your phone.

**This tool is novel.** No existing open-source project combines a desktop indicator bar + real-time mic VU + chapter marks + auto-scene switching + mobile web remote + reaction overlays into a single lightweight companion. The closest dead project is "OBS Toolbar" (Windows-only, abandoned 2021).

**Origin:** Built in a single session by Claude Opus (me) for a content creator who needed always-visible recording awareness while working across multiple monitor workflows. The monolith was then split into modules for open-source release.

---

## Architecture Overview

```
recbar/
├── __init__.py          9 lines   Package metadata + version
├── __main__.py         72 lines   Entry point, startup banner, arg handling
├── config.py           92 lines   Config loading from JSON, all derived constants
├── state.py            36 lines   OBSState (shared mutable state) + SignalBridge
├── obs_client.py       44 lines   obs_cmd() — fire-and-forget OBS WebSocket commands
├── poller.py          109 lines   OBSPoller thread — persistent WS, polls every 500ms
├── volume_meter.py     68 lines   VolumeMeter thread — real-time mic via InputVolumeMeters
├── auto_scene.py       47 lines   AutoSceneSwitcher thread — xdotool window class matching
├── chapters.py         74 lines   ChapterManager — timestamps + markdown export
├── overlay.py         230 lines   ReactionOverlay (fullscreen, click-through) + checklist
├── web_remote.py      190 lines   Mobile HTTP server + embedded HTML remote control
├── bar.py             587 lines   IndicatorBar — the main widget, 100% custom painted
├── ctl.py              74 lines   CLI control tool (recbar-ctl)
└── test_suite.py      105 lines   Visual test suite (14-step checklist)
                     ─────────
                      1,737 total (was 1,035 as monolith — growth from docs/structure)
```

### Dependency Graph

```
config.py ─────────────────────────────────────┐
state.py ──────────────────────────────────────┤
obs_client.py ← config                        │
poller.py ← config, state                     │
volume_meter.py ← config, state               │
auto_scene.py ← config, obs_client            │
chapters.py ← config                          │
overlay.py (standalone — PyQt6 only)           │
web_remote.py ← config, state, chapters       │
bar.py ← ALL of the above                     │
__main__.py ← config, bar                     │
ctl.py (standalone — no internal imports)      │
test_suite.py (standalone — file IPC only)     ┘
```

**No circular imports.** The dependency tree is strictly a DAG. `bar.py` is the sink (imports everything), `config.py` and `state.py` are the sources (import nothing internal).

---

## Technical Decisions & Rationale

### 1. 100% Custom Painting (no QWidgets)

The entire bar is drawn in `paintEvent()` using QPainter. No QLabels, QHBoxLayouts, or child widgets. **Why:** Layout with QWidgets broke on resize between 32px/64px/128px presets — text clipping, alignment drift, spacing inconsistency. Custom painting with proportional zones (`LAYOUT_ZONES` percentages) guarantees pixel-perfect layout at any size.

**Trade-off:** Harder to extend. Adding a new zone means editing LAYOUT_ZONES percentages AND the paintEvent. A widget-based approach would be more maintainable at the cost of visual control.

### 2. File-Based IPC (`/tmp/recbar_cmd`)

Commands from `recbar-ctl` and the web remote are written to a temp file, which the bar polls at 30fps. **Why:** Zero dependencies, dead simple, works across any language.

**Known weakness:** Two commands within the same 33ms frame will lose the first. Rapid-fire `recbar-ctl next && recbar-ctl next` may lose one. The visual test suite works around this with 80ms sleeps.

**Better approach:** Unix domain socket (SOCK_DGRAM) — reliable, ordered, zero message loss. This is the #1 upgrade priority.

### 3. Multiple WebSocket Connections to OBS

Currently three independent WebSocket connections:
- **OBSPoller:** Persistent, polls every 500ms (recording status, scenes, mic mute)
- **VolumeMeter:** Persistent, subscribed to InputVolumeMeters events only
- **obs_cmd():** Short-lived per command (opens, sends, closes)

**Why separate:** The Volume Meter needs `eventSubscriptions: 65536` (InputVolumeMeters), but the Poller needs request-response cycles without event noise. Mixing them on one socket would require message routing logic.

**Better approach:** Single persistent connection with message routing by requestId/eventType. Would reduce OBS load from 3 connections to 1.

### 4. X11 XShape for Click-Through Overlay

The reaction overlay is fullscreen but must not intercept any clicks. Qt's `WA_TransparentForMouseEvents` only works at the Qt level — X11 still routes events to the window. Solution: use ctypes to call `XShapeCombineRectangles` with 0 rectangles, setting an empty input shape.

**Limitation:** X11-only. On Wayland, the overlay falls back to Qt-level passthrough (which may intercept clicks in some compositors).

### 5. OBSState as Shared Mutable Object

All threads write to a single `OBSState` instance. Thread safety relies on CPython's GIL for atomic field writes.

**Risk:** If someone ports this to a non-GIL Python (free-threaded 3.13t), field writes become racy. Not a real concern today but worth noting.

### 6. Config from JSON File

`~/.config/recbar/config.json` with automatic fallback to `~/.config/obs-bar/config.json` for migration. Config is loaded once at import time.

**No hot-reload.** Editing the config requires restarting the bar. This is a conscious trade-off for simplicity.

---

## What Each Module Does (Detail)

### config.py
- Loads JSON config with `load_config()` → returns dict with sane defaults
- Derives all constants: `OBS_URL`, `MIC_NAME`, `SCENE_COLORS`, `AUTO_SCENE_RULES`, etc.
- `print_config_summary()` for startup diagnostics
- Handles migration from old `obs-bar` config path

### state.py
- `OBSState`: plain class with mutable fields (recording, paused, scene, mic_level, etc.)
- `SignalBridge`: QObject with a single `updated` pyqtSignal for thread→UI communication
- The deque `mic_history(maxlen=200)` stores waveform samples for visualization

### obs_client.py
- `obs_cmd(req_type, data)`: opens a short-lived WebSocket, authenticates (op:1), sends request (op:6), closes
- Runs in a daemon thread to avoid blocking the UI
- Silent failure by design (OBS may be disconnected)

### poller.py
- `OBSPoller`: daemon thread with persistent WebSocket connection
- Polls: `GetRecordStatus`, `GetCurrentProgramScene`, `GetSceneList`, `GetInputMute`
- Detects recording start/stop transitions → triggers `ChapterManager.on_rec_start/stop()`
- Disk space check via `shutil.disk_usage()` every ~5 seconds
- Emits `SignalBridge.updated` signal after each poll cycle

### volume_meter.py
- `VolumeMeter`: daemon thread subscribed to OBS InputVolumeMeters events
- Uses `eventSubscriptions: 65536` (1 << 16) during WebSocket identify
- Extracts `inputLevelsMul[0][1]` (peak) for the configured mic input
- Updates `state.mic_level` and appends to `state.mic_history`

### auto_scene.py
- `AutoSceneSwitcher`: polls `xdotool getactivewindow getwindowclassname` every 2 seconds
- Matches WM_CLASS against `AUTO_SCENE_RULES` from config
- Falls back to `AUTO_SCENE_DEFAULT` if no rule matches
- Only switches if target scene differs from current AND exists in OBS scene list

### chapters.py
- `ChapterManager`: tracks chapter marks with offsets relative to recording start
- `add(title)` → returns offset in seconds
- `on_rec_stop()` → exports to markdown file: `chapters_2026-02-28_14-30-00.md`
- `format_chapters()` → returns formatted strings for web remote API

### overlay.py
- `FloatingReaction`: rising emoji with drift, opacity fade, scale animation
- `ChecklistItem`: status (pending/running/pass/fail) with fade-in opacity
- `ReactionOverlay`: fullscreen QWidget, click-through via X11 XShape
- Renders at 30fps via QTimer, only repaints if there are active items
- Checklist API: `checklist_start/add/run/pass/fail/clear`

### web_remote.py
- `RemoteHandler`: handles GET / (HTML page), GET /status (JSON), POST /cmd (IPC write)
- `MobileServer`: daemon thread running HTTPServer on 0.0.0.0:PORT
- `MOBILE_HTML`: ~80 lines of embedded responsive HTML with dark theme
- Polls /status every 2 seconds, updates recording state, scenes, chapters
- REC button gets a glowing `recording` class when active (chef's kiss)
- Chapter input supports Enter key to submit

### bar.py
- `IndicatorBar`: main QWidget, 100% custom painted
- `LAYOUT_ZONES`: proportional zone system → `_zones()` computes pixel rects
- 3 size presets: 32px (slim), 64px (medium), 128px (large with waveform)
- `paintEvent()`: background → teal accent → REC zone → MIC zone → Scene name + waveform → Scene buttons → Time → Controls → REC dot (drawn LAST for Z-order)
- REC dot: dark halo → glow rings → red core → white-hot center pip → optional progress ring
- MIC VU bar: green (<55%) → yellow (<80%) → red (>80%) with segmentation lines
- Click zones: mic toggle, scene buttons, settings (cycle size), close
- Keyboard: Ctrl+1/2/3 (size), Ctrl+R/P/M (rec/pause/mic), Ctrl+Q (quit), Ctrl+Left/Right (scenes)
- Reads both `/tmp/recbar_cmd` and legacy `/tmp/obs_bar_cmd` for backward compat

### ctl.py
- Standalone CLI — no internal package imports
- Routes `react`, `scene`, `chapter`, `target`, `auto_scene`, `cl_*` commands with argument handling
- Named reaction map: fire, thumbsup, heart, rocket, star, clap, mind, party, 100, bolt

### test_suite.py
- 14-step visual test: resize bar, rec/pause/stop, mic toggle, scene switch, reaction burst
- Uses checklist overlay to show progress with pass/fail indicators
- Auto-clears after 15 seconds

---

## Known Issues & Limitations

1. **File IPC message loss** — Two commands within 33ms lose the first. Should migrate to Unix socket.
2. **3 WebSocket connections** — Wasteful. Should consolidate to 1 with message routing.
3. **No config hot-reload** — Must restart bar after editing config.json.
4. **X11-only features** — XShape passthrough and xdotool don't work on Wayland.
5. **No authentication** — Web remote on port 5555 has zero auth. Anyone on the LAN can control OBS.
6. **OBSState thread safety** — Relies on CPython GIL for atomic writes. Would break on free-threaded Python.
7. **No tests** — Zero pytest tests. The visual test suite tests the running system but there are no unit tests.
8. **bar.py is still 587 lines** — The paintEvent alone is ~220 lines. Could be split into painter helper methods.
9. **Hardcoded font** — JetBrains Mono and Noto Color Emoji. Should fall back gracefully if not installed.
10. **No systemd/autostart** — No .desktop file or systemd unit for auto-launch.

---

## Questions for Grok

I'd specifically like your critique on:

1. **Architecture:** Is the module split clean? Would you organize the package differently?
2. **Thread model:** 4 daemon threads (poller, volume meter, auto-scene, web server) all writing to shared OBSState. Is there a better concurrency model for this use case?
3. **The paintEvent approach:** 587 lines of custom painting vs. a proper QWidget tree with stylesheets. What's the right trade-off for a tool this size?
4. **IPC mechanism:** File polling vs. Unix socket vs. D-Bus vs. something else entirely?
5. **Web remote security:** What's the minimum viable auth for a LAN-only tool? Token in URL? mDNS discovery?
6. **What would you change** before recommending this to real users?
7. **What would you add** that isn't on the known issues list?
8. **Naming/branding:** RecBar vs. other names? What resonates for the OBS/streaming community?

---

## How to Read the Code

**Start here:** `recbar/__main__.py` (72 lines) — the entry point. Follow the imports.

**Core flow:**
1. `config.py` loads config → derives constants
2. `__main__.py` creates `QApplication` + `IndicatorBar`
3. `IndicatorBar.__init__()` spawns 4 daemon threads + creates overlay
4. Every 33ms: `animate()` → `_check_commands()` → `update()` → `paintEvent()`
5. `OBSPoller` polls OBS every 500ms → updates `OBSState` → emits signal → triggers repaint
6. `VolumeMeter` receives ~50ms InputVolumeMeters events → updates mic_level
7. External commands flow: CLI/remote → file write → bar reads → `_handle_cmd()` → action

**The painting order in bar.py paintEvent():**
1. Background fill (idle gray or recording red/yellow pulsing glow)
2. Top teal accent gradient
3. REC zone text (IDLE/REC/PAUSED/OFFLINE)
4. MIC zone (green dot + VU bar with real levels, or muted icon)
5. Scene name with emoji icon (+ waveform at size3)
6. Scene buttons (clickable, with active highlight)
7. Time display (recording timecode)
8. Controls (disk warning, auto-scene indicator, settings gear, close X)
9. **REC dot drawn LAST** — dark halo → glow rings → red core → white pip → progress ring

---

## File Listing (for reference)

```
~/projects/recbar/
├── .gitignore
├── LICENSE                   MIT
├── config.example.json       Example config with placeholder scenes
├── install.sh                Installer (pip install or manual)
├── pyproject.toml            Python packaging (pip install recbar)
├── GROK_REVIEW.md            This file
└── recbar/
    ├── __init__.py           Package metadata
    ├── __main__.py           Entry point
    ├── auto_scene.py         Auto-scene switcher (xdotool)
    ├── bar.py                Main indicator bar widget
    ├── chapters.py           Chapter mark manager
    ├── config.py             Configuration loading
    ├── ctl.py                CLI control tool
    ├── obs_client.py         OBS WebSocket command helper
    ├── overlay.py            Reaction overlay + checklist
    ├── poller.py             OBS status poller
    ├── state.py              Shared state object
    ├── test_suite.py         Visual test suite
    ├── volume_meter.py       Real-time mic levels
    └── web_remote.py         Mobile web remote
```

---

*Review requested by rathin. Code authored by Claude Opus 4.6 in a single session, then modularized for open-source release. February 2026.*
