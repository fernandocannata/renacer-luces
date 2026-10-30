"""Genera el ícono de Renacer LightShow (misma familia que Renacer Showtime).

Base grafito con borde metálico, tres cabezales en una vara con haces de luz
cruzados, y el botón redondo de la familia en ámbar con un sol.

    python herramientas/hacer_icono.py
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

S = 2048
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def hexf(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def mask(draw_fn, blur=0):
    m = Image.new("L", (S, S), 0)
    draw_fn(ImageDraw.Draw(m))
    if blur:
        m = m.filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(m, dtype=np.float32) / 255


def vgrad(top, bottom, y0=0, y1=S):
    t = np.clip((np.arange(S) - y0) / max(1, y1 - y0), 0, 1)[:, None, None]
    return hexf(top) * (1 - t) + hexf(bottom) * t * np.ones((1, S, 1))


def over(canvas, color, alpha):
    a = alpha[..., None]
    col = color if isinstance(color, np.ndarray) and color.ndim == 3 else np.broadcast_to(color, (S, S, 3))
    canvas[..., :3] = col * a + canvas[..., :3] * (1 - a)
    canvas[..., 3:] = a + canvas[..., 3:] * (1 - a)


def screen(canvas, color, alpha):
    a = alpha[..., None]
    col = np.broadcast_to(color, (S, S, 3)) * a
    canvas[..., :3] = 1 - (1 - canvas[..., :3]) * (1 - col)


def rr(box, r):
    return lambda d: d.rounded_rectangle(box, r, fill=255)


def ell(cx, cy, rx, ry=None):
    ry = rx if ry is None else ry
    return lambda d: d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)


def poly(pts):
    return lambda d: d.polygon(pts, fill=255)


def u(v):
    return v * S


canvas = np.zeros((S, S, 4), np.float32)

# ---------------------------------------------------------------- base ---
m0, R = u(0.05), u(0.205)
outer = mask(rr((m0, m0, S - m0, S - m0), R))
over(canvas, vgrad("#6c7482", "#1b1e23", m0, S - m0), outer)
inset = u(0.012)
inner = mask(rr((m0 + inset, m0 + inset, S - m0 - inset, S - m0 - inset), R - inset))
over(canvas, vgrad("#3b414b", "#1d2026", m0, S - m0), inner)
# brillo suave arriba
gloss = mask(ell(S / 2, u(0.02), u(0.62), u(0.34)), blur=u(0.05)) * inner * 0.10
over(canvas, hexf("#ffffff"), gloss)
# vignette interior (escenario a oscuras)
vig = mask(ell(u(0.42), u(0.62), u(0.42), u(0.36)), blur=u(0.08))
over(canvas, hexf("#121418"), inner * (1 - vig) * 0.45)

# ---------------------------------------------------------- haces de luz ---
truss_y = u(0.215)
heads = [  # x, color del haz, inclinación (desplazamiento al piso), ancho al piso
    (u(0.215), "#ff3fb0", u(0.19), u(0.12)),
    (u(0.425), "#ffc24a", u(0.0), u(0.24)),
    (u(0.635), "#33c8ff", -u(0.21), u(0.12)),
]
floor_y = u(0.905)
yy = np.arange(S, dtype=np.float32)[:, None] * np.ones((1, S), np.float32)
for x, col, dx, w in heads:
    top_y = truss_y + u(0.13)
    beam = mask(poly([(x - u(0.02), top_y), (x + u(0.02), top_y),
                      (x + dx + w / 2, floor_y), (x + dx - w / 2, floor_y)]), blur=u(0.006))
    fade = np.clip(1 - (yy - top_y) / (floor_y - top_y), 0, 1) ** 1.25
    a = beam * fade * inner
    glow = Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(u(0.03)))
    g = np.asarray(glow, np.float32) / 255
    screen(canvas, hexf(col), np.clip(a * 0.85 + g * 0.55, 0, 1))
    # charco de luz en el piso
    pool = mask(ell(x + dx, floor_y - u(0.01), w * 0.62, u(0.035)), blur=u(0.02)) * inner
    screen(canvas, hexf(col), pool * 0.55)

# ---------------------------------------------------------------- vara ---
tx0, tx1, th = u(0.13), u(0.73), u(0.052)
over(canvas, vgrad("#cfd5dd", "#59606b", truss_y - th / 2, truss_y + th / 2),
     mask(rr((tx0, truss_y - th / 2, tx1, truss_y + th / 2), u(0.012))))
lat = mask(lambda d: [d.line((x, truss_y - th / 2 + u(0.008), x + th * 0.8, truss_y + th / 2 - u(0.008)),
                             fill=255, width=int(u(0.006))) for x in np.arange(tx0 + u(0.01), tx1 - th, th * 0.9)])
over(canvas, hexf("#3a3f47"), lat * 0.7)

# ----------------------------------------------------------- cabezales ---
for x, col, dx, w in heads:
    ang = math.atan2(dx, floor_y - truss_y)
    # yugo
    yk = mask(rr((x - u(0.055), truss_y + u(0.02), x + u(0.055), truss_y + u(0.12)), u(0.03)))
    yk_in = mask(rr((x - u(0.035), truss_y + u(0.02), x + u(0.035), truss_y + u(0.14)), u(0.02)))
    over(canvas, vgrad("#9aa2ad", "#3c424b", truss_y, truss_y + u(0.12)), np.clip(yk - yk_in, 0, 1))
    # cabeza (rotada hacia donde apunta el haz)
    hw, hh = u(0.042), u(0.058)
    cx, cy = x, truss_y + u(0.085)
    c, s_ = math.cos(-ang), math.sin(-ang)
    pts = [(cx + px * c - py * s_, cy + px * s_ + py * c) for px, py in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
    head = mask(poly(pts), blur=u(0.002))
    over(canvas, vgrad("#5b626d", "#20242a", cy - hh, cy + hh), head)
    # lente encendida
    lx, ly = cx - math.sin(-ang) * hh * 0.9, cy + math.cos(-ang) * hh * 0.9
    over(canvas, hexf(col) * 0.6 + 0.4, mask(ell(lx, ly, u(0.03), u(0.016))))
    screen(canvas, hexf(col), mask(ell(lx, ly, u(0.05)), blur=u(0.02)) * 0.8)

# ------------------------------------------------- botón de la familia ---
bx, by, br = u(0.72), u(0.725), u(0.19)
shadow = mask(ell(bx + u(0.006), by + u(0.016), br + u(0.006)), blur=u(0.022))
over(canvas, hexf("#000000"), shadow * 0.55)
over(canvas, vgrad("#f0f2f5", "#7f8792", by - br, by + br), mask(ell(bx, by, br)))
ir = br - u(0.032)
over(canvas, vgrad("#3a2a12", "#6b4a1a", by - ir, by + ir), mask(ell(bx, by, ir + u(0.006))))
over(canvas, vgrad("#ffd36a", "#d47a0c", by - ir, by + ir), mask(ell(bx, by, ir)))
# brillo de vidrio
gl = mask(ell(bx, by - ir * 0.42, ir * 0.78, ir * 0.5), blur=u(0.008)) * mask(ell(bx, by, ir))
over(canvas, hexf("#ffffff"), gl * 0.32)
# sol
sun_sh = np.zeros((S, S), np.float32)
def sun(d, ox=0, oy=0):
    d.ellipse((bx + ox - u(0.047), by + oy - u(0.047), bx + ox + u(0.047), by + oy + u(0.047)), fill=255)
    for k in range(8):
        a = k * math.pi / 4
        r0, r1 = u(0.072), u(0.106)
        d.line((bx + ox + r0 * math.cos(a), by + oy + r0 * math.sin(a),
                bx + ox + r1 * math.cos(a), by + oy + r1 * math.sin(a)), fill=255, width=int(u(0.022)))
        for rr_ in (r0, r1):
            px, py = bx + ox + rr_ * math.cos(a), by + oy + rr_ * math.sin(a)
            d.ellipse((px - u(0.011), py - u(0.011), px + u(0.011), py + u(0.011)), fill=255)
over(canvas, hexf("#7a3f00"), mask(lambda d: sun(d, u(0.004), u(0.009)), blur=u(0.006)) * 0.45)
over(canvas, hexf("#fffaf0"), mask(sun))

img = Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8), "RGBA")

# --------------------------------------------------------------- salida ---
web = os.path.join(ROOT, "web")
img.resize((512, 512), Image.LANCZOS).save(os.path.join(web, "icono.png"))
img.resize((64, 64), Image.LANCZOS).save(os.path.join(web, "favicon.png"))
sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
img.resize((256, 256), Image.LANCZOS).save(os.path.join(ROOT, "icono.ico"), sizes=[(s, s) for s in sizes])
print("Ícono generado:", os.path.join(ROOT, "icono.ico"))
