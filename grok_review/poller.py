"""OBS status poller — polls recording/scene/mic state on a persistent connection.

Maintains a long-lived WebSocket connection to OBS, polling every 500ms.
Updates the shared OBSState object and emits Qt signals for UI refresh.
Also monitors disk space every ~5 seconds.
"""

import json
import shutil
import threading
import time

try:
    import websocket
except ImportError:
    websocket = None

from .config import OBS_URL, MIC_NAME, RECORDING_PATH


class OBSPoller(threading.Thread):
    """Background thread that polls OBS for recording/scene/mic status."""

    def __init__(self, state, signal, chapters):
        super().__init__(daemon=True)
        self.state = state
        self.signal = signal
        self.chapters = chapters
        self.running = True
        self._poll_count = 0

    def _send(self, ws, req_type, req_id, data=None):
        """Send an OBS request and wait for the matching response."""
        msg = {"op": 6, "d": {"requestType": req_type, "requestId": req_id}}
        if data:
            msg["d"]["requestData"] = data
        ws.send(json.dumps(msg))

        # Drain until we get op:7 (RequestResponse)
        resp = json.loads(ws.recv())
        while resp.get("op") != 7:
            resp = json.loads(ws.recv())
        return resp.get("d", {}).get("responseData", {})

    def run(self):
        if websocket is None:
            return

        while self.running:
            try:
                ws = websocket.create_connection(OBS_URL, timeout=3)
                json.loads(ws.recv())  # Hello
                ws.send(json.dumps({"op": 1, "d": {"rpcVersion": 1}}))
                ws.recv()  # Identified
                self.state.connected = True
                prev_rec = self.state.recording

                while self.running:
                    # Recording status
                    data = self._send(ws, "GetRecordStatus", "rs")
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
                            import sys
                            print(f"  Chapters saved: {path}", file=sys.stderr)
                        self.state.rec_start_time = 0.0
                    prev_rec = self.state.recording

                    # Current scene
                    data = self._send(ws, "GetCurrentProgramScene", "gs")
                    self.state.scene = data.get("sceneName", "?")

                    # Scene list
                    data = self._send(ws, "GetSceneList", "sl")
                    self.state.scenes = [s["sceneName"] for s in data.get("scenes", [])]

                    # Mic mute state
                    try:
                        data = self._send(ws, "GetInputMute", "mic", {"inputName": MIC_NAME})
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
                    time.sleep(0.5)

            except Exception:
                self.state.connected = False
                self.state.recording = False
                self.signal.updated.emit()
                time.sleep(2)
