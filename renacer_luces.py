"""Renacer LightShow — control de iluminación simple para la PC.

Uso:
    python renacer_luces.py            abre el programa
    python renacer_luces.py --sim      sin interfaz (simulador)
    python renacer_luces.py --sin-ventana   solo servidor (para usar desde el celular)
"""
import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

from luces.server import APP_NAME, App, serve


def port_busy(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


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

    app = App(output_kind="sim" if args.sim else None)
    port = args.puerto or int(app.storage.settings.get("puerto", 8730))
    url = "http://127.0.0.1:%d/" % port
    if port_busy(port):
        print("%s ya estaba abierto: muestro la ventana." % APP_NAME)
        app.output.stop()
        open_window(url)
        return
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
