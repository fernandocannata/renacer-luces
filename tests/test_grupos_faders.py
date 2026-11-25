"""Grupos, submasters (faders), velocidades, paletas y efectos para el baile."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_efectos_pares import CAB, PAR, dims, make, run  # noqa: E402

from luces import efectos  # noqa: E402


def perimetral(e):
    for fid in PAR[4:]:
        e.update_fixture(fid, grupo="Perimetral")
    for fid in PAR[:4]:
        e.update_fixture(fid, grupo="Trípode")


def test_grupos_por_tipo_y_propios():
    e = make()
    assert [g["name"] for g in e.groups()] == ["Cabezales", "Pares LED"] or \
        [g["name"] for g in e.groups()] == ["Pares LED", "Cabezales"]
    perimetral(e)
    names = {g["name"]: g["ids"] for g in e.groups()}
    assert names["Perimetral"] == PAR[4:] and names["Trípode"] == PAR[:4]
    e.update_fixture(PAR[0], grupo="")  # vacío: vuelve al grupo por tipo
    assert e.group_of(PAR[0]) == "Pares LED"


def test_submaster_baja_solo_su_grupo():
    e = make()
    perimetral(e)
    e.set_attrs(PAR, {"dim": 1})
    e.set_submaster("Perimetral", 0.5)
    fr = run(e, 1.5)[-1]
    d = dims(fr)
    assert d[:4] == [255] * 4
    assert all(126 <= x <= 129 for x in d[4:])


def test_flash_de_grupo():
    e = make()
    perimetral(e)
    e.set_attrs(PAR, {"dim": 0})
    e.set_hold("g:Trípode", True)
    d = dims(e.tick())
    assert d[:4] == [255] * 4 and d[4:] == [0] * 4


def test_velocidad_de_efectos_y_movimientos():
    e = make()
    a = e.add_fx(PAR, "onda", {"beats": 4})
    b = e.add_fx(CAB, "f_circulo", {"beats": 8})
    fx = {f["id"]: f for f in e.fx}
    base_a, base_b = e._fx_rate(fx[a]), e._fx_rate(fx[b])
    e.set_globals(fx_speed=2.0, mov_speed=0.5)
    assert abs(e._fx_rate(fx[a]) - 2 * base_a) < 1e-9
    assert abs(e._fx_rate(fx[b]) - 0.5 * base_b) < 1e-9
    e.set_globals(fx_speed=99)
    assert e.show["settings"]["fx_speed"] == 4.0


def test_tamano_de_movimientos_cero_los_deja_quietos():
    e = make()
    e.set_attrs(CAB, {"dim": 1})
    e.add_fx(CAB, "f_circulo", {"beats": 4, "size": 0.8})
    e.set_globals(mov_size=0.0)
    t = time.monotonic()
    pans = set()
    for k in range(20):
        e.tick(t + k * 0.05)
        pans.add(e.preview[CAB[0]]["p"])
    assert len(pans) == 1
    e.set_globals(mov_size=1.0)
    for k in range(20, 40):
        e.tick(t + k * 0.05)
        pans.add(e.preview[CAB[0]]["p"])
    assert len(pans) > 5


def test_paleta_cambia_los_efectos_de_color():
    e = make()
    f1 = e.add_fx(PAR, "color_beat", {"colors": ["#ff0000", "#00ff00"]})
    e.set_palette("hielo")
    pal = dict((k, c) for k, _, c in efectos.PALETTES)["hielo"]
    assert next(f for f in e.fx if f["id"] == f1)["colors"] == pal
    # los nuevos también la toman
    f2 = e.add_fx(PAR[:2], "confeti", {"colors": ["#ff0000"]})
    assert next(f for f in e.fx if f["id"] == f2)["colors"] == pal
    e.set_palette(None)
    assert e.show["settings"]["paleta"] is None


def test_mezclar_color_a_mano_saca_el_efecto_de_color():
    e = make()
    e.add_fx(PAR, "arcoiris")
    e.set_attrs(PAR[:2], {"r": 1.0})
    ids = [i for f in e.fx for i in f["ids"]]
    assert PAR[0] not in ids and PAR[2] in ids


def test_subida_termina_sola_y_queda_todo_prendido():
    e = make()
    e.set_bpm(120)
    e.set_attrs(PAR, {"dim": 0.4})
    e.add_fx(PAR, "subida", {"beats": 4})  # 4 tiempos a 120 = 2 segundos
    t = time.monotonic()
    for k in range(60):
        e.tick(t + k * 0.05)
    assert not e.fx
    assert all(e.look[p]["dim"] == 1.0 for p in PAR)


def test_color_al_beat_cambia_en_cada_tiempo():
    fx = {"type": "color_beat", "beats": 4, "spread": 0.0, "colors": ["#ff0000", "#00ff00", "#0000ff", "#ffffff"]}
    seen = [efectos.fx_eval(fx, 0, 4, b / 4 + 0.01, "s")[1] for b in range(4)]
    assert len({tuple(c) for c in seen}) == 4


def test_orden_de_las_filas_del_escenario():
    e = make()
    perimetral(e)
    names = lambda: [g["name"] for g in e.groups()]
    assert names() == ["Trípode", "Perimetral", "Cabezales"]  # arriba los pares, abajo los cabezales
    e.set_rows(["Trípode", "Cabezales", "Perimetral"])
    assert names() == ["Trípode", "Cabezales", "Perimetral"]
    e.update_fixture(PAR[0], grupo="Nuevo")  # un grupo nuevo va al final hasta que se acomode
    assert names()[-1] == "Nuevo"
