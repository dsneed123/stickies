"""Application controller: owns the store and every window."""

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, theme
from .board import Board
from .note_window import StickyNote
from .settings_window import SettingsWindow
from .store import Store, new_note

WELCOME_ITEMS = [
    "Drag the ⠿ handle to move me",
    "Enter adds an item",
    "Tick an item to leave it out of the prompt",
    "Hit ✨ to write a Claude prompt",
]


class StickiesApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.store = Store()
        self.windows = {}          # note id -> StickyNote
        self.board = None
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
        opened = 0
        for note in list(self.store.notes):
            if note.get("visible", True):
                self.show_note(note)
                opened += 1
        if opened == 0:
            # everything is hidden - give the user a way back in
            self.open_board()

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
        for window in list(self.windows.values()):
            window.shutdown()
            window.destroy()
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
        )

    # ------------------------------------------------------------------ notes

    def show_note(self, note):
        window = self.windows.get(note["id"])
        if window is None:
            window = StickyNote(self, note)
            self.windows[note["id"]] = window
            self.add_window(window)
        window.present_note()
        self._refresh_board()
        return window

    def hide_note(self, note):
        window = self.windows.get(note["id"])
        if window is not None:
            window.hide_note()
        else:
            note["visible"] = False
            self.store.save()
            self._refresh_board()

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
        if not self.store.notes and self.board is None:
            self.new_note()
        self._refresh_board()

    def show_all_notes(self):
        for note in list(self.store.notes):
            self.show_note(note)

    def hide_all_notes(self):
        for note in list(self.store.notes):
            self.hide_note(note)

    def notify_note_changed(self, _note):
        self._refresh_board()

    # ---------------------------------------------------------------- windows

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
        """Open the note if needed, then drop its ✨ panel down."""
        window = self.show_note(note)
        window.toggle_prompt(force=True)
        return window


def main(argv=None):
    app = StickiesApp()
    try:
        return app.run(argv if argv is not None else sys.argv)
    finally:
        app.store.save_now()
