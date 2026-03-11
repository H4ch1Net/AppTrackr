"""Neon theme system for the AppTrackr PySide6 UI."""

from __future__ import annotations

# -- Palette --
BG_DARKEST  = "#000000"
BG_DARK     = "#0b0f1a"
BG_CARD     = "#111827"
BG_CARD_ALT = "#1a2332"
BG_HOVER    = "#1e293b"
BG_INPUT    = "#0f172a"
TEXT_COLOR = "#ffffff"

# Default accent colors
CYAN        = "#06d6a0"
CYAN_DIM    = "#0a9e78"
PURPLE      = "#a855f7"
PURPLE_DIM  = "#7c3aed"
PINK        = "#ec4899"
BLUE        = "#3b82f6"
YELLOW      = "#fbbf24"
RED         = "#ef4444"
GREEN       = "#22c55e"

# Active theme accent (can be changed)
_ACTIVE_ACCENT = CYAN
_ACTIVE_ACCENT_DIM = CYAN_DIM

# Theme presets
THEME_PRESETS = {
    "Cyan": ("#06d6a0", "#0a9e78"),
    "Purple": ("#a855f7", "#7c3aed"),
    "Pink": ("#ec4899", "#be185d"),
    "Blue": ("#3b82f6", "#2563eb"),
    "Green": ("#22c55e", "#16a34a"),
    "Red": ("#ef4444", "#dc2626"),
    "Orange": ("#f97316", "#ea580c"),
    "Amber": ("#fbbf24", "#f59e0b"),
}


def set_theme(theme_name: str) -> None:
    """Set active theme accent color."""
    global _ACTIVE_ACCENT, _ACTIVE_ACCENT_DIM
    if theme_name in THEME_PRESETS:
        _ACTIVE_ACCENT, _ACTIVE_ACCENT_DIM = THEME_PRESETS[theme_name]


def get_accent() -> str:
    """Get current active accent color."""
    return _ACTIVE_ACCENT


def get_accent_dim() -> str:
    """Get current active accent dim color."""
    return _ACTIVE_ACCENT_DIM

TEXT        = "#e2e8f0"
TEXT_DIM    = "#94a3b8"
TEXT_MUTED  = "#64748b"

BORDER      = "#1e293b"

# -- Glow shadow CSS --
def glow(color: str = None, radius: int = 12, spread: int = 2) -> str:
    """Return a QSS drop-shadow string for glow effects."""
    # Qt doesn't support box-shadow natively; we use border + color trick
    if color is None:
        color = get_accent()
    return f"border: 1px solid {color};"


# -- Global stylesheet --
def get_stylesheet() -> str:
    """Generate stylesheet with current theme accent colors."""
    accent = get_accent()
    accent_dim = get_accent_dim()
    
    return f"""
/* ---- Global ---- */
QWidget {{
    color: {TEXT};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}

QMainWindow {{
    background-color: {BG_DARKEST};
}}

QStackedWidget, QStackedWidget > QWidget {{
    background-color: {BG_DARK};
}}

/* ---- Scroll bars ---- */
QScrollBar:vertical {{
    background: {BG_DARK};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {TEXT_MUTED};
    min-height: 30px;
    border-radius: 4px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {BG_DARK};
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {TEXT_MUTED};
    min-width: 30px;
    border-radius: 4px;
}}

/* ---- Buttons ---- */
QPushButton {{
    background-color: {BG_CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {BG_HOVER};
    border-color: {accent};
    color: {accent};
}}
QPushButton:pressed {{
    background-color: {BG_CARD_ALT};
}}
QPushButton#primary {{
    background-color: {accent_dim};
    color: {TEXT_COLOR};
    border-color: {accent};
}}
QPushButton#primary:hover {{
    background-color: {accent};
}}

/* ---- Labels ---- */
QLabel {{
    background: transparent;
}}
QLabel#heading {{
    font-size: 20px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#subheading {{
    font-size: 14px;
    color: {TEXT_DIM};
}}
QLabel#accent {{
    color: {accent};
    font-weight: 600;
}}
QLabel#value-large {{
    font-size: 28px;
    font-weight: 700;
    color: {accent};
}}

/* ---- Line edit ---- */
QLineEdit {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    color: {TEXT};
}}
QLineEdit:focus {{
    border-color: {accent};
}}

/* ---- Combo box ---- */
QComboBox {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    color: {TEXT};
}}
QComboBox:hover {{
    border-color: {accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    color: {TEXT};
    selection-background-color: {BG_HOVER};
}}

/* ---- Tab widget ---- */
QTabWidget::pane {{
    border: none;
    background: {BG_DARK};
}}
QTabBar::tab {{
    background: {BG_CARD};
    color: {TEXT_DIM};
    padding: 10px 20px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background: {BG_DARK};
    color: {accent};
    border-bottom: 2px solid {accent};
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}

/* ---- Progress bar ---- */
QProgressBar {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    color: {TEXT};
    height: 18px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent}, stop:1 {PURPLE});
    border-radius: 3px;
}}

/* ---- Slider ---- */
QSlider::groove:horizontal {{
    background: {BG_CARD};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {accent};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}

/* ---- Check box ---- */
QCheckBox {{
    spacing: 8px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid {BORDER};
    background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
}}

/* ---- Spin box ---- */
QSpinBox {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    color: {TEXT};
}}
QSpinBox:focus {{
    border-color: {accent};
}}

/* ---- Tool tip ---- */
QToolTip {{
    background: {BG_CARD};
    color: {TEXT};
    border: 1px solid {accent_dim};
    padding: 6px;
    border-radius: 4px;
}}

/* ---- Separator ---- */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {BORDER};
    max-height: 1px;
}}

/* ---- Menu ---- */
QMenu {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {BG_HOVER};
    color: {accent};
}}
"""


# Keep backward compatibility
GLOBAL_QSS = get_stylesheet()


def format_ms(ms: int) -> str:
    """Format milliseconds to human-readable string like '2h 15m'."""
    if ms < 0:
        ms = 0
    seconds = ms // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    mins = minutes % 60
    if hours < 24:
        return f"{hours}h {mins}m" if mins else f"{hours}h"
    days = hours // 24
    hrs = hours % 24
    return f"{days}d {hrs}h" if hrs else f"{days}d"
