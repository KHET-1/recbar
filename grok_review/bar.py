"""IndicatorBar — the main desktop widget.

100% custom-painted PyQt6 widget with proportional zone-based layout.
No QLabels, no QHBoxLayout — everything drawn in paintEvent() for
pixel-perfect control across all three size presets.

Layout zones (proportional, snap on resize):
┌──────────┬──────────┬────────────────┬──────────────┬──────────┬────────┐
│ REC 8%   │ MIC 14%  │ SCENE NAME 28% │ SCENE BTN 25%│ TIME 15% │ CTRL 10%│
└──────────┴──────────┴────────────────┴──────────────┴──────────┴────────┘
"""

import math
import time

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QFont, QPainter, QColor, QLinearGradient, QBrush, QPen

from .config import (
    CFG, SIZE_PRESETS, LAYOUT_ZONES,
    SCENE_COLORS, SCENE_ICONS, DEFAULT_SCENE_COLOR, DEFAULT_SCENE_ICON,
    IDLE_BG, MIC_NAME, DISK_WARN_GB, WEB_PORT,
)
from .state import OBSState, SignalBridge
from .obs_client import obs_cmd
from .overlay import ReactionOverlay
from .poller import OBSPoller
from .volume_meter import VolumeMeter
from .auto_scene import AutoSceneSwitcher
from .chapters import ChapterManager
from .web_remote import MobileServer, get_local_ip

# Command file path (also used by recbar-ctl and web remote)
CMD_FILE = "/tmp/recbar_cmd"

# Legacy command file for backward compat with obs-bar-ctl
LEGACY_CMD_FILE = "/tmp/obs_bar_cmd"


class IndicatorBar(QWidget):
    """Main desktop indicator bar for OBS recording.

    Features:
    - Pulsing REC dot with dark halo and progress ring
    - Real-time mic VU meter with green/yellow/red thresholds
    - Clickable scene buttons with emoji icons
    - Waveform visualization at size3 (128px)
    - Disk space warning
    - Auto-scene indicator
    - Settings (cycle size) and close buttons
    - Keyboard shortcuts (Ctrl+R/P/M/Q, Ctrl+Left/Right)
    - External command ingestion from /tmp/recbar_cmd
    """

    def __init__(self, position="bottom"):
        super().__init__()
        self.position = position
        self.state = OBSState()
        self.chapters = ChapterManager()
        self.pulse_phase = 0.0
        self.current_size = 1
        self.last_frame = time.time()
        self._hint_text = ""
        self._hint_until = 0.0
        self._click_zones = {}
        self._last_rec_state = False  # for flash effect on state transition
        self._flash_until = 0.0

        # Window flags: frameless, always-on-top, tool (no taskbar), X11 bypass
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self.screen_geo = QApplication.primaryScreen().geometry()

        # Reaction overlay (fullscreen, click-through)
        self.reaction_overlay = ReactionOverlay()
        self.reaction_overlay.show()

        self._apply_size(1)

        # Animation timer (30fps)
        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self.animate)
        self.anim_timer.start(33)

        # Signal bridge for thread-safe UI updates
        self.bridge = SignalBridge()
        self.bridge.updated.connect(self.update)

        # Background threads
        self.poller = OBSPoller(self.state, self.bridge, self.chapters)
        self.poller.start()
        self.volume_meter = VolumeMeter(self.state)
        self.volume_meter.start()
        self.auto_switcher = AutoSceneSwitcher(self.state)
        self.auto_switcher.start()
        self.web_server = MobileServer(self.state, self.chapters)
        self.web_server.start()

        ip = get_local_ip()
        print(f"  Remote:    http://{ip}:{WEB_PORT}")

    # ── Layout ─────────────────────────────────────────────

    def _zones(self):
        """Compute pixel rects for each proportional layout zone."""
        w, h = self.width(), self.height()
        zones = {}
        x = 0
        for i, (name, pct) in enumerate(LAYOUT_ZONES):
            zw = (w - x) if i == len(LAYOUT_ZONES) - 1 else int(w * pct)
            zones[name] = QRect(x, 0, zw, h)
            x += zw
        return zones

    def _apply_size(self, k):
        """Resize bar to one of three presets (1=slim, 2=medium, 3=large)."""
        h = SIZE_PRESETS[k][0]
        self.current_size = k
        y = 0 if self.position == "top" else self.screen_geo.height() - h
        self.setGeometry(0, y, self.screen_geo.width(), h)

    def _show_hint(self, text, ms=1500):
        """Show a temporary hint text in the time zone."""
        self._hint_text = text
        self._hint_until = time.time() + ms / 1000.0

    def _switch_scene(self, direction):
        """Switch to next (+1) or previous (-1) scene."""
        sc = self.state.scenes
        if not sc:
            return
        try:
            idx = sc.index(self.state.scene)
        except ValueError:
            idx = 0
        obs_cmd("SetCurrentProgramScene", {"sceneName": sc[(idx + direction) % len(sc)]})

    # ── Mouse Events ───────────────────────────────────────

    def mousePressEvent(self, event):
        pos = event.pos()
        for key, rect in self._click_zones.items():
            if rect.contains(pos):
                if key == "mic":
                    obs_cmd("ToggleInputMute", {"inputName": MIC_NAME})
                    self._show_hint("MIC toggle")
                elif key == "close":
                    self.close()
                elif key == "settings":
                    nxt = (self.current_size % 3) + 1
                    self._apply_size(nxt)
                    self._show_hint(["", "slim", "medium", "LARGE"][nxt])
                elif key.startswith("sbtn:"):
                    scene_name = key[5:]
                    obs_cmd("SetCurrentProgramScene", {"sceneName": scene_name})
                    self._show_hint(f"-> {scene_name}")
                return

    def mouseMoveEvent(self, event):
        for r in self._click_zones.values():
            if r.contains(event.pos()):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                return
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ── Keyboard Events ────────────────────────────────────

    def keyPressEvent(self, event):
        k = event.key()
        m = event.modifiers()
        ctrl = bool(m & Qt.KeyboardModifier.ControlModifier)

        if ctrl and k == Qt.Key.Key_1:
            self._apply_size(1); self._show_hint("slim")
        elif ctrl and k == Qt.Key.Key_2:
            self._apply_size(2); self._show_hint("medium")
        elif ctrl and k == Qt.Key.Key_3:
            self._apply_size(3); self._show_hint("LARGE")
        elif ctrl and k == Qt.Key.Key_R:
            obs_cmd("ToggleRecord"); self._show_hint("REC toggle")
        elif ctrl and k == Qt.Key.Key_P:
            obs_cmd("ToggleRecordPause"); self._show_hint("PAUSE toggle")
        elif ctrl and k == Qt.Key.Key_M:
            obs_cmd("ToggleInputMute", {"inputName": MIC_NAME}); self._show_hint("MIC toggle")
        elif ctrl and k == Qt.Key.Key_Right:
            self._switch_scene(1)
        elif ctrl and k == Qt.Key.Key_Left:
            self._switch_scene(-1)
        elif ctrl and k == Qt.Key.Key_Q:
            self.close()
        else:
            super().keyPressEvent(event)

    # ── External Command Ingestion ─────────────────────────

    def _check_commands(self):
        """Poll the command file for incoming commands from CLI/remote."""
        for cmd_file in (CMD_FILE, LEGACY_CMD_FILE):
            try:
                with open(cmd_file, "r") as f:
                    cmd = f.read().strip()
                if cmd:
                    open(cmd_file, "w").close()
                    self._handle_cmd(cmd)
            except FileNotFoundError:
                pass

    def _handle_cmd(self, cmd):
        """Process a single command string."""
        if cmd.startswith("size"):
            try:
                self._apply_size(int(cmd[4]))
            except (ValueError, KeyError):
                pass
        elif cmd == "rec":
            obs_cmd("ToggleRecord"); self._show_hint("REC toggle")
        elif cmd == "pause":
            obs_cmd("ToggleRecordPause"); self._show_hint("PAUSE toggle")
        elif cmd == "mic":
            obs_cmd("ToggleInputMute", {"inputName": MIC_NAME}); self._show_hint("MIC toggle")
        elif cmd == "next":
            self._switch_scene(1)
        elif cmd == "prev":
            self._switch_scene(-1)
        elif cmd.startswith("react:"):
            self.reaction_overlay.spawn(cmd.split(":", 1)[1])
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
            self.reaction_overlay.checklist_start(cmd.split(":", 1)[1])
        elif cmd.startswith("cl_add:"):
            self.reaction_overlay.checklist_add(cmd.split(":", 1)[1])
        elif cmd.startswith("cl_run:"):
            self.reaction_overlay.checklist_run(int(cmd.split(":", 1)[1]))
        elif cmd.startswith("cl_pass:"):
            self.reaction_overlay.checklist_pass(int(cmd.split(":", 1)[1]))
        elif cmd.startswith("cl_fail:"):
            self.reaction_overlay.checklist_fail(int(cmd.split(":", 1)[1]))
        elif cmd == "cl_clear":
            self.reaction_overlay.checklist_clear()

    # ── Animation ──────────────────────────────────────────

    def animate(self):
        self.pulse_phase += 0.1
        # Detect recording state transitions for flash effect
        if self.state.recording != self._last_rec_state:
            self._flash_until = time.time() + 0.4
            self._last_rec_state = self.state.recording
        self._check_commands()
        self.update()

    # ══════════════════════════════════════════════════════
    # PAINT — all rendering happens here
    # ══════════════════════════════════════════════════════

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        _, fs, _, gw_base = SIZE_PRESETS[self.current_size]
        zones = self._zones()
        self._click_zones.clear()

        font = QFont("JetBrains Mono", fs, QFont.Weight.Bold)
        font.setStyleHint(QFont.StyleHint.Monospace)
        sm = QFont("JetBrains Mono", max(7, fs - 2), QFont.Weight.Bold)
        sm.setStyleHint(QFont.StyleHint.Monospace)

        # ── Background ─────────────────────────────────────
        painter.fillRect(0, 0, w, h, QColor(IDLE_BG))

        if not self.state.connected:
            painter.fillRect(0, 0, w, h, QColor("#0d0d0d"))
        elif self.state.recording:
            p = 0.5 + 0.5 * math.sin(self.pulse_phase)
            if self.state.paused:
                rc = QColor(255, 193, 7, int(120 + 80 * p))
            else:
                rc = QColor(211, 47, 47, int(140 + 100 * p))
            gw = gw_base + 40

            # Left glow
            g = QLinearGradient(0, 0, gw, 0)
            g.setColorAt(0, rc); g.setColorAt(1, QColor(0, 0, 0, 0))
            painter.fillRect(0, 0, gw, h, QBrush(g))

            # Right glow
            g = QLinearGradient(w - gw, 0, w, 0)
            g.setColorAt(0, QColor(0, 0, 0, 0)); g.setColorAt(1, rc)
            painter.fillRect(w - gw, 0, gw, h, QBrush(g))

            # Bottom glow
            sh = max(3, h // 3)
            g = QLinearGradient(0, h - sh, 0, h)
            g.setColorAt(0, QColor(0, 0, 0, 0)); g.setColorAt(1, rc)
            painter.fillRect(0, h - sh, w, sh, QBrush(g))

        # State transition flash (brief white flash when rec starts/stops)
        if time.time() < self._flash_until:
            flash_alpha = int(80 * (self._flash_until - time.time()) / 0.4)
            painter.fillRect(0, 0, w, h, QColor(255, 255, 255, flash_alpha))

        # Top teal accent line
        gd = min(h // 2, 14)
        g = QLinearGradient(0, 0, 0, gd)
        g.setColorAt(0, QColor(0, 188, 212, 35)); g.setColorAt(1, QColor(0, 0, 0, 0))
        painter.fillRect(0, 0, w, gd, QBrush(g))

        # Bottom subtle border
        painter.setPen(QColor(0, 188, 212, 18))
        if self.position == "bottom":
            painter.drawLine(0, 0, w, 0)
        else:
            painter.drawLine(0, h - 1, w, h - 1)

        # ── REC Zone ───────────────────────────────────────
        z = zones["rec"]
        painter.setFont(font)
        if not self.state.connected:
            painter.setPen(QColor("#444455"))
            painter.drawText(z.adjusted(8, 0, 0, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             "OFFLINE")
        elif self.state.recording:
            tx = z.x() + max(20, h // 2 + 8)
            tr = QRect(tx, 0, z.width() - (tx - z.x()), h)
            if self.state.paused:
                painter.setPen(QColor("#FFC107"))
                painter.drawText(tr,
                                 Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                 "PAUSED")
            else:
                painter.setPen(QColor("#ffffff"))
                painter.drawText(tr,
                                 Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                 "REC")
        else:
            painter.setPen(QColor("#555566"))
            painter.drawText(z.adjusted(8, 0, 0, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             "IDLE")

        # ── MIC Zone (clickable) ───────────────────────────
        z = zones["mic"]
        self._click_zones["mic"] = z
        if self.state.mic_active:
            dr = max(3, h // 8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#4CAF50")))
            painter.drawEllipse(z.x() + 6, h // 2 - dr, dr * 2, dr * 2)

            painter.setFont(sm)
            painter.setPen(QColor("#4CAF50"))
            lx = z.x() + 6 + dr * 2 + 4
            painter.drawText(lx, 0, 50, h,
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             "MIC")

            # VU bar with real levels
            bx = lx + int(fs * 3.2)
            bw = max(30, z.right() - bx - 8)
            bh = max(4, h // 5)
            by = (h - bh) // 2

            # Background
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(35, 35, 55)))
            painter.drawRoundedRect(bx, by, bw, bh, 2, 2)

            # Fill with color thresholds
            lv = self.state.mic_level
            fw = int(bw * lv)
            if lv < 0.55:
                vc = QColor("#4CAF50")
            elif lv < 0.80:
                vc = QColor("#FFC107")
            else:
                vc = QColor("#f44336")
            painter.setBrush(QBrush(vc))
            painter.drawRoundedRect(bx, by, fw, bh, 2, 2)

            # Segmentation lines
            painter.setPen(QColor(26, 26, 46, 160))
            segs = max(5, bw // 8)
            for i in range(1, segs):
                sx = bx + i * bw // segs
                if sx < bx + fw:
                    painter.drawLine(sx, by + 1, sx, by + bh - 1)
        else:
            painter.setFont(sm)
            painter.setPen(QColor("#555566"))
            painter.drawText(z.adjusted(6, 0, -4, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             "\U0001F507 OFF")

        # ── Scene Name Zone ────────────────────────────────
        z = zones["scene"]
        painter.setFont(font)
        sc = QColor(SCENE_COLORS.get(self.state.scene, DEFAULT_SCENE_COLOR))
        painter.setPen(sc)
        icon = SCENE_ICONS.get(self.state.scene, DEFAULT_SCENE_ICON)
        painter.drawText(z, Qt.AlignmentFlag.AlignCenter, f"{icon}  {self.state.scene}")

        # Waveform at size3 — mirrored waveform behind scene text
        if self.current_size == 3 and len(self.state.mic_history) > 4:
            pts = list(self.state.mic_history)
            step = max(1, z.width() // len(pts))
            painter.setPen(QPen(QColor(0, 188, 212, 60), 1))
            wave_amp = h * 0.35
            mid = h // 2
            for i in range(1, len(pts)):
                x1 = z.x() + (i - 1) * step
                x2 = z.x() + i * step
                if x2 > z.right():
                    break
                d1 = int(pts[i - 1] * wave_amp)
                d2 = int(pts[i] * wave_amp)
                painter.drawLine(x1, mid - d1, x2, mid - d2)  # top half
                painter.drawLine(x1, mid + d1, x2, mid + d2)  # mirror

        # ── Scene Buttons ──────────────────────────────────
        z = zones["scenes"]
        scenes = self.state.scenes
        if scenes:
            pad = 3
            bh_ = max(16, h - 8)
            by_ = (h - bh_) // 2
            mbw = min(int((z.width() - pad * (len(scenes) + 1)) / max(1, len(scenes))), 72)
            total = len(scenes) * (mbw + pad) - pad
            sx = z.x() + (z.width() - total) // 2

            for i, sn in enumerate(scenes):
                bx_ = sx + i * (mbw + pad)
                br = QRect(bx_, by_, mbw, bh_)
                self._click_zones[f"sbtn:{sn}"] = br
                active = sn == self.state.scene

                scolor = QColor(SCENE_COLORS.get(sn, DEFAULT_SCENE_COLOR))
                painter.setPen(Qt.PenStyle.NoPen)
                if active:
                    scolor.setAlpha(90)
                    painter.setBrush(QBrush(scolor))
                else:
                    painter.setBrush(QBrush(QColor(28, 28, 48, 200)))
                painter.drawRoundedRect(br, 4, 4)

                # Border
                bc = QColor(SCENE_COLORS.get(sn, DEFAULT_SCENE_COLOR))
                bc.setAlpha(140 if active else 40)
                painter.setPen(bc)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(br, 4, 4)

                # Icon
                ef = QFont("Noto Color Emoji", max(8, bh_ // 2 - 2))
                painter.setFont(ef)
                painter.setPen(QColor("#ffffff"))
                painter.drawText(br, Qt.AlignmentFlag.AlignCenter,
                                 SCENE_ICONS.get(sn, DEFAULT_SCENE_ICON))

        # ── Time Zone ──────────────────────────────────────
        z = zones["time"]
        painter.setFont(font)
        if self.state.recording:
            painter.setPen(QColor("#ffffff"))
            painter.drawText(z, Qt.AlignmentFlag.AlignCenter, self.state.rec_time)

        # Hint overlay
        if self._hint_text and time.time() < self._hint_until:
            alpha = min(1.0, (self._hint_until - time.time()) / 0.3)
            painter.setFont(QFont("JetBrains Mono", max(8, fs - 4)))
            painter.setPen(QColor(136, 136, 136, int(255 * alpha)))
            painter.drawText(z.adjusted(0, 0, -8, 0),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             self._hint_text)

        # ── Controls Zone ──────────────────────────────────
        z = zones["ctrl"]
        bw_ = max(22, h)

        # Connection status dot
        cd = max(3, h // 10)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.state.connected:
            painter.setBrush(QBrush(QColor(76, 175, 80, 140)))
        else:
            p_dot = 0.5 + 0.5 * math.sin(self.pulse_phase * 2)
            painter.setBrush(QBrush(QColor(244, 67, 54, int(100 + 100 * p_dot))))
        painter.drawEllipse(z.x() + 3, h // 2 - cd, cd * 2, cd * 2)

        # Disk warning
        if 0 < self.state.disk_free_gb < DISK_WARN_GB:
            painter.setFont(sm)
            painter.setPen(QColor("#f44336"))
            painter.drawText(z.adjusted(4, 0, 0, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             f"\u26A0 {self.state.disk_free_gb:.0f}GB")

        # Auto-scene indicator
        if self.state.auto_scene_enabled:
            painter.setFont(QFont("JetBrains Mono", max(6, fs - 4)))
            painter.setPen(QColor("#4CAF50"))
            painter.drawText(z.adjusted(4, 0, -bw_ * 2 - 10, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                             "AUTO")

        # Settings gear
        gr = QRect(z.right() - bw_ * 2 - 6, 0, bw_, h)
        self._click_zones["settings"] = gr
        painter.setFont(QFont("JetBrains Mono", max(9, fs)))
        painter.setPen(QColor("#556677"))
        painter.drawText(gr, Qt.AlignmentFlag.AlignCenter, "\u2699")

        # Close X
        cr = QRect(z.right() - bw_ - 2, 0, bw_, h)
        self._click_zones["close"] = cr
        painter.setPen(QColor("#556677"))
        painter.drawText(cr, Qt.AlignmentFlag.AlignCenter, "\u2715")

        # ── REC Dot — drawn LAST to pop above everything ──
        rz = zones["rec"]
        if self.state.recording and not self.state.paused:
            p = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(self.pulse_phase * 1.5))
            dr = max(5, h // 5)
            dx = rz.x() + 6 + dr
            dy = h // 2

            painter.setPen(Qt.PenStyle.NoPen)

            # Dark halo for contrast
            painter.setBrush(QBrush(QColor(0, 0, 0, 210)))
            painter.drawEllipse(dx - dr - 4, dy - dr - 4, (dr + 4) * 2, (dr + 4) * 2)

            # Glow rings
            for i in range(3, 0, -1):
                painter.setBrush(QBrush(QColor(255, 30, 30, int(70 * p * i / 3))))
                painter.drawEllipse(dx - dr * i, dy - dr * i, dr * 2 * i, dr * 2 * i)

            # Red core
            painter.setBrush(QBrush(QColor(255, 40, 40, int(220 + 35 * p))))
            painter.drawEllipse(dx - dr, dy - dr, dr * 2, dr * 2)

            # White-hot center pip
            pr_ = max(2, dr // 3)
            painter.setBrush(QBrush(QColor(255, 220, 220, int(200 + 55 * p))))
            painter.drawEllipse(dx - pr_, dy - pr_, pr_ * 2, pr_ * 2)

            # Progress ring (if target duration set)
            if self.state.target_duration > 0 and self.state.rec_start_time > 0:
                elapsed = time.time() - self.state.rec_start_time
                progress = min(1.0, elapsed / (self.state.target_duration * 60))
                ring_r = dr + 6
                span = int(progress * 360 * 16)
                if progress < 0.7:
                    ring_c = QColor("#4CAF50")
                elif progress < 0.9:
                    ring_c = QColor("#FFC107")
                else:
                    ring_c = QColor("#f44336")
                painter.setPen(QPen(ring_c, max(2, h // 16)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawArc(dx - ring_r, dy - ring_r, ring_r * 2, ring_r * 2,
                                90 * 16, -span)

        elif self.state.recording and self.state.paused:
            p = 0.5 + 0.5 * math.sin(self.pulse_phase * 0.8)
            dr = max(5, h // 5)
            dx = rz.x() + 6 + dr
            dy = h // 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0, 0, 0, 200)))
            painter.drawEllipse(dx - dr - 3, dy - dr - 3, (dr + 3) * 2, (dr + 3) * 2)
            painter.setBrush(QBrush(QColor(255, 193, 7, int(180 + 75 * p))))
            painter.drawEllipse(dx - dr, dy - dr, dr * 2, dr * 2)

        painter.end()

    # ── Cleanup ────────────────────────────────────────────

    def closeEvent(self, event):
        self.poller.running = False
        self.volume_meter.running = False
        self.anim_timer.stop()
        self.reaction_overlay.close()
        event.accept()
