"""The prompt panel that drops down out of a note.

Same job the old separate window did - take the note's open items, stream them
through Ollama, hand back a Claude-ready prompt - but living inside the sticky
so you never leave it."""

import os
import re
import shlex
import subprocess
import tempfile
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from . import ollama, util
from .store import (AUTO_MODE, CLASSIFIER_SYSTEM, MODE_ORDER, MODES,
                    OPEN_QUESTIONS_MARKER, classifier_message,
                    collect_attachments, item_counts, note_to_markdown)


def build_user_message(note, mode_key, extra="", include_done=False, attachments=None):
    mode = MODES.get(mode_key, MODES["task"])
    source = note_to_markdown(note, include_done=include_done, marks=include_done)
    parts = ["APPROACH — %s. %s" % (mode["label"], mode["instruction"])]
    if note.get("mode") == "list" and not include_done:
        parts.append(
            "Every line under NOTES is still outstanding. Ticked-off items were "
            "already handled and have been removed, so do not ask about them."
        )
    parts += ["", "--- NOTES ---", source or "(the note is empty)", "--- END NOTES ---"]

    usable = [a for a in (attachments or []) if a.get("text")]
    if usable:
        parts += [
            "",
            "The files below describe the project as it stands today. They are "
            "background, not the task - the task is only what the NOTES say. Use "
            "them to fill in Context, to get names and paths right, and to avoid "
            "asking about anything they already answer.",
            "",
            "--- ATTACHED PROJECT FILES ---",
        ]
        for item in usable:
            parts += ["", "### %s" % item["name"], item["text"]]
        parts += ["", "--- END ATTACHED PROJECT FILES ---"]
    if extra.strip():
        parts += [
            "",
            "--- EXTRA CONTEXT FROM THE USER (authoritative - fold it in) ---",
            extra.strip(),
            "--- END EXTRA CONTEXT ---",
        ]
    parts += ["", "Now output only the finished prompt."]
    return "\n".join(parts)


class PromptPanel(Gtk.Box):
    def __init__(self, app, note, note_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.app = app
        self.store = app.store
        self.note = note
        self.note_window = note_window
        self.job = None
        self._timer_id = None
        self._elapsed = 0
        self._models = []
        self._splitter = None
        self._questions = ""
        self._chosen_mode = None
        self._classifying = False
        self.get_style_context().add_class("prompt-panel")
        self._build()

    # ------------------------------------------------------------------ build

    def _build(self):
        # ---- row 1: what and with what ----
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)

        self.mode_btn = util.text_button("Task ▾", "What kind of prompt to write")
        self.mode_btn.connect("clicked", self._on_mode_menu)
        top.pack_start(self.mode_btn, False, False, 0)

        self.model_btn = util.text_button("model ▾", "Which Ollama model writes it")
        self.model_btn.connect("clicked", self._on_model_menu)
        top.pack_start(self.model_btn, False, False, 0)

        self.run_btn = util.text_button("Generate")
        self.run_btn.get_style_context().add_class("primary")
        self.run_btn.connect("clicked", lambda *_: self.start())
        top.pack_end(self.run_btn, False, False, 0)

        self.stop_btn = util.text_button("Stop")
        self.stop_btn.set_no_show_all(True)
        self.stop_btn.connect("clicked", lambda *_: self.stop())
        top.pack_end(self.stop_btn, False, False, 0)

        self.spinner = Gtk.Spinner()
        top.pack_end(self.spinner, False, False, 2)
        self.pack_start(top, False, False, 0)

        # ---- row 2: scope ----
        scope = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.scope_label = Gtk.Label(xalign=0)
        self.scope_label.get_style_context().add_class("panel-note")
        self.scope_label.set_ellipsize(Pango.EllipsizeMode.END)
        scope.pack_start(self.scope_label, True, True, 0)

        self.include_done = Gtk.CheckButton(label="ticked too")
        self.include_done.get_style_context().add_class("panel-note")
        self.include_done.set_tooltip_text(
            "A ticked box means handled, so it stays out of the prompt. "
            "Turn this on to send the whole list."
        )
        self.include_done.set_active(bool(self.note.get("prompt_include_done")))
        self.include_done.connect("toggled", self._on_include_toggled)
        scope.pack_end(self.include_done, False, False, 0)
        self.pack_start(scope, False, False, 0)

        # ---- row 3: one dropdown for everything the user wants to add ----
        self.thoughts_btn = util.text_button(
            "▸ Extra thoughts",
            "Anything the note leaves out - repo, stack, constraints, or answers "
            "to what the model asked. Saved with the note.",
        )
        self.thoughts_btn.get_style_context().add_class("panel-note")
        self.thoughts_btn.set_halign(Gtk.Align.START)
        self.thoughts_btn.connect("clicked", self._toggle_thoughts)
        self.pack_start(self.thoughts_btn, False, False, 0)

        thoughts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        # what the model wanted to know, if anything - never part of the prompt
        self.questions_label = Gtk.Label(xalign=0)
        self.questions_label.set_line_wrap(True)
        self.questions_label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.questions_label.get_style_context().add_class("panel-note")
        self.questions_label.set_no_show_all(True)
        thoughts.pack_start(self.questions_label, False, False, 0)

        self.context_view = Gtk.TextView()
        self.context_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.context_view.set_left_margin(4)
        self.context_view.set_right_margin(4)
        self.context_view.set_top_margin(3)
        self.context_view.set_pixels_below_lines(2)
        self.context_view.get_buffer().set_text(self.note.get("prompt_context", "") or "")
        self.context_view.get_buffer().connect("changed", self._on_context_changed)
        self.context_scroll = util.scrolled(self.context_view)
        self.context_scroll.get_style_context().add_class("prompt-field")
        self.context_scroll.set_min_content_height(58)
        thoughts.pack_start(self.context_scroll, False, False, 0)
        self._context_placeholder()

        attach_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        attach_btn = util.text_button(
            "Attach file",
            "Attach a README, spec or config so the model knows the project. "
            "Re-read from disk on every run — you can also drop files onto the note.",
        )
        attach_btn.get_style_context().add_class("panel-note")
        attach_btn.connect("clicked", self._on_attach)
        attach_row.pack_start(attach_btn, False, False, 0)
        thoughts.pack_start(attach_row, False, False, 0)

        self.chips = Gtk.FlowBox()
        self.chips.set_selection_mode(Gtk.SelectionMode.NONE)
        self.chips.set_max_children_per_line(4)
        self.chips.set_row_spacing(0)
        self.chips.set_column_spacing(2)
        self.chips.set_homogeneous(False)
        thoughts.pack_start(self.chips, False, False, 0)

        self.thoughts_revealer = Gtk.Revealer()
        self.thoughts_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.thoughts_revealer.set_transition_duration(140)
        self.thoughts_revealer.add(thoughts)
        self.pack_start(self.thoughts_revealer, False, False, 0)

        # ---- row 4: the result ----
        self.result_view = Gtk.TextView()
        self.result_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.result_view.set_left_margin(5)
        self.result_view.set_right_margin(5)
        self.result_view.set_top_margin(5)
        self.result_view.set_pixels_below_lines(2)
        self.result_view.get_style_context().add_class("prompt-result")
        self.result_scroll = util.scrolled(self.result_view)
        self.result_scroll.get_style_context().add_class("prompt-field")
        self.result_scroll.set_min_content_height(110)
        self.pack_start(self.result_scroll, True, True, 0)

        # ---- row 5: status + actions ----
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.status = Gtk.Label(label="", xalign=0)
        self.status.get_style_context().add_class("panel-note")
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        bottom.pack_start(self.status, True, True, 0)

        self.copy_btn = util.text_button("Copy", "Copy the prompt to the clipboard")
        self.copy_btn.connect("clicked", self._on_copy)
        save_btn = util.text_button("Save", "Keep the prompt as its own note")
        save_btn.connect("clicked", self._on_save_note)
        self.claude_btn = util.text_button("→ Claude", "Open a terminal running Claude Code with this prompt")
        self.claude_btn.get_style_context().add_class("primary")
        self.claude_btn.connect("clicked", self._on_open_claude)
        for btn in (self.copy_btn, save_btn, self.claude_btn):
            bottom.pack_start(btn, False, False, 0)
        self.pack_start(bottom, False, False, 0)

    # ------------------------------------------------------------- appearance

    def _context_placeholder(self):
        """GtkTextView has no placeholder, so fake one."""
        buf = self.context_view.get_buffer()

        def sync(*_):
            empty = buf.get_char_count() == 0
            focused = self.context_view.has_focus()
            ctx = self.context_view.get_style_context()
            if empty and not focused:
                ctx.add_class("shows-placeholder")
            else:
                ctx.remove_class("shows-placeholder")
            self.context_view.queue_draw()

        def draw(widget, cr):
            if widget.get_buffer().get_char_count() or widget.has_focus():
                return False
            layout = widget.create_pango_layout("extra context…")
            cr.move_to(6, 4)
            style = widget.get_style_context()
            colour = style.get_color(style.get_state())
            cr.set_source_rgba(colour.red, colour.green, colour.blue, 0.40)
            PangoCairo.show_layout(cr, layout)
            return False

        buf.connect("changed", sync)
        self.context_view.connect("focus-in-event", lambda *_: sync())
        self.context_view.connect("focus-out-event", lambda *_: sync())
        self.context_view.connect_after("draw", draw)

    def on_shown(self):
        """Called each time the panel is revealed."""
        self.refresh_chips()
        if not self._models:
            GLib.idle_add(self._load_models)

    def refresh_scope(self):
        include = self.include_done.get_active()
        if self.note.get("mode") == "list":
            open_n, done_n = item_counts(self.note)
            sent = open_n + done_n if include else open_n
            text = "%d item%s" % (sent, "" if sent == 1 else "s")
            if done_n and not include:
                text += "  ·  %d ticked left out" % done_n
            self.scope_label.set_text(text + self._attachment_suffix())
            self.include_done.set_sensitive(done_n > 0)
        else:
            self.scope_label.set_text("whole note" + self._attachment_suffix())
            self.include_done.set_sensitive(False)

    def _attachment_suffix(self):
        count = len(self.note.get("attachments") or [])
        return "  ·  %d file%s" % (count, "" if count == 1 else "s") if count else ""

    def _on_include_toggled(self, _btn):
        self.note["prompt_include_done"] = self.include_done.get_active()
        self.store.save()
        self.refresh_scope()

    def _on_context_changed(self, buf):
        self.note["prompt_context"] = buf.get_text(
            buf.get_start_iter(), buf.get_end_iter(), False
        )
        self.store.save(delay=1.5)

    @property
    def context_text(self):
        return util.textview_text(self.context_view)

    # ------------------------------------------------------ extra thoughts

    @property
    def questions_text(self):
        return self._normalise_questions(self._questions)

    @staticmethod
    def _normalise_questions(raw):
        """Models are inconsistent about bullets - some emit '- - thing'.
        Render one clean '- ' per line regardless."""
        lines = []
        for line in (raw or "").strip().splitlines():
            line = line.strip()
            if not line:
                continue
            line = re.sub(r"^(?:[-*•]\s+)+", "", line)
            line = re.sub(r"^\d+[.)]\s+", "", line)
            if line:
                lines.append("- " + line)
        return "\n".join(lines)

    def open_thoughts(self):
        self._toggle_thoughts(force=True)

    def _toggle_thoughts(self, _button=None, force=None):
        showing = (not self.thoughts_revealer.get_reveal_child()) if force is None else force
        self.thoughts_revealer.set_reveal_child(showing)
        self._label_thoughts(showing)
        if showing:
            GLib.idle_add(self.context_view.grab_focus)

    def _label_thoughts(self, showing=None):
        if showing is None:
            showing = self.thoughts_revealer.get_reveal_child()
        count = len([l for l in self.questions_text.splitlines() if l.strip()])
        suffix = "  ·  %d question%s" % (count, "" if count == 1 else "s") if count else ""
        self.thoughts_btn.set_label(("▾ " if showing else "▸ ") + "Extra thoughts" + suffix)

    def _clear_questions(self):
        self._questions = ""
        self.questions_label.set_visible(False)
        self._label_thoughts()

    def _show_questions(self):
        text = self.questions_text
        lines = [l for l in text.splitlines() if l.strip()]
        bare = re.sub(r"^-\s*", "", lines[0]).strip().lower().rstrip(" .") if lines else ""
        if not lines or (len(lines) == 1 and
                         bare in ("none", "n/a", "nothing", "no open questions")):
            self._clear_questions()
            return
        self.questions_label.set_markup(
            "<span size='small'>%s</span>\n%s"
            % ("THE MODEL ASKED", GLib.markup_escape_text(text))
        )
        self.questions_label.set_visible(True)
        self._label_thoughts()

    def _settle_questions(self):
        """Catch models that ignored the marker and wrote the section inline."""
        if not self.questions_text:
            body = self.result_text
            match = re.search(
                r"(?im)^[ \t]*#{0,4}[ \t]*\**open[ \t]+questions\**[ \t]*:?[ \t]*$", body
            )
            if match is None:
                match = re.search(
                    r"(?im)^[ \t]*\**open[ \t]+questions\**[ \t]*:[ \t]*(?=\S)", body
                )
            if match is not None:
                self._questions = body[match.end():].strip()
                self.result_view.get_buffer().set_text(body[: match.start()].rstrip())
        self._show_questions()

    # -------------------------------------------------------------- attachments

    def attach(self, paths):
        return self.note_window.add_attachments(paths)

    def detach(self, path):
        self.note_window.detach(path)

    def refresh_attachments(self):
        self.note_window.refresh_attachments()

    def refresh_chips(self):
        for child in list(self.chips.get_children()):
            self.chips.remove(child)
        for item in collect_attachments(self.note):
            label = item["name"]
            tooltip = item["path"]
            if item["error"]:
                label = "! %s" % item["name"]
                tooltip += "\n%s" % item["error"]
            else:
                tooltip += "\n%s characters of context" % f"{len(item['text']):,}"
            tooltip += "\nClick to detach"
            chip = util.text_button(label + "   ✕", tooltip)
            chip.get_style_context().add_class("panel-note")
            chip.connect("clicked", lambda _b, p=item["path"]: self.detach(p))
            self.chips.add(chip)
        self.chips.show_all()
        self.refresh_scope()

    def _on_attach(self, _button):
        self.note_window.choose_attachments()

    # ------------------------------------------------------------------ menus

    def _on_mode_menu(self, button):
        menu = Gtk.Menu()
        current = self.store.settings.get("last_mode") or AUTO_MODE
        auto = Gtk.CheckMenuItem(label="Auto — let the model pick")
        auto.set_draw_as_radio(True)
        auto.set_active(current == AUTO_MODE)
        auto.connect("activate", lambda _i: self._set_mode(AUTO_MODE))
        menu.append(auto)
        menu.append(Gtk.SeparatorMenuItem())
        for key in MODE_ORDER:
            item = Gtk.CheckMenuItem(label=MODES[key]["label"])
            item.set_draw_as_radio(True)
            item.set_active(key == current)
            item.set_tooltip_text(MODES[key]["when"].capitalize())
            item.connect("activate", lambda _i, k=key: self._set_mode(k))
            menu.append(item)
        menu.show_all()
        menu.popup_at_widget(button, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.SOUTH_WEST, None)

    def _set_mode(self, key):
        self.store.settings["last_mode"] = key
        self.store.save()
        self._chosen_mode = None
        self._sync_mode_label()

    def _sync_mode_label(self):
        key = self.store.settings.get("last_mode") or AUTO_MODE
        if key == AUTO_MODE:
            picked = self._chosen_mode
            label = "Auto · %s" % MODES[picked]["short"] if picked else "Auto"
        else:
            label = MODES.get(key, MODES["task"])["short"]
        self.mode_btn.set_label("%s ▾" % label)

    def _on_model_menu(self, button):
        menu = Gtk.Menu()
        if not self._models:
            item = Gtk.MenuItem(label="No models found — is Ollama running?")
            item.set_sensitive(False)
            menu.append(item)
        current = self.store.settings.get("model")
        for name in self._models:
            item = Gtk.CheckMenuItem(label=name)
            item.set_draw_as_radio(True)
            item.set_active(name == current)
            item.connect("activate", lambda _i, n=name: self._set_model(n))
            menu.append(item)
        menu.show_all()
        menu.popup_at_widget(button, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.SOUTH_WEST, None)

    def _set_model(self, name):
        self.store.settings["model"] = name
        self.store.save()
        self.model_btn.set_label("%s ▾" % name)

    def _load_models(self):
        base = self.store.settings.get("ollama_url", "http://localhost:11434")
        try:
            self._models = ollama.list_models(base)
        except ollama.OllamaError as exc:
            self._set_status(str(exc).replace("\n", " "), error=True)
            self.model_btn.set_label("no model")
            return False
        wanted = self.store.settings.get("model") or ollama.pick_default(self._models)
        if wanted not in self._models:
            wanted = ollama.pick_default(self._models)
        self.store.settings["model"] = wanted
        self.model_btn.set_label("%s ▾" % wanted)
        self._sync_mode_label()
        self._set_status("ready")
        return False

    # -------------------------------------------------------------------- run

    def start(self):
        if self.job is not None:
            self.job.cancel()
        model = self.store.settings.get("model")
        if not model:
            self._set_status("No Ollama model available.", error=True)
            return
        mode_key = self.store.settings.get("last_mode") or AUTO_MODE

        self.result_view.get_buffer().set_text("")
        self._clear_questions()
        self._splitter = ollama.MarkerSplitter(OPEN_QUESTIONS_MARKER)
        self._elapsed = 0
        self.spinner.show()
        self.spinner.start()
        self.stop_btn.set_visible(True)
        self.run_btn.set_sensitive(False)
        self._set_status("writing…")
        if self._timer_id:
            GLib.source_remove(self._timer_id)
        self._timer_id = GLib.timeout_add_seconds(1, self._tick)

        if mode_key == AUTO_MODE:
            self._chosen_mode = None
            self._sync_mode_label()
            self._classifying = True
            self._set_status("choosing an approach…")
            threading.Thread(target=self._classify, args=(model,), daemon=True).start()
        else:
            self._launch(mode_key, model)

    def _classify(self, model):
        """Ask the model which approach fits, then generate with it."""
        settings = self.store.settings
        source = note_to_markdown(
            self.note, include_done=self.include_done.get_active(), marks=False
        )
        key = "task"
        try:
            answer = ollama.chat_once(
                settings.get("ollama_url", "http://localhost:11434"), model,
                CLASSIFIER_SYSTEM, classifier_message(source, self.context_text),
            )
            key = self._match_mode(answer)
        except ollama.OllamaError:
            pass          # unreachable server surfaces on the generate call
        except Exception:
            pass          # a bad classification must never block the real work
        GLib.idle_add(self._classified, key, model)

    @staticmethod
    def _match_mode(answer):
        text = (answer or "").strip().lower()
        for key in MODE_ORDER:
            if text == key:
                return key
        for key in MODE_ORDER:
            if re.search(r"\b%s\b" % key, text):
                return key
        return "task"

    def _classified(self, key, model):
        self._classifying = False
        self._chosen_mode = key
        self._sync_mode_label()
        self._launch(key, model)
        return False

    def _launch(self, mode_key, model):
        settings = self.store.settings
        approach = MODES.get(mode_key, MODES["task"])["label"]
        self._set_status("writing a %s prompt…" % approach.lower())
        self.job = ollama.StreamJob(
            settings.get("ollama_url", "http://localhost:11434"),
            model,
            settings.get("system_prompt", ""),
            build_user_message(
                self.note, mode_key, self.context_text,
                self.include_done.get_active(), collect_attachments(self.note),
            ),
            settings.get("temperature", 0.4),
        )
        job = self.job
        job.start(
            on_chunk=lambda v, t: GLib.idle_add(self._append, job, v),
            on_done=lambda info: GLib.idle_add(self._finish, job, info),
            on_error=lambda msg: GLib.idle_add(self._fail, job, msg),
        )

    def _tick(self):
        self._elapsed += 1
        if self._classifying:
            self._set_status("choosing an approach…  %ds" % self._elapsed)
        else:
            key = self._chosen_mode or self.store.settings.get("last_mode") or "task"
            approach = MODES.get(key, MODES["task"])["label"]
            self._set_status("writing a %s prompt…  %ds" % (approach.lower(), self._elapsed))
        return True

    def stop(self):
        if self.job is not None:
            self.job.cancel()
            self.job = None
        self._idle_ui()
        self._set_status("stopped")

    def _append(self, job, visible):
        if job is not self.job or not visible:
            return False
        prompt_part, questions_part = (
            self._splitter.feed(visible) if self._splitter else (visible, "")
        )
        if prompt_part:
            buf = self.result_view.get_buffer()
            buf.insert(buf.get_end_iter(), prompt_part)
            adj = self.result_scroll.get_vadjustment()
            if adj.get_value() + adj.get_page_size() >= adj.get_upper() - 50:
                GLib.idle_add(lambda: adj.set_value(adj.get_upper()) or False)
        if questions_part:
            self._questions += questions_part
            self._label_thoughts()
        return False

    def _finish(self, job, info):
        if job is not self.job:
            return False
        if self._splitter is not None:
            rest_prompt, rest_questions = self._splitter.flush()
            if rest_prompt or rest_questions:
                self._append(job, "")
                if rest_prompt:
                    buf = self.result_view.get_buffer()
                    buf.insert(buf.get_end_iter(), rest_prompt)
                if rest_questions:
                    self._questions += rest_questions
        self._settle_questions()
        self._idle_ui()
        bits = []
        if info.get("eval_count"):
            bits.append("%d tok" % info["eval_count"])
        if info.get("total_duration"):
            bits.append("%.1fs" % (info["total_duration"] / 1e9))
        status = "done" + ("  ·  " + "  ·  ".join(bits) if bits else "")
        if self.questions_text:
            status += "  ·  the model has questions — see Extra thoughts"
        self._set_status(status)
        self.job = None
        return False

    def _fail(self, job, message):
        if job is not self.job:
            return False
        self._idle_ui()
        self._set_status(message.replace("\n", " "), error=True)
        if not self.result_text:
            self.result_view.get_buffer().set_text(message)
        self.job = None
        return False

    def _idle_ui(self):
        self.spinner.stop()
        self.spinner.hide()
        self.stop_btn.set_visible(False)
        self.run_btn.set_sensitive(True)
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _set_status(self, text, error=False):
        self.status.set_text(text)
        ctx = self.status.get_style_context()
        if error:
            ctx.add_class("error")
        else:
            ctx.remove_class("error")

    # ---------------------------------------------------------------- actions

    @property
    def result_text(self):
        return util.textview_text(self.result_view).strip()

    def _on_copy(self, button):
        text = self.result_text
        if not text:
            return
        util.copy_to_clipboard(text)
        button.set_label("copied ✓")
        GLib.timeout_add_seconds(2, lambda: button.set_label("Copy") or False)

    def _on_save_note(self, _button):
        text = self.result_text
        if not text:
            return
        title = (self.note.get("title") or "Note").strip()
        note = self.store.add()
        note.update({"title": "Prompt: %s" % title, "text": text,
                     "color": "blue", "mode": "text"})
        self.store.save()
        self.app.show_note(note)

    def _on_open_claude(self, _button):
        text = self.result_text
        if not text:
            return
        util.copy_to_clipboard(text)
        settings = self.store.settings
        terminal = settings.get("terminal", "gnome-terminal")
        claude_cmd = settings.get("claude_cmd", "claude")
        fd, path = tempfile.mkstemp(prefix="stickies-prompt-", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        inner = '%s "$(cat %s)"; rm -f %s; exec $SHELL' % (
            claude_cmd, shlex.quote(path), shlex.quote(path)
        )
        argv = ([terminal, "--", "bash", "-lc", inner] if "gnome-terminal" in terminal
                else [terminal, "-e", "bash", "-lc", inner])
        try:
            subprocess.Popen(argv, cwd=os.path.expanduser("~"))
            self._set_status("launched %s — prompt also copied" % claude_cmd)
        except FileNotFoundError:
            util.error_dialog(
                self.note_window, "Couldn't launch the terminal",
                "'%s' was not found. The prompt is on your clipboard - paste it into "
                "Claude Code yourself, or set a different terminal in Settings." % terminal,
            )

    def shutdown(self):
        if self.job is not None:
            self.job.cancel()
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
