"""Efectos de intensidad y color (pensados para pares LED, sirven también en cabezales).

fx_eval() es una función pura: el motor la usa en vivo y el catálogo la usa para
dibujar la vista previa de cada efecto.
"""
import colorsys
import math
import random

from .fixtures import hex_to_rgb, rgb_to_hex

TAU = 2 * math.pi

# tipo: (familia, nombre, requisito)  requisito: "dim" | "color" (RGB o rueda) | "rgb"
TYPES = {
    "pulso": ("dim", "Persecución", "dim"),
    "rebote": ("dim", "Rebote", "dim"),
    "llenado": ("dim", "Llenado", "dim"),
    "onda": ("dim", "Onda", "dim"),
    "azar": ("dim", "Aleatorio", "dim"),
    "chispas": ("dim", "Chispas", "dim"),
    "relampago": ("dim", "Relámpago", "dim"),
    "par_impar": ("dim", "Pares e impares", "dim"),
    "centro": ("dim", "Desde el centro", "dim"),
    "latido": ("dim", "Latido", "dim"),
    "vela": ("dim", "Vela", "dim"),
    "destellos": ("dim", "Destellos al azar", "dim"),
    "arcoiris": ("color", "Arcoíris", "color"),  # en cabezales recorre la rueda de color
    "colores": ("color", "Alternar colores", "color"),
    "alternar": ("color", "Pares e impares de color", "color"),
    "mitades": ("color", "Mitades", "color"),
    "fuego": ("color", "Fuego", "rgb"),
    "degrade": ("color", "Degradé", "rgb"),
    "confeti": ("color", "Confeti", "color"),
    "barrido_color": ("color", "Barrido de color", "color"),
    # para el baile (pensados para los Nebula, sirven en cualquier par)
    "golpe": ("dim", "Golpe al beat", "dim"),
    "cometa": ("dim", "Cometa", "dim"),
    "strobo_tempo": ("dim", "Strobo al tempo", "dim"),
    "subida": ("dim", "Subida", "dim"),
    "color_beat": ("color", "Color al beat", "color"),
    "chispas_color": ("color", "Chispas de color", "rgb"),
}

# efectos que se apagan solos al terminar (la subida termina en un fogonazo)
ONCE = {"subida"}

# paletas rápidas: cambian los colores de todos los efectos de color
PALETTES = [
    ("fiesta", "Fiesta", ["#ff2020", "#2a46ff", "#22e04a", "#ffd60a", "#ff2ae6"]),
    ("fuego", "Fuego", ["#ff2010", "#ff6a00", "#ffb030", "#ffd60a"]),
    ("hielo", "Hielo", ["#2a46ff", "#22c8ff", "#ffffff", "#7a3cff"]),
    ("neon", "Neón", ["#ff2ae6", "#00f0ff", "#9dff00", "#7a3cff"]),
    ("calida", "Cálida", ["#ffb030", "#ff5fa0", "#ff7a2a", "#ffd9a0"]),
]
# tipos que toman la paleta (los que usan varios colores)
PALETTE_TYPES = {"colores", "alternar", "mitades", "degrade", "confeti", "barrido_color",
                 "color_beat", "chispas_color"}

SIZE_LABEL = {"golpe": "Corte", "cometa": "Cola", "strobo_tempo": "Rapidez", "subida": "Brillo final",
              "chispas_color": "Cantidad", "pulso": "Ancho", "rebote": "Ancho", "onda": "Profundidad", "azar": "Cantidad",
              "chispas": "Cantidad", "relampago": "Frecuencia", "fuego": "Intensidad",
              "centro": "Ancho", "vela": "Profundidad", "destellos": "Cantidad", "barrido_color": "Ancho"}


def frac(x):
    return x - math.floor(x)


def _rnd(*parts):
    return random.Random("|".join(str(p) for p in parts)).random()


def _smooth_noise(seed, t):
    """Ruido suave 0..1 (para el fuego)."""
    i = math.floor(t)
    a, b = _rnd(seed, i), _rnd(seed, i + 1)
    f = t - i
    f = f * f * (3 - 2 * f)
    return a + (b - a) * f


def fx_eval(fx, k, n, ph, seed=""):
    """Para el equipo k de n, en la fase ph: (factor de intensidad | None, color rgb | None)."""
    t = fx["type"]
    n = max(n, 1)
    order = (n - 1 - k) if fx.get("reverse") else k
    size = float(fx.get("size", 0.5))
    spread = float(fx.get("spread", 1.0))
    p = ph - spread * order / n
    cols = fx.get("colors") or ["#ff2020", "#2a46ff"]

    if t == "pulso":
        return (1.0 if frac(p) < max(size, 0.02) else 0.0), None
    if t == "onda":
        return (1 - size) + size * (0.5 + 0.5 * math.cos(TAU * p)), None
    if t == "azar":
        return (1.0 if _rnd(seed, k, math.floor(ph)) < size else 0.0), None
    if t == "rebote":  # una luz que va y viene
        f = frac(ph)
        pos = (f * 2 if f < 0.5 else 2 - f * 2) * (n - 1)
        if fx.get("reverse"):
            pos = (n - 1) - pos
        width = max(0.5, size * n / 2)
        return (1.0 if abs(k - pos) < width else 0.0), None
    if t == "llenado":  # se van prendiendo de a uno y después se apagan
        f = frac(ph) * 2
        if f < 1:
            return (1.0 if order < f * n else 0.0), None
        return (0.0 if order < (f - 1) * n else 1.0), None
    if t == "chispas":  # fondo bajo con destellos al azar
        sub = ph * 6
        on = _rnd(seed, k, math.floor(sub)) < size * 0.6 and frac(sub) < 0.45
        return (1.0 if on else 0.12), None
    if t == "relampago":  # oscuro, con dobles destellos blancos de golpe
        c = math.floor(ph)
        f = frac(ph)
        hit = _rnd(seed, "r", c) < max(size, 0.05)
        start = 0.1 + 0.6 * _rnd(seed, "s", c)
        flash = hit and (start <= f < start + 0.035 or start + 0.09 <= f < start + 0.14)
        return (1.0 if flash else 0.0), (1.0, 1.0, 1.0)
    if t == "par_impar":
        return (1.0 if (order + math.floor(ph * 2)) % 2 == 0 else 0.0), None
    if t == "centro":  # una ola que sale del medio hacia los costados (invertido: entra)
        u = abs(2.0 * k / (n - 1) - 1.0) if n > 1 else 0.0
        f = frac(ph) * 1.4 - 0.2
        if fx.get("reverse"):
            f = 1.0 - f
        return (1.0 if abs(u - f) < 0.12 + size * 0.35 else 0.0), None
    if t == "latido":  # pum-pum, todos juntos
        f = frac(p)
        beat = max(math.exp(-((f - 0.06) / 0.045) ** 2), 0.75 * math.exp(-((f - 0.3) / 0.05) ** 2))
        return 0.06 + 0.94 * beat, None
    if t == "vela":  # titileo suave, cada uno a su ritmo
        v = _smooth_noise("v" + str(seed) + str(k), ph * 10)
        return 1 - size * 0.75 * (1 - v), None
    if t == "destellos":  # apagados, con flashes cortos al azar
        sub = ph * 16
        on = _rnd(seed, "d", k, math.floor(sub)) < 0.08 + size * 0.3 and frac(sub) < 0.3
        return (1.0 if on else 0.0), None
    if t == "arcoiris":
        return None, colorsys.hsv_to_rgb(frac(p), 1.0, 1.0)
    if t == "colores":
        return None, hex_to_rgb(cols[int(frac(p) * len(cols)) % len(cols)])
    if t == "alternar":
        return None, hex_to_rgb(cols[(order + math.floor(ph * 2)) % 2 % len(cols)])
    if t == "mitades":
        half = 0 if order < n / 2 else 1
        return None, hex_to_rgb(cols[(half + math.floor(ph * 2)) % 2 % len(cols)])
    if t == "degrade":  # dos colores que se mezclan y corren
        a, b = hex_to_rgb(cols[0]), hex_to_rgb(cols[1 % len(cols)])
        m = 0.5 + 0.5 * math.cos(TAU * p)
        return None, tuple(a[i] * m + b[i] * (1 - m) for i in range(3))
    if t == "confeti":  # cada equipo con un color al azar, cambia en cada vuelta
        r = _rnd(seed, "c", k, math.floor(ph))
        return None, hex_to_rgb(cols[int(r * len(cols)) % len(cols)])
    if t == "barrido_color":  # una franja del segundo color cruza sobre el primero
        f = frac(ph) * (1 + 2 * 0.3) - 0.3
        pos = f * (n - 1) if n > 1 else 0
        if fx.get("reverse"):
            pos = (n - 1) - pos
        on = abs(k - pos) < max(0.5, size * n / 2)
        return None, hex_to_rgb(cols[(1 if on else 0) % len(cols)])
    if t == "golpe":  # pega fuerte en cada tiempo y se apaga rápido
        beats = max(float(fx.get("beats", 4)), 1.0)
        if spread >= 0.5:  # alternado: los pares en un tiempo, los impares en el otro
            f = frac((ph * beats - order % 2) / 2.0)
        else:
            f = frac(ph * beats)
        return 0.04 + 0.96 * math.exp(-f * (3.0 + size * 14.0)), None
    if t == "cometa":  # una luz con cola que da la vuelta por todos
        pos = frac(ph) * n
        if fx.get("reverse"):
            pos = n - pos
        d = (pos - k) % n          # cuánto pasó la cabeza por este equipo
        tail = max(0.6, size * n)
        return max(0.0, 1.0 - d / tail) if d < tail else 0.0, None
    if t == "strobo_tempo":  # destellos cortos pegados al tempo (1, 2, 4 u 8 por tiempo)
        beats = max(float(fx.get("beats", 1)), 0.25)
        div = 2 ** int(round(size * 3))
        return (1.0 if frac(p * beats * div) < 0.3 else 0.0), None
    if t == "subida":  # pulsos que se aceleran y terminan en un fogonazo
        x = min(ph, 1.0)
        if x >= 0.94:
            return 1.0, None
        beats = max(float(fx.get("beats", 16)), 1.0)
        q = beats * (2 ** (3 * x) - 1) / (3 * math.log(2))  # 1 pulso por tiempo al principio, 8 al final
        level = 0.35 + 0.65 * x
        return (level if frac(q) < 0.45 else 0.0), None
    if t == "color_beat":  # cambia de color en cada tiempo (juntos o alternados)
        beats = max(float(fx.get("beats", 4)), 1.0)
        b = math.floor(ph * beats + 1e-9)
        off = order if spread >= 0.5 else 0
        return None, hex_to_rgb(cols[(b + off) % len(cols)])
    if t == "chispas_color":  # destellos al azar, cada uno de un color
        sub = ph * 12
        cell = math.floor(sub)
        on = _rnd(seed, "cc", k, cell) < 0.1 + size * 0.45 and frac(sub) < 0.5
        col = hex_to_rgb(cols[int(_rnd(seed, "cl", k, cell) * len(cols)) % len(cols)])
        return (1.0 if on else 0.05), col
    if t == "fuego":
        v = _smooth_noise(str(seed) + str(k), ph * 8)
        dim = 1 - size * 0.65 * (1 - v)
        return dim, (1.0, 0.12 + 0.5 * v * v, 0.0)
    return None, None


# --------------------------------------------------------------- catálogo ---
PRESETS = [
    # id, nombre, tipo, parámetros
    ("persecucion", "Persecución", "pulso", {"beats": 8}),
    ("rebote", "Rebote", "rebote", {"beats": 4, "size": 0.25}),
    ("llenado", "Llenado", "llenado", {"beats": 8}),
    ("onda", "Onda", "onda", {"beats": 4, "size": 1.0, "spread": 1.0}),
    ("respiracion", "Respiración", "onda", {"beats": 8, "size": 1.0, "spread": 0.0}),
    ("aleatorio", "Aleatorio", "azar", {"beats": 1, "size": 0.4}),
    ("chispas", "Chispas", "chispas", {"beats": 4, "size": 0.5}),
    ("relampago", "Relámpago", "relampago", {"beats": 4, "size": 0.6}),
    ("par_impar", "Pares e impares", "par_impar", {"beats": 2}),
    ("arcoiris", "Arcoíris", "arcoiris", {"beats": 16, "spread": 0.0}),
    ("ola_arcoiris", "Ola arcoíris", "arcoiris", {"beats": 8, "spread": 1.0}),
    ("alternar_colores", "Alternar colores", "colores", {"beats": 2, "spread": 0.0}),
    ("color_par_impar", "Pares e impares de color", "alternar", {"beats": 2, "colors": ["#ff2ae6", "#22e6ee"]}),
    ("mitades", "Mitades", "mitades", {"beats": 4, "colors": ["#2a46ff", "#ffd60a"]}),
    ("fuego", "Fuego", "fuego", {"beats": 8, "size": 0.8}),
    ("desde_centro", "Desde el centro", "centro", {"beats": 4, "size": 0.3}),
    ("hacia_centro", "Hacia el centro", "centro", {"beats": 4, "size": 0.3, "reverse": True}),
    ("latido", "Latido", "latido", {"beats": 2, "spread": 0.0}),
    ("vela", "Vela", "vela", {"beats": 8, "size": 0.7}),
    ("destellos", "Destellos al azar", "destellos", {"beats": 4, "size": 0.5}),
    ("degrade", "Degradé", "degrade", {"beats": 8, "spread": 1.0, "colors": ["#ff2ae6", "#2a46ff"]}),
    ("degrade_calido", "Degradé cálido", "degrade", {"beats": 8, "spread": 1.0, "colors": ["#ff2020", "#ffb030"]}),
    ("confeti", "Confeti", "confeti", {"beats": 2, "colors": ["#ff2020", "#22e04a", "#2a46ff", "#ffd60a", "#ff2ae6"]}),
    ("barrido_color", "Barrido de color", "barrido_color", {"beats": 4, "size": 0.3, "colors": ["#2a46ff", "#ffffff"]}),
    # para el baile
    ("golpe", "Golpe al beat", "golpe", {"beats": 1, "size": 0.5, "spread": 0.0}),
    ("golpe_alterno", "Golpe alternado", "golpe", {"beats": 2, "size": 0.5, "spread": 1.0}),
    ("cometa", "Cometa", "cometa", {"beats": 4, "size": 0.4}),
    ("strobo_tempo", "Strobo al tempo", "strobo_tempo", {"beats": 1, "size": 0.67, "spread": 0.0}),
    ("subida", "Subida (al drop)", "subida", {"beats": 16, "spread": 0.0}),
    ("color_beat", "Color al beat", "color_beat", {"beats": 4, "spread": 0.0,
                                                    "colors": ["#ff2020", "#2a46ff", "#22e04a", "#ff2ae6"]}),
    ("color_beat_alt", "Color al beat alternado", "color_beat", {"beats": 4, "spread": 1.0,
                                                                  "colors": ["#ff2020", "#2a46ff", "#22e04a", "#ff2ae6"]}),
    ("chispas_color", "Chispas de color", "chispas_color", {"beats": 4, "size": 0.5,
                                                            "colors": ["#ff2020", "#2a46ff", "#22e04a", "#ffd60a", "#ff2ae6"]}),
]

PREVIEW_BASE = (1.0, 0.82, 0.55)  # color de fondo para dibujar efectos de intensidad


def preview_grid(ftype, params, n=8, steps=12):
    """Filas = momentos, columnas = equipos. Cada celda: [color, intensidad]."""
    fx = {"type": ftype, "size": 0.5, "spread": 1.0, "colors": ["#ff2020", "#2a46ff"], "reverse": False}
    if ftype == "pulso":
        fx["size"] = 1.0 / n
    fx.update(params)
    if ftype == "relampago":
        fx["size"] = 1.0  # en el dibujo, que siempre se vea un destello
    rows = []
    for s in range(steps):
        ph = s / steps
        row = []
        for k in range(n):
            d, rgb = fx_eval(fx, k, n, ph, "vista")
            row.append([rgb_to_hex(*(rgb or PREVIEW_BASE)), round(1.0 if d is None else d, 2)])
        rows.append(row)
    return rows


def catalog():
    out = []
    for pid, name, ftype, prm in PRESETS:
        fam, _, need = TYPES[ftype]
        out.append({"id": pid, "name": name, "type": ftype, "family": fam, "needs": need,
                    "params": prm, "grid": preview_grid(ftype, prm)})
    return out
