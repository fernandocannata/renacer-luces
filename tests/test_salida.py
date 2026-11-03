import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luces import dmx_output as d  # noqa: E402


class FakeFT:
    """Imita ftd2xx.dll: registra cada llamada con su hora real."""
    def __init__(self):
        self.calls, self.writes, self.log = [], [], []

    def __getattr__(self, name):
        def fn(*args):
            self.calls.append(name)
            self.log.append((name, time.perf_counter()))
            if name == "FT_CreateDeviceInfoList":
                args[0]._obj.value = 1
            if name == "FT_Write":
                n = args[2].value
                self.writes.append(bytes(args[1].raw[:n]))
                args[3]._obj.value = n
            return 0
        return fn


def run_output(seconds, rate="normal", jitter=0.0):
    out = d.D2xxOutput(rate=rate)
    out.lib = FakeFT()
    out.set_frame(bytes([10, 20, 30]))
    real_sleep = time.sleep
    if jitter:
        # la PC se demora al azar al despertar (Windows ocupado, otros hilos…)
        d.time.sleep = lambda s: real_sleep(s + random.uniform(0, jitter))
    try:
        out.start()
        real_sleep(seconds)
        out.stop()
    finally:
        d.time.sleep = real_sleep
    return out


def gaps_write_to_break(log):
    gaps, last_write = [], None
    for name, t in log:
        if name == "FT_Write":
            last_write = t
        elif name == "FT_SetBreakOn" and last_write is not None:
            gaps.append(t - last_write)
    return gaps


def test_open_dmx_secuencia_y_formato():
    out = run_output(0.4)
    c = out.lib.calls
    assert "FT_Open" in c and "FT_SetBaudRate" in c and "FT_SetDataCharacteristics" in c
    i = c.index("FT_SetBreakOn")
    assert c[i:i + 3] == ["FT_SetBreakOn", "FT_SetBreakOff", "FT_Write"]
    w = out.lib.writes[0]
    assert len(w) == 513 and w[0] == 0 and w[1:4] == bytes([10, 20, 30])


def test_nunca_corta_un_cuadro_aunque_la_pc_se_demore():
    """El BREAK siguiente no puede llegar antes de que el cuadro anterior salga entero."""
    out = run_output(1.2, jitter=0.012)
    gaps = gaps_write_to_break(out.lib.log)
    assert len(gaps) > 10
    assert min(gaps) >= d.TX_TIME + d.TX_MARGIN * 0.9, min(gaps)


def test_ritmos():
    normal = run_output(1.0)
    seguro = run_output(1.0, rate="seguro")
    assert 24 <= len(normal.lib.writes) <= 32
    assert 15 <= len(seguro.lib.writes) <= 21
    assert normal.status()["rate"] == "normal" and seguro.status()["rate"] == "seguro"


def test_sin_driver_cae_en_simulador():
    orig = d._load_d2xx
    d._load_d2xx = lambda: None
    try:
        assert isinstance(d.create_output("auto"), (d.SimOutput, d.SerialOutput))
    finally:
        d._load_d2xx = orig
