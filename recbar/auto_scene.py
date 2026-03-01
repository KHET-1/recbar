"""Auto-scene switcher — switches OBS scenes based on active window class.

Uses xdotool to poll the active window's WM_CLASS every 2 seconds.
Matches against user-defined rules in config.json.

Platform: xdotool is X11-only. On Wayland, auto-scene is disabled with a
warning at startup. Future: hyprctl/swaymsg support.
"""

import subprocess
import time
import threading

from .config import AUTO_SCENE_RULES, AUTO_SCENE_DEFAULT
from .obs_client import obs_cmd
from .platform import IS_WAYLAND, HAS_XDOTOOL


class AutoSceneSwitcher(threading.Thread):
    """Background thread that auto-switches OBS scenes based on focused window."""

    def __init__(self, state):
        super().__init__(daemon=True)
        self.state = state
        self.last_scene = ""
        self.available = HAS_XDOTOOL and not IS_WAYLAND

    def run(self):
        if not self.available:
            return  # Exit thread immediately on Wayland or missing xdotool

        while True:
            if self.state.auto_scene_enabled and self.state.connected:
                try:
                    r = subprocess.run(
                        ['xdotool', 'getactivewindow', 'getwindowclassname'],
                        capture_output=True, text=True, timeout=2
                    )
                    wm_class = r.stdout.strip().lower()

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
