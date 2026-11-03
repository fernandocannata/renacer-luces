"""Recepción de OS2L: VirtualDJ manda el pulso de la música (y botones) por TCP.

En VirtualDJ: Settings → Options → buscar "os2l":
    os2l          = auto
    os2lDirectIp  = 127.0.0.1:9996
y reiniciar VirtualDJ. VirtualDJ se conecta a este servidor y manda objetos JSON
pegados uno atrás del otro, por ejemplo:
    {"evt":"beat","change":false,"pos":123,"bpm":124.0,"strength":0.8}
"""
import json
import socket
import threading
import time


class JsonStream:
    """Separa objetos JSON que llegan pegados o partidos en varios paquetes."""

    def __init__(self):
        self.buf = ""

    def feed(self, text):
        self.buf += text
        out = []
        depth, in_str, esc, start = 0, False, False, None
        i = 0
        while i < len(self.buf):
            ch = self.buf[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}" and depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    chunk = self.buf[start:i + 1]
                    try:
                        obj = json.loads(chunk)
                        if isinstance(obj, dict):
                            out.append(obj)
                    except ValueError:
                        pass  # objeto roto: se descarta
                    self.buf = self.buf[i + 1:]
                    i, start = -1, None
            i += 1
        if depth == 0 and start is None:
            self.buf = self.buf.strip() if "{" in self.buf else ""
        if len(self.buf) > 65536:  # basura sin cerrar: no acumular para siempre
            self.buf = ""
        return out


class OS2LServer:
    def __init__(self, on_message, port=9996, host="127.0.0.1"):
        self.on_message = on_message
        self.port = int(port)
        self.host = host
        self.clients = 0
        self.listening = False
        self.error = ""
        self.last_msg = 0.0
        self._stop = threading.Event()
        self._sock = None

    def start(self):
        threading.Thread(target=self._serve, name="os2l", daemon=True).start()

    def stop(self):
        self._stop.set()
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass

    def status(self):
        return {"listening": self.listening, "clients": self.clients, "port": self.port,
                "error": self.error, "age": round(time.monotonic() - self.last_msg, 1) if self.last_msg else None}

    def _serve(self):
        while not self._stop.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((self.host, self.port))
                s.listen(4)
                s.settimeout(0.5)
                self._sock, self.listening, self.error = s, True, ""
            except OSError as e:
                self.listening = False
                self.error = "No se pudo abrir el puerto %d: %s" % (self.port, e)
                self._stop.wait(3)
                continue
            while not self._stop.is_set():
                try:
                    conn, _ = s.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=self._client, args=(conn,), daemon=True).start()
            self.listening = False
            try:
                s.close()
            except OSError:
                pass

    def _client(self, conn):
        self.clients += 1
        stream = JsonStream()
        conn.settimeout(1.0)
        try:
            while not self._stop.is_set():
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                for msg in stream.feed(data.decode("utf-8", "replace")):
                    self.last_msg = time.monotonic()
                    try:
                        self.on_message(msg)
                    except Exception as e:  # un mensaje raro no corta la conexión
                        print("OS2L:", e)
        except OSError:
            pass
        finally:
            self.clients = max(0, self.clients - 1)
            try:
                conn.close()
            except OSError:
                pass
