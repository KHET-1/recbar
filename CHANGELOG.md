# Changelog

## 1.2.0 — 2026-02-28

Platform hardening and remaining technical debt cleared.

### Added
- **Config hot-reload** — edit `config.json` and changes apply instantly (QFileSystemWatcher)
- **Platform detection** (`platform.py`) — X11/Wayland detection, font probing, xdotool check
- **Font fallback chain** — JetBrains Mono -> Fira Code -> DejaVu Sans Mono -> system monospace
- **Command dispatcher** (`commands.py`) — extracted from bar.py, testable independently
- **systemd user unit** (`recbar.service`) — `./install.sh --systemd` enables on login
- 15 new tests (platform detection + command dispatcher) — **34 total**

### Changed
- Wayland: skip X11BypassWindowManagerHint and XShape, auto-scene disabled with warning
- Auto-scene: exits immediately on Wayland or missing xdotool instead of spinning
- Overlay: skip XShape on Wayland, rely on Qt-level passthrough
- Keyboard shortcuts now route through CommandDispatcher (single code path)
- Startup banner shows session type and platform warnings
- bar.py reduced from 613 -> 584 lines (command handling extracted)

### Fixed
- Hardcoded "JetBrains Mono" / "Noto Color Emoji" — now auto-detected with fallbacks
- X11BypassWindowManagerHint crash on Wayland compositors

## 1.1.0 — 2026-02-28

Post-review hardening. All 5 priority items from Grok 4.2 review addressed.

### Added
- **Single persistent WebSocket** (`obs_connection.py`) — replaces 3 separate connections with 1 shared connection using requestId matching + event callback routing
- **Unix socket IPC** (`ipc.py`) — replaces file-based `/tmp/recbar_cmd` with `SOCK_DGRAM`. Zero message loss (50-command stress test)
- **Token auth for web remote** — random token per launch, all requests require `?token=XXX`
- **pytest test suite** — 19 tests covering config, chapters, IPC (0.23s)
- `.desktop` file for Linux desktop integration
- "Why RecBar" comparison section in README

### Changed
- `bar.py` paintEvent split from 220-line monolith into 18-line orchestrator + 8 named helpers
- `volume_meter.py` simplified from 68-line thread to 38-line callback handler
- `poller.py` uses shared connection instead of own WebSocket
- `obs_client.py` simplified to 20-line fire-and-forget wrapper
- `ctl.py` uses Unix socket with file fallback

### Fixed
- File IPC message loss under rapid commands
- Multiple WebSocket connections competing for OBS events

## 1.0.0 — 2026-02-27

Initial public release. Modular split from single-file obs-bar prototype.

- 14-module Python package with clean DAG dependency graph
- 100% custom QPainter rendering (no QWidgets)
- Real-time mic VU from OBS InputVolumeMeters
- Chapter marks with markdown export
- Auto-scene switching via xdotool
- Mobile web remote (HTTP)
- Reaction overlay with X11 click-through
- `pyproject.toml` packaging with 3 entry points
- MIT license
