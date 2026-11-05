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
    for prof in lib.profiles.values():
        prof["refresco"] = False  # acá se prueba otra cosa
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


def test_movimiento_arranca_desde_la_posicion_actual():
    e = make()
    e.front_layout(CAB, "abanico", fade=0)
    base = {f: e.pt_to_xy(f, e.look[f]["pan"], e.look[f]["tilt"]) for f in CAB}
    e.add_fx(CAB, "f_circulo", {"size": 0.3})
    t = time.monotonic()
    xs = {f: [] for f in CAB}
    for k in range(40):
        e.tick(t + k * 0.05)
        for f in CAB:
            xs[f].append(e.preview[f]["x"])
    for f in CAB:
        centro = (max(xs[f]) + min(xs[f])) / 2
        assert abs(centro - base[f][0]) < 0.08, (f, centro, base[f][0])
        assert max(xs[f]) - min(xs[f]) > 0.3  # se está moviendo
    # cambiar de posición no corta el movimiento
    e.front_layout(CAB, "cruzados", fade=0)
    assert any(x["type"] == "f_circulo" for x in e.fx)


def test_clear_deja_los_cabezales_al_frente():
    e = make()
    e.front_layout(CAB, "abanico", fade=0)
    e.clear_all()
    for k, f in enumerate(CAB):
        assert abs(e.look[f]["pan"] - (0.3 + 0.1 * k)) < 1e-6 and abs(e.look[f]["tilt"] - 0.95) < 1e-6


def test_sumar_movimientos():
    e = make()
    e.add_fx(CAB, "f_circulo", {"size": 0.3})
    e.add_fx(CAB, "f_barrido", {"size": 0.5}, stack=True)
    assert sorted(f["type"] for f in e.fx) == ["f_barrido", "f_circulo"]
    # el recorrido sumado es más ancho que cualquiera de los dos solos
    t = time.monotonic()
    xs = []
    for k in range(80):
        e.tick(t + k * 0.05)
        xs.append(e.preview[CAB[0]]["x"])
    assert max(xs) - min(xs) > 1.0
    # sin "sumar", reemplaza a los dos
    e.add_fx(CAB, "f_ocho")
    assert [f["type"] for f in e.fx] == ["f_ocho"]
    for _ in range(3):
        e.add_fx(CAB, "f_vertical", stack=True)
    import pytest
    with pytest.raises(ValueError):
        e.add_fx(CAB, "f_circulo", stack=True)


def test_strobo2_al_tempo_y_libre():
    e = make()
    pars = ["eq_par%d" % i for i in range(1, 9)]
    e.set_color(pars, [1, 0, 0, 0])
    e.set_bpm(120)
    e.set_strobe2(sync=True, div=2)  # 4 destellos por segundo
    e.set_hold("strobe2", True)
    t = time.monotonic()
    on = [e.tick(t + k * 0.01)[48] > 0 for k in range(200)]  # 2 segundos
    flashes = sum(1 for a, b in zip(on, on[1:]) if b and not a)
    assert 7 <= flashes <= 9, flashes
    e.set_strobe2(sync=False, hz=50)  # se limita a 12 por segundo
    assert e.show["settings"]["strobe2"]["hz"] == 12.0
    e.set_strobe2(white=True)
    f = e.tick(t + 5)
    e.set_hold("strobe2", False)
    assert e.tick(t + 6)[48] == 255  # al soltar vuelve a la normalidad


def test_gran_paneo_cubre_todo_el_frente_y_es_lento():
    e = make()
    p = next(x for x in frontal.catalog()["presets"] if x["id"] == "gran_paneo")
    e.set_bpm(120)
    e.add_fx(CAB, p["type"], dict(p["params"]))
    t = time.monotonic()
    xs, ys = [], []
    for k in range(17 * 10):              # 17 segundos (una vuelta son 32 tiempos = 16 s)
        e.tick(t + k * 0.1)
        xs.append(e.preview[CAB[1]]["x"]); ys.append(e.preview[CAB[1]]["y"])
    assert max(xs) - min(xs) > 1.8        # de un costado al otro
    assert max(ys) - min(ys) > 1.4        # y de abajo hacia arriba
    # lento: en medio segundo apenas se mueve
    assert abs(xs[5] - xs[0]) < 0.3


def test_canon_baja_90_grados_desde_lo_mas_alto_en_canon():
    e = make()
    e.set_rig(flip_y=True)  # colgados: "arriba" es tilt hacia abajo -> hay ~171° hacia arriba
    e.front_layout(CAB, "abanico", fade=0)
    pans = [e.look[f]["pan"] for f in CAB]
    p = next(x for x in frontal.PRESETS if x[0] == "canon")
    fid_fx = e.add_fx(CAB, "f_canon", dict(p[3]))
    fx = next(f for f in e.fx if f["id"] == fid_fx)
    ft = e.rig()["front"]
    degs = {}
    for ph in (0.0, 0.375, 0.5):
        e.fx_phase[fid_fx] = ph
        cur = {f: dict(e.look[f]) for f in CAB}
        e._apply_fx(cur, 0.0)
        degs[ph] = [(ft[f][1] - cur[f]["tilt"]) * 180 for f in CAB]  # flip: arriba = tilt menor
        assert [round(cur[f]["pan"], 6) for f in CAB] == [round(x, 6) for x in pans]  # no toca el pan
    # el primero arranca 90° por encima del frente y a mitad de vuelta está 90° más abajo
    assert abs(degs[0.0][0] - 90.0) < 0.5
    assert abs(degs[0.5][0] - 0.0) < 0.5
    # en canon: cada uno va atrasado respecto del anterior
    assert degs[0.375][0] < degs[0.375][1] < degs[0.375][2] < degs[0.375][3]
    assert fx["spread"] == 0.5


def test_canon_se_combina_con_abrir_y_cerrar():
    e = make()
    e.set_rig(flip_y=True)
    pc = dict(next(x for x in frontal.PRESETS if x[0] == "canon")[3])
    pa = dict(next(x for x in frontal.PRESETS if x[0] == "abre_cierra")[3])
    a = e.add_fx(CAB, "f_canon", pc)
    b = e.add_fx(CAB, "f_abanico", pa, stack=True)
    assert {f["id"] for f in e.fx} == {a, b}
    e.fx_phase[a], e.fx_phase[b] = 0.0, 0.5  # canon arriba, abanico bien abierto
    cur = {f: dict(e.look[f]) for f in CAB}
    e._apply_fx(cur, 0.0)
    xs = [e.pt_to_xy(f, cur[f]["pan"], cur[f]["tilt"])[0] for f in CAB]
    assert xs[0] < -0.5 and xs[-1] > 0.5  # abiertos a los costados
    ft = e.rig()["front"]
    assert abs((ft[CAB[0]][1] - cur[CAB[0]]["tilt"]) * 180 - 90.0) < 0.5  # y arriba de todo


def test_frente_recto_y_cruzados_par():
    e = make()
    e.front_layout(CAB, "recto", fade=0)
    xs = [e.pt_to_xy(f, e.look[f]["pan"], e.look[f]["tilt"])[0] for f in CAB]
    assert xs[0] < 0 < xs[-1] and abs(xs[0]) < 0.2  # apenas abiertos: paralelos
    e.front_layout(CAB, "cruzados_par", fade=0)
    xs = [e.pt_to_xy(f, e.look[f]["pan"], e.look[f]["tilt"])[0] for f in CAB]
    assert xs[0] > 0.4 and xs[3] < -0.4   # 1 y 4 se cruzan hacia adentro
    assert xs[1] < -0.4 and xs[2] > 0.4   # 2 y 3 abren hacia afuera


def test_altura_no_cambia_el_costado():
    e = make()
    e.set_rig(flip_y=True)
    e.front_layout(CAB, "cruzados_par", fade=0)
    before = e.movers_xy()
    e.front_height(CAB, 0.6)
    after = e.movers_xy()
    for f in CAB:
        assert abs(after[f][0] - before[f][0]) < 0.01
        assert abs(after[f][1] - 0.6) < 0.01
