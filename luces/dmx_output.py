"""Salida DMX para interfaces USB tipo "Open DMX" (chip FTDI), como la ElectroTAS TZ-1U.

El protocolo Open DMX es simple: la PC arma cada cuadro DMX a mano
(BREAK + MARK + código 0 + 512 canales a 250 kbaud, 8N2) y lo repite
continuamente. No hace falta instalar nada en Python: se usa el driver
FTDI (ftd2xx.dll) que Windows instala con la interfaz.

Orden de búsqueda:
  1. Driver FTDI D2XX (ftd2xx.dll / libftd2xx.so) vía ctypes.
  2. Puerto COM virtual de FTDI (requiere pyserial, opcional).
  3. Simulador (sin interfaz): el programa funciona igual, sin mandar luz.
"""
import ctypes
import ctypes.util
import os
import sys
import threading
import time

FRAME_PERIOD = 1.0 / 35      # ~35 cuadros por segundo (máximo físico ~44)
BREAK_S = 0.00015            # >88 µs
MAB_S = 0.00002              # >8 µs


class BaseOutput:
    kind = "base"
    label = "Salida"

    def __init__(self):
        self._frame = bytes(512)
        self.connected = False
        self.error = ""
        self.frames_sent = 0
        self._stop = threading.Event()
        self._thread = None

    def set_frame(self, frame):
        self._frame = bytes(frame[:512]).ljust(512, b"\x00")

    def start(self):
        self._thread = threading.Thread(target=self._run, name="dmx-out", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.close()

    def close(self):
        pass

    def status(self):
        return {"kind": self.kind, "label": self.label, "connected": self.connected,
                "error": self.error, "frames": self.frames_sent}

    def _run(self):
        next_t = time.perf_counter()
        while not self._stop.is_set():
            if not self.connected:
                if not self._try_open():
                    self._stop.wait(1.5)
                    continue
                next_t = time.perf_counter()
            try:
                self._send(self._frame)
                self.frames_sent += 1
            except Exception as e:  # interfaz desenchufada, etc.
                self.error = "Se perdió la interfaz: %s" % e
                self.connected = False
                self.close()
                continue
            next_t += FRAME_PERIOD
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.perf_counter()

    def _try_open(self):
        return False

    def _send(self, frame):
        pass


class SimOutput(BaseOutput):
    kind = "sim"
    label = "Simulador (sin interfaz)"

    def _try_open(self):
        self.connected = True
        self.error = ""
        return True

    def _send(self, frame):
        time.sleep(0)  # no hace nada: solo cuenta cuadros


# ------------------------------------------------------------- D2XX ---
FT_OK = 0
FT_BITS_8 = 8
FT_STOP_BITS_2 = 2
FT_PARITY_NONE = 0
FT_FLOW_NONE = 0x0000
FT_PURGE_RX = 1
FT_PURGE_TX = 2


def _load_d2xx():
    names = []
    if sys.platform.startswith("win"):
        names = ["ftd2xx64.dll", "ftd2xx.dll"]
        loader = getattr(ctypes, "WinDLL", ctypes.CDLL)
    else:
        found = ctypes.util.find_library("ftd2xx")
        names = [n for n in (found, "libftd2xx.so", "libftd2xx.dylib") if n]
        loader = ctypes.CDLL
    for n in names:
        try:
            return loader(n)
        except OSError:
            continue
    return None


class D2xxOutput(BaseOutput):
    kind = "d2xx"
    label = "Interfaz USB-DMX (driver FTDI)"

    def __init__(self, device_index=0):
        super().__init__()
        self.lib = _load_d2xx()
        self.index = device_index
        self.handle = ctypes.c_void_p()
        if self.lib is None:
            self.error = "No se encontró el driver FTDI (ftd2xx.dll). Instalalo desde la web de ElectroTAS o de FTDI."

    @classmethod
    def available(cls):
        lib = _load_d2xx()
        if lib is None:
            return False
        n = ctypes.c_ulong(0)
        try:
            return lib.FT_CreateDeviceInfoList(ctypes.byref(n)) == FT_OK and n.value > 0
        except Exception:
            return False

    def _ck(self, st, what):
        if st != FT_OK:
            raise IOError("%s falló (código %s)" % (what, st))

    def _try_open(self):
        if self.lib is None:
            return False
        try:
            n = ctypes.c_ulong(0)
            self.lib.FT_CreateDeviceInfoList(ctypes.byref(n))
            if n.value == 0:
                self.error = "No hay ninguna interfaz USB-DMX conectada."
                return False
            self.handle = ctypes.c_void_p()
            self._ck(self.lib.FT_Open(self.index, ctypes.byref(self.handle)), "Abrir interfaz")
            self._ck(self.lib.FT_ResetDevice(self.handle), "Reset")
            self._ck(self.lib.FT_SetBaudRate(self.handle, ctypes.c_ulong(250000)), "Velocidad")
            self._ck(self.lib.FT_SetDataCharacteristics(self.handle, ctypes.c_ubyte(FT_BITS_8),
                                                        ctypes.c_ubyte(FT_STOP_BITS_2),
                                                        ctypes.c_ubyte(FT_PARITY_NONE)), "Formato")
            self._ck(self.lib.FT_SetFlowControl(self.handle, ctypes.c_ushort(FT_FLOW_NONE),
                                                ctypes.c_ubyte(0), ctypes.c_ubyte(0)), "Flujo")
            self.lib.FT_ClrRts(self.handle)
            self.lib.FT_Purge(self.handle, ctypes.c_ulong(FT_PURGE_RX | FT_PURGE_TX))
            self.connected = True
            self.error = ""
            return True
        except Exception as e:
            self.error = str(e) + " ¿Otro programa (QLC+, FreeStyler, MagicQ) está usando la interfaz?"
            self.close()
            return False

    def _send(self, frame):
        data = b"\x00" + frame
        buf = ctypes.create_string_buffer(data, len(data))
        written = ctypes.c_ulong(0)
        self._ck(self.lib.FT_SetBreakOn(self.handle), "Break")
        time.sleep(BREAK_S)
        self._ck(self.lib.FT_SetBreakOff(self.handle), "Break")
        time.sleep(MAB_S)
        self._ck(self.lib.FT_Write(self.handle, buf, ctypes.c_ulong(len(data)), ctypes.byref(written)), "Envío")

    def close(self):
        if self.lib is not None and self.handle and self.handle.value:
            try:
                self.lib.FT_Close(self.handle)
            except Exception:
                pass
        self.handle = ctypes.c_void_p()
        self.connected = False


# ------------------------------------------------------- puerto COM ---
class SerialOutput(BaseOutput):
    kind = "serial"
    label = "Interfaz USB-DMX (puerto COM)"

    def __init__(self, port=None):
        super().__init__()
        self.port = port
        self.ser = None

    @staticmethod
    def find_ports():
        try:
            from serial.tools import list_ports
        except ImportError:
            return []
        return [p.device for p in list_ports.comports() if getattr(p, "vid", None) == 0x0403]

    def _try_open(self):
        try:
            import serial
        except ImportError:
            self.error = "Para usar el modo puerto COM hace falta pyserial."
            return False
        port = self.port or (self.find_ports() or [None])[0]
        if not port:
            self.error = "No se encontró ningún puerto COM de FTDI."
            return False
        try:
            self.ser = serial.Serial(port, baudrate=250000, bytesize=8, parity="N", stopbits=2,
                                     timeout=0, write_timeout=1)
            self.label = "Interfaz USB-DMX (%s)" % port
            self.connected = True
            self.error = ""
            return True
        except Exception as e:
            self.error = "No se pudo abrir %s: %s" % (port, e)
            return False

    def _send(self, frame):
        self.ser.break_condition = True
        time.sleep(BREAK_S)
        self.ser.break_condition = False
        time.sleep(MAB_S)
        self.ser.write(b"\x00" + frame)
        self.ser.flush()

    def close(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.connected = False


def create_output(kind="auto"):
    """Crea la salida pedida. 'auto' prueba la interfaz real y si no hay, simula."""
    if kind == "sim":
        return SimOutput()
    if kind == "serial":
        return SerialOutput()
    if kind == "d2xx":
        return D2xxOutput()
    if D2xxOutput.available():
        return D2xxOutput()
    if SerialOutput.find_ports():
        return SerialOutput()
    if _load_d2xx() is not None:
        # hay driver pero la interfaz no está enchufada: queda esperando que aparezca
        return D2xxOutput()
    return SimOutput()
