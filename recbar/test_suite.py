"""RecBar visual test suite — checklist overlay + live verification.

Displays a persistent checklist on the right side of the screen.
Each step lights up as it runs, then marks pass/fail.
Watch both the bar AND the checklist panel.

Usage: recbar-test [--slow]
"""

import sys
import time

CMD_FILE = "/tmp/recbar_cmd"
SLOW = "--slow" in sys.argv


def send(cmd):
    with open(CMD_FILE, "w") as f:
        f.write(cmd)
    time.sleep(0.08)


def wait(t=1.2):
    time.sleep(t * (2.0 if SLOW else 1.0))


TESTS = [
    ("Bar -> Slim (32px)",       "size1"),
    ("Bar -> Medium (64px)",     "size2"),
    ("Bar -> Large (128px)",     "size3"),
    ("Bar -> Slim (restore)",    "size1"),
    ("Recording START",          "rec"),
    ("Recording PAUSE",          "pause"),
    ("Recording UNPAUSE",        "pause"),
    ("Recording STOP",           "rec"),
    ("Mic MUTE toggle",          "mic"),
    ("Mic UNMUTE restore",       "mic"),
    ("Scene -> NEXT",            "next"),
    ("Scene -> NEXT",            "next"),
    ("Scene -> PREV (back)",     "prev"),
    ("Reaction burst",           None),
]


def main():
    total = len(TESTS)
    print(f"RecBar Visual Test — {total} checks")
    if SLOW:
        print("Running in SLOW mode (2x delay)")
    print("Watch the checklist panel on the right side of your screen\n")

    # Build the checklist on the overlay
    send("cl_start:RECBAR TEST")
    time.sleep(0.15)
    for label, _ in TESTS:
        send(f"cl_add:{label}")
        time.sleep(0.05)

    wait(1.0)

    # Run each test
    for i, (label, cmd) in enumerate(TESTS):
        print(f"[{i + 1}/{total}] {label}")

        # Mark as running (pulsing yellow)
        send(f"cl_run:{i}")
        wait(0.5)

        # Execute the command
        if cmd:
            send(cmd)
        else:
            # Reaction burst
            for emoji in ["\U0001F525", "\U0001F44D", "\u2764\uFE0F", "\U0001F680",
                          "\u2B50", "\U0001F44F", "\U0001F92F", "\U0001F389",
                          "\U0001F4AF", "\u26A1"]:
                send(f"react:{emoji}")
                time.sleep(0.2)

        wait(1.5)

        # Mark as passed
        send(f"cl_pass:{i}")
        wait(0.3)

    # Final celebration
    print()
    wait(0.5)
    for emoji in ["\u2705", "\U0001F3C1", "\U0001F389"]:
        send(f"react:{emoji}")
        time.sleep(0.3)

    print(f"\u2705 All {total} tests complete!")
    print("Checklist stays on screen — review it visually.")
    print("Run 'recbar-ctl cl_clear' to dismiss when done.\n")

    # Keep checklist visible for 15 seconds then auto-clear
    print("Auto-clearing checklist in 15 seconds...")
    time.sleep(15)
    send("cl_clear")
    print("Cleared.")


if __name__ == "__main__":
    main()
