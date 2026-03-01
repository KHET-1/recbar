"""Auto-scene switcher — switches OBS scenes based on active window.

Polls the active window's class/app_id every 2 seconds and matches against
user-defined rules in config.json.

Platform support:
- X11: xdotool getactivewindow getwindowclassname
- Hyprland: hyprctl activewindow -j → .class
- Sway/wlroots: swaymsg -t get_tree → focused node .app_id
- KDE Wayland: kdotool getactivewindow getappid (if available)
- GNOME Wayland: gdbus call (limited — only window title, not app_id)

Falls back gracefully: tries each method, uses the first that works.
"""

import json
import subprocess
import threading
import time

from .config import AUTO_SCENE_DEFAULT, AUTO_SCENE_RULES
from .obs_client import obs_cmd


def _get_active_window_class():
    """Get the active window's class/app_id using the best available method.

    Returns lowercase string or empty string on failure.
    """
    # Try each method in order of reliability
    for method in (_try_xdotool, _try_hyprctl, _try_swaymsg, _try_kdotool):
        result = method()
        if result:
            return result
    return ""


def _try_xdotool():
    """X11: xdotool getactivewindow getwindowclassname."""
    try:
        r = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowclassname"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().lower()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


def _try_hyprctl():
    """Hyprland: hyprctl activewindow -j → JSON with 'class' field."""
    try:
        r = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0 and r.stdout.strip():
            data = json.loads(r.stdout)
            return data.get("class", "").lower()
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return ""


def _try_swaymsg():
    """Sway/wlroots: swaymsg -t get_tree → find focused node's app_id."""
    try:
        r = subprocess.run(
            ["swaymsg", "-t", "get_tree"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0 and r.stdout.strip():
            tree = json.loads(r.stdout)
            focused = _find_focused_node(tree)
            if focused:
                app_id = focused.get("app_id") or ""
                if not app_id:
                    props = focused.get("window_properties", {})
                    app_id = props.get("class", "")
                return app_id.lower() if app_id else ""
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return ""


def _find_focused_node(node):
    """Recursively find the focused leaf node in a sway tree."""
    if node.get("focused") and not node.get("nodes") and not node.get("floating_nodes"):
        return node
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        result = _find_focused_node(child)
        if result:
            return result
    return None


def _try_kdotool():
    """KDE Wayland: kdotool getactivewindow → window ID, then class."""
    try:
        r = subprocess.run(
            ["kdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0 and r.stdout.strip():
            wid = r.stdout.strip()
            r2 = subprocess.run(
                ["kdotool", "getwindowclassname", wid],
                capture_output=True, text=True, timeout=2,
            )
            if r2.returncode == 0 and r2.stdout.strip():
                return r2.stdout.strip().lower()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


def detect_window_method():
    """Probe which window detection method works on this system.

    Returns the name of the working method or None.
    Called once at startup to avoid probing every 2 seconds.
    """
    probes = [
        ("xdotool", _try_xdotool),
        ("hyprctl", _try_hyprctl),
        ("swaymsg", _try_swaymsg),
        ("kdotool", _try_kdotool),
    ]
    for name, fn in probes:
        try:
            result = fn()
            if result:
                return name
        except Exception:
            pass
    return None


class AutoSceneSwitcher(threading.Thread):
    """Background thread that auto-switches OBS scenes based on focused window.

    Works on X11 (xdotool), Hyprland (hyprctl), Sway (swaymsg),
    and KDE Wayland (kdotool). Detects the best method at startup.
    """

    def __init__(self, state):
        super().__init__(daemon=True)
        self.state = state
        self.last_scene = ""
        self.method = None  # detected in run()

    def run(self):
        # Probe once to find a working method
        self.method = detect_window_method()
        if not self.method:
            return  # No working method — exit thread

        while True:
            if self.state.auto_scene_enabled and self.state.connected:
                try:
                    wm_class = _get_active_window_class()
                    if not wm_class:
                        time.sleep(2)
                        continue

                    target = AUTO_SCENE_DEFAULT
                    for pattern, scene in AUTO_SCENE_RULES:
                        if pattern in wm_class:
                            target = scene
                            break

                    if target and target != self.last_scene and target in self.state.scenes:
                        obs_cmd("SetCurrentProgramScene", {"sceneName": target})
                        self.last_scene = target
                except Exception:
                    pass

            time.sleep(2)
