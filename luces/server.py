"""Servidor local: sirve la interfaz y recibe comandos. Solo biblioteca estándar."""
import json
import mimetypes
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import efectos, frontal
from .dmx_output import create_output
from .os2l import OS2LServer
from .engine import FX_TYPES, Engine
from .fixtures import CHANNEL_ATTRS, PALETTE, Library
from .storage import Storage, base_dir, default_show, safe_name

APP_NAME = "Renacer LightShow"
APP_VERSION = "0.7"


def _read_build():
    """Número de compilación (lo escribe GitHub Actions al armar el .exe)."""
    if os.environ.get("RENACER_BUILD"):
        return os.environ["RENACER_BUILD"]
    try:
        with open(os.path.join(base_dir(), "luces", "BUILD"), encoding="utf-8-sig") as f:
            return f.read().strip() or "dev"
    except Exception:
        return "dev"


APP_BUILD = _read_build()


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class App:
    def __init__(self, output_kind=None):
        self.storage = Storage()
        root = base_dir()
        self.web_dir = os.path.join(root, "web")
        self.library = Library(os.path.join(root, "perfiles"), self.storage.user_profiles_dir)
        show = self._initial_show()
        self.engine = Engine(self.library, show)
        self.output = create_output(output_kind or self.storage.settings.get("salida", "auto"),
                                    self.storage.settings.get("dmx_ritmo", "normal"))
        # el primer cuadro ya sale con el estado real (no todo en cero: evita un salto al abrir)
        self.output.set_frame(self.engine.tick())
        self.output.start()
        # tempo desde VirtualDJ (OS2L): escucha siempre; aplica solo si está prendido
        self.engine.sync_ext = bool(self.storage.settings.get("os2l_sync"))
        self.os2l = OS2LServer(self._on_os2l, self.storage.settings.get("os2l_puerto", 9996))
        self.os2l.start()
        self.saved_version = self.engine.version
        self.last_save = time.monotonic()
        self.stop_event = threading.Event()
        self.server = None
        threading.Thread(target=self._loop, name="motor", daemon=True).start()

    def _initial_show(self):
        name = self.storage.settings.get("ultimo_show", "Mi show")
        try:
            return self.storage.load_show(name)
        except Exception:
            s = default_show(name="Mi show")
            self.storage.save_show(s)
            return s

    # ---------------------------------------------------------- bucle ---
    def _loop(self):
        period = 1.0 / Engine.FRAME_HZ
        nxt = time.perf_counter()
        while not self.stop_event.is_set():
            try:
                self.output.set_frame(self.engine.tick())
                if self.engine.version != self.saved_version and time.monotonic() - self.last_save > 2.0:
                    self.save_now()
            except Exception as e:  # nunca dejar caer el motor en pleno evento
                print("Error en el motor:", e)
            nxt += period
            d = nxt - time.perf_counter()
            if d > 0:
                time.sleep(d)
            else:
                nxt = time.perf_counter()

    def _on_os2l(self, msg):
        if msg.get("evt") == "beat":
            self.engine.external_beat(msg.get("bpm"))

    def sync_status(self):
        e, st = self.engine, self.os2l.status()
        age = time.monotonic() - e.ext_last if e.ext_last else None
        return {"on": e.sync_ext, "connected": st["clients"] > 0, "listening": st["listening"],
                "beats": age is not None and age < 2.5, "bpm": e.ext_bpm, "port": st["port"], "error": st["error"],
                "connections": st["connections"], "messages": st["messages"]}

    def save_now(self):
        self.saved_version = self.engine.version
        self.last_save = time.monotonic()
        try:
            self.storage.save_show(self.engine.export_show())
        except Exception as e:
            print("No se pudo guardar el show:", e)

    def shutdown(self):
        self.engine.set_blackout(True)
        self.engine.tick()
        self.output.set_frame(bytes(512))
        time.sleep(0.15)
        self.save_now()
        self.stop_event.set()
        self.os2l.stop()
        self.output.stop()
        if self.server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    # ------------------------------------------------------ datos UI ---
    def init_payload(self):
        return {
            "app": {"name": APP_NAME, "version": APP_VERSION, "build": APP_BUILD},
            "profiles": self.library.summary(),
            "palette": PALETTE,
            "fx_types": {k: {"family": v[0], "name": v[1]} for k, v in FX_TYPES.items()},
            "frontal": frontal.catalog(),
            "efectos": efectos.catalog(),
            "size_labels": efectos.SIZE_LABEL,
            "channel_attrs": CHANNEL_ATTRS,
            "shows": self.storage.list_shows(),
            "settings": self.storage.settings,
            "lan": "http://%s:%s" % (lan_ip(), self.storage.settings.get("puerto", 8730)),
            "data_dir": self.storage.dir,
            "output": self.output.status(),
            "sync": self.sync_status(),
            "state": self.engine.snapshot(),
        }

    # -------------------------------------------------------- comandos ---
    def command(self, c):
        e = self.engine
        cmd = c.get("cmd")
        ids = c.get("ids") or []
        if cmd == "set_attrs":
            e.set_attrs(ids, c.get("attrs", {}))
        elif cmd == "set_color":
            e.set_color(ids, c["rgbw"])
        elif cmd == "set_wheel":
            e.set_wheel(ids, c["key"], int(c["index"]))
        elif cmd == "set_position":
            e.set_position(ids, c.get("pan"), c.get("tilt"))
        elif cmd == "set_positions":
            e.set_positions(c.get("values", {}))
        elif cmd == "front_layout":
            e.front_layout(ids, c["name"], float(c.get("fade", 0.8)))
        elif cmd == "front_test":
            e.front_test(ids, c.get("x", 0), c.get("y", 0))
        elif cmd == "front_save":
            return e.save_front(ids)
        elif cmd == "rig_set":
            e.set_rig(**{k: c[k] for k in ("span_x", "span_y", "flip_x", "flip_y", "reverse_order") if k in c})
        elif cmd == "nudge":
            e.nudge(ids, c.get("pan", 0), c.get("tilt", 0))
        elif cmd == "clear_all":
            e.clear_all()
        elif cmd == "undo_clear":
            e.undo_clear()
        elif cmd == "fan":
            e.fan(ids, float(c["amount"]))
        elif cmd == "locate":
            e.locate(ids)
        elif cmd == "clear":
            e.clear(ids or None, float(c.get("fade", 0)))
        elif cmd == "add_fx":
            return e.add_fx(ids, c["type"], c.get("params"), bool(c.get("stack")))
        elif cmd == "update_fx":
            e.update_fx(c["id"], c.get("params", {}))
        elif cmd == "remove_fx":
            e.remove_fx(c.get("id"), ids or None)
        elif cmd == "save_scene":
            return e.save_scene(c.get("name"), c.get("id"), c.get("color"))
        elif cmd == "recall_scene":
            e.recall_scene(c["id"], c.get("fade"))
        elif cmd == "update_scene":
            e.update_scene(c["id"], name=c.get("name"), color=c.get("color"))
        elif cmd == "delete_scene":
            e.delete_scene(c["id"])
        elif cmd == "move_scene":
            e.move_scene(c["id"], c.get("delta", 0))
        elif cmd == "save_position":
            return e.save_position(c.get("name"), ids)
        elif cmd == "recall_position":
            e.recall_position(c["id"], ids or None)
        elif cmd == "delete_position":
            e.delete_position(c["id"])
        elif cmd == "add_cue":
            return e.add_cue(c["scene"], c.get("fade"), c.get("wait"))
        elif cmd == "update_cue":
            e.update_cue(c["id"], **{k: c[k] for k in ("fade", "wait", "scene") if k in c})
        elif cmd == "delete_cue":
            e.delete_cue(c["id"])
        elif cmd == "move_cue":
            e.move_cue(c["id"], c.get("delta", 0))
        elif cmd == "go":
            e.go(c.get("index"))
        elif cmd == "back":
            e.back()
        elif cmd == "stop_cues":
            e.stop_cues()
        elif cmd == "master":
            e.set_master(c["value"])
        elif cmd == "blackout":
            e.set_blackout(c["on"])
        elif cmd == "hold":
            if c.get("kind") not in ("flash", "strobe", "strobe2", "humo"):
                raise ValueError("Botón desconocido")
            e.set_hold(c["kind"], c["on"])
        elif cmd == "strobe2_set":
            e.set_strobe2(**{k: c[k] for k in ("sync", "div", "hz", "white") if k in c})
        elif cmd == "sync_set":
            e.set_sync(c.get("on"))
            self.storage.settings["os2l_sync"] = e.sync_ext
            self.storage.save_settings()
        elif cmd == "tap":
            e.tap()
        elif cmd == "bpm":
            e.set_bpm(c["value"])
        elif cmd == "show_settings":
            with e.lock:
                st = e.show["settings"]
                if "fade" in c:
                    st["fade"] = max(0.0, min(30.0, float(c["fade"])))
                if "cue_loop" in c:
                    st["cue_loop"] = bool(c["cue_loop"])
                e.changed()
        elif cmd == "add_fixtures":
            return e.add_fixtures(c["profile"], c.get("count", 1), c.get("address") or None, c.get("name") or None)
        elif cmd == "update_fixture":
            e.update_fixture(c["id"], **{k: c[k] for k in ("name", "address", "invert_pan", "invert_tilt", "profile") if k in c})
        elif cmd == "remove_fixture":
            e.remove_fixture(c["id"])
        elif cmd == "move_fixture":
            e.move_fixture(c["id"], c.get("delta", 0))
        elif cmd == "test_set":
            e.set_test(c["address"], c.get("value"))
        elif cmd == "test_clear":
            e.clear_test()
        elif cmd == "profile_save":
            pid = c.get("new_id") or c["id"]
            pid = "".join(ch for ch in pid.lower().replace(" ", "_") if ch.isalnum() or ch == "_")[:60] or "perfil"
            self.library.save_user_profile(pid, c["data"])
            e.refresh_profiles()
            return pid
        elif cmd == "show_save":
            self.save_now()
        elif cmd == "show_save_as":
            with e.lock:
                e.show["name"] = safe_name(c["name"])
                e.changed()
            self.save_now()
        elif cmd == "show_load":
            self.save_now()
            e.load_show(self.storage.load_show(c["name"]))
            self.saved_version = e.version
            self.storage.settings["ultimo_show"] = safe_name(c["name"])
            self.storage.save_settings()
        elif cmd == "show_new":
            self.save_now()
            name = safe_name(c.get("name") or "Show nuevo")
            if c.get("template") == "vacio":
                s = {"name": name, "fixtures": [], "scenes": [], "cues": [], "positions": [],
                     "settings": {"fade": 1.0, "cue_loop": False}}
            else:
                s = default_show(name=name)
            e.load_show(s)
            self.save_now()
        elif cmd == "show_delete":
            if safe_name(c["name"]) == e.show.get("name"):
                raise ValueError("No se puede borrar el show abierto")
            self.storage.delete_show(c["name"])
            e.changed()
        elif cmd == "output_set":
            kind = c.get("kind") or self.storage.settings.get("salida", "auto")
            rate = c.get("rate") or self.storage.settings.get("dmx_ritmo", "normal")
            old = self.output
            old.stop()
            self.output = create_output(kind, rate)
            self.output.start()
            self.storage.settings["salida"] = kind
            self.storage.settings["dmx_ritmo"] = rate
            self.storage.save_settings()
            e.changed()
        elif cmd == "app_settings":
            if "control_remoto" in c:
                self.storage.settings["control_remoto"] = bool(c["control_remoto"])
            self.storage.save_settings()
            e.changed()
        elif cmd == "quit":
            threading.Thread(target=self.shutdown, daemon=True).start()
        else:
            raise ValueError("Comando desconocido: %s" % cmd)
        return None


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "RenacerLightShow/" + APP_VERSION

        def log_message(self, fmt, *args):
            pass  # silencioso

        def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/events":
                return self._events()
            if path == "/api/init":
                return self._send(200, app.init_payload())
            if path == "/api/profiles":
                return self._send(200, app.library.summary())
            if path == "/":
                path = "/index.html"
            rel = os.path.normpath(path.lstrip("/"))
            full = os.path.join(app.web_dir, rel)
            if rel.startswith("..") or not os.path.isfile(full):
                return self._send(404, {"error": "No encontrado"})
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            with open(full, "rb") as f:
                self._send(200, f.read(), ctype)

        def do_POST(self):
            if urlparse(self.path).path != "/api/cmd":
                return self._send(404, {"error": "No encontrado"})
            try:
                n = int(self.headers.get("Content-Length", 0))
                c = json.loads(self.rfile.read(n) or b"{}")
                res = app.command(c)
                self._send(200, {"ok": True, "result": res})
            except Exception as ex:
                self._send(200, {"ok": False, "error": str(ex)})

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.close_connection = True
            last = -1
            try:
                while not app.stop_event.is_set():
                    eng = app.engine
                    if eng.version != last:
                        last = eng.version
                        snap = eng.snapshot()
                        snap["output"] = app.output.status()
                        snap["shows"] = app.storage.list_shows()
                        snap["app_settings"] = app.storage.settings
                        self._event("sync", snap)
                    self._event("live", {"pv": eng.preview, "beat": round(eng.beat_phase, 3),
                                         "cue": eng.cue_index, "out": app.output.status(),
                                         "sync": app.sync_status()})
                    time.sleep(1 / 15)
                self._event("bye", {})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return

        def _event(self, name, data):
            msg = "event: %s\ndata: %s\n\n" % (name, json.dumps(data, ensure_ascii=False))
            self.wfile.write(msg.encode("utf-8"))
            self.wfile.flush()

    return Handler


def serve(app, host, port):
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    app.server = httpd
    httpd.serve_forever(poll_interval=0.3)
