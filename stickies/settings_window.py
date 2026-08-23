"""Settings: Ollama endpoint/model, the system prompt, look, terminal wiring."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import ollama, util
from .store import DEFAULT_SYSTEM_PROMPT, COLORS
from .theme import COLOR_LABELS, THEME_LABELS, THEME_ORDER


class SettingsWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="Settings — Stickies")
        self.app = app
        self.store = app.store
        self.set_default_size(560, 560)
        self._build()
        self.connect("destroy", lambda *_: self.app.forget_settings())
        GLib.idle_add(self._load_models)

    def _build(self):
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("Settings")
        self.set_titlebar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_border_width(14)
        self.add(outer)

        settings = self.store.settings

        # --- Ollama ---
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        outer.pack_start(self._section("Ollama"), False, False, 0)

        self.url_entry = Gtk.Entry()
        self.url_entry.set_text(settings.get("ollama_url", "http://localhost:11434"))
        self.url_entry.set_hexpand(True)
        grid.attach(self._label("Server"), 0, 0, 1, 1)
        grid.attach(self.url_entry, 1, 0, 1, 1)

        refresh = util.icon_button("view-refresh-symbolic", "Reload model list", "⟳", css=())
        refresh.connect("clicked", lambda *_: self._load_models())
        grid.attach(refresh, 2, 0, 1, 1)

        self.model_combo = Gtk.ComboBoxText()
        self.model_combo.set_hexpand(True)
        grid.attach(self._label("Model"), 0, 1, 1, 1)
        grid.attach(self.model_combo, 1, 1, 2, 1)

        self.temp_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.2, 0.05)
        self.temp_scale.set_value(float(settings.get("temperature", 0.4)))
        self.temp_scale.set_digits(2)
        self.temp_scale.set_hexpand(True)
        grid.attach(self._label("Temperature"), 0, 2, 1, 1)
        grid.attach(self.temp_scale, 1, 2, 2, 1)

        self.model_status = Gtk.Label(xalign=0)
        self.model_status.get_style_context().add_class("dim-label-small")
        self.model_status.set_line_wrap(True)
        grid.attach(self.model_status, 1, 3, 2, 1)
        outer.pack_start(grid, False, False, 0)

        # --- system prompt ---
        outer.pack_start(self._section("Prompt-writer instructions"), False, False, 0)
        hint = Gtk.Label(
            label="The system prompt your local model follows when rewriting a note.",
            xalign=0,
        )
        hint.get_style_context().add_class("dim-label-small")
        outer.pack_start(hint, False, False, 0)

        self.sys_view = Gtk.TextView()
        self.sys_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.sys_view.set_left_margin(6)
        self.sys_view.set_right_margin(6)
        self.sys_view.set_top_margin(4)
        self.sys_view.get_buffer().set_text(settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
        scroll = util.scrolled(self.sys_view)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.set_min_content_height(170)
        outer.pack_start(scroll, True, True, 0)

        reset = Gtk.Button(label="Restore default instructions")
        reset.set_halign(Gtk.Align.START)
        reset.connect(
            "clicked",
            lambda *_: self.sys_view.get_buffer().set_text(DEFAULT_SYSTEM_PROMPT),
        )
        outer.pack_start(reset, False, False, 0)

        # --- look & wiring ---
        outer.pack_start(self._section("Notes"), False, False, 0)
        grid2 = Gtk.Grid(column_spacing=10, row_spacing=8)

        self.theme_combo = Gtk.ComboBoxText()
        for name in THEME_ORDER:
            self.theme_combo.append(name, THEME_LABELS[name])
        self.theme_combo.set_active_id(settings.get("theme", "classic"))
        self.theme_combo.set_tooltip_text("Changes every note's paper straight away")
        self.theme_combo.connect(
            "changed", lambda c: self.app.set_theme(c.get_active_id() or "classic")
        )
        grid2.attach(self._label("Theme"), 0, 0, 1, 1)
        grid2.attach(self.theme_combo, 1, 0, 1, 1)

        self.color_combo = Gtk.ComboBoxText()
        for color in COLORS:
            self.color_combo.append(color, COLOR_LABELS[color])
        self.color_combo.set_active_id(settings.get("default_color", "yellow"))
        grid2.attach(self._label("New notes are"), 0, 1, 1, 1)
        grid2.attach(self.color_combo, 1, 1, 1, 1)

        self.scale_spin = Gtk.SpinButton.new_with_range(0.7, 2.0, 0.05)
        self.scale_spin.set_value(float(settings.get("font_scale", 1.0)))
        grid2.attach(self._label("Text size"), 0, 2, 1, 1)
        grid2.attach(self.scale_spin, 1, 2, 1, 1)

        self.deck_check = Gtk.CheckButton(label="Show the deck at the top of the screen")
        self.deck_check.set_active(bool(settings.get("show_deck", True)))
        grid2.attach(self.deck_check, 1, 6, 2, 1)

        self.tabs_spin = Gtk.SpinButton.new_with_range(1, 30, 1)
        self.tabs_spin.set_value(int(settings.get("deck_max_tabs", 8)))
        self.tabs_spin.set_tooltip_text("Older notes fold into a “+N” menu on the deck")
        grid2.attach(self._label("Tabs on the deck"), 0, 7, 1, 1)
        grid2.attach(self.tabs_spin, 1, 7, 1, 1)

        self.gap_spin = Gtk.SpinButton.new_with_range(0, 120, 2)
        self.gap_spin.set_value(int(settings.get("grid_gap", 16)))
        self.gap_spin.set_tooltip_text("Space between notes when you Arrange them into a grid")
        grid2.attach(self._label("Grid spacing (px)"), 0, 8, 1, 1)
        grid2.attach(self.gap_spin, 1, 8, 1, 1)

        self.hand_check = Gtk.CheckButton(label="Handwritten font")
        self.hand_check.set_active(bool(settings.get("handwritten", False)))
        from .theme import available_handwriting

        family = available_handwriting()
        self.hand_check.set_sensitive(family is not None)
        self.hand_check.set_tooltip_text(
            "Uses %s" % family if family
            else "No handwriting font installed. Try: sudo apt install fonts-comic-neue"
        )
        grid2.attach(self.hand_check, 1, 3, 2, 1)

        self.term_entry = Gtk.Entry()
        self.term_entry.set_text(settings.get("terminal", "gnome-terminal"))
        grid2.attach(self._label("Terminal"), 0, 4, 1, 1)
        grid2.attach(self.term_entry, 1, 4, 2, 1)

        self.claude_entry = Gtk.Entry()
        self.claude_entry.set_text(settings.get("claude_cmd", "claude"))
        self.claude_entry.set_hexpand(True)
        grid2.attach(self._label("Claude command"), 0, 5, 1, 1)
        grid2.attach(self.claude_entry, 1, 5, 2, 1)
        outer.pack_start(grid2, False, False, 0)

        # --- actions ---
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Close")
        cancel.connect("clicked", lambda *_: self.destroy())
        save = Gtk.Button(label="Save")
        save.get_style_context().add_class("suggested-action")
        save.connect("clicked", self._on_save)
        actions.pack_start(cancel, False, False, 0)
        actions.pack_start(save, False, False, 0)
        outer.pack_start(actions, False, False, 0)

    @staticmethod
    def _label(text):
        label = Gtk.Label(label=text, xalign=0)
        return label

    @staticmethod
    def _section(text):
        label = Gtk.Label(xalign=0)
        label.set_markup("<b>%s</b>" % GLib.markup_escape_text(text))
        label.set_margin_top(6)
        return label

    def _load_models(self):
        url = self.url_entry.get_text().strip() or "http://localhost:11434"
        try:
            models = ollama.list_models(url)
        except ollama.OllamaError as exc:
            self.model_status.set_text(str(exc))
            return False
        self.model_combo.remove_all()
        for name in models:
            self.model_combo.append(name, name)
        wanted = self.store.settings.get("model") or ollama.pick_default(models)
        self.model_combo.set_active_id(wanted if wanted in models else ollama.pick_default(models))
        self.model_status.set_text("%d model%s available" % (len(models), "" if len(models) == 1 else "s"))
        return False

    def _on_save(self, _button):
        settings = self.store.settings
        settings["ollama_url"] = self.url_entry.get_text().strip() or "http://localhost:11434"
        if self.model_combo.get_active_id():
            settings["model"] = self.model_combo.get_active_id()
        settings["temperature"] = round(self.temp_scale.get_value(), 2)
        settings["system_prompt"] = util.textview_text(self.sys_view)
        settings["theme"] = self.theme_combo.get_active_id() or "classic"
        settings["default_color"] = self.color_combo.get_active_id() or "yellow"
        settings["font_scale"] = round(self.scale_spin.get_value(), 2)
        settings["handwritten"] = self.hand_check.get_active()
        settings["deck_max_tabs"] = int(self.tabs_spin.get_value())
        settings["grid_gap"] = int(self.gap_spin.get_value())
        self.app.set_deck_visible(self.deck_check.get_active())
        settings["terminal"] = self.term_entry.get_text().strip() or "gnome-terminal"
        settings["claude_cmd"] = self.claude_entry.get_text().strip() or "claude"
        self.store.save_now()
        self.app.reload_theme()
        self.destroy()
