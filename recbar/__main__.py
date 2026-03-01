"""RecBar entry point — launch the OBS recording indicator bar.

Usage:
    recbar              Launch the bar (bottom, slim)
    recbar --top        Position at top of screen
    recbar --version    Show version
    recbar --help       Show help
"""

import sys
import signal

from . import __version__


def main():
    if "--version" in sys.argv:
        print(f"recbar {__version__}")
        sys.exit(0)

    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        from .config import CONFIG_PATH, print_config_summary
        print_config_summary()
        print()
        sys.exit(0)

    # Import PyQt6 late — fail fast with clear message if missing
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        print("ERROR: PyQt6 is required. Install with: pip install PyQt6")
        sys.exit(1)

    try:
        import websocket  # noqa: F401
    except ImportError:
        print("ERROR: websocket-client is required. Install with: pip install websocket-client")
        sys.exit(1)

    from .config import CFG, CONFIG_PATH as CFG_PATH, print_config_summary
    from .bar import IndicatorBar

    position = CFG["position"]
    if "--top" in sys.argv:
        position = "top"

    # Startup banner
    print()
    print(f"  RecBar v{__version__}")
    print(f"  {'=' * 24}")
    print_config_summary()

    # Launch Qt app
    app = QApplication(sys.argv)

    # Graceful shutdown on SIGTERM/SIGINT
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    bar = IndicatorBar(position)
    bar.show()

    # Platform warnings
    from .platform import IS_WAYLAND, HAS_XDOTOOL
    if IS_WAYLAND:
        print("  Note:      Wayland detected — auto-scene and XShape click-through unavailable")
    elif not HAS_XDOTOOL:
        print("  Note:      xdotool not found — auto-scene switching disabled")

    print()
    print("  Ready. Press Ctrl+Q on bar to quit.")
    print(f"  Config hot-reload: edit {CFG_PATH} and changes apply instantly.")
    print()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
