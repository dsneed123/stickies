"""A small calendar that drops out of a note: pick a day, give it a label,
and it's attached to the note. Days with something on are marked."""

from datetime import date

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from . import util
from .store import add_event, describe_day, events_on, normalize_events, remove_event


class CalendarPopover(Gtk.Popover):
    def __init__(self, note_window, relative_to):
        super().__init__(relative_to=relative_to)
        self.note_window = note_window
        self.note = note_window.note
        self.set_position(Gtk.PositionType.TOP)
        self.get_style_context().add_class("calendar-popover")
        self._build()
        self.connect("closed", lambda *_: self.note_window.calendar_closed())

    def _build(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(8)

        self.calendar = Gtk.Calendar()
        self.calendar.set_property("show-details", False)
        self.calendar.connect("day-selected", lambda *_: self._refresh_day())
        self.calendar.connect("day-selected-double-click", lambda *_: self._add())
        self.calendar.connect("month-changed", lambda *_: self._mark_month())
        box.pack_start(self.calendar, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("What's on that day? (optional)")
        self.entry.connect("activate", lambda *_: self._add())
        row.pack_start(self.entry, True, True, 0)
        add = Gtk.Button(label="Add")
        add.get_style_context().add_class("suggested-action")
        add.set_tooltip_text("Attach the selected day to this note  (Enter)")
        add.connect("clicked", lambda *_: self._add())
        row.pack_start(add, False, False, 0)
        box.pack_start(row, False, False, 0)

        self.day_heading = Gtk.Label(xalign=0)
        self.day_heading.get_style_context().add_class("dim-label-small")
        box.pack_start(self.day_heading, False, False, 0)

        self.events_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(self.events_box, False, False, 0)

        self.add(box)
        box.show_all()
        self._mark_month()
        self._refresh_day()

    # --------------------------------------------------------------- helpers

    def selected_day(self):
        year, month, day = self.calendar.get_date()
        return date(year, month + 1, day)

    def _mark_month(self):
        year, month, _day = self.calendar.get_date()
        self.calendar.clear_marks()
        for event in normalize_events(self.note.get("events")):
            day = date.fromisoformat(event["date"])
            if day.year == year and day.month == month + 1:
                self.calendar.mark_day(day.day)

    def _refresh_day(self):
        for child in list(self.events_box.get_children()):
            self.events_box.remove(child)
        selected = self.selected_day()
        events = normalize_events(self.note.get("events"))
        today = events_on(self.note, selected)
        others = [e for e in events if e not in today]
        self.day_heading.set_text(
            "%s%s" % (describe_day(selected.isoformat()),
                      "" if today else "  ·  nothing attached, double-click or Add")
        )
        for event in today:
            self.events_box.pack_start(self._event_row(event, show_day=False), False, False, 0)
        if others:
            sep = Gtk.Label(label="Also on this note", xalign=0)
            sep.get_style_context().add_class("dim-label-small")
            sep.set_margin_top(4)
            self.events_box.pack_start(sep, False, False, 0)
            for event in others:
                self.events_box.pack_start(self._event_row(event, show_day=True), False, False, 0)
        self.events_box.show_all()

    def _event_row(self, event, show_day):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        text = event["label"] or "(no label)"
        if show_day:
            text = "%s — %s" % (describe_day(event["date"]), text)
        label = Gtk.Label(label=text, xalign=0)
        label.set_ellipsize(3)   # Pango.EllipsizeMode.END
        label.set_tooltip_text(event["date"])
        if show_day:
            label.set_has_tooltip(True)
            jump = Gtk.EventBox()
            jump.add(label)
            jump.connect("button-press-event", lambda *_, e=event: self._jump_to(e))
            row.pack_start(jump, True, True, 0)
        else:
            row.pack_start(label, True, True, 0)
        remove = util.icon_button("window-close-symbolic", "Remove this date", "×")
        remove.connect("clicked", lambda *_, e=event: self._remove(e))
        row.pack_start(remove, False, False, 0)
        return row

    def _jump_to(self, event):
        day = date.fromisoformat(event["date"])
        self.calendar.select_month(day.month - 1, day.year)
        self.calendar.select_day(day.day)

    # --------------------------------------------------------------- actions

    def _add(self):
        add_event(self.note, self.selected_day(), self.entry.get_text())
        self.entry.set_text("")
        self._changed()

    def _remove(self, event):
        remove_event(self.note, event)
        self._changed()

    def _changed(self):
        self._mark_month()
        self._refresh_day()
        self.note_window.on_events_changed()
