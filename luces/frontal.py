"""Movimientos frontales: cabezales en una barra (trípode) apuntando al público.

Todo se piensa "visto desde el público":
    x: -1 = bien a la izquierda   0 = al frente   +1 = bien a la derecha
    y: -1 = abajo (al piso/gente)  0 = altura del frente  +1 = arriba
El motor traduce (x, y) a pan/tilt con el "frente" calibrado de cada cabezal.
"""
import math
import random

TAU = 2 * math.pi


def head_u(k, n):
    """Lugar del cabezal en la barra: -1 el de la izquierda … +1 el de la derecha."""
    return 0.0 if n <= 1 else -1.0 + 2.0 * k / (n - 1)


def _ease(t):
    return 0.5 - 0.5 * math.cos(math.pi * t)


def _rand_point(seed, cycle):
    r = random.Random("%s|%d" % (seed, cycle))
    return r.uniform(-1, 1), r.uniform(-0.8, 0.8)


def _square(p):
    t = (p - math.floor(p)) * 4
    side, f = int(t) % 4, t - int(t)
    f = _ease(f)
    pts = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    (ax, ay), (bx, by) = pts[side], pts[(side + 1) % 4]
    return ax + (bx - ax) * f, ay + (by - ay) * f


def canon_s(p):
    """0 = arriba de todo, 1 = abajo del barrido; baja y sube suave."""
    return 0.5 - 0.5 * math.cos(TAU * p)


# Barrido vertical "en canon": grados reales de recorrido (tamaño 1 = 100°)
CANON_DEG = 100.0
CANON_TOP_MAX = 90.0   # lo más alto: hasta 90° por encima del frente


def shape(kind, p, u, seed=""):
    """Recorrido base (dx, dy) en -1..1 para la fase p (una vuelta por unidad)."""
    th = TAU * p
    if kind == "circulo":
        return math.cos(th), math.sin(th)
    if kind == "ocho":
        return math.sin(th), 0.55 * math.sin(2 * th)
    if kind == "ocho_v":
        return 0.55 * math.sin(2 * th), math.sin(th)
    if kind == "barrido":
        return math.sin(th), 0.0
    if kind == "vertical":
        return 0.0, math.sin(th)
    if kind == "tijera":       # se abren y se cruzan
        return u * math.cos(th), 0.0
    if kind == "abanico":      # abren hacia los costados y vuelven al centro
        return u * (0.5 - 0.5 * math.cos(th)), 0.0
    if kind == "pendulo":      # barrido que sube en las puntas
        s = math.sin(th)
        return s, 0.55 * s * s - 0.2
    if kind == "cuadrado":
        return _square(p)
    if kind == "recorrido":  # gran paneo: de costado a costado pasando por todas las alturas
        return math.sin(th), 0.9 * math.sin(3 * th)
    if kind == "espiral":  # se abre y se cierra girando
        r = 0.2 + 0.8 * (0.5 - 0.5 * math.cos(th))
        return r * math.cos(6 * th), r * math.sin(6 * th)
    if kind == "zigzag":
        tri = 2 / math.pi * math.asin(math.sin(4 * th))
        return math.sin(th), tri
    if kind == "pelota":  # cruza de lado a lado rebotando
        tri = 2 / math.pi * math.asin(math.sin(th))
        return tri, 1.6 * abs(math.sin(4 * th)) - 0.8
    if kind == "canon":  # de lo más alto hacia abajo y vuelve (el motor lo lleva a grados reales)
        return 0.0, 1.0 - 2.0 * canon_s(p)
    if kind == "aleatorio":
        c = math.floor(p)
        a, b = _rand_point(seed, c), _rand_point(seed, c + 1)
        f = _ease(p - c)
        return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
    return 0.0, 0.0


SHAPES = {
    "circulo": "Círculo", "ocho": "Ocho", "ocho_v": "Ocho parado", "barrido": "Barrido lateral",
    "vertical": "Arriba y abajo", "tijera": "Tijera", "abanico": "Abanico", "pendulo": "Péndulo",
    "cuadrado": "Cuadrado", "aleatorio": "Búsqueda al azar",
    "recorrido": "Gran paneo", "espiral": "Espiral", "zigzag": "Zigzag", "pelota": "Pelota",
    "canon": "Barrido vertical en canon",
}

# Parámetros de un movimiento frontal (además de velocidad, desfase e invertir)
DEFAULTS = {"size": 0.5, "altura": 0.0, "apertura": 0.0, "escalon": 0.0, "mirror": False,
            "spread": 0.0, "beats": 8}

# Combinaciones listas para usar
PRESETS = [
    ("circulo", "Círculo", "circulo", {"size": 0.45}),
    ("circulo_ola", "Círculos en ola", "circulo", {"size": 0.45, "spread": 0.5}),
    ("corona", "Corona arriba", "circulo", {"size": 0.3, "apertura": 0.6, "altura": 0.55, "spread": 0.5}),
    ("ocho", "Ocho", "ocho", {"size": 0.55}),
    ("ocho_v", "Ocho parado", "ocho_v", {"size": 0.5}),
    ("barrido", "Barrido lateral", "barrido", {"size": 0.8}),
    ("barrido_espejo", "Barrido en espejo", "barrido", {"size": 0.7, "mirror": True}),
    ("barrido_publico", "Barrido al público", "barrido", {"size": 0.9, "spread": 0.25, "altura": -0.5}),
    ("vertical", "Arriba y abajo", "vertical", {"size": 0.7, "beats": 4}),
    ("ola", "Ola", "vertical", {"size": 0.6, "spread": 1.0, "beats": 4}),
    ("cascada", "Cascada", "vertical", {"size": 0.6, "spread": 0.25, "apertura": 0.4, "beats": 4}),
    ("tijera", "Tijera", "tijera", {"size": 0.75}),
    ("abanico", "Abanico abre y cierra", "abanico", {"size": 1.0, "altura": 0.15}),
    ("pendulo", "Péndulo", "pendulo", {"size": 0.8, "beats": 4}),
    ("cuadrado", "Cuadrado", "cuadrado", {"size": 0.5}),
    ("busqueda", "Búsqueda al azar", "aleatorio", {"size": 0.8, "beats": 2}),
    ("gran_paneo", "Gran paneo (recepción)", "recorrido", {"size": 1.0, "beats": 32, "spread": 0.12}),
    ("paneo_sala", "Paneo lento de sala", "barrido", {"size": 1.0, "beats": 32, "spread": 0.15, "altura": -0.15}),
    ("espiral", "Espiral", "espiral", {"size": 0.7, "beats": 16}),
    ("zigzag", "Zigzag", "zigzag", {"size": 0.8, "beats": 16}),
    ("pelota", "Pelota", "pelota", {"size": 0.8, "beats": 8, "spread": 0.25}),
    # bajan desde lo más alto unos 90°, uno detrás del otro (la posición horizontal no la tocan)
    ("canon", "Barrido vertical en canon", "canon", {"size": 0.9, "beats": 8, "spread": 0.5}),
    # solo horizontal: se abren hacia los costados y se cierran (se combina con el de arriba)
    ("abre_cierra", "Abrir y cerrar", "abanico", {"size": 0.9, "beats": 8}),
]

# Posiciones fijas: función del lugar en la barra (u) -> (x, y)
LAYOUTS = [
    # el frente calibrado de cada cabezal es "derecho hacia adelante": todos paralelos
    ("frente", "Frente recto", lambda u: (0.0, 0.0)),
    ("publico", "Al público", lambda u: (0.0, -0.55)),
    ("alto", "Bien alto", lambda u: (0.0, 1.0)),
    ("abanico", "Abanico", lambda u: (0.8 * u, 0.0)),
    ("cruzados", "Cruzados", lambda u: (-0.55 * u, 0.0)),
    # los de las puntas se cruzan hacia adentro y los del medio abren hacia afuera
    ("cruzados_par", "Cruzados par", lambda u: (-0.55 * u if abs(u) > 0.5 else (0.6 if u > 0 else -0.6 if u < 0 else 0.0), 0.0)),
    ("costados", "A los costados", lambda u: ((0.75 + 0.25 * abs(u)) * (1 if u > 0 else -1 if u < 0 else 0), 0.1)),
    ("v", "En V", lambda u: (0.6 * u, 0.75)),
    ("escalera", "Escalera", lambda u: (0.45 * u, 0.55 * u)),
    ("foco", "Foco al centro", lambda u: (-0.18 * u, -0.25)),
]
LAYOUT_FN = {k: fn for k, _, fn in LAYOUTS}


def draw_point(u, x, y):
    """Punta del haz en el dibujito: sale de su lugar en la barra (x = 0 es derecho)."""
    return [round(0.88 * u + 2.0 * x, 3), y]


def fx_xy(fx, u, k, n, phase, seed):
    """Posición (x, y) de un cabezal dentro de un movimiento frontal."""
    kind = fx["type"][2:]
    order = (n - 1 - k) if fx.get("reverse") else k
    p = phase - float(fx.get("spread", 0.0)) * order / max(n, 1)
    dx, dy = shape(kind, p, u, seed)
    if fx.get("mirror") and u < 0:
        dx = -dx
    size = float(fx.get("size", 0.5))
    x = float(fx.get("apertura", 0.0)) * u + size * dx
    y = float(fx.get("altura", 0.0)) + float(fx.get("escalon", 0.0)) * u + size * dy
    return max(-1.3, min(1.3, x)), max(-1.3, min(1.3, y))


def preview_paths(kind, params, n=4, samples=72):
    """Recorrido de cada cabezal, para dibujar el ícono del movimiento."""
    fx = dict(DEFAULTS, **params, type="f_" + kind)
    if kind == "canon":  # en el dibujo se separan para que se vea cada haz
        fx["apertura"] = 0.75
    paths = []
    for k in range(n):
        u = head_u(k, n)
        pts = [fx_xy(fx, u, k, n, i / samples, "vista%d" % k) for i in range(samples + 1)]
        paths.append([[round(x, 3), round(y, 3)] for x, y in pts])
    return paths


def catalog():
    return {
        "presets": [{"id": pid, "name": name, "type": "f_" + kind, "params": dict(DEFAULTS, **prm),
                     "paths": preview_paths(kind, prm)} for pid, name, kind, prm in PRESETS],
        "layouts": [{"id": lid, "name": name,
                     "points": [draw_point(head_u(k, 4), *fn(head_u(k, 4))) for k in range(4)]}
                    for lid, name, fn in LAYOUTS],
    }
