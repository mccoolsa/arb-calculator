"""Colour palette and fonts for the dark UI."""

from __future__ import annotations

# Surfaces
BG = "#05080c"           # window background
PANEL = "#0c1520"        # content panel behind the cards
CARD = "#16212e"         # card surface
CARD_ALT = "#1b2938"     # nested / stat surface
FIELD = "#101b27"        # input interior
FIELD_HOVER = "#14212f"

# Table rows. FIELD_HOVER sits a shade off CARD, which is fine behind an
# input but invisible as a selection, so rows get their own pair.
ROW_HOVER = "#1c2937"
ROW_SELECTED = "#1d3b55"

# Lines
BORDER = "#25333f"
BORDER_SOFT = "#1c2836"

# Text
TEXT = "#e6edf5"
TEXT_DIM = "#b3c1d1"
MUTED = "#7e91a6"
FAINT = "#5b6b7d"

# Accents
ACCENT = "#22a7f0"
ACCENT_HOVER = "#43b8fb"
ACCENT_DIM = "#134a6c"
GREEN = "#3ddc97"
GREEN_DIM = "#12402f"
RED = "#ff6b6b"
RED_DIM = "#41202399"
AMBER = "#f5b04c"

_FAMILY = "Segoe UI"
_FAMILY_SEMI = "Segoe UI Semibold"
_MONO = "Consolas"

FONT = (_FAMILY, 10)
FONT_SM = (_FAMILY, 9)
FONT_XS = (_FAMILY, 8)
FONT_BOLD = (_FAMILY_SEMI, 10)
FONT_LABEL = (_FAMILY, 10)
FONT_H1 = (_FAMILY_SEMI, 16)
FONT_H2 = (_FAMILY_SEMI, 12)
FONT_H3 = (_FAMILY_SEMI, 10)
FONT_STAT = (_FAMILY_SEMI, 14)
FONT_HERO = (_FAMILY_SEMI, 24)
FONT_INPUT = (_MONO, 11)


def resolve_fonts(root) -> None:
    """Fall back to a generic family if Segoe UI is unavailable."""
    global FONT, FONT_SM, FONT_XS, FONT_BOLD, FONT_LABEL
    global FONT_H1, FONT_H2, FONT_H3, FONT_STAT, FONT_HERO, FONT_INPUT
    try:
        from tkinter import font as tkfont
        families = set(tkfont.families(root))
    except Exception:
        return
    if _FAMILY in families:
        return
    fallback = "Helvetica" if "Helvetica" in families else "TkDefaultFont"
    mono = "Courier" if "Courier" in families else fallback

    def swap(spec, family):
        return (family,) + tuple(spec[1:])

    FONT = swap(FONT, fallback)
    FONT_SM = swap(FONT_SM, fallback)
    FONT_XS = swap(FONT_XS, fallback)
    FONT_BOLD = swap(FONT_BOLD, fallback) + ("bold",)
    FONT_LABEL = swap(FONT_LABEL, fallback)
    FONT_H1 = swap(FONT_H1, fallback) + ("bold",)
    FONT_H2 = swap(FONT_H2, fallback) + ("bold",)
    FONT_H3 = swap(FONT_H3, fallback) + ("bold",)
    FONT_STAT = swap(FONT_STAT, fallback) + ("bold",)
    FONT_HERO = swap(FONT_HERO, fallback) + ("bold",)
    FONT_INPUT = swap(FONT_INPUT, mono)
