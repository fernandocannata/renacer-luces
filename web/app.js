'use strict';
/* Renacer LightShow — interfaz */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (v) => Math.round((v || 0) * 100) + '%';

let INIT = null;        // datos fijos (perfiles, paleta…)
let S = null;           // estado del show (llega por "sync")
let LIVE = { pv: {} };  // vista previa en vivo
let PROF = {};          // perfiles por id
const sel = new Set();  // equipos seleccionados
let lastScene = null;
let editScenes = false;
let dragging = null;    // control que el usuario está moviendo
const sigs = {};        // firmas para no redibujar de más

const TYPE_LABEL = { cabezal: 'Cabezales', par: 'Pares LED', strobo: 'Strobos', humo: 'Humo', dimmer: 'Dimmers' };
const TYPE_ORDER = ['cabezal', 'par', 'strobo', 'dimmer', 'humo'];

/* ------------------------------------------------------------ comunicación */
async function api(cmd, data = {}) {
  try {
    const r = await fetch('/api/cmd', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cmd, ...data }) });
    const j = await r.json();
    if (!j.ok) { toast(j.error || 'No se pudo hacer', true); return null; }
    return j.result ?? true;
  } catch (e) { toast('Sin conexión con el programa', true); return null; }
}
// Envía siempre el último valor, en orden, sin saturar (para sliders)
const lanes = {};
function sendLatest(key, cmd, data) {
  const l = (lanes[key] ||= { busy: false, next: null });
  l.next = [cmd, data];
  if (!l.busy) pump(l);
}
async function pump(l) {
  l.busy = true;
  while (l.next) { const [c, d] = l.next; l.next = null; await api(c, d); }
  l.busy = false;
}

let toastT = null;
function toast(msg, err = false, action = null) {
  const t = $('#toast');
  t.textContent = msg; t.className = 'show' + (err ? ' err' : '');
  if (action) {
    const b = document.createElement('button');
    b.className = 'small'; b.textContent = action.label;
    b.onclick = () => { t.className = ''; action.fn(); };
    t.appendChild(b);
  }
  clearTimeout(toastT); toastT = setTimeout(() => (t.className = ''), action ? 8000 : err ? 4200 : 2200);
}

function changed(key, val) {
  const s = JSON.stringify(val);
  if (sigs[key] === s) return false;
  sigs[key] = s; return true;
}

function setVal(el, v) {
  if (!el || el === dragging || (document.activeElement === el && el.type !== 'range')) return;
  if (el.type === 'checkbox') el.checked = !!v; else el.value = v;
}
document.addEventListener('pointerdown', (e) => { if (e.target.matches('input[type=range]')) dragging = e.target; });
window.addEventListener('pointerup', () => { dragging = null; });

/* ------------------------------------------------------------ utilidades */
const fixtures = () => (S ? S.fixtures : []);
const fx = (id) => fixtures().find((f) => f.id === id);
const profOf = (id) => PROF[fx(id)?.profile] || null;
const capsOf = (id) => new Set(profOf(id)?.caps || []);
const typeOf = (id) => profOf(id)?.tipo || 'dimmer';
const ordered = (ids) => fixtures().map((f) => f.id).filter((i) => ids.has ? ids.has(i) : ids.includes(i));
const selIds = () => ordered(sel);
const selWith = (cap) => selIds().filter((i) => capsOf(i).has(cap));
const lookOf = (id) => (S && S.look[id]) || {};
const firstVal = (cap, key) => { const i = selWith(cap)[0]; return i ? lookOf(i)[key] : undefined; };

function hexToRgb(h) { h = h.replace('#', ''); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255); }

/* ------------------------------------------------------------ arranque */
async function boot() {
  const r = await fetch('/api/init');
  INIT = await r.json();
  PROF = Object.fromEntries(INIT.profiles.map((p) => [p.id, p]));
  buildStatic();
  onSync(INIT.state);
  connect();
}

function connect() {
  const es = new EventSource('/events');
  es.addEventListener('sync', (e) => onSync(JSON.parse(e.data)));
  es.addEventListener('live', (e) => onLive(JSON.parse(e.data)));
  es.addEventListener('bye', () => { $('#lost').classList.add('show'); });
  es.onopen = async () => {
    $('#lost').classList.remove('show');
    if (INIT) { // por si el programa se reinició con perfiles nuevos
      try { const j = await (await fetch('/api/profiles')).json(); PROF = Object.fromEntries(j.map((p) => [p.id, p])); } catch (e) { /* nada */ }
    }
  };
  es.onerror = () => { $('#lost').classList.add('show'); };
}

/* ------------------------------------------------------------ sync / live */
function onSync(s) {
  S = s;
  for (const id of [...sel]) if (!fx(id)) sel.delete(id);
  renderTop();
  renderTiles();
  renderProgrammer();
  renderScenes();
  renderCues();
  renderFxList();
  renderMov();
  renderPositions();
  renderPatch();
  renderProbar();
  renderShow();
}

function onLive(d) {
  LIVE = d;
  let smoke = 0;
  for (const t of $$('.tile')) {
    const p = d.pv[t.dataset.id];
    if (!p) continue;
    t.style.setProperty('--c', p.c);
    t.style.setProperty('--d', p.d);
    t.classList.toggle('strobing', p.s > 0.01 && p.d > 0.02);
    if (t.classList.contains('t-humo')) smoke = Math.max(smoke, p.d);
    if (p.p != null) {
      if (S && S.rig && S.rig.calibrated && p.x != null) {
        t.style.setProperty('--rot', (-Math.max(-1.3, Math.min(1.3, p.x)) * 38).toFixed(1) + 'deg');
        t.style.setProperty('--tl', (0.5 + 0.5 * Math.max(0, Math.min(1, (p.y + 1.3) / 2.6))).toFixed(3));
      } else {
        t.style.setProperty('--rot', (-(p.p - 0.5) * 110).toFixed(1) + 'deg');
        t.style.setProperty('--tl', (0.55 + 0.45 * (p.t ?? 0.5)).toFixed(3));
      }
    }
  }
  const st = $('.stage');
  if (st) st.style.setProperty('--smoke', smoke.toFixed(2));
  $('#beat').classList.toggle('hit', d.beat < 0.15);
  if (d.sync) renderSync(d.sync);
  renderOut(d.out);
  if (S && d.cue !== S.cue_index) { S.cue_index = d.cue; sigs.cues = null; renderCues(); }
  drawXYPoints();
  drawAudience();
}

/* ------------------------------------------------------------ barra superior */
function renderTop() {
  $('#bpm').textContent = Math.round(S.bpm);
  setVal($('#fade'), S.settings.fade);
  $('#fadeVal').textContent = Number(S.settings.fade).toFixed(1) + ' s';
  setVal($('#master'), S.master);
  $('#masterVal').textContent = pct(S.master);
  $('#btnBlackout').classList.toggle('on', S.blackout);
  for (const [k, b] of [['flash', '#btnFlash'], ['strobe', '#btnStrobe'], ['strobe2', '#btnStrobe2']])
    $(b).classList.toggle('held', S.holds.includes(k));
  renderStrobe2();
  if (S.output) renderOut(S.output);
}

function renderOut(o) {
  if (!o) return;
  const b = $('#out');
  b.className = o.kind === 'sim' ? 'sim' : o.connected ? 'ok' : 'err';
  $('#outLbl').textContent = o.kind === 'sim' ? 'Simulador' : o.connected ? 'Interfaz conectada' : 'Interfaz no encontrada';
  const det = $('#outDetail');
  if (det) det.textContent = o.label + (o.connected ? ` — enviando ${Math.round(o.fps || 0)} cuadros por segundo.` : '') + (o.error ? ' ' + o.error : '');
}

/* ------------------------------------------------------------ tempo desde VirtualDJ */
function renderSync(sy) {
  const b = $('#btnSync');
  const state = !sy.on ? 'off' : sy.beats ? 'live' : 'wait';
  b.className = 'syncbtn ' + state;
  b.setAttribute('aria-pressed', sy.on);
  const msg = !sy.on ? 'Apagado: el tempo lo marcás vos con Tap.'
    : sy.beats ? `Siguiendo a VirtualDJ${sy.bpm ? ' (' + sy.bpm.toFixed(1) + ' BPM)' : ''}.`
    : sy.connected ? 'VirtualDJ conectado: esperando que suene un tema.'
    : sy.listening ? 'Esperando a VirtualDJ: tocá en VirtualDJ la tecla con os2l_button (ver Show y ajustes).'
    : (sy.error || 'No se pudo abrir la conexión.');
  b.title = 'Seguir el tempo de VirtualDJ. ' + msg;
  $('#btnTap').disabled = !!sy.on;
  $('#btnTap').title = sy.on ? 'Con VDJ prendido, el tempo lo marca VirtualDJ' : 'Tocá al ritmo de la música (tecla T)';
  $('#syncDetail').textContent = (sy.connected ? 'Estado: VirtualDJ conectado. ' : 'Estado: VirtualDJ no conectado. ') + msg
    + ` (conexiones: ${sy.connections || 0}, mensajes: ${sy.messages || 0})`;
  $('#syncPort').textContent = sy.port;
}

/* ------------------------------------------------------------ strobo 2 */
function renderStrobe2() {
  const st = (S.settings && S.settings.strobe2) || {};
  for (const r of $$('input[name=s2mode]')) r.checked = (r.value === 'sync') === !!st.sync;
  $$('[data-s2div]').forEach((b) => (b.className = 'small ' + (st.sync && +b.dataset.s2div === +st.div ? 'on' : 'ghost')));
  setVal($('#s2hz'), st.hz);
  $('#s2hzVal').textContent = (+st.hz || 0).toFixed(1) + '/s';
  setVal($('#s2white'), st.white);
  const rate = st.sync ? S.bpm / 60 * st.div : st.hz;
  $('#s2rate').textContent = `Ahora: ${rate.toFixed(1).replace('.0', '')} destellos por segundo${st.sync ? ' a ' + Math.round(S.bpm) + ' BPM' : ''}.` + (rate > 12 ? ' Más de 12 por segundo puede verse irregular.' : '');
}

/* ------------------------------------------------------------ equipos */
function renderTiles() {
  const sig = fixtures().map((f) => [f.id, f.name, f.profile]);
  if (changed('tiles', sig)) {
    const groups = {};
    for (const f of fixtures()) (groups[typeOf(f.id)] ||= []).push(f);
    const types = Object.keys(groups).sort((a, b) => TYPE_ORDER.indexOf(a) - TYPE_ORDER.indexOf(b));
    const rigTypes = types.filter((t) => t !== 'humo');
    const tileHtml = (f, i) => {
      const t = typeOf(f.id), mover = capsOf(f.id).has('mover');
      return `<button class="tile t-${t} ${mover ? 'mover' : ''}" data-id="${f.id}" title="${esc(f.name)} — dirección ${f.address}">
          <span class="beam"></span>${fixtureSvg(t, mover)}<span class="nm">${i + 1}</span></button>`;
    };
    $('#tileGroups').innerHTML = types.length ? `
      <div class="stage">
        <div class="haze"></div><div class="valance"></div><div class="leg l"></div><div class="leg r"></div>
        ${rigTypes.map((t) => `<div class="rig"><div class="truss"><span class="tag">${esc(TYPE_LABEL[t] || t)}</span></div>
            <div class="fixrow">${groups[t].map(tileHtml).join('')}</div></div>`).join('')}
        <div class="apron">${groups.humo ? `<div class="rig floor-rig"><div class="fixrow">${groups.humo.map(tileHtml).join('')}</div></div>` : ''}</div>
      </div>`
      : `<div class="emptysel">El escenario está vacío. Agregá tus equipos en “Equipos y direcciones”.</div>`;
    layoutBeams();
    const present = new Set(fixtures().map((f) => typeOf(f.id)));
    $('#groupChips').innerHTML = [
      ['all', 'Todos'],
      ...TYPE_ORDER.filter((t) => present.has(t)).map((t) => ['type:' + t, TYPE_LABEL[t]]),
      ['odd', '1, 3, 5…'], ['even', '2, 4, 6…'], ['h1', 'Primera mitad'], ['h2', 'Segunda mitad'],
      ['inv', 'Invertir'], ['none', 'Ninguno'],
    ].map(([k, l]) => `<button class="ghost" data-g="${k}">${esc(l)}</button>`).join('');
  }
  paintSelection();
}

/* dibujo de cada equipo colgado en la vara */
function fixtureSvg(type, mover) {
  const clamp = '<rect x="17" y="0" width="6" height="5" rx="1" class="clamp"/>';
  let g;
  if (mover) g = clamp + '<path d="M7 5h26v19a4 4 0 0 1-4 4h-2V12H13v16h-2a4 4 0 0 1-4-4z" class="metal"/>'
    + '<rect x="12.5" y="10" width="15" height="21" rx="5" class="metal2"/><ellipse cx="20" cy="31" rx="5.5" ry="2.6" class="lens"/>';
  else if (type === 'strobo') g = clamp + '<rect x="3" y="6" width="34" height="15" rx="3" class="metal2"/><rect x="6" y="15" width="28" height="6" rx="2" class="lens"/>';
  else if (type === 'humo') g = '<rect x="3" y="12" width="30" height="18" rx="3" class="metal2"/><rect x="33" y="18" width="5" height="6" rx="1" class="metal"/><circle cx="12" cy="21" r="3" class="lens"/>';
  else g = clamp + '<path d="M11 5h18l3 22H8z" class="metal2"/><ellipse cx="20" cy="27.5" rx="12.5" ry="3.6" class="lens"/>';
  return `<svg class="body" viewBox="0 0 40 34" aria-hidden="true">${g}</svg>`;
}

/* largo de cada haz: desde la lente hasta el piso del escenario */
function layoutBeams() {
  const st = $('.stage');
  if (!st) return;
  const floor = st.querySelector('.apron').getBoundingClientRect().top + 64;
  for (const t of $$('.tile', st)) {
    const r = t.getBoundingClientRect();
    t.style.setProperty('--len', Math.max(40, floor - r.top - 30) + 'px');
  }
}
window.addEventListener('resize', () => layoutBeams());

function paintSelection() {
  for (const t of $$('.tile')) t.classList.toggle('sel', sel.has(t.dataset.id));
  const n = sel.size;
  $('#selCount').textContent = n ? `${n} seleccionado${n > 1 ? 's' : ''}` : '';
}

function applyGroup(g) {
  const lights = fixtures().filter((f) => typeOf(f.id) !== 'humo').map((f) => f.id);
  const base = sel.size ? selIds() : lights;
  let next;
  if (g === 'all') next = lights;
  else if (g === 'none') next = [];
  else if (g.startsWith('type:')) next = fixtures().filter((f) => typeOf(f.id) === g.slice(5)).map((f) => f.id);
  else if (g === 'odd') next = base.filter((_, i) => i % 2 === 0);
  else if (g === 'even') next = base.filter((_, i) => i % 2 === 1);
  else if (g === 'h1') next = base.slice(0, Math.ceil(base.length / 2));
  else if (g === 'h2') next = base.slice(Math.ceil(base.length / 2));
  else if (g === 'inv') next = lights.filter((i) => !sel.has(i));
  sel.clear(); next.forEach((i) => sel.add(i));
  selectionChanged();
}

function selectionChanged() {
  paintSelection();
  $('#fan').value = 0; $('#fanVal').textContent = '0';
  sigs.prog = null;
  renderProgrammer();
  if (S) renderMov();
}

/* ------------------------------------------------------------ programador */
/* qué se puede hacer con lo elegido: solo lo que TODOS admiten */
function availability(ids) {
  const every = (fn) => ids.length > 0 && ids.every((i) => fn(capsOf(i)));
  const haz = ['cw', 'gobo', 'prism', 'focus', 'strobe'].filter((c) => every((cs) => cs.has(c)));
  const a = {
    dim: every((c) => c.has('dim')), mover: every((c) => c.has('mover')),
    color: every((c) => c.has('rgb') || c.has('cw')), rgb: every((c) => c.has('rgb')), haz,
  };
  a.tabs = ids.length ? { color: a.dim, pos: a.mover, mov: a.mover, haz: haz.length > 0, fx: a.dim || a.color }
    : { color: true, pos: true, mov: true, haz: true, fx: true };
  return a;
}
function renderTabs(ids, av) {
  let firstVisible = null, activeHidden = false;
  for (const b of $$('#progTabs button')) {
    const ok = av.tabs[b.dataset.p] !== false;
    b.hidden = !ok;
    if (ok && !firstVisible) firstVisible = b;
    if (!ok && b.classList.contains('on')) activeHidden = true;
  }
  if (activeHidden && firstVisible) firstVisible.click();
  const kinds = [...new Set(ids.map(typeOf))].map((t) => TYPE_LABEL[t] || t);
  $('#selKind').textContent = !kinds.length ? ''
    : kinds.length === 1 ? 'Opciones para ' + kinds[0]
    : kinds.slice(0, -1).join(', ') + ' y ' + kinds.at(-1) + ': solo lo que tienen en común';
  $('#selKind').style.display = kinds.length ? '' : 'none';
}
function renderFxPresets(ids, av) {
  const okFor = (need) => !ids.length || (need === 'dim' ? av.dim : need === 'rgb' ? av.rgb : av.color);
  if (!changed('fxPresets', [ids.length, av.dim, av.color, av.rgb])) return;
  const grid = (rows) => `<svg viewBox="0 0 80 48" preserveAspectRatio="none" aria-hidden="true">${rows.map((row, r) =>
    row.map(([c, d], k) => `<rect x="${k * 10 + 0.6}" y="${r * 4 + 0.4}" width="8.8" height="3.2" rx="1" fill="${c}" opacity="${(0.07 + 0.93 * d).toFixed(2)}"/>`).join('')).join('')}</svg>`;
  const btns = (fam) => INIT.efectos.filter((p) => p.family === fam && okFor(p.needs))
    .map((p) => `<button data-fxpreset="${p.id}">${grid(p.grid)}<span>${esc(p.name)}</span></button>`).join('');
  const dimB = btns('dim'), colB = btns('color');
  $('#fxDim').innerHTML = dimB; $('#fxCol').innerHTML = colB;
  $('#fxDimTitle').style.display = dimB ? '' : 'none';
  $('#fxColTitle').style.display = colB ? '' : 'none';
  $('#fxNone').textContent = dimB || colB ? '' : 'Lo que elegiste no tiene efectos en común.';
}

function renderProgrammer() {
  const ids = selIds();
  const av = availability(ids);
  renderTabs(ids, av);
  renderFxPresets(ids, av);
  $('#noSel').style.display = ids.length ? 'none' : '';
  const dim = firstVal('dim', 'dim');
  setVal($('#dim'), dim ?? 0);
  $('#dimVal').textContent = dim == null ? '—' : pct(dim);

  // posición
  const movers = selWith('mover');
  $('#posHint').textContent = movers.length
    ? 'Arrastrá dentro del recuadro para apuntar. Si elegiste varios cabezales, se mueven juntos manteniendo el abanico.'
    : 'Elegí uno o más cabezales para moverlos.';
  const pts = firstVal('pts', 'pts');
  setVal($('#pts'), pts ?? 0);
  $('#ptsVal').textContent = pts == null ? '—' : (pts < 0.05 ? 'máxima' : pct(1 - pts));

  // haz
  const has = (c) => av.haz.includes(c) || (c === 'prot' && av.haz.includes('prism'));
  $('#hazCw').style.display = has('cw') ? '' : 'none';
  $('#hazGobo').style.display = has('gobo') ? '' : 'none';
  $('#hazPrism').style.display = has('prism') || has('prot') ? '' : 'none';
  $('#hazFocus').style.display = has('focus') ? '' : 'none';
  $('#hazStrobe').style.display = has('strobe') ? '' : 'none';
  $('#hazEmpty').style.display = ['cw', 'gobo', 'prism', 'focus', 'strobe'].some(has) ? 'none' : '';
  const slotsSig = ['cw', 'gobo', 'prism'].map((c) => [selWith(c)[0] ? fx(selWith(c)[0]).profile : null, firstVal(c, c)]);
  if (changed('slots', slotsSig)) {
    renderSlots('#cwSlots', 'cw', 'color_wheel', true);
    renderSlots('#goboSlots', 'gobo', 'gobo');
    renderSlots('#prismSlots', 'prism', 'prism');
  }
  for (const [id, cap, key] of [['prot', 'prot', 'prot'], ['focus', 'focus', 'focus'], ['strobe', 'strobe', 'strobe']]) {
    const v = firstVal(cap, key);
    setVal($('#' + id), v ?? 0);
    $('#' + id + 'Val').textContent = v == null ? '—' : (id === 'strobe' && v < 0.005 ? 'no' : id === 'prot' && v < 0.005 ? 'quieto' : pct(v));
  }
  drawXYPoints();
}

function renderSlots(sel_, cap, key, swatch = false) {
  const first = selWith(cap)[0];
  const slots = first ? (PROF[fx(first).profile][key] || []) : [];
  const cur = first ? lookOf(first)[cap] : -1;
  $(sel_).innerHTML = slots.map((s, i) => `<button class="${i === cur ? 'on' : 'ghost'}" data-slot="${cap}" data-i="${i}">
     ${swatch ? `<span class="chip" style="background:${esc(s.hex || '#fff')}"></span>` : ''}${esc(s.nombre)}</button>`).join('');
}

/* XY pad */
let xyDrag = null;
function xyFromEvent(e) {
  const r = $('#xy').getBoundingClientRect();
  return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, 1 - (e.clientY - r.top) / r.height))];
}
function drawXYPoints() {
  const pad = $('#xy');
  if (!pad || !S) return;
  const movers = selWith('mover');
  const pts = $$('.pt', pad);
  while (pts.length < movers.length) { const d = document.createElement('span'); d.className = 'pt'; pad.appendChild(d); pts.push(d); }
  pts.forEach((p, k) => {
    const id = movers[k];
    if (!id) { p.remove(); return; }
    const lv = LIVE.pv[id] || {};
    const pan = lv.p ?? lookOf(id).pan ?? 0.5, tilt = lv.t ?? lookOf(id).tilt ?? 0.5;
    p.style.left = pan * 100 + '%'; p.style.top = (1 - tilt) * 100 + '%';
  });
}

/* ------------------------------------------------------------ efectos */
const FX_SIZE_LABEL = { pulso: 'Ancho', onda: 'Profundidad', azar: 'Cantidad', circulo: 'Tamaño', ocho: 'Tamaño', paneo: 'Tamaño', tilt: 'Tamaño' };
const isMove = (f) => INIT.fx_types[f.type]?.family === 'pos';
const signed = (v) => (v > 0.005 ? '+' : '') + Math.round(v * 100) + '%';
function fxSlider(f, k, label, min, max, fmt = 'pct') {
  const v = +f[k] || 0;
  return `<div class="slider"><label>${label}</label><input type="range" min="${min}" max="${max}" step="0.01" value="${v}" data-fx="${f.id}" data-k="${k}" data-fmt="${fmt}"><output>${fmt === 'signed' ? signed(v) : pct(v)}</output></div>`;
}
function fxCard(f) {
  const names = f.ids.map((i) => fx(i)?.name).filter(Boolean);
  const typeName = f.name || INIT.fx_types[f.type]?.name || f.type;
  const front = f.type.startsWith('f_');
  const speed = f.sync
    ? `<div class="slider"><label>Una vuelta cada</label><select data-fx="${f.id}" data-k="beats">${[1, 2, 4, 8, 16, 32].map((b) => `<option value="${b}" ${+f.beats === b ? 'selected' : ''}>${b} tiempo${b > 1 ? 's' : ''}</option>`).join('')}</select><output></output></div>`
    : `<div class="slider"><label>Velocidad</label><input type="range" min="0.02" max="4" step="0.01" value="${f.hz}" data-fx="${f.id}" data-k="hz"><output>${(+f.hz).toFixed(2)}/s</output></div>`;
  const sizeLabel = (INIT.size_labels || {})[f.type] || FX_SIZE_LABEL[f.type];
  const size = front ? fxSlider(f, 'size', 'Tamaño', 0, 1) : sizeLabel ? fxSlider(f, 'size', sizeLabel, 0, 1) : '';
  const frontExtra = front ? fxSlider(f, 'altura', 'Altura', -1, 1, 'signed')
    + fxSlider(f, 'apertura', 'Apertura', -1, 1, 'signed') + fxSlider(f, 'escalon', 'Escalón', -1, 1, 'signed') : '';
  const many = f.type === 'colores';
  const colors = ['colores', 'alternar', 'mitades'].includes(f.type) ? `<div class="row" style="margin:6px 0">
      ${(many ? f.colors : f.colors.slice(0, 2)).map((c, i) => `<input type="color" value="${esc(c)}" data-fxc="${f.id}" data-i="${i}">`).join('')}
      ${many ? `<button class="ghost small" data-fxcadd="${f.id}" ${f.colors.length >= 6 ? 'disabled' : ''}>+ color</button>
      <button class="ghost small" data-fxcdel="${f.id}" ${f.colors.length <= 2 ? 'disabled' : ''}>− color</button>` : ''}</div>` : '';
  return `<div class="fxcard">
    <div class="row"><strong>${esc(typeName)}</strong><span class="hint grow">${esc(names.length > 3 ? names.length + ' equipos' : names.join(', '))}</span>
      <button class="ghost small" data-fxdel="${f.id}">Quitar</button></div>
    <label class="hint row" style="gap:6px;margin:6px 0"><input type="checkbox" data-fx="${f.id}" data-k="sync" ${f.sync ? 'checked' : ''}> Al tempo (${Math.round(S.bpm)} BPM)</label>
    ${speed}${size}${frontExtra}
    ${fxSlider(f, 'spread', 'Desfase', 0, 1)}
    ${colors}
    <div class="row">${front ? `<button class="small ${f.mirror ? 'on' : 'ghost'}" data-fx="${f.id}" data-k="mirror" title="Los de la izquierda se mueven al revés que los de la derecha">Espejo</button>` : ''}
      <button class="small ${f.reverse ? 'on' : 'ghost'}" data-fx="${f.id}" data-k="reverse">Invertir dirección</button></div>
  </div>`;
}
function renderFxList() {
  if (!changed('fx', S.fx)) return;
  if (dragging && dragging.closest('#fxList, #movList')) { sigs.fx = null; return; }
  const other = S.fx.filter((f) => !isMove(f)), moves = S.fx.filter(isMove);
  $('#fxList').innerHTML = other.length ? other.map(fxCard).join('')
    : '<p class="hint">No hay efectos corriendo. Elegí equipos y tocá un efecto de arriba.</p>';
  $('#movList').innerHTML = moves.length ? `<h3>${moves.length > 1 ? moves.length + ' movimientos sumados' : 'Movimiento en marcha'}</h3>` + moves.map(fxCard).join('') : '';
}

/* ------------------------------------------------------------ movimientos frontales */
const HEAD_COLORS = ['#ff5aa0', '#ffc24a', '#4fd18b', '#33c8ff', '#b48cff', '#ff8a3d'];
const sx = (x) => (50 + Math.max(-1.35, Math.min(1.35, x)) / 1.35 * 46).toFixed(2);
const sy = (y) => (50 - Math.max(-1.35, Math.min(1.35, y)) / 1.35 * 42).toFixed(2);
function moveTargets() {
  const m = selWith('mover');
  return m.length ? m : (S ? S.movers : []);
}
function buildMovStatic() {
  const cat = INIT.frontal;
  const svgPaths = (paths) => {
    const all = paths.flat();
    const xs = all.map((q) => q[0]), ys = all.map((q) => q[1]);
    const w = Math.max(...xs) - Math.min(...xs), h = Math.max(...ys) - Math.min(...ys);
    const k = 80 / Math.max(w, h * 1.4, 0.4);
    const cx = (Math.max(...xs) + Math.min(...xs)) / 2, cy = (Math.max(...ys) + Math.min(...ys)) / 2;
    const P = ([x, y]) => [(50 + (x - cx) * k).toFixed(1), (50 - (y - cy) * k).toFixed(1)];
    const snap = Math.round(paths[0].length * 0.18);
    return `<svg viewBox="0 0 100 100" aria-hidden="true">
      ${paths.map((pts, i) => `<polyline points="${pts.map((q) => P(q).join(',')).join(' ')}" stroke="${HEAD_COLORS[i % HEAD_COLORS.length]}"/>`).join('')}
      ${paths.map((pts, i) => { const [x, y] = P(pts[snap]); return `<circle cx="${x}" cy="${y}" r="5" fill="${HEAD_COLORS[i % HEAD_COLORS.length]}"/>`; }).join('')}</svg>`;
  };
  $('#movPresets').innerHTML = cat.presets.map((p, i) => `<button data-mpreset="${i}">${svgPaths(p.paths)}<span>${esc(p.name)}</span></button>`).join('');
  $('#layouts').innerHTML = cat.layouts.map((l) => `<button data-layout="${l.id}"><svg viewBox="0 0 100 60" aria-hidden="true"><line x1="4" y1="30" x2="96" y2="30" class="hz"/>
    ${l.points.map(([x, y], k) => `<line x1="${20 + k * 20}" y1="58" x2="${sx(x)}" y2="${(30 - Math.max(-1.35, Math.min(1.35, y)) / 1.35 * 26).toFixed(1)}" stroke="${HEAD_COLORS[k]}" class="ray"/>`).join('')}
    </svg><span>${esc(l.name)}</span></button>`).join('');
}
function renderMov() {
  const r = S.rig || {};
  const movers = S.movers || [];
  $('#frontWarn').style.display = r.calibrated || !movers.length ? 'none' : '';
  const t = moveTargets();
  $('#movTarget').textContent = !movers.length ? 'No hay cabezales en el show'
    : selWith('mover').length ? `Se aplica a los ${t.length} elegidos` : `Se aplica a los ${t.length} cabezales`;
  setVal($('#flipX'), r.flip_x); setVal($('#flipY'), r.flip_y); setVal($('#revOrder'), r.reverse_order);
  setVal($('#spanX'), r.span_x); setVal($('#spanY'), r.span_y);
  $('#spanXVal').textContent = Math.round(r.span_x) + '°';
  $('#spanYVal').textContent = Math.round(r.span_y) + '°';
  const done = movers.filter((i) => r.front && r.front[i]).length;
  $('#frontSummary').textContent = movers.length ? `${done} de ${movers.length} listos` : '';
  if (changed('frontStatus', [movers, r.front, movers.map((i) => fx(i)?.name)])) {
    $('#frontStatus').innerHTML = movers.map((i, k) => `<span class="fchip ${r.front && r.front[i] ? 'ok' : ''}">${k + 1}. ${esc(fx(i)?.name || '')}${r.front && r.front[i] ? ' ✓' : ''}</span>`).join('');
    if (!r.calibrated && !$('#frontBox').dataset.touched) $('#frontBox').open = true;
  }
  if (changed('audDots', movers)) {
    $$('#audView .adot').forEach((d) => d.remove());
    movers.forEach((id, k) => {
      const d = document.createElement('span'); d.className = 'adot'; d.dataset.id = id; d.textContent = k + 1;
      $('#audView').appendChild(d);
    });
  }
  drawAudience();
}
function drawAudience() {
  if (!S) return;
  for (const d of $$('#audView .adot')) {
    const p = LIVE.pv[d.dataset.id];
    if (!p || p.x == null) continue;
    d.style.left = sx(p.x) + '%'; d.style.top = sy(p.y) + '%';
    d.style.setProperty('--c', p.c); d.style.setProperty('--d', p.d);
  }
}

/* ------------------------------------------------------------ escenas */
function renderScenes() {
  if (!changed('scenes', [S.scenes, editScenes, lastScene])) return;
  $('#scenesEmpty').style.display = S.scenes.length ? 'none' : '';
  $('#btnEditScenes').classList.toggle('on', editScenes);
  $('#btnEditScenes').textContent = editScenes ? 'Listo' : 'Editar';
  $('#scenes').innerHTML = S.scenes.map((s, i) => `
    <div class="scene ${s.id === lastScene ? 'last' : ''}" style="--sc:${esc(s.color)}" ${editScenes ? '' : `role="button" tabindex="0" data-scene="${s.id}"`}>
      ${i < 9 ? `<span class="k">${i + 1}</span>` : ''}${esc(s.name)}
      ${editScenes ? `<div class="tools">
        <button data-sre="${s.id}" title="Reemplaza la escena por lo que está en escena ahora">Regrabar</button>
        <button data-sren="${s.id}">Renombrar</button>
        <input type="color" value="${esc(s.color)}" data-scol="${s.id}" title="Color del botón" style="width:30px;height:24px;border:0;padding:0;background:none">
        <button data-smv="${s.id}" data-d="-1" title="Mover antes">◀</button><button data-smv="${s.id}" data-d="1" title="Mover después">▶</button>
        <button data-sdel="${s.id}" class="danger">Borrar</button></div>` : ''}
    </div>`).join('');
  $('#cueScene').innerHTML = S.scenes.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
  $('#btnAddCue').disabled = !S.scenes.length;
}
document.addEventListener('click', (e) => {
  const sc = e.target.closest('[data-scene]');
  if (sc && sc.closest('.scene')) recall(sc.dataset.scene);
});
function recall(id) { lastScene = id; sigs.scenes = null; api('recall_scene', { id }); }

/* ------------------------------------------------------------ secuencia */
function renderCues() {
  setVal($('#cueLoop'), S.settings.cue_loop);
  if (!changed('cues', [S.cues, S.cue_index, S.settings.cue_loop, S.scenes.map((s) => [s.id, s.name])])) return;
  const opts = (cur) => S.scenes.map((s) => `<option value="${s.id}" ${s.id === cur ? 'selected' : ''}>${esc(s.name)}</option>`).join('');
  $('#cues').innerHTML = S.cues.length ? S.cues.map((c, i) => `
    <li class="cue ${i === S.cue_index ? 'cur' : ''}">
      <button class="n ghost small" data-cuego="${i}" title="Ir a este paso">${i + 1}</button>
      <div><select data-cue="${c.id}" data-k="scene">${opts(c.scene)}</select>
        <div class="meta" style="margin-top:6px">
          <label>Fundido <input type="number" step="0.1" min="0" value="${c.fade}" data-cue="${c.id}" data-k="fade"> s</label>
          <label>Espera <input type="number" step="0.5" min="0" value="${c.wait ?? ''}" placeholder="GO" data-cue="${c.id}" data-k="wait"> s</label>
        </div></div>
      <div class="row" style="flex-direction:column;gap:4px">
        <button class="ghost small" data-cuemv="${c.id}" data-d="-1" title="Subir">▲</button>
        <button class="ghost small" data-cuemv="${c.id}" data-d="1" title="Bajar">▼</button>
        <button class="ghost small danger" data-cuedel="${c.id}" title="Quitar paso">✕</button>
      </div></li>`).join('') : '<p class="hint">La secuencia está vacía. Agregá pasos con escenas ya guardadas.</p>';
  $('#go').textContent = S.cue_index >= 0 && S.cues.length ? `GO  ${Math.min(S.cue_index + 2, S.cues.length)}/${S.cues.length}` : 'GO';
  const nextIdx = S.cue_index + 1 < S.cues.length ? S.cue_index + 1 : (S.settings.cue_loop && S.cues.length ? 0 : -1);
  const nextCue = S.cues[nextIdx];
  const nextName = nextCue ? (S.scenes.find((x) => x.id === nextCue.scene)?.name || 'Escena') : '';
  $('#standby').classList.toggle('armed', !!nextCue);
  $('#nextCue').innerHTML = nextCue ? `Standby: <b>${nextIdx + 1}. ${esc(nextName)}</b>`
    : (S.cues.length ? 'Fin de la secuencia' : 'Sin pasos en la secuencia');
}

/* ------------------------------------------------------------ posiciones */
function renderPositions() {
  if (!changed('pos', S.positions)) return;
  $('#positions').innerHTML = S.positions.length ? S.positions.map((p) => `
     <span class="row" style="gap:2px"><button data-pos="${p.id}">${esc(p.name)}</button><button class="ghost small" data-posdel="${p.id}" title="Borrar posición">✕</button></span>`).join('')
    : '<span class="hint">Todavía no guardaste posiciones. Apuntá los cabezales y guardala con un nombre (ej. “Pista”, “Novios”).</span>';
}

/* ------------------------------------------------------------ patch */
function renderPatch() {
  if (changed('patchProfiles', Object.keys(PROF))) {
    const groups = {};
    for (const p of Object.values(PROF)) (groups[p.tipo || 'otro'] ||= []).push(p);
    $('#addProfile').innerHTML = Object.entries(groups).map(([t, ps]) => `<optgroup label="${esc(TYPE_LABEL[t] || t)}">
      ${ps.map((p) => `<option value="${p.id}">${esc(p.nombre)}${p.origen === 'usuario' ? ' (propio)' : ''}</option>`).join('')}</optgroup>`).join('');
    updateAddNote();
  }
  if (!changed('patch', [S.fixtures, S.conflicts, Object.keys(PROF)])) return;
  const conf = S.conflicts.map((g) => g.map((i) => fx(i)?.name).join(' y '));
  $('#conflicts').innerHTML = conf.length ? `<div class="box errbox">Hay equipos que se pisan: ${esc(conf.join('; '))}. Cambiá una de las direcciones.</div>` : '';
  $('#patchRows').innerHTML = fixtures().map((f) => {
    const p = PROF[f.profile]; const n = p ? p.canales.length : 1; const mover = capsOf(f.id).has('mover');
    return `<tr>
      <td><div class="row" style="gap:2px;flex-wrap:nowrap"><button class="ghost small" data-fmv="${f.id}" data-d="-1" title="Subir">▲</button><button class="ghost small" data-fmv="${f.id}" data-d="1" title="Bajar">▼</button></div></td>
      <td><input type="text" value="${esc(f.name)}" data-fix="${f.id}" data-k="name"></td>
      <td>${esc(p ? p.nombre : 'Perfil faltante: ' + f.profile)}${p && !p.verificado ? ' <span style="color:var(--warn)">(a verificar)</span>' : ''}</td>
      <td><input type="number" min="1" max="512" value="${f.address}" data-fix="${f.id}" data-k="address"></td>
      <td class="addr">${f.address}–${f.address + n - 1}</td>
      <td>${mover ? `<label class="hint"><input type="checkbox" data-fix="${f.id}" data-k="invert_pan" ${f.invert_pan ? 'checked' : ''}> pan</label>
                     <label class="hint"><input type="checkbox" data-fix="${f.id}" data-k="invert_tilt" ${f.invert_tilt ? 'checked' : ''}> tilt</label>` : ''}</td>
      <td><button class="ghost small danger" data-fdel="${f.id}">Quitar</button></td></tr>`;
  }).join('') || '<tr><td colspan="7" class="hint">No hay equipos en este show.</td></tr>';
  const use = new Array(513).fill(0);
  for (const f of fixtures()) { const n = PROF[f.profile]?.canales.length || 1; for (let a = f.address; a < f.address + n && a <= 512; a++) use[a]++; }
  $('#dmxbar').innerHTML = use.slice(1).map((u) => `<i class="${u > 1 ? 'x' : u ? 'u' : ''}"></i>`).join('');
  updateAddNote();
}
function updateAddNote() {
  const p = PROF[$('#addProfile').value];
  if (!p || !S) return;
  const n = p.canales.length;
  const used = new Set();
  for (const f of fixtures()) { const m = PROF[f.profile]?.canales.length || 1; for (let a = f.address; a < f.address + m; a++) used.add(a); }
  let free = null; for (let a = 1; a + n - 1 <= 512; a++) { let ok = true; for (let k = 0; k < n; k++) if (used.has(a + k)) { ok = false; break; } if (ok) { free = a; break; } }
  $('#addNote').textContent = `Ocupa ${n} canal${n > 1 ? 'es' : ''}. ${free ? 'Próxima dirección libre: ' + free + '.' : 'No queda lugar en el universo.'} ${p.nota || ''}`;
}

/* ------------------------------------------------------------ probar canales */
let draft = null;      // copia editable del perfil
let draftFor = null;
function renderProbar() {
  if (changed('testFixList', fixtures().map((f) => [f.id, f.name]))) {
    const cur = $('#testFix').value;
    $('#testFix').innerHTML = fixtures().map((f) => `<option value="${f.id}">${esc(f.name)} — dirección ${f.address} (${esc(PROF[f.profile]?.nombre || f.profile)})</option>`).join('');
    if (cur && fx(cur)) $('#testFix').value = cur;
  }
  const id = $('#testFix').value;
  const f = fx(id);
  const key = f ? [f.id, f.profile, f.address, PROF[f.profile]] : null;
  if (changed('probar', key)) {
    draftFor = f ? f.id : null;
    draft = f && PROF[f.profile] ? JSON.parse(JSON.stringify(PROF[f.profile])) : null;
    buildProbar();
  }
  // valores en vivo de prueba
  for (const r of $$('.chrow')) {
    const a = r.dataset.addr; const v = S.test[a];
    r.classList.toggle('live', v != null);
    const sl = $('input[type=range]', r);
    if (v != null) { setVal(sl, v); $('.v', r).textContent = v; }
  }
}
function buildProbar() {
  const f = fx(draftFor);
  if (!f || !draft) { $('#chRows').innerHTML = '<p class="hint">Elegí un equipo.</p>'; $('#profNote').innerHTML = ''; $('#wheelEditors').innerHTML = ''; $('#strobeEdit').style.display = 'none'; return; }
  $('#profNote').className = 'box' + (draft.verificado ? '' : ' warnbox');
  $('#profNote').innerHTML = `<strong>${esc(draft.nombre)}</strong>${draft.origen === 'usuario' ? ' (perfil propio)' : ''}<br><span>${esc(draft.nota || '')}</span>`;
  const opts = (cur) => Object.entries(INIT.channel_attrs).map(([k, l]) => `<option value="${k}" ${k === cur ? 'selected' : ''}>${esc(l)}</option>`).join('');
  $('#chRows').innerHTML = `<div class="chrow hint"><span>Canal</span><span>Dir.</span><span class="fn">Función</span><span>Probar</span><span></span></div>` +
    draft.canales.map((c, i) => {
      const addr = f.address + i;
      return `<div class="chrow" data-addr="${addr}">
        <span class="addr">${i + 1}</span><span class="hint">${addr}</span>
        <span class="fn row" style="gap:6px"><select data-ch="${i}">${opts(c.attr)}</select>
          ${c.attr === 'raw' ? `<input type="number" min="0" max="255" value="${c.default || 0}" data-chdef="${i}" title="Valor fijo cuando no lo estás probando">` : ''}</span>
        <input type="range" min="0" max="255" value="${S.test[addr] ?? 0}" data-test="${addr}">
        <span class="v">${S.test[addr] ?? '—'}</span></div>`;
    }).join('');
  const attrs = new Set(draft.canales.map((c) => c.attr));
  const chAddr = (attr) => { const i = draft.canales.findIndex((c) => c.attr === attr); return i < 0 ? null : f.address + i; };
  const wheel = (key, title, withHex) => {
    if (!attrs.has(key)) return '';
    const addr = chAddr(key);
    const v = S.test[addr] ?? (draft[key]?.[0]?.dmx || 0);
    const names = key === 'color_wheel'
      ? WHEEL_COLORS.map(([n, h]) => `<button class="small ghost" data-wname="${esc(n)}" data-whex="${h}"><span class="chip" style="background:${h}"></span>${esc(n)}</button>`).join('')
      : `<button class="small ghost" data-wname="Abierto">Abierto (sin ${key === 'gobo' ? 'gobo' : 'prisma'})</button><button class="small" data-wname="*">Agregar ${key === 'gobo' ? 'gobo' : 'prisma'} en este valor</button>`;
    return `<div class="box wcal" data-wcal="${key}" data-addr="${addr}">
      <h2>${title}: encontrar cada posición</h2>
      <ol class="steps">
        <li><button class="small" data-wlight>Prender el equipo para ver</button></li>
        <li>Mové la rueda hasta que ${key === 'color_wheel' ? 'el color se vea entero, sin partirse' : key === 'gobo' ? 'el gobo quede quieto y centrado (si tiembla, estás en la zona de "gobo que se sacude": probá un valor más bajo)' : 'la posición quede centrada'}.</li>
        <li>Tocá ${key === 'color_wheel' ? 'el nombre del color que ves' : 'el botón para anotarla'}. Repetí con todas y al final tocá <b>Guardar perfil</b>.</li>
      </ol>
      <div class="row wdial">
        <button class="small ghost" data-wstep="-5">−5</button><button class="small ghost" data-wstep="-1">−1</button>
        <input type="range" min="0" max="255" value="${v}" data-wval class="grow">
        <button class="small ghost" data-wstep="1">+1</button><button class="small ghost" data-wstep="5">+5</button>
        <output class="addr" data-wout>${v}</output>
      </div>
      <div class="row wnames">${names}</div>
      <h3>Anotadas</h3>
      <div class="row wlist" data-wlist></div>
      <div class="row" style="margin-top:8px"><button class="small ghost danger" data-wclear>Empezar de cero</button></div>
      <details class="wtext"><summary class="hint">Editar como texto</summary>
        <p class="hint">Una posición por línea: ${withHex ? '<em>Nombre = valor DMX = #color</em>' : '<em>Nombre = valor DMX</em>'}.</p>
        <textarea data-wheel="${key}"></textarea></details>
    </div>`;
  };
  $('#wheelEditors').innerHTML = wheel('color_wheel', 'Rueda de color', true) + wheel('gobo', 'Gobos', false) + wheel('prism', 'Prisma', false);
  for (const k of ['color_wheel', 'gobo', 'prism']) syncWheel(k);
  const st = draft.strobe || { off: 0, min: 10, max: 255 };
  $('#strobeEdit').style.display = attrs.has('strobe') ? '' : 'none';
  $('#strobeEdit').innerHTML = `<h2>Canal de strobo</h2><div class="row" style="margin-top:8px">
     <label class="hint">Sin strobo <input type="number" min="0" max="255" value="${st.off}" data-st="off"></label>
     <label class="hint">Más lento <input type="number" min="0" max="255" value="${st.min}" data-st="min"></label>
     <label class="hint">Más rápido <input type="number" min="0" max="255" value="${st.max}" data-st="max"></label></div>`;
  const pr = draft.prism_rot;
  $('#prismEdit').style.display = attrs.has('prism') ? '' : 'none';
  $('#prismEdit').innerHTML = `<h2>Rotación del prisma</h2>
     <label class="row" style="margin-top:8px"><input type="checkbox" data-pr="on" ${pr ? 'checked' : ''}> La rotación está en el mismo canal del prisma</label>
     <div class="row" style="margin-top:8px">
       <label class="hint">Desde (lento) <input type="number" min="0" max="255" value="${pr ? pr.min : 145}" data-pr="min"></label>
       <label class="hint">Hasta (rápido) <input type="number" min="0" max="255" value="${pr ? pr.max : 255}" data-pr="max"></label></div>
     <p class="hint">Con la barra de Rotación en cero el prisma queda fijo; al subirla usa estos valores del canal del prisma.</p>`;
}
const WHEEL_COLORS = [
  ['Blanco', '#ffffff'], ['Rojo', '#ff2020'], ['Naranja', '#ff8a1a'], ['Ámbar', '#ffb030'], ['Amarillo', '#ffe21a'],
  ['Verde', '#24e04a'], ['Verde claro', '#9dff6a'], ['Cian', '#22e6ee'], ['Celeste', '#3fd7ff'], ['Azul', '#2a4dff'],
  ['Violeta', '#8a3dff'], ['Lavanda', '#b9a2ff'], ['Magenta', '#ff2ae6'], ['Rosa', '#ff5fc8'], ['Cálido', '#ffd29a'],
];
function wheelText(key) {
  return (draft[key] || []).map((s) => key === 'color_wheel' ? `${s.nombre} = ${s.dmx} = ${s.hex || '#ffffff'}` : `${s.nombre} = ${s.dmx}`).join('\n');
}
function syncWheel(key) {
  const box = $(`[data-wcal="${key}"]`); if (!box) return;
  const list = (draft[key] || []).slice().sort((a, b) => a.dmx - b.dmx);
  draft[key] = list;
  $('[data-wlist]', box).innerHTML = list.length ? list.map((s, i) => `<span class="wchip" data-wjump="${s.dmx}">
      ${s.hex ? `<span class="chip" style="background:${esc(s.hex)}"></span>` : ''}${esc(s.nombre)} <b>${s.dmx}</b>
      <button class="small ghost" data-wdel="${i}" title="Quitar">✕</button></span>`).join('')
    : '<span class="hint">Todavía ninguna.</span>';
  $('[data-wheel]', box).value = wheelText(key);
}
function parseWheel(text, withHex) {
  return text.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => {
    const parts = l.split('=').map((x) => x.trim());
    const o = { nombre: parts[0] || 'Posición', dmx: Math.max(0, Math.min(255, parseInt(parts[1], 10) || 0)) };
    if (withHex) o.hex = /^#[0-9a-f]{6}$/i.test(parts[2] || '') ? parts[2] : '#ffffff';
    return o;
  });
}
function collectDraft() {
  for (const t of $$('[data-wheel]')) draft[t.dataset.wheel] = parseWheel(t.value, t.dataset.wheel === 'color_wheel');
  for (const i of $$('[data-st]')) { draft.strobe = draft.strobe || {}; draft.strobe[i.dataset.st] = Math.max(0, Math.min(255, +i.value || 0)); }
  const prOn = $('[data-pr=on]');
  if (prOn && $('#prismEdit').style.display !== 'none') {
    if (prOn.checked) draft.prism_rot = { min: Math.max(0, Math.min(255, +$('[data-pr=min]').value || 0)), max: Math.max(0, Math.min(255, +$('[data-pr=max]').value || 255)) };
    else delete draft.prism_rot;
  }
  const clean = JSON.parse(JSON.stringify(draft)); delete clean.caps; delete clean.id; delete clean.origen;
  return clean;
}

/* ------------------------------------------------------------ show */
function renderShow() {
  setVal($('#showName'), S.show_name);
  $('#dataDir').textContent = INIT.data_dir;
  if (S.app_settings) {
    setVal($('#outKind'), S.app_settings.salida || 'auto');
    setVal($('#outRate'), S.app_settings.dmx_ritmo || 'normal');
    setVal($('#remote'), S.app_settings.control_remoto);
    $('#remoteHint').textContent = S.app_settings.control_remoto
      ? `Activado. Si recién lo prendiste, cerrá y volvé a abrir el programa. Después, en el celular (misma Wi-Fi) abrí ${INIT.lan}`
      : 'Desactivado: solo se puede controlar desde esta computadora.';
  }
  if (S.shows && changed('shows', [S.shows.map((s) => s.name), S.show_name])) {
    $('#showRows').innerHTML = S.shows.map((s) => `<tr><td>${esc(s.name)}${s.name === S.show_name ? ' <span class="hint">(abierto)</span>' : ''}</td>
      <td class="hint">${new Date(s.mtime * 1000).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' })}</td>
      <td style="text-align:right">${s.name === S.show_name ? '' : `<button class="ghost small" data-showopen="${esc(s.name)}">Abrir</button>
        <button class="ghost small danger" data-showdel="${esc(s.name)}">Borrar</button>`}</td></tr>`).join('');
  }
}

/* ------------------------------------------------------------ armado estático y eventos */
function buildStatic() {
  $('#appVersion').textContent = `Versión ${INIT.app.version} (compilación ${INIT.app.build || 'dev'})`;
  $('#brand').title = $('#appVersion').textContent;
  $('#palette').innerHTML = INIT.palette.map((c, i) => `<button class="swatch" style="--sw:${c.hex}" data-pal="${i}"><span>${esc(c.nombre)}</span></button>`).join('');

  // pestañas
  for (const b of $$('#tabs button')) b.onclick = () => {
    $$('#tabs button').forEach((x) => x.classList.toggle('on', x === b));
    $$('.view').forEach((v) => v.classList.toggle('on', v.id === b.dataset.view));
    if (b.dataset.view !== 'probar' && S && Object.keys(S.test).length) api('test_clear');
  };
  for (const b of $$('#progTabs button')) b.onclick = () => {
    $$('#progTabs button').forEach((x) => x.classList.toggle('on', x === b));
    $$('.ppanel').forEach((p) => p.classList.toggle('on', p.dataset.p === b.dataset.p));
    drawXYPoints();
  };
  $('#out').onclick = () => $('#tabs [data-view=show]').click();

  // barra superior
  $('#btnTap').onclick = () => api('tap');
  $('#btnSync').onclick = async () => {
    const on = !S.sync_ext;
    if (await api('sync_set', { on })) toast(on ? 'El tempo sigue a VirtualDJ' : 'Tempo manual: usá Tap');
  };
  renderSync(INIT.sync);
  $('#fade').oninput = (e) => { $('#fadeVal').textContent = (+e.target.value).toFixed(1) + ' s'; sendLatest('fade', 'show_settings', { fade: +e.target.value }); };
  $('#master').oninput = (e) => { $('#masterVal').textContent = pct(+e.target.value); sendLatest('master', 'master', { value: +e.target.value }); };
  $('#btnBlackout').onclick = () => api('blackout', { on: !S.blackout });
  const s2pop = $('#s2Pop');
  $('#btnS2Cfg').onclick = (e) => { e.stopPropagation(); s2pop.hidden = !s2pop.hidden; $('#btnS2Cfg').setAttribute('aria-expanded', !s2pop.hidden); };
  document.addEventListener('click', (e) => { if (!s2pop.hidden && !e.target.closest('.s2wrap')) { s2pop.hidden = true; $('#btnS2Cfg').setAttribute('aria-expanded', false); } });
  for (const r of $$('input[name=s2mode]')) r.onchange = () => api('strobe2_set', { sync: r.value === 'sync' });
  s2pop.addEventListener('click', (e) => { const b = e.target.closest('[data-s2div]'); if (b) api('strobe2_set', { sync: true, div: +b.dataset.s2div }); });
  $('#s2hz').oninput = (e) => { $('#s2hzVal').textContent = (+e.target.value).toFixed(1) + '/s'; sendLatest('s2hz', 'strobe2_set', { sync: false, hz: +e.target.value }); };
  $('#s2white').onchange = (e) => api('strobe2_set', { white: e.target.checked });
  $('#btnClear').onclick = async () => {
    if (!(await api('clear_all'))) return;
    sel.clear(); lastScene = null; sigs.scenes = null; selectionChanged(); renderScenes();
    toast('Todo a cero', false, { label: 'Deshacer', fn: () => api('undo_clear').then((ok) => ok && toast('Listo, volvió como estaba')) });
  };
  for (const [k, b] of [['flash', '#btnFlash'], ['strobe', '#btnStrobe'], ['strobe2', '#btnStrobe2']]) {
    const el = $(b);
    const on = (e) => { e.preventDefault(); el.setPointerCapture?.(e.pointerId); el.classList.add('held'); api('hold', { kind: k, on: true }); };
    const off = () => { if (!el.classList.contains('held')) return; el.classList.remove('held'); api('hold', { kind: k, on: false }); };
    el.addEventListener('pointerdown', on);
    el.addEventListener('pointerup', off); el.addEventListener('pointercancel', off); el.addEventListener('lostpointercapture', off);
  }

  // equipos
  $('#tileGroups').addEventListener('click', (e) => {
    const t = e.target.closest('.tile'); if (!t) return;
    sel.has(t.dataset.id) ? sel.delete(t.dataset.id) : sel.add(t.dataset.id);
    selectionChanged();
  });
  $('#groupChips').addEventListener('click', (e) => { const b = e.target.closest('[data-g]'); if (b) applyGroup(b.dataset.g); });

  // color e intensidad
  const needSel = () => { if (!sel.size) { toast('Primero elegí equipos'); return false; } return true; };
  $('#dim').oninput = (e) => { if (!needSel()) return; $('#dimVal').textContent = pct(+e.target.value); sendLatest('dim', 'set_attrs', { ids: selIds(), attrs: { dim: +e.target.value } }); };
  for (const b of $$('[data-dim]')) b.onclick = () => needSel() && api('set_attrs', { ids: selIds(), attrs: { dim: +b.dataset.dim } });
  $('#palette').addEventListener('click', (e) => { const b = e.target.closest('[data-pal]'); if (b && needSel()) api('set_color', { ids: selIds(), rgbw: INIT.palette[+b.dataset.pal].rgbw }); });
  $('#customColor').oninput = (e) => { if (needSel()) sendLatest('color', 'set_color', { ids: selIds(), rgbw: [...hexToRgb(e.target.value), 0] }); };
  $('#btnLocate').onclick = () => needSel() && api('locate', { ids: selIds() });
  $('#btnOff').onclick = () => needSel() && api('clear', { ids: selIds() });

  // posición
  const pad = $('#xy');
  pad.addEventListener('pointerdown', (e) => {
    const movers = selWith('mover');
    if (!movers.length) { toast('Elegí cabezales para moverlos'); return; }
    pad.setPointerCapture(e.pointerId);
    const start = Object.fromEntries(movers.map((i) => [i, [lookOf(i).pan ?? 0.5, lookOf(i).tilt ?? 0.5]]));
    const cx = movers.reduce((a, i) => a + start[i][0], 0) / movers.length;
    const cy = movers.reduce((a, i) => a + start[i][1], 0) / movers.length;
    xyDrag = { movers, start, cx, cy };
    xyMove(e);
  });
  pad.addEventListener('pointermove', (e) => xyDrag && xyMove(e));
  const end = () => { xyDrag = null; };
  pad.addEventListener('pointerup', end); pad.addEventListener('pointercancel', end);
  $('#fan').oninput = (e) => { $('#fanVal').textContent = (+e.target.value).toFixed(2); const m = selWith('mover'); if (m.length > 1) sendLatest('fan', 'fan', { ids: m, amount: +e.target.value }); else toast('El abanico necesita dos o más cabezales'); };
  $('#pts').oninput = (e) => { const m = selWith('pts'); if (m.length) sendLatest('pts', 'set_attrs', { ids: m, attrs: { pts: +e.target.value } }); };
  $('#btnCenter').onclick = () => { const m = selWith('mover'); if (m.length) api('set_position', { ids: m, pan: 0.5, tilt: 0.5 }); };
  $('#btnSavePos').onclick = async () => {
    const m = selWith('mover'); if (!m.length) { toast('Elegí los cabezales cuya posición querés guardar'); return; }
    const name = prompt('Nombre de la posición', 'Posición ' + (S.positions.length + 1)); if (name === null) return;
    if (await api('save_position', { ids: m, name })) toast('Posición guardada');
  };
  $('#positions').addEventListener('click', (e) => {
    const p = e.target.closest('[data-pos]'); if (p) api('recall_position', { id: p.dataset.pos, ids: selWith('mover') });
    const d = e.target.closest('[data-posdel]'); if (d && confirm('¿Borrar esta posición?')) api('delete_position', { id: d.dataset.posdel });
  });

  // haz
  $('.ppanel[data-p=haz]').addEventListener('click', (e) => {
    const b = e.target.closest('[data-slot]'); if (!b) return;
    const cap = b.dataset.slot; api('set_wheel', { ids: selWith(cap), key: cap, index: +b.dataset.i });
  });
  for (const k of ['prot', 'focus', 'strobe']) $('#' + k).oninput = (e) => {
    const ids = selWith(k); if (!ids.length) return;
    $('#' + k + 'Val').textContent = k === 'strobe' && +e.target.value < 0.005 ? 'no' : k === 'prot' && +e.target.value < 0.005 ? 'quieto' : pct(+e.target.value);
    sendLatest(k, 'set_attrs', { ids, attrs: { [k]: +e.target.value } });
  };

  // efectos
  $('.ppanel[data-p=fx]').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-fxpreset]');
    if (b) {
      if (!needSel()) return;
      const p = INIT.efectos.find((x) => x.id === b.dataset.fxpreset);
      if (await api('add_fx', { ids: selIds(), type: p.type, params: { ...p.params } })) toast(p.name + ' en marcha');
    }
  });
  for (const list of [$('#fxList'), $('#movList')]) {
    list.addEventListener('input', (e) => {
      const t = e.target;
      if (t.dataset.fx && t.type === 'range') {
        const out = t.parentElement.querySelector('output');
        if (out) out.textContent = t.dataset.k === 'hz' ? (+t.value).toFixed(2) + '/s' : t.dataset.fmt === 'signed' ? signed(+t.value) : pct(+t.value);
        sendLatest('fx' + t.dataset.fx + t.dataset.k, 'update_fx', { id: t.dataset.fx, params: { [t.dataset.k]: +t.value } });
      }
      if (t.dataset.fxc) {
        const f = S.fx.find((x) => x.id === t.dataset.fxc); if (!f) return;
        const colors = [...f.colors]; colors[+t.dataset.i] = t.value;
        sendLatest('fxc' + f.id, 'update_fx', { id: f.id, params: { colors } });
      }
    });
    list.addEventListener('change', (e) => {
      const t = e.target;
      if (t.dataset.fx && t.type === 'checkbox') api('update_fx', { id: t.dataset.fx, params: { [t.dataset.k]: t.checked } });
      if (t.dataset.fx && t.tagName === 'SELECT') api('update_fx', { id: t.dataset.fx, params: { [t.dataset.k]: +t.value } });
    });
    list.addEventListener('click', (e) => {
      const t = e.target.closest('button'); if (!t) return;
      if (t.dataset.fxdel) api('remove_fx', { id: t.dataset.fxdel });
      if (t.dataset.k === 'reverse' || t.dataset.k === 'mirror') {
        const f = S.fx.find((x) => x.id === t.dataset.fx); api('update_fx', { id: t.dataset.fx, params: { [t.dataset.k]: !f[t.dataset.k] } });
      }
      const palette = ['#ff2020', '#2a46ff', '#22e04a', '#ffd60a', '#ff2ae6', '#22e6ee'];
      if (t.dataset.fxcadd) { const f = S.fx.find((x) => x.id === t.dataset.fxcadd); api('update_fx', { id: f.id, params: { colors: [...f.colors, palette[f.colors.length % palette.length]] } }); }
      if (t.dataset.fxcdel) { const f = S.fx.find((x) => x.id === t.dataset.fxcdel); api('update_fx', { id: f.id, params: { colors: f.colors.slice(0, -1) } }); }
    });
  }

  // movimientos frontales
  buildMovStatic();
  const needMovers = () => { const t = moveTargets(); if (!t.length) toast('No hay cabezales en el show'); return t; };
  let movStack = false;
  $('#btnMovStack').onclick = () => {
    movStack = !movStack;
    $('#btnMovStack').className = 'small ' + (movStack ? 'on' : 'ghost');
    $('#btnMovStack').setAttribute('aria-pressed', movStack);
    toast(movStack ? 'Los movimientos nuevos se suman a los que ya andan' : 'Cada movimiento nuevo reemplaza al anterior');
  };
  $('#movPresets').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-mpreset]'); if (!b) return;
    const t = needMovers(); if (!t.length) return;
    const p = INIT.frontal.presets[+b.dataset.mpreset];
    if (await api('add_fx', { ids: t, type: p.type, params: { ...p.params, name: p.name }, stack: movStack }))
      toast(p.name + (movStack ? ' sumado' : ' en marcha'));
  });
  $('#layouts').addEventListener('click', (e) => {
    const b = e.target.closest('[data-layout]'); if (!b) return;
    const t = needMovers(); if (t.length) api('front_layout', { ids: t, name: b.dataset.layout });
  });
  $('#btnMovStop').onclick = () => {
    const t = moveTargets(); const ids = S.fx.filter(isMove).flatMap((f) => f.ids.filter((i) => t.includes(i)));
    if (!ids.length) { toast('No hay movimiento andando'); return; }
    // quita solo los movimientos (deja colores e intensidad)
    for (const f of S.fx.filter(isMove)) if (f.ids.some((i) => t.includes(i))) api('remove_fx', { id: f.id });
    toast('Movimiento frenado: quedan en su posición');
  };
  $('#btnFrontSave').onclick = async () => {
    const m = selWith('mover');
    if (!m.length) { toast('Primero tocá el cabezal que ya apuntaste al frente'); return; }
    const n = await api('front_save', { ids: m });
    if (n) toast(n > 1 ? `Frente guardado para ${n} cabezales` : 'Frente guardado. Seguí con el próximo cabezal.');
  };
  $('#frontBox').addEventListener('toggle', () => { $('#frontBox').dataset.touched = '1'; });
  $('#frontBox').addEventListener('click', (e) => {
    const b = e.target.closest('[data-ftest]'); if (!b) return;
    const [x, y] = b.dataset.ftest.split(',').map(Number);
    const t = needMovers(); if (t.length) api('front_test', { ids: t, x, y });
  });
  $('#flipX').onchange = (e) => api('rig_set', { flip_x: e.target.checked });
  $('#flipY').onchange = (e) => api('rig_set', { flip_y: e.target.checked });
  $('#revOrder').onchange = (e) => api('rig_set', { reverse_order: e.target.checked });
  $('#spanX').oninput = (e) => { $('#spanXVal').textContent = e.target.value + '°'; sendLatest('spanX', 'rig_set', { span_x: +e.target.value }); };
  $('#spanY').oninput = (e) => { $('#spanYVal').textContent = e.target.value + '°'; sendLatest('spanY', 'rig_set', { span_y: +e.target.value }); };

  // ajuste fino (en grados)
  let nudgeStep = 1;
  for (const box of $$('[data-nudgebox]')) box.innerHTML = `
    <button class="ghost small" data-nudge="-1,0" title="Pan hacia un lado">Pan ◀</button>
    <button class="ghost small" data-nudge="1,0" title="Pan hacia el otro lado">Pan ▶</button>
    <button class="ghost small" data-nudge="0,1" title="Tilt hacia un lado">Tilt ▲</button>
    <button class="ghost small" data-nudge="0,-1" title="Tilt hacia el otro lado">Tilt ▼</button>
    <span class="steppick"><button class="small on" data-step="1">1°</button><button class="small ghost" data-step="5">5°</button></span>`;
  document.addEventListener('click', (e) => {
    const st = e.target.closest('[data-step]');
    if (st) { nudgeStep = +st.dataset.step; $$('[data-step]').forEach((b) => b.className = 'small ' + (+b.dataset.step === nudgeStep ? 'on' : 'ghost')); return; }
    const n = e.target.closest('[data-nudge]');
    if (n) {
      const m = selWith('mover'); if (!m.length) { toast('Elegí un cabezal'); return; }
      const [dp, dt] = n.dataset.nudge.split(',').map(Number);
      api('nudge', { ids: m, pan: dp * nudgeStep, tilt: dt * nudgeStep });
    }
    const g = e.target.closest('[data-goto]');
    if (g) { e.preventDefault(); $(`#progTabs [data-p=${g.dataset.goto}]`).click(); }
  });

  $('#btnFxClearSel').onclick = () => needSel() && api('remove_fx', { ids: selIds() });

  // escenas
  $('#btnSaveScene').onclick = async () => {
    const name = prompt('Nombre de la escena', 'Escena ' + (S.scenes.length + 1)); if (name === null) return;
    const id = await api('save_scene', { name, color: INIT.palette[(S.scenes.length + 2) % INIT.palette.length].hex });
    if (id) { lastScene = id; toast('Escena guardada'); }
  };
  $('#btnEditScenes').onclick = () => { editScenes = !editScenes; sigs.scenes = null; renderScenes(); };
  $('#scenes').addEventListener('click', async (e) => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.sre && confirm('¿Reemplazar esta escena por lo que está en escena ahora?')) { await api('save_scene', { id: b.dataset.sre }); toast('Escena regrabada'); }
    if (b.dataset.sren) { const s = S.scenes.find((x) => x.id === b.dataset.sren); const n = prompt('Nuevo nombre', s.name); if (n) api('update_scene', { id: s.id, name: n }); }
    if (b.dataset.smv) api('move_scene', { id: b.dataset.smv, delta: +b.dataset.d });
    if (b.dataset.sdel && confirm('¿Borrar la escena? También se quita de la secuencia.')) api('delete_scene', { id: b.dataset.sdel });
  });
  $('#scenes').addEventListener('change', (e) => { if (e.target.dataset.scol) api('update_scene', { id: e.target.dataset.scol, color: e.target.value }); });
  $('#scenes').addEventListener('keydown', (e) => { const s = e.target.closest('[data-scene]'); if (s && (e.key === 'Enter')) recall(s.dataset.scene); });

  // secuencia
  $('#go').onclick = () => api('go');
  $('#btnBack').onclick = () => api('back');
  $('#btnStopCues').onclick = () => api('stop_cues');
  $('#cueLoop').onchange = (e) => api('show_settings', { cue_loop: e.target.checked });
  $('#btnAddCue').onclick = () => $('#cueScene').value && api('add_cue', { scene: $('#cueScene').value });
  const cues = $('#cues');
  cues.addEventListener('change', (e) => {
    const t = e.target; if (!t.dataset.cue) return;
    api('update_cue', { id: t.dataset.cue, [t.dataset.k]: t.dataset.k === 'scene' ? t.value : (t.value === '' ? null : +t.value) });
  });
  cues.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.cuego) api('go', { index: +b.dataset.cuego });
    if (b.dataset.cuemv) api('move_cue', { id: b.dataset.cuemv, delta: +b.dataset.d });
    if (b.dataset.cuedel) api('delete_cue', { id: b.dataset.cuedel });
  });

  // patch
  $('#addProfile').onchange = updateAddNote;
  $('#btnAddFix').onclick = async () => {
    const r = await api('add_fixtures', { profile: $('#addProfile').value, count: +$('#addCount').value || 1, address: +$('#addAddr').value || null, name: $('#addName').value.trim() || null });
    if (r) { toast(r.length > 1 ? `Se agregaron ${r.length} equipos` : 'Equipo agregado'); $('#addAddr').value = ''; $('#addName').value = ''; }
  };
  const pr = $('#patchRows');
  pr.addEventListener('change', (e) => {
    const t = e.target; if (!t.dataset.fix) return;
    const v = t.type === 'checkbox' ? t.checked : t.type === 'number' ? +t.value : t.value;
    api('update_fixture', { id: t.dataset.fix, [t.dataset.k]: v }).then((ok) => { if (!ok) { sigs.patch = null; renderPatch(); } });
  });
  pr.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.fmv) api('move_fixture', { id: b.dataset.fmv, delta: +b.dataset.d });
    if (b.dataset.fdel && confirm('¿Quitar este equipo del show?')) { sel.delete(b.dataset.fdel); api('remove_fixture', { id: b.dataset.fdel }); }
  });

  // probar canales
  $('#testFix').onchange = () => { sigs.probar = null; renderProbar(); };
  $('#btnTestClear').onclick = () => { api('test_clear'); $$('#chRows input[type=range]').forEach((r) => (r.value = 0)); $$('#chRows .v').forEach((v) => (v.textContent = '—')); };
  $('#chRows').addEventListener('input', (e) => {
    const t = e.target;
    if (t.dataset.test) { t.closest('.chrow').querySelector('.v').textContent = t.value; sendLatest('t' + t.dataset.test, 'test_set', { address: +t.dataset.test, value: +t.value }); }
  });
  $('#chRows').addEventListener('change', (e) => {
    const t = e.target;
    if (t.dataset.ch != null && t.tagName === 'SELECT') { collectDraft(); draft.canales[+t.dataset.ch].attr = t.value; buildProbar(); }
    if (t.dataset.chdef != null) draft.canales[+t.dataset.chdef].default = Math.max(0, Math.min(255, +t.value || 0));
  });
  const we = $('#wheelEditors');
  const wSet = (box, v) => {
    v = Math.max(0, Math.min(255, Math.round(v)));
    $('[data-wval]', box).value = v; $('[data-wout]', box).textContent = v;
    sendLatest('w' + box.dataset.addr, 'test_set', { address: +box.dataset.addr, value: v });
  };
  we.addEventListener('input', (e) => {
    const box = e.target.closest('[data-wcal]'); if (!box) return;
    if (e.target.matches('[data-wval]')) wSet(box, +e.target.value);
  });
  we.addEventListener('change', (e) => {
    const box = e.target.closest('[data-wcal]');
    if (box && e.target.matches('[data-wheel]')) { draft[box.dataset.wcal] = parseWheel(e.target.value, box.dataset.wcal === 'color_wheel'); syncWheel(box.dataset.wcal); }
  });
  we.addEventListener('click', (e) => {
    const box = e.target.closest('[data-wcal]'); if (!box) return;
    const key = box.dataset.wcal, b = e.target.closest('button, [data-wjump]');
    if (!b) return;
    const cur = +$('[data-wval]', box).value;
    if (b.matches('[data-wlight]')) {
      const f = fx(draftFor);
      draft.canales.forEach((c, i) => {
        if (c.attr === 'intensity') api('test_set', { address: f.address + i, value: 255 });
        if (c.attr === 'strobe') api('test_set', { address: f.address + i, value: (draft.strobe || {}).off || 0 });
      });
      wSet(box, cur);
      toast('Equipo prendido para calibrar');
    } else if (b.dataset.wstep) wSet(box, cur + +b.dataset.wstep);
    else if (b.dataset.wdel != null) { draft[key].splice(+b.dataset.wdel, 1); syncWheel(key); }
    else if (b.dataset.wjump != null && !e.target.closest('button')) wSet(box, +b.dataset.wjump);
    else if (b.matches('[data-wclear]')) { if (confirm('¿Borrar todas las posiciones anotadas de esta rueda?')) { draft[key] = []; syncWheel(key); } }
    else if (b.dataset.wname) {
      const list = draft[key] = draft[key] || [];
      let name = b.dataset.wname;
      if (name === '*') name = (key === 'gobo' ? 'Gobo ' : 'Prisma ') + (list.filter((x) => x.nombre !== 'Abierto').length + 1);
      const entry = { nombre: name, dmx: cur };
      if (key === 'color_wheel') entry.hex = b.dataset.whex;
      const same = list.findIndex((x) => x.nombre === name);
      if (same >= 0) list[same] = entry; else list.push(entry);
      syncWheel(key);
      toast(`${name} anotado en ${cur}`);
    }
  });
  $('#btnSaveProfile').onclick = async () => {
    if (!draft) return;
    const r = await api('profile_save', { id: draft.id, data: collectDraft() });
    if (r) { await refreshProfiles(); toast('Perfil guardado. Los equipos que lo usan ya responden con el cambio.'); }
  };
  $('#btnSaveProfileAs').onclick = async () => {
    const name = $('#newProfileName').value.trim();
    if (!draft || !name) { toast('Escribí un nombre para el perfil nuevo'); return; }
    const old = fx(draftFor).profile;
    const data = collectDraft(); data.nombre = name; data.verificado = true;
    const pid = await api('profile_save', { id: draft.id, new_id: name, data });
    if (!pid) return;
    await refreshProfiles();
    if (confirm('¿Usar este perfil nuevo en todos los equipos que tenían “' + (PROF[old]?.nombre || old) + '”?')) {
      for (const f of fixtures().filter((x) => x.profile === old)) await api('update_fixture', { id: f.id, profile: pid });
    } else await api('update_fixture', { id: draftFor, profile: pid });
    $('#newProfileName').value = '';
    toast('Perfil nuevo guardado');
  };
  $('#rawVal').oninput = (e) => { $('#rawValOut').textContent = e.target.value; sendLatest('raw', 'test_set', { address: +$('#rawAddr').value, value: +e.target.value }); };
  $('#rawAddr').onchange = () => { $('#rawVal').value = 0; $('#rawValOut').textContent = '0'; };

  // show
  $('#btnSaveAs').onclick = async () => { const n = $('#showName').value.trim(); if (n && await api('show_save_as', { name: n })) toast('Show guardado como “' + n + '”'); };
  $('#showRows').addEventListener('click', async (e) => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.showopen) { sel.clear(); lastScene = null; if (await api('show_load', { name: b.dataset.showopen })) toast('Show abierto'); }
    if (b.dataset.showdel && confirm('¿Borrar el show “' + b.dataset.showdel + '”? No se puede deshacer.')) api('show_delete', { name: b.dataset.showdel });
  });
  const newShow = async (template) => {
    const name = $('#newShowName').value.trim() || prompt('Nombre del show nuevo', 'Show nuevo');
    if (!name) return;
    sel.clear(); lastScene = null;
    if (await api('show_new', { name, template })) { $('#newShowName').value = ''; toast('Show nuevo creado'); }
  };
  $('#btnNewMine').onclick = () => newShow('mi_equipo');
  $('#btnNewEmpty').onclick = () => newShow('vacio');
  $('#outKind').onchange = (e) => api('output_set', { kind: e.target.value });
  $('#outRate').onchange = (e) => api('output_set', { rate: e.target.value }).then((ok) => ok && toast('Ritmo de envío cambiado'));
  $('#btnReconnect').onclick = () => api('output_set', { kind: $('#outKind').value }).then((ok) => ok && toast('Reconectando la interfaz'));
  $('#remote').onchange = (e) => api('app_settings', { control_remoto: e.target.checked });
  $('#btnQuit').onclick = () => { if (confirm('Se apagan todas las luces y se cierra el programa. ¿Seguro?')) api('quit'); };

  // teclado
  const holdKeys = { f: 'flash', s: 'strobe', a: 'strobe2', h: 'humo' };
  const isTyping = (e) => e.target.matches('input[type=text], input[type=number], textarea, select');
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a' && !isTyping(e)) { e.preventDefault(); applyGroup('all'); return; }
    if (isTyping(e) || e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === ' ') { e.preventDefault(); if (!e.repeat) api('go'); }
    else if (/^[1-9]$/.test(k)) { const s = S.scenes[+k - 1]; if (s) recall(s.id); }
    else if (k === 't' && !e.repeat && !S.sync_ext) api('tap');
    else if (k === 'b' && !e.repeat) api('blackout', { on: !S.blackout });
    else if (k === 'escape') applyGroup('none');
    else if (holdKeys[k] && !e.repeat) api('hold', { kind: holdKeys[k], on: true });
  });
  document.addEventListener('keyup', (e) => { const k = e.key.toLowerCase(); if (holdKeys[k]) api('hold', { kind: holdKeys[k], on: false }); });
  // seguridad: si la ventana pierde el foco, se sueltan flash/strobo/humo
  window.addEventListener('blur', () => { for (const k of ['flash', 'strobe', 'strobe2', 'humo']) if (S && S.holds.includes(k)) api('hold', { kind: k, on: false }); });
}

function xyMove(e) {
  const [x, y] = xyFromEvent(e);
  const { movers, start, cx, cy } = xyDrag;
  const values = {};
  for (const i of movers) values[i] = [Math.min(1, Math.max(0, start[i][0] + x - cx)), Math.min(1, Math.max(0, start[i][1] + y - cy))];
  sendLatest('xy', 'set_positions', { values });
}

async function refreshProfiles() {
  const j = await (await fetch('/api/profiles')).json();
  PROF = Object.fromEntries(j.map((p) => [p.id, p]));
  for (const k of ['probar', 'patch', 'patchProfiles', 'tiles', 'slots']) sigs[k] = null;
  onSync(S);
}

boot();
