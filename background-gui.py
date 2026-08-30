#!/usr/bin/env python3
"""Graphical picker for the boot menu background (GTK4 / libadwaita)."""
import glob, json, os, shutil, subprocess, sys, tempfile, threading
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk, Gio

HERE = os.path.dirname(os.path.abspath(__file__))
LIB  = os.path.join(HERE, "library")
CACHE = os.path.join(GLib.get_user_cache_dir(), "refind-background")
sys.path.insert(0, HERE)
import build as B

APP_ID = "io.github.idank0.RefindBackground"


def catalogo():
    cfg = json.load(open(os.path.join(LIB, "library.json")))
    voci = [{**s, "path": os.path.join(HERE, s["file"]), "custom": False} for s in cfg["sfondi"]]
    for p in sorted(glob.glob(os.path.join(LIB, "custom", "*"))):
        if p.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp")):
            voci.append({"slug": os.path.splitext(os.path.basename(p))[0],
                         "nome": os.path.basename(p), "path": p, "custom": True,
                         "licenza": "tua", "luminosita": None, "darken_consigliato": None})
    return cfg, voci


def miniature(voci):
    """Library thumbnails are sliced out of the contact sheet, so they already
    show the theme. Custom photos get a plain crop — fast, and the Preview
    button renders the real thing anyway."""
    os.makedirs(CACHE, exist_ok=True)
    from PIL import Image
    sheet_path = os.path.join(LIB, "preview-sheet.jpg")
    sheet = Image.open(sheet_path) if os.path.exists(sheet_path) else None
    n_lib = sum(1 for v in voci if not v["custom"])
    for i, v in enumerate(voci):
        dst = os.path.join(CACHE, f"{v['slug']}.png")
        v["thumb"] = dst
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(v["path"]):
            continue
        if not v["custom"] and sheet is not None and i < n_lib:
            x, y = (i % 2) * 960, (i // 2) * 602 + 62
            sheet.crop((x, y, x + 960, y + 540)).resize((384, 216), Image.LANCZOS).save(dst)
        else:
            im = Image.open(v["path"]).convert("RGB"); w, h = im.size
            if w / h > 16 / 9:
                nw = int(h * 16 / 9); im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
            else:
                nh = int(w * 9 / 16); im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
            im.resize((384, 216), Image.LANCZOS).save(dst)


class Finestra(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Sfondo del menu di avvio",
                         default_width=1020, default_height=760)
        self.cfg, self.voci = catalogo()
        self.selezione = 0
        self.lavoro = False

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toasts.set_child(root)

        hb = Adw.HeaderBar()
        titolo = Adw.WindowTitle(title="Sfondo del menu di avvio",
                                 subtitle="scegline uno, o aggiungi una tua foto")
        hb.set_title_widget(titolo)
        piu = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Aggiungi una tua foto")
        piu.connect("clicked", self.aggiungi)
        hb.pack_start(piu)
        root.append(hb)

        sw = Gtk.ScrolledWindow(vexpand=True)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.SINGLE,
                                homogeneous=True, column_spacing=14, row_spacing=14,
                                max_children_per_line=3, min_children_per_line=2,
                                margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        self.flow.connect("selected-children-changed", self.cambio_selezione)
        sw.set_child(self.flow)
        root.append(sw)
        self.popola()

        # ---- barra inferiore
        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      margin_top=6, margin_bottom=16, margin_start=18, margin_end=18)
        gruppo = Adw.PreferencesGroup()
        riga = Adw.ActionRow(title="Scurimento automatico",
                             subtitle="Attenua la foto quel tanto che basta perché il vetro e le scritte si leggano")
        self.auto = Gtk.Switch(active=str(self.cfg.get("darken_predefinito")) == "auto",
                               valign=Gtk.Align.CENTER)
        self.auto.connect("state-set", lambda *_: (self.aggiorna_slider(), False)[1])
        riga.add_suffix(self.auto); riga.set_activatable_widget(self.auto)
        gruppo.add(riga)

        self.riga_man = Adw.ActionRow(title="Scurimento manuale")
        self.scala = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.scala.set_size_request(320, -1); self.scala.set_draw_value(True)
        self.scala.set_value_pos(Gtk.PositionType.RIGHT)
        d = self.cfg.get("darken_predefinito")
        self.scala.set_value(0 if str(d) == "auto" else int(d))
        self.riga_man.add_suffix(self.scala)
        gruppo.add(self.riga_man)
        bar.append(gruppo)

        azioni = Gtk.Box(spacing=10, halign=Gtk.Align.END)
        self.b_prev = Gtk.Button(label="Anteprima")
        self.b_prev.connect("clicked", lambda *_: self.esegui(False))
        self.b_app = Gtk.Button(label="Applica")
        self.b_app.add_css_class("suggested-action")
        self.b_app.connect("clicked", lambda *_: self.esegui(True))
        self.spinner = Gtk.Spinner()
        self.stato = Gtk.Label(label="", xalign=0)
        azioni.append(self.stato); azioni.append(self.spinner)
        azioni.append(self.b_prev); azioni.append(self.b_app)
        bar.append(azioni)
        root.append(bar)
        self.aggiorna_slider()

    # ------------------------------------------------------------------ ui
    def popola(self):
        miniature(self.voci)
        while (c := self.flow.get_first_child()):
            self.flow.remove(c)
        for v in self.voci:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            card.add_css_class("card"); card.set_size_request(300, -1)
            pic = Gtk.Picture.new_for_filename(v["thumb"])
            pic.set_content_fit(Gtk.ContentFit.COVER)
            pic.set_size_request(-1, 168)
            card.append(pic)
            nome = Gtk.Label(label=v["nome"], xalign=0.5, ellipsize=3)
            nome.add_css_class("heading")
            nome.set_margin_start(8); nome.set_margin_end(8)
            card.append(nome)
            det = v["licenza"]
            if v.get("darken_consigliato") is not None:
                det += "  ·  auto " + (f"{v['darken_consigliato']}%" if v['darken_consigliato'] else "non serve")
            sub = Gtk.Label(label=det, xalign=0.5, ellipsize=3)
            sub.add_css_class("dim-label"); sub.add_css_class("caption")
            sub.set_margin_bottom(10); sub.set_margin_start(8); sub.set_margin_end(8)
            card.append(sub)
            self.flow.append(card)
        GLib.idle_add(lambda: self.flow.select_child(self.flow.get_child_at_index(self.selezione)))

    def aggiorna_slider(self):
        self.riga_man.set_sensitive(not self.auto.get_active())

    def cambio_selezione(self, *_):
        sel = self.flow.get_selected_children()
        if sel:
            self.selezione = sel[0].get_index()

    def toast(self, testo, secondi=4):
        t = Adw.Toast(title=testo); t.set_timeout(secondi); self.toasts.add_toast(t)

    # -------------------------------------------------------------- azioni
    def aggiungi(self, *_):
        dlg = Gtk.FileDialog(title="Scegli una foto")
        f = Gtk.FileFilter(); f.set_name("Immagini")
        for p in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp"): f.add_pattern(p)
        store = Gio.ListStore.new(Gtk.FileFilter); store.append(f)
        dlg.set_filters(store)
        def fatto(d, res):
            try: gf = d.open_finish(res)
            except GLib.Error: return
            src = gf.get_path()
            os.makedirs(os.path.join(LIB, "custom"), exist_ok=True)
            dst = os.path.join(LIB, "custom", os.path.basename(src))
            shutil.copy(src, dst)
            self.cfg, self.voci = catalogo()
            self.selezione = len(self.voci) - 1
            self.popola()
            self.toast(f"Aggiunta: {os.path.basename(src)}")
        dlg.open(self, None, fatto)

    def esegui(self, installa):
        if self.lavoro: return
        v = self.voci[self.selezione]
        darken = "auto" if self.auto.get_active() else int(self.scala.get_value())
        self.lavoro = True
        self.b_prev.set_sensitive(False); self.b_app.set_sensitive(False)
        self.spinner.start()
        self.stato.set_text("Genero l'anteprima…  (una decina di secondi)")

        def lavoro():
            try:
                tmp = tempfile.mkdtemp(prefix="refind-bg-")
                prev = os.path.join(tmp, "preview.png")
                B.build(v["path"], darken, tmp, prev, quiet=True)
                GLib.idle_add(self.dopo_build, tmp, prev, installa, None)
            except Exception as e:
                GLib.idle_add(self.dopo_build, None, None, installa, str(e))
        threading.Thread(target=lavoro, daemon=True).start()

    def dopo_build(self, tmp, prev, installa, errore):
        if errore:
            self.fine(); self.toast(f"Errore: {errore}", 8); return
        if not installa:
            self.fine(); self.mostra(prev)
            self.toast("Anteprima aperta — non ho installato niente"); return
        self.stato.set_text("Installo…  (ti verrà chiesta la password)")
        def lavoro():
            try:
                r = subprocess.run(["pkexec", os.path.join(HERE, "install-assets.sh"), tmp],
                                   capture_output=True, text=True)
                GLib.idle_add(self.dopo_install, tmp, r.returncode, r.stderr.strip())
            except Exception as e:
                GLib.idle_add(self.dopo_install, tmp, 1, str(e))
        threading.Thread(target=lavoro, daemon=True).start()

    def dopo_install(self, tmp, rc, err):
        self.fine()
        if rc != 0:
            self.toast(f"Installazione non riuscita: {err or 'annullata'}", 8); return
        for p in glob.glob(f"{tmp}/*.png") + glob.glob(f"{tmp}/icons/*.png"):
            dst = os.path.join(HERE, "assets", os.path.relpath(p, tmp))
            os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy(p, dst)
        self.toast("Fatto — riavvia per vedere il nuovo sfondo", 6)

    def fine(self):
        self.lavoro = False; self.spinner.stop(); self.stato.set_text("")
        self.b_prev.set_sensitive(True); self.b_app.set_sensitive(True)

    def mostra(self, path):
        finale = os.path.join(CACHE, "preview.png"); shutil.copy(path, finale)
        Gio.AppInfo.launch_default_for_uri(f"file://{finale}", None)


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
    def do_activate(self):
        (self.props.active_window or Finestra(self)).present()


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
