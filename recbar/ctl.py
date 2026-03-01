"""RecBar CLI control — send commands to a running RecBar instance.

Uses Unix domain socket (primary) with file fallback (legacy).

Usage:
    recbar-ctl size1|size2|size3          Resize bar
    recbar-ctl rec                        Toggle recording
    recbar-ctl pause                      Toggle pause
    recbar-ctl mic                        Toggle mic mute
    recbar-ctl next|prev                  Scene switch
    recbar-ctl scene "Scene Name"         Switch to named scene
    recbar-ctl react EMOJI                Spawn reaction
    recbar-ctl react fire|heart|100       Named reactions
    recbar-ctl chapter "Title"            Add chapter mark (while recording)
    recbar-ctl target MINUTES             Set recording target duration
    recbar-ctl auto_scene on|off          Toggle auto-scene switching
    recbar-ctl cl_start "Title"           Start checklist panel
    recbar-ctl cl_add "Item text"         Add checklist item
    recbar-ctl cl_run INDEX               Mark item as running
    recbar-ctl cl_pass INDEX              Mark item as passed
    recbar-ctl cl_fail INDEX              Mark item as failed
    recbar-ctl cl_clear                   Dismiss checklist
"""

import socket
import sys

SOCK_PATH = "/tmp/recbar.sock"
LEGACY_CMD_FILE = "/tmp/recbar_cmd"

NAMED_REACTIONS = {
    "fire": "\U0001F525",
    "thumbsup": "\U0001F44D",
    "heart": "\u2764\uFE0F",
    "rocket": "\U0001F680",
    "star": "\u2B50",
    "clap": "\U0001F44F",
    "mind": "\U0001F92F",
    "party": "\U0001F389",
    "100": "\U0001F4AF",
    "bolt": "\u26A1",
}


def _send_unix(cmd):
    """Send via Unix socket. Returns True on success."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.sendto(cmd.encode(), SOCK_PATH)
        return True
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        return False
    finally:
        sock.close()


def _send_file(cmd):
    """Fallback: write to legacy command file."""
    try:
        with open(LEGACY_CMD_FILE, "w") as f:
            f.write(cmd)
        return True
    except OSError:
        return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "react" and len(sys.argv) >= 3:
        emoji = sys.argv[2]
        emoji = NAMED_REACTIONS.get(emoji, emoji)
        cmd = f"react:{emoji}"
    elif cmd == "scene" and len(sys.argv) >= 3:
        cmd = f"scene:{' '.join(sys.argv[2:])}"
    elif cmd == "chapter" and len(sys.argv) >= 3:
        cmd = f"chapter:{' '.join(sys.argv[2:])}"
    elif cmd == "target" and len(sys.argv) >= 3:
        cmd = f"target:{sys.argv[2]}"
    elif cmd == "auto_scene" and len(sys.argv) >= 3:
        cmd = f"auto_scene:{sys.argv[2]}"
    elif cmd in ("cl_start", "cl_add") and len(sys.argv) >= 3:
        cmd = f"{cmd}:{' '.join(sys.argv[2:])}"
    elif cmd in ("cl_run", "cl_pass", "cl_fail") and len(sys.argv) >= 3:
        cmd = f"{cmd}:{sys.argv[2]}"

    # Try Unix socket first, fall back to file
    if not _send_unix(cmd):
        if not _send_file(cmd):
            print("Error: RecBar is not running", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
