#!/bin/bash
# RecBar installer — pip install or manual drop into ~/.local/bin
set -e

CONFIG_DIR="$HOME/.config/recbar"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  ⚡ RecBar Installer"
echo "  ════════════════════"
echo ""

# Check Python version
python_ok=$(python3 -c "import sys; print(1 if sys.version_info >= (3, 10) else 0)" 2>/dev/null || echo 0)
if [ "$python_ok" != "1" ]; then
    echo "  ERROR: Python 3.10+ required"
    exit 1
fi

# Check dependencies
missing=()
python3 -c "import PyQt6" 2>/dev/null || missing+=("PyQt6")
python3 -c "import websocket" 2>/dev/null || missing+=("websocket-client")
command -v xdotool &>/dev/null || missing+=("xdotool (apt install xdotool)")

if [ ${#missing[@]} -gt 0 ]; then
    echo "  Missing dependencies: ${missing[*]}"
    echo ""
    echo "  Install with:"
    echo "    pip install PyQt6 websocket-client"
    echo "    sudo apt install xdotool"
    echo ""
    read -p "  Continue anyway? [y/N] " -n 1 -r
    echo ""
    [[ ! $REPLY =~ ^[Yy]$ ]] && exit 1
fi

# Install via pip (editable mode for development, or standard)
if [ "$1" = "--dev" ]; then
    echo "  Installing in editable mode..."
    pip install -e "$SCRIPT_DIR" --break-system-packages 2>/dev/null \
        || pip install -e "$SCRIPT_DIR"
    echo "  Installed (editable): recbar, recbar-ctl, recbar-test"
else
    echo "  Installing..."
    pip install "$SCRIPT_DIR" --break-system-packages 2>/dev/null \
        || pip install "$SCRIPT_DIR"
    echo "  Installed: recbar, recbar-ctl, recbar-test"
fi

# Default config (only if not exists)
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    cp "$SCRIPT_DIR/config.example.json" "$CONFIG_DIR/config.json"
    echo "  Created config: $CONFIG_DIR/config.json"
    echo "  Edit it to add your scenes and auto-scene rules."
else
    echo "  Config exists: $CONFIG_DIR/config.json (not overwritten)"
fi

echo ""
echo "  Quick start:"
echo "    recbar                     Launch the bar"
echo "    recbar-ctl rec             Toggle recording"
echo "    recbar-ctl chapter 'Intro' Add chapter mark"
echo "    recbar --version           Version info"
echo ""
echo "  Mobile remote: http://YOUR_IP:5555 (auto-starts with bar)"
echo ""
