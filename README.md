# RecBar

Lightweight OBS recording companion bar for Linux.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![Platform Linux](https://img.shields.io/badge/platform-linux-orange)

## What It Does

RecBar sits at the edge of your screen and gives you always-visible recording awareness:

- **Pulsing REC dot** with dark halo, glow rings, and optional progress ring
- **Real-time mic VU meter** with green/yellow/red thresholds from actual OBS audio levels
- **Scene buttons** with emoji icons — click to switch
- **Chapter marks** — timestamp moments during recording, exported to markdown
- **Auto-scene switching** — automatically change OBS scenes based on active window
- **Mobile web remote** — control OBS from your phone (token-authenticated, zero install)
- **Reaction overlay** — floating emoji reactions that rise and fade
- **Waveform visualization** — mirrored audio waveform at large size

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

RecBar is the only always-visible Linux-native desktop bar with real mic VU + chapters + mobile remote in one package.

## Install

```bash
# From source
git clone https://github.com/KHET-1/recbar.git
cd recbar
pip install .

# Or with the install script
./install.sh

# With autostart on login
./install.sh --autostart
```

### Dependencies

- Python 3.10+
- PyQt6
- websocket-client
- xdotool (for auto-scene switching)
- OBS Studio with WebSocket Server enabled (Tools -> WebSocket Server Settings)

## Usage

```bash
recbar              # Launch the bar
recbar --top        # Position at top of screen
recbar --version    # Show version

recbar-ctl rec                  # Toggle recording
recbar-ctl pause                # Toggle pause
recbar-ctl mic                  # Toggle mic mute
recbar-ctl next                 # Next scene
recbar-ctl prev                 # Previous scene
recbar-ctl chapter "Intro"      # Add chapter mark
recbar-ctl target 30            # Set 30-min target (progress ring)
recbar-ctl react fire           # Spawn fire reaction
recbar-ctl auto_scene on        # Enable auto-scene switching

recbar-test                     # Run 14-step visual test suite
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
  Remote: http://192.168.1.100:5555?token=abc123...
```

Open that URL on your phone for full recording control — scenes, reactions, chapters, mic toggle. Token changes every launch. LAN-only.

## Configuration

Edit `~/.config/recbar/config.json`:

```json
{
    "position": "bottom",
    "recording_path": "~/Videos/OBS",
    "web_port": 5555,
    "obs_host": "localhost",
    "obs_port": 4455,
    "mic_input_name": "Mic/Aux",
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

## Architecture

```
recbar/
├── config.py          Config loading + constants
├── state.py           Shared OBS state + signal bridge
├── obs_connection.py  Single persistent WebSocket with message routing
├── obs_client.py      Fire-and-forget command wrapper
├── ipc.py             Unix socket IPC server/client
├── poller.py          OBS status polling (shared connection)
├── volume_meter.py    Real-time mic levels (callback handler)
├── auto_scene.py      Window-based scene switching (xdotool)
├── chapters.py        Chapter marks + markdown export
├── overlay.py         Reaction overlay + checklist (X11 click-through)
├── web_remote.py      Mobile HTTP remote + token auth
├── bar.py             Main indicator widget (8 paint helpers)
├── ctl.py             CLI control (Unix socket + file fallback)
└── test_suite.py      Visual test suite
```

See [CHANGELOG.md](CHANGELOG.md) for version history.

## License

MIT
