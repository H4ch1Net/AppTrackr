"""'In other terms': tracked time retold as Everest summit days, Moon trips and novels."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ... import perspective
from ...data import db
from .. import fmt, fonts, icons, motion, theme
from .components import Card, SegmentedControl, button, label, vdivider
from .rolling import RollingLabel

PERIODS = (("today", "Today"), ("week", "This week"), ("all", "All time"))


class _Glyph(QWidget):
    """Line icon that follows the theme and can change without rebinding."""

    def __init__(self, size: int = 20, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.name = ""

    def set_name(self, name: str) -> None:
        self.name = name
        self.update()

    def paintEvent(self, _event):
        if self.name:
            p = QPainter(self)
            p.drawPixmap(0, 0, icons.pixmap(self.name, theme.current().text_dim, self.width()))


class FactTile(QFrame):
    """One comparison: icon, rolling figure, what it counts, and the basis for the number."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("cell", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.glyph = _Glyph(20)
        top.addWidget(self.glyph, 0, Qt.AlignmentFlag.AlignVCenter)
        self.value = RollingLabel("–")
        self.value.setFont(fonts.sans(28, 600, tabular=True))
        top.addWidget(self.value, 1)
        lay.addLayout(top)
        self.what = label("", wrap=True)
        self.what.setFont(fonts.sans(13, 500))
        lay.addWidget(self.what)
        self.basis = label("", "caption", wrap=True)
        lay.addWidget(self.basis)
        lay.addStretch(1)
        self.key = ""

    def sizeHint(self) -> QSize:
        return QSize(220, super().sizeHint().height())

    def show_fact(self, fact: perspective.Fact | None, animate: bool) -> None:
        if fact is None:
            self.key = ""
            self.glyph.set_name("")
            self.value.setText("–")
            self.what.setText("")
            self.basis.setText("")
            return
        changed = fact.key != self.key
        self.key = fact.key
        self.glyph.set_name(fact.icon)
        if animate:
            self.value.roll_to(fact.value)
        else:
            self.value.setText(fact.value)
        self.what.setText(fact.label)
        self.basis.setText(fact.basis)
        if animate and changed:
            for w in (self.what, self.basis, self.glyph):
                motion.fade(w, 0.0, 1.0, motion.GENTLE, motion.DECELERATE)


class OtherTermsCard(Card):
    """Three comparisons for the chosen period, with a shuffle."""

    def __init__(self, index: int | None = None, parent=None):
        super().__init__("In other terms", "–", parent=parent, index=index)
        self.period = SegmentedControl([text for _, text in PERIODS])
        self.period.changed.connect(self._set_period)
        self.header_actions.addWidget(self.period)
        self.shuffle = button("Shuffle", kind="ghost", icon="refresh-cw", on_click=self._shuffle)
        self.shuffle.setToolTip("Show other comparisons")
        self.header_actions.addWidget(self.shuffle)
        row = QFrame()
        row.setProperty("cell", True)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.tiles: list[FactTile] = []
        for i in range(3):
            if i:
                lay.addWidget(vdivider())
            tile = FactTile()
            self.tiles.append(tile)
            lay.addWidget(tile, 1)
        self.body.addWidget(row)
        stored = db.get_setting("perspective_period", "week")
        self._period = stored if stored in dict(PERIODS) else "week"
        self.period.set_current([key for key, _ in PERIODS].index(self._period))
        self._offset = date.today().toordinal()  # a different set each day
        self._totals: dict[str, float] = {}
        self._shown_offset: int | None = None
        self._shown_period: str | None = None

    @property
    def current_period(self) -> str:
        return self._period

    def set_totals(self, today_ms: float, week_ms: float, all_ms: float) -> None:
        """Called on every refresh; figures roll as the totals grow."""
        self._totals = {"today": today_ms, "week": week_ms, "all": all_ms}
        self._render()

    def _set_period(self, index: int) -> None:
        self._period = PERIODS[index][0]
        db.set_setting("perspective_period", self._period)
        self._render()

    def _shuffle(self) -> None:
        self._offset += 1
        self._render()

    def _render(self) -> None:
        ms = self._totals.get(self._period, 0)
        minutes = ms / 60000
        phrase = {"today": "today", "week": "this week", "all": "since you started tracking"}[self._period]
        if minutes < 1:
            self.set_caption(f"Nothing tracked {phrase} yet. Comparisons appear as time adds up.")
            for tile in self.tiles:
                tile.show_fact(None, False)
            self.shuffle.setEnabled(False)
            return
        self.set_caption(f"{fmt.duration(ms, short=True)} in apps {phrase}. That is about:")
        facts = perspective.pick(minutes, len(self.tiles), self._offset)
        self.shuffle.setEnabled(perspective.readable_count(minutes) > len(self.tiles))
        animate = self.isVisible() and (self._shown_period is not None)
        for i, tile in enumerate(self.tiles):
            fact = facts[i] if i < len(facts) else None
            delay = (
                i * 70 if animate and (self._shown_offset != self._offset or self._shown_period != self._period) else 0
            )
            if delay:
                QTimer.singleShot(int(delay * motion.time_scale), tile, lambda t=tile, f=fact: t.show_fact(f, True))
            else:
                tile.show_fact(fact, animate)
        self._shown_offset, self._shown_period = self._offset, self._period
