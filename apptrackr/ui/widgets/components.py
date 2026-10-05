"""Shared widgets. Colors always come from the active theme."""

from __future__ import annotations

from functools import lru_cache
from typing import Callable

from PySide6.QtCore import (
    Property,
    QEvent,
    QFileInfo,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QBoxLayout,
    QButtonGroup,
    QFileIconProvider,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import fonts, icons, motion, theme
from ..signals import bus
from .rolling import RollingLabel

PAGE_MARGIN = 28
MAX_CONTENT_WIDTH = 1280


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


# Type scale. Roles listed here get their font in code (QSS cannot set letter
# spacing or OpenType features); the stylesheet only colours them.
ROLE_FONTS: dict[str, Callable[[], QFont]] = {
    "title": lambda: fonts.sans(24, 600),
    "subtitle": lambda: fonts.sans(13),
    "heading": lambda: fonts.sans(15, 600),
    "value": lambda: fonts.sans(28, 600, tabular=True),
    "hero": lambda: fonts.sans(44, 600, tabular=True),
    "caption": lambda: fonts.sans(12),
    "eyebrow": lambda: fonts.mono(10, 500, 10),
    "eyebrowAccent": lambda: fonts.mono(10, 500, 10),
    "tick": lambda: fonts.mono(9, 400, 4),
    "pill": lambda: fonts.mono(9, 500, 8),
    "pillAccent": lambda: fonts.mono(9, 500, 8),
    "pillDanger": lambda: fonts.mono(9, 500, 8),
}
UPPERCASE_ROLES = {"eyebrow", "eyebrowAccent", "pill", "pillAccent", "pillDanger"}


def _apply_role_font(widget: QWidget, role: str | None) -> None:
    maker = ROLE_FONTS.get(role or "")
    widget.setFont(maker() if maker else fonts.sans(13))


def set_role(widget: QWidget, role: str | None) -> QWidget:
    widget.setProperty("role", role)
    _apply_role_font(widget, role)
    if isinstance(widget, QLabel) and role in UPPERCASE_ROLES:
        widget.setText(widget.text().upper())
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    return widget


class RoleLabel(QLabel):
    """QLabel that upper-cases its text for engraved-label roles."""

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        super().setText(text.upper() if self.property("role") in UPPERCASE_ROLES else text)


class ElidedLabel(QLabel):
    """Single-line label that elides in the middle to fit (paths); the full text is its tooltip."""

    def __init__(self, text: str = "", role: str | None = None, parent=None):
        super().__init__(parent)
        self._full = ""
        set_role(self, role)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._full = text
        self.setToolTip(text)
        self.updateGeometry()
        self._elide()

    def full_text(self) -> str:
        return self._full

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.fontMetrics().horizontalAdvance(self._full), super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        super().setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, self.width()))


def label(text: str = "", role: str | None = None, wrap: bool = False, align: Qt.AlignmentFlag | None = None) -> QLabel:
    lbl = RoleLabel()
    if role:
        lbl.setProperty("role", role)
        if role in ROLE_FONTS:
            _apply_role_font(lbl, role)
    lbl.setText(text)
    lbl.setWordWrap(wrap)
    if align is not None:
        lbl.setAlignment(align)
    return lbl


def eyebrow(text: str, index: int | None = None, accent: bool = False) -> QLabel:
    """Small engraved section label, optionally numbered ("02  TODAY BY HOUR")."""
    shown = f"{index:02d}   {text}" if index is not None else text
    return label(shown, "eyebrowAccent" if accent else "eyebrow")


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


def count_to(lbl: QLabel, start: float, end: float, formatter: Callable[[float], str]) -> None:
    """Animate a label's number from *start* to *end*."""
    motion.tween(
        lbl,
        float(start),
        float(end),
        motion.SLOWER,
        lambda v: lbl.setText(formatter(v)),
        motion.DECELERATE,
        key="count",
    )


def animate_progress(bar, start: float, end: float) -> None:
    """Ease a QProgressBar between two values."""
    motion.tween(
        bar,
        float(start),
        float(end),
        motion.SLOW,
        lambda v: bar.setValue(int(round(v))),
        motion.EASY_EASE,
        key="progress",
    )


def divider() -> QFrame:
    line = QFrame()
    line.setProperty("divider", True)
    return line


def vdivider() -> QFrame:
    line = QFrame()
    line.setProperty("vdivider", True)
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
        "ink": t.ink,
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
    except (RuntimeError, TypeError, SystemError):
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
    """Panel: hairline-bordered surface with an engraved header (index, title, caption, actions)."""

    def __init__(
        self,
        title: str = "",
        caption: str = "",
        parent=None,
        padding: int = 18,
        spacing: int = 12,
        index: int | None = None,
    ):
        super().__init__(parent)
        self.setProperty("card", True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding - 2, padding, padding)
        self.body.setSpacing(spacing)
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(6)
        self.title_label: QLabel | None = None
        self.caption_label: QLabel | None = None
        self._index = index
        if title:
            self.title_label = eyebrow(title, index)
            head = QVBoxLayout()
            head.setSpacing(3)
            head.addWidget(self.title_label)
            if caption:
                self.caption_label = label(caption, "caption", wrap=True)
                head.addWidget(self.caption_label)
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addLayout(head, 1)
            row.addLayout(self.header_actions)
            self.body.addLayout(row)

    def set_title(self, text: str) -> None:
        if self.title_label is not None:
            self.title_label.setText(f"{self._index:02d}   {text}" if self._index is not None else text)

    def set_caption(self, text: str) -> None:
        if self.caption_label is not None:
            self.caption_label.setText(text)


class _Paper(QWidget):
    """Page canvas: window colour with a faint graph-paper dot grid."""

    STEP = 24

    def paintEvent(self, event):
        t = theme.current()
        p = QPainter(self)
        p.fillRect(event.rect(), QColor(t.window))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.grid))
        r = event.rect()
        step = self.STEP
        x0 = (r.left() // step) * step + step // 2
        y0 = (r.top() // step) * step + step // 2
        for y in range(y0, r.bottom() + step, step):
            for x in range(x0, r.right() + step, step):
                p.drawRect(QRectF(x - 0.75, y - 0.75, 1.5, 1.5))


class Page(QScrollArea):
    """Scrollable page with consistent margins and a centered max width.

    Rows registered with stack_when_narrow() switch to a vertical stack while
    the side-by-side layout would not fit the viewport.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._rows: list[QBoxLayout] = []
        self._compact = False
        self._wide_need = 0
        self._pending = False
        outer = _Paper()
        outer.setObjectName("scrollContent")
        outer.installEventFilter(self)
        outer_lay = QHBoxLayout(outer)
        outer_lay.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN - 2, PAGE_MARGIN, PAGE_MARGIN)
        self.content = QWidget()
        self.content.setMaximumWidth(MAX_CONTENT_WIDTH)
        self.layout_ = QVBoxLayout(self.content)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(16)
        outer_lay.addWidget(self.content)
        self.setWidget(outer)

    def add(self, item, stretch: int = 0) -> None:
        if isinstance(item, QLayout):
            self.layout_.addLayout(item, stretch)
        else:
            self.layout_.addWidget(item, stretch)

    def stack_when_narrow(self, row: QBoxLayout) -> QBoxLayout:
        self._rows.append(row)
        return row

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_compact()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.LayoutRequest and obj is self.widget() and self._rows and not self._pending:
            self._pending = True
            QTimer.singleShot(0, self, self._update_compact)
        return super().eventFilter(obj, event)

    def _update_compact(self) -> None:
        self._pending = False
        if not self._rows:
            return
        available = self.viewport().width()
        if self._compact:
            compact = available < self._wide_need
        else:
            self._wide_need = self.widget().minimumSizeHint().width()
            compact = self._wide_need > available
        if compact != self._compact:
            self._compact = compact
            direction = QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
            for row in self._rows:
                row.setDirection(direction)


class PageHeader(QWidget):
    """Kicker (engraved context line), title, subtitle and right-aligned actions."""

    def __init__(self, title: str, subtitle: str = "", parent=None, kicker: str = ""):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(10)
        left = QVBoxLayout()
        left.setSpacing(4)
        self.kicker = label(kicker, "eyebrowAccent")
        self.kicker.setVisible(bool(kicker))
        left.addWidget(self.kicker)
        self.title = label(title, "title")
        left.addWidget(self.title)
        self.subtitle = label(subtitle, "subtitle")
        self.subtitle.setVisible(bool(subtitle))
        left.addWidget(self.subtitle)
        lay.addLayout(left, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        lay.addLayout(self.actions)
        lay.setAlignment(self.actions, Qt.AlignmentFlag.AlignBottom)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))

    def set_kicker(self, text: str) -> None:
        self.kicker.setText(text)
        self.kicker.setVisible(bool(text))


# ---------------------------------------------------------------------------
# Data display
# ---------------------------------------------------------------------------


class StatTile(QFrame):
    """Readout: engraved caption, large tabular value and a secondary line.

    Framed tiles are panels of their own; unframed ones sit in a MetricGrid.
    """

    def __init__(self, caption: str, icon: str | None = None, tone: str = "accent", parent=None, framed: bool = True):
        super().__init__(parent)
        self.setProperty("card" if framed else "cell", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(6)
        self.caption = eyebrow(caption)
        lay.addWidget(self.caption)
        self.value = RollingLabel("–")
        set_role(self.value, "value")
        lay.addWidget(self.value)
        self.sub = label("", "caption")
        lay.addWidget(self.sub)
        self._number: float | None = None
        self._formatter: Callable[[float], str] | None = None
        self._count_on_show = False

    def set(self, value: str, sub: str = "", sub_role: str = "caption", tooltip: str = "") -> None:
        self.value.setText(value)
        self.sub.setText(sub)
        if self.sub.property("role") != sub_role:
            set_role(self.sub, sub_role)
        self.setToolTip(tooltip)

    def set_number(
        self,
        number: float,
        formatter: Callable[[float], str],
        sub: str = "",
        sub_role: str = "caption",
        tooltip: str = "",
    ) -> None:
        """Show a numeric value. The first value counts up from zero when the tile is first
        shown, large jumps count toward the new value, and small live changes roll."""
        previous, self._number, self._formatter = self._number, number, formatter
        self.set(self.value.text(), sub, sub_role, tooltip)
        current = motion.running(self, "count")
        if current is not None:
            current.setEndValue(float(number))
            return
        if previous is None:
            if self.isVisible():
                self._count(0.0, number)
            else:
                self.value.setText(formatter(number))
                self._count_on_show = True
            return
        if abs(number - previous) > max(abs(previous) * 0.25, 0.5) and self.isVisible():
            self._count(previous, number)
        else:
            self.value.roll_to(formatter(number))

    def reset(self) -> None:
        """Forget the shown number so the next value counts up from zero (e.g. a different item)."""
        self._number = None

    def _count(self, start: float, end: float) -> None:
        motion.tween(self, float(start), float(end), motion.SLOWER, self._show_count, motion.DECELERATE, key="count")

    def _show_count(self, value: float) -> None:
        if self._formatter is not None:
            self.value.setText(self._formatter(value))

    def showEvent(self, event):
        super().showEvent(event)
        if self._count_on_show and self._number is not None:
            self._count_on_show = False
            self._count(0.0, self._number)


class MetricGrid(QFrame):
    """One panel holding readouts in a grid separated by hairlines."""

    def __init__(self, tiles: list[StatTile], columns: int = 2, parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        rows = (len(tiles) + columns - 1) // columns
        for i, tile in enumerate(tiles):
            r, c = divmod(i, columns)
            grid.addWidget(tile, r * 2, c * 2)
            if c < columns - 1:
                line = vdivider()
                grid.addWidget(line, r * 2, c * 2 + 1)
            if r < rows - 1:
                grid.addWidget(divider(), r * 2 + 1, c * 2)
                if c < columns - 1:
                    grid.addWidget(divider(), r * 2 + 1, c * 2 + 1)
        for c in range(columns):
            grid.setColumnStretch(c * 2, 1)


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
        # Neutral monogram plate: calm, consistent, never a random colour.
        t = theme.current()
        radius = max(3.0, self._size * 0.16)
        p.setPen(QPen(QColor(t.border_strong), 1))
        p.setBrush(QColor(t.surface_alt))
        p.drawRoundedRect(QRectF(0.5, 0.5, self._size - 1, self._size - 1), radius, radius)
        p.setFont(fonts.mono(int(self._size * 0.42), 500, 0))
        p.setPen(QColor(t.text_dim))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._name.strip()[:1].upper())


class UsageBar(QWidget):
    """Thin horizontal meter with an optional limit marker."""

    def __init__(
        self,
        fraction: float = 0.0,
        tone: str = "accent",
        marker: float | None = None,
        animate_from: float | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._target = fraction
        self._fraction = fraction if animate_from is None else animate_from
        self._tone = tone
        self._marker = marker
        self._pending = animate_from is not None and abs(animate_from - fraction) > 0.001
        self.setFixedHeight(10)
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, fraction: float, tone: str | None = None, marker: float | None = None) -> None:
        self._tone = tone or self._tone
        self._marker = marker
        self._morph(fraction)

    def _morph(self, fraction: float) -> None:
        self._target = fraction
        motion.tween(self, self._fraction, fraction, motion.SLOW, self._set_fraction, motion.EASY_EASE, key="bar")

    def _set_fraction(self, value: float) -> None:
        self._fraction = value
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending:
            self._pending = False
            self._morph(self._target)

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        h, y = 4.0, (self.height() - 4) / 2
        p.setBrush(QColor(t.track))
        p.drawRoundedRect(QRectF(0, y, self.width(), h), 2, 2)
        frac = max(0.0, min(1.0, self._fraction))
        if frac > 0:
            p.setBrush(QColor(tone_color(self._tone)))
            p.drawRoundedRect(QRectF(0, y, max(h, self.width() * frac), h), 2, 2)
        if self._marker is not None and 0 < self._marker < 1:
            x = self.width() * self._marker
            p.setBrush(QColor(t.text_dim))
            p.drawRect(QRectF(x - 1, 0, 2, self.height()))


class Swatch(QWidget):
    """Small square colour key (category identity next to its label)."""

    def __init__(self, color: str, size: int = 8, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(size, size)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._color))
        p.drawRoundedRect(QRectF(self.rect()), 1.5, 1.5)


def legend_item(color: str, text: str) -> QWidget:
    """Swatch plus caption, kept together when a legend wraps."""
    host = QWidget()
    row = QHBoxLayout(host)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    row.addWidget(Swatch(color, 8))
    row.addWidget(label(text, "caption"))
    return host


class FlowLayout(QLayout):
    """Left-to-right layout that wraps onto new lines (legends, chips)."""

    def __init__(self, parent: QWidget | None = None, h_spacing: int = 16, v_spacing: int = 6):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h, self._v = h_spacing, v_spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _arrange(self, rect: QRect, apply: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x > rect.x() and x + hint.width() > rect.right() + 1:
                x, y, line = rect.x(), y + line + self._v, 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._h
            line = max(line, hint.height())
        return y + line - rect.y()


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
        tone: str = "ink",
        extra: str = "",
        marker: float | None = None,
        animate_from: float | None = None,
        rank: int | None = None,
        dot: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.app_id = app["app_id"]
        self.fraction = fraction
        self._hover = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"{app.get('name', '')}, {value}")
        self.setToolTip(f"{app.get('name', '')}: {value}" + (f" ({sub})" if sub else ""))
        self.setMinimumHeight(46)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 10, 6)
        lay.setSpacing(12)
        if rank is not None:
            num = label(f"{rank:02d}", "tick")
            num.setFixedWidth(18)
            lay.addWidget(num)
        lay.addWidget(AppAvatar(app.get("name", ""), app.get("icon_path"), 28))

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name = label(app.get("name", ""))
        name.setFont(fonts.sans(13, 600))
        name_row.addWidget(name)
        if app.get("is_favorite"):
            name_row.addWidget(icon_label("star", "gold", 12, filled=True))
        name_row.addStretch(1)
        text.addLayout(name_row)
        if sub:
            sub_row = QHBoxLayout()
            sub_row.setSpacing(6)
            if dot:
                sub_row.addWidget(Swatch(dot, 6))
            sub_row.addWidget(label(sub, "caption"), 1)
            text.addLayout(sub_row)
        holder = QWidget()
        holder.setLayout(text)
        holder.setMinimumWidth(120)
        holder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(holder, 3)

        self.bar = UsageBar(fraction, tone, marker, animate_from)
        lay.addWidget(self.bar, 2)

        val = label(
            value,
            "danger" if tone == "danger" else None,
            align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        val.setFont(fonts.sans(13, 600, tabular=True))
        val.setMinimumWidth(70)
        lay.addWidget(val)
        if extra:
            ex = label(extra, "tick", align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            ex.setMinimumWidth(34)
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

    def enterEvent(self, event):
        motion.tween(self, self._hover, 1.0, motion.FASTER, self._set_hover, motion.DECELERATE, key="hover")
        super().enterEvent(event)

    def leaveEvent(self, event):
        motion.tween(self, self._hover, 0.0, motion.FAST, self._set_hover, motion.ACCELERATE, key="hover")
        super().leaveEvent(event)

    def _set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    def focusInEvent(self, event):
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, event):
        t = theme.current()
        strength = max(self._hover, 1.0 if self.hasFocus() else 0.0)
        if strength > 0:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            fill = QColor(t.hover)
            fill.setAlphaF(strength)
            p.setPen(QPen(QColor(t.accent), 1) if self.hasFocus() else Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
            p.end()
        super().paintEvent(event)


ILLUSTRATIONS = {
    "calendar-days": "calendar",
    "search": "search",
    "layout-grid": "search",
    "star": "star",
    "mouse-pointer-click": "clicks",
    "power": "unplugged",
    "gift": "gift",
    "zap": "waiting",
    "clock": "waiting",
    "castle": "blueprint",
}


class Illustration(QLabel):
    """Hairline line-art that re-tints itself with the theme."""

    def __init__(self, name: str, width: int = 120, parent=None):
        super().__init__(parent)
        self._name = name
        self._width = width
        self.setFixedSize(width, int(width * 0.8))

        def apply():
            t = theme.current()
            try:
                self.setPixmap(icons.illustration(name, t.text_dim, t.accent, t.border, width))
            except RuntimeError:
                pass

        apply()
        self._apply = apply
        bus.theme_changed.connect(apply)
        self.destroyed.connect(lambda *_: _safe_disconnect(apply))


class EmptyState(QWidget):
    """Illustration, title, explanation and an optional next step."""

    def __init__(
        self, icon: str, title: str, message: str = "", action: str = "", on_action: Callable | None = None, parent=None
    ):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 20, 16, 24)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art = ILLUSTRATIONS.get(icon)
        if art:
            lay.addWidget(Illustration(art, 110), 0, Qt.AlignmentFlag.AlignHCenter)
        else:
            lay.addWidget(icon_label(icon, "text_muted", 28), 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(2)
        lay.addWidget(label(title, "heading", align=Qt.AlignmentFlag.AlignCenter))
        if message:
            msg = label(message, "dim", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
            msg.setMaximumWidth(400)
            lay.addWidget(msg, 0, Qt.AlignmentFlag.AlignHCenter)
        if action and on_action:
            lay.addSpacing(8)
            lay.addWidget(button(action, on_click=on_action), 0, Qt.AlignmentFlag.AlignHCenter)


class SegmentedControl(QFrame):
    changed = Signal(int)

    def __init__(self, options: list[str], current: int = 0, parent=None):
        super().__init__(parent)
        self.setProperty("segmented", True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self._thumb = QFrame(self)
        self._thumb.setObjectName("segThumb")
        self._thumb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, text in enumerate(options):
            b = QPushButton(text)
            b.setProperty("segment", True)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            b.installEventFilter(self)
            self._group.addButton(b, i)
            lay.addWidget(b)
        self._group.button(current).setChecked(True)
        self._group.idClicked.connect(self._on_clicked)

    def current(self) -> int:
        return self._group.checkedId()

    def set_current(self, index: int) -> None:
        btn = self._group.button(index)
        if btn and not btn.isChecked():
            btn.setChecked(True)
            self._move_thumb(animate=self.isVisible())

    def _on_clicked(self, index: int) -> None:
        self._move_thumb(animate=True)
        self.changed.emit(index)

    def _move_thumb(self, animate: bool) -> None:
        btn = self._group.checkedButton()
        if btn is None:
            return
        target = QRectF(btn.geometry())
        if animate:
            start = QRectF(self._thumb.geometry())
            motion.tween(
                self,
                start,
                target,
                motion.NORMAL,
                lambda r: self._thumb.setGeometry(r.toRect()),
                motion.EASY_EASE,
                key="thumb",
            )
        else:
            self._thumb.setGeometry(target.toRect())
        self._thumb.lower()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move) and obj is self._group.checkedButton():
            if motion.running(self, "thumb") is None:
                self._move_thumb(animate=False)
        return super().eventFilter(obj, event)


class Toggle(QAbstractButton):
    """On/off switch. The knob stretches while pressed and springs into place."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._knob = 1.0 if checked else 0.0
        self._press = 0.0
        self._hover = 0.0
        super().setChecked(checked)
        self.toggled.connect(self._animate)
        self.pressed.connect(lambda: self._tween("press", 1.0, motion.FASTER))
        self.released.connect(lambda: self._tween("press", 0.0, motion.FAST))

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
        motion.tween(
            self, self._knob, 1.0 if checked else 0.0, motion.GENTLE, self._set_knob, motion.SPRING, key="knob"
        )

    def _tween(self, name: str, target: float, duration: int) -> None:
        def apply(v: float) -> None:
            setattr(self, f"_{name}", v)
            self.update()

        motion.tween(self, getattr(self, f"_{name}"), target, duration, apply, motion.DECELERATE, key=name)

    def enterEvent(self, event):
        self._tween("hover", 1.0, motion.FAST)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._tween("hover", 0.0, motion.NORMAL)
        super().leaveEvent(event)

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 2, 38, 18)
        k = max(0.0, min(1.0, self._knob))  # colours never overshoot; position may
        off = theme._mix(t.border_strong, t.text_muted, 0.35 * self._hover)
        track = QColor(theme._mix(off, t.text, k))
        if not self.isEnabled():
            track.setAlphaF(0.4)
        p.setPen(QPen(QColor(t.accent), 2) if self.hasFocus() else Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme._mix(t.text_dim if t.dark else "#ffffff", t.window, k)))
        stretch = 5 * self._press
        width = 12 + stretch
        x = 4 + self._knob * (20 - stretch)
        p.drawRoundedRect(QRectF(x, 5, width, 12), 2.5, 2.5)


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
        t.setFont(fonts.sans(13, 600))
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
        self._rest_y = 0
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
        was_visible = self.isVisible() and self._effect.opacity() > 0.5
        self.adjustSize()
        self.reposition()
        self.raise_()
        self.show()
        if was_visible:
            self._animate(0, 0, 1.0, 1.0, 0, motion.LINEAR)  # cancel a dismissal in progress
        else:
            self._animate(12, 0, 0.0, 1.0, motion.GENTLE, motion.DECELERATE)
        self._timer.start(msec + (2500 if action else 0))

    def _animate(self, dy0: float, dy1: float, op0: float, op1: float, duration: int, easing, on_done=None) -> None:
        def step(t: float) -> None:
            self.move(self.x(), int(self._rest_y + motion.lerp(dy0, dy1, t)))
            self._effect.setOpacity(motion.lerp(op0, op1, t))

        motion.tween(self, 0.0, 1.0, duration, step, easing, on_done, key="toast")

    def reposition(self) -> None:
        parent = self.parentWidget()
        if not parent:
            return
        self.setMaximumWidth(min(560, parent.width() - 40))
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        self._rest_y = parent.height() - self.height() - 24
        self.move(max(20, x), self._rest_y)

    def dismiss(self) -> None:
        if self.isVisible():
            self._animate(0, 8, self._effect.opacity(), 0.0, motion.FAST, motion.ACCELERATE, self.hide)

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
        self.setFont(fonts.mono(9, 500, 0))
        self.setFixedHeight(16)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()

    def set_count(self, n: int) -> None:
        self.setText(str(n) if n < 100 else "99+")
        self.setVisible(n > 0)


class StatusModule(QAbstractButton):
    """Sidebar recorder module: live dot, state, current app and session clock."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedHeight(60)
        self._head, self._name, self._clock, self._tone, self._live = "", "", "", "text_muted", False
        self._hover = False
        self.pulse = motion.PulseDot(5, self)
        self.pulse.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.pulse.move(10, 9)

    def set_status(self, head: str, name: str, clock: str, tone: str, live: bool) -> None:
        self._head, self._name, self._clock, self._tone, self._live = head, name, clock, tone, live
        self.pulse.set_state(live, tone_color(tone))
        self.setAccessibleName(f"{head}: {name} {clock}".strip())
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        edge = t.accent if self.hasFocus() else (t.text_muted if self._hover else t.border)
        p.setPen(QPen(QColor(edge), 1))
        p.setBrush(QColor(t.surface))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), theme.RADIUS_PANEL, theme.RADIUS_PANEL)
        if not self._live:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(tone_color(self._tone)))
            p.drawRoundedRect(QRectF(16, 16, 8, 8), 1.5, 1.5)
        p.setFont(fonts.mono(9, 500, 10))
        p.setPen(QColor(tone_color("accent_text" if self._live else self._tone)))
        p.drawText(QRectF(32, 10, self.width() - 40, 16), Qt.AlignmentFlag.AlignVCenter, self._head.upper())
        p.setPen(QColor(t.text_dim))
        p.drawText(
            QRectF(32, 10, self.width() - 44, 16),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            self._clock,
        )
        p.setFont(fonts.sans(13, 600))
        p.setPen(QColor(t.text))
        name = p.fontMetrics().elidedText(self._name, Qt.TextElideMode.ElideRight, self.width() - 26)
        p.drawText(QRectF(14, 30, self.width() - 26, 20), Qt.AlignmentFlag.AlignVCenter, name)
