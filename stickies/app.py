"""Application controller: owns the store and every window."""

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, theme, util
from .board import Board
from .deck import Deck
from .grid import GridMode
from .note_window import SHADOW_MARGIN, StickyNote
from .settings_window import SettingsWindow
from .store import Store, new_note

WELCOME_ITEMS = [
    "Drag the ⠿ handle to move me",
    "Enter adds an item",
    "Tick an item to leave it out of the prompt",
    "Hit Prompt to write a Claude prompt",
]


class StickiesApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.store = Store()
        self.windows = {}          # note id -> StickyNote
        self._pre_arrange = None   # {id: (x, y)} before the last "Arrange"
        self.grid = GridMode(self)
        self.board = None
        self.deck = None
        self.settings_window = None
        self.add_main_option(
            "new", ord("n"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
            "Create a new note and exit", None,
        )

    # ------------------------------------------------------------- lifecycle

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.reload_theme()

    def do_command_line(self, command_line):
        options = command_line.get_options_dict().end().unpack()
        self.activate()
        if options.get("new"):
            self.new_note()
        return 0

    def do_activate(self):
        if not self.store.notes:
            self._create_welcome_note()
        if self.store.settings.get("show_deck", True):
            self.open_deck()
        opened = 0
        for note in list(self.store.notes):
            if note.get("visible", True):
                self.show_note(note)
                opened += 1
        if opened == 0 and self.deck is None:
            # everything is hidden and there is no deck - give a way back in
            self.open_board()
        self._refresh_deck()

    def _create_welcome_note(self):
        note = new_note(color=self.store.settings.get("default_color", "yellow"))
        note.update(
            {
                "title": "Welcome 👋",
                "mode": "list",
                "items": [{"text": t, "done": False} for t in WELCOME_ITEMS],
                "x": 120,
                "y": 120,
                "w": 236,
                "h": 268,
            }
        )
        self.store.add(note)

    def quit_app(self):
        self.store.save_now()
        self.grid.shutdown()
        for window in list(self.windows.values()):
            window.shutdown()
            window.destroy()
        if self.deck:
            self.deck.destroy()
        if self.board:
            self.board.destroy()
        if self.settings_window:
            self.settings_window.destroy()
        self.quit()

    def reload_theme(self):
        settings = self.store.settings
        theme.install(
            font_scale=settings.get("font_scale", 1.0),
            handwritten=settings.get("handwritten", False),
            theme=settings.get("theme", "classic"),
        )

    # ------------------------------------------------------------------ notes

    def show_note(self, note):
        window = self.windows.get(note["id"])
        if window is None:
            window = StickyNote(self, note)
            self.windows[note["id"]] = window
            self.add_window(window)
        window.present_note()
        self.grid.reflow()
        self._refresh_board()
        self._refresh_deck()
        return window

    def hide_note(self, note):
        window = self.windows.get(note["id"])
        if window is not None:
            window.hide_note()
        else:
            note["visible"] = False
            self.store.save()
            self._refresh_board()
        self.grid.reflow()
        self._refresh_deck()

    def new_note(self, near=None):
        settings = self.store.settings
        note = new_note(color=settings.get("default_color", "yellow"))
        if near is not None:
            try:
                x, y = near.get_position()
                note["x"], note["y"] = x + 30, y + 30
            except Exception:
                pass
        self.store.add(note)
        window = self.show_note(note)
        GLib.idle_add(window.title_entry.grab_focus)
        return note

    def duplicate_note(self, note):
        copy = self.store.duplicate(note["id"])
        if copy is not None:
            self.show_note(copy)
        return copy

    def delete_note(self, note_id):
        window = self.windows.pop(note_id, None)
        if window is not None:
            window.shutdown()
            self.remove_window(window)
            window.destroy()
        self.store.remove(note_id)
        self.grid.reflow()
        if not self.store.notes and self.board is None and self.deck is None:
            self.new_note()
        self._refresh_board()
        self._refresh_deck()

    def show_all_notes(self):
        for note in list(self.store.notes):
            self.show_note(note)

    def hide_all_notes(self):
        for note in list(self.store.notes):
            self.hide_note(note)

    # ---------------------------------------------------------------- arrange

    def _visible_windows(self):
        return [w for w in self.windows.values()
                if w.get_visible() and w.note.get("visible", True)]

    @staticmethod
    def shadow_margin():
        return SHADOW_MARGIN

    def arrange_notes(self, by_size=True):
        """Fit every on-screen note into equal cells in the grid region."""
        windows = self._visible_windows()
        if not windows:
            return
        self._pre_arrange = {w.note["id"]: (w.note.get("x"), w.note.get("y"),
                                             w.note.get("w"), w.note.get("h")) for w in windows}
        placed = self.grid.plan(windows, by_size=by_size)
        self.grid._apply(placed)

    def set_grid_fraction(self, fraction):
        self.store.settings["grid_fraction"] = int(fraction)
        self.store.save()
        if self.grid.enabled:
            self.grid.reflow()
        else:
            self.arrange_notes()

    def set_grid_side(self, side):
        self.store.settings["grid_side"] = side
        self.store.save()
        if self.grid.enabled:
            self.grid.reflow()
        else:
            self.arrange_notes()

    def restore_layout(self):
        snapshot, self._pre_arrange = self._pre_arrange, None
        if not snapshot:
            return
        for note_id, (x, y, w, h) in snapshot.items():
            window = self.windows.get(note_id)
            if window is None or x is None or y is None:
                continue
            window.suppress_docking(1500)
            if w and h:
                window.resize(int(w), int(h))
                window.note["w"], window.note["h"] = int(w), int(h)
            window.move(int(x), int(y))
            window.note["x"], window.note["y"] = int(x), int(y)
        self.store.save()

    def notify_note_changed(self, _note):
        self.grid.reflow()
        self._refresh_board()
        self._refresh_deck()

    # ---------------------------------------------------------------- windows

    def open_deck(self):
        if self.deck is None:
            self.deck = Deck(self)
            self.add_window(self.deck)
        self.deck.refresh()
        self.deck.show_all()
        self.deck.present()
        return self.deck

    def set_theme(self, name):
        self.store.settings["theme"] = name
        self.store.save()
        self.reload_theme()

    def set_deck_visible(self, on):
        self.store.settings["show_deck"] = bool(on)
        self.store.save()
        if on:
            self.open_deck()
        elif self.deck is not None:
            deck, self.deck = self.deck, None
            self.remove_window(deck)
            deck.destroy()
            if not any(n.get("visible", True) for n in self.store.notes):
                self.open_board()

    def _refresh_deck(self):
        if self.deck is not None:
            GLib.idle_add(self.deck.refresh)

    def open_board(self):
        if self.board is None:
            self.board = Board(self)
            self.add_window(self.board)
        self.board.refresh()
        self.board.show_all()
        self.board.present()
        return self.board

    def forget_board(self):
        self.board = None

    def _refresh_board(self):
        if self.board is not None:
            GLib.idle_add(self.board.refresh)

    def open_settings(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self)
            self.add_window(self.settings_window)
        self.settings_window.show_all()
        self.settings_window.present()
        return self.settings_window

    def forget_settings(self):
        self.settings_window = None

    def toggle_prompt(self, note):
        """Open the note if needed, then drop its prompt panel down."""
        window = self.show_note(note)
        window.toggle_prompt(force=True)
        return window


def main(argv=None):
    app = StickiesApp()
    try:
        return app.run(argv if argv is not None else sys.argv)
    finally:
        app.store.save_now()
