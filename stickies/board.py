"""'All notes' - find, show, hide and delete every note including hidden ones."""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk, Pango  # noqa: E402

from . import util
from .store import describe_day, next_event, note_to_markdown
from .theme import COLOR_LABELS


class Board(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="All notes — Stickies")
        self.app = app
        self.store = app.store
        self.set_default_size(400, 500)
        self._query = ""
        self._build()
        self.connect("destroy", lambda *_: self.app.forget_board())
        self.refresh()

    def _build(self):
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("All notes")
        new_btn = Gtk.Button(label="New note")
        new_btn.get_style_context().add_class("suggested-action")
        new_btn.connect("clicked", lambda *_: self.app.new_note())
        header.pack_start(new_btn)

        menu_btn = util.icon_button("open-menu-symbolic", "Menu", "≡", css=())
        menu_btn.connect("clicked", self._on_menu)
        header.pack_end(menu_btn)
        self.set_titlebar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)

        search = Gtk.SearchEntry()
        search.set_placeholder_text("Search titles and contents")
        search.set_margin_top(8)
        search.set_margin_bottom(8)
        search.set_margin_start(10)
        search.set_margin_end(10)
        search.connect("search-changed", self._on_search)
        outer.pack_start(search, False, False, 0)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.set_placeholder(self._placeholder())
        outer.pack_start(util.scrolled(self.listbox), True, True, 0)

        self.status = Gtk.Label(xalign=0)
        self.status.get_style_context().add_class("dim-label-small")
        self.status.set_margin_start(12)
        self.status.set_margin_top(6)
        self.status.set_margin_bottom(8)
        outer.pack_start(self.status, False, False, 0)

    def _placeholder(self):
        label = Gtk.Label(label="No notes yet.\nHit “New note” to stick one on the screen.")
        label.set_justify(Gtk.Justification.CENTER)
        label.get_style_context().add_class("dim-label")
        label.set_margin_top(40)
        label.show()
        return label

    def _on_search(self, entry):
        self._query = entry.get_text().strip().lower()
        self.refresh()

    def _on_menu(self, button):
        menu = Gtk.Menu()
        menu.append(util.menu_item("Show all notes", lambda *_: self.app.show_all_notes()))
        menu.append(util.menu_item("Hide all notes", lambda *_: self.app.hide_all_notes()))
        menu.append(util.separator())
        menu.append(util.arrange_submenu(self.app))
        menu.append(util.separator())
        menu.append(util.menu_item("Settings…", lambda *_: self.app.open_settings()))
        menu.append(util.separator())
        menu.append(util.menu_item("Quit Stickies", lambda *_: self.app.quit_app()))
        menu.show_all()
        menu.popup_at_widget(button, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

    # ------------------------------------------------------------------ rows

    def refresh(self):
        for child in list(self.listbox.get_children()):
            self.listbox.remove(child)
        notes = sorted(self.store.notes, key=lambda n: n.get("updated") or "", reverse=True)
        shown = 0
        for note in notes:
            if self._query and self._query not in note_to_markdown(note).lower():
                continue
            self.listbox.add(self._row(note))
            shown += 1
        self.listbox.show_all()
        total = len(self.store.notes)
        visible = sum(1 for n in self.store.notes if n.get("visible", True))
        self.status.set_text(
            "%d note%s · %d on screen%s"
            % (total, "" if total == 1 else "s", visible,
               "  ·  showing %d match%s" % (shown, "" if shown == 1 else "es") if self._query else "")
        )

    def _row(self, note):
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_border_width(9)

        chip = util.swatch(note.get("color", "yellow"), size=14)
        chip.set_valign(Gtk.Align.START)
        chip.set_margin_top(3)
        chip.set_tooltip_text(COLOR_LABELS.get(note.get("color", "yellow"), ""))
        box.pack_start(chip, False, False, 0)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = (note.get("title") or "").strip() or "Untitled"
        title_label = Gtk.Label(label=title, xalign=0)
        title_label.set_ellipsize(Pango.EllipsizeMode.END)
        title_label.get_style_context().add_class("board-title")
        text_box.pack_start(title_label, False, False, 0)

        preview = Gtk.Label(label=self._preview(note), xalign=0)
        preview.set_ellipsize(Pango.EllipsizeMode.END)
        preview.set_lines(2)
        preview.set_line_wrap(True)
        preview.get_style_context().add_class("board-preview")
        text_box.pack_start(preview, False, False, 0)
        box.pack_start(text_box, True, True, 0)

        on_screen = note.get("visible", True)
        toggle = util.icon_button(
            "window-close-symbolic" if on_screen else "window-restore-symbolic",
            "Hide from screen" if on_screen else "Show on screen",
            "×" if on_screen else "▣", css=(),
        )
        toggle.connect("clicked", lambda *_, n=note: self._toggle(n))

        prompt_btn = util.icon_button("starred-symbolic", "Write a Claude prompt from this note", "*", css=())
        prompt_btn.connect("clicked", lambda *_, n=note: self.app.toggle_prompt(n))

        delete = util.icon_button("user-trash-symbolic", "Delete note", "🗑", css=())
        delete.connect("clicked", lambda *_, n=note: self._delete(n))

        for btn in (prompt_btn, toggle, delete):
            btn.set_valign(Gtk.Align.CENTER)
            box.pack_start(btn, False, False, 0)

        row.add(box)
        return row

    def _preview(self, note):
        soon = next_event(note)
        prefix = ""
        if soon is not None:
            prefix = "\U0001f4c5 %s%s  ·  " % (describe_day(soon["date"]),
                                             " " + soon["label"] if soon["label"] else "")
        return prefix + self._body_preview(note)

    def _body_preview(self, note):
        if note.get("mode") == "list":
            items = [i for i in note.get("items", []) if i.get("text", "").strip()]
            done = sum(1 for i in items if i.get("done"))
            head = "  ·  ".join(i["text"].strip() for i in items[:3]) or "empty checklist"
            return "%d/%d done — %s" % (done, len(items), head)
        body = " ".join((note.get("text") or "").split())
        return body or "empty note"

    def _toggle(self, note):
        if note.get("visible", True):
            self.app.hide_note(note)
        else:
            self.app.show_note(note)
        self.refresh()

    def _delete(self, note):
        title = (note.get("title") or "").strip()
        if util.confirm(
            self, "Delete this note?",
            "%s will be removed permanently." % ("“%s”" % title if title else "This note"),
        ):
            self.app.delete_note(note["id"])
