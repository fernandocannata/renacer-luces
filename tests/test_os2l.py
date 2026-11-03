import os
import socket
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luces.engine import Engine  # noqa: E402
from luces.fixtures import Library  # noqa: E402
from luces.os2l import JsonStream, OS2LServer  # noqa: E402
from luces.storage import default_show  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_mensajes_pegados_y_partidos():
    js = JsonStream()
    out = js.feed('{"evt":"beat","bpm":124.0}{"evt":"btn","name":"Luz {1}","state":"on"}{"evt":"be')
    assert [m["evt"] for m in out] == ["beat", "btn"] and out[1]["name"] == "Luz {1}"
    out = js.feed('at","change":true,"pos":5,"bpm":125.5}\n')
    assert out == [{"evt": "beat", "change": True, "pos": 5, "bpm": 125.5}]
    assert js.feed('basura {"roto": } {"evt":"beat"}') == [{"evt": "beat"}]


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_virtualdj_marca_el_tempo_solo_si_esta_prendido():
    e = Engine(Library(os.path.join(ROOT, "perfiles"), tempfile.mkdtemp()), default_show())
    port = free_port()
    srv = OS2LServer(lambda m: e.external_beat(m.get("bpm")) if m.get("evt") == "beat" else None, port)
    srv.start()
    for _ in range(50):
        if srv.listening:
            break
        time.sleep(0.05)
    vdj = socket.create_connection(("127.0.0.1", port))
    try:
        vdj.sendall(b'{"evt":"beat","change":false,"pos":1,"bpm":128.0,"strength":0.7}')
        time.sleep(0.3)
        assert e.bpm == 120.0 and e.ext_bpm == 128.0      # apagado: no toca el tempo
        assert srv.status()["clients"] == 1
        e.set_sync(True)
        assert e.bpm == 128.0                              # al prender toma el último BPM
        e.beat_phase = 0.6
        vdj.sendall(b'{"evt":"beat","pos":2,"bpm":12')    # llega partido
        time.sleep(0.1)
        vdj.sendall(b'6.4}')
        time.sleep(0.3)
        assert e.bpm == 126.4 and e.beat_phase < 0.05     # sigue el tempo y alinea el pulso
        e.tap(); e.tap()
        assert e.bpm == 126.4                              # con VirtualDJ manda él, el Tap no cambia nada
        e.set_sync(False)
        vdj.sendall(b'{"evt":"beat","bpm":90}')
        time.sleep(0.3)
        assert e.bpm == 126.4
    finally:
        vdj.close()
        srv.stop()
