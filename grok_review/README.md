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
- **Mobile web remote** — control OBS from your phone (zero install, just open a URL)
- **Reaction overlay** — floating emoji reactions that rise and fade
- **Waveform visualization** — mirrored audio waveform at large size

## Install

```bash
# From source
git clone https://github.com/KHET-1/recbar.git
cd recbar
pip install .

# Or with the install script
./install.sh
```

### Dependencies

- Python 3.10+
- PyQt6
- websocket-client
- xdotool (for auto-scene switching)
- OBS Studio with WebSocket Server enabled (Tools → WebSocket Server Settings)

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

When RecBar launches, it starts a web server on port 5555. Open `http://YOUR_IP:5555` on your phone to get a full remote control with recording, scenes, reactions, and chapter marks.

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
├── state.py           Shared OBS state object
├── obs_client.py      WebSocket command helper
├── poller.py          Status polling thread
├── volume_meter.py    Real-time mic levels
├── auto_scene.py      Window-based scene switching
├── chapters.py        Chapter marks + markdown export
├── overlay.py         Reaction overlay + checklist
├── web_remote.py      Mobile HTTP remote
├── bar.py             Main indicator widget
├── ctl.py             CLI control tool
└── test_suite.py      Visual test suite
```

## License

MIT
