"""Chapter mark manager — timestamps during recording, exported to markdown.

Usage via CLI: recbar-ctl chapter "Introduction"
Creates markdown file on recording stop: chapters_2026-02-28_14-30-00.md
"""

import os
import time

from .config import RECORDING_PATH


class ChapterManager:
    """Manages chapter marks during OBS recording sessions.

    Chapters are timestamped relative to recording start.
    On recording stop, exports all chapters to a markdown file.
    """

    def __init__(self):
        self.chapters = []
        self.rec_start = 0.0

    def on_rec_start(self):
        """Called when recording starts — resets chapter list."""
        self.rec_start = time.time()
        self.chapters = []

    def add(self, title):
        """Add a chapter mark at the current recording offset.

        Returns offset in seconds, or None if not recording.
        """
        if self.rec_start <= 0:
            return None
        offset = time.time() - self.rec_start
        self.chapters.append((offset, title))
        return offset

    def on_rec_stop(self):
        """Called when recording stops — exports chapters to markdown.

        Returns the file path written, or None if no chapters.
        """
        if not self.chapters:
            self.rec_start = 0.0
            return None

        os.makedirs(RECORDING_PATH, exist_ok=True)
        fname = os.path.join(
            RECORDING_PATH,
            f"chapters_{time.strftime('%Y-%m-%d_%H-%M-%S')}.md"
        )

        with open(fname, 'w') as f:
            f.write("# Recording Chapters\n\n")
            for offset, title in self.chapters:
                h = int(offset // 3600)
                m = int(offset % 3600 // 60)
                s = int(offset % 60)
                f.write(f"- `{h:02d}:{m:02d}:{s:02d}` \u2014 {title}\n")

        self.rec_start = 0.0
        return fname

    def format_chapters(self):
        """Return list of formatted chapter strings for API/display."""
        lines = []
        for offset, title in self.chapters:
            h = int(offset // 3600)
            m = int(offset % 3600 // 60)
            s = int(offset % 60)
            lines.append(f"{h:02d}:{m:02d}:{s:02d} - {title}")
        return lines
