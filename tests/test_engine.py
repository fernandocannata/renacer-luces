import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luces.engine import Engine  # noqa: E402
from luces.fixtures import Library, nearest_slot  # noqa: E402
from luces.storage import default_show  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make():
    lib = Library(os.path.join(ROOT, "perfiles"), tempfile.mkdtemp())
    return Engine(lib, default_show())


CAB = ["eq_cab%d" % i for i in range(1, 5)]
PAR = ["eq_par%d" % i for i in range(1, 9)]


def ch(frame, addr):
    return frame[addr - 1]


def test_patch_por_defecto():
    e = make()
    assert len(e.show["fixtures"]) == 12
    assert e.conflicts() == []
    f = e.tick()
    assert len(f) == 512
    # todos los dimmers en cero (cabezales: canal 6; pares: canal 1)
    assert all(ch(f, 1 + 12 * i + 5) == 0 for i in range(4))
    assert all(ch(f, 49 + 8 * i) == 0 for i in range(8))


def test_par_color_y_dimmer():
    e = make()
    e.set_color(["eq_par1"], [1, 0, 0, 0])   # rojo, se prende solo
    f = e.tick()
    # par1 en dirección 49: dim, R, G, B, W, strobo, función, velocidad
    assert ch(f, 49) == 255 and ch(f, 50) == 255 and ch(f, 51) == 0 and ch(f, 53) == 0
    assert ch(f, 55) == 0  # función en 0 = control DMX
    e.set_master(0.5)
    assert ch(e.tick(), 49) == 128


def test_cabezal_posicion_16bit_e_invertido():
    e = make()
    e.set_attrs(["eq_cab1"], {"dim": 1})
    e.set_position(["eq_cab1"], 0.25, 0.75)
    f = e.tick()
    pan16 = (ch(f, 1) << 8) | ch(f, 2)
    assert abs(pan16 - round(0.25 * 65535)) <= 1
    e.update_fixture("eq_cab1", invert_pan=True)
    f = e.tick()
    assert abs(((ch(f, 1) << 8) | ch(f, 2)) - round(0.75 * 65535)) <= 1


def test_rueda_de_color_por_cercania():
    e = make()
    slots = e.lib.get("venetian_vt_b100_12ch")["color_wheel"]
    assert slots[nearest_slot(slots, (0, 0, 1))]["nombre"] == "Azul"
    assert slots[nearest_slot(slots, (1, 1, 1))]["nombre"] == "Blanco"
    assert slots[nearest_slot(slots, (1, 0, 0))]["nombre"] == "Rojo"
    e.set_color(["eq_cab1"], [0, 0, 1, 0])
    f = e.tick()
    assert ch(f, 8) == 90  # dmx del azul en el perfil


def test_blackout_flash_strobo_humo():
    e = make()
    e.set_color(PAR, [0, 0, 1, 0])
    e.set_blackout(True)
    assert ch(e.tick(), 49) == 0
    e.set_hold("flash", True)
    f = e.tick()
    assert ch(f, 49) == 255 and ch(f, 53) == 255 and ch(f, 52) == 0  # blanco a full
    e.set_hold("flash", False)
    e.set_hold("strobe", True)
    assert ch(e.tick(), 54) == 255  # canal de strobo al máximo
    e.set_hold("strobe", False)
    e.add_fixtures("generico_humo_1ch")
    hid = e.show["fixtures"][-1]["id"]
    addr = e.fixture(hid)["address"]
    assert ch(e.tick(), addr) == 0
    e.set_hold("humo", True)
    assert ch(e.tick(), addr) == 255


def test_escena_con_fundido():
    e = make()
    e.set_color(PAR, [1, 0, 0, 0])
    a = e.save_scene("Roja")
    e.clear()
    assert ch(e.tick(), 50) == 0
    t0 = time.monotonic()
    e.recall_scene(a, fade=2.0)
    mid = ch(e.tick(t0 + 1.0), 50)
    assert 60 < mid < 200, mid
    assert ch(e.tick(t0 + 2.5), 50) == 255


def test_cambio_manual_durante_fundido_es_inmediato():
    e = make()
    e.set_color(PAR, [1, 0, 0, 0])
    a = e.save_scene("Roja")
    e.clear()
    t0 = time.monotonic()
    e.recall_scene(a, fade=4.0)
    e.set_attrs(["eq_par1"], {"dim": 0.0})
    assert ch(e.tick(t0 + 1), 49) == 0
    assert ch(e.tick(t0 + 1), 57) > 0  # el resto sigue el fundido


def test_efectos():
    e = make()
    fid = e.add_fx(PAR, "pulso")
    fx = e.fx[0]
    assert fx["ids"] == PAR and fx["beats"] == 8
    # la persecución deja ~1 de 8 pares prendido a la vez
    on = []
    t = time.monotonic()
    for k in range(20):
        f = e.tick(t + k * 0.11)
        on.append(sum(1 for i in range(8) if ch(f, 49 + 8 * i) > 0))
    assert max(on) <= 2 and sum(on) > 0
    # agregar otro efecto de intensidad reemplaza al anterior
    e.add_fx(PAR, "onda")
    assert len(e.fx) == 1 and e.fx[0]["type"] == "onda"
    # color y movimiento conviven
    e.add_fx(PAR, "arcoiris")
    e.add_fx(CAB, "circulo")
    assert {f["type"] for f in e.fx} == {"onda", "arcoiris", "circulo"}
    e.set_attrs(CAB, {"dim": 1})
    p1 = ch(e.tick(t + 3), 1)
    p2 = ch(e.tick(t + 4), 1)
    assert p1 != p2  # el círculo mueve el pan
    e.remove_fx(fid)  # id viejo ya no existe: no rompe
    e.remove_fx(ids=PAR)
    assert {f["type"] for f in e.fx} == {"circulo"}


def test_efecto_posicion_solo_en_cabezales():
    e = make()
    e.add_fx(CAB + PAR, "ocho")
    assert e.fx[0]["ids"] == CAB


def test_secuencia_go_back_y_autoseguir():
    e = make()
    e.set_color(PAR, [1, 0, 0, 0]); a = e.save_scene("A")
    e.set_color(PAR, [0, 1, 0, 0]); b = e.save_scene("B")
    e.add_cue(a, fade=0)
    e.add_cue(b, fade=0, wait=1.0)
    e.add_cue(a, fade=0)
    e.go()
    assert e.cue_index == 0 and ch(e.tick(), 50) == 255
    e.go()
    t = time.monotonic()
    assert e.cue_index == 1 and ch(e.tick(t), 51) == 255
    e.tick(t + 1.2)  # autoseguir después de 1 s
    assert e.cue_index == 2
    e.back()
    assert e.cue_index == 1
    e.go(); e.go()  # al final, sin loop, se queda
    assert e.cue_index == 2


def test_abanico_y_posiciones():
    e = make()
    e.set_position(CAB, 0.5, 0.5)
    e.fan(CAB, 1.0)
    pans = [e.look[i]["pan"] for i in CAB]
    assert pans == sorted(pans) and pans[0] < 0.5 < pans[-1]
    pid = e.save_position("Público", CAB)
    e.set_position(CAB, 0.1, 0.1)
    e.recall_position(pid, fade=0)
    assert [round(e.look[i]["pan"], 3) for i in CAB] == [round(p, 3) for p in pans]


def test_tap_tempo():
    e = make()
    e.taps = []
    base = time.monotonic()
    import luces.engine as m
    real = m.time.monotonic
    try:
        for k in range(4):
            m.time.monotonic = lambda k=k: base + k * 0.5
            e.tap()
    finally:
        m.time.monotonic = real
    assert e.bpm == 120.0


def test_probar_canales_y_conflictos():
    e = make()
    e.set_test(5, 200)
    assert ch(e.tick(), 5) == 200
    e.clear_test()
    assert ch(e.tick(), 5) == 0
    e.update_fixture("eq_par1", address=1)  # pisa al cabezal 1
    assert e.conflicts()


def test_guardar_y_recargar_show():
    e = make()
    e.set_color(PAR, [0, 0, 1, 0])
    e.add_fx(PAR, "onda")
    data = e.export_show()
    e2 = Engine(e.lib, data)
    assert e2.look["eq_par3"]["b"] == 1 and e2.fx[0]["type"] == "onda"


def test_rotacion_del_prisma_en_el_canal_del_prisma():
    e = make()
    e.set_attrs(["eq_cab1"], {"dim": 1})
    e.set_wheel(["eq_cab1"], "prism", 1)
    assert ch(e.tick(), 10) == 128                 # prisma fijo
    e.set_attrs(["eq_cab1"], {"prot": 0.0001})
    assert ch(e.tick(), 10) == 128                 # rotación en cero: sigue fijo
    e.set_attrs(["eq_cab1"], {"prot": 0.01})
    assert 145 <= ch(e.tick(), 10) <= 147          # rotación lenta
    e.set_attrs(["eq_cab1"], {"prot": 1.0})
    assert ch(e.tick(), 10) == 255                 # rotación rápida
    assert ch(e.tick(), 11) == 0                   # el canal 11 no recibe la rotación


def test_perfil_guardado_con_gobos_viejos_se_corrige(tmp_path):
    import json
    from luces.fixtures import Library, caps
    old = json.load(open(os.path.join(ROOT, "perfiles", "venetian_vt_b100_12ch.json"), encoding="utf-8"))
    old["gobo"] = [{"nombre": n, "dmx": v} for n, v in zip(["Abierto"] + ["Gobo %d" % k for k in range(1, 10)],
                                                         [0, 14, 28, 42, 56, 70, 84, 98, 112, 126])]
    old.pop("prism_rot", None)
    (tmp_path / "venetian_vt_b100_12ch.json").write_text(json.dumps(old), encoding="utf-8")
    lib = Library(os.path.join(ROOT, "perfiles"), str(tmp_path))
    p = lib.get("venetian_vt_b100_12ch")
    assert p["origen"] == "usuario"
    assert max(g["dmx"] for g in p["gobo"]) == 76          # ninguno en la zona que tiembla
    assert p["prism_rot"] == {"min": 145, "max": 255} and "prot" in caps(p)
    # un perfil que el usuario ya calibró no se toca
    old["gobo"] = [{"nombre": "Abierto", "dmx": 0}, {"nombre": "Gobo 1", "dmx": 10}]
    (tmp_path / "venetian_vt_b100_12ch.json").write_text(json.dumps(old), encoding="utf-8")
    lib.reload()
    assert [g["dmx"] for g in lib.get("venetian_vt_b100_12ch")["gobo"]] == [0, 10]


def test_gobos_grabados_toman_su_nombre(tmp_path):
    import json
    from luces.fixtures import Library
    prof = json.load(open(os.path.join(ROOT, "perfiles", "venetian_vt_b100_12ch.json"), encoding="utf-8"))
    vals = [0, 12, 22, 32, 42, 52, 62, 72]
    prof["gobo"] = [{"nombre": "Abierto" if v == 0 else "Gobo %d" % i, "dmx": v} for i, v in enumerate(vals)]
    (tmp_path / "venetian_vt_b100_12ch.json").write_text(json.dumps(prof), encoding="utf-8")
    lib = Library(os.path.join(ROOT, "perfiles"), str(tmp_path))
    assert [g["nombre"] for g in lib.get("venetian_vt_b100_12ch")["gobo"]] == [
        "Abierto", "Círculo", "Serpiente", "Cruz", "Margarita", "Estrella", "Espiral", "Flor"]


def test_medios_colores_no_se_eligen_solos():
    from luces.fixtures import nearest_slot
    slots = [{"nombre": "Blanco", "dmx": 0, "hex": "#ffffff"},
             {"nombre": "Rojo / Verde", "dmx": 8, "hex": "#ff2020", "hex2": "#24e04a"},
             {"nombre": "Rojo", "dmx": 12, "hex": "#ff2020"}]
    assert slots[nearest_slot(slots, (1, 0, 0))]["nombre"] == "Rojo"
