"""Tests for auto-scene switcher with multi-compositor support."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from recbar.auto_scene import (
    _find_focused_node,
    _try_hyprctl,
    _try_kdotool,
    _try_swaymsg,
    _try_xdotool,
)


def test_try_xdotool_missing(monkeypatch):
    """xdotool returns empty when not found."""
    monkeypatch.setenv("PATH", "/nonexistent")
    assert _try_xdotool() == ""


def test_try_hyprctl_missing(monkeypatch):
    """hyprctl returns empty when not found."""
    monkeypatch.setenv("PATH", "/nonexistent")
    assert _try_hyprctl() == ""


def test_try_swaymsg_missing(monkeypatch):
    """swaymsg returns empty when not found."""
    monkeypatch.setenv("PATH", "/nonexistent")
    assert _try_swaymsg() == ""


def test_try_kdotool_missing(monkeypatch):
    """kdotool returns empty when not found."""
    monkeypatch.setenv("PATH", "/nonexistent")
    assert _try_kdotool() == ""


def test_find_focused_node_simple():
    """Find focused leaf in a flat sway tree."""
    tree = {
        "focused": False,
        "nodes": [
            {"focused": False, "nodes": [], "floating_nodes": [], "app_id": "firefox"},
            {"focused": True, "nodes": [], "floating_nodes": [], "app_id": "codium"},
        ],
        "floating_nodes": [],
    }
    result = _find_focused_node(tree)
    assert result is not None
    assert result["app_id"] == "codium"


def test_find_focused_node_nested():
    """Find focused leaf in a nested sway tree."""
    tree = {
        "focused": False,
        "nodes": [{
            "focused": False,
            "nodes": [{
                "focused": True,
                "nodes": [],
                "floating_nodes": [],
                "app_id": "terminal",
            }],
            "floating_nodes": [],
        }],
        "floating_nodes": [],
    }
    result = _find_focused_node(tree)
    assert result is not None
    assert result["app_id"] == "terminal"


def test_find_focused_node_none():
    """Return None when no node is focused."""
    tree = {
        "focused": False,
        "nodes": [
            {"focused": False, "nodes": [], "floating_nodes": [], "app_id": "x"},
        ],
        "floating_nodes": [],
    }
    assert _find_focused_node(tree) is None
