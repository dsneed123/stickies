"""Snap-to-grid mode: notes live in equal cells in one part of the screen.

While the mode is on every on-screen note is resized into a cell of a
rectangle (the left or right half, third or quarter of the work area, below
the deck). Dragging a note shows a translucent slot where it will land;
letting go drops it there and the others shuffle around it. New, shown and
hidden notes reflow the grid."""

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import theme, util
from .layout import SpanGrid

SETTLE_MS = 260     # no configure events for this long = the drag has ended


class SlotHighlight(Gtk.Window):
    """A see-through dashed rectangle marking where a dragged note will snap."""

    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.TOOLTIP)
        self.set_app_paintable(True)
        theme.enable_rgba(self)
        self.connect("draw", self._draw)

    def _draw(self, _widget, cr):
        w, h = self.get_size()
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        r, inset = 9, 2.5
        x0, y0, x1, y1 = inset, inset, w - inset, h - inset
        cr.new_sub_path()
        cr.arc(x1 - r, y0 + r, r, -1.5708, 0)
        cr.arc(x1 - r, y1 - r, r, 0, 1.5708)
        cr.arc(x0 + r, y1 - r, r, 1.5708, 3.14159)
        cr.arc(x0 + r, y0 + r, r, 3.14159, 4.71239)
        cr.close_path()
        cr.set_source_rgba(0.30, 0.55, 1.0, 0.18)
        cr.fill_preserve()
        cr.set_source_rgba(0.30, 0.55, 1.0, 0.85)
        cr.set_line_width(2.5)
        cr.set_dash([8, 6])
        cr.stroke()
        return True

    def place(self, x, y, w, h):
        self.resize(max(1, w), max(1, h))
        self.move(x, y)
        if not self.get_visible():
            self.show_all()
        try:
            self.input_shape_combine_region(cairo.Region())   # clicks pass through
        except Exception:
            pass
        self.queue_draw()


class GridMode:
    def __init__(self, app):
        self.app = app
        self.highlight = None
        self._settle = None
        self._resize_source = None
        self._last_plan = None
        self._order = list(self.store.settings.get("grid_order") or [])

    @property
    def store(self):
        return self.app.store

    # ----------------------------------------------------------------- state

    @property
    def enabled(self):
        return bool(self.store.settings.get("grid_mode"))

    def set_enabled(self, on):
        self.store.settings["grid_mode"] = bool(on)
        if on:
            self._order = []          # tallest-first on entry, then stable
            self.reflow()
        else:
            self._hide_highlight()
        self.store.save()

    # ---------------------------------------------------------------- region

    def region(self):
        area = util.primary_workarea()
        if area is None:
            return None
        ax, ay, aw, ah = area
        deck = self.app.deck
        if deck is not None and deck.get_visible():
            _dx, dy, _dw, dh = deck.dock_rect()
            clear = dy + dh - ay
            if 0 < clear < ah // 2:
                ay, ah = ay + clear, ah - clear
        gap = self.gap()
        fraction = max(1, min(4, int(self.store.settings.get("grid_fraction", 2))))
        width = aw // fraction
        if self.store.settings.get("grid_side", "left") == "right":
            ax = ax + aw - width
        # keep a gap's worth of space at the region's edges too; the windows
        # already carry a transparent shadow gutter that counts towards it
        pad = max(0, gap - self.app.shadow_margin())
        return ax + pad, ay + pad, width - 2 * pad, ah - 2 * pad

    def gap(self):
        return max(0, int(self.store.settings.get("grid_gap", 16)))

    # ---------------------------------------------------------------- layout

    def _ordered(self, windows, by_size=False):
        """Stable order: remembered order first, newcomers after (tallest
        first, so big notes lead when the mode is first switched on)."""
        by_id = {w.note["id"]: w for w in windows}
        known = [] if by_size else [by_id[i] for i in self._order if i in by_id]
        new = [w for w in windows if w not in known]
        new.sort(key=lambda w: (-w.get_size()[1], -w.get_size()[0], w.note.get("created") or ""))
        return known + new

    def plan(self, windows, dragging=None, by_size=False, pinned=None):
        """{id: (x, y, w, h)} for ``windows``. ``dragging`` is pinned to the
        cell under it and the rest flow around; ``pinned`` ({id: window}) keeps
        those notes in the cell they already occupy."""
        region = self.region()
        if region is None or not windows:
            return {}
        grid = SpanGrid(region, gap=self.gap())
        ordered = self._ordered(windows, by_size)
        items = [(w.note["id"], *self.own_size(w)) for w in ordered]
        pins = {}
        for window in list((pinned or {}).values()) + ([dragging] if dragging else []):
            if window in windows:
                x, y = window.get_position()
                pins[window.note["id"]] = grid.cell_at((x, y), grid.span(*self.own_size(window)))
        placed = grid.pack(items, pinned=pins)
        self._order = grid.reading_order(placed)
        return placed

    @staticmethod
    def own_size(window):
        """The size the user gave a note, as opposed to the cell the grid
        last stretched it into - so switching grid size doesn't drift spans."""
        note = window.note
        if not note.get("own_w") or not note.get("own_h"):
            note["own_w"], note["own_h"] = window.get_size()
        return note["own_w"], note["own_h"]

    @staticmethod
    def remember_own_size(window):
        window.note["own_w"], window.note["own_h"] = window.get_size()

    def _apply(self, placed, skip=None):
        self._last_plan = dict(placed)
        for window in self.app._visible_windows():
            if window is skip:
                continue
            target = placed.get(window.note["id"])
            if target is None:
                continue
            x, y, w, h = (int(v) for v in target)
            window.suppress_docking(800)
            if window.keeps_own_size():
                # collapsed, or the prompt panel is open: only move it
                if (x, y) != tuple(window.get_position()):
                    window.move(x, y)
                window.note.update({"x": x, "y": y})
                continue
            if (w, h) != tuple(window.get_size()):
                window._grid_sized = True
                GLib.timeout_add(SETTLE_MS, window.clear_grid_sized)
            window.place_at(x, y, w, h)
            window.note.update({"x": x, "y": y, "w": w, "h": h})
        self.store.settings["grid_order"] = list(self._order)
        self.store.save()

    def reflow(self):
        if not self.enabled:
            return
        windows = self.app._visible_windows()
        if not windows:
            return
        self._apply(self.plan(windows))

    # ------------------------------------------------------------------ drag

    def on_drag_moved(self, window):
        """Called from a note's configure-event while the user is dragging it."""
        if not self.enabled:
            return
        windows = self.app._visible_windows()
        if window not in windows:
            return
        placed = self.plan(windows, dragging=window)
        self._apply(placed, skip=window)
        x, y, w, h = placed[window.note["id"]]
        inset = self.app.shadow_margin()
        if self.highlight is None:
            self.highlight = SlotHighlight()
        self.highlight.place(int(x) + inset, int(y) + inset, w - 2 * inset, h - 2 * inset)
        if self._settle is not None:
            GLib.source_remove(self._settle)
        self._settle = GLib.timeout_add(SETTLE_MS, self._on_settled, window)

    def _on_settled(self, window):
        self._settle = None
        window.drag_finished()
        self._hide_highlight()
        if not self.enabled or window.note.get("visible", True) is False:
            return False
        placed = self.plan(self.app._visible_windows(), dragging=window)
        self._apply(placed)
        return False

    def on_resized(self, window):
        """A note was resized by hand: re-pack around its new size, keeping it
        in the cell it occupies."""
        if not self.enabled or window._dragging:
            return
        if self._resize_source is not None:
            GLib.source_remove(self._resize_source)
        self._resize_source = GLib.timeout_add(SETTLE_MS, self._on_resize_settled, window)

    def _on_resize_settled(self, window):
        self._resize_source = None
        if not self.enabled:
            return False
        windows = self.app._visible_windows()
        if window in windows:
            self.remember_own_size(window)
            placed = self.plan(windows, pinned={window.note["id"]: window})
            if placed != self._last_plan:       # unchanged = nothing to do, no loop
                self._apply(placed)
        return False

    def cancel_drag(self):
        if self._settle is not None:
            GLib.source_remove(self._settle)
            self._settle = None
        self._hide_highlight()

    def _hide_highlight(self):
        if self.highlight is not None:
            self.highlight.hide()

    def shutdown(self):
        self.cancel_drag()
        if self.highlight is not None:
            self.highlight.destroy()
            self.highlight = None
