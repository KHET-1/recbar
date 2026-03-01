"""Tests for command dispatcher module."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class FakeState:
    def __init__(self):
        self.target_duration = 0
        self.auto_scene_enabled = False
        self.recording = True
        self.rec_start_time = 1000000.0


class FakeChapters:
    def __init__(self):
        self.added = []
        self.rec_start_time = 1000000.0

    def add(self, title):
        self.added.append(title)
        return 60.5  # fake offset


class FakeOverlay:
    def __init__(self):
        self.spawned = []
        self.checklist_ops = []

    def spawn(self, emoji):
        self.spawned.append(emoji)

    def checklist_start(self, title):
        self.checklist_ops.append(("start", title))

    def checklist_add(self, text):
        self.checklist_ops.append(("add", text))

    def checklist_run(self, i):
        self.checklist_ops.append(("run", i))

    def checklist_pass(self, i):
        self.checklist_ops.append(("pass", i))

    def checklist_fail(self, i):
        self.checklist_ops.append(("fail", i))

    def checklist_clear(self):
        self.checklist_ops.append(("clear",))


def _make_dispatcher():
    from recbar.commands import CommandDispatcher

    state = FakeState()
    chapters = FakeChapters()
    overlay = FakeOverlay()
    sizes = []
    hints = []
    scenes = []

    d = CommandDispatcher(
        state, chapters, overlay,
        apply_size_fn=lambda s: sizes.append(s),
        show_hint_fn=lambda t, ms=1500: hints.append(t),
        switch_scene_fn=lambda d: scenes.append(d),
    )
    return d, state, chapters, overlay, sizes, hints, scenes


def test_size_command():
    d, _, _, _, sizes, hints, _ = _make_dispatcher()
    d.handle("size2")
    assert sizes == [2]


def test_next_prev():
    d, _, _, _, _, _, scenes = _make_dispatcher()
    d.handle("next")
    d.handle("prev")
    assert scenes == [1, -1]


def test_react():
    d, _, _, overlay, _, _, _ = _make_dispatcher()
    d.handle("react:fire")
    assert overlay.spawned == ["fire"]


def test_chapter():
    d, _, chapters, _, _, hints, _ = _make_dispatcher()
    d.handle("chapter:Intro")
    assert chapters.added == ["Intro"]
    assert any("CH" in h for h in hints)


def test_target():
    d, state, _, _, _, hints, _ = _make_dispatcher()
    d.handle("target:30")
    assert state.target_duration == 30
    assert any("30" in h for h in hints)


def test_auto_scene_on():
    d, state, _, _, _, hints, _ = _make_dispatcher()
    d.handle("auto_scene:on")
    assert state.auto_scene_enabled is True


def test_auto_scene_off():
    d, state, _, _, _, _, _ = _make_dispatcher()
    state.auto_scene_enabled = True
    d.handle("auto_scene:off")
    assert state.auto_scene_enabled is False


def test_checklist_ops():
    d, _, _, overlay, _, _, _ = _make_dispatcher()
    d.handle("cl_start:Test Suite")
    d.handle("cl_add:Step 1")
    d.handle("cl_run:0")
    d.handle("cl_pass:0")
    d.handle("cl_clear")
    assert overlay.checklist_ops == [
        ("start", "Test Suite"),
        ("add", "Step 1"),
        ("run", 0),
        ("pass", 0),
        ("clear",),
    ]


def test_scene_command(monkeypatch):
    """scene: command should call obs_cmd (mocked)."""
    calls = []
    import recbar.commands as cmd_mod
    monkeypatch.setattr(cmd_mod, "obs_cmd", lambda *a, **kw: calls.append(a))
    d, _, _, _, _, _, _ = _make_dispatcher()
    d.handle("scene:Desktop")
    assert calls == [("SetCurrentProgramScene", {"sceneName": "Desktop"})]
