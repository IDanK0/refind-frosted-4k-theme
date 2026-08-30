#!/usr/bin/env python3
"""Graphical picker for the boot menu background (GTK4 / libadwaita).

Interface strings go through gettext, so the window follows the system
language. Translations live in po/ and are compiled into locale/.
"""
import gettext, glob, json, os, shutil, subprocess, sys, tempfile, threading
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio

HERE   = os.path.dirname(os.path.abspath(__file__))
LIB    = os.path.join(HERE, "library")
CACHE  = os.path.join(GLib.get_user_cache_dir(), "refind-background")
DOMAIN = "refind-background"
APP_ID = "io.github.idank0.RefindBackground"

_ = gettext.translation(DOMAIN, os.path.join(HERE, "locale"), fallback=True).gettext

sys.path.insert(0, HERE)
import build as B


def catalogue():
    """Library entries first, then anything dropped in library/custom/."""
    cfg = json.load(open(os.path.join(LIB, "library.json")))
    entries = [{**b, "path": os.path.join(HERE, b["file"]), "custom": False}
               for b in cfg["backgrounds"]]
    for p in sorted(glob.glob(os.path.join(LIB, "custom", "*"))):
        if p.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp")):
            entries.append({"slug": os.path.splitext(os.path.basename(p))[0],
                            "name": os.path.basename(p), "path": p, "custom": True,
                            "licence": _("yours"), "luminance": None,
                            "suggested_darken": None})
    return cfg, entries


def thumbnails(entries):
    """Library thumbnails are sliced out of the contact sheet, so the grid
    already shows the theme and appears instantly. Custom photos get a plain
    crop; the Preview button renders the real thing anyway."""
    os.makedirs(CACHE, exist_ok=True)
    from PIL import Image
    sheet_path = os.path.join(LIB, "preview-sheet.jpg")
    sheet = Image.open(sheet_path) if os.path.exists(sheet_path) else None
    n_lib = sum(1 for e in entries if not e["custom"])
    for i, e in enumerate(entries):
        dst = os.path.join(CACHE, f"{e['slug']}.png")
        e["thumb"] = dst
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(e["path"]):
            continue
        if not e["custom"] and sheet is not None and i < n_lib:
            x, y = (i % 2) * 960, (i // 2) * 602 + 62
            sheet.crop((x, y, x + 960, y + 540)).resize((384, 216), Image.LANCZOS).save(dst)
        else:
            im = Image.open(e["path"]).convert("RGB"); w, h = im.size
            if w / h > 16 / 9:
                nw = int(h * 16 / 9); im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
            else:
                nh = int(w * 9 / 16); im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
            im.resize((384, 216), Image.LANCZOS).save(dst)


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=_("Boot Menu Background"),
                         default_width=1020, default_height=760)
        self.cfg, self.entries = catalogue()
        self.selected = 0
        self.busy = False

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toasts.set_child(root)

        hb = Adw.HeaderBar()
        hb.set_title_widget(Adw.WindowTitle(
            title=_("Boot Menu Background"),
            subtitle=_("pick one, or add a photo of your own")))
        add = Gtk.Button(icon_name="list-add-symbolic",
                         tooltip_text=_("Add a photo of your own"))
        add.connect("clicked", self.on_add)
        hb.pack_start(add)
        root.append(hb)

        sw = Gtk.ScrolledWindow(vexpand=True)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.SINGLE,
                                homogeneous=True, column_spacing=14, row_spacing=14,
                                max_children_per_line=3, min_children_per_line=2,
                                margin_top=18, margin_bottom=18,
                                margin_start=18, margin_end=18)
        self.flow.connect("selected-children-changed", self.on_select)
        sw.set_child(self.flow)
        root.append(sw)
        self.fill()

        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      margin_top=6, margin_bottom=16, margin_start=18, margin_end=18)
        group = Adw.PreferencesGroup()
        row = Adw.ActionRow(
            title=_("Automatic dimming"),
            subtitle=_("Dim the photo just enough for the glass and the labels to read"))
        self.auto = Gtk.Switch(active=str(self.cfg.get("default_darken")) == "auto",
                               valign=Gtk.Align.CENTER)
        self.auto.connect("state-set", lambda *_a: (self.sync_slider(), False)[1])
        row.add_suffix(self.auto); row.set_activatable_widget(self.auto)
        group.add(row)

        self.manual_row = Adw.ActionRow(title=_("Dim by"))
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.scale.set_size_request(320, -1)
        self.scale.set_draw_value(True)
        self.scale.set_value_pos(Gtk.PositionType.RIGHT)
        d = self.cfg.get("default_darken")
        self.scale.set_value(0 if str(d) == "auto" else int(d))
        self.manual_row.add_suffix(self.scale)
        group.add(self.manual_row)

        row = Adw.ActionRow(
            title=_("Match colours to the photo"),
            subtitle=_("Draw the logos, labels and glass in the picture's own colour, "
                       "instead of Windows blue and Ubuntu orange"))
        self.tint = Gtk.Switch(active=int(self.cfg.get("default_tint", 100)) > 0,
                               valign=Gtk.Align.CENTER)
        row.add_suffix(self.tint); row.set_activatable_widget(self.tint)
        group.add(row)
        bar.append(group)

        actions = Gtk.Box(spacing=10, halign=Gtk.Align.END)
        self.b_prev = Gtk.Button(label=_("Preview"))
        self.b_prev.connect("clicked", lambda *_a: self.run(False))
        self.b_apply = Gtk.Button(label=_("Apply"))
        self.b_apply.add_css_class("suggested-action")
        self.b_apply.connect("clicked", lambda *_a: self.run(True))
        self.spinner = Gtk.Spinner()
        self.status = Gtk.Label(label="", xalign=0)
        for w in (self.status, self.spinner, self.b_prev, self.b_apply):
            actions.append(w)
        bar.append(actions)
        root.append(bar)
        self.sync_slider()

    # ---------------------------------------------------------------- view
    def fill(self):
        thumbnails(self.entries)
        while (c := self.flow.get_first_child()):
            self.flow.remove(c)
        for e in self.entries:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            card.add_css_class("card"); card.set_size_request(300, -1)
            pic = Gtk.Picture.new_for_filename(e["thumb"])
            pic.set_content_fit(Gtk.ContentFit.COVER)
            pic.set_size_request(-1, 168)
            card.append(pic)
            name = Gtk.Label(label=e["name"], xalign=0.5, ellipsize=3)
            name.add_css_class("heading")
            name.set_margin_start(8); name.set_margin_end(8)
            card.append(name)
            detail = e["licence"]
            if e.get("suggested_darken") is not None:
                detail += "  ·  " + (_("auto {0}%").format(e["suggested_darken"])
                                     if e["suggested_darken"] else _("no dimming needed"))
            sub = Gtk.Label(label=detail, xalign=0.5, ellipsize=3)
            sub.add_css_class("dim-label"); sub.add_css_class("caption")
            sub.set_margin_bottom(10); sub.set_margin_start(8); sub.set_margin_end(8)
            card.append(sub)
            self.flow.append(card)
        GLib.idle_add(lambda: self.flow.select_child(self.flow.get_child_at_index(self.selected)))

    def sync_slider(self):
        self.manual_row.set_sensitive(not self.auto.get_active())

    def on_select(self, *_a):
        sel = self.flow.get_selected_children()
        if sel:
            self.selected = sel[0].get_index()

    def toast(self, text, seconds=4):
        t = Adw.Toast(title=text); t.set_timeout(seconds); self.toasts.add_toast(t)

    # -------------------------------------------------------------- actions
    def on_add(self, *_a):
        dlg = Gtk.FileDialog(title=_("Choose a photo"))
        filt = Gtk.FileFilter(); filt.set_name(_("Images"))
        for p in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp"):
            filt.add_pattern(p)
        store = Gio.ListStore.new(Gtk.FileFilter); store.append(filt)
        dlg.set_filters(store)

        def done(d, res):
            try:
                gf = d.open_finish(res)
            except GLib.Error:
                return
            src = gf.get_path()
            os.makedirs(os.path.join(LIB, "custom"), exist_ok=True)
            shutil.copy(src, os.path.join(LIB, "custom", os.path.basename(src)))
            self.cfg, self.entries = catalogue()
            self.selected = len(self.entries) - 1
            self.fill()
            self.toast(_("Added: {0}").format(os.path.basename(src)))
        dlg.open(self, None, done)

    def run(self, install):
        if self.busy:
            return
        entry = self.entries[self.selected]
        darken = "auto" if self.auto.get_active() else int(self.scale.get_value())
        tint   = 100 if self.tint.get_active() else 0
        self.busy = True
        self.b_prev.set_sensitive(False); self.b_apply.set_sensitive(False)
        self.spinner.start()
        self.status.set_text(_("Rendering…  (about ten seconds)"))

        def work():
            try:
                tmp = tempfile.mkdtemp(prefix="refind-bg-")
                preview = os.path.join(tmp, "preview.png")
                B.build(entry["path"], darken, tmp, preview, quiet=True, tint=tint)
                GLib.idle_add(self.built, tmp, preview, install, None)
            except Exception as exc:
                GLib.idle_add(self.built, None, None, install, str(exc))
        threading.Thread(target=work, daemon=True).start()

    def built(self, tmp, preview, install, error):
        if error:
            self.idle(); self.toast(_("Failed: {0}").format(error), 8); return
        if not install:
            self.idle(); self.show_image(preview)
            self.toast(_("Preview opened — nothing was installed")); return
        self.status.set_text(_("Installing…  (you will be asked for your password)"))

        def work():
            try:
                r = subprocess.run(["pkexec", os.path.join(HERE, "install-assets.sh"), tmp],
                                   capture_output=True, text=True)
                GLib.idle_add(self.installed, tmp, r.returncode, r.stderr.strip())
            except Exception as exc:
                GLib.idle_add(self.installed, tmp, 1, str(exc))
        threading.Thread(target=work, daemon=True).start()

    def installed(self, tmp, rc, err):
        self.idle()
        if rc != 0:
            self.toast(_("Install failed: {0}").format(err or _("cancelled")), 8); return
        for p in glob.glob(f"{tmp}/*.png") + glob.glob(f"{tmp}/icons/*.png"):
            dst = os.path.join(HERE, "assets", os.path.relpath(p, tmp))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(p, dst)
        self.toast(_("Done — reboot to see the new background"), 6)

    def idle(self):
        self.busy = False
        self.spinner.stop()
        self.status.set_text("")
        self.b_prev.set_sensitive(True); self.b_apply.set_sensitive(True)

    def show_image(self, path):
        final = os.path.join(CACHE, "preview.png")
        shutil.copy(path, final)
        Gio.AppInfo.launch_default_for_uri(f"file://{final}", None)


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        (self.props.active_window or Window(self)).present()


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
