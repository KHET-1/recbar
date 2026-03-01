"""Command dispatcher — handles all IPC and keyboard commands.

Extracted from bar.py to reduce its size and isolate command logic.
"""

from .config import MIC_NAME
from .obs_client import obs_cmd


class CommandDispatcher:
    """Processes command strings from IPC, web remote, and keyboard shortcuts."""

    def __init__(self, state, chapters, reaction_overlay, apply_size_fn, show_hint_fn, switch_scene_fn):
        self.state = state
        self.chapters = chapters
        self.overlay = reaction_overlay
        self._apply_size = apply_size_fn
        self._show_hint = show_hint_fn
        self._switch_scene = switch_scene_fn

    def handle(self, cmd):
        """Process a single command string."""
        if cmd.startswith("size"):
            try:
                self._apply_size(int(cmd[4]))
            except (ValueError, KeyError):
                pass
        elif cmd == "rec":
            obs_cmd("ToggleRecord")
            self._show_hint("REC toggle")
        elif cmd == "pause":
            obs_cmd("ToggleRecordPause")
            self._show_hint("PAUSE toggle")
        elif cmd == "mic":
            obs_cmd("ToggleInputMute", {"inputName": MIC_NAME})
            self._show_hint("MIC toggle")
        elif cmd == "next":
            self._switch_scene(1)
        elif cmd == "prev":
            self._switch_scene(-1)
        elif cmd.startswith("react:"):
            self.overlay.spawn(cmd.split(":", 1)[1])
        elif cmd.startswith("scene:"):
            obs_cmd("SetCurrentProgramScene", {"sceneName": cmd.split(":", 1)[1]})
        elif cmd.startswith("chapter:"):
            title = cmd.split(":", 1)[1]
            offset = self.chapters.add(title)
            if offset is not None:
                m, s = int(offset // 60), int(offset % 60)
                self._show_hint(f"CH {m:02d}:{s:02d} {title}")
            else:
                self._show_hint("Not recording")
        elif cmd.startswith("target:"):
            try:
                self.state.target_duration = int(cmd.split(":", 1)[1])
                self._show_hint(f"Target: {self.state.target_duration}min")
            except ValueError:
                pass
        elif cmd.startswith("auto_scene:"):
            val = cmd.split(":", 1)[1].lower()
            self.state.auto_scene_enabled = val in ("on", "1", "true")
            self._show_hint("AutoScene " + ("ON" if self.state.auto_scene_enabled else "OFF"))
        elif cmd.startswith("cl_start:"):
            self.overlay.checklist_start(cmd.split(":", 1)[1])
        elif cmd.startswith("cl_add:"):
            self.overlay.checklist_add(cmd.split(":", 1)[1])
        elif cmd.startswith("cl_run:"):
            self.overlay.checklist_run(int(cmd.split(":", 1)[1]))
        elif cmd.startswith("cl_pass:"):
            self.overlay.checklist_pass(int(cmd.split(":", 1)[1]))
        elif cmd.startswith("cl_fail:"):
            self.overlay.checklist_fail(int(cmd.split(":", 1)[1]))
        elif cmd == "cl_clear":
            self.overlay.checklist_clear()
