"""Shared OBS state object and Qt signal bridge.

OBSState is a plain mutable container shared by all threads.
SignalBridge provides thread-safe Qt signal emission for UI updates.
"""

from collections import deque

from PyQt6.QtCore import QObject, pyqtSignal


class OBSState:
    """Mutable state container shared across all threads.

    Thread safety: individual field writes are atomic in CPython (GIL).
    No complex multi-field transactions are needed.
    """

    def __init__(self):
        self.connected = False
        self.recording = False
        self.paused = False
        self.rec_time = "00:00:00"
        self.scene = "?"
        self.scenes = []
        self.mic_active = False
        self.mic_level = 0.0
        self.mic_history = deque(maxlen=200)
        self.disk_free_gb = -1.0
        self.target_duration = 0
        self.rec_start_time = 0.0
        self.auto_scene_enabled = False


class SignalBridge(QObject):
    """Thread-safe Qt signal for triggering UI repaints from background threads."""
    updated = pyqtSignal()
