"""Post-it look: paper colours, adhesive strip, drop shadow, stylesheet."""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

# Modelled on the real Post-it range.
# name: (paper top, paper bottom, adhesive strip, edge line, ink)
PALETTE = {
    "yellow": ("#fffbb0", "#fdee87", "#f9e372", "#e8d264", "#2f2a12"),
    "green":  ("#e3f8b4", "#cfec8e", "#c2e079", "#aecb68", "#25300f"),
    "blue":   ("#ccecfd", "#b0defa", "#9ad3f3", "#88c0e2", "#12293a"),
    "pink":   ("#ffd6e6", "#fcbcd6", "#f7a9c8", "#e695b6", "#3a1526"),
    "purple": ("#e9dcfb", "#d7c2f3", "#c9b0ec", "#b59cdb", "#261637"),
    "orange": ("#ffe3bd", "#ffcd95", "#ffbe7c", "#eeaa68", "#3a2410"),
    "white":  ("#fafaf4", "#eeeee6", "#e2e2d8", "#cfcfc4", "#2b2b26"),
}

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
  border-radius: 2px;
  border-top: 1px solid rgba(255,255,255,0.55);
  box-shadow: 0 1px 2px rgba(0,0,0,0.22),
              0 6px 14px rgba(0,0,0,0.24),
              0 12px 26px rgba(0,0,0,0.12);
}
/* the lift/curl at the bottom edge */
.sticky-curl {
  min-height: 6px;
  background-image: linear-gradient(to bottom,
      rgba(0,0,0,0.00) 0%,
      rgba(0,0,0,0.05) 55%,
      rgba(0,0,0,0.11) 100%);
  border-radius: 0 0 2px 2px;
}
.sticky-header { padding: 0 2px 1px 4px; }
/* the grab bar: generous target, faint dots so it reads as draggable */
.sticky-grab { opacity: 0.30; }
.sticky-header:hover .sticky-grab { opacity: 0.62; }
.sticky-body   { padding: 2px 7px 0 7px; }
.sticky-footer { padding: 0 4px 0 4px; }

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

.sticky-title { font-weight: bold; font-size: 0.97em; letter-spacing: 0.2px; }
.sticky-count { font-size: 0.76em; opacity: 0.6; padding-right: 3px; }
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
  background-color: rgba(0,0,0,0.10);
  border-radius: 4px;
}
.sticky button:active  { background-color: rgba(0,0,0,0.18); }
.sticky button.toggled { opacity: 0.95; background-color: rgba(0,0,0,0.12); border-radius: 4px; }

/* ---- checklist ---- */
.sticky list, .sticky row, .sticky list row { background-color: transparent; }
.sticky row:selected { background-color: rgba(0,0,0,0.06); }
.sticky checkbutton { padding: 0; min-height: 15px; }
.sticky-item-done { opacity: 0.42; }

/* row delete button: only there when you hover the row */
.sticky .row-del { opacity: 0; }
.sticky list row:hover .row-del { opacity: 0.40; }
.sticky .row-del:hover { opacity: 1; }

/* the one button that matters */
.sticky button.primary { opacity: 0.80; font-weight: bold; padding: 0 5px; }
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


def _color_rules():
    """Per-colour rules. These carry an extra class of specificity so they win
    against the system theme - without this, a dark GTK theme paints light text
    onto the light paper."""
    out = []
    for name, (top, bottom, strip, edge, ink) in PALETTE.items():
        out.append(
            """
/* paper */
.sticky-%(n)s .sticky, .sticky.sticky-%(n)s {
  color: %(ink)s;
  background-image: linear-gradient(to bottom, %(top)s 0%%, %(bottom)s 100%%);
  border-left: 1px solid %(edge)s;
  border-right: 1px solid %(edge)s;
  border-bottom: 1px solid %(edge)s;
}
.sticky-%(n)s .sticky-header {
  background-image: linear-gradient(to bottom,
      rgba(0,0,0,0.045) 0%%, rgba(0,0,0,0.012) 78%%, rgba(0,0,0,0.00) 100%%);
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
.sticky-%(n)s .sticky scrolledwindow,
.sticky-%(n)s .sticky viewport,
.sticky-%(n)s .sticky checkbutton {
  background-color: transparent;
  background-image: none;
  border: none;
  box-shadow: none;
  text-shadow: none;
}
.sticky-%(n)s .sticky button:hover  { background-color: rgba(0,0,0,0.10); border-radius: 4px; }
.sticky-%(n)s .sticky button:active { background-color: rgba(0,0,0,0.18); border-radius: 4px; }
.sticky-%(n)s .sticky button.toggled { background-color: rgba(0,0,0,0.13); border-radius: 4px; }

/* selection */
.sticky-%(n)s .sticky entry selection,
.sticky-%(n)s .sticky textview text selection {
  background-color: rgba(0,0,0,0.20);
  color: %(ink)s;
}

/* checkbox drawn as ink on paper, not as a themed widget */
.sticky-%(n)s .sticky check {
  min-width: 13px;
  min-height: 13px;
  background-image: none;
  background-color: rgba(255,255,255,0.60);
  border: 1px solid %(edge)s;
  border-radius: 3px;
  box-shadow: none;
  color: %(ink)s;
}
.sticky-%(n)s .sticky check:hover   { background-color: rgba(255,255,255,0.90); }
.sticky-%(n)s .sticky check:checked { background-color: %(strip)s; color: %(ink)s; }

.swatch-%(n)s { background-image: linear-gradient(to bottom, %(top)s, %(bottom)s);
                border: 1px solid %(edge)s; }
"""
            % {"n": name, "top": top, "bottom": bottom, "strip": strip,
               "edge": edge, "ink": ink}
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
  border-top: 1px solid rgba(0,0,0,0.13);
}
.sticky scrolledwindow.prompt-field {
  background-color: rgba(255,255,255,0.46);
  background-image: none;
  border: 1px solid rgba(0,0,0,0.13);
  border-radius: 3px;
}
.sticky .prompt-result { font-family: monospace; font-size: 0.84em; }
.sticky .panel-note { font-size: 0.78em; opacity: 0.62; }
.sticky .panel-note:hover { opacity: 0.92; }
.sticky label.error { color: #8f2c22; opacity: 0.95; }
.sticky .prompt-panel button { opacity: 0.62; }
.sticky .prompt-panel button:hover { opacity: 1; }
.sticky .prompt-panel button.primary { opacity: 0.9; }
"""

_provider = None


def install(font_scale=1.0, handwritten=False):
    """(Re)load the stylesheet screen-wide. Safe to call again on settings change."""
    global _provider
    css = _BASE_CSS + _color_rules() + _PANEL_CSS
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
