'use strict';
/* LightShow Remoto: control del show desde el celular */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (v) => Math.round((v || 0) * 100) + '%';
const APP = window.RenacerApp || null;   // existe dentro de la app de Android

let INIT = null, S = null, LIVE = { pv: {} }, PROF = {};
let sel = null, lastScene = null, stack = false;   // sel: equipos elegidos en el celular
const sigs = {};
const changed = (k, v) => { const s = JSON.stringify(v); if (sigs[k] === s) return false; sigs[k] = s; return true; };

const TYPE_LABEL = { cabezal: 'Cabezales', par: 'Pares LED', strobo: 'Strobos', humo: 'Humo', dimmer: 'Dimmers' };
const HEAD_COLORS = ['#ff5aa0', '#ffc24a', '#4fd18b', '#33c8ff', '#b48cff', '#ff8a3d'];
const PAL_NOT_FOR_MOVERS = ['Rosa', 'Violeta', 'Cálido'];

/* ------------------------------------------------------------ conexión */
async function api(cmd, data = {}) {
  try {
    const r = await fetch('/api/cmd', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cmd, ...data }) });
    const j = await r.json();
    if (!j.ok) { toast(j.error || 'No se pudo hacer', true); return null; }
    return j.result ?? true;
  } catch (e) { toast('Sin conexión con la PC', true); return null; }
}
const lanes = {};
function sendLatest(key, cmd, data) {
  const l = (lanes[key] ||= { busy: false, next: null });
  l.next = [cmd, data];
  if (!l.busy) (async () => { l.busy = true; while (l.next) { const [c, d] = l.next; l.next = null; await api(c, d); } l.busy = false; })();
}
let toastT;
function toast(msg, err = false, action = null) {
  const t = $('#toast');
  t.textContent = msg; t.className = 'show' + (err ? ' err' : '');
  if (action) { const b = document.createElement('button'); b.textContent = action.label; b.onclick = () => { t.className = ''; action.fn(); }; t.appendChild(b); }
  clearTimeout(toastT); toastT = setTimeout(() => (t.className = ''), action ? 8000 : err ? 4000 : 1800);
}
function lost(on, msg) {
  $('#lost').classList.toggle('show', on);
  if (msg) $('#lostMsg').textContent = msg;
  $('#conn').className = 'conn ' + (on ? 'err' : 'ok');
}

async function boot() {
  if (APP) { $('#changePc').hidden = false; $('#changePc').onclick = () => APP.changePc(); }
  try {
    const r = await fetch('/api/init');
    if (r.status === 403) { lost(true, (await r.json()).error); setTimeout(boot, 3000); return; }
    INIT = await r.json();
  } catch (e) { lost(true, 'Reintentando…'); setTimeout(boot, 2000); return; }
  PROF = Object.fromEntries(INIT.profiles.map((p) => [p.id, p]));
  buildStatic();
  onSync(INIT.state);
  connect();
}
function connect() {
  const es = new EventSource('/events');
  es.addEventListener('sync', (e) => onSync(JSON.parse(e.data)));
  es.addEventListener('live', (e) => onLive(JSON.parse(e.data)));
  es.onopen = () => lost(false);
  es.onerror = () => {
    lost(true, 'Reintentando…');
    // si la PC cortó (programa reiniciado o control apagado) se vuelve a empezar
    if (es.readyState === EventSource.CLOSED) setTimeout(() => location.reload(), 3000);
  };
}

/* ------------------------------------------------------------ utilidades */
const fixtures = () => (S ? S.fixtures : []);
const fx = (id) => fixtures().find((f) => f.id === id);
const capsOf = (id) => new Set(PROF[fx(id)?.profile]?.caps || []);
const typeOf = (id) => PROF[fx(id)?.profile]?.tipo || 'dimmer';
const lookOf = (id) => (S && S.look[id]) || {};
const lights = () => fixtures().filter((f) => typeOf(f.id) !== 'humo').map((f) => f.id);
const ofType = (t) => fixtures().filter((f) => typeOf(f.id) === t).map((f) => f.id);
const movers = () => fixtures().filter((f) => capsOf(f.id).has('mover')).map((f) => f.id);
// equipos elegidos, en el orden del show
const groupIds = () => lights().filter((i) => sel.has(i));
const moverIds = () => movers().filter((i) => sel.has(i));
function avail(ids) {
  const every = (fn) => ids.length > 0 && ids.every((i) => fn(capsOf(i)));
  return { dim: every((c) => c.has('dim')), color: every((c) => c.has('rgb') || c.has('cw')), rgb: every((c) => c.has('rgb')) };
}
const slotBg = (s) => (s.hex2 ? `linear-gradient(90deg, ${s.hex} 50%, ${s.hex2} 50%)` : (s.hex || '#fff'));
const rgbwHex = ([r, g, b, w]) => '#' + [r, g, b].map((v) => Math.round(Math.min(1, v + w) * 255).toString(16).padStart(2, '0')).join('');

/* ------------------------------------------------------------ dibujos de presets */
function gridSvg(rows) {
  return `<svg viewBox="0 0 80 48" preserveAspectRatio="none" aria-hidden="true">${rows.map((row, r) =>
    row.map(([c, d], k) => `<rect x="${k * 10 + 0.6}" y="${r * 4 + 0.4}" width="8.8" height="3.2" rx="1" fill="${c}" opacity="${(0.07 + 0.93 * d).toFixed(2)}"/>`).join('')).join('')}</svg>`;
}
function pathSvg(paths) {
  const all = paths.flat(), xs = all.map((q) => q[0]), ys = all.map((q) => q[1]);
  const w = Math.max(...xs) - Math.min(...xs), h = Math.max(...ys) - Math.min(...ys);
  const k = 80 / Math.max(w, h * 1.4, 0.4), cx = (Math.max(...xs) + Math.min(...xs)) / 2, cy = (Math.max(...ys) + Math.min(...ys)) / 2;
  const P = ([x, y]) => [(50 + (x - cx) * k).toFixed(1), (50 - (y - cy) * k).toFixed(1)];
  const snap = Math.round(paths[0].length * 0.18);
  return `<svg viewBox="0 0 100 100" aria-hidden="true">${paths.map((pts, i) => `<polyline points="${pts.map((q) => P(q).join(',')).join(' ')}" stroke="${HEAD_COLORS[i % 6]}"/>`).join('')}
    ${paths.map((pts, i) => { const [x, y] = P(pts[snap]); return `<circle cx="${x}" cy="${y}" r="5" fill="${HEAD_COLORS[i % 6]}"/>`; }).join('')}</svg>`;
}
function layoutSvg(points) {
  const sx = (x) => (50 + Math.max(-1.35, Math.min(1.35, x)) / 1.35 * 46).toFixed(2);
  return `<svg viewBox="0 0 100 60" aria-hidden="true"><line x1="4" y1="30" x2="96" y2="30" class="hz"/>
    ${points.map(([x, y], k) => `<line x1="${20 + k * 20}" y1="58" x2="${sx(x)}" y2="${(30 - Math.max(-1.35, Math.min(1.35, y)) / 1.35 * 26).toFixed(1)}" stroke="${HEAD_COLORS[k]}" class="ray"/>`).join('')}</svg>`;
}

/* ------------------------------------------------------------ armado */
function buildStatic() {
  $('#moves').innerHTML = INIT.frontal.presets.map((p, i) => `<button data-move="${i}">${pathSvg(p.paths)}<span>${esc(p.name)}</span></button>`).join('');
  $('#layouts').innerHTML = INIT.frontal.layouts.map((l) => `<button data-layout="${l.id}">${layoutSvg(l.points)}<span>${esc(l.name)}</span></button>`).join('');

  for (const b of $$('.tabs button')) b.onclick = () => {
    $$('.tabs button').forEach((x) => x.classList.toggle('on', x === b));
    $$('main section').forEach((s) => s.classList.toggle('on', s.dataset.tab === b.dataset.go));
    window.scrollTo(0, 0);
  };
  document.addEventListener('contextmenu', (e) => e.preventDefault());

  // barra
  $('#tap').onclick = () => api('tap');
  $('#vdj').onclick = () => { const on = !S.sync_ext; api('sync_set', { on }).then((ok) => ok && toast(on ? 'El tempo sigue a VirtualDJ' : 'Tempo manual: usá Tap')); };
  $('#bo').onclick = () => api('blackout', { on: !S.blackout });
  $('#master').oninput = (e) => { $('#masterVal').textContent = pct(+e.target.value); sendLatest('master', 'master', { value: +e.target.value }); };
  for (const b of $$('[data-hold]')) {
    const k = b.dataset.hold;
    const on = (e) => { e.preventDefault(); b.setPointerCapture?.(e.pointerId); b.classList.add('held'); api('hold', { kind: k, on: true }); };
    const off = () => { if (!b.classList.contains('held')) return; b.classList.remove('held'); api('hold', { kind: k, on: false }); };
    b.addEventListener('pointerdown', on);
    b.addEventListener('pointerup', off); b.addEventListener('pointercancel', off); b.addEventListener('lostpointercapture', off);
  }
  $('#clr').onclick = async () => {
    if (!(await api('clear_all'))) return;
    lastScene = null; sigs.scenes = null;
    toast('Todo a cero', false, { label: 'Deshacer', fn: () => api('undo_clear') });
  };

  // escenas
  $('#go').onclick = () => api('go');
  $('#back').onclick = () => api('back');
  $('#stop').onclick = () => api('stop_cues');
  $('#scenes').addEventListener('click', (e) => {
    const b = e.target.closest('[data-scene]'); if (!b) return;
    lastScene = b.dataset.scene; sigs.scenes = null; api('recall_scene', { id: b.dataset.scene });
  });

  // selección de equipos
  for (const box of $$('[data-sel]')) box.addEventListener('click', (e) => {
    const g = e.target.closest('[data-g]'), f = e.target.closest('[data-fid]');
    if (g) {
      const k = g.dataset.g, mov = box.dataset.sel === 'mov';
      const ids = k === 'all' ? (mov ? movers() : lights()) : k === 'none' ? [] : ofType(k);
      if (mov) { for (const i of movers()) sel.delete(i); for (const i of ids) sel.add(i); }
      else sel = new Set(ids);
    } else if (f) {
      const id = f.dataset.fid;
      sel.has(id) ? sel.delete(id) : sel.add(id);
    } else return;
    sigs.sel = null; sigs.fxp = null; sigs.col = null; render();
  });

  // efectos
  for (const box of [$('#fxDim'), $('#fxCol')]) box.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-fxp]'); if (!b) return;
    const p = INIT.efectos.find((x) => x.id === b.dataset.fxp);
    const ids = groupIds();
    if (!ids.length) return toast('Elegí al menos un equipo', true);
    if (await api('add_fx', { ids, type: p.type, params: { ...p.params } })) toast(p.name + ' en marcha');
  });
  for (const box of [$('#fxActive'), $('#movActive')]) box.addEventListener('click', (e) => {
    const b = e.target.closest('[data-del]'); if (b) api('remove_fx', { id: b.dataset.del });
  });

  // movimientos
  $('#moves').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-move]'); if (!b) return;
    const p = INIT.frontal.presets[+b.dataset.move];
    const ids = moverIds();
    if (!ids.length) return toast('Elegí al menos un cabezal', true);
    if (await api('add_fx', { ids, type: p.type, params: { ...p.params, name: p.name }, stack })) toast(p.name + (stack ? ' sumado' : ' en marcha'));
  });
  $('#layouts').addEventListener('click', (e) => { const b = e.target.closest('[data-layout]'); if (!b) return; const ids = moverIds(); if (!ids.length) return toast('Elegí al menos un cabezal', true); api('front_layout', { ids, name: b.dataset.layout }); });
  $('#stack').onclick = () => { stack = !stack; $('#stack').classList.toggle('on', stack); $('#stack').setAttribute('aria-pressed', stack); };
  $('#movStop').onclick = () => {
    const ids = new Set(moverIds());
    const moves = S.fx.filter((f) => INIT.fx_types[f.type]?.family === 'pos' && f.ids.some((i) => ids.has(i)));
    moves.forEach((f) => api('remove_fx', { id: f.id }));
    toast(moves.length ? 'Movimiento frenado' : 'No hay movimiento andando');
  };

  // color e intensidad (sin equipos elegidos no hace nada)
  const pick = () => { const ids = groupIds(); if (!ids.length) toast('Elegí al menos un equipo', true); return ids; };
  $('#dim').oninput = (e) => { $('#dimVal').textContent = pct(+e.target.value); const ids = groupIds(); if (ids.length) sendLatest('dim', 'set_attrs', { ids, attrs: { dim: +e.target.value } }); };
  for (const b of $$('[data-dim]')) b.onclick = () => { const ids = pick(); if (ids.length) api('set_attrs', { ids, attrs: { dim: +b.dataset.dim } }); };
  $('#off').onclick = () => { const ids = pick(); if (ids.length) api('clear', { ids }); };
  $('#palette').addEventListener('click', (e) => { const b = e.target.closest('[data-pal]'); if (!b) return; const ids = pick(); if (ids.length) api('set_color', { ids, rgbw: INIT.palette[+b.dataset.pal].rgbw }); });
  $('#wheel').addEventListener('click', (e) => {
    const b = e.target.closest('[data-ws]'); if (!b) return;
    const ids = pick(); if (!ids.length) return;
    api('set_wheel', { ids, key: 'cw', index: +b.dataset.ws });
    if ((lookOf(ids[0]).dim ?? 0) === 0) api('set_attrs', { ids, attrs: { dim: 1 } });
  });
  $('#mine').addEventListener('click', (e) => { const b = e.target.closest('[data-mine]'); if (!b) return; const ids = pick(); if (ids.length) api('set_color', { ids, rgbw: S.app_settings.colores_propios[+b.dataset.mine].rgbw }); });

  // haz: gobo, prisma, foco y strobo del equipo (solo a los elegidos que lo tienen)
  const withCap = (c) => groupIds().filter((i) => capsOf(i).has(c));
  $('section[data-tab=haz]').addEventListener('click', (e) => {
    const b = e.target.closest('[data-slot]');
    if (b) { const ids = withCap(b.dataset.slot); if (ids.length) api('set_wheel', { ids, key: b.dataset.slot, index: +b.dataset.i }); }
    const st = e.target.closest('[data-strb]');
    if (st) { const ids = withCap('strobe'); if (ids.length) api('set_attrs', { ids, attrs: { strobe: +st.dataset.strb } }); }
  });
  for (const k of ['prot', 'focus', 'strobe']) $('#' + k).oninput = (e) => {
    const ids = withCap(k); if (!ids.length) return;
    $('#' + k + 'Val').textContent = hazTxt(k, +e.target.value);
    sendLatest(k, 'set_attrs', { ids, attrs: { [k]: +e.target.value } });
  };

  window.addEventListener('blur', () => { for (const k of ['flash', 'strobe', 'strobe2']) if (S && S.holds.includes(k)) api('hold', { kind: k, on: false }); });
}

/* ------------------------------------------------------------ estado */
function onSync(s) { S = s; render(); }
function onLive(d) {
  LIVE = d;
  $('#beat').classList.toggle('hit', d.beat < 0.15);
  if (d.sync) renderSync(d.sync);
  if (S && d.cue !== S.cue_index) { S.cue_index = d.cue; renderCues(); }
}
function renderSync(sy) {
  const b = $('#vdj');
  b.className = 'vdj ' + (!sy.on ? 'off' : sy.beats ? 'live' : 'wait');
  b.setAttribute('aria-pressed', sy.on);
  $('#tap').disabled = !!sy.on;
}

function render() {
  if (!S) return;
  $('#bpm').textContent = Math.round(S.bpm);
  $('#bo').classList.toggle('on', S.blackout);
  for (const b of $$('[data-hold]')) b.classList.toggle('held', S.holds.includes(b.dataset.hold));
  if (document.activeElement !== $('#master')) $('#master').value = S.master;
  $('#masterVal').textContent = pct(S.master);
  renderSel(); renderCues(); renderScenes(); renderFx(); renderMov(); renderColor(); renderHaz();
}

function renderSel() {
  const all = lights(), have = new Set(all);
  if (sel === null) sel = new Set(all);
  for (const i of [...sel]) if (!have.has(i)) sel.delete(i);
  const present = [...new Set(all.map(typeOf))];
  const looks = all.map((i) => [i, tileColor(i)]);
  if (!changed('sel', [all, [...sel], looks, fixtures().map((f) => f.name)])) return;
  let count = {};
  const tile = (i) => {
    const t = typeOf(i), n = (count[t] = (count[t] || 0) + 1), f = fx(i);
    const word = t === 'cabezal' ? 'Cabezal' : t === 'par' ? 'Par' : (TYPE_LABEL[t] || 'Equipo').replace(/s$/, '');
    return `<button class="fxt ${sel.has(i) ? 'on' : ''}" data-fid="${i}" aria-pressed="${sel.has(i)}" title="${esc(f.name)}" style="--lc:${tileColor(i)}">
      <b>${n}</b><small>${esc(word)}</small></button>`;
  };
  for (const box of $$('[data-sel]')) {
    count = {};
    const mov = box.dataset.sel === 'mov';
    const ids = mov ? movers() : all;
    const on = (k) => {
      const g = k === 'all' ? ids : k === 'none' ? [] : ofType(k);
      const cur = ids.filter((i) => sel.has(i));
      return cur.length === g.length && g.every((i) => sel.has(i));
    };
    const groups = mov ? [['all', 'Todos los cabezales'], ['none', 'Ninguno']]
      : [['all', 'Todos'], ...present.map((t) => [t, TYPE_LABEL[t] || t]), ['none', 'Ninguno']];
    box.innerHTML = `<div class="chips">${groups.map(([k, l]) => `<button data-g="${k}" class="${on(k) ? 'on' : ''}">${esc(l)}</button>`).join('')}</div>
      ${[...new Set(ids.map(typeOf))].map((t) => `<div class="tiles">${ids.filter((i) => typeOf(i) === t).map(tile).join('')}</div>`).join('')}`;
  }
}
// color actual de cada equipo para la rayita del botón
function tileColor(i) {
  const l = lookOf(i), p = PROF[fx(i)?.profile] || {};
  if ((l.dim ?? 1) <= 0.01) return '#2a2331';
  if ('r' in l) return rgbwHex([l.r || 0, l.g || 0, l.b || 0, l.w || 0]);
  const sl = (p.color_wheel || [])[l.cw ?? 0];
  return sl ? (sl.hex || '#fff') : '#f6efe2';
}

function renderCues() {
  const i = S.cue_index, cues = S.cues;
  const nextIdx = i + 1 < cues.length ? i + 1 : (S.settings.cue_loop && cues.length ? 0 : -1);
  const c = cues[nextIdx];
  const name = c ? (S.scenes.find((x) => x.id === c.scene)?.name || 'Escena') : '';
  $('#standby').classList.toggle('armed', !!c);
  $('#nextCue').innerHTML = c ? `Standby: <b>${nextIdx + 1}. ${esc(name)}</b>` : (cues.length ? 'Fin de la secuencia' : 'Sin pasos en la secuencia');
  $('#go').textContent = i >= 0 && cues.length ? `GO  ${Math.min(i + 2, cues.length)}/${cues.length}` : 'GO';
}

function renderScenes() {
  if (!changed('scenes', [S.scenes, lastScene])) return;
  $('#scenes').innerHTML = S.scenes.length ? S.scenes.map((s) => `<button class="scene ${s.id === lastScene ? 'last' : ''}" style="--sc:${esc(s.color)}" data-scene="${s.id}">${esc(s.name)}</button>`).join('')
    : '<p class="hint">Todavía no hay escenas. Se graban desde la PC.</p>';
}

function renderFx() {
  const ids = groupIds(), av = avail(ids);
  if (changed('fxp', [av, ids.length])) {
    const ok = (need) => (need === 'dim' ? av.dim : need === 'rgb' ? av.rgb : av.color);
    const btns = (fam) => INIT.efectos.filter((p) => p.family === fam && ok(p.needs)).map((p) => `<button data-fxp="${p.id}">${gridSvg(p.grid)}<span>${esc(p.name)}</span></button>`).join('');
    const d = btns('dim'), c = btns('color');
    $('#fxDim').innerHTML = d; $('#fxCol').innerHTML = c;
    $('#fxDimT').style.display = d ? '' : 'none'; $('#fxColT').style.display = c ? '' : 'none';
    $('#fxNone').textContent = !ids.length ? 'Elegí arriba los equipos.' : d || c ? '' : 'Estos equipos no tienen efectos en común.';
  }
  const act = (list, empty) => list.length ? list.map((f) => {
    const n = f.ids.length;
    return `<div class="active"><b>${esc(f.name || INIT.fx_types[f.type]?.name || f.type)}</b><span>${n} equipo${n > 1 ? 's' : ''}</span><button data-del="${f.id}">Quitar</button></div>`;
  }).join('') : `<p class="hint">${empty}</p>`;
  if (changed('fxa', S.fx.map((f) => [f.id, f.name, f.type, f.ids.length]))) {
    const isMove = (f) => INIT.fx_types[f.type]?.family === 'pos';
    $('#fxActive').innerHTML = act(S.fx.filter((f) => !isMove(f)), 'Ningún efecto andando.');
    $('#movActive').innerHTML = act(S.fx.filter(isMove), 'Ningún movimiento andando.');
  }
}

function renderMov() {
  const n = movers().length, k = moverIds().length;
  $('#movHint').textContent = !n ? 'No hay cabezales en el show.'
    : S.rig && !S.rig.calibrated ? 'Ojo: el frente al público todavía no está ajustado (se hace en la PC).'
    : !k ? 'Elegí arriba los cabezales.'
    : `Se aplica a ${k === n ? 'los ' + n + ' cabezales' : k === 1 ? '1 cabezal' : k + ' cabezales'}.`;
}

function renderColor() {
  const ids = groupIds();
  const wheel = ids.filter((i) => capsOf(i).has('cw') && !capsOf(i).has('rgb'));
  const rgb = ids.filter((i) => capsOf(i).has('rgb'));
  const onlyWheel = ids.length > 0 && wheel.length === ids.length, onlyRgb = ids.length > 0 && rgb.length === ids.length;
  const dimIds = ids.filter((i) => capsOf(i).has('dim'));
  const dv = dimIds.length ? lookOf(dimIds[0]).dim : 0;
  if (document.activeElement !== $('#dim')) $('#dim').value = dv || 0;
  $('#dimVal').textContent = pct(dv);
  $('#palBox').style.display = onlyWheel ? 'none' : '';
  $('#wheelBox').style.display = onlyWheel ? '' : 'none';
  const mine = (S.app_settings && S.app_settings.colores_propios) || [];
  $('#mineBox').style.display = onlyRgb && mine.length ? '' : 'none';
  const slots = onlyWheel ? (PROF[fx(wheel[0]).profile]?.color_wheel || []) : [];
  const cur = onlyWheel ? lookOf(wheel[0]).cw : -1;
  if (!changed('col', [wheel.length > 0, slots, cur, mine])) return;
  $('#palette').innerHTML = INIT.palette.map((c, i) => (wheel.length && PAL_NOT_FOR_MOVERS.includes(c.nombre)) ? ''
    : `<button class="swatch" style="--sw:${c.hex}" data-pal="${i}">${esc(c.nombre)}</button>`).join('');
  $('#wheel').innerHTML = slots.map((sl, i) => `<button class="swatch ${i === cur ? 'cur' : ''}" style="--sw:${slotBg(sl)}" data-ws="${i}">${esc(sl.nombre)}</button>`).join('');
  $('#mine').innerHTML = mine.map((m, i) => `<button class="swatch" style="--sw:${rgbwHex(m.rgbw)}" data-mine="${i}">${esc(m.nombre)}</button>`).join('');
}

const hazTxt = (k, v) => (v == null ? '—' : k === 'strobe' && v < 0.005 ? 'no' : k === 'prot' && v < 0.005 ? 'quieto' : pct(v));
function renderHaz() {
  const ids = groupIds();
  const w = (c) => ids.filter((i) => capsOf(i).has(c));
  const show = (el, on) => ($(el).style.display = on ? '' : 'none');
  const g = w('gobo'), pr = w('prism'), po = w('prot'), fo = w('focus'), sb = w('strobe');
  show('#hzGobo', g.length); show('#hzPrism', pr.length); show('#hzProt', po.length); show('#hzFocus', fo.length); show('#hzStrobe', sb.length);
  $('#hazNone').textContent = !ids.length ? 'Elegí arriba los equipos.' : (g.length || pr.length || fo.length || sb.length) ? '' : 'Los equipos elegidos no tienen gobos, prisma ni strobo.';
  for (const [k, list] of [['prot', po], ['focus', fo], ['strobe', sb]]) {
    const v = list.length ? (lookOf(list[0])[k] ?? 0) : null;
    if (document.activeElement !== $('#' + k)) $('#' + k).value = v ?? 0;
    $('#' + k + 'Val').textContent = hazTxt(k, v);
  }
  const slots = (list, key) => (list.length ? PROF[fx(list[0]).profile]?.[key] || [] : []);
  const cur = (list, key) => (list.length ? lookOf(list[0])[key] ?? 0 : -1);
  if (!changed('haz', [slots(g, 'gobo'), cur(g, 'gobo'), slots(pr, 'prism'), cur(pr, 'prism')])) return;
  const html = (list, key) => slots(list, key).map((sl, i) => `<button class="${i === cur(list, key) ? 'on' : ''}" data-slot="${key}" data-i="${i}">${esc(sl.nombre)}</button>`).join('');
  $('#goboSlots').innerHTML = html(g, 'gobo');
  $('#prismSlots').innerHTML = html(pr, 'prism');
}

boot();
