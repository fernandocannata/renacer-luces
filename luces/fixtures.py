"""Perfiles de equipos: carga, capacidades y utilidades de color."""
import colorsys
import json
import os

# Funciones que puede tener un canal dentro de un perfil
CHANNEL_ATTRS = {
    "intensity": "Dimmer / intensidad",
    "red": "Rojo",
    "green": "Verde",
    "blue": "Azul",
    "white": "Blanco",
    "strobe": "Strobo",
    "pan": "Pan",
    "pan_fine": "Pan fino",
    "tilt": "Tilt",
    "tilt_fine": "Tilt fino",
    "pt_speed": "Velocidad Pan/Tilt",
    "color_wheel": "Rueda de color",
    "gobo": "Gobo",
    "prism": "Prisma",
    "prism_rotation": "Rotación de prisma",
    "focus": "Foco",
    "smoke": "Humo",
    "raw": "Otro (valor fijo)",
}

# Atributos que viven en el "estado" de cada equipo (todos normalizados 0..1,
# salvo los de rueda que son índices enteros)
CONTINUOUS = {"dim", "r", "g", "b", "w", "pan", "tilt", "pts", "focus", "prot", "smoke"}
DISCRETE = {"cw", "gobo", "prism", "strobe"}

# Paleta de colores rápida (r, g, b, w)
PALETTE = [
    {"nombre": "Blanco", "rgbw": [0, 0, 0, 1], "hex": "#ffffff"},
    {"nombre": "Cálido", "rgbw": [1, 0.55, 0.15, 0.6], "hex": "#ffd29a"},
    {"nombre": "Rojo", "rgbw": [1, 0, 0, 0], "hex": "#ff2020"},
    {"nombre": "Naranja", "rgbw": [1, 0.35, 0, 0], "hex": "#ff7a12"},
    {"nombre": "Amarillo", "rgbw": [1, 0.8, 0, 0], "hex": "#ffd60a"},
    {"nombre": "Verde", "rgbw": [0, 1, 0, 0], "hex": "#22e04a"},
    {"nombre": "Cian", "rgbw": [0, 1, 1, 0], "hex": "#22e6ee"},
    {"nombre": "Azul", "rgbw": [0, 0, 1, 0], "hex": "#2a46ff"},
    {"nombre": "Violeta", "rgbw": [0.45, 0, 1, 0], "hex": "#7a2aff"},
    {"nombre": "Magenta", "rgbw": [1, 0, 1, 0], "hex": "#ff2ae6"},
    {"nombre": "Rosa", "rgbw": [1, 0.15, 0.45, 0], "hex": "#ff5aa0"},
]


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) != 6:
        return (1.0, 1.0, 1.0)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_to_hex(r, g, b):
    c = lambda v: max(0, min(255, int(round(v * 255))))
    return "#%02x%02x%02x" % (c(r), c(g), c(b))


def rgbw_to_rgb(r, g, b, w):
    return (min(1, r + w), min(1, g + w), min(1, b + w))


def _norm(rgb):
    m = max(rgb)
    return tuple(v / m for v in rgb) if m > 0 else (0, 0, 0)


def nearest_slot(slots, rgb):
    """Índice de la rueda de color más parecido a un color RGB."""
    if not slots:
        return 0
    target = _norm(rgb)
    th, ts, _ = colorsys.rgb_to_hsv(*target)
    best, best_d = 0, 1e9
    for i, s in enumerate(slots):
        sr = _norm(hex_to_rgb(s.get("hex", "#ffffff")))
        sh, ss, _ = colorsys.rgb_to_hsv(*sr)
        if ts < 0.25 or ss < 0.25:  # blancos / poco saturados: compara saturación
            d = abs(ts - ss) * 2 + (0 if ts < 0.25 and ss < 0.25 else 1)
        else:
            dh = min(abs(th - sh), 1 - abs(th - sh))
            d = dh * 4 + abs(ts - ss)
        if d < best_d:
            best, best_d = i, d
    return best


class Library:
    """Biblioteca de perfiles: los que vienen con el programa + los del usuario."""

    def __init__(self, builtin_dir, user_dir):
        self.builtin_dir = builtin_dir
        self.user_dir = user_dir
        self.profiles = {}
        self.reload()

    def reload(self):
        self.profiles = {}
        for d, origen in ((self.builtin_dir, "incluido"), (self.user_dir, "usuario")):
            if not d or not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(d, fn), encoding="utf-8") as f:
                        p = json.load(f)
                    p["id"] = fn[:-5]
                    p["origen"] = origen
                    self.profiles[p["id"]] = p
                except Exception as e:  # perfil roto: se ignora
                    print("Perfil inválido", fn, e)

    def get(self, pid):
        return self.profiles.get(pid)

    def save_user_profile(self, pid, data):
        os.makedirs(self.user_dir, exist_ok=True)
        clean = {k: v for k, v in data.items() if k not in ("id", "origen")}
        with open(os.path.join(self.user_dir, pid + ".json"), "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
        self.reload()

    def summary(self):
        out = []
        for pid, p in sorted(self.profiles.items(), key=lambda kv: kv[1].get("nombre", "")):
            out.append(dict(p, caps=sorted(caps(p))))
        return out


def caps(profile):
    """Conjunto de capacidades de un perfil."""
    attrs = {c.get("attr") for c in profile.get("canales", [])}
    c = set()
    if attrs & {"red", "green", "blue"}:
        c.add("rgb")
    if "white" in attrs:
        c.add("white")
    if "intensity" in attrs:
        c.add("intensity")
    if "intensity" in attrs or attrs & {"red", "green", "blue", "white"}:
        c.add("dim")
    for a, cap in (("pan", "pan"), ("tilt", "tilt"), ("pt_speed", "pts"), ("color_wheel", "cw"),
                   ("gobo", "gobo"), ("prism", "prism"), ("prism_rotation", "prot"),
                   ("focus", "focus"), ("strobe", "strobe"), ("smoke", "smoke")):
        if a in attrs:
            c.add(cap)
    if "pan" in c or "tilt" in c:
        c.add("mover")
    return c


def default_look(profile):
    c = caps(profile)
    look = {}
    if "dim" in c:
        look["dim"] = 0.0
    if "rgb" in c:
        if "white" in c:
            look.update(r=0.0, g=0.0, b=0.0, w=1.0)
        else:
            look.update(r=1.0, g=1.0, b=1.0)
    elif "white" in c:
        look["w"] = 1.0
    if "cw" in c:
        look["cw"] = 0
    if "pan" in c:
        look["pan"] = 0.5
    if "tilt" in c:
        look["tilt"] = 0.5
    if "pts" in c:
        look["pts"] = 0.0
    if "gobo" in c:
        look["gobo"] = 0
    if "prism" in c:
        look["prism"] = 0
    if "prot" in c:
        look["prot"] = 0.0
    if "focus" in c:
        look["focus"] = 0.5
    if "strobe" in c:
        look["strobe"] = 0.0
    if "smoke" in c:
        look["smoke"] = 0.0
    return look


def apply_color(profile, look, rgbw):
    """Aplica un color (r,g,b,w) a un equipo, sea LED o rueda de color."""
    c = caps(profile)
    r, g, b, w = (list(rgbw) + [0, 0, 0, 0])[:4]
    if "rgb" in c:
        if "white" in c:
            look.update(r=r, g=g, b=b, w=w)
        else:
            rr, gg, bb = rgbw_to_rgb(r, g, b, w)
            look.update(r=rr, g=gg, b=bb)
    elif "white" in c:
        look["w"] = max(r, g, b, w)
    if "cw" in c:
        look["cw"] = nearest_slot(profile.get("color_wheel", []), rgbw_to_rgb(r, g, b, w))
