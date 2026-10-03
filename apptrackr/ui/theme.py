"""Design tokens and the global Qt stylesheet.

All colors come from the active Theme, so switching mode or accent only needs
a new stylesheet plus a repaint of custom-painted widgets.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtGui import QColor, QPalette

ACCENTS = {
    "Cyan": "#10d9a3",
    "Blue": "#4f8cff",
    "Purple": "#a274ff",
    "Pink": "#f0609e",
    "Red": "#f2545b",
    "Orange": "#ff8a3d",
    "Amber": "#f5b82e",
    "Green": "#3ccf6e",
}
DEFAULT_ACCENT = "Cyan"
MODES = ("dark", "light", "system")


@dataclass(frozen=True)
class Theme:
    dark: bool
    window: str
    sidebar: str
    surface: str
    surface_alt: str
    hover: str
    input: str
    border: str
    border_strong: str
    text: str
    text_dim: str
    text_muted: str
    track: str
    accent: str = ACCENTS[DEFAULT_ACCENT]
    gold: str = "#f5b82e"
    danger: str = "#f2545b"
    warning: str = "#f59e0b"
    success: str = "#3ccf6e"

    # Derived accent tokens -------------------------------------------------
    def accent_soft(self, alpha: float = 0.16) -> str:
        c = QColor(self.accent)
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"

    @property
    def accent_hover(self) -> str:
        c = QColor(self.accent)
        return (c.lighter(112) if self.dark else c.darker(108)).name()

    @property
    def accent_text(self) -> str:
        """Accent usable as a text color on the window background."""
        c = QColor(self.accent)
        return c.name() if self.dark else c.darker(135).name()

    @property
    def on_accent(self) -> str:
        c = QColor(self.accent)
        luminance = 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
        return "#06110d" if luminance > 0.5 else "#ffffff"

    def color(self, name: str) -> QColor:
        return QColor(getattr(self, name))


DARK = Theme(
    dark=True,
    window="#0f1216",
    sidebar="#0b0d10",
    surface="#161a20",
    surface_alt="#1c2129",
    hover="#222833",
    input="#12161b",
    border="#242a33",
    border_strong="#323a46",
    text="#e7eaf0",
    text_dim="#a3abb9",
    text_muted="#6c7586",
    track="#232a34",
)

LIGHT = Theme(
    dark=False,
    window="#f5f6f8",
    sidebar="#eceef2",
    surface="#ffffff",
    surface_alt="#f3f4f7",
    hover="#e7eaef",
    input="#ffffff",
    border="#e1e4ea",
    border_strong="#cdd2da",
    text="#14171c",
    text_dim="#4a5363",
    text_muted="#858d9b",
    track="#e9ecf1",
    gold="#d99a06",
    danger="#dc3545",
    warning="#d97706",
    success="#16a34a",
)

_current = DARK
_mode = "dark"
_accent_name = DEFAULT_ACCENT


def current() -> Theme:
    return _current


def mode() -> str:
    return _mode


def accent_name() -> str:
    return _accent_name


def configure(mode: str | None = None, accent: str | None = None, system_dark: bool = True) -> Theme:
    """Select mode ('dark', 'light', 'system') and accent preset; returns the new theme."""
    global _current, _mode, _accent_name
    if mode in MODES:
        _mode = mode
    if accent in ACCENTS:
        _accent_name = accent
    dark = system_dark if _mode == "system" else _mode == "dark"
    _current = replace(DARK if dark else LIGHT, accent=ACCENTS[_accent_name])
    return _current


def palette(t: Theme | None = None) -> QPalette:
    """QPalette matching the theme, for widgets the stylesheet does not reach."""
    t = t or _current
    p = QPalette()
    role = QPalette.ColorRole
    p.setColor(role.Window, QColor(t.window))
    p.setColor(role.WindowText, QColor(t.text))
    p.setColor(role.Base, QColor(t.input))
    p.setColor(role.AlternateBase, QColor(t.surface_alt))
    p.setColor(role.Text, QColor(t.text))
    p.setColor(role.Button, QColor(t.surface_alt))
    p.setColor(role.ButtonText, QColor(t.text))
    p.setColor(role.Highlight, QColor(t.accent))
    p.setColor(role.HighlightedText, QColor(t.on_accent))
    p.setColor(role.ToolTipBase, QColor(t.surface_alt))
    p.setColor(role.ToolTipText, QColor(t.text))
    p.setColor(role.PlaceholderText, QColor(t.text_muted))
    p.setColor(role.Link, QColor(t.accent_text))
    p.setColor(QPalette.ColorGroup.Disabled, role.Text, QColor(t.text_muted))
    p.setColor(QPalette.ColorGroup.Disabled, role.ButtonText, QColor(t.text_muted))
    p.setColor(QPalette.ColorGroup.Disabled, role.WindowText, QColor(t.text_muted))
    return p


def stylesheet(t: Theme | None = None, arrow_icon: str = "") -> str:
    """Global QSS. *arrow_icon* is a file path for the combo box arrow image."""
    t = t or _current
    return f"""
QWidget {{ color: {t.text}; }}
QMainWindow, QDialog, QMessageBox {{ background: {t.window}; }}
QWidget#page, QWidget#scrollContent {{ background: {t.window}; }}
QScrollArea {{ background: transparent; border: none; }}

/* Sidebar */
QWidget#sidebar {{ background: {t.sidebar}; border-right: 1px solid {t.border}; }}
QLabel#brand {{ font-size: 16px; font-weight: 700; color: {t.text}; }}
QPushButton[nav="true"] {{
    background: transparent; color: {t.text_dim}; border: none; border-radius: 8px;
    text-align: left; padding: 0 12px; font-size: 13px; font-weight: 600;
}}
QPushButton[nav="true"]:hover {{ background: {t.hover}; color: {t.text}; }}
QPushButton[nav="true"]:checked {{ background: {t.accent_soft(0.14)}; color: {t.text}; }}
QPushButton[nav="true"]:focus {{ border: 1px solid {t.accent}; }}
QLabel#navBadge {{
    background: {t.accent}; color: {t.on_accent}; border-radius: 9px;
    font-size: 11px; font-weight: 700; padding: 0 6px;
}}
QPushButton#statusPill {{
    background: {t.surface}; border: 1px solid {t.border}; border-radius: 10px;
    padding: 9px 12px; text-align: left; color: {t.text_dim}; font-weight: 600;
}}
QPushButton#statusPill:hover {{ border-color: {t.border_strong}; color: {t.text}; }}
QPushButton#statusPill:focus {{ border-color: {t.accent}; }}

/* Typography */
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: 22px; font-weight: 700; }}
QLabel[role="subtitle"] {{ font-size: 13px; color: {t.text_dim}; }}
QLabel[role="section"] {{ font-size: 11px; font-weight: 700; color: {t.text_muted}; }}
QLabel[role="heading"] {{ font-size: 15px; font-weight: 700; }}
QLabel[role="value"] {{ font-size: 24px; font-weight: 700; }}
QLabel[role="hero"] {{ font-size: 34px; font-weight: 700; color: {t.accent_text}; }}
QLabel[role="dim"] {{ color: {t.text_dim}; }}
QLabel[role="muted"] {{ color: {t.text_muted}; }}
QLabel[role="caption"] {{ color: {t.text_muted}; font-size: 11px; }}
QLabel[role="accent"] {{ color: {t.accent_text}; font-weight: 600; }}
QLabel[role="danger"] {{ color: {t.danger}; font-weight: 600; }}
QLabel[role="warning"] {{ color: {t.warning}; font-weight: 600; }}
QLabel[role="success"] {{ color: {t.success}; font-weight: 600; }}
QLabel[role="pill"] {{
    background: {t.surface_alt}; border: 1px solid {t.border}; border-radius: 9px;
    color: {t.text_dim}; font-size: 11px; font-weight: 600; padding: 1px 8px;
}}
QLabel[role="pillAccent"] {{
    background: {t.accent_soft(0.16)}; border-radius: 9px; color: {t.accent_text};
    font-size: 11px; font-weight: 700; padding: 1px 8px;
}}
QLabel[role="pillDanger"] {{
    background: rgba(242, 84, 91, 0.16); border-radius: 9px; color: {t.danger};
    font-size: 11px; font-weight: 700; padding: 1px 8px;
}}
QLabel#kbd {{
    background: {t.surface_alt}; border: 1px solid {t.border_strong}; border-radius: 4px;
    padding: 1px 6px; font-size: 11px; color: {t.text_dim};
}}

/* Surfaces */
QFrame[card="true"] {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 12px; }}
QFrame[card="true"] QLabel {{ border: none; }}
QFrame[row="true"] {{ background: transparent; border: none; border-radius: 8px; }}
QFrame[row="true"]:hover {{ background: {t.hover}; }}
QFrame[divider="true"] {{ background: {t.border}; border: none; min-height: 1px; max-height: 1px; }}
QFrame[banner="true"] {{
    background: {t.accent_soft(0.10)}; border: 1px solid {t.accent_soft(0.35)}; border-radius: 10px;
}}

/* Buttons */
QPushButton, QToolButton {{
    background: {t.surface_alt}; color: {t.text}; border: 1px solid {t.border_strong};
    border-radius: 8px; padding: 7px 14px; font-weight: 600;
}}
QPushButton:hover, QToolButton:hover {{ background: {t.hover}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {t.border}; }}
QPushButton:focus, QToolButton:focus {{ border-color: {t.accent}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t.text_muted}; background: {t.surface}; border-color: {t.border}; }}
QPushButton:checked {{ background: {t.accent_soft(0.14)}; border-color: {t.accent_soft(0.55)}; }}
QPushButton[kind="primary"] {{ background: {t.accent}; color: {t.on_accent}; border: 1px solid {t.accent}; }}
QPushButton[kind="primary"]:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
QPushButton[kind="primary"]:focus {{ border: 1px solid {t.text}; }}
QPushButton[kind="primary"]:disabled {{ background: {t.surface_alt}; color: {t.text_muted}; border-color: {t.border}; }}
QPushButton[kind="ghost"], QToolButton[kind="ghost"] {{ background: transparent; border: 1px solid transparent; color: {t.text_dim}; }}
QPushButton[kind="ghost"]:hover, QToolButton[kind="ghost"]:hover {{ background: {t.hover}; color: {t.text}; }}
QPushButton[kind="ghost"]:focus, QToolButton[kind="ghost"]:focus {{ border-color: {t.accent}; }}
QPushButton[kind="ghost"]:checked {{ background: {t.accent_soft(0.12)}; color: {t.text}; }}
QPushButton[kind="danger"] {{ color: {t.danger}; }}
QPushButton[kind="link"] {{ background: transparent; border: none; color: {t.accent_text}; padding: 2px 0; }}
QPushButton[kind="link"]:hover {{ text-decoration: underline; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

/* Segmented control */
QFrame[segmented="true"] {{ background: {t.input}; border: 1px solid {t.border}; border-radius: 9px; }}
QPushButton[segment="true"] {{
    background: transparent; border: 1px solid transparent; border-radius: 7px;
    color: {t.text_dim}; padding: 5px 12px; font-weight: 600;
}}
QPushButton[segment="true"]:hover {{ color: {t.text}; }}
QPushButton[segment="true"]:checked {{ background: {t.surface_alt}; color: {t.text}; border-color: {t.border_strong}; }}
QPushButton[segment="true"]:focus {{ border-color: {t.accent}; }}

/* Inputs */
QLineEdit, QComboBox, QSpinBox {{
    background: {t.input}; border: 1px solid {t.border_strong}; border-radius: 8px;
    padding: 6px 10px; selection-background-color: {t.accent}; selection-color: {t.on_accent};
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {t.text_muted}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {t.accent}; }}
QComboBox {{ padding-right: 28px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 26px; border: none; background: transparent; }}
QComboBox::down-arrow {{ image: url("{arrow_icon}"); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{
    background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 8px; padding: 4px;
    selection-background-color: {t.hover}; selection-color: {t.text}; outline: none;
}}

/* Progress */
QProgressBar {{ background: {t.track}; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; }}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 4px; }}
QProgressBar[tone="danger"]::chunk {{ background: {t.danger}; }}
QProgressBar[tone="gold"]::chunk {{ background: {t.gold}; }}

/* Scroll bars */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border_strong}; min-height: 32px; border-radius: 3px; }}
QScrollBar::handle:vertical:hover {{ background: {t.text_muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.border_strong}; min-width: 32px; border-radius: 3px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* Popups */
QToolTip {{
    background: {t.surface_alt}; color: {t.text}; border: 1px solid {t.border_strong};
    border-radius: 6px; padding: 6px 8px;
}}
QMenu {{ background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t.hover}; }}
QMenu::item:disabled {{ color: {t.text_muted}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 6px; }}
QProgressDialog QLabel {{ padding: 4px; }}

/* Toast */
QFrame#toast {{ background: {t.surface_alt}; border: 1px solid {t.border_strong}; border-radius: 10px; }}
QFrame#toast QLabel {{ color: {t.text}; }}
"""
