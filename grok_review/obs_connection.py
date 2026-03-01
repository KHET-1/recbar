"""Single persistent OBS WebSocket connection with message routing.

Replaces the previous pattern of 3 separate connections (poller, volume meter,
fire-and-forget commands). One connection handles everything:
- Request/response matching by requestId (for poller queries)
- Event routing via callback (for InputVolumeMeters)
- Fire-and-forget commands (no response wait)

Auto-reconnects on connection loss with exponential backoff.
"""

import json
import threading
import time

try:
    import websocket
except ImportError:
    websocket = None

from .config import OBS_URL


class OBSConnection:
    """Single persistent WebSocket connection to OBS Studio.

    Thread-safe: multiple threads can call request() and send() concurrently.
    The internal reader thread routes responses to waiting callers and
    dispatches events to the registered callback.
    """

    def __init__(self, url=OBS_URL, event_callback=None):
        self.url = url
        self._event_callback = event_callback
        self._ws = None
        self._send_lock = threading.Lock()
        self._pending = {}       # requestId -> threading.Event
        self._results = {}       # requestId -> response data
        self._connected = False
        self._running = True
        self._req_counter = 0
        self._counter_lock = threading.Lock()

    @property
    def connected(self):
        return self._connected

    def start(self):
        """Start the connection manager thread (handles connect + reconnect)."""
        t = threading.Thread(target=self._connection_loop, daemon=True)
        t.start()

    def stop(self):
        """Signal the connection to shut down."""
        self._running = False
        self._connected = False
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass

    def _next_id(self):
        """Generate a unique request ID."""
        with self._counter_lock:
            self._req_counter += 1
            return f"req_{self._req_counter}"

    def _connection_loop(self):
        """Connect, authenticate, read messages. Reconnect on failure."""
        if websocket is None:
            return

        backoff = 1
        while self._running:
            try:
                self._ws = websocket.create_connection(self.url, timeout=5)
                json.loads(self._ws.recv())  # Hello

                # Subscribe to InputVolumeMeters (1 << 16 = 65536)
                self._ws.send(json.dumps({
                    "op": 1,
                    "d": {"rpcVersion": 1, "eventSubscriptions": 65536}
                }))
                json.loads(self._ws.recv())  # Identified

                self._connected = True
                backoff = 1  # Reset backoff on successful connect

                # Read loop — route messages
                while self._running:
                    raw = self._ws.recv()
                    msg = json.loads(raw)
                    op = msg.get("op")

                    if op == 7:  # RequestResponse
                        req_id = msg.get("d", {}).get("requestId")
                        if req_id in self._pending:
                            self._results[req_id] = msg.get("d", {}).get("responseData", {})
                            self._pending[req_id].set()

                    elif op == 5:  # Event
                        if self._event_callback:
                            try:
                                self._event_callback(msg.get("d", {}))
                            except Exception:
                                pass

            except Exception:
                self._connected = False
                # Wake any threads waiting on responses
                for evt in self._pending.values():
                    evt.set()
                self._pending.clear()
                self._results.clear()

                if self._running:
                    time.sleep(min(backoff, 10))
                    backoff = min(backoff * 2, 10)

    def request(self, req_type, data=None, timeout=3):
        """Send a request and wait for the response. Thread-safe.

        Returns response data dict, or empty dict on timeout/error.
        """
        if not self._connected:
            return {}

        req_id = self._next_id()
        event = threading.Event()
        self._pending[req_id] = event

        msg = {"op": 6, "d": {"requestType": req_type, "requestId": req_id}}
        if data:
            msg["d"]["requestData"] = data

        try:
            with self._send_lock:
                self._ws.send(json.dumps(msg))
        except Exception:
            self._pending.pop(req_id, None)
            return {}

        if event.wait(timeout):
            result = self._results.pop(req_id, {})
            self._pending.pop(req_id, None)
            return result
        else:
            self._pending.pop(req_id, None)
            self._results.pop(req_id, None)
            return {}

    def send(self, req_type, data=None):
        """Fire-and-forget command. Thread-safe. No response wait."""
        if not self._connected:
            return

        req_id = self._next_id()
        msg = {"op": 6, "d": {"requestType": req_type, "requestId": req_id}}
        if data:
            msg["d"]["requestData"] = data

        try:
            with self._send_lock:
                self._ws.send(json.dumps(msg))
        except Exception:
            pass
