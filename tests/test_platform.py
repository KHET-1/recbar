"""Tests for platform detection module."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from recbar.platform import detect_session_type, has_xdotool


def test_detect_session_type_returns_valid():
    """Session type should be one of the known values."""
    result = detect_session_type()
    assert result in ("x11", "wayland", "unknown")


def test_detect_session_from_env(monkeypatch):
    """XDG_SESSION_TYPE should be respected."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    assert detect_session_type() == "wayland"


def test_detect_x11_from_env(monkeypatch):
    """XDG_SESSION_TYPE=x11 should return x11."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert detect_session_type() == "x11"


def test_detect_wayland_display_fallback(monkeypatch):
    """WAYLAND_DISPLAY should trigger wayland detection."""
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert detect_session_type() == "wayland"


def test_detect_display_fallback(monkeypatch):
    """DISPLAY without WAYLAND_DISPLAY should return x11."""
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    assert detect_session_type() == "x11"


def test_has_xdotool_returns_bool():
    """has_xdotool should return a boolean."""
    assert isinstance(has_xdotool(), bool)
