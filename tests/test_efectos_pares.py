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


def make():
    e = Engine(Library(os.path.join(ROOT, "perfiles"), tempfile.mkdtemp()), default_show())
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
