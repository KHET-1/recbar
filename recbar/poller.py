"""OBS status poller — polls recording/scene/mic state via shared connection.

Uses the single persistent OBSConnection for all requests.
Polls every 500ms. Also monitors disk space every ~5 seconds.
"""

import shutil
import sys
import threading
import time

from .config import MIC_NAME, RECORDING_PATH


class OBSPoller(threading.Thread):
    """Background thread that polls OBS for recording/scene/mic status."""

    def __init__(self, state, signal, chapters, connection):
        super().__init__(daemon=True)
        self.state = state
        self.signal = signal
        self.chapters = chapters
        self.conn = connection
        self.running = True
        self._poll_count = 0

    def run(self):
        prev_rec = False

        while self.running:
            if not self.conn.connected:
                self.state.connected = False
                self.state.recording = False
                self.signal.updated.emit()
                time.sleep(1)
                continue

            self.state.connected = True

            try:
                # Recording status
                data = self.conn.request("GetRecordStatus")
                self.state.recording = data.get("outputActive", False)
                self.state.paused = data.get("outputPaused", False)
                tc = data.get("outputTimecode", "00:00:00")
                self.state.rec_time = tc.split(".")[0] if "." in tc else tc

                # Detect recording start/stop transitions
                if self.state.recording and not prev_rec:
                    self.state.rec_start_time = time.time()
                    self.chapters.on_rec_start()
                elif not self.state.recording and prev_rec:
                    path = self.chapters.on_rec_stop()
                    if path:
                        print(f"  Chapters saved: {path}", file=sys.stderr)
                    self.state.rec_start_time = 0.0
                prev_rec = self.state.recording

                # Current scene
                data = self.conn.request("GetCurrentProgramScene")
                self.state.scene = data.get("sceneName", "?")

                # Scene list
                data = self.conn.request("GetSceneList")
                self.state.scenes = [s["sceneName"] for s in data.get("scenes", [])]

                # Mic mute state
                try:
                    data = self.conn.request("GetInputMute", {"inputName": MIC_NAME})
                    self.state.mic_active = not data.get("inputMuted", True)
                except Exception:
                    self.state.mic_active = False

                # Disk space (every ~5 seconds)
                self._poll_count += 1
                if self._poll_count % 10 == 0:
                    try:
                        u = shutil.disk_usage(RECORDING_PATH)
                        self.state.disk_free_gb = u.free / (1024**3)
                    except Exception:
                        pass

                self.signal.updated.emit()

            except Exception:
                pass

            time.sleep(0.5)
