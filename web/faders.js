'use strict';
/* Faders verticales (PC y celular).
   Faders.render(box, defs) dibuja o actualiza un banco. Cada def:
   { key, label, color, value (0..1), text (lo que se muestra), onSet(v),
     btn: { label, hold?, on?, title?, down(), up(), click() } }
   Se manejan arrastrando (si se agarra la perilla no salta), con la rueda del
   mouse encima del fader, y con el teclado (flechas, RePág/AvPág, Inicio/Fin). */
(function () {
  const escH = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const CAP = 26;          // alto de la perilla (px)
  const HOLD_MS = 700;     // después de soltar, ignorar el valor viejo que llega del programa

  function setPos(fd, v) {
    fd.style.setProperty('--v', Math.max(0, Math.min(1, v)).toFixed(4));
    const t = fd.querySelector('.fd-track');
    t.setAttribute('aria-valuenow', Math.round(v * 100));
  }

  function bind(box) {
    if (box._fdBound) return;
    box._fdBound = true;
    let drag = null;
    const defOf = (fd) => box._defs[fd.dataset.k];
    const set = (fd, v, d) => {
      v = Math.max(0, Math.min(1, v));
      fd._v = v; fd._until = Date.now() + HOLD_MS;
      setPos(fd, v);
      if (d.fmt) fd.querySelector('.fd-val').textContent = d.fmt(v);
      d.onSet && d.onSet(v);
    };
    const fromY = (track, y) => {
      const r = track.getBoundingClientRect();
      return 1 - (y - r.top - CAP / 2) / Math.max(1, r.height - CAP);
    };
    box.addEventListener('pointerdown', (e) => {
      const track = e.target.closest('.fd-track'); if (!track) return;
      const fd = track.closest('.fd'), d = defOf(fd); if (!d) return;
      e.preventDefault();
      track.setPointerCapture?.(e.pointerId);
      track.focus({ preventScroll: true });
      const at = fromY(track, e.clientY), cur = fd._v ?? d.value;
      const r = track.getBoundingClientRect();
      const onCap = Math.abs(at - cur) * (r.height - CAP) < CAP * 0.8;
      drag = { fd, d, track, off: onCap ? cur - at : 0, id: e.pointerId };
      fd.classList.add('active');
      if (!onCap) set(fd, at, d);
    });
    box.addEventListener('pointermove', (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      set(drag.fd, fromY(drag.track, e.clientY) + drag.off, drag.d);
    });
    const end = (e) => {
      if (!drag || (e.pointerId != null && e.pointerId !== drag.id)) return;
      drag.fd.classList.remove('active'); drag.fd._until = Date.now() + HOLD_MS; drag = null;
    };
    box.addEventListener('pointerup', end); box.addEventListener('pointercancel', end);
    box.addEventListener('lostpointercapture', end);
    // rueda del mouse: con el puntero encima del fader (Shift = pasos grandes)
    box.addEventListener('wheel', (e) => {
      const fd = e.target.closest('.fd'); if (!fd) return;
      const d = defOf(fd); if (!d) return;
      e.preventDefault();
      const delta = Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX;
      if (!delta) return;
      const step = (e.shiftKey ? 0.05 : 0.02) * (d.wheelStep || 1);
      set(fd, (fd._v ?? d.value) + (delta < 0 ? step : -step), d);
    }, { passive: false });
    box.addEventListener('keydown', (e) => {
      const track = e.target.closest('.fd-track'); if (!track) return;
      const fd = track.closest('.fd'), d = defOf(fd); if (!d) return;
      const cur = fd._v ?? d.value;
      const k = { ArrowUp: 0.01, ArrowRight: 0.01, ArrowDown: -0.01, ArrowLeft: -0.01, PageUp: 0.1, PageDown: -0.1 }[e.key];
      if (k != null) { e.preventDefault(); e.stopPropagation(); set(fd, cur + k, d); }
      else if (e.key === 'Home') { e.preventDefault(); e.stopPropagation(); set(fd, 0, d); }
      else if (e.key === 'End') { e.preventDefault(); e.stopPropagation(); set(fd, 1, d); }
    });
    // botón de abajo: click o "mantener apretado"
    box.addEventListener('pointerdown', (e) => {
      const b = e.target.closest('.fd-btn'); if (!b) return;
      const d = defOf(b.closest('.fd')); if (!d || !d.btn || !d.btn.hold) return;
      e.preventDefault(); b.setPointerCapture?.(e.pointerId); b.classList.add('held'); d.btn.down && d.btn.down();
    });
    const up = (e) => {
      const b = e.target.closest?.('.fd-btn'); if (!b || !b.classList.contains('held')) return;
      b.classList.remove('held'); const d = defOf(b.closest('.fd')); d && d.btn.up && d.btn.up();
    };
    box.addEventListener('pointerup', up); box.addEventListener('pointercancel', up); box.addEventListener('lostpointercapture', up);
    box.addEventListener('click', (e) => {
      const b = e.target.closest('.fd-btn'); if (!b) return;
      const d = defOf(b.closest('.fd')); if (d && d.btn && !d.btn.hold && d.btn.click) d.btn.click();
    });
  }

  function render(box, defs) {
    bind(box);
    box._defs = Object.fromEntries(defs.map((d) => [d.key, d]));
    const sig = JSON.stringify(defs.map((d) => [d.key, d.label, d.color, d.btn && d.btn.label]));
    if (box._sig !== sig) {
      box._sig = sig;
      box.innerHTML = defs.map((d) => `
        <div class="fd" data-k="${escH(d.key)}" style="--c:${escH(d.color || '#d9a55b')}">
          <div class="fd-name" title="${escH(d.label)}"><i></i><span>${escH(d.label)}</span></div>
          <output class="fd-val"></output>
          <div class="fd-track" tabindex="0" role="slider" aria-label="${escH(d.label)}" aria-valuemin="0" aria-valuemax="100">
            <span class="fd-rail"></span><span class="fd-fill"></span><span class="fd-cap"></span>
          </div>
          ${d.btn ? `<button class="fd-btn" title="${escH(d.btn.title || '')}">${escH(d.btn.label)}</button>` : '<span class="fd-btn fd-nobtn"></span>'}
        </div>`).join('');
    }
    const now = Date.now();
    for (const d of defs) {
      const fd = box.querySelector(`.fd[data-k="${CSS.escape(d.key)}"]`);
      if (!fd) continue;
      const busy = fd.classList.contains('active') || (fd._until && now < fd._until);
      if (!busy) { fd._v = d.value; setPos(fd, d.value); fd.querySelector('.fd-val').textContent = d.text; }
      if (d.btn) fd.querySelector('.fd-btn').classList.toggle('on', !!d.btn.on);
    }
  }

  // valores de los faders de velocidad: 0..1 <-> x0,25..x4 (en el medio, x1)
  const speedFromV = (v) => Math.pow(4, 2 * v - 1);
  const vFromSpeed = (s) => (Math.log(s) / Math.log(4) + 1) / 2;
  const speedText = (s) => '×' + (s < 1 ? s.toFixed(2) : s.toFixed(1)).replace('.', ',');

  /* bancos: qué faders hay en Grupos, Selección y Efectos (lo usan la PC y el celular) */
  const GROUP_COLORS = ['#c9a2ff', '#ff5a5f', '#3fd7ff', '#4fd18b', '#ffb030', '#ff5fc8'];
  function groupColor(name, i) {
    if (/cabez/i.test(name)) return '#c9a2ff';
    return GROUP_COLORS[(i + 1) % GROUP_COLORS.length];
  }
  const pctTxt = (v) => Math.round(v * 100) + '%';
  function defs(bank, ctx) {
    const { S, ids, capsOf, lookOf, api, sendLatest } = ctx;
    const F = { speedFromV, vFromSpeed, speedText };
    const groups = () => (S.groups || []).filter((g) => g.tipo !== 'humo' && g.ids.length);
    if (bank === 'grupos') {
      return [{
        key: 'master', label: 'Master', color: '#d9a55b', value: S.master, text: pctTxt(S.master), fmt: pctTxt,
        onSet: (v) => sendLatest('fd:master', 'master', { value: v }),
        btn: { label: 'Blackout', on: S.blackout, title: 'Apaga todo (tecla B)', click: () => api('blackout', { on: !S.blackout }) },
      }, ...groups().map((g, i) => {
        const v = (S.settings.submasters || {})[g.name] ?? 1;
        return {
          key: 'g:' + g.name, label: g.name, color: groupColor(g.name, i), value: v, text: pctTxt(v), fmt: pctTxt,
          onSet: (x) => sendLatest('fd:g:' + g.name, 'submaster', { group: g.name, value: x }),
          btn: { label: 'Flash', hold: true, title: 'Mantener: ' + g.name + ' a pleno',
            down: () => api('hold', { kind: 'g:' + g.name, on: true }), up: () => api('hold', { kind: 'g:' + g.name, on: false }) },
        };
      })];
    }
    if (bank === 'efx') {
      const st = S.settings;
      const sp = (k, label, color) => ({
        key: k, label, color, value: F.vFromSpeed(st[k] || 1), text: F.speedText(st[k] || 1), fmt: (v) => F.speedText(F.speedFromV(v)),
        onSet: (v) => sendLatest('fd:' + k, 'fx_globals', { [k]: F.speedFromV(v) }),
        btn: { label: 'Normal', click: () => api('fx_globals', { [k]: 1 }) },
      });
      return [
        sp('fx_speed', 'Vel. efectos', '#4fd18b'),
        sp('mov_speed', 'Vel. movim.', '#3fd7ff'),
        { key: 'mov_size', label: 'Tamaño mov.', color: '#c9a2ff', value: (st.mov_size ?? 1) / 1.5, text: pctTxt(st.mov_size ?? 1),
          fmt: (v) => pctTxt(v * 1.5), onSet: (v) => sendLatest('fd:msize', 'fx_globals', { mov_size: v * 1.5 }),
          btn: { label: 'Normal', click: () => api('fx_globals', { mov_size: 1 }) } },
        { key: 'fade', label: 'Fundido', color: '#d9a55b', value: (st.fade ?? 1) / 10, text: Number(st.fade ?? 1).toFixed(1) + ' s',
          fmt: (v) => (v * 10).toFixed(1) + ' s', onSet: (v) => sendLatest('fd:fade', 'show_settings', { fade: Math.round(v * 100) / 10 }),
          btn: { label: '0 s', click: () => api('show_settings', { fade: 0 }) } },
      ];
    }
    // selección: un fader por cada cosa que tenga alguno de los equipos elegidos
    const w = (cap) => ids.filter((i) => capsOf(i).has(cap));
    const first = (list, key, def = 0) => (list.length ? lookOf(list[0])[key] ?? def : def);
    const defs = [];
    const dimIds = w('dim');
    if (dimIds.length) defs.push({ key: 'dim', label: 'Dimmer', color: '#f2ebdf', value: first(dimIds, 'dim'), text: pctTxt(first(dimIds, 'dim')), fmt: pctTxt,
      onSet: (v) => sendLatest('fd:dim', 'set_attrs', { ids: dimIds, attrs: { dim: v } }),
      btn: { label: 'Full', click: () => api('set_attrs', { ids: dimIds, attrs: { dim: 1 } }) } });
    const rgbIds = w('rgb');
    const mix = [['r', 'Rojo', '#ff3b3b', [1, 0, 0, 0]], ['g', 'Verde', '#2ee05a', [0, 1, 0, 0]], ['b', 'Azul', '#3d6bff', [0, 0, 1, 0]]];
    if (rgbIds.some((i) => capsOf(i).has('white'))) mix.push(['w', 'Blanco', '#f6f3ee', [0, 0, 0, 1]]);
    if (rgbIds.length) for (const [k, label, color, solo] of mix) {
      const list = k === 'w' ? rgbIds.filter((i) => capsOf(i).has('white')) : rgbIds;
      defs.push({ key: k, label, color, value: first(list, k), text: pctTxt(first(list, k)), fmt: pctTxt,
        onSet: (v) => sendLatest('fd:' + k, 'set_attrs', { ids: list, attrs: { [k]: v } }),
        btn: { label: 'Solo', title: 'Solo este color, a pleno', click: () => api('set_color', { ids: list, rgbw: solo }) } });
    }
    const stIds = w('strobe');
    if (stIds.length) defs.push({ key: 'strobe', label: 'Strobo', color: '#ffffff', value: first(stIds, 'strobe'),
      text: first(stIds, 'strobe') < 0.005 ? 'No' : pctTxt(first(stIds, 'strobe')), fmt: (v) => (v < 0.005 ? 'No' : pctTxt(v)),
      onSet: (v) => sendLatest('fd:strobe', 'set_attrs', { ids: stIds, attrs: { strobe: v } }),
      btn: { label: 'No', click: () => api('set_attrs', { ids: stIds, attrs: { strobe: 0 } }) } });
    const prIds = w('prot');
    if (prIds.length) defs.push({ key: 'prot', label: 'Rot. prisma', color: '#ffb030', value: first(prIds, 'prot'),
      text: first(prIds, 'prot') < 0.005 ? 'Quieto' : pctTxt(first(prIds, 'prot')), fmt: (v) => (v < 0.005 ? 'Quieto' : pctTxt(v)),
      onSet: (v) => sendLatest('fd:prot', 'set_attrs', { ids: prIds, attrs: { prot: v } }),
      btn: { label: 'Quieto', click: () => api('set_attrs', { ids: prIds, attrs: { prot: 0 } }) } });
    const mvIds = w('mover');
    if (mvIds.length) {
      const y = (S.movers_xy && S.movers_xy[mvIds[0]] ? S.movers_xy[mvIds[0]][1] : 0);
      const yTxt = (yy) => (yy > 0.005 ? '+' : '') + Math.round(yy * 100) + '%';
      defs.push({ key: 'alt', label: 'Altura', color: '#c9a2ff', value: (y + 1) / 2, text: yTxt(y), fmt: (v) => yTxt(v * 2 - 1),
        onSet: (v) => sendLatest('fd:alt', 'front_height', { ids: mvIds, y: v * 2 - 1 }),
        btn: { label: 'Frente', click: () => api('front_height', { ids: mvIds, y: 0, fade: 0.6 }) } });
    }
    return defs;
  }

  window.Faders = { render, defs, speedFromV, vFromSpeed, speedText };
})();
