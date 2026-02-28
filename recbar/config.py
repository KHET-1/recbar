"""Configuration loading and constants.

Loads user config from ~/.config/recbar/config.json with sane defaults.
All derived constants (OBS_URL, MIC_NAME, scene maps, etc.) are computed here.
"""

import os
import sys
import json

CONFIG_PATH = os.path.expanduser("~/.config/recbar/config.json")

# Fallback to old obs-bar config location for migration
_OLD_CONFIG = os.path.expanduser("~/.config/obs-bar/config.json")


def load_config():
    """Load config from JSON file, return defaults if missing or malformed."""
    defaults = {
        "position": "bottom",
        "recording_path": "~/Videos/OBS",
        "web_port": 5555,
        "disk_warn_gb": 5.0,
        "obs_host": "localhost",
        "obs_port": 4455,
        "mic_input_name": "Mic/Aux",
        "scenes": {},
        "auto_scene_rules": [],
        "auto_scene_default": "",
    }

    config_file = CONFIG_PATH
    if not os.path.exists(config_file) and os.path.exists(_OLD_CONFIG):
        config_file = _OLD_CONFIG

    try:
        with open(config_file) as f:
            user = json.load(f)
        defaults.update(user)
    except FileNotFoundError:
        pass
    except json.JSONDecodeError as e:
        print(f"  WARNING: Config parse error in {config_file}: {e}", file=sys.stderr)
        print(f"  Using defaults.", file=sys.stderr)

    return defaults


CFG = load_config()

# ── Derived constants ──────────────────────────────────────

SCENE_COLORS = {name: s["color"] for name, s in CFG["scenes"].items()}
SCENE_ICONS = {name: s.get("icon", "\U0001F4FA") for name, s in CFG["scenes"].items()}
DEFAULT_SCENE_COLOR = "#607D8B"
DEFAULT_SCENE_ICON = "\U0001F4FA"
IDLE_BG = "#1a1a2e"

SIZE_PRESETS = {
    1: (32,  10, 3,  80),    # slim:   height, font_size, _, glow_width
    2: (64,  16, 5,  120),   # medium
    3: (128, 28, 8,  180),   # large (waveform visible)
}

LAYOUT_ZONES = [
    ("rec",    0.08),
    ("mic",    0.14),
    ("scene",  0.28),
    ("scenes", 0.25),
    ("time",   0.15),
    ("ctrl",   0.10),
]

RECORDING_PATH = os.path.expanduser(CFG["recording_path"])
OBS_URL = f"ws://{CFG['obs_host']}:{CFG['obs_port']}"
MIC_NAME = CFG["mic_input_name"]
AUTO_SCENE_RULES = [(r["match"], r["scene"]) for r in CFG["auto_scene_rules"]]
AUTO_SCENE_DEFAULT = CFG["auto_scene_default"]
WEB_PORT = CFG["web_port"]
DISK_WARN_GB = CFG["disk_warn_gb"]


def print_config_summary():
    """Print startup config info for diagnostics."""
    print(f"  Config:    {CONFIG_PATH}")
    print(f"  OBS:       {OBS_URL}")
    print(f"  Mic:       {MIC_NAME}")
    print(f"  Scenes:    {len(CFG['scenes'])} configured")
    print(f"  Rec path:  {RECORDING_PATH}")
    print(f"  Web port:  {WEB_PORT}")
    if AUTO_SCENE_RULES:
        print(f"  Auto-scene: {len(AUTO_SCENE_RULES)} rules")
