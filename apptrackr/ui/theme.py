"""Design tokens and the global stylesheet: the "Instrument panel" system.

Six palettes (three dark, three light) share one structure: neutral surfaces,
hairline borders and a single signal accent. Data marks are drawn in neutral
ink; the accent marks what is live or selected. Every palette keeps small text
at 4.5:1 or better, and accents are re-stepped per palette so marks read at 3:1
and accent text at 4.5:1. Fonts come from ui/fonts.py.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtGui import QColor, QPalette

# Signal accents, tuned for dark surfaces. Light palettes darken them (fit_accent)
# so fills and text keep their contrast.
ACCENTS = {
    "Orange": "#ff6b1a",
    "Amber": "#f2b01e",
    "Red": "#f04e4e",
    "Pink": "#ec5f9c",
    "Purple": "#9d7bff",
    "Blue": "#4c8dff",
    "Cyan": "#22c3a6",
    "Green": "#47c46b",
}
DEFAULT_ACCENT = "Orange"
MODES = ("dark", "light", "system")

RADIUS_PANEL = 6
RADIUS_CONTROL = 4


def _mix(a: str, b: str, t: float) -> str:
    """Blend colour *a* toward *b* by *t* (0..1)."""
    ca, cb = QColor(a), QColor(b)
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
    ).name()


def _luminance(c: QColor) -> float:
    def lin(v: float) -> float:
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(c.redF()) + 0.7152 * lin(c.greenF()) + 0.0722 * lin(c.blueF())


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(QColor(a)), _luminance(QColor(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _step_until(color: str, against: tuple[str, ...], target: float, dark: bool) -> str:
    """Lighten (dark themes) or darken (light themes) *color* in HSV until it meets *target*."""
    c = QColor(color)
    for _ in range(40):
        if all(contrast(c.name(), bg) >= target for bg in against):
            break
        c = c.lighter(104) if dark else c.darker(104)
        if dark and c.value() >= 255:  # saturated colours stop lightening in HSV; blend toward white
            c = QColor(_mix(c.name(), "#ffffff", 0.08))
    return c.name()


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
    ink: str  # neutral data marks
    grid: str  # graph-paper dots
    accent: str = ACCENTS[DEFAULT_ACCENT]
    gold: str = "#e9a923"
    danger: str = "#f04e4e"
    warning: str = "#f2a516"
    success: str = "#47c46b"
    name: str = ""

    def accent_soft(self, alpha: float = 0.16) -> str:
        c = QColor(self.accent)
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"

    @property
    def accent_hover(self) -> str:
        c = QColor(self.accent)
        return (c.lighter(110) if self.dark else c.darker(108)).name()

    @property
    def accent_text(self) -> str:
        """Accent usable as small text on the window and on panels (4.5:1)."""
        return _step_until(self.accent, (self.window, self.surface), 4.5, self.dark)

    @property
    def on_accent(self) -> str:
        """Ink or white, whichever reads better on an accent fill."""
        ink, white = "#14120f", "#ffffff"
        return ink if contrast(self.accent, ink) >= contrast(self.accent, white) else white

    def heat(self, level: int, today: bool = False) -> str:
        """Quantized calendar ramp: 0 = empty, 1..4 = ink steps. Today uses the signal hue."""
        if level <= 0:
            return self.track
        top = self.accent if today else self.text_dim
        return _mix(self.surface, top, (0.22, 0.42, 0.66, 0.9 if not today else 1.0)[min(level, 4) - 1])

    def color(self, name: str) -> QColor:
        return QColor(getattr(self, name))


GRAPHITE = Theme(
    name="Graphite",
    dark=True,
    window="#121210",
    sidebar="#0e0e0c",
    surface="#191917",
    surface_alt="#21201d",
    hover="#292825",
    input="#151513",
    border="#2b2a26",
    border_strong="#3b3a35",
    text="#edebe4",
    text_dim="#aaa79d",
    text_muted="#8b8880",
    track="#25241f",
    ink="#6b6860",
    grid="#23221f",
)

CARBON = Theme(
    name="Carbon",
    dark=True,
    window="#000000",
    sidebar="#050505",
    surface="#0c0c0c",
    surface_alt="#141414",
    hover="#1b1b1b",
    input="#080808",
    border="#242424",
    border_strong="#353535",
    text="#f3f3f1",
    text_dim="#a9a9a6",
    text_muted="#80807d",
    track="#1a1a1a",
    ink="#5e5e5c",
    grid="#151515",
)

MIDNIGHT = Theme(
    name="Midnight",
    dark=True,
    window="#0b0f17",
    sidebar="#080b11",
    surface="#111723",
    surface_alt="#18202e",
    hover="#1f2938",
    input="#0d121c",
    border="#232d3d",
    border_strong="#334055",
    text="#e7ecf3",
    text_dim="#a0abbd",
    text_muted="#7d89a1",
    track="#1a2231",
    ink="#58657b",
    grid="#171f2c",
)

_LIGHT_STATUS = {"gold": "#b9800a", "danger": "#d23b30", "warning": "#b86e00", "success": "#2a8a47"}

PAPER = Theme(
    name="Paper",
    dark=False,
    window="#f2f0ea",
    sidebar="#ebe8e0",
    surface="#faf9f5",
    surface_alt="#f1eee7",
    hover="#e9e5dc",
    input="#fdfcf9",
    border="#ddd8cd",
    border_strong="#c8c2b5",
    text="#191814",
    text_dim="#4f4c44",
    text_muted="#6b675e",
    track="#e7e3d9",
    ink="#969082",
    grid="#e0dcd2",
    **_LIGHT_STATUS,
)

PORCELAIN = Theme(
    name="Porcelain",
    dark=False,
    window="#f0f2f4",
    sidebar="#e8ebee",
    surface="#fbfcfd",
    surface_alt="#eff1f4",
    hover="#e5e8ec",
    input="#ffffff",
    border="#d8dce2",
    border_strong="#c2c8d0",
    text="#14171c",
    text_dim="#48505c",
    text_muted="#626976",
    track="#e3e6eb",
    ink="#8c939e",
    grid="#dde1e6",
    **_LIGHT_STATUS,
)

SAGE = Theme(
    name="Sage",
    dark=False,
    window="#edf0ea",
    sidebar="#e4e8e0",
    surface="#f8faf6",
    surface_alt="#ecefe8",
    hover="#e1e6dc",
    input="#fbfcfa",
    border="#d3d9cd",
    border_strong="#bbc4b4",
    text="#151a13",
    text_dim="#465041",
    text_muted="#5f695a",
    track="#dfe4da",
    ink="#899282",
    grid="#d9dfd3",
    **_LIGHT_STATUS,
)

DARK_PALETTES = {t.name: t for t in (GRAPHITE, CARBON, MIDNIGHT)}
LIGHT_PALETTES = {t.name: t for t in (PAPER, PORCELAIN, SAGE)}
PALETTES = {**DARK_PALETTES, **LIGHT_PALETTES}
DEFAULT_DARK, DEFAULT_LIGHT = GRAPHITE.name, PAPER.name


def fit_accent(color: str, base: Theme) -> str:
    """The accent as used on *base*: stepped until marks read at 3:1 against its panels."""
    return _step_until(color, (base.surface, base.window), 3.0, base.dark)


def build(palette_name: str, accent_name: str = DEFAULT_ACCENT) -> Theme:
    """A complete theme: palette plus fitted accent."""
    base = PALETTES.get(palette_name, GRAPHITE)
    return replace(base, accent=fit_accent(ACCENTS.get(accent_name, ACCENTS[DEFAULT_ACCENT]), base))


# Category colours: a validated categorical set (dataviz reference palette), stepped
# per mode. Text never wears these; they mark swatches, dots and share segments.
# The reference orange is swapped for bronze so no category reads as the signal colour.
CATEGORY_COLORS = {
    "Work": ("#2a78d6", "#3987e5"),
    "Development": ("#1baf7a", "#199e70"),
    "Communication": ("#eda100", "#c98500"),
    "Study": ("#4a3aa7", "#9085e9"),
    "Social": ("#008300", "#008300"),
    "Games": ("#e87ba4", "#d55181"),
    "Entertainment": ("#e34948", "#e66767"),
    "Tools": ("#8c6d1f", "#9c7a25"),
    None: ("#a39e92", "#5e5b54"),
}

_current = build(DEFAULT_DARK)
_mode = "dark"
_accent_name = DEFAULT_ACCENT
_palettes = {"dark": DEFAULT_DARK, "light": DEFAULT_LIGHT}


def current() -> Theme:
    return _current


def mode() -> str:
    return _mode


def accent_name() -> str:
    return _accent_name


def palette_choice(kind: str) -> str:
    """The palette chosen for 'dark' or 'light' mode."""
    return _palettes[kind]


def category_color(category: str | None) -> str:
    light, dark = CATEGORY_COLORS.get(category, CATEGORY_COLORS[None])
    return dark if _current.dark else light


def configure(
    mode: str | None = None,
    accent: str | None = None,
    system_dark: bool = True,
    dark_palette: str | None = None,
    light_palette: str | None = None,
) -> Theme:
    """Select mode ('dark', 'light', 'system'), accent and per-mode palettes; returns the new theme."""
    global _current, _mode, _accent_name
    if mode in MODES:
        _mode = mode
    if accent in ACCENTS:
        _accent_name = accent
    if dark_palette in DARK_PALETTES:
        _palettes["dark"] = dark_palette
    if light_palette in LIGHT_PALETTES:
        _palettes["light"] = light_palette
    dark = system_dark if _mode == "system" else _mode == "dark"
    _current = build(_palettes["dark" if dark else "light"], _accent_name)
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
    for r in (role.Text, role.ButtonText, role.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, r, QColor(t.text_muted))
    return p


def stylesheet(t: Theme | None = None, arrow_icon: str = "") -> str:
    """Global QSS. *arrow_icon* is a file path for the combo box arrow image."""
    t = t or _current
    rp, rc = RADIUS_PANEL, RADIUS_CONTROL
    return f"""
QWidget {{ color: {t.text}; }}
QMainWindow, QDialog, QMessageBox {{ background: {t.window}; }}
QScrollArea {{ background: transparent; border: none; }}

/* Sidebar */
QWidget#sidebar {{ background: {t.sidebar}; border-right: 1px solid {t.border}; }}
QPushButton[nav="true"] {{
    background: transparent; color: {t.text_dim}; border: 1px solid transparent; border-radius: {rc}px;
    text-align: left; padding: 0 10px; font-size: 13px; font-weight: 500;
}}
QPushButton[nav="true"]:hover {{ background: {t.hover}; color: {t.text}; }}
QPushButton[nav="true"]:checked {{ background: {t.surface_alt}; color: {t.text}; border-color: {t.border}; }}
QPushButton[nav="true"]:focus {{ border-color: {t.accent}; }}
QFrame#navIndicator {{ background: {t.accent}; border: none; border-radius: 1px; }}
QLabel#navKey {{ color: {t.text_muted}; border: 1px solid {t.border}; border-radius: 3px; }}
QLabel#navBadge {{
    background: {t.accent}; color: {t.on_accent}; border-radius: 3px; padding: 0 5px;
}}

/* Typography (mono roles get their font in code; see widgets.components.label) */
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: 24px; font-weight: 600; }}
QLabel[role="subtitle"] {{ font-size: 13px; color: {t.text_dim}; }}
QLabel[role="eyebrow"], QLabel[role="tick"] {{ color: {t.text_muted}; }}
QLabel[role="eyebrowAccent"] {{ color: {t.accent_text}; }}
QLabel[role="heading"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="value"] {{ font-size: 28px; font-weight: 600; }}
QLabel[role="hero"] {{ font-size: 44px; font-weight: 600; color: {t.text}; }}
QLabel[role="dim"] {{ color: {t.text_dim}; }}
QLabel[role="muted"] {{ color: {t.text_muted}; }}
QLabel[role="caption"] {{ color: {t.text_muted}; font-size: 12px; }}
QLabel[role="accent"] {{ color: {t.accent_text}; font-weight: 600; }}
QLabel[role="danger"] {{ color: {t.danger}; font-weight: 600; }}
QLabel[role="warning"] {{ color: {t.warning}; font-weight: 600; }}
QLabel[role="success"] {{ color: {t.success}; font-weight: 600; }}
QLabel[role="pill"] {{
    background: transparent; border: 1px solid {t.border_strong}; border-radius: 3px;
    color: {t.text_dim}; padding: 1px 6px;
}}
QLabel[role="pillAccent"] {{
    background: {t.accent_soft(0.14)}; border: 1px solid {t.accent_soft(0.45)}; border-radius: 3px;
    color: {t.accent_text}; padding: 1px 6px;
}}
QLabel[role="pillDanger"] {{
    background: transparent; border: 1px solid {t.danger}; border-radius: 3px; color: {t.danger}; padding: 1px 6px;
}}
QLabel#kbd {{
    background: {t.surface_alt}; border: 1px solid {t.border_strong}; border-bottom-width: 2px;
    border-radius: 3px; padding: 1px 6px; color: {t.text_dim};
}}

/* Surfaces */
QFrame[card="true"] {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: {rp}px; }}
QFrame[card="true"] QLabel {{ border: none; }}
QFrame[cell="true"] {{ background: transparent; border: none; }}
QFrame[row="true"] {{ background: transparent; border: none; border-radius: {rc}px; }}
QFrame[row="true"]:hover {{ background: {t.hover}; }}
QFrame[divider="true"] {{ background: {t.border}; border: none; min-height: 1px; max-height: 1px; }}
QFrame[vdivider="true"] {{ background: {t.border}; border: none; min-width: 1px; max-width: 1px; }}
QFrame[banner="true"] {{
    background: {t.accent_soft(0.08)}; border: 1px solid {t.accent_soft(0.4)}; border-radius: {rp}px;
}}

/* Buttons */
QPushButton, QToolButton {{
    background: transparent; color: {t.text}; border: 1px solid {t.border_strong};
    border-radius: {rc}px; padding: 6px 12px; font-weight: 500;
}}
QPushButton:hover, QToolButton:hover {{ background: {t.hover}; border-color: {t.text_muted}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {t.border}; }}
QPushButton:focus, QToolButton:focus {{ border-color: {t.accent}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t.text_muted}; border-color: {t.border}; background: transparent; }}
QPushButton:checked {{ background: {t.accent_soft(0.12)}; border-color: {t.accent_soft(0.55)}; }}
QPushButton[kind="primary"] {{ background: {t.accent}; color: {t.on_accent}; border: 1px solid {t.accent}; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
QPushButton[kind="primary"]:focus {{ border: 1px solid {t.text}; }}
QPushButton[kind="primary"]:disabled {{ background: transparent; color: {t.text_muted}; border-color: {t.border}; }}
QPushButton[kind="ghost"], QToolButton[kind="ghost"] {{ background: transparent; border: 1px solid transparent; color: {t.text_dim}; }}
QPushButton[kind="ghost"]:hover, QToolButton[kind="ghost"]:hover {{ background: {t.hover}; color: {t.text}; }}
QPushButton[kind="ghost"]:focus, QToolButton[kind="ghost"]:focus {{ border-color: {t.accent}; }}
QPushButton[kind="ghost"]:checked {{ background: {t.accent_soft(0.12)}; color: {t.text}; }}
QPushButton[kind="danger"] {{ color: {t.danger}; }}
QPushButton[kind="link"] {{ background: transparent; border: none; color: {t.accent_text}; padding: 2px 0; font-weight: 500; }}
QPushButton[kind="link"]:hover {{ text-decoration: underline; background: transparent; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

/* Segmented control */
QFrame[segmented="true"] {{ background: {t.input}; border: 1px solid {t.border}; border-radius: {rc + 1}px; }}
QPushButton[segment="true"] {{
    background: transparent; border: 1px solid transparent; border-radius: {rc - 1}px;
    color: {t.text_dim}; padding: 4px 12px; font-weight: 500;
}}
QPushButton[segment="true"]:hover {{ color: {t.text}; background: transparent; }}
QPushButton[segment="true"]:checked {{ background: transparent; color: {t.text}; border-color: transparent; }}
QFrame#segThumb {{ background: {t.surface_alt}; border: 1px solid {t.border_strong}; border-radius: {rc - 1}px; }}
QPushButton[segment="true"]:focus {{ border-color: {t.accent}; }}

/* Inputs */
QLineEdit, QComboBox, QSpinBox {{
    background: {t.input}; border: 1px solid {t.border_strong}; border-radius: {rc}px;
    padding: 6px 10px; selection-background-color: {t.accent}; selection-color: {t.on_accent};
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {t.text_muted}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {t.accent}; }}
QComboBox {{ padding-right: 28px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 26px; border: none; background: transparent; }}
QComboBox::down-arrow {{ image: url("{arrow_icon}"); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{
    background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: {rc}px; padding: 4px;
    selection-background-color: {t.hover}; selection-color: {t.text}; outline: none;
}}

/* Progress */
QProgressBar {{ background: {t.track}; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }}
QProgressBar::chunk {{ background: {t.ink}; border-radius: 2px; }}
QProgressBar[tone="accent"]::chunk {{ background: {t.accent}; }}
QProgressBar[tone="danger"]::chunk {{ background: {t.danger}; }}
QProgressBar[tone="gold"]::chunk {{ background: {t.gold}; }}

/* Scroll bars */
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border_strong}; min-height: 32px; border-radius: 2px; }}
QScrollBar::handle:vertical:hover {{ background: {t.text_muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.border_strong}; min-width: 32px; border-radius: 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* Popups */
QToolTip {{
    background: {t.surface_alt}; color: {t.text}; border: 1px solid {t.border_strong};
    border-radius: {rc}px; padding: 6px 8px;
}}
QMenu {{ background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: {rp}px; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: {rc - 1}px; }}
QMenu::item:selected {{ background: {t.hover}; }}
QMenu::item:disabled {{ color: {t.text_muted}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 6px; }}
QProgressDialog QLabel {{ padding: 4px; }}

/* Toast */
QFrame#toast {{ background: {t.surface_alt}; border: 1px solid {t.border_strong}; border-left: 3px solid {t.accent}; border-radius: {rc}px; }}
QFrame#toast QLabel {{ color: {t.text}; }}
"""
