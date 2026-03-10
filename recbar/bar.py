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

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from .auto_scene import AutoSceneSwitcher
from .chapters import ChapterManager
from .commands import CommandDispatcher
from .config import (
    CONFIG_PATH,
    DEFAULT_SCENE_COLOR,
    DEFAULT_SCENE_ICON,
    DISK_WARN_GB,
    IDLE_BG,
    LAYOUT_ZONES,
    MIC_NAME,
    SCENE_COLORS,
    SCENE_ICONS,
    SIZE_PRESETS,
    reload_config,
)
from .ipc import IPCServer, check_legacy_cmd_file
from .obs_client import obs_cmd, set_connection
from .obs_connection import OBSConnection
from .overlay import ReactionOverlay
from .platform import IS_WAYLAND, get_font_family
from .poller import OBSPoller
from .state import OBSState, SignalBridge
from .volume_meter import VolumeMeter
from .web_remote import MobileServer, get_remote_url


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

        # Font detection (run once, cache results)
        self._mono_font, self._emoji_font = get_font_family()

        # Window flags: frameless, always-on-top, tool (no taskbar)
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        if not IS_WAYLAND:
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self.screen_geo = QApplication.primaryScreen().geometry()

        # Reaction overlay (fullscreen, click-through)
        self.reaction_overlay = ReactionOverlay()
        self.reaction_overlay.show()

        self._apply_size(1)

        # Command dispatcher (handles IPC/keyboard commands)
        self.dispatcher = CommandDispatcher(
            self.state, self.chapters, self.reaction_overlay,
            self._apply_size, self._show_hint, self._switch_scene,
        )

        # Animation timer (30fps)
        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self.animate)
        self.anim_timer.start(33)

        # Signal bridge for thread-safe UI updates
        self.bridge = SignalBridge()
        self.bridge.updated.connect(self.update)

        # Unix socket IPC server
        self.ipc = IPCServer()
        self.ipc.start()

        # Single shared OBS WebSocket connection
        self.volume_meter = VolumeMeter(self.state)
        self.obs_conn = OBSConnection(event_callback=self.volume_meter.on_event)
        self.obs_conn.start()
        set_connection(self.obs_conn)

        # Background threads (poller uses shared connection)
        self.poller = OBSPoller(self.state, self.bridge, self.chapters, self.obs_conn)
        self.poller.start()
        self.auto_switcher = AutoSceneSwitcher(self.state)
        self.auto_switcher.start()
        self.web_server = MobileServer(self.state, self.chapters)
        self.web_server.start()

        remote_url = get_remote_url()
        print(f"  Remote:    {remote_url}")

        # Config hot-reload via QFileSystemWatcher
        from PyQt6.QtCore import QFileSystemWatcher
        self._config_watcher = QFileSystemWatcher()
        if CONFIG_PATH:
            self._config_watcher.addPath(CONFIG_PATH)
            self._config_watcher.fileChanged.connect(self._on_config_changed)

    def _on_config_changed(self, path):
        """Reload config when config.json changes on disk."""
        if reload_config():
            self._show_hint("Config reloaded")
            # Re-add watch (some editors replace file, which removes the watch)
            if path not in self._config_watcher.files():
                self._config_watcher.addPath(path)
        else:
            self._show_hint("Config error")

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

        # Map keyboard shortcuts to command strings
        KEY_MAP = {
            Qt.Key.Key_1: "size1", Qt.Key.Key_2: "size2", Qt.Key.Key_3: "size3",
            Qt.Key.Key_R: "rec", Qt.Key.Key_P: "pause", Qt.Key.Key_M: "mic",
            Qt.Key.Key_Right: "next", Qt.Key.Key_Left: "prev",
        }

        if ctrl and k == Qt.Key.Key_Q:
            self.close()
        elif ctrl and k in KEY_MAP:
            self.dispatcher.handle(KEY_MAP[k])
        else:
            super().keyPressEvent(event)

    # ── External Command Ingestion ─────────────────────────

    def _check_commands(self):
        """Receive commands from Unix socket IPC (+ legacy file fallback)."""
        # Primary: Unix socket (reliable, ordered, no message loss)
        for cmd in self.ipc.recv_all():
            self.dispatcher.handle(cmd)

        # Legacy: file-based fallback for old obs-bar-ctl users
        legacy = check_legacy_cmd_file()
        if legacy:
            self.dispatcher.handle(legacy)

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
    # PAINT — orchestrator calls zone helpers
    # ══════════════════════════════════════════════════════

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        _, fs, _, gw_base = SIZE_PRESETS[self.current_size]
        zones = self._zones()
        self._click_zones.clear()

        font = QFont(self._mono_font, fs, QFont.Weight.Bold)
        font.setStyleHint(QFont.StyleHint.Monospace)
        sm = QFont(self._mono_font, max(7, fs - 2), QFont.Weight.Bold)
        sm.setStyleHint(QFont.StyleHint.Monospace)

        self._draw_background(painter, w, h, gw_base)

        # Clip each zone to prevent cross-zone bleed at large sizes
        for name, draw_fn in [
            ("rec",    lambda p: self._draw_rec_zone(p, zones["rec"], font, h)),
            ("mic",    lambda p: self._draw_mic_zone(p, zones["mic"], sm, fs, h)),
            ("scene",  lambda p: self._draw_scene_name(p, zones["scene"], font, h)),
            ("scenes", lambda p: self._draw_scene_buttons(p, zones["scenes"], h)),
            ("time",   lambda p: self._draw_time_zone(p, zones["time"], font, fs, h)),
            ("ctrl",   lambda p: self._draw_controls(p, zones["ctrl"], sm, fs, h)),
        ]:
            painter.save()
            painter.setClipRect(zones[name])
            draw_fn(painter)
            painter.restore()

        # Rec dot drawn last — clips to widget bounds only (glow intentionally cross-zone)
        painter.save()
        painter.setClipRect(0, 0, w, h)
        self._draw_rec_dot(painter, zones["rec"], h)
        painter.restore()

        painter.end()

    # ── Paint Helpers ──────────────────────────────────────

    def _draw_background(self, p, w, h, gw_base):
        """Background fill, recording glow, flash, teal accent, border."""
        p_obj = p  # avoid shadowing

        p_obj.fillRect(0, 0, w, h, QColor(IDLE_BG))

        if not self.state.connected:
            p_obj.fillRect(0, 0, w, h, QColor("#0d0d0d"))
        elif self.state.recording:
            pulse = 0.5 + 0.5 * math.sin(self.pulse_phase)
            if self.state.paused:
                rc = QColor(255, 193, 7, int(120 + 80 * pulse))
            else:
                rc = QColor(211, 47, 47, int(140 + 100 * pulse))
            gw = gw_base + 40

            g = QLinearGradient(0, 0, gw, 0)
            g.setColorAt(0, rc)
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p_obj.fillRect(0, 0, gw, h, QBrush(g))

            g = QLinearGradient(w - gw, 0, w, 0)
            g.setColorAt(0, QColor(0, 0, 0, 0))
            g.setColorAt(1, rc)
            p_obj.fillRect(w - gw, 0, gw, h, QBrush(g))

            sh = max(3, h // 3)
            g = QLinearGradient(0, h - sh, 0, h)
            g.setColorAt(0, QColor(0, 0, 0, 0))
            g.setColorAt(1, rc)
            p_obj.fillRect(0, h - sh, w, sh, QBrush(g))

        # State transition flash
        if time.time() < self._flash_until:
            flash_alpha = int(80 * (self._flash_until - time.time()) / 0.4)
            p_obj.fillRect(0, 0, w, h, QColor(255, 255, 255, flash_alpha))

        # Top teal accent
        gd = min(h // 2, 14)
        g = QLinearGradient(0, 0, 0, gd)
        g.setColorAt(0, QColor(0, 188, 212, 35))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p_obj.fillRect(0, 0, w, gd, QBrush(g))

        # Bottom subtle border
        p_obj.setPen(QColor(0, 188, 212, 18))
        if self.position == "bottom":
            p_obj.drawLine(0, 0, w, 0)
        else:
            p_obj.drawLine(0, h - 1, w, h - 1)

    def _draw_rec_zone(self, p, z, font, h):
        """REC zone text: OFFLINE / REC / PAUSED / IDLE."""
        p.setFont(font)
        if not self.state.connected:
            p.setPen(QColor("#444455"))
            p.drawText(z.adjusted(8, 0, 0, 0),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       "OFFLINE")
        elif self.state.recording:
            tx = z.x() + max(20, h // 2 + 8)
            tr = QRect(tx, 0, z.width() - (tx - z.x()), h)
            if self.state.paused:
                p.setPen(QColor("#FFC107"))
                p.drawText(tr, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "PAUSED")
            else:
                p.setPen(QColor("#ffffff"))
                p.drawText(tr, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "REC")
        else:
            p.setPen(QColor("#555566"))
            p.drawText(z.adjusted(8, 0, 0, 0),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "IDLE")

    def _draw_mic_zone(self, p, z, sm, fs, h):
        """MIC zone: green dot + VU bar when active, muted icon when off."""
        self._click_zones["mic"] = z
        if not self.state.connected:
            return  # Don't show mic status when OBS isn't connected
        if self.state.mic_active:
            dr = max(3, h // 8)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor("#4CAF50")))
            p.drawEllipse(z.x() + 6, h // 2 - dr, dr * 2, dr * 2)

            p.setFont(sm)
            p.setPen(QColor("#4CAF50"))
            lx = z.x() + 6 + dr * 2 + 4
            align = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            p.drawText(lx, 0, 50, h, align, "MIC")

            # VU bar
            bx = lx + int(fs * 3.2)
            bw = max(30, z.right() - bx - 8)
            bh = max(4, h // 5)
            by = (h - bh) // 2

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(35, 35, 55)))
            p.drawRoundedRect(bx, by, bw, bh, 2, 2)

            lv = self.state.mic_level
            fw = int(bw * lv)
            if lv < 0.55:
                vc = QColor("#4CAF50")
            elif lv < 0.80:
                vc = QColor("#FFC107")
            else:
                vc = QColor("#f44336")
            p.setBrush(QBrush(vc))
            p.drawRoundedRect(bx, by, fw, bh, 2, 2)

            p.setPen(QColor(26, 26, 46, 160))
            segs = max(5, bw // 8)
            for i in range(1, segs):
                sx = bx + i * bw // segs
                if sx < bx + fw:
                    p.drawLine(sx, by + 1, sx, by + bh - 1)
        else:
            p.setFont(sm)
            p.setPen(QColor("#555566"))
            p.drawText(z.adjusted(6, 0, -4, 0),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       "\U0001F507 OFF")

    def _draw_scene_name(self, p, z, font, h):
        """Scene name with icon + waveform at size3."""
        if not self.state.connected:
            p.setFont(font)
            p.setPen(QColor("#444455"))
            p.drawText(z, Qt.AlignmentFlag.AlignCenter, "Waiting for OBS\u2026")
            return

        # Waveform behind text (size3 only)
        if self.current_size == 3 and len(self.state.mic_history) > 4:
            pts = list(self.state.mic_history)
            step = max(1, z.width() // len(pts))
            p.setPen(QPen(QColor(0, 188, 212, 50), 2))
            wave_amp = h * 0.3
            mid = h // 2
            for i in range(1, len(pts)):
                x1 = z.x() + (i - 1) * step
                x2 = z.x() + i * step
                if x2 > z.right():
                    break
                d1 = int(pts[i - 1] * wave_amp)
                d2 = int(pts[i] * wave_amp)
                p.drawLine(x1, mid - d1, x2, mid - d2)
                p.drawLine(x1, mid + d1, x2, mid + d2)

        p.setFont(font)
        sc = QColor(SCENE_COLORS.get(self.state.scene, DEFAULT_SCENE_COLOR))
        p.setPen(sc)
        icon = SCENE_ICONS.get(self.state.scene, DEFAULT_SCENE_ICON)
        p.drawText(z, Qt.AlignmentFlag.AlignCenter, f"{icon}  {self.state.scene}")

    def _draw_scene_buttons(self, p, z, h):
        """Clickable scene buttons with emoji icons."""
        scenes = self.state.scenes
        if not scenes:
            return

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
            p.setPen(Qt.PenStyle.NoPen)
            if active:
                scolor.setAlpha(90)
                p.setBrush(QBrush(scolor))
            else:
                p.setBrush(QBrush(QColor(28, 28, 48, 200)))
            p.drawRoundedRect(br, 4, 4)

            bc = QColor(SCENE_COLORS.get(sn, DEFAULT_SCENE_COLOR))
            bc.setAlpha(140 if active else 40)
            p.setPen(bc)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(br, 4, 4)

            ef = QFont(self._emoji_font, max(8, bh_ // 2 - 2))
            p.setFont(ef)
            p.setPen(QColor("#ffffff"))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter,
                       SCENE_ICONS.get(sn, DEFAULT_SCENE_ICON))

    def _draw_time_zone(self, p, z, font, fs, h):
        """Recording timecode + hint text overlay."""
        p.setFont(font)
        if self.state.recording:
            p.setPen(QColor("#ffffff"))
            p.drawText(z, Qt.AlignmentFlag.AlignCenter, self.state.rec_time)

        if self._hint_text and time.time() < self._hint_until:
            alpha = min(1.0, (self._hint_until - time.time()) / 0.3)
            p.setFont(QFont(self._mono_font, max(8, fs - 4)))
            p.setPen(QColor(136, 136, 136, int(255 * alpha)))
            p.drawText(z.adjusted(0, 0, -8, 0),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       self._hint_text)

    def _draw_controls(self, p, z, sm, fs, h):
        """Controls zone: connection dot, disk warning, auto-scene, gear, close."""
        # Button width scales with height but is capped at 1/4 of zone width
        # so buttons never crowd out the OBS label on any screen size.
        bw_ = min(max(22, h // 2), z.width() // 4)

        # Gear + close take rightmost portion; OBS label gets what remains
        btn_total = bw_ * 2 + 8          # gear + close + gap
        label_right = z.right() - btn_total - 4   # right edge for text content

        # Connection status dot + OBS label
        cd = max(3, h // 10)
        p.setPen(Qt.PenStyle.NoPen)
        if self.state.connected:
            dot_c = QColor(76, 175, 80, 140)
        else:
            p_dot = 0.5 + 0.5 * math.sin(self.pulse_phase * 2)
            dot_c = QColor(100, 100, 120, int(60 + 80 * p_dot))
        p.setBrush(QBrush(dot_c))
        p.drawEllipse(z.x() + 3, h // 2 - cd, cd * 2, cd * 2)

        obs_label_x = z.x() + cd * 2 + 8
        obs_label_w = max(0, label_right - obs_label_x)
        if obs_label_w > 4:
            p.setFont(sm)
            p.setPen(dot_c)
            p.drawText(obs_label_x, 0, obs_label_w, h,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       "OBS")

        # Disk warning — shown below OBS at size3, inline otherwise
        if 0 < self.state.disk_free_gb < DISK_WARN_GB:
            p.setFont(sm)
            p.setPen(QColor("#f44336"))
            if self.current_size == 3:
                p.drawText(z.x() + 4, h // 2, obs_label_w, h // 2,
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           f"\u26A0 {self.state.disk_free_gb:.0f}GB")
            else:
                p.drawText(z.adjusted(4, 0, -btn_total - 4, 0),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           f"\u26A0 {self.state.disk_free_gb:.0f}GB")

        # Auto-scene indicator — right-aligned against button area
        if self.state.auto_scene_enabled:
            p.setFont(QFont(self._mono_font, max(6, fs - 4)))
            p.setPen(QColor("#4CAF50"))
            p.drawText(z.x(), 0, max(0, label_right - z.x() - 4), h,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, "AUTO")

        # Size toggle — overlapping rectangles icon
        gr = QRect(z.right() - btn_total + 2, 0, bw_, h)
        self._click_zones["settings"] = gr
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#556677"), max(1, h // 32)))
        cx, cy = gr.center().x(), gr.center().y()
        u = max(3, h // 8)
        p.drawRect(cx - u, cy - u, u, u)
        p.drawRect(cx - 1, cy - 1, int(u * 1.5), int(u * 1.5))

        # Close X
        cr = QRect(z.right() - bw_ - 2, 0, bw_, h)
        self._click_zones["close"] = cr
        p.setPen(QColor("#556677"))
        p.drawText(cr, Qt.AlignmentFlag.AlignCenter, "\u2715")

    def _draw_rec_dot(self, p, rz, h):
        """REC dot — drawn LAST to pop above everything.

        Active recording: dark halo -> glow rings -> red core -> white pip -> progress ring.
        Paused: dark halo -> amber dot.
        """
        if self.state.recording and not self.state.paused:
            pulse = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(self.pulse_phase * 1.5))
            dr = max(5, h // 5)
            max_glow = h // 2 - 2
            # Clamp dx so glow rings never go negative (size3 issue: dr=25, ring_r up to 62)
            dx = max(rz.x() + max_glow + 1, rz.x() + 6 + dr)
            dy = h // 2

            p.setPen(Qt.PenStyle.NoPen)

            # Dark halo
            p.setBrush(QBrush(QColor(0, 0, 0, 210)))
            p.drawEllipse(dx - dr - 4, dy - dr - 4, (dr + 4) * 2, (dr + 4) * 2)

            # Glow rings — scaled to stay within bar height
            for i in range(3, 0, -1):
                ring_r = dr + int((max_glow - dr) * i / 3)
                p.setBrush(QBrush(QColor(255, 30, 30, int(55 * pulse * i / 3))))
                p.drawEllipse(dx - ring_r, dy - ring_r, ring_r * 2, ring_r * 2)

            # Red core
            p.setBrush(QBrush(QColor(255, 40, 40, int(220 + 35 * pulse))))
            p.drawEllipse(dx - dr, dy - dr, dr * 2, dr * 2)

            # White-hot center pip
            pr_ = max(2, dr // 3)
            p.setBrush(QBrush(QColor(255, 220, 220, int(200 + 55 * pulse))))
            p.drawEllipse(dx - pr_, dy - pr_, pr_ * 2, pr_ * 2)

            # Progress ring
            if self.state.target_duration > 0 and self.state.rec_start_time > 0:
                elapsed = time.time() - self.state.rec_start_time
                progress = min(1.0, elapsed / (self.state.target_duration * 60))
                ring_r = dr + 6
                span = int(progress * 360 * 16)
                ring_c = (QColor("#4CAF50") if progress < 0.7
                          else QColor("#FFC107") if progress < 0.9
                          else QColor("#f44336"))
                p.setPen(QPen(ring_c, max(2, h // 16)))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(dx - ring_r, dy - ring_r, ring_r * 2, ring_r * 2, 90 * 16, -span)

        elif self.state.recording and self.state.paused:
            pulse = 0.5 + 0.5 * math.sin(self.pulse_phase * 0.8)
            dr = max(5, h // 5)
            dx = rz.x() + 6 + dr
            dy = h // 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(0, 0, 0, 200)))
            p.drawEllipse(dx - dr - 3, dy - dr - 3, (dr + 3) * 2, (dr + 3) * 2)
            p.setBrush(QBrush(QColor(255, 193, 7, int(180 + 75 * pulse))))
            p.drawEllipse(dx - dr, dy - dr, dr * 2, dr * 2)

    # ── Cleanup ────────────────────────────────────────────

    def closeEvent(self, event):
        self.poller.running = False
        self.obs_conn.stop()
        self.ipc.stop()
        self.anim_timer.stop()
        self.reaction_overlay.close()
        event.accept()
