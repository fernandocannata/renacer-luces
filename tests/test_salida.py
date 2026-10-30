import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luces import dmx_output as d  # noqa: E402


class FakeFT:
    """Imita ftd2xx.dll y registra las llamadas."""
    def __init__(self):
        self.calls, self.writes = [], []

    def __getattr__(self, name):
        def fn(*args):
            self.calls.append(name)
            if name == "FT_CreateDeviceInfoList":
                args[0]._obj.value = 1
            if name == "FT_Write":
                self.writes.append(bytes(args[1].raw[: args[2].value]))
            return 0
        return fn


def test_open_dmx_secuencia_y_formato():
    out = d.D2xxOutput()
    out.lib = FakeFT()
    out.set_frame(bytes([10, 20, 30]))
    out.start()
    time.sleep(0.25)
    out.stop()
    c = out.lib.calls
    assert "FT_Open" in c and "FT_SetBaudRate" in c and "FT_SetDataCharacteristics" in c
    # cada cuadro: break on -> break off -> write
    i = c.index("FT_SetBreakOn")
    assert c[i:i + 3] == ["FT_SetBreakOn", "FT_SetBreakOff", "FT_Write"]
    w = out.lib.writes[0]
    assert len(w) == 513 and w[0] == 0 and w[1:4] == bytes([10, 20, 30])
    # ritmo: ~35 cuadros por segundo
    assert 5 <= len(out.lib.writes) <= 12


def test_sin_driver_cae_en_simulador():
    orig = d._load_d2xx
    d._load_d2xx = lambda: None
    try:
        assert isinstance(d.create_output("auto"), (d.SimOutput, d.SerialOutput))
    finally:
        d._load_d2xx = orig
