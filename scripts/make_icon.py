"""Build packaging/apptrackr.ico from apptrackr/assets/logo.svg.

    python scripts/make_icon.py

The .ico holds PNG-compressed frames from 16 to 256 px (supported since Windows Vista).
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_png(svg: bytes, size: int) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg)).render(painter)
    painter.end()
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(data)


def build_ico(frames: list[tuple[int, bytes]]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries, blobs = b"", b""
    for size, png in frames:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    return header + entries + blobs


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    _app = QGuiApplication(sys.argv[:1])
    svg = (ROOT / "apptrackr" / "assets" / "logo.svg").read_bytes()
    out = ROOT / "packaging" / "apptrackr.ico"
    out.write_bytes(build_ico([(s, render_png(svg, s)) for s in SIZES]))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
