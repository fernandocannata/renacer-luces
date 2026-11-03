"""Dónde y cómo se guardan los shows, perfiles propios y ajustes."""
import json
import os
import re
import shutil
import sys


def base_dir():
    """Carpeta del programa (funciona también empaquetado como .exe)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    """Carpeta de datos del usuario: Documentos/Renacer LightShow."""
    override = os.environ.get("RENACER_LUCES_DATA")
    if override:
        d = override
    else:
        home = os.path.expanduser("~")
        docs = os.path.join(home, "Documents")
        if not os.path.isdir(docs):
            docs = os.path.join(home, "Documentos") if os.path.isdir(os.path.join(home, "Documentos")) else home
        d = os.path.join(docs, "Renacer LightShow")
        old = os.path.join(docs, "Renacer Luces")  # nombre anterior del programa
        if not os.path.exists(d) and os.path.isdir(old):
            try:
                shutil.copytree(old, d)  # se copia: la carpeta vieja queda como respaldo
            except Exception as e:
                print("No se pudieron traer los datos de 'Renacer Luces':", e)
    for sub in ("", "shows", "perfiles"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    return d


def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", (name or "").strip())[:60]
    return name or "Mi show"


class Storage:
    def __init__(self):
        self.dir = data_dir()
        self.shows_dir = os.path.join(self.dir, "shows")
        self.user_profiles_dir = os.path.join(self.dir, "perfiles")
        self.settings_path = os.path.join(self.dir, "ajustes.json")
        self.settings = {"ultimo_show": "Mi show", "salida": "auto", "control_remoto": False, "puerto": 8731,
                         "dmx_ritmo": "normal"}
        try:
            with open(self.settings_path, encoding="utf-8") as f:
                self.settings.update(json.load(f))
        except Exception:
            pass
        if self.settings.get("puerto") == 8730:  # puerto de "Renacer Luces": se cambia para no chocar con la versión vieja
            self.settings["puerto"] = 8731

    def save_settings(self):
        self._atomic_write(self.settings_path, self.settings)

    def list_shows(self):
        out = []
        for fn in sorted(os.listdir(self.shows_dir)):
            if fn.endswith(".json"):
                p = os.path.join(self.shows_dir, fn)
                out.append({"name": fn[:-5], "mtime": os.path.getmtime(p)})
        return sorted(out, key=lambda s: -s["mtime"])

    def show_path(self, name):
        return os.path.join(self.shows_dir, safe_name(name) + ".json")

    def load_show(self, name):
        with open(self.show_path(name), encoding="utf-8") as f:
            s = json.load(f)
        s["name"] = safe_name(name)
        return s

    def save_show(self, show):
        name = safe_name(show.get("name"))
        show["name"] = name
        self._atomic_write(self.show_path(name), show)
        if self.settings.get("ultimo_show") != name:
            self.settings["ultimo_show"] = name
            self.save_settings()

    def delete_show(self, name):
        p = self.show_path(name)
        if os.path.exists(p):
            os.remove(p)

    @staticmethod
    def _atomic_write(path, data):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)


def default_show(engine_cls=None, library=None, name="Mi show"):
    """Show inicial con el equipamiento de Fernando: 4 VT-B100 y 8 Nebula Quad 14."""
    fixtures = []
    addr = 1
    for i in range(4):
        fixtures.append({"id": "eq_cab%d" % (i + 1), "name": "Cabezal %d" % (i + 1),
                         "profile": "venetian_vt_b100_12ch", "address": addr,
                         "invert_pan": False, "invert_tilt": False})
        addr += 12
    for i in range(8):
        fixtures.append({"id": "eq_par%d" % (i + 1), "name": "Par %d" % (i + 1),
                         "profile": "tecshow_nebula_quad14_8ch", "address": addr,
                         "invert_pan": False, "invert_tilt": False})
        addr += 8
    return {"name": name, "version": 1, "fixtures": fixtures, "scenes": [], "cues": [],
            "positions": [], "settings": {"fade": 1.0, "cue_loop": False}}
