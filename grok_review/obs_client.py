"""OBS WebSocket client — command helper.

Provides obs_cmd() for fire-and-forget OBS commands.
Each call opens a short-lived websocket connection.

Future: replace with a persistent shared connection pool.
"""

import json
import threading

try:
    import websocket
except ImportError:
    websocket = None

from .config import OBS_URL


def obs_cmd(req_type, data=None):
    """Send a single OBS WebSocket command in a background thread.

    Opens a new connection, authenticates, sends the command, and closes.
    Failures are silently ignored (OBS may be disconnected).
    """
    if websocket is None:
        return

    def _do():
        try:
            ws = websocket.create_connection(OBS_URL, timeout=3)
            json.loads(ws.recv())  # Hello
            ws.send(json.dumps({"op": 1, "d": {"rpcVersion": 1}}))
            ws.recv()  # Identified
            msg = {"op": 6, "d": {"requestType": req_type, "requestId": "cmd"}}
            if data:
                msg["d"]["requestData"] = data
            ws.send(json.dumps(msg))
            ws.recv()
            ws.close()
        except Exception:
            pass

    threading.Thread(target=_do, daemon=True).start()
