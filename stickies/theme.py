"""Post-it look: paper colours, adhesive strip, drop shadow, stylesheet."""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

# Each theme maps the seven note colours to
# (paper top, paper bottom, adhesive strip, edge line, ink).
PALETTES = {
    # the real Post-it range
    "classic": {
        "yellow": ("#fffbb0", "#fdee87", "#f9e372", "#e8d264", "#2f2a12"),
        "green":  ("#e3f8b4", "#cfec8e", "#c2e079", "#aecb68", "#25300f"),
        "blue":   ("#ccecfd", "#b0defa", "#9ad3f3", "#88c0e2", "#12293a"),
        "pink":   ("#ffd6e6", "#fcbcd6", "#f7a9c8", "#e695b6", "#3a1526"),
        "purple": ("#e9dcfb", "#d7c2f3", "#c9b0ec", "#b59cdb", "#261637"),
        "orange": ("#ffe3bd", "#ffcd95", "#ffbe7c", "#eeaa68", "#3a2410"),
        "white":  ("#fafaf4", "#eeeee6", "#e2e2d8", "#cfcfc4", "#2b2b26"),
    },
    # milky, low-saturation, soft
    "pastel": {
        "yellow": ("#fffde0", "#fdf7c6", "#f6edaa", "#e7dc9a", "#4a4326"),
        "green":  ("#f0fbe0", "#e1f4cb", "#d0eab4", "#bdd8a0", "#33421f"),
        "blue":   ("#e6f5fe", "#d4ebfb", "#c0def4", "#accce4", "#22384a"),
        "pink":   ("#ffeaf3", "#fdd9e9", "#f8c8dc", "#e9b4cb", "#4a2536"),
        "purple": ("#f3ebfe", "#e6d9fa", "#d7c8f2", "#c5b4e2", "#342546"),
        "orange": ("#fff2e2", "#ffe4c8", "#ffd6ae", "#f0c295", "#4a3420"),
        "white":  ("#fdfdfa", "#f5f5ef", "#eaeae2", "#d9d9d0", "#3a3a34"),
    },
    # loud highlighter brights
    "neon": {
        "yellow": ("#ffff9e", "#fdfa5c", "#f7f13a", "#ded72c", "#2b2a05"),
        "green":  ("#ddffa8", "#c3fb6b", "#b0f24d", "#98da38", "#1d2c06"),
        "blue":   ("#b8f0ff", "#88e4ff", "#66d9fb", "#4cc0e4", "#042a38"),
        "pink":   ("#ffc6e2", "#ff9dcb", "#ff7fbb", "#ee66a4", "#3d0c26"),
        "purple": ("#e4ccff", "#cfa8ff", "#bf90ff", "#a97ae8", "#25073f"),
        "orange": ("#ffd8a8", "#ffbb6b", "#ffa94d", "#ef9438", "#3a1e04"),
        "white":  ("#ffffff", "#f1f1f1", "#e0e0e0", "#c7c7c7", "#1f1f1f"),
    },
    # dark paper, light ink - for dark desktops
    "night": {
        "yellow": ("#4d4726", "#3d391b", "#5f5833", "#2b2813", "#f4eec9"),
        "green":  ("#324726", "#28391c", "#405932", "#1c2913", "#def1c6"),
        "blue":   ("#253c4d", "#1c303e", "#324d5f", "#132229", "#d3eafb"),
        "pink":   ("#4d2636", "#3d1c2b", "#5f3345", "#2b131e", "#f9d6e6"),
        "purple": ("#36284d", "#2a1e3d", "#45345f", "#1f1629", "#e4d6f9"),
        "orange": ("#4d3823", "#3d2c1b", "#5f4733", "#2b1f13", "#fce3c5"),
        "white":  ("#3a3a40", "#2e2e34", "#4a4a51", "#212125", "#ededf0"),
    },
    # candy
    "bubblegum": {
        "yellow": ("#fff6cc", "#ffeaa6", "#ffe08a", "#f0cd77", "#4a3a1a"),
        "green":  ("#daf8e4", "#bff1d2", "#a8e9c2", "#91d3ac", "#17392a"),
        "blue":   ("#d8edff", "#bbdeff", "#a4d0fc", "#8dbae9", "#16304a"),
        "pink":   ("#ffe1f1", "#ffc4e4", "#ffadd8", "#f295c3", "#4a1533"),
        "purple": ("#eeddff", "#ddc4ff", "#ceb0ff", "#b799eb", "#2d1049"),
        "orange": ("#ffe4d7", "#ffcbb5", "#ffb99d", "#efa485", "#4a2418"),
        "white":  ("#fdf8fc", "#f6eef4", "#ebe1e9", "#d9cbd7", "#3a2c37"),
    },
    # cool and fresh
    "mint": {
        "yellow": ("#f5fbd2", "#e9f6b0", "#dcee99", "#c6da85", "#333d12"),
        "green":  ("#d7f7e6", "#b8eed2", "#a1e4c2", "#8acdab", "#12352a"),
        "blue":   ("#d5f3f8", "#b4e8f1", "#9bdce8", "#85c5d1", "#0f3038"),
        "pink":   ("#fde6f0", "#f9cdde", "#f4b9cf", "#e2a3ba", "#3d1a2a"),
        "purple": ("#e8e4fc", "#d3ccf6", "#c1b8ef", "#aaa1da", "#221c40"),
        "orange": ("#fdf0d8", "#f9deb6", "#f4ce9b", "#e2b985", "#3d2b14"),
        "white":  ("#f8fcfb", "#eef4f2", "#e1e9e7", "#ced8d5", "#293331"),
    },
}

THEME_LABELS = {
    "classic": "Classic Post-it",
    "pastel": "Pastel",
    "neon": "Highlighter",
    "night": "Night",
    "bubblegum": "Bubblegum",
    "mint": "Mint",
}
THEME_ORDER = ["classic", "pastel", "bubblegum", "mint", "neon", "night"]

# Surfaces that sit on top of the paper (input fields, checkboxes, chips) have
# to flip with the theme, or a light field lands under light ink.
TOKENS = {
    "classic": {"field": "rgba(255,255,255,0.46)", "field_border": "rgba(0,0,0,0.13)",
                "check": "rgba(255,255,255,0.60)", "hover": "rgba(0,0,0,0.09)",
                "active": "rgba(0,0,0,0.16)"},
    "pastel":  {"field": "rgba(255,255,255,0.58)", "field_border": "rgba(0,0,0,0.11)",
                "check": "rgba(255,255,255,0.72)", "hover": "rgba(0,0,0,0.07)",
                "active": "rgba(0,0,0,0.13)"},
    "neon":    {"field": "rgba(255,255,255,0.52)", "field_border": "rgba(0,0,0,0.18)",
                "check": "rgba(255,255,255,0.70)", "hover": "rgba(0,0,0,0.10)",
                "active": "rgba(0,0,0,0.18)"},
    "night":   {"field": "rgba(0,0,0,0.26)", "field_border": "rgba(255,255,255,0.13)",
                "check": "rgba(0,0,0,0.30)", "hover": "rgba(255,255,255,0.10)",
                "active": "rgba(255,255,255,0.16)",
                "sheen": "rgba(255,255,255,0.10)", "tape": "rgba(255,255,255,0.16)"},
    "bubblegum": {"field": "rgba(255,255,255,0.56)", "field_border": "rgba(0,0,0,0.10)",
                  "check": "rgba(255,255,255,0.74)", "hover": "rgba(0,0,0,0.07)",
                  "active": "rgba(0,0,0,0.13)"},
    "mint":    {"field": "rgba(255,255,255,0.56)", "field_border": "rgba(0,0,0,0.10)",
                "check": "rgba(255,255,255,0.74)", "hover": "rgba(0,0,0,0.07)",
                "active": "rgba(0,0,0,0.13)"},
}

# light themes all share the same paper sheen and tape
for _name, _tok in TOKENS.items():
    _tok.setdefault("sheen", "rgba(255,255,255,0.55)")
    _tok.setdefault("tape", "rgba(255,255,255,0.34)")

DEFAULT_THEME = "classic"
PALETTE = PALETTES[DEFAULT_THEME]   # rebound by install()

COLOR_LABELS = {
    "yellow": "Canary",
    "green": "Limeade",
    "blue": "Blue Sky",
    "pink": "Power Pink",
    "purple": "Iris",
    "orange": "Marrakesh",
    "white": "White",
}

# Tried in order for the note body when "handwritten" is on.
HANDWRITING_STACK = [
    "Caveat", "Patrick Hand", "Indie Flower", "Shadows Into Light",
    "Comic Neue", "Comic Sans MS", "Chilanka", "Chandas",
]

_BASE_CSS = """
window.sticky-window { background-color: transparent; }

/* ---- the paper ---- */
.sticky {
  border-radius: 10px;
  border-top: 1px solid rgba(255,255,255,0.55);
  box-shadow: 0 0 0 0.5px rgba(0,0,0,0.10),
              0 1px 2px rgba(0,0,0,0.10),
              0 4px 8px rgba(0,0,0,0.11),
              0 12px 24px rgba(0,0,0,0.13);
}
/* the lift/curl at the bottom edge */
.sticky-curl { min-height: 5px; background-image: none; }
.sticky-header { padding: 0 4px 2px 8px; }
/* the grab bar: generous target, faint dots so it reads as draggable */
.sticky-grab { opacity: 0.30; }
.tape { min-width: 58px; min-height: 13px; }
.sticky-grab { opacity: 0.22; }
.sticky-header:hover .sticky-grab { opacity: 0.45; }
.sticky-header:hover .sticky-grab { opacity: 0.62; }
.sticky-body   { padding: 3px 11px 0 11px; }
.sticky-footer { padding: 1px 7px 1px 7px; }

/* ---- text ---- */
.sticky entry,
.sticky textview,
.sticky textview text {
  background-color: transparent;
  background-image: none;
  border: none;
  box-shadow: none;
  outline: none;
  padding: 0 1px;
  font-size: 0.94em;
  caret-color: currentColor;
}
.sticky entry selection,
.sticky textview text selection { background-color: rgba(40,90,175,0.30); }
.sticky entry:disabled, .sticky textview:disabled { color: inherit; }

.sticky-title { font-weight: 600; font-size: 1.0em; letter-spacing: -0.005em; }
.sticky-date-due { color: #c0392b; opacity: 1; font-weight: bold; }
.sticky-date-past { opacity: 0.35; text-decoration: line-through; }
.calendar-popover calendar { font-size: 0.9em; }
.sticky-count { font-size: 0.74em; opacity: 0.5; padding-right: 4px;
                font-feature-settings: "tnum"; }
.sticky-placeholder { opacity: 0.42; font-style: italic; }

/* ---- chrome buttons: invisible until hovered ---- */
.sticky button, .sticky button.flat {
  background: none;
  background-image: none;
  border: none;
  box-shadow: none;
  padding: 0 3px;
  min-width: 17px;
  min-height: 17px;
  opacity: 0.42;
  color: inherit;
}
.sticky button:hover {
  opacity: 1;
  background-color: rgba(0,0,0,0.09);
  border-radius: 6px;
}
.sticky button:active  { background-color: rgba(0,0,0,0.14); border-radius: 6px; }
.sticky button.toggled { opacity: 1; background-color: rgba(0,0,0,0.09); border-radius: 6px; }

/* ---- checklist ---- */
.sticky list, .sticky row, .sticky list row { background-color: transparent; }
.sticky row:selected { background-color: rgba(0,0,0,0.05); border-radius: 6px; }
.sticky checkbutton { padding: 0; min-height: 15px; }
.sticky-item-done { opacity: 0.42; }

/* row delete button: only there when you hover the row */
.sticky .row-del { opacity: 0; }
.sticky list row:hover .row-del { opacity: 0.40; }
.sticky .row-del:hover { opacity: 1; }

/* the one button that matters */
.sticky button.format-b { font-weight: bold; font-family: serif; font-size: 1.05em; }
.sticky button.primary { opacity: 0.9; font-weight: 600; padding: 1px 9px; border-radius: 6px;
                         letter-spacing: 0.01em; }
.sticky button.primary:hover { opacity: 1; }

.sticky-grip { opacity: 0.30; }
.sticky-grip:hover { opacity: 0.75; }

.sticky scrollbar { background: none; border: none; }
.sticky scrollbar slider {
  background-color: rgba(0,0,0,0.20);
  border: none; min-width: 6px; min-height: 6px; border-radius: 6px;
}
.sticky scrollbar slider:hover { background-color: rgba(0,0,0,0.36); }

/* ---- companion windows ---- */
.prompt-view { font-family: monospace; }
.thinking-view { font-family: monospace; font-size: 0.85em; opacity: 0.65; }
.dim-label-small { font-size: 0.85em; opacity: 0.7; }
.board-preview { font-size: 0.88em; opacity: 0.70; }
.board-title { font-weight: bold; }
.swatch { min-width: 18px; min-height: 18px; border-radius: 2px;
          box-shadow: 0 1px 2px rgba(0,0,0,0.3); }
"""


def _hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _blend(a, b, amount):
    """Mix two hex colours. amount=0 -> a, amount=1 -> b."""
    ra, ga, ba = _hex_to_rgb(a)
    rb, gb, bb = _hex_to_rgb(b)
    return "#%02x%02x%02x" % (
        round(ra + (rb - ra) * amount),
        round(ga + (gb - ga) * amount),
        round(ba + (bb - ba) * amount),
    )


def _color_rules(palette, tokens):
    """Per-colour rules. These carry an extra class of specificity so they win
    against the system theme - without this, a dark GTK theme paints light text
    onto the light paper."""
    out = []
    for name, (top, bottom, strip, edge, ink) in palette.items():
        out.append(
            """
/* paper */
.sticky-%(n)s .sticky, .sticky.sticky-%(n)s {
  color: %(ink)s;
  background-color: %(paper)s;
  background-image: none;
  border-left: 1px solid %(edge)s;
  border-right: 1px solid %(edge)s;
  border-bottom: 1px solid %(edge)s;
}
.sticky-%(n)s .sticky-header {
  background-color: %(paper)s;
  background-image: none;
  border-bottom: 1px solid %(strip)s;
}
.sticky-%(n)s .sticky-footer { border-top: 1px solid %(strip)s; }

/* ink - every text-bearing node, or the system theme wins */
.sticky-%(n)s .sticky,
.sticky-%(n)s .sticky label,
.sticky-%(n)s .sticky entry,
.sticky-%(n)s .sticky textview,
.sticky-%(n)s .sticky textview text,
.sticky-%(n)s .sticky button,
.sticky-%(n)s .sticky button label,
.sticky-%(n)s .sticky button image,
.sticky-%(n)s .sticky image,
.sticky-%(n)s .sticky checkbutton,
.sticky-%(n)s .sticky checkbutton label {
  color: %(ink)s;
  caret-color: %(ink)s;
  -gtk-icon-effect: none;
}

/* strip every inherited surface back to bare paper */
.sticky-%(n)s .sticky entry,
.sticky-%(n)s .sticky textview,
.sticky-%(n)s .sticky textview text,
.sticky-%(n)s .sticky button,
.sticky-%(n)s .sticky list,
.sticky-%(n)s .sticky list row,
.sticky-%(n)s .sticky list.sticky-list,
.sticky-%(n)s .sticky list.sticky-list row,
.sticky-%(n)s .sticky list.sticky-list row:hover,
.sticky-%(n)s .sticky flowbox,
.sticky-%(n)s .sticky flowboxchild,
.sticky-%(n)s .sticky scrolledwindow,
.sticky-%(n)s .sticky viewport,
.sticky-%(n)s .sticky checkbutton {
  background-color: transparent;
  background-image: none;
  border: none;
  box-shadow: none;
  text-shadow: none;
}
.sticky-%(n)s .sticky button:hover  { background-color: %(hover)s; border-radius: 6px; }
.sticky-%(n)s .sticky button:active { background-color: %(active)s; border-radius: 6px; }
.sticky-%(n)s .sticky button.toggled { background-color: %(hover)s; border-radius: 6px; }

/* selection */
.sticky-%(n)s .sticky entry selection,
.sticky-%(n)s .sticky textview text selection {
  background-color: rgba(0,0,0,0.20);
  color: %(ink)s;
}

/* checkbox drawn as ink on paper, not as a themed widget */
.sticky-%(n)s .sticky check {
  min-width: 14px;
  min-height: 14px;
  background-image: none;
  background-color: %(check)s;
  border: 1px solid %(edge)s;
  border-radius: 4px;
  box-shadow: none;
  color: %(ink)s;
}
.sticky-%(n)s .sticky check:hover   { background-color: %(check_hover)s; }
.sticky-%(n)s .sticky check:checked { background-color: %(strip)s; color: %(ink)s; }

.swatch-%(n)s { background-color: %(paper)s; background-image: none;
                border: 1px solid %(edge)s; }

/* must out-specify the `.deck button` reset, which lands later in the sheet */
.deck button.deck-tab.deck-%(n)s,
.deck button.deck-tab.deck-%(n)s label {
  color: %(ink)s;
}
.deck button.deck-tab.deck-%(n)s {
  background-color: %(paper)s;
  background-image: none;
  border: 1px solid %(edge)s;
}
.deck button.deck-tab.deck-%(n)s:hover {
  background-color: %(strip)s;
  border-color: rgba(0,0,0,0.40);
}
"""
            % {"n": name, "top": top, "bottom": bottom, "strip": strip,
               "edge": edge, "ink": ink,
               "hover": tokens["hover"], "active": tokens["active"],
               "check": tokens["check"], "paper": _blend(top, bottom, 0.55),
               "check_hover": tokens["check"].replace("0.60", "0.85")
                                             .replace("0.72", "0.92")
                                             .replace("0.70", "0.90")
                                             .replace("0.30", "0.44")}
        )
    return "\n".join(out)


def available_handwriting():
    """First installed font from HANDWRITING_STACK, or None."""
    try:
        ctx = Gtk.Label().get_pango_context()
        installed = {f.get_name() for f in ctx.list_families()}
    except Exception:
        return None
    for name in HANDWRITING_STACK:
        if name in installed:
            return name
    return None


# Appended AFTER the per-colour rules so it wins the specificity tie on
# scrolledwindow backgrounds.
_PANEL_CSS = """
.sticky .prompt-panel {
  padding: 4px 7px 3px 7px;
  border-top: 1px solid @stickies_field_border;
}
.sticky scrolledwindow.prompt-field {
  background-color: @stickies_field;
  background-image: none;
  border: 1px solid @stickies_field_border;
  border-radius: 7px;
}
.sticky .prompt-result { font-family: monospace; font-size: 0.82em; }
.sticky .panel-label {
  font-size: 0.68em;
  letter-spacing: 0.10em;
  opacity: 0.42;
  font-weight: 600;
}
.sticky .panel-note { font-size: 0.76em; opacity: 0.55; letter-spacing: 0.005em; }
.sticky .panel-note:hover { opacity: 0.92; }
.sticky label.error { color: #8f2c22; opacity: 0.95; }
.sticky .prompt-panel button { opacity: 0.62; }
.sticky .prompt-panel button:hover { opacity: 1; }
.sticky .prompt-panel button.primary { opacity: 0.9; }
.sticky .prompt-panel flowboxchild { padding: 0; }
.sticky .prompt-panel flowbox button {
  padding: 0 8px;
  background-color: @stickies_field;
  border: 1px solid @stickies_field_border;
  border-radius: 6px;
  opacity: 0.72;
}
.sticky .prompt-panel flowbox button:hover {
  opacity: 1;
  background-color: @stickies_field_hover;
}
"""

_DECK_CSS = """
.deck {
  background-color: rgba(28,28,34,0.97);
  background-image: none;
  border-radius: 12px;
  padding: 5px 10px 6px 10px;
  border: 1px solid rgba(255,255,255,0.09);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.06),
              0 1px 2px rgba(0,0,0,0.30),
              0 8px 22px rgba(0,0,0,0.30);
}
.deck-grip { color: #ececf2; opacity: 0.30; }
.deck.deck-hot {
  background-color: rgba(74,74,94,0.97);
  background-image: none;
  border-color: rgba(255,255,255,0.34);
  box-shadow: 0 5px 20px rgba(0,0,0,0.5);
}

.deck button {
  background: none;
  background-image: none;
  border: none;
  box-shadow: none;
  text-shadow: none;
  min-height: 22px;
  padding: 0 6px;
}
.deck-action { color: #ececf2; opacity: 0.5; border-radius: 6px; font-size: 1.0em; }
.deck-action:hover { opacity: 1; background-color: rgba(255,255,255,0.14); }

.deck-tab {
  border-radius: 7px;
  padding: 0 10px;
  border: 1px solid rgba(0,0,0,0.25);
  font-size: 0.83em;
  min-height: 21px;
  letter-spacing: 0.005em;
}
.deck-tab:hover { border-color: rgba(0,0,0,0.45); }
.deck-tab:active { padding-top: 1px; }
.deck-more { color: #ececf2; background-color: rgba(255,255,255,0.10); border-color: rgba(255,255,255,0.18); }
.deck-more:hover { background-color: rgba(255,255,255,0.22); }
.deck-away { opacity: 0.42; }
.deck-away:hover { opacity: 0.75; }
.deck-badge {
  font-size: 0.72em;
  opacity: 0.55;
  padding: 0 4px;
  border-radius: 10px;
  background-color: rgba(0,0,0,0.10);
}
"""

_provider = None


def install(font_scale=1.0, handwritten=False, theme=DEFAULT_THEME):
    """(Re)load the stylesheet screen-wide. Safe to call again on settings change."""
    global _provider, PALETTE
    if theme not in PALETTES:
        theme = DEFAULT_THEME
    PALETTE = PALETTES[theme]
    tokens = TOKENS[theme]
    defs = (
        "@define-color stickies_field %(field)s;\n"
        "@define-color stickies_field_border %(field_border)s;\n"
        "@define-color stickies_field_hover %(hover_field)s;\n"
        "@define-color stickies_tape %(tape)s;\n"
        % {"field": tokens["field"], "field_border": tokens["field_border"],
           "hover_field": tokens["check"], "tape": tokens["tape"]}
    )
    css = defs + _BASE_CSS + _color_rules(PALETTE, tokens) + _PANEL_CSS + _DECK_CSS
    if font_scale and abs(font_scale - 1.0) > 0.01:
        css += "\n.sticky { font-size: %.2fem; }\n" % font_scale
    if handwritten:
        family = available_handwriting()
        if family:
            css += (
                "\n.sticky-title, .sticky textview, .sticky entry,"
                " .sticky checkbutton label { font-family: '%s'; }\n"
                ".sticky textview, .sticky entry { font-size: 1.12em; }\n" % family
            )
    screen = Gdk.Screen.get_default()
    if screen is None:
        return None
    if _provider is not None:
        Gtk.StyleContext.remove_provider_for_screen(screen, _provider)
    _provider = Gtk.CssProvider()
    _provider.load_from_data(css.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_screen(
        screen, _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    return _provider


def enable_rgba(window):
    """Alpha channel, so the drop shadow and square corners composite cleanly."""
    screen = window.get_screen()
    visual = screen.get_rgba_visual() if screen else None
    if visual is not None and screen.is_composited():
        window.set_visual(visual)
        window.set_app_paintable(True)
        return True
    return False
