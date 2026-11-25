"""Motor de luces: estado, fundidos, efectos, escenas, secuencia y salida DMX."""
import colorsys
import copy
import math
import random
import threading
import time
import uuid

from . import efectos, frontal
from .fixtures import (CONTINUOUS, PALETTE, apply_color, caps, default_look,
                       hex_to_rgb, nearest_slot, rgb_to_hex, rgbw_to_rgb)

# ---------------------------------------------------------------- efectos ---
FX_TYPES = {
    # tipo: (familia, nombre visible)
    "circulo": ("pos", "Círculo"),
    "ocho": ("pos", "Ocho"),
    "paneo": ("pos", "Paneo"),
    "tilt": ("pos", "Tilt"),
}
# intensidad y color (módulo efectos)
for _k, (_fam, _n, _need) in efectos.TYPES.items():
    FX_TYPES[_k] = (_fam, _n)
# movimientos frontales (cabezales mirando al público)
for _k, _n in frontal.SHAPES.items():
    FX_TYPES["f_" + _k] = ("pos", _n)

# Strobo 2: strobo por software, al tempo o a velocidad libre
STROBE2_DEFAULT = {"sync": True, "div": 2, "hz": 6.0, "white": False}
STROBE2_DIVS = (0.5, 1, 2, 4)        # destellos por tiempo
STROBE2_MAX_HZ = 12.0                 # con ~30 cuadros/s, más rápido se pierde
MAX_MOVES = 4                         # movimientos sumados como máximo

# nombre de grupo por defecto según el tipo de equipo
TYPE_GROUP = {"cabezal": "Cabezales", "par": "Pares LED", "strobo": "Strobos", "humo": "Humo", "dimmer": "Dimmers"}
SPEED_RANGE = (0.25, 4.0)   # velocidad de efectos y movimientos: x0,25 a x4
SIZE_MAX = 1.5              # tamaño de movimientos: hasta 150 %

RIG_DEFAULT = {"front": {}, "span_x": 60.0, "span_y": 35.0, "flip_x": False, "flip_y": False,
               "reverse_order": False, "calibrated": False}


def new_id(prefix):
    return prefix + uuid.uuid4().hex[:8]


def frac(x):
    return x - math.floor(x)


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


class Engine:
    FRAME_HZ = 40

    def __init__(self, library, show, on_change=None):
        self.lib = library
        self.lock = threading.RLock()
        self.on_change = on_change or (lambda: None)
        self.version = 0
        # estado en vivo
        self.look = {}
        self.fx = []
        self.fade = None
        self.master = 1.0
        self.blackout = False
        self.holds = set()          # 'flash', 'strobe', 'humo'
        self.bpm = 120.0
        self.taps = []
        self.sync_ext = False      # seguir el tempo de VirtualDJ (OS2L)
        self.ext_bpm = None
        self.ext_last = 0.0
        self.test = {}              # dirección DMX (1..512) -> valor 0..255
        self.cue_index = -1
        self.cue_next_at = None
        self.fx_phase = {}
        self.last_t = time.monotonic()
        self.beat_phase = 0.0
        self.preview = {}
        self.frame = bytes(512)
        self._undo = None
        self._refresh = {}  # equipos que no toman un valor hasta verlo cambiar
        self._wake = {}     # equipos "despertándose": id -> momento de inicio
        self.load_show(show)

    # ------------------------------------------------------------ show ---
    def load_show(self, show):
        with self.lock:
            show.setdefault("fixtures", [])
            show.setdefault("scenes", [])
            show.setdefault("cues", [])
            show.setdefault("positions", [])
            st = show.setdefault("settings", {})
            st.setdefault("fade", 1.0)
            st.setdefault("cue_loop", False)
            st.setdefault("strobe2", {})
            st.setdefault("submasters", {})     # grupo -> 0..1
            st.setdefault("fx_speed", 1.0)
            st.setdefault("mov_speed", 1.0)
            st.setdefault("mov_size", 1.0)
            st.setdefault("paleta", None)
            for k, v in STROBE2_DEFAULT.items():
                st["strobe2"].setdefault(k, v)
            self.show = show
            self.rig()
            self._undo = None
            saved = show.get("state", {})
            self.look = {}
            for fx in show["fixtures"]:
                prof = self.lib.get(fx["profile"])
                base = default_look(prof) if prof else {}
                base.update({k: v for k, v in saved.get("look", {}).get(fx["id"], {}).items() if k in base})
                self.look[fx["id"]] = base
            self.fx = copy.deepcopy(saved.get("fx", []))
            self.master = saved.get("master", 1.0)
            self.bpm = saved.get("bpm", 120.0)
            self.fade = None
            self.cue_index = -1
            self.cue_next_at = None
            self.test = {}
            self.changed()

    def export_show(self):
        with self.lock:
            s = copy.deepcopy(self.show)
            s["state"] = {"look": self._materialize(time.monotonic()), "fx": copy.deepcopy(self.fx),
                          "master": self.master, "bpm": self.bpm}
            return s

    def changed(self):
        self.version += 1
        self.on_change()

    def fixture(self, fid):
        for f in self.show["fixtures"]:
            if f["id"] == fid:
                return f
        return None

    def group_of(self, fid):
        """Grupo del equipo: el que le puso el usuario o, si no, según su tipo."""
        f = self.fixture(fid)
        if not f:
            return ""
        g = (f.get("grupo") or "").strip()
        if g:
            return g
        prof = self.lib.get(f["profile"]) or {}
        t = prof.get("tipo", "otro")
        return TYPE_GROUP.get(t, t.capitalize())

    ROW_RANK = {"par": 0, "strobo": 1, "dimmer": 2, "cabezal": 3, "humo": 9}
    LUGARES = ("truss", "piso")

    def _rows(self):
        """Filas guardadas del escenario: [{name, lugar}] (acepta el formato viejo, solo nombres)."""
        out = []
        for r in self.show["settings"].get("filas") or []:
            if isinstance(r, str):
                r = {"name": r}
            name = str(r.get("name", "")).strip()[:40]
            if name and all(x["name"] != name for x in out):
                out.append({"name": name, "lugar": r.get("lugar") if r.get("lugar") in self.LUGARES else None})
        return out

    def groups(self):
        """Filas del escenario, de arriba hacia abajo: [{name, ids, tipo, lugar}].
        Cada grupo es una fila: colgada de un truss o apoyada en el piso. Por defecto
        arriba los pares y abajo los cabezales (el humo, en el piso); el usuario las
        reordena, agrega truss o pisos vacíos y arrastra equipos de una a otra."""
        out = {}
        for f in self.show["fixtures"]:
            g = self.group_of(f["id"])
            prof = self.lib.get(f["profile"]) or {}
            e = out.setdefault(g, {"name": g, "ids": [], "tipo": prof.get("tipo", "otro")})
            e["ids"].append(f["id"])
        groups = sorted(out.values(), key=lambda g: self.ROW_RANK.get(g["tipo"], 5))
        rows = self._rows()
        for r in rows:  # filas creadas a mano todavía vacías
            if r["name"] not in out:
                groups.append({"name": r["name"], "ids": [], "tipo": "vacio"})
        meta = {r["name"]: r for r in rows}
        for g in groups:
            lugar = (meta.get(g["name"]) or {}).get("lugar")
            g["lugar"] = lugar or ("piso" if g["tipo"] == "humo" else "truss")
        if rows:
            pos = {r["name"]: i for i, r in enumerate(rows)}
            base = {g["name"]: i for i, g in enumerate(groups)}
            groups.sort(key=lambda g: pos.get(g["name"], len(rows) + base[g["name"]]))
        return groups

    def _save_rows(self, groups):
        self.show["settings"]["filas"] = [{"name": g["name"], "lugar": g["lugar"]} for g in groups][:40]

    def set_rows(self, names):
        """Orden de las filas (nombres de grupo, de arriba hacia abajo)."""
        with self.lock:
            cur = {g["name"]: g for g in self.groups()}
            order = [cur[n] for n in names if n in cur] + [g for n, g in cur.items() if n not in names]
            self._save_rows(order)
            self.changed()

    def add_row(self, lugar="truss", name=None):
        """Agrega un truss (o un lugar en el piso) vacío, al final de los de su tipo."""
        with self.lock:
            lugar = lugar if lugar in self.LUGARES else "truss"
            groups = self.groups()
            names = {g["name"] for g in groups}
            if name:
                name = str(name).strip()[:40]
                if name in names:
                    raise ValueError("Ya hay una fila con ese nombre")
            else:
                base, k = ("Truss" if lugar == "truss" else "Piso"), 1
                while "%s %d" % (base, k) in names:
                    k += 1
                name = "%s %d" % (base, k)
            groups.append({"name": name, "ids": [], "tipo": "vacio", "lugar": lugar})
            self._save_rows(groups)
            self.changed()
            return name

    def update_row(self, name, new_name=None, lugar=None):
        """Cambia el nombre de una fila (y el grupo de sus equipos) o si cuelga o va al piso."""
        with self.lock:
            groups = self.groups()
            g = next((x for x in groups if x["name"] == name), None)
            if not g:
                raise ValueError("No existe esa fila")
            if lugar in self.LUGARES:
                g["lugar"] = lugar
            if new_name is not None:
                new_name = str(new_name).strip()[:40]
                if not new_name:
                    raise ValueError("Poné un nombre")
                if new_name != name:
                    if any(x["name"] == new_name for x in groups):
                        raise ValueError("Ya hay una fila con ese nombre")
                    for fid in g["ids"]:
                        self.fixture(fid)["grupo"] = new_name
                    subs = self.show["settings"].get("submasters", {})
                    if name in subs:
                        subs[new_name] = subs.pop(name)
                    self.holds.discard("g:" + name)
                    g["name"] = new_name
            self._save_rows(groups)
            self.changed()

    def remove_row(self, name):
        with self.lock:
            groups = self.groups()
            g = next((x for x in groups if x["name"] == name), None)
            if not g:
                return
            if g["ids"]:
                raise ValueError("Primero pasá sus equipos a otra fila (arrastrándolos) o borralos en Equipos y direcciones")
            self._save_rows([x for x in groups if x["name"] != name])
            self.show["settings"].get("submasters", {}).pop(name, None)
            self.changed()

    def place_fixture(self, fid, row, before=None):
        """Pasa un equipo a una fila (truss o piso) y lo deja antes de 'before' (o al final de la fila)."""
        with self.lock:
            f = self.fixture(fid)
            if not f:
                raise ValueError("Equipo inexistente")
            groups = self.groups()
            if not any(g["name"] == row for g in groups):
                raise ValueError("No existe esa fila")
            self._save_rows(groups)  # que el orden de las filas no cambie al mover equipos
            f["grupo"] = row
            lst = self.show["fixtures"]
            lst.remove(f)
            if before and before != fid and self.fixture(before):
                lst.insert(lst.index(self.fixture(before)), f)
            else:
                last = max((i for i, x in enumerate(lst) if self.group_of(x["id"]) == row), default=None)
                lst.insert(len(lst) if last is None else last + 1, f)
            self.changed()

    def set_submaster(self, group, value):
        with self.lock:
            self.show["settings"]["submasters"][str(group)[:40]] = clamp(float(value))
            self.changed()

    def set_globals(self, **kw):
        """Velocidad de efectos/movimientos y tamaño de movimientos (los faders de Efectos)."""
        with self.lock:
            st = self.show["settings"]
            for k in ("fx_speed", "mov_speed"):
                if k in kw:
                    st[k] = round(clamp(float(kw[k]), *SPEED_RANGE), 3)
            if "mov_size" in kw:
                st["mov_size"] = round(clamp(float(kw["mov_size"]), 0.0, SIZE_MAX), 3)
            self.changed()

    def set_palette(self, pid):
        """Paleta rápida: cambia los colores de los efectos de color que están andando."""
        with self.lock:
            pal = {k: cols for k, _, cols in efectos.PALETTES}
            if pid and pid not in pal:
                raise ValueError("Paleta desconocida")
            self.show["settings"]["paleta"] = pid or None
            if pid:
                for fx in self.fx:
                    if fx["type"] in efectos.PALETTE_TYPES:
                        fx["colors"] = list(pal[pid])
            self.changed()

    def profile_of(self, fid):
        f = self.fixture(fid)
        return self.lib.get(f["profile"]) if f else None

    # ----------------------------------------------------- fundidos ---
    def _materialize(self, now):
        """Estado actual teniendo en cuenta un fundido en curso."""
        if not self.fade:
            return copy.deepcopy(self.look)
        f = self.fade
        t = 1.0 if f["dur"] <= 0 else clamp((now - f["start"]) / f["dur"])
        if t >= 1.0:
            self.fade = None
            return copy.deepcopy(self.look)
        t = t * t * (3 - 2 * t)  # curva suave
        out = {}
        for fid, tgt in self.look.items():
            src = f["from"].get(fid, tgt)
            cur = {}
            for k, v in tgt.items():
                a = src.get(k, v)
                if k in CONTINUOUS:
                    cur[k] = a + (v - a) * t
                else:
                    cur[k] = v
            out[fid] = cur
        return out

    def _start_fade(self, dur, now=None):
        now = now or time.monotonic()
        cur = self._materialize(now)
        if dur and dur > 0:
            self.fade = {"from": cur, "start": now, "dur": float(dur)}
        else:
            self.fade = None
        return cur

    def _set(self, fid, key, value):
        """Cambio manual inmediato (corta el fundido solo para ese atributo)."""
        if fid not in self.look or key not in self.look[fid]:
            return
        self.look[fid][key] = value
        if self.fade and fid in self.fade["from"]:
            self.fade["from"][fid][key] = value

    # ------------------------------------------------- programación ---
    def set_attrs(self, ids, attrs):
        with self.lock:
            if {"r", "g", "b", "w"} & set(attrs):
                self._drop_fx(ids, "color")  # mezclar a mano manda sobre los efectos de color
            for fid in ids:
                for k, v in attrs.items():
                    if k in CONTINUOUS or k == "strobe":
                        self._set(fid, k, clamp(float(v)))
                    elif k in ("cw", "gobo", "prism"):
                        self._set(fid, k, int(v))
            self.changed()

    def set_color(self, ids, rgbw):
        with self.lock:
            for fid in ids:
                prof = self.profile_of(fid)
                if not prof or fid not in self.look:
                    continue
                tmp = dict(self.look[fid])
                apply_color(prof, tmp, rgbw)
                for k in ("r", "g", "b", "w", "cw"):
                    if k in tmp:
                        self._set(fid, k, tmp[k])
                # si estaba apagado, al elegir color lo prende
                if self.look[fid].get("dim", 1) == 0:
                    self._set(fid, "dim", 1.0)
            self._drop_fx(ids, "color")
            self.changed()

    def set_wheel(self, ids, key, index):
        with self.lock:
            for fid in ids:
                prof = self.profile_of(fid)
                slots = (prof or {}).get({"cw": "color_wheel"}.get(key, key), [])
                if slots and 0 <= index < len(slots):
                    self._set(fid, key, int(index))
            if key == "cw":
                self._drop_fx(ids, "color")
            self.changed()

    def set_position(self, ids, pan, tilt):
        with self.lock:
            for fid in ids:
                if pan is not None:
                    self._set(fid, "pan", clamp(float(pan)))
                if tilt is not None:
                    self._set(fid, "tilt", clamp(float(tilt)))
            self.changed()

    def set_positions(self, values):
        """Posición individual por equipo: {id: [pan, tilt]}."""
        with self.lock:
            for fid, (pan, tilt) in values.items():
                if pan is not None:
                    self._set(fid, "pan", clamp(float(pan)))
                if tilt is not None:
                    self._set(fid, "tilt", clamp(float(tilt)))
            self.changed()

    def fan(self, ids, amount):
        """Abre los cabezales en abanico alrededor de su centro."""
        with self.lock:
            movers = [i for i in self._ordered(ids) if "pan" in self.look.get(i, {})]
            n = len(movers)
            if n < 2:
                return
            cur = self._materialize(time.monotonic())
            center = sum(cur[i]["pan"] for i in movers) / n
            spread = float(amount) * 0.25  # 0.25 de recorrido = ~135° en 540°
            for k, fid in enumerate(movers):
                self._set(fid, "pan", clamp(center + spread * (k / (n - 1) - 0.5)))
            self.changed()

    def home_look(self, fid):
        """Estado de reposo de un equipo: apagado y, si es cabezal calibrado, al frente."""
        prof = self.profile_of(fid)
        if not prof:
            return {}
        d = default_look(prof)
        front = self.show.get("rig", {}).get("front", {}).get(fid)
        if front and "pan" in d:
            d["pan"], d["tilt"] = self._front_pt(fid)
        return d

    def locate(self, ids):
        """Ubicar: prende a full en blanco, centrado, sin gobo ni prisma."""
        with self.lock:
            for fid in ids:
                prof = self.profile_of(fid)
                if not prof:
                    continue
                d = self.home_look(fid)
                d.pop("smoke", None)
                if "dim" in d:
                    d["dim"] = 1.0
                for k, v in d.items():
                    self._set(fid, k, v)
            self._drop_fx(ids, None)
            self.changed()

    def clear(self, ids=None, fade=0.0):
        """Vuelve a cero: todo apagado y sin efectos."""
        with self.lock:
            targets = ids or list(self.look.keys())
            self._start_fade(fade)
            for fid in targets:
                if self.profile_of(fid):
                    self.look[fid] = self.home_look(fid)
            if ids:
                self._drop_fx(ids, None)
            else:
                self.fx = []
            self.changed()

    # ---------------------------------------------- frente al público ---
    def rig(self):
        r = self.show.setdefault("rig", {})
        for k, v in RIG_DEFAULT.items():
            r.setdefault(k, copy.deepcopy(v))
        return r

    def movers(self):
        """Cabezales en orden de izquierda a derecha, vistos desde el público."""
        m = [f["id"] for f in self.show["fixtures"] if "pan" in self.look.get(f["id"], {})]
        return m[::-1] if self.rig().get("reverse_order") else m

    def mover_u(self, fid):
        m = self.movers()
        return frontal.head_u(m.index(fid), len(m)) if fid in m else 0.0

    def _degrees(self, fid):
        prof = self.profile_of(fid) or {}
        return float(prof.get("pan_deg", 540)), float(prof.get("tilt_deg", 180))

    @staticmethod
    def _rooms(front, deg, flip):
        """Grados disponibles hacia + y hacia − (en el sentido del público)."""
        hi, lo = (1.0 - front) * deg, front * deg
        return (lo, hi) if flip else (hi, lo)

    def _axis(self, front, value, span, deg, flip):
        pos_room, neg_room = self._rooms(front, deg, flip)
        use = min(span, pos_room if value >= 0 else neg_room)
        return clamp(front + (-1.0 if flip else 1.0) * value * use / deg)

    def _axis_inv(self, front, pos, span, deg, flip):
        d = (pos - front) * deg * (-1.0 if flip else 1.0)
        pos_room, neg_room = self._rooms(front, deg, flip)
        use = min(span, pos_room if d >= 0 else neg_room)
        return d / use if use > 0.5 else 0.0

    def _front_pt(self, fid):
        """Frente calibrado (pan, tilt). Si el pan quedó pegado a un tope del recorrido
        (no le queda lugar para girar hacia un costado), se usa la misma dirección una
        vuelta (360°) más allá, donde tiene lugar para los dos lados."""
        r = self.rig()
        fp, ft = r["front"].get(fid, [0.5, 0.5])
        pdeg = self._degrees(fid)[0]
        need = 1.4 * float(r["span_x"]) / pdeg   # lugar para posiciones y movimientos grandes
        if pdeg > 360 and min(fp, 1.0 - fp) < need:
            turn = 360.0 / pdeg
            options = [c for c in (fp - turn, fp, fp + turn) if 0.0 <= c <= 1.0]
            fp = max(options, key=lambda c: min(c, 1.0 - c))
        return fp, ft

    def xy_to_pt(self, fid, x, y):
        """Punto del público (x, y) -> pan/tilt. Si un eje no tiene recorrido
        suficiente (cabezales colgados no suben mucho más que la horizontal),
        el movimiento se achata para que entre, en lugar de cortarse."""
        r = self.rig()
        fp, ft = self._front_pt(fid)
        pdeg, tdeg = self._degrees(fid)
        return (self._axis(fp, x, float(r["span_x"]), pdeg, r.get("flip_x")),
                self._axis(ft, y, float(r["span_y"]), tdeg, r.get("flip_y")))

    def pt_to_xy(self, fid, pan, tilt):
        r = self.rig()
        fp, ft = self._front_pt(fid)
        pdeg, tdeg = self._degrees(fid)
        return (self._axis_inv(fp, pan, float(r["span_x"]), pdeg, r.get("flip_x")),
                self._axis_inv(ft, tilt, float(r["span_y"]), tdeg, r.get("flip_y")))

    def _canon_tilt(self, fid, fx, k, n, phase):
        """Barrido vertical en canon: en grados reales, desde lo más alto que da el
        cabezal (sin pasar de 90° sobre el frente) hacia abajo. No toca el pan."""
        r = self.rig()
        ft = r["front"].get(fid, [0.5, 0.5])[1]
        tdeg = self._degrees(fid)[1]
        flip = r.get("flip_y")
        up_room, down_room = self._rooms(ft, tdeg, flip)
        top = min(up_room - 2.0, frontal.CANON_TOP_MAX)
        top = max(-down_room, top + min(float(fx.get("altura", 0.0)), 0.0) * 45.0)  # Altura en menos: arranca más abajo
        rng = max(0.0, min(1.0, float(fx.get("size", 0.9)))) * frontal.CANON_DEG
        order = (n - 1 - k) if fx.get("reverse") else k
        p = phase - float(fx.get("spread", 0.0)) * order / max(n, 1)
        deg = max(-down_room, top - rng * frontal.canon_s(p))
        return clamp(ft + (-1.0 if flip else 1.0) * deg / tdeg)

    def nudge(self, ids, dpan_deg=0.0, dtilt_deg=0.0):
        """Ajuste fino en grados (para apuntar con precisión)."""
        with self.lock:
            for fid in ids:
                v = self.look.get(fid, {})
                if "pan" not in v:
                    continue
                pdeg, tdeg = self._degrees(fid)
                self._set(fid, "pan", clamp(v["pan"] + float(dpan_deg) / pdeg))
                self._set(fid, "tilt", clamp(v.get("tilt", 0.5) + float(dtilt_deg) / tdeg))
            self._drop_fx(ids, "pos")
            self.changed()

    def front_layout(self, ids, name, fade=0.8):
        """Posición fija pensada desde el público (abanico, cruzados, en V…)."""
        fn = frontal.LAYOUT_FN.get(name)
        if not fn:
            raise ValueError("Posición desconocida")
        with self.lock:
            targets = [i for i in self.movers() if i in set(ids)] or []
            if not targets:
                raise ValueError("Elegí cabezales")
            self._start_fade(fade)
            for fid in targets:
                pan, tilt = self.xy_to_pt(fid, *fn(self.mover_u(fid)))
                self.look[fid]["pan"], self.look[fid]["tilt"] = pan, tilt
            self.changed()  # si hay un movimiento corriendo, sigue desde la posición nueva

    def front_height(self, ids, y, fade=0.0):
        """Sube o baja los cabezales elegidos sin cambiar hacia qué costado miran."""
        y = max(-1.2, min(1.2, float(y)))
        with self.lock:
            targets = [i for i in self.movers() if i in set(ids)]
            if not targets:
                raise ValueError("Elegí cabezales")
            if fade:
                self._start_fade(fade)
            for fid in targets:
                v = self.look[fid]
                x, _ = self.pt_to_xy(fid, v.get("pan", 0.5), v.get("tilt", 0.5))
                v["pan"], v["tilt"] = self.xy_to_pt(fid, x, y)
            self.changed()

    def movers_xy(self):
        out = {}
        for fid in self.movers():
            v = self.look.get(fid, {})
            x, y = self.pt_to_xy(fid, v.get("pan", 0.5), v.get("tilt", 0.5))
            out[fid] = [round(x, 3), round(y, 3)]
        return out

    def front_test(self, ids, x, y):
        """Mueve los cabezales a un punto del público (para verificar direcciones)."""
        with self.lock:
            targets = [i for i in self.movers() if i in set(ids)]
            for fid in targets:
                pan, tilt = self.xy_to_pt(fid, float(x), float(y))
                self._set(fid, "pan", pan)
                self._set(fid, "tilt", tilt)
            self._drop_fx(targets, "pos")
            self.changed()

    def save_front(self, ids):
        """Toma la posición actual de cada cabezal como su 'frente al público'."""
        with self.lock:
            r = self.rig()
            targets = [i for i in self.movers() if i in set(ids)]
            if not targets:
                raise ValueError("Elegí los cabezales ya apuntados al frente")
            for fid in targets:
                r["front"][fid] = [round(self.look[fid]["pan"], 5), round(self.look[fid]["tilt"], 5)]
            r["calibrated"] = True
            self.changed()
            return len(targets)

    def set_rig(self, **kw):
        with self.lock:
            r = self.rig()
            for k in ("span_x", "span_y"):
                if k in kw:
                    r[k] = max(5.0, min(270.0 if k == "span_x" else 90.0, float(kw[k])))
            for k in ("flip_x", "flip_y", "reverse_order"):
                if k in kw:
                    r[k] = bool(kw[k])
            self.changed()

    # ------------------------------------------------------------ clear ---
    def clear_all(self):
        """Vuelve todo a cero, como recién abierto (guarda para poder deshacer)."""
        with self.lock:
            self._undo = {"look": self._materialize(time.monotonic()), "fx": copy.deepcopy(self.fx),
                          "master": self.master, "blackout": self.blackout, "cue_index": self.cue_index}
            self.fade = None
            for f in self.show["fixtures"]:
                if self.lib.get(f["profile"]):
                    self.look[f["id"]] = self.home_look(f["id"])
            self.fx = []
            self.master = 1.0
            self.blackout = False
            self.holds = set()
            self.test = {}
            self.cue_index = -1
            self.cue_next_at = None
            self.changed()

    def undo_clear(self):
        with self.lock:
            u = self._undo
            if not u:
                raise ValueError("No hay nada para deshacer")
            self._undo = None
            for fid, v in u["look"].items():
                if fid in self.look:
                    self.look[fid] = v
            self.fx = u["fx"]
            self.master, self.blackout, self.cue_index = u["master"], u["blackout"], u["cue_index"]
            self.changed()

    def _ordered(self, ids):
        order = [f["id"] for f in self.show["fixtures"]]
        s = set(ids)
        return [i for i in order if i in s]

    # ------------------------------------------------------- efectos ---
    def _drop_fx(self, ids, family):
        ids = set(ids)
        keep = []
        for fx in self.fx:
            if family is None or FX_TYPES.get(fx["type"], ("",))[0] == family:
                fx["ids"] = [i for i in fx["ids"] if i not in ids]
            if fx["ids"]:
                keep.append(fx)
        self.fx = keep

    def add_fx(self, ids, ftype, params=None, stack=False):
        if ftype not in FX_TYPES:
            raise ValueError("Efecto desconocido")
        with self.lock:
            fam = FX_TYPES[ftype][0]
            ids = self._ordered(ids)
            if fam == "pos":
                ids = [i for i in ids if "pan" in self.look.get(i, {}) or "tilt" in self.look.get(i, {})]
            elif fam == "color":
                need = efectos.TYPES.get(ftype, ("", "", "color"))[2]
                keys = {"r"} if need == "rgb" else {"r", "cw", "w"}
                ids = [i for i in ids if keys & set(self.look.get(i, {}))]
            else:
                ids = [i for i in ids if "dim" in self.look.get(i, {})]
            if not ids:
                raise ValueError("Ningún equipo seleccionado admite ese efecto")
            if stack and fam == "pos":
                # se suma a los movimientos que ya tienen (hasta MAX_MOVES)
                moves = [f for f in self.fx if FX_TYPES.get(f["type"], ("",))[0] == "pos" and set(f["ids"]) & set(ids)]
                if len(moves) >= MAX_MOVES:
                    raise ValueError("Ya hay %d movimientos sumados: frená alguno antes" % MAX_MOVES)
            else:
                self._drop_fx(ids, fam)
            fx = {"id": new_id("fx"), "type": ftype, "ids": ids, "sync": True, "beats": 4,
                  "hz": 0.5, "size": 0.5, "spread": 1.0, "reverse": False,
                  "colors": ["#ff2020", "#2a46ff"]}
            if ftype == "pulso":
                fx.update(size=round(1.0 / max(len(ids), 1), 3), beats=len(ids) if len(ids) > 1 else 1)
            if ftype == "azar":
                fx.update(beats=1, size=0.4, spread=0.0)
            if ftype == "onda":
                fx.update(size=1.0)
            if ftype == "arcoiris":
                fx.update(beats=16, spread=0.5)
            if ftype == "colores":
                fx.update(beats=2, spread=0.0)
            if ftype in ("circulo", "ocho", "paneo", "tilt"):
                fx.update(beats=8, spread=0.25, size=0.5)
            if ftype.startswith("f_"):
                fx.update(frontal.DEFAULTS)
                fx["name"] = str((params or {}).get("name") or FX_TYPES[ftype][1])[:40]
            fx.update({k: v for k, v in (params or {}).items() if k in fx and k not in ("id", "ids", "type")})
            pid = self.show["settings"].get("paleta")
            if pid and ftype in efectos.PALETTE_TYPES:
                fx["colors"] = list({k: c for k, _, c in efectos.PALETTES}[pid])
            self.fx.append(fx)
            if fam == "dim" or ftype.startswith("f_"):  # sobre equipos apagados no se vería
                for fid in ids:
                    if self.look[fid].get("dim", 0) == 0:
                        self._set(fid, "dim", 1.0)
            self.changed()
            return fx["id"]

    def update_fx(self, fx_id, params):
        with self.lock:
            for fx in self.fx:
                if fx["id"] == fx_id:
                    for k, v in params.items():
                        if k in ("sync", "reverse", "mirror"):
                            fx[k] = bool(v)
                        elif k in ("beats", "hz", "size", "spread", "altura", "apertura", "escalon"):
                            fx[k] = float(v)
                        elif k == "colors" and isinstance(v, list) and v:
                            fx[k] = [str(c) for c in v][:6]
            self.changed()

    def remove_fx(self, fx_id=None, ids=None):
        with self.lock:
            if fx_id:
                self.fx = [f for f in self.fx if f["id"] != fx_id]
            elif ids:
                self._drop_fx(ids, None)
            else:
                self.fx = []
            self.changed()

    def _fx_rate(self, fx):
        st = self.show["settings"]
        mult = st.get("mov_speed" if FX_TYPES.get(fx["type"], ("",))[0] == "pos" else "fx_speed", 1.0)
        if fx["type"] in efectos.ONCE:
            mult = 1.0  # la subida dura lo que dice (16 tiempos), para caer justo en el drop
        if fx.get("sync", True):
            return (self.bpm / 60.0) / max(float(fx.get("beats", 4)), 0.25) * mult
        return max(float(fx.get("hz", 0.5)), 0.0) * mult

    def _apply_fx(self, cur, dt):
        live = set()
        done = []
        msize = float(self.show["settings"].get("mov_size", 1.0))
        for fx in self.fx:
            live.add(fx["id"])
            ph = self.fx_phase.get(fx["id"], 0.0) + dt * self._fx_rate(fx)
            self.fx_phase[fx["id"]] = ph
            if fx["type"] in efectos.ONCE and ph >= 1.0:
                done.append(fx["id"])
            if msize != 1.0 and FX_TYPES.get(fx["type"], ("",))[0] == "pos":
                fx = dict(fx, size=float(fx.get("size", 0.5)) * msize)
            ids = [i for i in fx["ids"] if i in cur]
            if fx.get("reverse"):
                ids = ids[::-1]
            n = max(len(ids), 1)
            size = float(fx.get("size", 0.5))
            spread = float(fx.get("spread", 1.0))
            t = fx["type"]
            if t.startswith("f_"):
                fids = [i for i in self.movers() if i in set(ids)]
                for k, fid in enumerate(fids):
                    if t == "f_canon":
                        cur[fid]["tilt"] = self._canon_tilt(fid, fx, k, len(fids), ph)
                        continue
                    # el movimiento se suma a la posición actual del cabezal (abanico, en V, etc.)
                    bx, by = self.pt_to_xy(fid, cur[fid]["pan"], cur[fid].get("tilt", 0.5))
                    dx, dy = frontal.fx_xy(fx, self.mover_u(fid), k, len(fids), ph, fx["id"] + fid)
                    pan, tilt = self.xy_to_pt(fid, bx + dx, by + dy)
                    cur[fid]["pan"], cur[fid]["tilt"] = pan, tilt
                continue
            if t in efectos.TYPES:
                for k, fid in enumerate(fx["ids"]):
                    v = cur.get(fid)
                    if v is None:
                        continue
                    d, rgb = efectos.fx_eval(fx, k, len(fx["ids"]), ph, fx["id"] + fid)
                    if d is not None and "dim" in v:
                        v["dim"] *= d
                    if rgb is not None:
                        # blanco puro: usar el LED blanco del equipo si lo tiene
                        rgbw = (0.0, 0.0, 0.0, 1.0) if min(rgb) >= 0.999 else (rgb[0], rgb[1], rgb[2], 0.0)
                        apply_color(self.profile_of(fid), v, rgbw)
                continue
            for k, fid in enumerate(ids):
                v = cur[fid]
                p = ph - spread * k / n
                # movimientos viejos (escenas guardadas antes de los frontales)
                ap, at = 0.12 * size, 0.22 * size
                if t == "circulo":
                    dp, dtl = ap * math.cos(2 * math.pi * p), at * math.sin(2 * math.pi * p)
                elif t == "ocho":
                    dp, dtl = ap * math.sin(2 * math.pi * p), at * 0.6 * math.sin(4 * math.pi * p)
                elif t == "paneo":
                    dp, dtl = ap * 1.6 * math.sin(2 * math.pi * p), 0.0
                else:
                    dp, dtl = 0.0, at * math.sin(2 * math.pi * p)
                if "pan" in v:
                    v["pan"] = clamp(v["pan"] + dp)
                if "tilt" in v:
                    v["tilt"] = clamp(v["tilt"] + dtl)
        for k in list(self.fx_phase):
            if k not in live:
                del self.fx_phase[k]
        if done:  # la subida terminó: queda todo prendido, listo para el drop
            ended = [f for f in self.fx if f["id"] in done]
            self.fx = [f for f in self.fx if f["id"] not in done]
            for f in ended:
                for fid in f["ids"]:
                    if fid in self.look and "dim" in self.look[fid]:
                        self.look[fid]["dim"] = 1.0
            self.changed()

    # -------------------------------------------------------- escenas ---
    def save_scene(self, name, scene_id=None, color=None):
        with self.lock:
            data = {"look": self._materialize(time.monotonic()), "fx": copy.deepcopy(self.fx)}
            if scene_id:
                for s in self.show["scenes"]:
                    if s["id"] == scene_id:
                        s.update(data)
                        if name:
                            s["name"] = name
                        self.changed()
                        return scene_id
            sid = new_id("sc")
            self.show["scenes"].append(dict(data, id=sid, name=name or "Escena %d" % (len(self.show["scenes"]) + 1),
                                            color=color or "#3a4766"))
            self.changed()
            return sid

    def scene(self, sid):
        for s in self.show["scenes"]:
            if s["id"] == sid:
                return s
        return None

    def recall_scene(self, sid, fade=None):
        with self.lock:
            s = self.scene(sid)
            if not s:
                raise ValueError("La escena no existe")
            fade = self.show["settings"]["fade"] if fade is None else float(fade)
            self._start_fade(fade)
            for fid in self.look:
                prof = self.profile_of(fid)
                base = default_look(prof) if prof else {}
                saved = s["look"].get(fid)
                if saved is None:
                    continue  # equipo agregado después de grabar la escena: no se toca
                base.update({k: v for k, v in saved.items() if k in base})
                self.look[fid] = base
            # efectos: conserva la fase de los que ya estaban corriendo
            self.fx = copy.deepcopy(s.get("fx", []))
            self.changed()

    def update_scene(self, sid, **kw):
        with self.lock:
            s = self.scene(sid)
            if s:
                for k in ("name", "color"):
                    if kw.get(k):
                        s[k] = str(kw[k])[:60]
            self.changed()

    def delete_scene(self, sid):
        with self.lock:
            self.show["scenes"] = [s for s in self.show["scenes"] if s["id"] != sid]
            self.show["cues"] = [c for c in self.show["cues"] if c["scene"] != sid]
            self.changed()

    def move_scene(self, sid, delta):
        with self.lock:
            self._move(self.show["scenes"], sid, delta)
            self.changed()

    @staticmethod
    def _move(lst, item_id, delta):
        for i, it in enumerate(lst):
            if it["id"] == item_id:
                j = max(0, min(len(lst) - 1, i + int(delta)))
                lst.insert(j, lst.pop(i))
                return

    # ------------------------------------------------------ posiciones ---
    def save_position(self, name, ids):
        with self.lock:
            cur = self._materialize(time.monotonic())
            vals = {fid: [cur[fid].get("pan", 0.5), cur[fid].get("tilt", 0.5)]
                    for fid in ids if fid in cur and ("pan" in cur[fid] or "tilt" in cur[fid])}
            if not vals:
                raise ValueError("Seleccioná cabezales para guardar la posición")
            pid = new_id("ps")
            self.show["positions"].append({"id": pid, "name": name or "Posición", "values": vals})
            self.changed()
            return pid

    def recall_position(self, pid, ids=None, fade=0.6):
        with self.lock:
            p = next((x for x in self.show["positions"] if x["id"] == pid), None)
            if not p:
                return
            self._start_fade(fade)
            for fid, (pan, tilt) in p["values"].items():
                if ids and fid not in ids:
                    continue
                if fid in self.look:
                    if "pan" in self.look[fid]:
                        self.look[fid]["pan"] = pan
                    if "tilt" in self.look[fid]:
                        self.look[fid]["tilt"] = tilt
            self.changed()

    def delete_position(self, pid):
        with self.lock:
            self.show["positions"] = [p for p in self.show["positions"] if p["id"] != pid]
            self.changed()

    # ------------------------------------------------------ secuencia ---
    def add_cue(self, scene_id, fade=None, wait=None):
        with self.lock:
            if not self.scene(scene_id):
                raise ValueError("La escena no existe")
            cid = new_id("cu")
            self.show["cues"].append({"id": cid, "scene": scene_id,
                                      "fade": self.show["settings"]["fade"] if fade is None else float(fade),
                                      "wait": None if wait in (None, "", 0) else float(wait)})
            self.changed()
            return cid

    def update_cue(self, cid, **kw):
        with self.lock:
            for c in self.show["cues"]:
                if c["id"] == cid:
                    if "fade" in kw:
                        c["fade"] = max(0.0, float(kw["fade"]))
                    if "wait" in kw:
                        w = kw["wait"]
                        c["wait"] = None if w in (None, "", 0, "0") else max(0.0, float(w))
                    if kw.get("scene") and self.scene(kw["scene"]):
                        c["scene"] = kw["scene"]
            self.changed()

    def delete_cue(self, cid):
        with self.lock:
            self.show["cues"] = [c for c in self.show["cues"] if c["id"] != cid]
            self.cue_index = min(self.cue_index, len(self.show["cues"]) - 1)
            self.changed()

    def move_cue(self, cid, delta):
        with self.lock:
            self._move(self.show["cues"], cid, delta)
            self.changed()

    def go(self, index=None):
        with self.lock:
            cues = self.show["cues"]
            if not cues:
                return
            if index is None:
                index = self.cue_index + 1
                if index >= len(cues):
                    if not self.show["settings"].get("cue_loop"):
                        self.cue_next_at = None
                        return
                    index = 0
            index = max(0, min(len(cues) - 1, int(index)))
            c = cues[index]
            self.cue_index = index
            self.recall_scene(c["scene"], c["fade"])
            self.cue_next_at = (time.monotonic() + c["fade"] + c["wait"]) if c.get("wait") is not None else None
            self.changed()

    def back(self):
        with self.lock:
            if self.cue_index > 0:
                self.go(self.cue_index - 1)

    def stop_cues(self):
        with self.lock:
            self.cue_next_at = None
            self.cue_index = -1
            self.changed()

    # -------------------------------------------------- controles globales ---
    def set_master(self, v):
        with self.lock:
            self.master = clamp(float(v))
            self.changed()

    def set_blackout(self, on):
        with self.lock:
            self.blackout = bool(on)
            self.changed()

    def set_hold(self, kind, on):
        with self.lock:
            (self.holds.add if on else self.holds.discard)(kind)
            self.changed()

    def strobe2_rate(self):
        st = self.show["settings"]["strobe2"]
        if st.get("sync"):
            return self.bpm / 60.0 * float(st.get("div", 2))
        return float(st.get("hz", 6.0))

    def _strobe2_on(self):
        st = self.show["settings"]["strobe2"]
        if st.get("sync"):  # pegado al pulso del tempo
            ph = frac(self.beat_phase * float(st.get("div", 2)))
        else:
            ph = frac(time.monotonic() * float(st.get("hz", 6.0)))
        return ph < 0.4

    def set_strobe2(self, **kw):
        with self.lock:
            st = self.show["settings"]["strobe2"]
            if "sync" in kw:
                st["sync"] = bool(kw["sync"])
            if "white" in kw:
                st["white"] = bool(kw["white"])
            if "div" in kw:
                d = float(kw["div"])
                st["div"] = min(STROBE2_DIVS, key=lambda x: abs(x - d))
            if "hz" in kw:
                st["hz"] = round(clamp(float(kw["hz"]), 0.5, STROBE2_MAX_HZ), 1)
            self.changed()

    # ------------------------------------------- tempo desde VirtualDJ ---
    def external_beat(self, bpm=None):
        """Llega un pulso de la música (OS2L). Solo manda si el seguimiento está prendido."""
        with self.lock:
            self.ext_last = time.monotonic()
            try:
                b = float(bpm) if bpm is not None else None
            except (TypeError, ValueError):
                b = None
            if b is not None and 30 <= b <= 300:
                self.ext_bpm = b
            if self.sync_ext:
                self.beat_phase = 0.0  # el compás queda pegado al pulso real
                if b is not None and 30 <= b <= 300:
                    nb = round(b, 1)
                    if abs(nb - self.bpm) >= 0.1:
                        self.bpm = nb
                        self.changed()

    def set_sync(self, on):
        with self.lock:
            self.sync_ext = bool(on)
            if self.sync_ext and self.ext_bpm:
                self.bpm = round(self.ext_bpm, 1)
            self.changed()

    def tap(self):
        with self.lock:
            if self.sync_ext:
                return  # el tempo lo maneja VirtualDJ
            now = time.monotonic()
            if self.taps and now - self.taps[-1] > 2.0:
                self.taps = []
            self.taps.append(now)
            self.taps = self.taps[-5:]
            if len(self.taps) >= 2:
                iv = [b - a for a, b in zip(self.taps, self.taps[1:])]
                self.bpm = round(clamp(60.0 / (sum(iv) / len(iv)), 30, 300), 1)
                self.beat_phase = 0.0
            self.changed()

    def set_bpm(self, bpm):
        with self.lock:
            self.bpm = clamp(float(bpm), 30, 300)
            self.changed()

    # --------------------------------------------------------- patch ---
    def used_addresses(self, exclude=None):
        used = {}
        for f in self.show["fixtures"]:
            if f["id"] == exclude:
                continue
            prof = self.lib.get(f["profile"])
            n = len(prof["canales"]) if prof else 1
            for a in range(f["address"], f["address"] + n):
                used.setdefault(a, []).append(f["id"])
        return used

    def next_free(self, nch):
        used = self.used_addresses()
        a = 1
        while a + nch - 1 <= 512:
            if all(x not in used for x in range(a, a + nch)):
                return a
            a += 1
        return None

    def add_fixtures(self, profile_id, count=1, address=None, name=None, grupo=None):
        with self.lock:
            prof = self.lib.get(profile_id)
            if not prof:
                raise ValueError("Perfil inexistente")
            nch = len(prof["canales"])
            count = max(1, min(64, int(count)))
            base = name or prof.get("nombre", "Equipo").split("(")[0].strip()
            existing = sum(1 for f in self.show["fixtures"] if f["profile"] == profile_id)
            addr = int(address) if address else self.next_free(nch)
            created = []
            for k in range(count):
                if addr is None or addr + nch - 1 > 512:
                    raise ValueError("No hay más direcciones DMX libres en el universo")
                fid = new_id("eq")
                self.show["fixtures"].append({"id": fid, "name": "%s %d" % (base, existing + k + 1),
                                              "profile": profile_id, "address": addr,
                                              "invert_pan": False, "invert_tilt": False})
                if grupo:
                    self.show["fixtures"][-1]["grupo"] = str(grupo).strip()[:40]
                self.look[fid] = default_look(prof)
                created.append(fid)
                addr = addr + nch
            self.changed()
            return created

    def update_fixture(self, fid, **kw):
        with self.lock:
            f = self.fixture(fid)
            if not f:
                return
            if "name" in kw and kw["name"]:
                f["name"] = str(kw["name"])[:40]
            if "address" in kw:
                prof = self.lib.get(f["profile"])
                nch = len(prof["canales"]) if prof else 1
                a = int(kw["address"])
                if not 1 <= a <= 513 - nch:
                    raise ValueError("Dirección fuera de rango (1-%d)" % (513 - nch))
                f["address"] = a
            for k in ("invert_pan", "invert_tilt"):
                if k in kw:
                    f[k] = bool(kw[k])
            if "grupo" in kw:
                g = str(kw["grupo"] or "").strip()[:40]
                if g:
                    f["grupo"] = g
                else:
                    f.pop("grupo", None)
            if "icono" in kw:
                f["icono"] = str(kw["icono"])[:20] if kw["icono"] else None
            if "profile" in kw and self.lib.get(kw["profile"]):
                f["profile"] = kw["profile"]
                self.look[fid] = default_look(self.lib.get(kw["profile"]))
            self.changed()

    def remove_fixture(self, fid):
        with self.lock:
            self.show["fixtures"] = [f for f in self.show["fixtures"] if f["id"] != fid]
            self.look.pop(fid, None)
            self._drop_fx([fid], None)
            self.changed()

    def move_fixture(self, fid, delta):
        with self.lock:
            self._move(self.show["fixtures"], fid, delta)
            self.changed()

    def conflicts(self):
        return sorted({tuple(sorted(set(v))) for v in self.used_addresses().values() if len(set(v)) > 1})

    def refresh_profiles(self):
        """Tras editar un perfil: rehace el estado de los equipos que lo usan."""
        with self.lock:
            for f in self.show["fixtures"]:
                prof = self.lib.get(f["profile"])
                if not prof:
                    continue
                d = default_look(prof)
                old = self.look.get(f["id"], {})
                d.update({k: v for k, v in old.items() if k in d})
                self.look[f["id"]] = d
            self.fade = None
            self.changed()

    # ---------------------------------------------------- probar canales ---
    def set_test(self, address, value):
        with self.lock:
            a = int(address)
            if 1 <= a <= 512:
                if value is None:
                    self.test.pop(a, None)
                else:
                    self.test[a] = max(0, min(255, int(value)))
            self.changed()

    def clear_test(self):
        with self.lock:
            self.test = {}
            self.changed()

    # ------------------------------------------------ cálculo de salida ---
    def tick(self, now=None):
        """Calcula un cuadro DMX. Se llama ~40 veces por segundo."""
        with self.lock:
            now = now or time.monotonic()
            dt = clamp(now - self.last_t, 0.0, 0.25)
            self.last_t = now
            self.beat_phase = frac(self.beat_phase + dt * self.bpm / 60.0)
            if self.cue_next_at is not None and now >= self.cue_next_at:
                self.cue_next_at = None
                self.go()
            cur = self._materialize(now)
            self._apply_fx(cur, dt)
            frame = bytearray(512)
            preview = {}
            soft_strobe_on = frac(now * 12.0) < 0.5
            subs = self.show["settings"].get("submasters", {})
            for f in self.show["fixtures"]:
                prof = self.lib.get(f["profile"])
                v = cur.get(f["id"])
                if not prof or v is None:
                    continue
                c = caps(prof)
                v = dict(v)
                light = "dim" in v
                grp = self.group_of(f["id"])
                if light:
                    sub = subs.get(grp, 1.0)
                    v["dim"] = v["dim"] * self.master * sub * (0.0 if self.blackout else 1.0)
                if light and ("g:" + grp) in self.holds:  # Flash del grupo: a pleno con su color
                    v["dim"] = 1.0 * (0.0 if self.blackout else 1.0)
                if "flash" in self.holds and light:
                    v["dim"] = 1.0
                    apply_color(prof, v, (0, 0, 0, 1))
                    if "strobe" in v:
                        v["strobe"] = 0.0
                if "strobe" in self.holds and light:
                    v["dim"] = 1.0
                    if "strobe" in c:
                        v["strobe"] = 1.0
                    else:
                        v["dim"] = 1.0 if soft_strobe_on else 0.0
                if "strobe2" in self.holds and light:
                    on = self._strobe2_on()
                    v["dim"] = 1.0 if on else 0.0
                    if "strobe" in v:
                        v["strobe"] = 0.0  # lo maneja el programa, no el equipo
                    if on and self.show["settings"]["strobe2"].get("white"):
                        apply_color(prof, v, (0, 0, 0, 1))
                if "humo" in self.holds and "smoke" in v:
                    v["smoke"] = 1.0
                self._write(frame, f, prof, c, v)
                if prof.get("refresco"):
                    self._refresh_channels(frame, f, prof, now)
                if f["id"] in self._wake:
                    self._wake_channels(frame, f, prof, now)
                pv = self._preview(prof, c, v)
                if "pan" in v:
                    pv["x"], pv["y"] = (round(q, 3) for q in self.pt_to_xy(f["id"], v["pan"], v.get("tilt", 0.5)))
                preview[f["id"]] = pv
            for a, val in self.test.items():
                frame[a - 1] = val
            self.frame = bytes(frame)
            self.preview = preview
            return self.frame

    REFRESH_ATTRS = ("intensity", "red", "green", "blue", "white")
    REFRESH_EVERY = 2.0    # segundos entre refrescos aunque no cambie nada
    REFRESH_DELAY = 0.1    # el refresco llega 100 ms después de un cambio
    REFRESH_LEN = 0.075    # dura ~75 ms: más de un cuadro de salida

    def _refresh_channels(self, frame, f, prof, now):
        """Algunos equipos (varios Nebula) siguen usando un valor viejo en un canal
        hasta que lo ven cambiar. Cuando cambia algo, y cada tanto, se mueven sus
        canales de color y dimmer 2 pasos (invisible) y se devuelven a su valor."""
        addrs = [f["address"] - 1 + i for i, ch in enumerate(prof.get("canales", []))
                 if ch.get("attr") in self.REFRESH_ATTRS and 0 <= f["address"] - 1 + i < 512]
        if not addrs:
            return
        st = self._refresh.setdefault(f["id"], {"last": None, "at": None, "next": now + self.REFRESH_EVERY})
        vals = tuple(frame[a] for a in addrs)
        if vals != st["last"]:
            # el valor nuevo sale tal cual; el refresco llega un instante después
            st["last"] = vals
            st["at"] = now + self.REFRESH_DELAY
        elif st["at"] is None and now >= st["next"]:
            st["at"] = now
        if st["at"] is not None and now >= st["at"]:
            if now < st["at"] + self.REFRESH_LEN:
                for a in addrs:
                    frame[a] = frame[a] + 2 if frame[a] <= 253 else frame[a] - 2
            else:
                st["at"] = None
                st["next"] = now + self.REFRESH_EVERY

    WAKE_STEP = 0.12  # cada paso del "despertar" (más de 3 cuadros de salida)

    def wake(self, ids=None):
        """Sube y baja de a un canal (dimmer, R, G, B, W) a los equipos con "despertar",
        con el dimmer en cero. Algunos Nebula no sueltan un valor viejo (por ejemplo el
        blanco prendido al encenderlos) hasta que el canal hace ese recorrido."""
        with self.lock:
            now = time.monotonic()
            for f in self.show["fixtures"]:
                prof = self.lib.get(f["profile"]) or {}
                if (ids is None and prof.get("despertar")) or (ids is not None and f["id"] in ids):
                    self._wake[f["id"]] = now
            self.changed()
            return len(self._wake)

    def _wake_steps(self, prof):
        idx = {ch.get("attr"): i for i, ch in enumerate(prof.get("canales", []))
               if ch.get("attr") in self.REFRESH_ATTRS}
        dim = idx.get("intensity")
        steps = []  # cada paso: {índice de canal: valor}; el resto queda como esté
        hold = {idx[a]: 0 for a in ("red", "green", "blue", "white") if a in idx}
        if dim is not None:
            hold[dim] = 0
        steps.append(dict(hold))
        for a in ("red", "green", "blue", "white"):
            if a in idx:
                steps.append({**hold, idx[a]: 255})
                steps.append({**hold, idx[a]: 0})
        if dim is not None:
            colors0 = {idx[a]: 0 for a in ("red", "green", "blue", "white") if a in idx}
            steps.append({**colors0, dim: 255})
            steps.append({**colors0, dim: 0})
        return steps

    def _wake_channels(self, frame, f, prof, now):
        steps = self._wake_steps(prof)
        k = int((now - self._wake[f["id"]]) / self.WAKE_STEP)
        if k >= len(steps):
            del self._wake[f["id"]]
            return
        for i, val in steps[k].items():
            a = f["address"] - 1 + i
            if 0 <= a < 512:
                frame[a] = val

    @staticmethod
    def _slot_dmx(prof, key, idx):
        slots = prof.get(key, [])
        if not slots:
            return 0
        return int(slots[max(0, min(len(slots) - 1, int(idx)))].get("dmx", 0))

    def _write(self, frame, f, prof, c, v):
        dim = v.get("dim", 1.0)
        scale_color = 1.0 if "intensity" in c else dim
        pan = v.get("pan", 0.5)
        tilt = v.get("tilt", 0.5)
        if f.get("invert_pan"):
            pan = 1.0 - pan
        if f.get("invert_tilt"):
            tilt = 1.0 - tilt
        pan16 = int(round(clamp(pan) * 65535))
        tilt16 = int(round(clamp(tilt) * 65535))
        st = prof.get("strobe", {"off": 0, "min": 10, "max": 255})
        for i, ch in enumerate(prof.get("canales", [])):
            addr = f["address"] - 1 + i
            if not 0 <= addr < 512:
                continue
            a = ch.get("attr")
            if a == "intensity":
                val = dim * 255
            elif a == "red":
                val = v.get("r", 0) * scale_color * 255
            elif a == "green":
                val = v.get("g", 0) * scale_color * 255
            elif a == "blue":
                val = v.get("b", 0) * scale_color * 255
            elif a == "white":
                val = v.get("w", 0) * scale_color * 255
            elif a == "pan":
                val = pan16 >> 8
            elif a == "pan_fine":
                val = pan16 & 0xFF
            elif a == "tilt":
                val = tilt16 >> 8
            elif a == "tilt_fine":
                val = tilt16 & 0xFF
            elif a == "pt_speed":
                val = v.get("pts", 0) * 255
            elif a == "strobe":
                s = v.get("strobe", 0)
                val = st.get("off", 0) if s <= 0.001 else st.get("min", 10) + s * (st.get("max", 255) - st.get("min", 10))
            elif a == "color_wheel":
                val = self._slot_dmx(prof, "color_wheel", v.get("cw", 0))
            elif a == "gobo":
                val = self._slot_dmx(prof, "gobo", v.get("gobo", 0))
            elif a == "prism":
                pr = prof.get("prism_rot")
                if pr and v.get("prot", 0) > 0.001:
                    # rotación dentro del mismo canal: de lento (min) a rápido (max)
                    lo, hi = float(pr.get("min", 145)), float(pr.get("max", 255))
                    val = lo + v["prot"] * (hi - lo)
                else:
                    val = self._slot_dmx(prof, "prism", v.get("prism", 0))
            elif a == "prism_rotation":
                val = 0 if prof.get("prism_rot") else v.get("prot", 0) * 255
            elif a == "focus":
                val = v.get("focus", 0.5) * 255
            elif a == "smoke":
                val = v.get("smoke", 0) * 255
            else:
                val = ch.get("default", 0)
            frame[addr] = max(0, min(255, int(round(val))))

    @staticmethod
    def _preview(prof, c, v):
        dim = v.get("dim", 1.0) if "dim" in c else 1.0
        if "rgb" in c:
            rgb = rgbw_to_rgb(v.get("r", 0), v.get("g", 0), v.get("b", 0), v.get("w", 0))
        elif "cw" in c:
            slots = prof.get("color_wheel", [])
            idx = max(0, min(len(slots) - 1, int(v.get("cw", 0)))) if slots else 0
            rgb = hex_to_rgb(slots[idx]["hex"]) if slots else (1, 1, 1)
        elif "white" in c:
            rgb = (v.get("w", 1),) * 3
        elif "smoke" in c:
            rgb = (0.8, 0.8, 0.85)
            dim = v.get("smoke", 0)
        else:
            rgb = (1, 1, 1)
        return {"c": rgb_to_hex(*rgb), "d": round(dim, 3),
                "p": round(v["pan"], 3) if "pan" in v else None,
                "t": round(v["tilt"], 3) if "tilt" in v else None,
                "s": round(v.get("strobe", 0), 2)}

    # ---------------------------------------------------- para la UI ---
    def snapshot(self):
        with self.lock:
            now = time.monotonic()
            return copy.deepcopy({
                "fixtures": self.show["fixtures"],
                "scenes": [{k: s[k] for k in ("id", "name", "color")} for s in self.show["scenes"]],
                "cues": self.show["cues"],
                "positions": [{"id": p["id"], "name": p["name"], "ids": list(p["values"])}
                              for p in self.show["positions"]],
                "settings": self.show["settings"],
                "show_name": self.show.get("name", "Mi show"),
                "look": self._materialize(now) if self.fade else self.look,
                "fx": self.fx,
                "master": self.master, "blackout": self.blackout, "holds": sorted(self.holds),
                "bpm": self.bpm, "cue_index": self.cue_index, "sync_ext": self.sync_ext,
                "cue_auto": self.cue_next_at is not None,
                "test": {str(k): v for k, v in self.test.items()},
                "conflicts": self.conflicts(),
                "rig": self.rig(), "movers": self.movers(), "movers_xy": self.movers_xy(), "groups": self.groups(), "can_undo_clear": self._undo is not None,
                "version": self.version,
            })
