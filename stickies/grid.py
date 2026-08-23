"""Snap-to-grid mode: notes live packed in one half of the screen.

While the mode is on every on-screen note is tiled into a rectangle (the
left or right half of the work area, below the deck). Dragging a note shows a
translucent slot where it will land; letting go drops it there and the others
shuffle around it. New, shown and hidden notes reflow the grid."""

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import theme, util
from .layout import arrange_grid

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
        self.store = app.store
        self.highlight = None
        self._settle = None
        self._order = list(self.store.settings.get("grid_order") or [])

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
        half = aw // 2
        if self.store.settings.get("grid_side", "left") == "right":
            ax = ax + aw - half
        inset = self.app.shadow_margin()
        # the gap also pads the region's edges, minus the shadow gutter the
        # windows already carry
        pad = max(0, gap - inset)
        return ax + pad - inset, ay + pad - inset, half - pad + inset, ah - pad + inset

    def gap(self):
        return max(0, int(self.store.settings.get("grid_gap", 16)))

    # ---------------------------------------------------------------- layout

    def _ordered(self, windows):
        """Stable order: remembered order first, newcomers sorted tallest-first."""
        by_id = {w.note["id"]: w for w in windows}
        known = [by_id[i] for i in self._order if i in by_id]
        new = [w for w in windows if w.note["id"] not in self._order]
        new.sort(key=lambda w: (-w.get_size()[1], -w.get_size()[0], w.note.get("created") or ""))
        return known + new

    def _plan(self, windows, dragging=None):
        """{id: (x, y)} for ``windows``; ``dragging`` is slotted nearest its
        current centre rather than at its remembered place."""
        region = self.region()
        if region is None:
            return {}
        others = self._ordered([w for w in windows if w is not dragging])
        boxes = [(w.note["id"], *w.get_size()) for w in others]
        if dragging is None:
            placed = arrange_grid(boxes, region, gap=self.gap())
            self._order = [w.note["id"] for w in others]
            return placed
        dx, dy = dragging.get_position()
        dw, dh = dragging.get_size()
        cx, cy = dx + dw / 2, dy + dh / 2
        best, best_d = len(boxes), None
        for index in range(len(boxes) + 1):
            trial = boxes[:index] + [(dragging.note["id"], dw, dh)] + boxes[index:]
            px, py = arrange_grid(trial, region, gap=self.gap())[dragging.note["id"]]
            d = (px + dw / 2 - cx) ** 2 + (py + dh / 2 - cy) ** 2
            if best_d is None or d < best_d:
                best, best_d = index, d
        trial = boxes[:best] + [(dragging.note["id"], dw, dh)] + boxes[best:]
        placed = arrange_grid(trial, region, gap=self.gap())
        self._order = [b[0] for b in trial]
        return placed

    def _apply(self, placed, skip=None):
        for window in self.app._visible_windows():
            if window is skip:
                continue
            target = placed.get(window.note["id"])
            if target is None:
                continue
            x, y = int(target[0]), int(target[1])
            if (x, y) != tuple(window.get_position()):
                window.suppress_docking(800)
                window.move(x, y)
            window.note["x"], window.note["y"] = x, y
        self.store.settings["grid_order"] = list(self._order)
        self.store.save()

    def reflow(self):
        if not self.enabled:
            return
        windows = self.app._visible_windows()
        if not windows:
            return
        self._apply(self._plan(windows))

    # ------------------------------------------------------------------ drag

    def on_drag_moved(self, window):
        """Called from a note's configure-event while the user is dragging it."""
        if not self.enabled:
            return
        windows = self.app._visible_windows()
        if window not in windows:
            return
        placed = self._plan(windows, dragging=window)
        self._apply(placed, skip=window)
        x, y = placed[window.note["id"]]
        w, h = window.get_size()
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
        placed = self._plan(self.app._visible_windows(), dragging=window)
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
