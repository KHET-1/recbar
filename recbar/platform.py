"""Platform detection — X11 vs Wayland, font availability.

Provides session type detection and font fallback chain so the rest of
the codebase can adapt without scattered platform checks.
"""

import os
import shutil


def detect_session_type():
    """Detect whether we're running on X11 or Wayland.

    Returns 'x11', 'wayland', or 'unknown'.
    """
    # XDG_SESSION_TYPE is the standard
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session in ("x11", "wayland"):
        return session

    # Fallback: WAYLAND_DISPLAY is set on Wayland
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"

    # Fallback: DISPLAY is set on X11
    if os.environ.get("DISPLAY"):
        return "x11"

    return "unknown"


def has_xdotool():
    """Check if xdotool is available (X11-only tool)."""
    return shutil.which("xdotool") is not None


def get_font_family():
    """Return the best available monospace font.

    Tries JetBrains Mono first, then common fallbacks.
    Returns tuple of (primary, emoji) font family names.
    """
    try:
        from PyQt6.QtGui import QFontDatabase
        available = QFontDatabase.families()
        available_lower = [f.lower() for f in available]
    except Exception:
        return "monospace", "monospace"

    # Monospace preference order
    mono_candidates = [
        "JetBrains Mono",
        "Fira Code",
        "Source Code Pro",
        "DejaVu Sans Mono",
        "Liberation Mono",
        "Noto Sans Mono",
        "Monospace",
    ]
    mono = "monospace"
    for font in mono_candidates:
        if font.lower() in available_lower:
            mono = font
            break

    # Emoji font
    emoji_candidates = [
        "Noto Color Emoji",
        "Twemoji",
        "Segoe UI Emoji",
        "Apple Color Emoji",
    ]
    emoji = mono  # fallback to mono if no emoji font
    for font in emoji_candidates:
        if font.lower() in available_lower:
            emoji = font
            break

    return mono, emoji


# Module-level constants (computed once on import)
SESSION_TYPE = detect_session_type()
IS_X11 = SESSION_TYPE == "x11"
IS_WAYLAND = SESSION_TYPE == "wayland"
HAS_XDOTOOL = has_xdotool()
