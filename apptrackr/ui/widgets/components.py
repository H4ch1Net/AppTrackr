"""Reusable neon-themed widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property, Signal
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QPen, QFont, QPixmap
from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QGraphicsDropShadowEffect,
    QSizePolicy, QPushButton, QFileIconProvider,
)
from PySide6.QtCore import QFileInfo

from .. import theme


class NeonCard(QFrame):
    """A glassy card with optional glow border."""

    def __init__(self, parent=None, glow_color: str = None, title: str = ""):
        super().__init__(parent)
        if glow_color is None:
            glow_color = theme.get_accent()
        self.setObjectName("neonCard")
        self._glow_color = glow_color
        self.setStyleSheet(f"""
            QFrame#neonCard {{
                background-color: {theme.BG_CARD};
                border: 1px solid {theme.BORDER};
                border-radius: 12px;
            }}
            QFrame#neonCard:hover {{
                border-color: {glow_color};
            }}
        """)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(14)
        
        # Let cards expand/shrink naturally with the parent layout.
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        if title:
            lbl = QLabel(title)
            lbl.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {theme.TEXT_DIM}; background: transparent;")
            lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self._layout.addWidget(lbl)

        # Subtle glow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(glow_color))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)

    def content_layout(self) -> QVBoxLayout:
        return self._layout


class StatValue(QWidget):
    """A large stat display: value + label underneath."""

    def __init__(self, value: str = "0", label: str = "", accent: str = None, parent=None):
        super().__init__(parent)
        if accent is None:
            accent = theme.get_accent()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._value_label = QLabel(value)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_label.setStyleSheet(
            f"font-size: 28px; font-weight: 700; color: {accent}; background: transparent;"
        )
        layout.addWidget(self._value_label)

        self._desc_label = QLabel(label)
        self._desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._desc_label.setStyleSheet(
            f"font-size: 11px; color: {theme.TEXT_DIM}; background: transparent;"
        )
        layout.addWidget(self._desc_label)

    def set_value(self, v: str) -> None:
        self._value_label.setText(v)


class AppRow(QFrame):
    """A row showing an app's name + usage bar."""

    clicked = Signal(int)

    def __init__(self, app_id: int, name: str, value_ms: int, max_ms: int,
                 is_favorite: bool = False, icon_path: str | None = None, parent=None):
        super().__init__(parent)
        self._app_id = app_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(56)
        self.setStyleSheet(f"""
            QFrame {{
                background: {theme.BG_CARD};
                border-radius: 8px;
            }}
            QFrame:hover {{
                background: {theme.BG_HOVER};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Favorite star
        fav = QLabel("\u2605" if is_favorite else "\u2606")
        fav.setStyleSheet(f"color: {theme.YELLOW if is_favorite else theme.TEXT_MUTED}; font-size: 16px; background: transparent;")
        fav.setFixedWidth(20)
        layout.addWidget(fav)

        # App icon thumbnail (best-effort)
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(20, 20)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent;")
        icon = self._load_app_icon(icon_path)
        if not icon.isNull():
            icon_lbl.setPixmap(icon)
        layout.addWidget(icon_lbl)

        # App name
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"font-weight: 600; color: {theme.TEXT}; background: transparent;")
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        name_lbl.setMinimumWidth(0)
        layout.addWidget(name_lbl, stretch=2)

        # Usage bar
        bar_container = QWidget()
        bar_container.setStyleSheet("background: transparent;")
        bar_layout = QHBoxLayout(bar_container)
        bar_layout.setContentsMargins(0, 0, 0, 0)

        bar_bg = QFrame()
        bar_bg.setFixedHeight(8)
        bar_bg.setStyleSheet(f"background: {theme.BG_INPUT}; border-radius: 4px;")
        bar_bg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        pct = min(value_ms / max(max_ms, 1), 1.0)
        bar_fill = QFrame(bar_bg)
        bar_fill.setFixedHeight(8)
        bar_fill.setMinimumWidth(max(int(pct * 300), 2))
        bar_fill.setMaximumWidth(int(pct * 300))
        bar_fill.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {theme.get_accent()}, stop:1 {theme.PURPLE});"
            f"border-radius: 4px;"
        )

        bar_layout.addWidget(bar_bg)
        layout.addWidget(bar_container, stretch=1)

        # Time label
        time_lbl = QLabel(theme.format_ms(value_ms))
        time_lbl.setStyleSheet(f"color: {theme.get_accent()}; font-weight: 600; background: transparent;")
        time_lbl.setFixedWidth(84)
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(time_lbl)

    def mousePressEvent(self, event):
        self.clicked.emit(self._app_id)
        super().mousePressEvent(event)

    @staticmethod
    def _load_app_icon(icon_path: str | None) -> QPixmap:
        if not icon_path:
            return QPixmap()
        try:
            provider = QFileIconProvider()
            icon = provider.icon(QFileInfo(icon_path))
            if icon.isNull():
                return QPixmap()
            return icon.pixmap(20, 20)
        except Exception:
            return QPixmap()


class SidebarButton(QPushButton):
    """Navigation sidebar button with icon + text."""

    def __init__(self, icon_char: str, text: str, parent=None):
        super().__init__(parent)
        self.setText(f" {icon_char}  {text}")
        self.setFixedHeight(44)
        self.setCheckable(True)
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {theme.TEXT_DIM};
                border: none;
                border-radius: 8px;
                text-align: left;
                padding: 0 16px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {theme.BG_HOVER};
                color: {theme.TEXT};
            }}
            QPushButton:checked {{
                background: {theme.BG_CARD};
                color: {theme.get_accent()};
                border-left: 3px solid {theme.get_accent()};
            }}
        """)


class GradientBar(QWidget):
    """Horizontal gradient bar for charts."""

    def __init__(self, value: float = 0.0, max_val: float = 1.0,
                 color_start: str = None, color_end: str = theme.PURPLE,
                 parent=None):
        super().__init__(parent)
        if color_start is None:
            color_start = theme.get_accent()
        self._value = value
        self._max_val = max_val
        self._c1 = QColor(color_start)
        self._c2 = QColor(color_end)
        self.setFixedHeight(12)
        self.setMinimumWidth(40)

    def set_value(self, v: float, max_v: float | None = None):
        self._value = v
        if max_v is not None:
            self._max_val = max_v
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        # Background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.BG_INPUT))
        p.drawRoundedRect(0, 0, w, h, h // 2, h // 2)

        # Fill
        pct = min(self._value / max(self._max_val, 1), 1.0)
        fill_w = max(int(pct * w), 0)
        if fill_w > 0:
            grad = QLinearGradient(0, 0, fill_w, 0)
            grad.setColorAt(0, self._c1)
            grad.setColorAt(1, self._c2)
            p.setBrush(grad)
            p.drawRoundedRect(0, 0, fill_w, h, h // 2, h // 2)
        p.end()
