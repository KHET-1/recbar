# RecBar

Lightweight OBS recording companion bar for Linux.

![CI](https://github.com/KHET-1/recbar/actions/workflows/ci.yml/badge.svg)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![Platform Linux](https://img.shields.io/badge/platform-linux-orange)
![Version](https://img.shields.io/badge/version-1.2.0-blueviolet)

## What It Looks Like

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ● REC  │ ● MIC ████████░░░░ │  🖥️  Desktop  │ 🖥️ 📷 📺 ⚡ │ 01:23:45 │ ● ⚙ ✕ │
└──────────────────────────────────────────────────────────────────────────────┘
  ↑ pulsing    ↑ real-time VU     ↑ scene name    ↑ buttons     ↑ timecode
  rec dot      from OBS peaks     + waveform       click to      + hints
                                   at large size   switch
```

Three size presets — **slim** (32px), **medium** (64px), **large** (128px with waveform):

```
Slim:    ┃● REC │ ● MIC ██░░ │ Desktop │ 🖥️📷📺 │ 01:23 │ ●⚙✕┃
Medium:  ┃● REC  │ ● MIC █████░░░ │  🖥️ Desktop  │ 🖥️ 📷 📺 │ 01:23:45 │ ● ⚙ ✕┃
Large:   ┃● REC   │ ● MIC ████████░░░░ │  🖥️  Desktop  ∿∿∿  │ 🖥️ 📷 📺 ⚡ │ 01:23:45 │ AUTO ● ⚙ ✕┃
                                          ↑ waveform
```

Mobile remote (phone browser, zero install):

```
┌─────────────────────┐
│   ⚡ RecBar Remote   │
│  ● REC 01:23:45     │
│                     │
│  ⏺ REC  ⏸ PAUSE  🎤│
│                     │
│  🖥️ Desktop  📷 Cam │
│  📺 Screen   ⚡ BRB │
│                     │
│  🔥 👍 ❤️ 🚀 💯 🎉  │
│                     │
│  [Chapter title___] │
│  + Add Chapter      │
└─────────────────────┘
```

## What It Does

RecBar sits at the edge of your screen and gives you always-visible recording awareness:

- **Pulsing REC dot** — dark halo, glow rings, optional progress ring (scales cleanly across all bar sizes)
- **Real-time mic VU meter** — green/yellow/red thresholds from actual OBS audio peaks
- **Scene buttons** — emoji icons, click to switch, current scene highlighted
- **Chapter marks** — timestamp moments during recording, export to markdown
- **Auto-scene switching** — change OBS scenes based on active window title (X11 + Wayland)
- **Mobile web remote** — token-authenticated, LAN-only, zero install required
- **Reaction overlay** — floating emoji that rise and fade, triggerable from remote
- **Waveform visualization** — mirrored audio waveform at large size (128px)
- **OBS WebSocket auth** — full challenge-response authentication (OBS 28+)
- **Config hot-reload** — edit `~/.config/recbar/config.json`, changes apply instantly
- **Pixel-perfect layout** — per-zone clipping prevents overlap at all three sizes

## Why RecBar

No other Linux tool combines all of these in one lightweight package:

| Feature | RecBar | OBS Core | Adv Scene Switcher | Touch Portal | Dream Deck |
|---------|--------|----------|-------------------|--------------|------------|
| Always-visible desktop bar | **Yes** | No | No | No | No |
| Real mic VU (OBS peaks) | **Yes** | Basic | No | No | No |
| Chapter marks + export | **Yes** | No | No | No | No |
| Auto-scene switching | **Yes** | Plugin | **Yes** | No | No |
| Mobile web remote | **Yes** | No | No | Yes (Wine) | Partial |
| Reaction overlay | **Yes** | No | No | No | No |
| Linux native | **Yes** | Yes | Yes | Wine only | Yes |
| Zero mouse once running | **Yes** | No | No | No | No |
| Wayland-aware | **Yes** | Yes | Partial | No | No |

RecBar is the only always-visible Linux-native desktop bar with real mic VU + chapters + mobile remote in one package.

## Install

```bash
# From source
git clone https://github.com/KHET-1/recbar.git
cd recbar
pip install .

# Or with the install script
./install.sh

# With autostart on login (systemd user unit)
./install.sh --autostart

# systemd only (no desktop file)
./install.sh --systemd
```

### Dependencies

- Python 3.10+
- PyQt6
- websocket-client
- xdotool (optional — for auto-scene switching on X11)
- OBS Studio 28+ with WebSocket Server enabled (Tools → WebSocket Server Settings)

## Usage

```bash
recbar              # Launch at bottom of screen
recbar --top        # Position at top of screen
recbar --version    # Show version

# Control from any terminal or script
recbar-ctl rec                  # Toggle recording
recbar-ctl pause                # Toggle pause
recbar-ctl mic                  # Toggle mic mute
recbar-ctl next                 # Next scene
recbar-ctl prev                 # Previous scene
recbar-ctl chapter "Intro"      # Add chapter mark
recbar-ctl target 30            # Set 30-min target (shows progress ring on rec dot)
recbar-ctl react fire           # Spawn fire reaction emoji
recbar-ctl auto_scene on        # Enable auto-scene switching

# Visual test suite (no OBS needed)
recbar-test
```

### Keyboard Shortcuts (when bar is focused)

| Shortcut | Action |
|----------|--------|
| Ctrl+R | Toggle recording |
| Ctrl+P | Toggle pause |
| Ctrl+M | Toggle mic mute |
| Ctrl+1/2/3 | Bar size (slim/medium/large) |
| Ctrl+Left/Right | Previous/next scene |
| Ctrl+Q | Quit |

### Mobile Remote

When RecBar launches, it prints a URL with a one-time auth token:

```
  Remote: http://192.168.1.100:7777?token=abc123...
```

Open that URL on your phone for full recording control — scenes, reactions, chapters, mic toggle. Token changes every launch. LAN-only, no external service.

## Configuration

Edit `~/.config/recbar/config.json` (hot-reloads on save — no restart needed):

```json
{
    "position": "bottom",
    "recording_path": "~/Videos/OBS",
    "web_port": 7777,
    "obs_host": "localhost",
    "obs_port": 4455,
    "obs_password": "",
    "mic_input_name": "Mic/Aux",
    "disk_warn_gb": 10,
    "scenes": {
        "Desktop":      {"color": "#2196F3", "icon": "🖥️"},
        "Webcam":       {"color": "#4CAF50", "icon": "📷"},
        "Screen Share": {"color": "#FF5722", "icon": "📺"}
    },
    "auto_scene_rules": [
        {"match": "firefox", "scene": "Screen Share"},
        {"match": "code",    "scene": "Desktop"}
    ],
    "auto_scene_default": "Desktop"
}
```

**`obs_password`** — set this if your OBS WebSocket server has a password configured. RecBar handles the full SHA-256 challenge-response handshake automatically.

## Architecture

```
recbar/                18 modules, ~2,200 lines
├── config.py          Config loading + hot-reload (QFileSystemWatcher)
├── state.py           Shared OBS state + signal bridge
├── platform.py        X11/Wayland detection + font probing
├── obs_connection.py  WebSocket with full OBS auth + message routing
├── obs_client.py      Fire-and-forget command wrapper
├── ipc.py             Unix socket IPC server/client
├── commands.py        Command dispatcher (extracted, testable)
├── poller.py          OBS status polling (shared connection)
├── volume_meter.py    Real-time mic levels (callback handler)
├── auto_scene.py      Window-based scene switching (X11 + Wayland)
├── chapters.py        Chapter marks + markdown export
├── overlay.py         Reaction overlay + checklist (Wayland-aware)
├── web_remote.py      Mobile HTTP remote + token auth
├── bar.py             Main indicator widget — proportional zone layout,
│                      per-zone painter clipping, 8 paint helpers
├── ctl.py             CLI control (Unix socket + file fallback)
└── test_suite.py      Visual test suite

tests/                 34 tests, ~0.25s
├── test_config.py     Config defaults, loading, presets
├── test_chapters.py   Chapter marks + export
├── test_ipc.py        Unix socket + 50-cmd stress test
├── test_platform.py   X11/Wayland detection
└── test_commands.py   Command dispatcher
```

### Layout System

RecBar uses a **proportional zone layout** — six zones defined as screen-width percentages:

```
rec 8% │ mic 14% │ scene 28% │ scenes 25% │ time 15% │ ctrl 10%
```

Each zone gets its own clipped `QPainter` context, so elements can never visually bleed into adjacent zones regardless of screen resolution or bar size. The REC dot is drawn last (above all zones) with widget-level clipping.

See [CHANGELOG.md](CHANGELOG.md) for version history.

## License

MIT
