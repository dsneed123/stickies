"""A slim strip pinned to the top of the screen holding every note as a tab.

Click a tab to bring that note down onto the desktop, click again to put it
away. Drag a tab downwards to pull the note out and place it under the cursor.
It stands in for a tray icon, which this desktop has no indicator support for."""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import theme, util
from .theme import THEME_LABELS, THEME_ORDER

TAB_CHARS = 14
PULL_THRESHOLD = 14


class Deck(Gtk.Window):
    def __init__(self, app):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.app = app
        self.store = app.store
        self._pull = None

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_keep_above(True)
        self.stick()
        self.get_style_context().add_class("sticky-window")
        theme.enable_rgba(self)

        self._user_moved = bool(self.store.settings.get("deck_position"))
        self._build()
        self.connect("size-allocate", lambda *_: self._reposition())
        self.connect("configure-event", self._on_configure)

    # ------------------------------------------------------------------ build

    def _build(self):
        holder = Gtk.EventBox()
        holder.set_visible_window(False)
        holder.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        holder.connect("button-press-event", self._on_strip_press)

        self.strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        self.strip.get_style_context().add_class("deck")
        for setter in ("set_margin_start", "set_margin_end", "set_margin_bottom"):
            getattr(self.strip, setter)(9)
        self.strip.set_margin_top(3)   # let the pill float clear of the edge

        self.grip = Gtk.Image.new_from_icon_name("list-drag-handle-symbolic", Gtk.IconSize.MENU)
        self.grip.get_style_context().add_class("deck-grip")
        self.strip.pack_start(self.grip, False, False, 2)

        self.tabs = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        self.strip.pack_start(self.tabs, False, False, 0)

        add_btn = util.icon_button("list-add-symbolic", "New note  (Ctrl+N)", "+", css=())
        add_btn.get_style_context().add_class("deck-action")
        add_btn.connect("clicked", lambda *_: self.app.new_note())
        self.strip.pack_start(add_btn, False, False, 0)

        menu_btn = util.icon_button("open-menu-symbolic", "Menu", "\u2261", css=())
        menu_btn.get_style_context().add_class("deck-action")
        menu_btn.connect("clicked", self._on_menu)
        self.strip.pack_start(menu_btn, False, False, 0)

        holder.add(self.strip)
        self.add(holder)

    # ------------------------------------------------------------------- tabs

    def refresh(self):
        for child in list(self.tabs.get_children()):
            self.tabs.remove(child)
        notes = sorted(self.store.notes, key=lambda n: n.get("created") or "")
        for note in notes:
            self.tabs.pack_start(self._tab(note), False, False, 0)
        self.tabs.show_all()
        GLib.idle_add(self._reposition)

    def _tab(self, note):
        title = (note.get("title") or "").strip() or "untitled"
        short = title if len(title) <= TAB_CHARS else title[: TAB_CHARS - 1] + "…"
        on_screen = note.get("visible", True)

        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_focus_on_click(False)
        ctx = button.get_style_context()
        ctx.add_class("deck-tab")
        ctx.add_class("deck-%s" % note.get("color", "yellow"))
        if not on_screen:
            ctx.add_class("deck-away")

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        # already truncated to TAB_CHARS above; ellipsizing here lets GTK shrink
        # the label to a single character when the strip is tight
        label = Gtk.Label(label=short, xalign=0)
        row.pack_start(label, False, False, 0)
        if note.get("mode") == "list":
            items = [i for i in note.get("items", []) if i.get("text", "").strip()]
            open_n = sum(1 for i in items if not i.get("done"))
            if open_n:
                badge = Gtk.Label(label=str(open_n))
                badge.get_style_context().add_class("deck-badge")
                row.pack_start(badge, False, False, 0)
        button.add(row)

        button.set_tooltip_text(
            "%s\n%s  ·  drag down to pull it out"
            % (title, "click to put it away" if on_screen else "click to bring it down")
        )
        button.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON1_MOTION_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
        )
        button.connect("button-press-event", self._on_tab_press, note)
        button.connect("motion-notify-event", self._on_tab_motion, note)
        button.connect("button-release-event", self._on_tab_release, note)
        return button

    # ------------------------------------------------------------------ input

    def _on_tab_press(self, _widget, event, note):
        if event.button == 1:
            self._pull = (event.x_root, event.y_root, event.time, note, False)
        elif event.button == 3:
            self._tab_menu(event, note)
            return True
        return False

    def _on_tab_motion(self, _widget, event, note):
        if self._pull is None:
            return False
        ox, oy, otime, pulled_note, done = self._pull
        if done or pulled_note is not note:
            return False
        if event.y_root - oy < PULL_THRESHOLD:
            return False
        self._pull = (ox, oy, otime, note, True)
        window = self.app.show_note(note)
        _dx, dy, _dw, dh = self.dock_rect()
        drop_y = max(int(event.y_root), dy + dh + 6)   # clear of the deck itself
        window.suppress_docking(1400)                  # or it snaps straight back
        window.move(int(event.x_root) - 60, drop_y)
        # hand the drag to the window manager so the note follows the cursor
        window.begin_move_drag(1, int(event.x_root), drop_y, event.time)
        self.refresh()
        return True

    def _on_tab_release(self, _widget, event, note):
        pull, self._pull = self._pull, None
        if pull is None or event.button != 1:
            return False
        if pull[4]:          # already pulled out by dragging
            return True
        if note.get("visible", True):
            self.app.hide_note(note)
        else:
            self.app.show_note(note)
        self.refresh()
        return True

    def _on_configure(self, *_):
        if self._user_moved:
            self.store.settings["deck_position"] = list(self.get_position())
            self.store.save(delay=1.5)
        return False

    def _on_strip_press(self, _widget, event):
        if event.button == 1:
            self._user_moved = True
            self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
            return True
        if event.button == 3:
            self._on_menu(None, event)
            return True
        return False

    def _tab_menu(self, event, note):
        menu = Gtk.Menu()
        on_screen = note.get("visible", True)
        menu.append(util.menu_item(
            "Put away" if on_screen else "Bring down",
            lambda *_: (self.app.hide_note(note) if on_screen else self.app.show_note(note),
                        self.refresh()),
        ))
        menu.append(util.menu_item("Write a prompt", lambda *_: self.app.toggle_prompt(note)))
        menu.append(util.separator())
        menu.append(util.menu_item("Delete note…", lambda *_: self._confirm_delete(note)))
        menu.show_all()
        menu.popup_at_pointer(event)

    def _confirm_delete(self, note):
        title = (note.get("title") or "").strip()
        if util.confirm(
            self, "Delete this note?",
            "%s will be removed permanently." % ("“%s”" % title if title else "This note"),
        ):
            self.app.delete_note(note["id"])

    def _on_menu(self, button, event=None):
        menu = Gtk.Menu()
        menu.append(util.menu_item("New note", lambda *_: self.app.new_note()))
        menu.append(util.separator())
        menu.append(util.menu_item("Bring all down", lambda *_: self.app.show_all_notes()))
        menu.append(util.menu_item("Put all away", lambda *_: self.app.hide_all_notes()))
        menu.append(util.separator())
        theme_item = Gtk.MenuItem(label="Theme")
        theme_menu = Gtk.Menu()
        current = self.store.settings.get("theme", "classic")
        for name in THEME_ORDER:
            entry = Gtk.CheckMenuItem(label=THEME_LABELS[name])
            entry.set_draw_as_radio(True)
            entry.set_active(name == current)
            entry.connect("activate", lambda _i, n=name: self.app.set_theme(n))
            theme_menu.append(entry)
        theme_item.set_submenu(theme_menu)
        menu.append(theme_item)
        menu.append(util.separator())
        menu.append(util.menu_item("All notes…", lambda *_: self.app.open_board()))
        menu.append(util.menu_item("Settings…", lambda *_: self.app.open_settings()))
        menu.append(util.menu_item("Hide the deck", lambda *_: self.app.set_deck_visible(False)))
        menu.append(util.separator())
        menu.append(util.menu_item("Quit Stickies", lambda *_: self.app.quit_app()))
        menu.show_all()
        if event is not None:
            menu.popup_at_pointer(event)
        else:
            menu.popup_at_widget(button, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

    # ------------------------------------------------------------- docking

    def dock_rect(self):
        """Screen rectangle a note has to be held over to go back in."""
        x, y = self.get_position()
        width, height = self.get_size()
        return x, y, width, height

    def set_hot(self, on):
        ctx = self.strip.get_style_context()
        if on:
            ctx.add_class("deck-hot")
        else:
            ctx.remove_class("deck-hot")

    # -------------------------------------------------------------- placement

    def _reposition(self):
        """Centre on the primary monitor's top edge, unless dragged elsewhere."""
        saved = self.store.settings.get("deck_position")
        width, _height = self.get_size()
        display = Gdk.Display.get_default()
        if display is None:
            return False
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        area = monitor.get_workarea()
        if saved:
            x, y = int(saved[0]), int(saved[1])
            x = max(area.x, min(x, area.x + area.width - width))
            y = max(area.y, min(y, area.y + area.height - 40))
        else:
            x = area.x + (area.width - width) // 2
            y = area.y
        self.move(x, y)
        return False

    def remember_position(self):
        self.store.settings["deck_position"] = list(self.get_position())
        self.store.save()
