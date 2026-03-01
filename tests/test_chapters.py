"""Tests for recbar.chapters — chapter marks and markdown export."""

import os
import tempfile
import time

import pytest


def test_add_chapter_not_recording():
    """Adding a chapter when not recording returns None."""
    from recbar.chapters import ChapterManager
    cm = ChapterManager()
    assert cm.add("Test") is None


def test_add_chapter_during_recording():
    """Adding a chapter during recording returns offset."""
    from recbar.chapters import ChapterManager
    cm = ChapterManager()
    cm.on_rec_start()
    time.sleep(0.05)
    offset = cm.add("Introduction")
    assert offset is not None
    assert offset >= 0.0
    assert len(cm.chapters) == 1
    assert cm.chapters[0][1] == "Introduction"


def test_multiple_chapters():
    """Multiple chapters accumulate correctly."""
    from recbar.chapters import ChapterManager
    cm = ChapterManager()
    cm.on_rec_start()
    cm.add("Chapter 1")
    time.sleep(0.02)
    cm.add("Chapter 2")
    time.sleep(0.02)
    cm.add("Chapter 3")
    assert len(cm.chapters) == 3


def test_format_chapters():
    """format_chapters returns properly formatted strings."""
    from recbar.chapters import ChapterManager
    cm = ChapterManager()
    cm.on_rec_start()
    cm.add("Intro")
    lines = cm.format_chapters()
    assert len(lines) == 1
    assert "Intro" in lines[0]
    assert ":" in lines[0]  # timecode format


def test_on_rec_stop_exports_markdown(tmp_path, monkeypatch):
    """Stopping recording exports chapters to markdown file."""
    import recbar.chapters as ch_mod

    # Temporarily redirect RECORDING_PATH
    monkeypatch.setattr(ch_mod, 'RECORDING_PATH', str(tmp_path))

    cm = ch_mod.ChapterManager()
    cm.on_rec_start()
    cm.add("Segment A")
    cm.add("Segment B")

    result = cm.on_rec_stop()
    assert result is not None
    assert os.path.exists(result)

    with open(result) as f:
        content = f.read()
    assert "Recording Chapters" in content
    assert "Segment A" in content
    assert "Segment B" in content


def test_on_rec_stop_no_chapters():
    """Stopping recording with no chapters returns None."""
    from recbar.chapters import ChapterManager
    cm = ChapterManager()
    cm.on_rec_start()
    assert cm.on_rec_stop() is None


def test_rec_start_resets():
    """Starting a new recording clears previous chapters."""
    from recbar.chapters import ChapterManager
    cm = ChapterManager()
    cm.on_rec_start()
    cm.add("Old Chapter")
    cm.on_rec_start()  # new recording
    assert len(cm.chapters) == 0
