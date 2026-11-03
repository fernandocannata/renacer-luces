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

BREAK_S = 0.00015            # >88 µs
MAB_S = 0.00002              # >8 µs
# Un cuadro completo (código de inicio + 512 canales, 11 bits por byte a 250 kbaud)
# tarda ~22,6 ms en salir por el cable. El próximo BREAK nunca puede llegar antes:
# si llega, corta el cuadro y lo que quedaba en el buffer de la interfaz se cuela
# al comienzo del siguiente, corriendo todos los canales (equipos "locos" o reseteos).
TX_TIME = 513 * 11 / 250000.0
TX_MARGIN = 0.004            # margen por el buffer interno del chip y el USB
RATES = {"normal": 30.0, "seguro": 20.0}


def _hires_timer(on):
    """En Windows, pide timers de 1 ms para que las esperas sean precisas."""
    if not sys.platform.startswith("win"):
        return
    try:
        winmm = ctypes.WinDLL("winmm")
        (winmm.timeBeginPeriod if on else winmm.timeEndPeriod)(1)
    except Exception:
        pass


class BaseOutput:
    kind = "base"
    label = "Salida"

    def __init__(self, rate="normal"):
        self._frame = bytes(512)
        self.connected = False
        self.error = ""
        self.frames_sent = 0
        self.rate = rate if rate in RATES else "normal"
        self.period = 1.0 / RATES[self.rate]
        self.tx_done_at = 0.0     # cuándo termina de salir el último cuadro enviado
        self.fps = 0.0
        self._fps_count, self._fps_t = 0, time.perf_counter()
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
                "error": self.error, "frames": self.frames_sent, "fps": round(self.fps, 1),
                "rate": self.rate}

    def _run(self):
        _hires_timer(True)
        if sys.platform.startswith("win"):  # que Windows no lo postergue
            try:
                k32 = ctypes.WinDLL("kernel32")
                k32.SetThreadPriority(k32.GetCurrentThread(), 2)  # THREAD_PRIORITY_HIGHEST
            except Exception:
                pass
        last_start = 0.0
        try:
            while not self._stop.is_set():
                if not self.connected:
                    if not self._try_open():
                        self._stop.wait(1.5)
                        continue
                # el próximo cuadro empieza recién cuando el anterior terminó de salir
                # y pasó el período elegido, medido desde el comienzo real del anterior
                wait_until = max(last_start + self.period, self.tx_done_at + TX_MARGIN)
                delay = wait_until - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                    continue  # vuelve a chequear (la espera pudo cortarse antes)
                try:
                    last_start = time.perf_counter()
                    self._send(self._frame)
                    self.frames_sent += 1
                    self._count_fps()
                except Exception as e:  # interfaz desenchufada, etc.
                    self.error = "Se perdió la interfaz: %s" % e
                    self.connected = False
                    self.close()
        finally:
            _hires_timer(False)

    def _count_fps(self):
        self._fps_count += 1
        now = time.perf_counter()
        if now - self._fps_t >= 1.0:
            self.fps = self._fps_count / (now - self._fps_t)
            self._fps_count, self._fps_t = 0, now

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
        self.tx_done_at = time.perf_counter() + TX_TIME  # simula el tiempo de cable


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

    def __init__(self, device_index=0, rate="normal"):
        super().__init__(rate)
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

    def _tx_queue(self):
        rx, tx, ev = ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_ulong(0)
        try:
            if self.lib.FT_GetStatus(self.handle, ctypes.byref(rx), ctypes.byref(tx), ctypes.byref(ev)) == FT_OK:
                return tx.value
        except Exception:
            pass
        return 0

    def _send(self, frame):
        data = b"\x00" + frame
        buf = ctypes.create_string_buffer(data, len(data))
        written = ctypes.c_ulong(0)
        # seguridad extra: si el driver todavía tiene bytes del cuadro anterior, esperar
        limit = time.perf_counter() + 0.1
        while self._tx_queue() > 0 and time.perf_counter() < limit:
            time.sleep(0.001)
        self._ck(self.lib.FT_SetBreakOn(self.handle), "Break")
        time.sleep(BREAK_S)
        self._ck(self.lib.FT_SetBreakOff(self.handle), "Break")
        time.sleep(MAB_S)
        t0 = time.perf_counter()
        self._ck(self.lib.FT_Write(self.handle, buf, ctypes.c_ulong(len(data)), ctypes.byref(written)), "Envío")
        if written.value != len(data):
            raise IOError("la interfaz aceptó %d de %d bytes" % (written.value, len(data)))
        # FT_Write vuelve enseguida: los bytes siguen saliendo por el cable ~22,6 ms más
        self.tx_done_at = t0 + TX_TIME

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

    def __init__(self, port=None, rate="normal"):
        super().__init__(rate)
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
        t0 = time.perf_counter()
        self.ser.write(b"\x00" + frame)
        self.ser.flush()
        self.tx_done_at = max(t0 + TX_TIME, time.perf_counter())

    def close(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.connected = False


def create_output(kind="auto", rate="normal"):
    """Crea la salida pedida. 'auto' prueba la interfaz real y si no hay, simula."""
    if kind == "sim":
        return SimOutput(rate)
    if kind == "serial":
        return SerialOutput(rate=rate)
    if kind == "d2xx":
        return D2xxOutput(rate=rate)
    if D2xxOutput.available():
        return D2xxOutput(rate=rate)
    if SerialOutput.find_ports():
        return SerialOutput(rate=rate)
    if _load_d2xx() is not None:
        # hay driver pero la interfaz no está enchufada: queda esperando que aparezca
        return D2xxOutput(rate=rate)
    return SimOutput(rate)
