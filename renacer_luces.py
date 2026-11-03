"""Renacer LightShow — control de iluminación simple para la PC.

Uso:
    python renacer_luces.py            abre el programa
    python renacer_luces.py --sim      sin interfaz (simulador)
    python renacer_luces.py --sin-ventana   solo servidor (para usar desde el celular)
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

from luces.server import APP_BUILD, APP_NAME, APP_VERSION, App, serve
from luces.storage import Storage

OLD_PORTS = (8730, 8731)  # 8730: "Renacer Luces" (versión 1); 8731: Renacer LightShow


def port_busy(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def running_info(port):
    """Qué programa está atendiendo en ese puerto (si es uno de los nuestros)."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/init" % port, timeout=3) as r:
            return json.load(r).get("app", {}) or {}
    except Exception:
        return {}


def ask_quit(port):
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/api/cmd" % port, data=b'{"cmd": "quit"}',
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:
        pass


def wait_port_free(port, seconds=8.0):
    end = time.time() + seconds
    while time.time() < end:
        if not port_busy(port):
            return True
        time.sleep(0.2)
    return not port_busy(port)


def take_over(my_port):
    """Si hay una versión anterior corriendo de fondo, la cierra para que no
    siga manejando la interfaz. Devuelve True si ya está corriendo ESTA versión."""
    me = (APP_NAME, APP_VERSION, APP_BUILD)
    for port in sorted(set(OLD_PORTS) | {my_port}):
        if not port_busy(port):
            continue
        info = running_info(port)
        if not str(info.get("name", "")).startswith("Renacer"):
            continue  # otro programa usa ese puerto: no lo tocamos
        if port == my_port and (info.get("name"), info.get("version"), info.get("build")) == me:
            return True
        print("Cerrando %s %s que seguía abierto de fondo…" % (info.get("name"), info.get("version", "")))
        ask_quit(port)
        if not wait_port_free(port):
            print("No se pudo cerrar la versión anterior en el puerto %d." % port)
        time.sleep(0.6)  # que libere la interfaz USB
    return False


def open_window(url):
    """Abre la interfaz como ventana de aplicación (Edge/Chrome) o en el navegador."""
    if sys.platform.startswith("win"):
        pf = [os.environ.get(k, "") for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
        candidates = []
        for base in pf:
            if base:
                candidates += [os.path.join(base, r"Microsoft\Edge\Application\msedge.exe"),
                               os.path.join(base, r"Google\Chrome\Application\chrome.exe")]
        for exe in candidates:
            if os.path.isfile(exe):
                try:
                    subprocess.Popen([exe, "--app=" + url, "--window-size=1400,880",
                                      "--user-data-dir=" + os.path.join(os.environ.get("LOCALAPPDATA", "."),
                                                                         "RenacerLightShow", "ventana")])
                    return
                except Exception:
                    pass
    webbrowser.open(url)


def main():
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--sim", action="store_true", help="usar simulador en lugar de la interfaz")
    ap.add_argument("--puerto", type=int, default=None)
    ap.add_argument("--sin-ventana", action="store_true", help="no abrir la ventana")
    args = ap.parse_args()

    # el hilo que manda el DMX no debe esperar a los demás más de 1 ms
    sys.setswitchinterval(0.001)
    port = args.puerto or int(Storage().settings.get("puerto", 8731))
    url = "http://127.0.0.1:%d/" % port
    if take_over(port):
        print("%s ya estaba abierto: muestro la ventana." % APP_NAME)
        if not args.sin_ventana:
            open_window(url)
        return
    if port_busy(port):
        print("El puerto %d está ocupado por otro programa." % port)
    app = App(output_kind="sim" if args.sim else None)
    host = "0.0.0.0" if app.storage.settings.get("control_remoto") else "127.0.0.1"
    print("%s funcionando en %s  (Ctrl+C para salir)" % (APP_NAME, url))
    print("Salida DMX:", app.output.status()["label"])
    if not args.sin_ventana:
        threading.Timer(0.6, open_window, args=(url,)).start()
    try:
        serve(app, host, port)
    except KeyboardInterrupt:
        pass
    finally:
        if not app.stop_event.is_set():
            app.shutdown()
        time.sleep(0.2)


if __name__ == "__main__":
    main()
