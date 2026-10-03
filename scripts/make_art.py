"""Render the README banner (dark and light) and the GitHub social preview.

    python scripts/make_art.py [--out docs]

Drawn with the app's own theme tokens, fonts and chart conventions, so the
art stays in step with the interface.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCALE = 2  # render at 2x for high-density screens
# Minutes of focus per hour for the sample day; the last entry is the current hour.
HOURS = [0, 0, 0, 0, 0, 0, 0, 0, 0, 18, 52, 55, 28, 10, 41, 49, 17]
KICKER = "Foreground time tracker · Windows"
TAGLINE = "Counts the time each app actually has focus."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "docs"))
    args = parser.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen
    from PySide6.QtSvg import QSvgRenderer

    from apptrackr import paths
    from apptrackr.ui import fonts, theme
    from apptrackr.ui.widgets.charts import _column

    _app = QGuiApplication(sys.argv[:1])
    fonts.load()
    logo = QSvgRenderer(str(paths.assets_dir() / "logo.svg"))

    def text(p: QPainter, x: float, y: float, s: str, font, color: str, align=Qt.AlignmentFlag.AlignLeft) -> None:
        """Draw *s* with its baseline at *y*; right-aligned text ends at *x*."""
        p.setFont(font)
        p.setPen(QColor(color))
        if align & Qt.AlignmentFlag.AlignRight:
            x -= p.fontMetrics().horizontalAdvance(s)
        p.drawText(QPointF(x, y), s)

    def paper(p: QPainter, t: theme.Theme, w: float, h: float, radius: float) -> None:
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), radius, radius)
        p.fillPath(frame, QColor(t.window))
        p.save()
        p.setClipPath(frame)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.grid))
        step = 24
        for gx in range(step, int(w), step):
            for gy in range(step, int(h), step):
                p.drawEllipse(QPointF(gx, gy), 0.9, 0.9)
        p.restore()
        p.setPen(QPen(QColor(t.border), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(frame)

    def instrument(p: QPainter, t: theme.Theme, r: QRectF, title: str = "Today by hour") -> None:
        """A cut-out of the dashboard's 'Today by hour' panel."""
        p.setPen(QPen(QColor(t.border), 1))
        p.setBrush(QColor(t.surface))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), theme.RADIUS_PANEL, theme.RADIUS_PANEL)
        pad = 20
        text(p, r.left() + pad, r.top() + 30, f"01   {title.upper()}", fonts.mono(10, 500, 8), t.text_muted)
        total = sum(HOURS)
        readout = f"{total // 60}h {total % 60:02d}m"
        big = fonts.sans(24, 600, tabular=True)
        text(p, r.right() - pad, r.top() + 36, readout, big, t.text, Qt.AlignmentFlag.AlignRight)

        left, right = r.left() + pad + 30, r.right() - pad
        top, base = r.top() + 70, r.bottom() - 40
        peak = 60
        axis_font = fonts.mono(9, 400, 4)
        for minutes, name in ((0, "0"), (30, "30M"), (60, "1H")):
            y = base - (base - top) * minutes / peak
            p.setPen(QPen(QColor(t.border), 1))
            p.drawLine(QPointF(left, y), QPointF(right, y))
            text(p, left - 8, y + 3.5, name, axis_font, t.text_muted, Qt.AlignmentFlag.AlignRight)

        slot = (right - left) / 24
        bar_w = min(10.0, slot * 0.62)
        now = len(HOURS) - 1
        for hour in range(24):
            x = left + hour * slot + (slot - bar_w) / 2
            tick = 5 if hour % 6 == 0 else 3
            p.setPen(QPen(QColor(t.border_strong), 1))
            p.drawLine(QPointF(left + (hour + 0.5) * slot, base), QPointF(left + (hour + 0.5) * slot, base + tick))
            if hour % 6 == 0:
                text(p, left + (hour + 0.5) * slot - 7, base + 18, f"{hour:02d}", axis_font, t.text_muted)
            minutes = HOURS[hour] if hour < len(HOURS) else 0
            if not minutes:
                continue
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.accent if hour == now else t.ink))
            p.drawPath(_column(x, base, bar_w, (base - top) * minutes / peak, 2))
        # Value label for the current hour, beside its bar where the rest of the day is still empty.
        x_now = left + now * slot + (slot + bar_w) / 2 + 5
        y_now = base - (base - top) * HOURS[now] / peak + 9
        text(p, x_now, y_now, f"{HOURS[now]}m", fonts.sans(11, 600, tabular=True), t.text)

    def identity(p: QPainter, t: theme.Theme, x: float, y: float, title_px: int, tagline_px: int = 15) -> None:
        """Logo, kicker, wordmark and tagline stacked from (x, y)."""
        logo.render(p, QRectF(x, y, 56, 56))
        text(p, x, y + 98, KICKER.upper(), fonts.mono(10, 500, 10), t.accent_text)
        text(p, x - 2, y + 98 + title_px + 4, "AppTrackr", fonts.sans(title_px, 600), t.text)
        text(p, x, y + 98 + title_px + 34, TAGLINE, fonts.sans(tagline_px, 400), t.text_dim)

    def render(name: str, t: theme.Theme, w: int, h: int, draw) -> None:
        image = QImage(w * SCALE, h * SCALE, QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(SCALE)
        image.fill(Qt.GlobalColor.transparent)
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        draw(p, t, w, h)
        p.end()
        out = Path(args.out) / name
        out.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(out))
        print(f"wrote {out}")

    def banner(p, t, w, h):
        paper(p, t, w, h, 10)
        identity(p, t, 48, 44, 46)
        instrument(p, t, QRectF(w - 48 - 360, 40, 360, h - 80))

    def social(p, t, w, h):
        # Some surfaces crop the preview toward its center, so everything keeps a 40px margin.
        paper(p, t, w, h, 0)
        identity(p, t, 40, 52, 40, 13)
        instrument(p, t, QRectF(w - 40 - 270, 40, 270, h - 80), "Today")
        text(p, 40, h - 40, "github.com/H4ch1Net/AppTrackr", fonts.mono(9, 500, 6), t.text_muted)

    accent = theme.ACCENTS[theme.DEFAULT_ACCENT]
    dark = replace(theme.GRAPHITE, accent=accent)
    light = replace(theme.PAPER, accent=accent)
    render("banner-dark.png", dark, 880, 280, banner)
    render("banner-light.png", light, 880, 280, banner)
    render("social-preview.png", dark, 640, 320, social)
    return 0


if __name__ == "__main__":
    sys.exit(main())
