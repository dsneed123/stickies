"""Small GTK helpers shared by the windows."""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402


def icon_button(icon_name, tooltip, fallback="?", size=Gtk.IconSize.MENU, css=("flat",)):
    btn = Gtk.Button()
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.set_focus_on_click(False)
    theme = Gtk.IconTheme.get_default()
    if icon_name and theme.has_icon(icon_name):
        btn.set_image(Gtk.Image.new_from_icon_name(icon_name, size))
        btn.set_always_show_image(True)
    else:
        btn.set_label(fallback)
    if tooltip:
        btn.set_tooltip_text(tooltip)
    for cls in css:
        btn.get_style_context().add_class(cls)
    return btn


def text_button(label, tooltip=None):  # noqa: D401
    btn = Gtk.Button(label=label)
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.set_focus_on_click(False)
    if tooltip:
        btn.set_tooltip_text(tooltip)
    btn.get_style_context().add_class("flat")
    return btn


def menu_item(label, callback, *args):
    item = Gtk.MenuItem(label=label)
    if callback:
        item.connect("activate", callback, *args)
    return item


def check_item(label, active, callback, *args):
    item = Gtk.CheckMenuItem(label=label)
    item.set_active(bool(active))
    if callback:
        item.connect("toggled", callback, *args)
    return item


def separator():
    return Gtk.SeparatorMenuItem()


def copy_to_clipboard(text):
    clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clip.set_text(text, -1)
    clip.store()


def confirm(parent, heading, body, ok_label="Delete", destructive=True):
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.NONE,
        text=heading,
    )
    dialog.format_secondary_text(body)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    ok = dialog.add_button(ok_label, Gtk.ResponseType.OK)
    if destructive:
        ok.get_style_context().add_class("destructive-action")
    dialog.set_default_response(Gtk.ResponseType.CANCEL)
    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.OK


def error_dialog(parent, heading, body):
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.CLOSE,
        text=heading,
    )
    dialog.format_secondary_text(body)
    dialog.run()
    dialog.destroy()


def swatch(color_name, size=16):
    # a Box, not a DrawingArea: GtkBox renders its CSS background for us
    box = Gtk.Box()
    box.set_size_request(size, size)
    box.set_valign(Gtk.Align.CENTER)
    box.set_halign(Gtk.Align.CENTER)
    ctx = box.get_style_context()
    ctx.add_class("swatch")
    ctx.add_class("swatch-%s" % color_name)
    return box


def scrolled(child, hpolicy=Gtk.PolicyType.NEVER, vpolicy=Gtk.PolicyType.AUTOMATIC):
    sw = Gtk.ScrolledWindow()
    sw.set_policy(hpolicy, vpolicy)
    sw.set_overlay_scrolling(True)
    sw.add(child)
    return sw


def textview_text(view):
    buf = view.get_buffer()
    return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)


def primary_workarea():
    """(x, y, width, height) of the primary monitor minus panels, or None."""
    display = Gdk.Display.get_default()
    if display is None:
        return None
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    if monitor is None:
        return None
    area = monitor.get_workarea()
    return area.x, area.y, area.width, area.height


def arrange_submenu(app):
    """'Arrange' menu shared by the deck, the board and the note menu."""
    item = Gtk.MenuItem(label="Arrange")
    sub = Gtk.Menu()
    sub.append(menu_item("Into a grid now", lambda *_: app.arrange_notes()))
    sub.append(menu_item("Into a grid, in the order they were made",
                         lambda *_: app.arrange_notes(by_size=False)))
    restore = menu_item("Restore previous layout", lambda *_: app.restore_layout())
    restore.set_sensitive(bool(getattr(app, "_pre_arrange", None)))
    sub.append(restore)
    sub.append(separator())
    sub.append(check_item("Keep notes snapped to the grid", app.grid.enabled,
                          lambda i: app.grid.set_enabled(i.get_active())))
    side = Gtk.MenuItem(label="Grid takes the")
    side_menu = Gtk.Menu()
    current = app.store.settings.get("grid_side", "left")
    for key, label in (("left", "Left half of the screen"), ("right", "Right half of the screen")):
        entry = Gtk.CheckMenuItem(label=label)
        entry.set_draw_as_radio(True)
        entry.set_active(key == current)
        entry.connect("activate", lambda _i, k=key: app.set_grid_side(k))
        side_menu.append(entry)
    side.set_submenu(side_menu)
    sub.append(side)
    item.set_submenu(sub)
    return item
