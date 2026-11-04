import os
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luces import efectos  # noqa: E402
from luces.engine import Engine  # noqa: E402
from luces.fixtures import Library  # noqa: E402
from luces.storage import default_show  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAR = ["eq_par%d" % i for i in range(1, 9)]
CAB = ["eq_cab%d" % i for i in range(1, 5)]


def make(refresco=False):
    lib = Library(os.path.join(ROOT, "perfiles"), tempfile.mkdtemp())
    for prof in lib.profiles.values():
        prof["refresco"] = prof.get("refresco", False) and refresco
    e = Engine(lib, default_show())
    e.set_color(PAR, [0, 0, 1, 0])
    return e


def dims(frame):
    return [frame[48 + 8 * i] for i in range(8)]


def run(e, secs=4.0, step=0.05):
    t = time.monotonic()
    return [e.tick(t + k * step) for k in range(int(secs / step))]


@pytest.mark.parametrize("preset", efectos.catalog(), ids=lambda p: p["id"])
def test_cada_efecto_anda_en_los_pares(preset):
    e = make()
    e.add_fx(PAR, preset["type"], dict(preset["params"]))
    frames = run(e)
    seen = {bytes(f[48:112]) for f in frames}
    assert len(seen) >= 2, "el efecto no cambia nada"
    # nunca toca el canal de función del Nebula (debe quedar en 0 = control DMX)
    assert all(f[48 + 8 * i + 6] == 0 for f in frames for i in range(8))


def test_rebote_prende_de_a_poco():
    e = make()
    e.add_fx(PAR, "rebote", {"size": 0.25})
    for f in run(e):
        assert 1 <= sum(1 for d in dims(f) if d > 0) <= 3


def test_relampago_casi_siempre_oscuro():
    e = make()
    e.add_fx(PAR, "relampago", {"size": 1.0})
    frames = run(e, 8, 0.01)
    lit = sum(1 for f in frames if dims(f)[0] > 0)
    assert 0 < lit < len(frames) * 0.2
    # los destellos son blancos (W a full en el Nebula)
    assert any(f[52] == 255 for f in frames if f[48] > 0)


def test_arcoiris_en_cabezales_recorre_la_rueda():
    e = make()
    e.set_attrs(CAB, {"dim": 1})
    e.add_fx(CAB, "arcoiris", {"beats": 4, "spread": 0})
    seen = {f[7] for f in run(e, 4.0)}  # canal de rueda de color del cabezal 1
    assert len(seen) >= 4, seen        # pasa por varios colores de la rueda


def test_efectos_rgb_no_van_en_cabezales():
    e = make()
    with pytest.raises(ValueError):
        e.add_fx(CAB, "fuego")
    e.add_fx(CAB + PAR, "fuego")
    assert e.fx[0]["ids"] == PAR  # con todo elegido, solo se aplica a los que pueden
    e.add_fx(CAB + PAR, "mitades")  # alternar de a pasos sí va en rueda de color
    assert set(e.fx[-1]["ids"]) == set(CAB + PAR)


def test_intensidad_y_color_conviven_y_se_reemplazan_por_familia():
    e = make()
    e.add_fx(PAR, "pulso")
    e.add_fx(PAR, "arcoiris")
    e.add_fx(PAR, "rebote")
    assert sorted(f["type"] for f in e.fx) == ["arcoiris", "rebote"]


def test_catalogo_con_vista_previa():
    cat = efectos.catalog()
    assert len(cat) >= 12
    for p in cat:
        assert len(p["grid"]) == 12 and len(p["grid"][0]) == 8
        assert p["needs"] in ("dim", "color", "rgb")


def test_refresco_de_canales_en_nebula():
    """El Nebula no toma un valor hasta verlo cambiar: el programa los mueve 2 pasos y vuelve."""
    e = make(refresco=True)
    assert e.lib.get("tecshow_nebula_quad14_8ch")["refresco"]
    e.set_color(PAR, [1, 0, 0, 0])            # rojo puro: blanco en 0
    t = time.monotonic()
    frames = [e.tick(t + k * 0.025) for k in range(12)]
    w = [f[52] for f in frames]                # canal 5 (blanco) del Par 1
    r = [f[49] for f in frames]                # canal 2 (rojo)
    assert w[0] == 0 and r[0] == 255           # primero sale el color tal cual
    assert 2 in w and w[-1] == 0               # después el blanco se mueve y vuelve a 0
    assert r[-1] == 255 and min(r) >= 253      # el rojo apenas se toca y vuelve a full
    # cada 2 segundos se refresca aunque no cambie nada
    later = [e.tick(t + 2.5 + k * 0.025)[52] for k in range(8)]
    assert 2 in later and later[-1] == 0
    # nunca toca función ni velocidad
    assert all(e.tick(t + 5 + k * 0.025)[54] == 0 for k in range(10))
