"""Unix domain socket IPC — reliable, ordered, zero message loss.

Replaces the file-based /tmp/recbar_cmd hack. Uses SOCK_DGRAM (datagram)
so each command is an atomic message — no framing needed, no partial reads.

Server (bar): binds to /tmp/recbar.sock, non-blocking recv in animation loop.
Client (ctl/web): sendto /tmp/recbar.sock, fire-and-forget.
"""

import os
import socket

SOCK_PATH = "/tmp/recbar.sock"

# Legacy file path — checked as fallback for old obs-bar-ctl users
LEGACY_CMD_FILE = "/tmp/obs_bar_cmd"


class IPCServer:
    """Non-blocking Unix datagram socket server for receiving commands."""

    def __init__(self, path=SOCK_PATH):
        self.path = path
        self.sock = None

    def start(self):
        """Bind the socket. Removes stale socket file if present."""
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass

        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(self.path)
        self.sock.setblocking(False)
        # Allow other users to send commands
        os.chmod(self.path, 0o666)

    def recv(self):
        """Non-blocking receive. Returns command string or None."""
        if self.sock is None:
            return None
        try:
            data = self.sock.recv(4096)
            return data.decode().strip()
        except BlockingIOError:
            return None
        except Exception:
            return None

    def recv_all(self):
        """Drain all pending commands. Returns list of command strings."""
        commands = []
        while True:
            cmd = self.recv()
            if cmd is None:
                break
            commands.append(cmd)
        return commands

    def stop(self):
        """Close socket and remove socket file."""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass


def send_command(cmd, path=SOCK_PATH):
    """Send a command to a running RecBar instance. Fire-and-forget.

    Returns True if sent, False if RecBar isn't running.
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.sendto(cmd.encode(), path)
        return True
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        return False
    finally:
        sock.close()


def check_legacy_cmd_file():
    """Check the legacy file-based command pipe. Returns command or None."""
    try:
        with open(LEGACY_CMD_FILE, "r") as f:
            cmd = f.read().strip()
        if cmd:
            open(LEGACY_CMD_FILE, "w").close()
            return cmd
    except FileNotFoundError:
        pass
    return None
