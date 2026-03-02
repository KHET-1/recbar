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

# Install .desktop file (app launcher + autostart option)
DESKTOP_SRC="$SCRIPT_DIR/recbar.desktop"
if [ -f "$DESKTOP_SRC" ]; then
    APPS_DIR="$HOME/.local/share/applications"
    mkdir -p "$APPS_DIR"
    cp "$DESKTOP_SRC" "$APPS_DIR/recbar.desktop"
    echo "  Desktop entry: $APPS_DIR/recbar.desktop"

    if [[ "$*" == *"--autostart"* ]]; then
        AUTOSTART_DIR="$HOME/.config/autostart"
        mkdir -p "$AUTOSTART_DIR"
        cp "$DESKTOP_SRC" "$AUTOSTART_DIR/recbar.desktop"
        echo "  Autostart: $AUTOSTART_DIR/recbar.desktop"
    else
        echo "  Tip: ./install.sh --autostart to launch RecBar on login"
    fi
fi

# Install systemd user service (optional)
SERVICE_SRC="$SCRIPT_DIR/recbar.service"
if [ -f "$SERVICE_SRC" ] && [[ "$*" == *"--systemd"* ]]; then
    SYSTEMD_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SYSTEMD_DIR"
    cp "$SERVICE_SRC" "$SYSTEMD_DIR/recbar.service"
    systemctl --user daemon-reload
    systemctl --user enable recbar.service
    echo "  Systemd:   $SYSTEMD_DIR/recbar.service (enabled)"
    echo "  Start:     systemctl --user start recbar"
fi

echo ""
echo "  Quick start:"
echo "    recbar                     Launch the bar"
echo "    recbar-ctl rec             Toggle recording"
echo "    recbar-ctl chapter 'Intro' Add chapter mark"
echo "    recbar --version           Version info"
echo ""
echo "  Mobile remote: http://YOUR_IP:7777 (auto-starts with bar)"
echo ""
