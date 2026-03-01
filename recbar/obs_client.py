"""OBS command helper — fire-and-forget via shared connection.

Uses the singleton OBSConnection for all commands instead of
opening a new WebSocket per command.
"""

# The shared connection is set by bar.py at startup
_connection = None


def set_connection(conn):
    """Set the shared OBS connection (called once at startup)."""
    global _connection
    _connection = conn


def obs_cmd(req_type, data=None):
    """Send a fire-and-forget OBS command via the shared connection."""
    if _connection is not None:
        _connection.send(req_type, data)
