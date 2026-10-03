"""Shared widgets. Colors always come from the active theme."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Callable

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QFileInfo,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFileIconProvider,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import icons, theme
from ..signals import bus

PAGE_MARGIN = 28
MAX_CONTENT_WIDTH = 1280


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def set_role(widget: QWidget, role: str | None) -> QWidget:
    widget.setProperty("role", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    return widget


def label(text: str = "", role: str | None = None, wrap: bool = False, align: Qt.AlignmentFlag | None = None) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    if align is not None:
        lbl.setAlignment(align)
    return lbl


def button(
    text: str = "",
    kind: str | None = None,
    icon: str | None = None,
    tooltip: str = "",
    on_click: Callable | None = None,
) -> QPushButton:
    btn = QPushButton(text)
    if kind:
        btn.setProperty("kind", kind)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    if tooltip:
        btn.setToolTip(tooltip)
    if on_click:
        btn.clicked.connect(lambda *_: on_click())
    if icon:
        IconBinding.attach(
            btn, icon, "text_on" if kind == "primary" else ("danger" if kind == "danger" else "text_dim")
        )
    return btn


def divider() -> QFrame:
    line = QFrame()
    line.setProperty("divider", True)
    return line


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def hbox(*items, spacing: int = 8, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for item in items:
        if item is None:
            lay.addStretch(1)
        elif isinstance(item, QLayout):
            lay.addLayout(item)
        else:
            lay.addWidget(item)
    return lay


def vbox(*items, spacing: int = 8, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for item in items:
        if item is None:
            lay.addStretch(1)
        elif isinstance(item, QLayout):
            lay.addLayout(item)
        else:
            lay.addWidget(item)
    return lay


def tone_color(tone: str) -> str:
    t = theme.current()
    return {
        "accent": t.accent,
        "text": t.text,
        "text_dim": t.text_dim,
        "text_muted": t.text_muted,
        "text_on": t.on_accent,
        "danger": t.danger,
        "warning": t.warning,
        "gold": t.gold,
        "success": t.success,
        "accent_text": t.accent_text,
    }.get(tone, tone)


class IconBinding:
    """Keeps a button's or label's icon tinted for the current theme."""

    @staticmethod
    def attach(
        widget: QWidget,
        name: str,
        tone: str = "text_dim",
        size: int = 16,
        checked_tone: str | None = None,
        filled: bool = False,
    ) -> None:
        def apply():
            if isinstance(widget, QLabel):
                widget.setPixmap(icons.pixmap(name, tone_color(tone), size, filled))
            else:
                widget.setIcon(
                    icons.icon(name, tone_color(tone), size, tone_color(checked_tone) if checked_tone else None)
                )
                widget.setIconSize(QSize(size, size))

        apply()
        widget._icon_apply = apply  # keep the closure alive with the widget
        bus.theme_changed.connect(apply)
        widget.destroyed.connect(lambda *_: _safe_disconnect(apply))


def _safe_disconnect(slot) -> None:
    try:
        bus.theme_changed.disconnect(slot)
    except (RuntimeError, TypeError):
        pass


def icon_label(name: str, tone: str = "text_dim", size: int = 16, filled: bool = False) -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    IconBinding.attach(lbl, name, tone, size, filled=filled)
    return lbl


# ---------------------------------------------------------------------------
# Layout containers
# ---------------------------------------------------------------------------


class Card(QFrame):
    """Rounded surface with an optional header (title, caption and actions)."""

    def __init__(self, title: str = "", caption: str = "", parent=None, padding: int = 18, spacing: int = 12):
        super().__init__(parent)
        self.setProperty("card", True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(spacing)
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(6)
        self.title_label: QLabel | None = None
        self.caption_label: QLabel | None = None
        if title:
            self.title_label = label(title, "heading")
            head = QVBoxLayout()
            head.setSpacing(2)
            head.addWidget(self.title_label)
            if caption:
                self.caption_label = label(caption, "caption", wrap=True)
                head.addWidget(self.caption_label)
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addLayout(head, 1)
            row.addLayout(self.header_actions)
            self.body.addLayout(row)

    def set_caption(self, text: str) -> None:
        if self.caption_label is not None:
            self.caption_label.setText(text)


class Page(QScrollArea):
    """Scrollable page with consistent margins and a centered max width."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer = QWidget()
        outer.setObjectName("scrollContent")
        outer_lay = QHBoxLayout(outer)
        outer_lay.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN - 4, PAGE_MARGIN, PAGE_MARGIN)
        self.content = QWidget()
        self.content.setMaximumWidth(MAX_CONTENT_WIDTH)
        self.layout_ = QVBoxLayout(self.content)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(18)
        outer_lay.addWidget(self.content)
        self.setWidget(outer)

    def add(self, item, stretch: int = 0) -> None:
        if isinstance(item, QLayout):
            self.layout_.addLayout(item, stretch)
        else:
            self.layout_.addWidget(item, stretch)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 4)
        lay.setSpacing(10)
        left = QVBoxLayout()
        left.setSpacing(2)
        self.title = label(title, "title")
        left.addWidget(self.title)
        self.subtitle = label(subtitle, "subtitle")
        self.subtitle.setVisible(bool(subtitle))
        left.addWidget(self.subtitle)
        lay.addLayout(left, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        lay.addLayout(self.actions)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))


# ---------------------------------------------------------------------------
# Data display
# ---------------------------------------------------------------------------


class StatTile(QFrame):
    """Compact KPI: caption with icon, large value and a secondary line."""

    def __init__(self, caption: str, icon: str, tone: str = "accent", parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(icon_label(icon, tone, 14))
        self.caption = label(caption, "caption")
        top.addWidget(self.caption, 1)
        lay.addLayout(top)
        self.value = label("–", "value")
        lay.addWidget(self.value)
        self.sub = label("", "caption")
        lay.addWidget(self.sub)

    def set(self, value: str, sub: str = "", sub_role: str = "caption", tooltip: str = "") -> None:
        self.value.setText(value)
        self.sub.setText(sub)
        if self.sub.property("role") != sub_role:
            set_role(self.sub, sub_role)
        self.setToolTip(tooltip)


@lru_cache(maxsize=256)
def _file_icon(path: str, size: int) -> QPixmap:
    try:
        ic = QFileIconProvider().icon(QFileInfo(path))
        return ic.pixmap(size, size) if not ic.isNull() else QPixmap()
    except Exception:
        return QPixmap()


class AppAvatar(QWidget):
    """The app's own icon when available, otherwise a colored monogram."""

    def __init__(self, name: str, icon_path: str | None = None, size: int = 28, parent=None):
        super().__init__(parent)
        self._name = name or "?"
        self._size = size
        self._pixmap = _file_icon(icon_path, size) if icon_path else QPixmap()
        self.setFixedSize(size, size)

    def set_app(self, name: str, icon_path: str | None) -> None:
        self._name = name or "?"
        self._pixmap = _file_icon(icon_path, self._size) if icon_path else QPixmap()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._pixmap.isNull():
            p.drawPixmap(self.rect(), self._pixmap)
            return
        digest = int(hashlib.md5(self._name.lower().encode()).hexdigest()[:6], 16)
        dark = theme.current().dark
        bg = QColor.fromHsl(digest % 360, 110 if dark else 150, 70 if dark else 215)
        fg = QColor.fromHsl(digest % 360, 160, 205 if dark else 70)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        radius = self._size * 0.28
        p.drawRoundedRect(QRectF(0, 0, self._size, self._size), radius, radius)
        font = QFont(self.font())
        font.setPixelSize(int(self._size * 0.46))
        font.setBold(True)
        p.setFont(font)
        p.setPen(fg)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._name.strip()[:1].upper())


class UsageBar(QWidget):
    """Thin horizontal meter with an optional limit marker."""

    def __init__(self, fraction: float = 0.0, tone: str = "accent", marker: float | None = None, parent=None):
        super().__init__(parent)
        self._fraction = fraction
        self._tone = tone
        self._marker = marker
        self.setFixedHeight(6)
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, fraction: float, tone: str | None = None, marker: float | None = None) -> None:
        self._fraction = fraction
        self._tone = tone or self._tone
        self._marker = marker
        self.update()

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        h = self.height()
        p.setBrush(QColor(t.track))
        p.drawRoundedRect(QRectF(0, 0, self.width(), h), h / 2, h / 2)
        frac = max(0.0, min(1.0, self._fraction))
        if frac > 0:
            p.setBrush(QColor(tone_color(self._tone)))
            p.drawRoundedRect(QRectF(0, 0, max(h, self.width() * frac), h), h / 2, h / 2)
        if self._marker is not None and 0 < self._marker < 1:
            x = self.width() * self._marker
            p.setPen(QPen(QColor(t.text_dim), 2))
            p.drawLine(int(x), 0, int(x), h)


class AppRow(QFrame):
    """Clickable list row: avatar, name, meter and value."""

    clicked = Signal(int)
    context_requested = Signal(int, QPoint)

    def __init__(
        self,
        app: dict,
        value: str,
        fraction: float,
        sub: str = "",
        tone: str = "accent",
        extra: str = "",
        marker: float | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.app_id = app["app_id"]
        self.setProperty("row", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"{app.get('name', '')}, {value}")
        self.setToolTip(f"{app.get('name', '')}: {value}" + (f" ({sub})" if sub else ""))
        self.setMinimumHeight(48)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 12, 6)
        lay.setSpacing(12)
        lay.addWidget(AppAvatar(app.get("name", ""), app.get("icon_path"), 28))

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(0)
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name = label(app.get("name", ""))
        name.setStyleSheet("font-weight: 600;")
        name_row.addWidget(name)
        if app.get("is_favorite"):
            name_row.addWidget(icon_label("star", "gold", 12, filled=True))
        name_row.addStretch(1)
        text.addLayout(name_row)
        if sub:
            text.addWidget(label(sub, "caption"))
        holder = QWidget()
        holder.setLayout(text)
        holder.setMinimumWidth(120)
        holder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(holder, 3)

        self.bar = UsageBar(fraction, tone, marker)
        lay.addWidget(self.bar, 2)

        val = label(
            value,
            "danger" if tone == "danger" else None,
            align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        if tone != "danger":
            val.setStyleSheet("font-weight: 600;")
        val.setMinimumWidth(70)
        lay.addWidget(val)
        if extra:
            ex = label(extra, "caption", align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            ex.setMinimumWidth(38)
            lay.addWidget(ex)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.app_id)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit(self.app_id)
            return
        if event.key() == Qt.Key.Key_Menu:
            self.context_requested.emit(self.app_id, self.mapToGlobal(self.rect().center()))
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        self.context_requested.emit(self.app_id, event.globalPos())

    def focusInEvent(self, event):
        self.setStyleSheet(f"QFrame[row='true'] {{ background: {theme.current().hover}; }}")
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.setStyleSheet("")
        super().focusOutEvent(event)


class EmptyState(QWidget):
    def __init__(
        self, icon: str, title: str, message: str = "", action: str = "", on_action: Callable | None = None, parent=None
    ):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 28, 16, 28)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic = icon_label(icon, "text_muted", 28)
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(4)
        lay.addWidget(label(title, "heading", align=Qt.AlignmentFlag.AlignCenter))
        if message:
            msg = label(message, "dim", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
            msg.setMaximumWidth(420)
            lay.addWidget(msg, 0, Qt.AlignmentFlag.AlignHCenter)
        if action and on_action:
            lay.addSpacing(6)
            lay.addWidget(button(action, on_click=on_action), 0, Qt.AlignmentFlag.AlignHCenter)


class SegmentedControl(QFrame):
    changed = Signal(int)

    def __init__(self, options: list[str], current: int = 0, parent=None):
        super().__init__(parent)
        self.setProperty("segmented", True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, text in enumerate(options):
            b = QPushButton(text)
            b.setProperty("segment", True)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            self._group.addButton(b, i)
            lay.addWidget(b)
        self._group.button(current).setChecked(True)
        self._group.idClicked.connect(self.changed.emit)

    def current(self) -> int:
        return self._group.checkedId()

    def set_current(self, index: int) -> None:
        btn = self._group.button(index)
        if btn:
            btn.setChecked(True)


class Toggle(QAbstractButton):
    """Animated on/off switch."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._knob = 1.0 if checked else 0.0
        super().setChecked(checked)
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return QSize(40, 22)

    def set_silently(self, checked: bool) -> None:
        self.blockSignals(True)
        self.setChecked(checked)
        self.blockSignals(False)
        self._knob = 1.0 if checked else 0.0
        self.update()

    def _get_knob(self) -> float:
        return self._knob

    def _set_knob(self, value: float) -> None:
        self._knob = value
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._knob)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, 38, 20)
        off, on = QColor(t.border_strong), QColor(t.accent)
        track = QColor(
            int(off.red() + (on.red() - off.red()) * self._knob),
            int(off.green() + (on.green() - off.green()) * self._knob),
            int(off.blue() + (on.blue() - off.blue()) * self._knob),
        )
        if not self.isEnabled():
            track.setAlphaF(0.4)
        p.setPen(QPen(QColor(t.accent), 2) if self.hasFocus() else Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, 10, 10)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.on_accent if self._knob > 0.5 else "#ffffff"))
        x = 4 + self._knob * 18
        p.drawEllipse(QRectF(x, 4, 14, 14))


class SettingRow(QWidget):
    """Title and description on the left, a control on the right."""

    def __init__(self, title: str, description: str = "", control: QWidget | None = None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.setSpacing(16)
        text = QVBoxLayout()
        text.setSpacing(2)
        t = label(title)
        t.setStyleSheet("font-weight: 600;")
        text.addWidget(t)
        if description:
            text.addWidget(label(description, "caption", wrap=True))
        lay.addLayout(text, 1)
        if control is not None:
            lay.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
            if isinstance(control, QAbstractButton):
                control.setAccessibleName(title)


class Toast(QFrame):
    """Transient message at the bottom of the window, with an optional action."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(10)
        self._icon = QLabel()
        self._icon.setFixedSize(16, 16)
        lay.addWidget(self._icon)
        self._text = QLabel()
        lay.addWidget(self._text, 1)
        self._action = button("", kind="link")
        self._action.hide()
        lay.addWidget(self._action)
        self._callback: Callable | None = None
        self._action.clicked.connect(self._run_action)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(160)
        self._fade.finished.connect(self._hide_if_faded)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self.hide()

    def show_message(
        self, text: str, tone: str = "success", action: str = "", callback: Callable | None = None, msec: int = 3200
    ) -> None:
        name = {"success": "circle-check", "danger": "triangle-alert", "warning": "triangle-alert", "info": "info"}.get(
            tone, "info"
        )
        self._icon.setPixmap(icons.pixmap(name, tone_color("accent" if tone == "success" else tone), 16))
        self._text.setText(text)
        self._callback = callback
        self._action.setText(action)
        self._action.setVisible(bool(action and callback))
        self.adjustSize()
        self.reposition()
        self.raise_()
        self.show()
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity() if self.isVisible() else 0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start(msec + (2500 if action else 0))

    def reposition(self) -> None:
        parent = self.parentWidget()
        if not parent:
            return
        self.setMaximumWidth(min(560, parent.width() - 40))
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        self.move(max(20, x), parent.height() - self.height() - 24)

    def dismiss(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _hide_if_faded(self) -> None:
        if self._effect.opacity() < 0.05:
            self.hide()

    def _run_action(self) -> None:
        callback, self._callback = self._callback, None
        self.dismiss()
        if callback:
            callback()


class Badge(QLabel):
    """Small counter pill used on navigation items."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navBadge")
        self.setFixedHeight(18)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()

    def set_count(self, n: int) -> None:
        self.setText(str(n) if n < 100 else "99+")
        self.setVisible(n > 0)
