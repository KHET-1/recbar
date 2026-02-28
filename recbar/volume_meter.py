"""Real-time mic volume meter via OBS InputVolumeMeters events.

Subscribes to OBS WebSocket event stream (eventSubscriptions: 1 << 16)
and updates OBSState.mic_level + mic_history with actual peak values.
"""

import json
import threading
import time

try:
    import websocket
except ImportError:
    websocket = None

from .config import OBS_URL, MIC_NAME


class VolumeMeter(threading.Thread):
    """Background thread that reads real-time mic levels from OBS.

    Uses a dedicated WebSocket connection subscribed only to
    InputVolumeMeters events (high-frequency, ~50ms intervals).
    """

    def __init__(self, state):
        super().__init__(daemon=True)
        self.state = state
        self.running = True

    def run(self):
        if websocket is None:
            return

        while self.running:
            try:
                ws = websocket.create_connection(OBS_URL, timeout=5)
                json.loads(ws.recv())  # Hello

                # Subscribe to InputVolumeMeters only (1 << 16 = 65536)
                ws.send(json.dumps({
                    "op": 1,
                    "d": {"rpcVersion": 1, "eventSubscriptions": 65536}
                }))
                ws.recv()  # Identified

                while self.running:
                    msg = json.loads(ws.recv())
                    if msg.get("op") != 5:  # Only care about Event messages
                        continue

                    d = msg.get("d", {})
                    if d.get("eventType") != "InputVolumeMeters":
                        continue

                    for inp in d.get("eventData", {}).get("inputs", []):
                        if inp.get("inputName") != MIC_NAME:
                            continue
                        levels = inp.get("inputLevelsMul", [[0, 0, 0]])
                        if levels and levels[0]:
                            # [magnitude, peak, inputPeak] — use peak
                            peak = levels[0][1] if len(levels[0]) > 1 else levels[0][0]
                            self.state.mic_level = max(0.0, min(1.0, float(peak)))
                            self.state.mic_history.append(self.state.mic_level)

            except Exception:
                self.state.mic_level = 0.0
                time.sleep(2)
