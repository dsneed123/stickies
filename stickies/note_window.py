"""One sticky note = one borderless, always-on-top window styled like a Post-it."""

import os
import re

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from . import theme, util
from .prompt_panel import PromptPanel
from .store import COLORS, collect_attachments, note_to_markdown
from .theme import COLOR_LABELS

SHADOW_MARGIN = 9  # transparent gutter the drop shadow is painted into

# Rich text lives as (start, end, name) character offsets alongside the plain
# text, so the note stays greppable and converts cleanly to markdown.
FORMAT_TAGS = {
    "bold": {"weight": Pango.Weight.BOLD},
    "italic": {"style": Pango.Style.ITALIC},
    "underline": {"underline": Pango.Underline.SINGLE},
    "strike": {"strikethrough": True},
}

# "  - thing", "3) thing", "12. thing"
LIST_RE = re.compile(r"^(\s*)(?:([-*+•])|(\d+)([.)]))(\s+)(.*)$")
CASCADE = [0]


class ChecklistRow(Gtk.ListBoxRow):
    """A checkbox plus inline, word-wrapping text. Enter starts the next item,
    Backspace on an empty one deletes it."""

    def __init__(self, note_window, item):
        super().__init__()
        self.note_window = note_window
        self.item = item
        self.set_activatable(False)
        self.set_can_focus(False)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box.set_margin_top(1)
        box.set_margin_bottom(1)

        self.check = Gtk.CheckButton()
        self.check.set_active(bool(item.get("done")))
        self.check.set_focus_on_click(False)
        self.check.set_valign(Gtk.Align.START)
        self.check.set_margin_top(2)
        self.check.connect("toggled", self._on_toggled)

        self.view = Gtk.TextView()
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_accepts_tab(False)
        self.view.set_hexpand(True)
        self.view.set_left_margin(0)
        self.view.set_right_margin(0)
        self.view.set_pixels_above_lines(1)
        self.view.set_pixels_below_lines(2)
        self.buffer = self.view.get_buffer()
        self.buffer.set_text(item.get("text", ""))
        self.done_tag = self.buffer.create_tag("done", strikethrough=True)
        self.buffer.connect("changed", self._on_changed)
        self.view.connect("key-press-event", self._on_key)

        self.remove_btn = util.icon_button("window-close-symbolic", "Remove item", "×")
        self.remove_btn.get_style_context().add_class("row-del")
        self.remove_btn.set_valign(Gtk.Align.START)
        self.remove_btn.connect("clicked", lambda *_: self.note_window.remove_row(self))

        box.pack_start(self.check, False, False, 0)
        box.pack_start(self.view, True, True, 0)
        box.pack_end(self.remove_btn, False, False, 0)
        self.add(box)
        self.remove_btn.set_opacity(0.0)
        self.connect("state-flags-changed", self._on_state)
        self._sync_strike()

    def _on_state(self, _widget, _flags):
        hot = bool(self.get_state_flags() & Gtk.StateFlags.PRELIGHT)
        self.remove_btn.set_opacity(0.55 if hot else 0.0)

    # -- text --

    @property
    def text(self):
        return self.buffer.get_text(
            self.buffer.get_start_iter(), self.buffer.get_end_iter(), False
        )

    def focus_text(self, at_end=False):
        self.view.grab_focus()
        it = self.buffer.get_end_iter() if at_end else self.buffer.get_start_iter()
        self.buffer.place_cursor(it)

    def _sync_strike(self):
        start, end = self.buffer.get_bounds()
        self.buffer.remove_tag(self.done_tag, start, end)
        ctx = self.view.get_style_context()
        if self.check.get_active():
            self.buffer.apply_tag(self.done_tag, start, end)
            ctx.add_class("sticky-item-done")
        else:
            ctx.remove_class("sticky-item-done")

    def _on_toggled(self, *_):
        self.item["done"] = self.check.get_active()
        self._sync_strike()
        self.note_window.on_items_changed()

    def _on_changed(self, *_):
        self.item["text"] = self.text
        if self.check.get_active():
            self._sync_strike()
        self.note_window.on_items_changed()

    def _on_key(self, _widget, event):
        key = event.keyval
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        alt = event.state & Gdk.ModifierType.MOD1_MASK
        shift = event.state & Gdk.ModifierType.SHIFT_MASK

        if ctrl and key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self.check.set_active(not self.check.get_active())
            return True
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not shift:
            self.note_window.insert_row_after(self)
            return True
        if alt and key in (Gdk.KEY_Up, Gdk.KEY_Down):
            self.note_window.move_row(self, -1 if key == Gdk.KEY_Up else 1)
            return True
        cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        if key == Gdk.KEY_BackSpace and not self.text:
            self.note_window.remove_row(self, focus_previous=True)
            return True
        if key == Gdk.KEY_Up and cursor.get_line() == 0:
            return self.note_window.focus_sibling(self, -1)
        if key == Gdk.KEY_Down and cursor.get_line() == self.buffer.get_line_count() - 1:
            return self.note_window.focus_sibling(self, 1)
        return False


class StickyNote(Gtk.Window):
    def __init__(self, app, note):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.app = app
        self.store = app.store
        self.note = note
        self._save_source = None
        self._loading = True
        self._rows = []
        self.prompt_panel = None
        self._pre_prompt_size = None
        self._pending_formats = set()
        self._dock_source = None
        self._dock_blocked_until = 0
        self._dragging = False
        self._grid_sized = False   # the grid itself is resizing this window

        self.set_decorated(False)
        self.set_resizable(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_default_size(note.get("w") or 236, note.get("h") or 248)
        self.set_size_request(150, 72)
        self.get_style_context().add_class("sticky-window")
        theme.enable_rgba(self)

        self._build()
        self._apply_color(note.get("color", "yellow"))
        self._apply_mode(note.get("mode", "text"), initial=True)
        self._apply_flags()
        self.update_attachment_badge()
        self._place()

        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_add_uri_targets()
        self.connect("drag-data-received", self._on_drag_data)

        self.connect("configure-event", self._on_configure)
        self.connect("key-press-event", self._on_key)
        self.connect("delete-event", self._on_delete_event)
        self._loading = False

    # ------------------------------------------------------------------ build

    def _build(self):
        self.paper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.paper.get_style_context().add_class("sticky")
        for setter in ("set_margin_start", "set_margin_end", "set_margin_top", "set_margin_bottom"):
            getattr(self.paper, setter)(SHADOW_MARGIN)

        # input-only wrapper: middle-drag moves the note from anywhere on it
        self.root_event = Gtk.EventBox()
        self.root_event.set_visible_window(False)
        self.root_event.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.root_event.connect("button-press-event", self._on_any_press)
        self.root_event.add(self.paper)
        self.add(self.root_event)

        self.paper.pack_start(self._build_header(), False, False, 0)
        self.paper.pack_start(self._build_body(), True, True, 0)
        self.footer_holder = self._build_footer()
        self.paper.pack_start(self.footer_holder, False, False, 0)

        # the prompt panel drops out of the bottom of the note
        self.prompt_revealer = Gtk.Revealer()
        self.prompt_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.prompt_revealer.set_transition_duration(150)
        self.paper.pack_start(self.prompt_revealer, False, False, 0)

        curl = Gtk.Box()
        curl.get_style_context().add_class("sticky-curl")
        self.paper.pack_start(curl, False, False, 0)
        self.curl = curl

    def _build_header(self):
        self.header = Gtk.EventBox()
        self.header.get_style_context().add_class("sticky-header")
        self.header.connect("button-press-event", self._on_header_press)
        self.header.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # full-width grab bar across the top - the adhesive strip of the paper
        self.grip = Gtk.EventBox()
        self.grip.set_visible_window(False)
        self.grip.set_size_request(-1, 16)
        dots = Gtk.Image.new_from_icon_name("list-drag-handle-symbolic", Gtk.IconSize.MENU)
        dots.set_valign(Gtk.Align.CENTER)
        dots.get_style_context().add_class("sticky-grab")
        # a strip of washi tape holding the note up
        tape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tape.get_style_context().add_class("tape")
        tape.set_halign(Gtk.Align.CENTER)
        tape.set_valign(Gtk.Align.CENTER)
        tape.pack_start(dots, True, True, 0)
        self.grip.add(tape)
        self.grip.set_tooltip_text("Drag to move  ·  double-click to roll up")
        self.grip.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.grip.connect("button-press-event", self._on_header_press)
        self.grip.connect("realize", self._set_move_cursor)
        column.pack_start(self.grip, False, False, 0)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)

        self.title_entry = Gtk.Entry()
        self.title_entry.set_has_frame(False)
        self.title_entry.set_placeholder_text("Untitled")
        self.title_entry.set_text(self.note.get("title", ""))
        self.title_entry.set_hexpand(True)
        self.title_entry.get_style_context().add_class("sticky-title")
        self.title_entry.connect("changed", self._on_title_changed)
        self.title_entry.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON1_MOTION_MASK
        )
        self.title_entry.connect("button-press-event", self._on_title_press)
        self.title_entry.connect("motion-notify-event", self._on_title_motion)
        self.title_entry.connect("button-release-event", self._on_title_release)
        self._drag_origin = None
        box.pack_start(self.title_entry, True, True, 0)

        self.attach_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.attach_badge.set_no_show_all(True)
        self.attach_badge.set_valign(Gtk.Align.CENTER)
        self.attach_badge.set_tooltip_text("Files attached as prompt context")
        clip = Gtk.Image.new_from_icon_name("mail-attachment-symbolic", Gtk.IconSize.MENU)
        clip.get_style_context().add_class("sticky-count")
        self.attach_label = Gtk.Label()
        self.attach_label.get_style_context().add_class("sticky-count")
        self.attach_badge.pack_start(clip, False, False, 0)
        self.attach_badge.pack_start(self.attach_label, False, False, 0)
        clip.show()
        self.attach_label.show()
        box.pack_start(self.attach_badge, False, False, 0)

        self.count_label = Gtk.Label()
        self.count_label.get_style_context().add_class("sticky-count")
        self.count_label.set_no_show_all(True)
        box.pack_start(self.count_label, False, False, 0)

        add_btn = util.icon_button("list-add-symbolic", "New note  (Ctrl+N)", "+")
        add_btn.connect("clicked", lambda *_: self.app.new_note(near=self))
        menu_btn = util.icon_button("open-menu-symbolic", "Menu", "≡")
        menu_btn.connect("clicked", self._on_menu_clicked)
        close_btn = util.icon_button(
            "window-close-symbolic", "Hide note  (Ctrl+W)\nThe note is kept - reopen from All Notes", "×"
        )
        close_btn.connect("clicked", lambda *_: self.hide_note())
        for btn in (add_btn, menu_btn, close_btn):
            box.pack_start(btn, False, False, 0)

        column.pack_start(box, False, False, 0)
        self.header.add(column)
        return self.header

    def _build_body(self):
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.body.get_style_context().add_class("sticky-body")

        # plain text
        self.textview = Gtk.TextView()
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.textview.set_left_margin(2)
        self.textview.set_right_margin(2)
        self.textview.set_pixels_above_lines(1)
        self.textview.set_pixels_below_lines(3)
        buf = self.textview.get_buffer()
        for name, props in FORMAT_TAGS.items():
            buf.create_tag(name, **props)
        buf.set_text(self.note.get("text", ""))
        self._load_spans()
        buf.connect("changed", self._on_text_changed)
        buf.connect_after("insert-text", self._on_insert_after)
        self.textview.connect("key-press-event", self._on_text_key)
        self.text_scroll = util.scrolled(self.textview)

        # checklist
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.get_style_context().add_class("sticky-list")
        list_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        list_holder.pack_start(self.list_box, False, False, 0)
        self.add_item_btn = util.text_button("Add item")
        self.add_item_btn.set_halign(Gtk.Align.START)
        self.add_item_btn.connect("clicked", lambda *_: self.append_row(focus=True))
        list_holder.pack_start(self.add_item_btn, False, False, 0)
        self.list_scroll = util.scrolled(list_holder)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.add_named(self.text_scroll, "text")
        self.stack.add_named(self.list_scroll, "list")
        self.body.pack_start(self.stack, True, True, 0)
        return self.body

    def _build_footer(self):
        self.footer_event = Gtk.EventBox()
        self.footer_event.set_visible_window(False)
        self.footer_event.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.footer_event.connect("button-press-event", self._on_header_press)
        self.footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)
        self.footer.get_style_context().add_class("sticky-footer")
        self.footer_event.add(self.footer)

        self.mode_btn = util.icon_button(
            "checkbox-checked-symbolic", "Checklist / plain text  (Ctrl+T)", "\u2611")
        self.mode_btn.connect("clicked", lambda *_: self.toggle_mode())

        self.color_btn = util.icon_button("color-select-symbolic", "Note colour", "\u25cf")
        self.color_btn.connect("clicked", self._on_color_clicked)

        self.attach_btn = util.icon_button(
            "mail-attachment-symbolic",
            "Attach a file as context for this note's prompts", "\u2317")
        self.attach_btn.connect("clicked", self._on_attach_clicked)

        self.prompt_btn = prompt_btn = util.text_button("Prompt")
        prompt_btn.get_style_context().add_class("primary")
        prompt_btn.set_tooltip_text(
            "Turn this note into an optimised Claude prompt with Ollama  (Ctrl+Enter)"
        )
        prompt_btn.connect("clicked", lambda *_: self.toggle_prompt())

        self.format_btn = util.text_button("B", "Formatting  (Ctrl+B / I / U)")
        self.format_btn.get_style_context().add_class("format-b")
        self.format_btn.set_no_show_all(True)  # show_all() must not resurrect it
        self.format_btn.connect("clicked", self._on_format_menu)

        for btn in (self.mode_btn, self.format_btn, self.attach_btn, self.color_btn):
            self.footer.pack_start(btn, False, False, 0)
        self.footer.pack_start(prompt_btn, False, False, 4)

        grip = Gtk.EventBox()
        grip.get_style_context().add_class("sticky-grip")
        grip.add(Gtk.Image.new_from_icon_name("pan-down-symbolic", Gtk.IconSize.MENU))
        grip.set_tooltip_text("Drag to resize")
        grip.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        grip.connect("button-press-event", self._on_grip_press)
        grip.set_valign(Gtk.Align.END)
        grip.connect("realize", self._set_resize_cursor)
        self.footer.pack_end(grip, False, False, 0)
        return self.footer_event

    # ------------------------------------------------------------- appearance

    def _apply_color(self, color):
        ctx = self.get_style_context()
        for name in COLORS:
            ctx.remove_class("sticky-%s" % name)
        ctx.add_class("sticky-%s" % color)
        self.note["color"] = color

    def set_color(self, color):
        self._apply_color(color)
        self.queue_draw()
        self.schedule_save()

    def _apply_flags(self):
        self.set_keep_above(bool(self.note.get("pinned", True)))
        if self.note.get("sticky"):
            self.stick()
        else:
            self.unstick()

    @staticmethod
    def _toggle_class(widget, on):
        ctx = widget.get_style_context()
        if on:
            ctx.add_class("toggled")
        else:
            ctx.remove_class("toggled")

    def _place(self):
        x, y = self.note.get("x"), self.note.get("y")
        if x is None or y is None:
            step = CASCADE[0] % 8
            CASCADE[0] += 1
            x, y = 90 + step * 34, 90 + step * 30
            self.note["x"], self.note["y"] = x, y
        self.move(int(x), int(y))

    # ------------------------------------------------------------------ modes

    def _apply_mode(self, mode, initial=False):
        self.note["mode"] = mode
        is_list = mode == "list"
        self.stack.set_visible_child_name("list" if is_list else "text")
        self._toggle_class(self.mode_btn, is_list)
        if hasattr(self, "format_btn"):
            self.format_btn.set_visible(not is_list)  # formatting is text-mode only
        self.count_label.set_visible(is_list)
        if is_list:
            self._rebuild_rows()
            self._update_count()
        if not initial:
            self.schedule_save()

    def toggle_mode(self):
        if self.note.get("mode") == "list":
            lines = []
            for item in self.note.get("items", []):
                text = item.get("text", "").strip()
                if text:
                    lines.append(("[x] " if item.get("done") else "") + text)
            self.note["text"] = "\n".join(lines)
            self.note["spans"] = []
            self.textview.get_buffer().set_text(self.note["text"])
            self._apply_mode("text")
        else:
            items = []
            for line in util.textview_text(self.textview).splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                done = False
                for marker in ("[x]", "[X]", "- [x]", "- [X]"):
                    if stripped.startswith(marker):
                        done = True
                        stripped = stripped[len(marker):].strip()
                        break
                for bullet in ("- [ ]", "[ ]", "-", "*", "•"):
                    if stripped.startswith(bullet):
                        stripped = stripped[len(bullet):].strip()
                        break
                if stripped:
                    items.append({"text": stripped, "done": done})
            self.note["spans"] = []
            self.note["items"] = items or [{"text": "", "done": False}]
            self._apply_mode("list")
            GLib.idle_add(self._focus_row, 0)

    # ------------------------------------------------------------- check rows

    def _rebuild_rows(self):
        for row in list(self._rows):
            self.list_box.remove(row)
        self._rows = []
        if not self.note.get("items"):
            self.note["items"] = [{"text": "", "done": False}]
        for item in self.note["items"]:
            row = ChecklistRow(self, item)
            self.list_box.add(row)
            self._rows.append(row)
        self.list_box.show_all()

    def _update_count(self):
        items = [i for i in self.note.get("items", []) if i.get("text", "").strip()]
        done = sum(1 for i in items if i.get("done"))
        self.count_label.set_text("%d/%d" % (done, len(items)) if items else "")
        # the unticked items are what the prompt is built from
        open_n = len(items) - done
        if self.note.get("mode") == "list" and open_n:
            self.prompt_btn.set_label("Prompt · %d" % open_n)
        else:
            self.prompt_btn.set_label("Prompt")

    def on_items_changed(self):
        self._update_count()
        self.schedule_save()

    def append_row(self, focus=False):
        item = {"text": "", "done": False}
        self.note.setdefault("items", []).append(item)
        row = ChecklistRow(self, item)
        self.list_box.add(row)
        self._rows.append(row)
        self.list_box.show_all()
        if focus:
            GLib.idle_add(self._focus_row, len(self._rows) - 1)
        self.schedule_save()

    def insert_row_after(self, row):
        index = self._rows.index(row) + 1
        item = {"text": "", "done": False}
        self.note["items"].insert(index, item)
        new_row = ChecklistRow(self, item)
        self.list_box.insert(new_row, index)
        self._rows.insert(index, new_row)
        self.list_box.show_all()
        GLib.idle_add(self._focus_row, index)
        self.schedule_save()

    def remove_row(self, row, focus_previous=False):
        if row not in self._rows:
            return
        index = self._rows.index(row)
        if len(self._rows) == 1:  # never leave an empty list with no way back in
            row.buffer.set_text("")
            row.check.set_active(False)
            return
        self._rows.pop(index)
        self.note["items"].pop(index)
        self.list_box.remove(row)
        target = index - 1 if focus_previous or index >= len(self._rows) else index
        if 0 <= target < len(self._rows):
            GLib.idle_add(self._focus_row, target, True)
        self.on_items_changed()

    def move_row(self, row, delta):
        index = self._rows.index(row)
        target = index + delta
        if not (0 <= target < len(self._rows)):
            return
        self._rows.pop(index)
        self._rows.insert(target, row)
        item = self.note["items"].pop(index)
        self.note["items"].insert(target, item)
        self.list_box.remove(row)
        self.list_box.insert(row, target)
        self.list_box.show_all()
        GLib.idle_add(self._focus_row, target)
        self.schedule_save()

    def focus_sibling(self, row, delta):
        index = self._rows.index(row) + delta
        if 0 <= index < len(self._rows):
            self._focus_row(index, at_end=delta < 0)
            return True
        return False

    def _focus_row(self, index, at_end=False):
        if 0 <= index < len(self._rows):
            self._rows[index].focus_text(at_end=at_end)
        return False

    # ------------------------------------------------------------ persistence

    # ------------------------------------------------------------ formatting

    def _load_spans(self):
        buf = self.textview.get_buffer()
        table = buf.get_tag_table()
        end_offset = buf.get_end_iter().get_offset()
        for span in self.note.get("spans") or []:
            try:
                start, end, name = int(span[0]), int(span[1]), span[2]
            except (TypeError, ValueError, IndexError):
                continue
            tag = table.lookup(name)
            if tag is None or end <= start:
                continue
            start, end = max(0, start), min(end, end_offset)
            if end > start:
                buf.apply_tag(tag, buf.get_iter_at_offset(start), buf.get_iter_at_offset(end))

    def _collect_spans(self):
        """Walk each tag's toggle points and record them as offset ranges."""
        buf = self.textview.get_buffer()
        table = buf.get_tag_table()
        spans = []
        for name in FORMAT_TAGS:
            tag = table.lookup(name)
            if tag is None:
                continue
            it = buf.get_start_iter()
            if not it.has_tag(tag) and not it.forward_to_tag_toggle(tag):
                continue
            while True:
                start = it.get_offset()
                if it.forward_to_tag_toggle(tag):
                    spans.append([start, it.get_offset(), name])
                else:
                    spans.append([start, buf.get_end_iter().get_offset(), name])
                    break
                if not it.forward_to_tag_toggle(tag):
                    break
        return spans

    @staticmethod
    def _range_tagged(start, end, tag):
        it = start.copy()
        if not it.has_tag(tag):
            return False
        return not (it.forward_to_tag_toggle(tag) and it.compare(end) < 0)

    def toggle_format(self, name):
        if self.note.get("mode") == "list":
            return False
        buf = self.textview.get_buffer()
        tag = buf.get_tag_table().lookup(name)
        if tag is None:
            return False
        bounds = buf.get_selection_bounds()
        if bounds:
            start, end = bounds
            if self._range_tagged(start, end, tag):
                buf.remove_tag(tag, start, end)
            else:
                buf.apply_tag(tag, start, end)
            self._on_text_changed(buf)
        else:
            # no selection: arm it for whatever gets typed next
            self._pending_formats.symmetric_difference_update({name})
        return True

    def clear_formatting(self):
        buf = self.textview.get_buffer()
        bounds = buf.get_selection_bounds() or (buf.get_start_iter(), buf.get_end_iter())
        buf.remove_all_tags(*bounds)
        self._pending_formats.clear()
        self._on_text_changed(buf)

    def _on_insert_after(self, buf, location, text, _length):
        if not self._pending_formats or not text:
            return
        start = buf.get_iter_at_offset(max(0, location.get_offset() - len(text)))
        for name in self._pending_formats:
            tag = buf.get_tag_table().lookup(name)
            if tag is not None:
                buf.apply_tag(tag, start, location)

    def apply_list(self, kind):
        """Prefix the selected lines (or the current one) with - or 1. 2. 3."""
        buf = self.textview.get_buffer()
        bounds = buf.get_selection_bounds()
        if bounds:
            start, end = bounds
        else:
            start = buf.get_iter_at_mark(buf.get_insert())
            end = start.copy()
        start.set_line_offset(0)
        if not end.ends_line():
            end.forward_to_line_end()
        lines = buf.get_text(start, end, False).split("\n")
        out, number = [], 1
        for line in lines:
            match = LIST_RE.match(line)
            indent = match.group(1) if match else ""
            body = match.group(6) if match else line.strip()
            if not body.strip():
                out.append(line)
                continue
            if kind == "bullet":
                out.append("%s- %s" % (indent, body))
            else:
                out.append("%s%d. %s" % (indent, number, body))
                number += 1
        buf.delete(start, end)
        buf.insert(start, "\n".join(out))
        return True

    def _continue_list(self):
        """Enter on a list line starts the next bullet / number."""
        buf = self.textview.get_buffer()
        cursor = buf.get_iter_at_mark(buf.get_insert())
        line_start = cursor.copy()
        line_start.set_line_offset(0)
        match = LIST_RE.match(buf.get_text(line_start, cursor, False))
        if not match:
            return False
        indent, bullet, number, sep, space, content = match.groups()
        if not content.strip():
            buf.delete(line_start, cursor)  # empty item: end the list
            return True
        if bullet:
            prefix = "%s%s%s" % (indent, bullet, space)
        else:
            prefix = "%s%d%s%s" % (indent, int(number) + 1, sep, space)
        buf.insert(cursor, "\n" + prefix)
        return True

    def _on_text_key(self, _widget, event):
        key = event.keyval
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        shift = event.state & Gdk.ModifierType.SHIFT_MASK
        if ctrl and not shift:
            if key in (Gdk.KEY_b, Gdk.KEY_B):
                return self.toggle_format("bold")
            if key in (Gdk.KEY_i, Gdk.KEY_I):
                return self.toggle_format("italic")
            if key in (Gdk.KEY_u, Gdk.KEY_U):
                return self.toggle_format("underline")
        if ctrl and shift:
            if key in (Gdk.KEY_x, Gdk.KEY_X):
                return self.toggle_format("strike")
            if key in (Gdk.KEY_seven, Gdk.KEY_ampersand):
                return self.apply_list("number")
            if key in (Gdk.KEY_eight, Gdk.KEY_asterisk):
                return self.apply_list("bullet")
            if key in (Gdk.KEY_space,):
                self.clear_formatting()
                return True
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not shift and not ctrl:
            return self._continue_list()
        return False

    def _format_menu(self):
        menu = Gtk.Menu()
        for name, label, accel in (
            ("bold", "Bold", "Ctrl+B"),
            ("italic", "Italic", "Ctrl+I"),
            ("underline", "Underline", "Ctrl+U"),
            ("strike", "Strikethrough", "Ctrl+Shift+X"),
        ):
            menu.append(util.menu_item(
                "%s   %s" % (label, accel), lambda _i, n=name: self.toggle_format(n)
            ))
        menu.append(util.separator())
        menu.append(util.menu_item("Bullet list   Ctrl+Shift+8",
                                   lambda *_: self.apply_list("bullet")))
        menu.append(util.menu_item("Numbered list   Ctrl+Shift+7",
                                   lambda *_: self.apply_list("number")))
        menu.append(util.separator())
        menu.append(util.menu_item("Clear formatting   Ctrl+Shift+Space",
                                   lambda *_: self.clear_formatting()))
        return menu

    def _on_format_menu(self, button):
        menu = self._format_menu()
        menu.show_all()
        menu.popup_at_widget(button, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.SOUTH_WEST, None)

    def _on_title_changed(self, entry):
        self.note["title"] = entry.get_text()
        self.schedule_save()

    def _on_text_changed(self, buf):
        if self._loading:
            return
        self.note["text"] = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        self.note["spans"] = self._collect_spans()
        self.schedule_save()

    def _on_configure(self, _widget, _event):
        if self._loading:
            return False
        x, y = self.get_position()
        w, h = self.get_size()
        resized = (w, h) != (self.note.get("w"), self.note.get("h"))
        if (x, y, w, h) != (self.note.get("x"), self.note.get("y"),
                            self.note.get("w"), self.note.get("h")):
            self.note.update({"x": x, "y": y, "w": w, "h": h})
            self.store.save(delay=1.5)
        self._check_dock(x, y, w)
        if self._dragging:
            self.app.grid.on_drag_moved(self)
        elif resized and not self._grid_sized:
            if not self.app.grid.enabled:
                self.note["own_w"], self.note["own_h"] = w, h
            self.app.grid.on_resized(self)
        return False

    def begin_user_move(self, button, x_root, y_root, time):
        """Start a window-manager move and remember that the user is dragging,
        so the grid can preview and snap the drop."""
        self._dragging = True
        self.begin_move_drag(button, x_root, y_root, time)

    def drag_finished(self):
        self._dragging = False

    def place_at(self, x, y, w, h):
        """Move and resize in one go, so the window manager clamps the new
        size to the screen rather than the old one."""
        gdk = self.get_window()
        if gdk is not None and self.get_realized():
            self.resize(w, h)            # keep GTK's own idea of the size in step
            gdk.move_resize(x, y, w, h)
        else:
            self.resize(w, h)
            self.move(x, y)

    def clear_grid_sized(self):
        self._grid_sized = False
        return False

    def keeps_own_size(self):
        """True while the grid must not resize this note."""
        return bool(self.note.get("collapsed")) or (
            self.prompt_revealer is not None and self.prompt_revealer.get_reveal_child())

    # ------------------------------------------------------------ deck docking

    def suppress_docking(self, milliseconds):
        self._dock_blocked_until = GLib.get_monotonic_time() + milliseconds * 1000

    def _check_dock(self, x, y, width):
        """Hold a note over the deck for a moment and it goes back in."""
        deck = getattr(self.app, "deck", None)
        if deck is None or not deck.get_visible():
            return self._cancel_dock()
        if GLib.get_monotonic_time() < self._dock_blocked_until:
            return self._cancel_dock()
        dx, dy, dw, dh = deck.dock_rect()
        # only the note's title strip counts, not its whole body
        head_bottom = y + SHADOW_MARGIN + 44
        overlapping = not (x + width < dx or x > dx + dw
                           or head_bottom < dy or y > dy + dh)
        if not overlapping:
            return self._cancel_dock()
        if self._dock_source is None:
            deck.set_hot(True)
            self._dock_source = GLib.timeout_add(420, self._dock_now)

    def _dock_now(self):
        self._dock_source = None
        deck = getattr(self.app, "deck", None)
        if deck is not None:
            deck.set_hot(False)
        self.hide_note()
        return False

    def _cancel_dock(self):
        if self._dock_source is not None:
            GLib.source_remove(self._dock_source)
            self._dock_source = None
            deck = getattr(self.app, "deck", None)
            if deck is not None:
                deck.set_hot(False)

    def schedule_save(self):
        if self._loading:
            return
        self.store.touch(self.note)
        self.app.notify_note_changed(self.note)

    # ------------------------------------------------------------------ input

    def _on_header_press(self, _widget, event):
        if event.type == Gdk.EventType._2BUTTON_PRESS and event.button == 1:
            self.toggle_collapsed()
            return True
        if event.button == 1:
            self.begin_user_move(event.button, int(event.x_root), int(event.y_root), event.time)
            return True
        if event.button == 3:
            self._popup_menu(event)
            return True
        return False

    @staticmethod
    def _set_cursor(widget, name):
        window = widget.get_window()
        if window is not None:
            cursor = Gdk.Cursor.new_from_name(widget.get_display(), name)
            if cursor is not None:
                window.set_cursor(cursor)

    def _set_move_cursor(self, widget):
        self._set_cursor(widget, "grab")

    def _set_resize_cursor(self, widget):
        self._set_cursor(widget, "se-resize")

    def _on_any_press(self, _widget, event):
        if event.button == 2:  # middle-drag moves the note from anywhere
            self.begin_user_move(event.button, int(event.x_root), int(event.y_root), event.time)
            return True
        if event.button == 3:
            self._popup_menu(event)
            return True
        return False

    # Pressing the title still puts the caret where you clicked; only once the
    # pointer travels past the threshold does it turn into a window move.
    DRAG_THRESHOLD = 10

    def _on_title_press(self, _widget, event):
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self._drag_origin = None
            return False
        if event.button == 1:
            self._drag_origin = (event.x_root, event.y_root, event.time)
        return False

    def _on_title_motion(self, _widget, event):
        if self._drag_origin is None:
            return False
        ox, oy, otime = self._drag_origin
        if max(abs(event.x_root - ox), abs(event.y_root - oy)) < self.DRAG_THRESHOLD:
            return False
        self._drag_origin = None
        self.begin_user_move(1, int(ox), int(oy), otime)
        return True

    def _on_title_release(self, *_):
        self._drag_origin = None
        return False

    def _on_grip_press(self, _widget, event):
        if event.button == 1:
            self.begin_resize_drag(
                Gdk.WindowEdge.SOUTH_EAST, event.button,
                int(event.x_root), int(event.y_root), event.time,
            )
            return True
        return False

    def _on_key(self, _widget, event):
        key = event.keyval
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        if not ctrl:
            return False
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.toggle_prompt()
        elif key in (Gdk.KEY_n, Gdk.KEY_N):
            self.app.new_note(near=self)
        elif key in (Gdk.KEY_d, Gdk.KEY_D):
            self.app.duplicate_note(self.note)
        elif key in (Gdk.KEY_g, Gdk.KEY_G):
            self.app.arrange_notes()
        elif key in (Gdk.KEY_t, Gdk.KEY_T):
            self.toggle_mode()
        elif key in (Gdk.KEY_l, Gdk.KEY_L):
            self.app.open_board()
        elif key in (Gdk.KEY_w, Gdk.KEY_W):
            self.hide_note()
        elif key in (Gdk.KEY_q, Gdk.KEY_Q):
            self.app.quit_app()
        elif key in (Gdk.KEY_comma,):
            self.app.open_settings()
        else:
            return False
        return True

    def _on_drag_data(self, _widget, context, _x, _y, data, _info, time):
        paths = []
        for uri in data.get_uris() or []:
            try:
                path, _host = GLib.filename_from_uri(uri)
            except Exception:
                continue
            paths.append(path)
        if paths:
            self.attach_files(paths)
        Gtk.drag_finish(context, bool(paths), False, time)

    def attach_files(self, paths):
        """Drop a README on a note and it becomes context for its prompts."""
        return self.add_attachments(paths)

    def add_attachments(self, paths):
        """Add files, skipping duplicates and directories. -> how many stuck."""
        current = self.note.setdefault("attachments", [])
        added = 0
        for path in paths:
            path = os.path.abspath(os.path.expanduser(path))
            if os.path.isdir(path) or path in current:
                continue
            current.append(path)
            added += 1
        if added:
            self.store.save()
            self.refresh_attachments()
        return added

    def detach(self, path):
        attachments = self.note.get("attachments") or []
        if path in attachments:
            attachments.remove(path)
            self.store.save()
            self.refresh_attachments()

    def refresh_attachments(self):
        self.update_attachment_badge()
        if self.prompt_panel is not None:
            self.prompt_panel.refresh_chips()

    def choose_attachments(self):
        dialog = Gtk.FileChooserDialog(
            title="Attach files to “%s”" % ((self.note.get("title") or "").strip() or "this note"),
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Attach", Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        dialog.set_select_multiple(True)
        text_filter = Gtk.FileFilter()
        text_filter.set_name("Text, markdown and source")
        for pattern in ("*.md", "*.markdown", "*.txt", "*.rst", "*.json", "*.yaml",
                        "*.yml", "*.toml", "*.ini", "*.cfg", "*.env", "*.py", "*.js",
                        "*.ts", "*.tsx", "*.go", "*.rs", "*.java", "*.rb", "*.c",
                        "*.h", "*.cpp", "*.sh", "*.sql", "Makefile", "Dockerfile"):
            text_filter.add_pattern(pattern)
        dialog.add_filter(text_filter)
        any_filter = Gtk.FileFilter()
        any_filter.set_name("All files")
        any_filter.add_pattern("*")
        dialog.add_filter(any_filter)
        existing = self.note.get("attachments") or []
        dialog.set_current_folder(
            os.path.dirname(existing[-1]) if existing else os.path.expanduser("~")
        )
        added = 0
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            added = self.add_attachments(dialog.get_filenames())
        dialog.destroy()
        return added

    def _on_attach_clicked(self, button):
        """No files yet? Go straight to the picker. Otherwise show what's on."""
        attachments = self.note.get("attachments") or []
        if not attachments:
            self.choose_attachments()
            return
        menu = Gtk.Menu()
        menu.append(util.menu_item("Attach a file…", lambda *_: self.choose_attachments()))
        menu.append(util.separator())
        heading = Gtk.MenuItem(label="Attached — click to detach")
        heading.set_sensitive(False)
        menu.append(heading)
        for item in collect_attachments(self.note):
            label = item["name"] if not item["error"] else "%s  (%s)" % (item["name"], item["error"])
            entry = util.menu_item("   %s   ✕" % label, lambda _i, p=item["path"]: self.detach(p))
            entry.set_tooltip_text(item["path"])
            menu.append(entry)
        menu.show_all()
        menu.popup_at_widget(button, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.SOUTH_WEST, None)

    def update_attachment_badge(self):
        count = len(self.note.get("attachments") or [])
        self.attach_label.set_text(str(count) if count else "")
        self.attach_badge.set_visible(bool(count))

    def _on_delete_event(self, *_):
        self.hide_note()
        return True

    # ------------------------------------------------------------------ menus

    def _on_menu_clicked(self, button):
        self._popup_menu(None, button)

    def _on_color_clicked(self, button):
        menu = Gtk.Menu()
        for color in COLORS:
            item = Gtk.MenuItem()
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.pack_start(util.swatch(color), False, False, 0)
            row.pack_start(Gtk.Label(label=COLOR_LABELS[color], xalign=0), True, True, 0)
            if color == self.note.get("color"):
                row.pack_end(
                    Gtk.Image.new_from_icon_name("object-select-symbolic", Gtk.IconSize.MENU),
                    False, False, 0,
                )
            item.add(row)
            item.connect("activate", lambda _i, c=color: self.set_color(c))
            menu.append(item)
        menu.show_all()
        menu.popup_at_widget(button, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.SOUTH_WEST, None)

    def _color_submenu(self):
        menu = Gtk.Menu()
        for color in COLORS:
            item = Gtk.MenuItem()
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.pack_start(util.swatch(color), False, False, 0)
            row.pack_start(Gtk.Label(label=COLOR_LABELS[color], xalign=0), True, True, 0)
            item.add(row)
            item.connect("activate", lambda _i, c=color: self.set_color(c))
            menu.append(item)
        return menu

    def _popup_menu(self, event, widget=None):
        menu = Gtk.Menu()
        add = menu.append
        add(util.menu_item("New note", lambda *_: self.app.new_note(near=self)))
        add(util.menu_item("Duplicate note", lambda *_: self.app.duplicate_note(self.note)))
        add(util.separator())
        add(util.menu_item(
            "Plain text" if self.note.get("mode") == "list" else "Turn into checklist",
            lambda *_: self.toggle_mode(),
        ))
        if self.note.get("mode") != "list":
            format_item = Gtk.MenuItem(label="Format")
            format_item.set_submenu(self._format_menu())
            add(format_item)
        color_item = Gtk.MenuItem(label="Colour")
        color_item.set_submenu(self._color_submenu())
        add(color_item)
        add(util.separator())
        add(util.check_item("Keep on top", self.note.get("pinned"),
                            lambda i: self.set_pinned(i.get_active())))
        add(util.check_item("Show on all workspaces", self.note.get("sticky"),
                            lambda i: self.set_sticky(i.get_active())))
        add(util.separator())
        add(util.menu_item("Prompt panel",
                           lambda *_: self.toggle_prompt()))
        add(util.menu_item("Attach a file as context…", lambda *_: self._menu_attach()))
        add(util.menu_item("Copy note text",
                           lambda *_: util.copy_to_clipboard(note_to_markdown(self.note))))
        add(util.separator())
        add(util.arrange_submenu(self.app))
        add(util.menu_item("All notes…", lambda *_: self.app.open_board()))
        add(util.menu_item("Settings…", lambda *_: self.app.open_settings()))
        add(util.separator())
        add(util.menu_item("Hide this note", lambda *_: self.hide_note()))
        add(util.menu_item("Delete note…", lambda *_: self.delete_note()))
        add(util.separator())
        add(util.menu_item("Quit Stickies", lambda *_: self.app.quit_app()))
        menu.show_all()
        if event is not None:
            menu.popup_at_pointer(event)
        else:
            menu.popup_at_widget(widget, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

    # ---------------------------------------------------------------- actions

    def _menu_attach(self):
        self.choose_attachments()

    def toggle_prompt(self, force=None):
        """Slide the prompt panel in or out of the bottom of the note."""
        if self.prompt_panel is None:
            self.prompt_panel = PromptPanel(self.app, self.note, self)
            self.prompt_revealer.add(self.prompt_panel)
            self.prompt_revealer.show_all()
        opening = (not self.prompt_revealer.get_reveal_child()) if force is None else force
        if opening:
            self._pre_prompt_size = self.get_size()
            width, height = self._pre_prompt_size
            # the note body keeps a slice; the panel takes the rest
            self.paper.child_set_property(self.body, "expand", False)
            self.paper.child_set_property(self.prompt_revealer, "expand", True)
            self.body.set_size_request(-1, min(height - 40, 130))
            self.resize(max(width, 400), max(height, 480))
            self.prompt_revealer.set_reveal_child(True)
            self.prompt_panel.on_shown()
        else:
            self.prompt_revealer.set_reveal_child(False)
            self.paper.child_set_property(self.body, "expand", True)
            self.paper.child_set_property(self.prompt_revealer, "expand", False)
            self.body.set_size_request(-1, -1)
            if self._pre_prompt_size:
                self.resize(*self._pre_prompt_size)
        self._toggle_class(self.prompt_btn, opening)
        return opening

    def set_pinned(self, on):
        self.note["pinned"] = bool(on)
        self._apply_flags()
        self.schedule_save()

    def toggle_pinned(self):
        self.set_pinned(not self.note.get("pinned", True))

    def set_sticky(self, on):
        self.note["sticky"] = bool(on)
        self._apply_flags()
        self.schedule_save()

    def toggle_collapsed(self):
        collapsed = not self.note.get("collapsed")
        self.note["collapsed"] = collapsed
        if collapsed and self.prompt_revealer.get_reveal_child():
            self.toggle_prompt(force=False)
        self.body.set_visible(not collapsed)
        self.footer_holder.set_visible(not collapsed)
        self.prompt_revealer.set_visible(not collapsed)
        self.curl.set_visible(not collapsed)
        if collapsed:
            self.resize(self.note.get("w") or 236, 1)
        else:
            self.resize(self.note.get("w") or 236, self.note.get("h") or 248)
        self.schedule_save()

    def apply_collapsed_state(self):
        if self.note.get("collapsed"):
            self.body.set_visible(False)
            self.footer_holder.set_visible(False)
            self.curl.set_visible(False)
            self.resize(self.note.get("w") or 236, 1)

    def shutdown(self):
        self._cancel_dock()
        self._dragging = False
        if self.prompt_panel is not None:
            self.prompt_panel.shutdown()

    def hide_note(self):
        if self.prompt_panel is not None:
            self.prompt_panel.shutdown()
        self.note["visible"] = False
        self._dragging = False
        self.app.grid.cancel_drag()
        self.store.save()
        self.hide()
        self.app.notify_note_changed(self.note)

    def delete_note(self):
        title = (self.note.get("title") or "").strip()
        if util.confirm(
            self, "Delete this note?",
            "%s will be removed permanently." % ("“%s”" % title if title else "This note"),
        ):
            self.app.delete_note(self.note["id"])

    def refresh_from_note(self):
        """Re-read the model after an external change (board rename, etc.)."""
        self._loading = True
        self.title_entry.set_text(self.note.get("title", ""))
        if self.note.get("mode") == "list":
            self._rebuild_rows()
            self._update_count()
        else:
            self.textview.get_buffer().set_text(self.note.get("text", ""))
        self._apply_color(self.note.get("color", "yellow"))
        self._apply_flags()
        self._loading = False

    def present_note(self):
        self.note["visible"] = True
        self.show_all()
        is_list = self.note.get("mode") == "list"
        self.count_label.set_visible(is_list)
        self.format_btn.set_visible(not is_list)
        self.update_attachment_badge()
        self.stack.set_visible_child_name("list" if is_list else "text")
        self.apply_collapsed_state()
        self.present()
        self.store.save()
