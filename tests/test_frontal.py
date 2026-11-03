import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luces import frontal  # noqa: E402
from luces.engine import Engine  # noqa: E402
from luces.fixtures import Library  # noqa: E402
from luces.storage import default_show  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAB = ["eq_cab%d" % i for i in range(1, 5)]


def make():
    lib = Library(os.path.join(ROOT, "perfiles"), tempfile.mkdtemp())
    e = Engine(lib, default_show())
    # cabezales colgados: cada uno con su propio pan "de frente", tilt cerca del tope
    for k, fid in enumerate(CAB):
        e.set_position([fid], 0.3 + 0.1 * k, 0.95)
    assert e.save_front(CAB) == 4
    e.set_attrs(CAB, {"dim": 1})
    return e


def test_al_frente_vuelve_a_lo_calibrado():
    e = make()
    e.front_layout(CAB, "abanico", fade=0)
    e.front_layout(CAB, "frente", fade=0)
    for k, fid in enumerate(CAB):
        assert abs(e.look[fid]["pan"] - (0.3 + 0.1 * k)) < 1e-6
        assert abs(e.look[fid]["tilt"] - 0.95) < 1e-6


def test_abanico_abre_y_cruzados_cruza():
    e = make()
    e.front_layout(CAB, "abanico", fade=0)
    xs = [e.pt_to_xy(f, e.look[f]["pan"], e.look[f]["tilt"])[0] for f in CAB]
    assert xs[0] < 0 < xs[-1] and xs == sorted(xs)
    e.front_layout(CAB, "cruzados", fade=0)
    xs = [e.pt_to_xy(f, e.look[f]["pan"], e.look[f]["tilt"])[0] for f in CAB]
    assert xs[0] > 0 > xs[-1]
    # invertir el orden de la barra da vuelta quién es "izquierda"
    e.set_rig(reverse_order=True)
    e.front_layout(CAB, "abanico", fade=0)
    xs = [e.pt_to_xy(f, e.look[f]["pan"], e.look[f]["tilt"])[0] for f in CAB]
    assert xs[0] > 0 > xs[-1]


def test_tilt_sin_lugar_se_achata_no_se_corta():
    e = make()  # frente en tilt 0.95: solo quedan 9° hacia arriba
    p_up = e.xy_to_pt(CAB[0], 0, 1.0)[1]
    p_half = e.xy_to_pt(CAB[0], 0, 0.5)[1]
    p_down = e.xy_to_pt(CAB[0], 0, -1.0)[1]
    assert abs(p_up - 1.0) < 1e-6 and abs(p_half - 0.975) < 1e-6
    assert abs(p_down - (0.95 - 35 / 180)) < 1e-6  # para abajo usa los 35° completos
    # con "arriba/abajo invertido" el lugar libre pasa a ser el otro lado
    e.set_rig(flip_y=True)
    assert e.xy_to_pt(CAB[0], 0, 1.0)[1] < 0.95


def test_movimientos_frontales_corren():
    e = make()
    for p in frontal.catalog()["presets"]:
        e.add_fx(CAB, p["type"], dict(p["params"], name=p["name"]))
        t = time.monotonic()
        seen = set()
        for k in range(30):
            f = e.tick(t + k * 0.1)
            seen.add((f[0], f[2]))  # pan y tilt del cabezal 1
        assert len(seen) > 3, p["id"]
        assert len([x for x in e.fx if x["type"].startswith("f_")]) == 1  # reemplaza al anterior


def test_tijera_se_cruza():
    e = make()
    fx = {"type": "f_tijera", "size": 0.8}
    a = frontal.fx_xy(fx, -1, 0, 4, 0.0, "s")[0]
    b = frontal.fx_xy(fx, -1, 0, 4, 0.5, "s")[0]
    assert a < 0 < b


def test_espejo_y_vista_previa():
    e = make()
    e.add_fx(CAB, "f_barrido", {"mirror": True, "size": 0.7})
    e.tick()
    t = time.monotonic()
    e.tick(t + 0.9)
    pv = e.preview
    assert "x" in pv[CAB[0]] and "y" in pv[CAB[0]]
    # en espejo, los de la izquierda y la derecha se mueven opuestos
    assert pv[CAB[0]]["x"] * pv[CAB[3]]["x"] <= 0.0001


def test_clear_todo_y_deshacer():
    e = make()
    e.set_color(CAB, [1, 0, 0, 0])
    e.add_fx(CAB, "f_circulo")
    e.set_master(0.4)
    e.set_blackout(True)
    e.set_hold("humo", True)
    e.clear_all()
    assert e.fx == [] and e.master == 1.0 and not e.blackout and not e.holds
    assert all(e.look[f]["dim"] == 0 for f in CAB)
    assert e.snapshot()["can_undo_clear"]
    e.undo_clear()
    assert e.fx and e.master == 0.4 and e.look[CAB[0]]["dim"] == 1
    assert not e.snapshot()["can_undo_clear"]
    # el frente calibrado sobrevive al clear
    e.clear_all()
    assert e.rig()["calibrated"] and len(e.rig()["front"]) == 4
