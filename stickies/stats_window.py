"""A little desktop widget: how much sticky work got done, and what's left.

Borderless, always on top, draggable like a note; position remembered. Shows
today / this week / streak, a bar chart of the last 14 days of ticked items,
the notes with the most open work, and the next attached dates."""

import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk, Pango  # noqa: E402

from . import analytics, theme, util
from .store import describe_day

CHART_DAYS = 14


class Chart(Gtk.DrawingArea):
    """Bars: ticked items per day, most recent on the right."""

    def __init__(self):
        super().__init__()
        self.set_size_request(252, 74)
        self.days = []
        self.connect("draw", self._draw)

    def update(self, days):
        self.days = days
        self.queue_draw()

    def _draw(self, _widget, cr):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        if not self.days:
            return False
        top = max((count for _d, count in self.days), default=0)
        label_h = 14
        plot_h = height - label_h - 4
        step = width / len(self.days)
        bar_w = max(3.0, step - 5)
        cr.select_font_face("sans", 0, 0)
        cr.set_font_size(9)
        for i, (day, count) in enumerate(self.days):
            x = i * step + (step - bar_w) / 2
            frac = (count / top) if top else 0
            bar = max(2.0, plot_h * frac) if count else 2.0
            y = 4 + (plot_h - bar)
            if count:
                cr.set_source_rgba(0.97, 0.72, 0.25, 0.95)
            else:
                cr.set_source_rgba(1, 1, 1, 0.14)
            r = min(3.0, bar_w / 2)
            cr.new_sub_path()
            cr.arc(x + bar_w - r, y + r, r, -math.pi / 2, 0)
            cr.line_to(x + bar_w, y + bar)
            cr.line_to(x, y + bar)
            cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
            cr.close_path()
            cr.fill()
            if count:
                cr.set_source_rgba(1, 1, 1, 0.85)
                text = str(count)
                ext = cr.text_extents(text)
                cr.move_to(x + bar_w / 2 - ext.width / 2, y - 3)
                cr.show_text(text)
            if i == len(self.days) - 1 or day.weekday() == 0:
                cr.set_source_rgba(1, 1, 1, 0.45)
                text = "now" if i == len(self.days) - 1 else day.strftime("%-d")
                ext = cr.text_extents(text)
                cr.move_to(x + bar_w / 2 - ext.width / 2, height - 3)
                cr.show_text(text)
        return False


class StatsWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.app = app
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_keep_above(True)
        self.stick()
        self.get_style_context().add_class("sticky-window")
        theme.enable_rgba(self)
        self._build()
        self.connect("configure-event", self._on_configure)
        self.refresh()
        self._place()

    @property
    def store(self):
        return self.app.store

    # ------------------------------------------------------------------ build

    def _build(self):
        holder = Gtk.EventBox()
        holder.set_visible_window(False)
        holder.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        holder.connect("button-press-event", self._on_press)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        outer.get_style_context().add_class("stats-widget")
        for setter in ("set_margin_start", "set_margin_end", "set_margin_top", "set_margin_bottom"):
            getattr(outer, setter)(9)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        title = Gtk.Label(label="Work done", xalign=0)
        title.get_style_context().add_class("stats-title")
        head.pack_start(title, True, True, 2)
        close = util.icon_button("window-close-symbolic", "Hide the widget", "×", css=())
        close.get_style_context().add_class("deck-action")
        close.connect("clicked", lambda *_: self.app.set_stats_visible(False))
        head.pack_end(close, False, False, 0)
        outer.pack_start(head, False, False, 0)

        self.numbers = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0, homogeneous=True)
        self._stats = {}
        for key, caption in (("today", "today"), ("week", "this week"), ("streak", "day streak")):
            cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            big = Gtk.Label(label="0")
            big.get_style_context().add_class("stats-big")
            small = Gtk.Label(label=caption)
            small.get_style_context().add_class("stats-small")
            cell.pack_start(big, False, False, 0)
            cell.pack_start(small, False, False, 0)
            self.numbers.pack_start(cell, True, True, 0)
            self._stats[key] = big
        outer.pack_start(self.numbers, False, False, 0)

        self.chart = Chart()
        outer.pack_start(self.chart, False, False, 0)

        self.lists = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        outer.pack_start(self.lists, False, False, 0)

        holder.add(outer)
        self.add(holder)

    def _line(self, text, css="stats-row", tooltip=None):
        label = Gtk.Label(label=text, xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(34)
        label.get_style_context().add_class(css)
        if tooltip:
            label.set_tooltip_text(tooltip)
        self.lists.pack_start(label, False, False, 0)

    # ---------------------------------------------------------------- refresh

    def refresh(self):
        history = self.store.history
        self._stats["today"].set_text(str(analytics.done_today(history)))
        self._stats["week"].set_text(str(analytics.done_this_week(history)))
        self._stats["streak"].set_text(str(analytics.streak(history)))
        self.chart.update(analytics.per_day(history, CHART_DAYS))

        for child in list(self.lists.get_children()):
            self.lists.remove(child)
        work = analytics.open_work(self.store.notes)
        if work:
            self._line("Still open", "stats-heading")
            for note, open_n, total in work[:4]:
                title = (note.get("title") or "").strip() or "untitled"
                self._line("%s   %d of %d left" % (title, open_n, total),
                           tooltip="%d/%d done" % (total - open_n, total))
        events = analytics.upcoming_events(self.store.notes)
        if events:
            self._line("Coming up", "stats-heading")
            for note, event in events:
                title = (note.get("title") or "").strip() or "untitled"
                self._line("%s — %s%s" % (describe_day(event["date"]), title,
                                          "  ·  " + event["label"] if event["label"] else ""))
        if not work and not events and not history:
            self._line("Tick things off your checklists\nand they'll show up here.")
        self.lists.show_all()

    # ------------------------------------------------------------------ shell

    def _on_press(self, _widget, event):
        if event.button == 1:
            self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
            return True
        return False

    def _on_configure(self, *_):
        self.store.settings["stats_position"] = list(self.get_position())
        self.store.save(delay=1.5)
        return False

    def _place(self):
        saved = self.store.settings.get("stats_position")
        area = util.primary_workarea()
        if area is None:
            return
        ax, ay, aw, ah = area
        if saved:
            x, y = int(saved[0]), int(saved[1])
        else:
            x, y = ax + aw - 300, ay + ah - 420
        self.move(max(ax, min(x, ax + aw - 60)), max(ay, min(y, ay + ah - 60)))
