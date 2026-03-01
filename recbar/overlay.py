"""Reaction overlay and checklist panel.

Fullscreen transparent window that displays:
- Floating emoji reactions that rise and fade
- Persistent checklist panel for visual test suites

Uses X11 XShape extension for true click-through at the window server level.
"""

import math
import time
import random

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QPainter, QColor, QBrush

# Late-import font detection to avoid circular imports
_mono_font = None
_emoji_font = None


def _get_fonts():
    global _mono_font, _emoji_font
    if _mono_font is None:
        from .platform import get_font_family
        _mono_font, _emoji_font = get_font_family()
    return _mono_font, _emoji_font


class FloatingReaction:
    """A single emoji reaction that floats upward and fades."""

    def __init__(self, emoji, x, screen_height):
        self.emoji = emoji
        self.x = x
        self.start_y = float(screen_height - 50)
        self.y = self.start_y
        self.opacity = 1.0
        self.scale = 1.0
        self.born = time.time()
        self.lifetime = 3.0
        self.size = 48
        self.drift = (hash(emoji + str(time.time())) % 80) - 40

    def update(self, dt):
        age = time.time() - self.born
        p = age / self.lifetime
        self.y = self.start_y - self.start_y * p * 0.8
        self.x += self.drift * dt * 0.3
        self.opacity = max(0, 1.0 - (p - 0.7) / 0.3) if p > 0.7 else min(1.0, p / 0.05)
        self.scale = (0.3 + p / 0.1 * 0.9 if p < 0.1
                      else 1.2 * (1.0 - (p - 0.85) / 0.15) if p > 0.85 else 1.2)
        return age < self.lifetime


class ChecklistItem:
    """A single item in the overlay checklist panel."""

    def __init__(self, text, status="pending"):
        self.text = text
        self.status = status  # pending | running | pass | fail
        self.born = time.time()
        self.opacity = 0.0

    def update(self):
        self.opacity = min(1.0, (time.time() - self.born) / 0.2)


class ReactionOverlay(QWidget):
    """Fullscreen transparent overlay for reactions and checklists.

    Uses X11 XShape extension to make the window truly click-through
    at the X server level (not just Qt's WA_TransparentForMouseEvents).
    """

    def __init__(self):
        super().__init__()
        self.reactions = []
        self.checklist = []
        self.checklist_title = ""
        self.last_frame = time.time()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(0, 0, screen.width(), screen.height())
        self.screen_h = screen.height()
        self.screen_w = screen.width()

        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self.animate)
        self.anim_timer.start(33)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self._x11_passthrough)

    def _x11_passthrough(self):
        """Set empty X11 input shape so clicks pass through to windows below.

        On Wayland, this is skipped — Qt's WA_TransparentForMouseEvents
        handles it (less reliable but functional).
        """
        from .platform import IS_X11
        if not IS_X11:
            return  # Wayland: rely on Qt-level passthrough (set in __init__)

        try:
            import ctypes
            import ctypes.util

            wid = int(self.winId())
            xlib = ctypes.cdll.LoadLibrary(ctypes.util.find_library('X11'))
            xext = ctypes.cdll.LoadLibrary(ctypes.util.find_library('Xext'))
            d = xlib.XOpenDisplay(None)
            if not d:
                return
            # ShapeInput = 2, ShapeSet = 0 — set input region to empty (0 rectangles)
            xext.XShapeCombineRectangles(
                d, ctypes.c_ulong(wid), ctypes.c_int(2),
                ctypes.c_int(0), ctypes.c_int(0),
                None, ctypes.c_int(0), ctypes.c_int(0), ctypes.c_int(0)
            )
            xlib.XFlush(d)
            xlib.XCloseDisplay(d)
        except Exception:
            pass  # Missing Xext — fall back to Qt-level passthrough

    # ── Reaction API ───────────────────────────────────────

    def spawn(self, emoji):
        x = random.randint(int(self.screen_w * 0.15), int(self.screen_w * 0.85))
        self.reactions.append(FloatingReaction(emoji, x, self.screen_h))

    # ── Checklist API ──────────────────────────────────────

    def checklist_start(self, title):
        self.checklist = []
        self.checklist_title = title

    def checklist_add(self, text):
        self.checklist.append(ChecklistItem(text))

    def checklist_run(self, i):
        if 0 <= i < len(self.checklist):
            self.checklist[i].status = "running"
            self.checklist[i].born = time.time()

    def checklist_pass(self, i):
        if 0 <= i < len(self.checklist):
            self.checklist[i].status = "pass"

    def checklist_fail(self, i):
        if 0 <= i < len(self.checklist):
            self.checklist[i].status = "fail"

    def checklist_clear(self):
        self.checklist = []
        self.checklist_title = ""

    # ── Animation & Paint ──────────────────────────────────

    def animate(self):
        now = time.time()
        dt = now - self.last_frame
        self.last_frame = now
        self.reactions = [r for r in self.reactions if r.update(dt)]
        for item in self.checklist:
            item.update()
        if self.reactions or self.checklist:
            self.update()

    def paintEvent(self, event):
        if not self.reactions and not self.checklist:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # ── Checklist panel ────────────────────────────────
        if self.checklist:
            lh, pw = 32, 420
            ph = (len(self.checklist) + 1) * lh + 24
            px = self.screen_w - pw - 30
            py = int(self.screen_h * 0.15)

            # Background
            p.save()
            p.setOpacity(0.85)
            p.setBrush(QBrush(QColor("#0a0a1a")))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(px, py, pw, ph, 12, 12)
            p.restore()

            # Border
            p.save()
            p.setOpacity(0.6)
            p.setPen(QColor("#2196F3"))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(px, py, pw, ph, 12, 12)
            p.restore()

            # Title
            p.save()
            p.setOpacity(0.95)
            mono, _ = _get_fonts()
            p.setFont(QFont(mono, 13, QFont.Weight.Bold))
            p.setPen(QColor("#ffffff"))
            p.drawText(px + 16, py + lh, self.checklist_title)
            p.restore()

            # Items
            STATUS_STYLE = {
                "pending": ("\u25CB", QColor("#666677")),
                "pass":    ("\u2713", QColor("#4CAF50")),
                "fail":    ("\u2717", QColor("#f44336")),
            }
            for i, item in enumerate(self.checklist):
                y = py + (i + 2) * lh
                p.save()
                p.setOpacity(item.opacity)
                mono, _ = _get_fonts()
                p.setFont(QFont(mono, 11))
                if item.status == "running":
                    pulse = 0.6 + 0.4 * math.sin(time.time() * 4)
                    ic, c = "\u25B6", QColor(255, 235, 59, int(255 * pulse))
                else:
                    ic, c = STATUS_STYLE.get(item.status, ("\u25CB", QColor("#666677")))
                p.setPen(c)
                p.drawText(px + 16, y, f"{ic}  {item.text}")
                p.restore()

        # ── Floating reactions ─────────────────────────────
        for r in self.reactions:
            if r.opacity <= 0:
                continue
            p.save()
            p.setOpacity(r.opacity)
            _, emoji = _get_fonts()
            p.setFont(QFont(emoji, max(8, int(r.size * r.scale))))
            p.drawText(int(r.x), int(r.y), r.emoji)
            p.restore()

        p.end()
