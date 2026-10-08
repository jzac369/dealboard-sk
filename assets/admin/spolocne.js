// ── Spoločné pomôcky pre moduly adminu ────────────────────────────────
// window.HKU: prístup k databáze, registrácia stránok, formátovanie,
// grafy, okná, CSV, úlohy pre plánovač. Moduly sa načítajú po hlavnom
// skripte v admin.html, ktorý pripraví window.HK (dáta a prihlásenie).
import {
  collection, collectionGroup, doc, getDoc, getDocs, setDoc, updateDoc, addDoc, deleteDoc, query, where,
  orderBy, limit, onSnapshot, serverTimestamp, writeBatch, documentId, Timestamp, deleteField, increment,
} from "https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js";

const fs = {
  collection, collectionGroup, doc, getDoc, getDocs, setDoc, updateDoc, addDoc, deleteDoc, query, where,
  orderBy, limit, onSnapshot, serverTimestamp, writeBatch, documentId, Timestamp, deleteField, increment,
};

const esc = t => String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const norm = t => String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
const pad = n => String(n).padStart(2, '0');
const naDatum = t => (t && t.toDate) ? t.toDate() : (t instanceof Date ? t : (typeof t === 'number' ? new Date(t) : (typeof t === 'string' && t ? new Date(t) : null)));

const U = window.HKU = {
  fs, esc, norm, pad, naDatum,
  get db() { return window.HK.db; },
  ref: (...cesta) => doc(window.HK.db, ...cesta),
  kol: (...cesta) => collection(window.HK.db, ...cesta),

  // ── formátovanie ──
  eur: (n, des = 2) => (Number(n) || 0).toLocaleString('sk-SK', { minimumFractionDigits: des, maximumFractionDigits: des }) + ' €',
  cislo: n => (Number(n) || 0).toLocaleString('sk-SK'),
  den: t => { const d = naDatum(t); return d ? `${d.getDate()}. ${d.getMonth() + 1}. ${d.getFullYear()}` : ''; },
  cas: t => { const d = naDatum(t); return d ? `${d.getDate()}. ${d.getMonth() + 1}. ${pad(d.getHours())}:${pad(d.getMinutes())}` : ''; },
  casDlhy: t => {
    const d = naDatum(t); if (!d) return '';
    const dni = ['ne', 'po', 'ut', 'st', 'št', 'pi', 'so'];
    return `${dni[d.getDay()]} ${d.getDate()}. ${d.getMonth() + 1}. o ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  },
  pred: t => {
    const d = naDatum(t); if (!d) return '';
    const m = Math.round((Date.now() - d.getTime()) / 60000);
    if (m < 1) return 'práve teraz';
    if (m < 60) return `pred ${m} min`;
    if (m < 1440) return `pred ${Math.round(m / 60)} h`;
    return `pred ${Math.round(m / 1440)} d`;
  },
  iso: d => d.toISOString().slice(0, 10),
  doInputu: d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`,
  dnesIso: () => new Date().toISOString().slice(0, 10),
  isoPosun: (iso, dni) => { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + dni); return d.toISOString().slice(0, 10); },
  mesiac: iso => { const [r, m] = iso.split('-'); return ['jan', 'feb', 'mar', 'apr', 'máj', 'jún', 'júl', 'aug', 'sep', 'okt', 'nov', 'dec'][Number(m) - 1] + ' ' + r.slice(2); },
  sklon: (n, a, b, c) => `${n} ${n === 1 ? a : (n >= 2 && n <= 4 ? b : c)}`,
  host: u => { try { return new URL(u).hostname.replace(/^www\./, '').toLowerCase(); } catch (e) { return ''; } },

  // Rovnaký tvar adresy ako generate_deal_pages.py a facebook_post.py.
  slug: t => {
    let s = String(t || '').normalize('NFKD').replace(/[^\x00-\x7F]/g, '').toLowerCase();
    s = s.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    return s.slice(0, 60).replace(/^-+|-+$/g, '') || 'deal';
  },
  adresaDealu: d => `https://henkukaj.sk/deal/${U.slug(d.title)}-${d.id}/`,

  // ── registrácia stránok ──
  // init(el) raz pri prvom otvorení (po prihlásení), show(el) pri každom
  // otvorení a po udalostiach v zozname obnov (napr. 'hk:deals').
  _stranky: {},
  stranka(id, def) {
    U._stranky[id] = { ...def, hotovo: false };
    U._skus(id);
  },
  _el: id => document.getElementById('pg-' + id),
  async _skus(id) {
    const s = U._stranky[id];
    // Provízie sú súčasť záložky Prehľad v stránke Dognet: načítajú sa, až keď je záložka otvorená.
    const vidna = window.HK_STRANKA === id || (id === 'provizie' && window.HK_STRANKA === 'dognet' && (window.HK_DOGNET_TAB || 'prehlad') === 'prehlad');
    if (!s || !vidna || !window.HK || !window.HK.rola) return;
    const el = U._el(id);
    if (!el) return;
    try {
      // init môže byť async (načítanie dát) - show až po ňom, a druhé
      // volanie počas načítavania počká na to isté.
      if (!s.pripravene) { el.innerHTML = ''; s.pripravene = Promise.resolve(s.init && s.init(el)); }
      await s.pripravene;
      s.hotovo = true;
      if (s.show) await s.show(el);
    } catch (e) {
      // Zlyhané načítanie (napr. výpadok siete) sa pri ďalšom otvorení skúsi znova.
      if (!s.hotovo) s.pripravene = null;
      console.error('Stránka', id, e);
      el.insertAdjacentHTML('beforeend', `<p class="pg-chyba">Stránku sa nepodarilo zobraziť: ${esc(e.message)}</p>`);
    }
  },
  jeVidna: id => window.HK_STRANKA === id,

  // ── úlohy pre plánovač (admin_ulohy) ──
  // Vráti Promise s výsledkom; priebeh(stav, ms) hlási čakanie.
  uloha(typ, vstup, priebeh) {
    return new Promise(async (ok, zle) => {
      let ref;
      try {
        ref = await addDoc(U.kol('admin_ulohy'), { typ, vstup: vstup || {}, stav: 'caka', vytvorene: serverTimestamp(), by: window.HK.email });
      } catch (e) { zle(e); return; }
      const t0 = Date.now();
      const tik = setInterval(() => priebeh && priebeh('caka', Date.now() - t0), 1000);
      const unsub = onSnapshot(ref, s => {
        const d = s.data() || {};
        if (d.stav === 'hotovo') { clearInterval(tik); unsub(); ok(d.vysledok || {}); }
        else if (d.stav === 'chyba') { clearInterval(tik); unsub(); zle(new Error(d.chyba || 'Úloha zlyhala.')); }
        else if (priebeh) priebeh(d.stav, Date.now() - t0);
      }, e => { clearInterval(tik); zle(e); });
    });
  },
  textCakania: (stav, ms) => stav === 'bezi'
    ? 'Plánovač na tom pracuje…'
    : (ms < 45000 ? 'Čakám na plánovač (zvyčajne pár sekúnd)…'
      : 'Plánovač sa práve reštartuje – úloha sa spustí hneď, ako sa rozbehne (najneskôr do 15 minút). Stránku môžeš zatvoriť, výsledok sa uloží.'),

  // ── súbory ──
  stiahni(nazov, obsah, typ = 'text/plain;charset=utf-8') {
    const blob = obsah instanceof Blob ? obsah : new Blob([obsah], { type: typ });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = nazov;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  },
  citajSubor: (subor, ako = 'text') => new Promise((ok, zle) => {
    const r = new FileReader();
    r.onload = () => ok(r.result);
    r.onerror = () => zle(r.error);
    if (ako === 'url') r.readAsDataURL(subor); else r.readAsText(subor, 'utf-8');
  }),
  // CSV: oddeľovač zistí sám (; , tab), úvodzovky podľa normy.
  csv(text) {
    text = String(text || '').replace(/^﻿/, '');
    const prvy = text.split(/\r?\n/)[0] || '';
    const odd = [';', ',', '\t'].sort((a, b) => prvy.split(b).length - prvy.split(a).length)[0];
    const riadky = []; let r = [], b = '', vUv = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (vUv) {
        if (c === '"') { if (text[i + 1] === '"') { b += '"'; i++; } else vUv = false; }
        else b += c;
      } else if (c === '"') vUv = true;
      else if (c === odd) { r.push(b); b = ''; }
      else if (c === '\n' || c === '\r') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        r.push(b); b = '';
        if (r.some(x => x.trim() !== '')) riadky.push(r);
        r = [];
      } else b += c;
    }
    r.push(b);
    if (r.some(x => x.trim() !== '')) riadky.push(r);
    return riadky;
  },
  kopiruj(text) {
    navigator.clipboard.writeText(text).then(() => window.toast('Skopírované do schránky.'), () => window.toast('Kopírovanie zlyhalo.', 'chyba'));
  },

  // ── okno ──
  okno(titulok, html, { siroke = false } = {}) {
    U.zavriOkno();
    const ov = document.createElement('div');
    ov.className = 'hk-okno-ov';
    ov.innerHTML = `<div class="hk-okno${siroke ? ' siroke' : ''}" role="dialog" aria-modal="true">
        <div class="hk-okno-hlava"><h3>${esc(titulok)}</h3><button type="button" class="btn btn-ic" data-zavriet aria-label="Zavrieť"><svg class="ix"><use href="#ix-x"></use></svg></button></div>
        <div class="hk-okno-telo">${html}</div></div>`;
    ov.addEventListener('click', e => { if (e.target === ov || e.target.closest('[data-zavriet]')) U.zavriOkno(); });
    document.body.appendChild(ov);
    document.body.classList.add('okno-otvorene');
    U._esc = e => { if (e.key === 'Escape') U.zavriOkno(); };
    document.addEventListener('keydown', U._esc);
    return ov.querySelector('.hk-okno-telo');
  },
  zavriOkno() {
    document.querySelectorAll('.hk-okno-ov').forEach(x => x.remove());
    document.body.classList.remove('okno-otvorene');
    if (U._esc) document.removeEventListener('keydown', U._esc);
  },

  // ── grafy (bez knižnice) ──
  // Vodorovné pruhy: [[popis, hodnota, doplnok?], …]
  pruhy(dvojice, { format = U.cislo, prazdne = 'Zatiaľ žiadne dáta.', max = 12 } = {}) {
    if (!dvojice.length) return `<p class="vis-empty">${esc(prazdne)}</p>`;
    const top = Math.max(...dvojice.map(d => d[1])) || 1;
    return `<div class="hb">` + dvojice.slice(0, max).map(([n, v, x]) => `
      <div class="hb-r"><span class="hb-n" title="${esc(n)}">${esc(n)}</span>
        <span class="hb-w"><span class="hb-b" style="width:${Math.max(1.5, v / top * 100).toFixed(1)}%"></span></span>
        <b class="hb-v">${format(v)}</b>${x ? `<span class="hb-x">${x}</span>` : ''}</div>`).join('') + `</div>`;
  },
  // Stĺpcový graf, aj skladaný: rady = [{ n, farba, hodnoty: [] }], popisy = []
  stlpce(popisy, rady, { format = U.cislo, vyska = 200 } = {}) {
    const n = popisy.length;
    if (!n) return '<p class="vis-empty">Zatiaľ žiadne dáta.</p>';
    const sucty = popisy.map((_, i) => rady.reduce((a, r) => a + (Number(r.hodnoty[i]) || 0), 0));
    const max = Math.max(...sucty) || 1;
    const W = 1000, H = vyska, top = 14, dole = 24, sir = W / n, st = Math.max(4, Math.min(48, sir * 0.62));
    const kazdy = Math.ceil(n / 12);
    let svg = `<svg class="graf" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img">`;
    [0.25, 0.5, 0.75, 1].forEach(k => {
      const y = top + (H - top - dole) * (1 - k);
      svg += `<line x1="0" x2="${W}" y1="${y}" y2="${y}" class="graf-mriezka"/>`;
    });
    popisy.forEach((p, i) => {
      let y = H - dole;
      const x = i * sir + (sir - st) / 2;
      rady.forEach(r => {
        const v = Number(r.hodnoty[i]) || 0;
        if (!v) return;
        const h = v / max * (H - top - dole);
        y -= h;
        svg += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${st.toFixed(1)}" height="${h.toFixed(1)}" rx="3" fill="${r.farba}"><title>${esc(p)} · ${esc(r.n)}: ${esc(format(v))}</title></rect>`;
      });
    });
    svg += `</svg>`;
    const osa = `<div class="graf-osa">${popisy.map((p, i) => `<span style="left:${((i + 0.5) / n * 100).toFixed(2)}%">${i % kazdy === 0 ? esc(p) : ''}</span>`).join('')}</div>`;
    const legenda = rady.length > 1 ? `<div class="graf-leg">${rady.map(r => `<span><i style="background:${r.farba}"></i>${esc(r.n)}</span>`).join('')}</div>` : '';
    return `<div class="graf-wrap"><div class="graf-max">${esc(format(max))}</div>${svg}${osa}${legenda}</div>`;
  },

  // ── obdobie ──
  // Lišta Dnes / 7 / 30 / 90 / vlastné; po zmene zavolá zmena(rozsah).
  obdobie(el, zmena, predvolene = '30') {
    const stav = { typ: predvolene, od: '', do: '' };
    el.innerHTML = `<div class="obdobie-bar">
        ${[['1', 'Dnes'], ['7', '7 dní'], ['30', '30 dní'], ['90', '90 dní'], ['365', 'Rok']].map(([k, t]) =>
          `<button type="button" data-o="${k}" class="${k === predvolene ? 'on' : ''}">${t}</button>`).join('')}
        <span class="obdobie-vlastne"><input type="date" data-od aria-label="Od"> – <input type="date" data-do aria-label="Do">
          <button type="button" data-o="vlastne">Použiť</button></span>
      </div><p class="obdobie-text"></p>`;
    const vypis = () => {
      const r = window.HK.rozsah(stav);
      const f = i => `${Number(i.slice(8))}. ${Number(i.slice(5, 7))}. ${i.slice(0, 4)}`;
      el.querySelector('.obdobie-text').textContent = `${f(r.od)} – ${f(r.do)} · porovnanie s ${f(r.predOd)} – ${f(r.predDo)}`;
      return r;
    };
    el.addEventListener('click', e => {
      const b = e.target.closest('[data-o]');
      if (!b) return;
      if (b.dataset.o === 'vlastne') {
        stav.od = el.querySelector('[data-od]').value; stav.do = el.querySelector('[data-do]').value;
        if (!stav.od || !stav.do) { window.toast('Vyber dátum od a do.', 'chyba'); return; }
      }
      stav.typ = b.dataset.o;
      el.querySelectorAll('[data-o]').forEach(x => x.classList.toggle('on', x === b));
      zmena(vypis());
    });
    return { rozsah: vypis };
  },
  zmena(teraz, predtym) {
    if (!predtym && !teraz) return '<span class="kpi-d">–</span>';
    if (!predtym) return '<span class="kpi-d nahor">nové</span>';
    const pct = Math.round((teraz - predtym) / predtym * 100);
    return `<span class="kpi-d ${pct > 0 ? 'nahor' : (pct < 0 ? 'nadol' : '')}">${pct > 0 ? '▲' : (pct < 0 ? '▼' : '')} ${Math.abs(pct)} %</span>`;
  },
  kpi: (lab, hod, zmena = '', sub = '') => `<div class="kpi"><div class="kpi-lab">${lab}</div><div class="kpi-num">${hod}</div>${zmena}${sub ? `<div class="kpi-sub">${sub}</div>` : ''}</div>`,

  // Dokumenty s dátumom ako ID (kliky_den, pouzitie) v rozsahu dní.
  async dni(kolekcia, od, doD) {
    const snap = await getDocs(query(U.kol(kolekcia), where(documentId(), '>=', od), where(documentId(), '<=', doD)));
    const m = {};
    snap.forEach(d => { m[d.id] = d.data() || {}; });
    return m;
  },

  // Tlačidlo s priebehom: počas akcie je vypnuté.
  async akcia(btn, fn) {
    const povodne = btn.innerHTML;
    btn.disabled = true;
    try { return await fn(); }
    catch (e) { console.error(e); window.toast('Nepodarilo sa: ' + e.message, 'chyba'); }
    finally { btn.disabled = false; btn.innerHTML = povodne; }
  },
  upozornenia(zdroj, zoznam) {
    window.HK_UPOZORNENIA = window.HK_UPOZORNENIA || {};
    window.HK_UPOZORNENIA[zdroj] = zoznam;
    if (window.HK_ZVONCEK) window.HK_ZVONCEK();
  },
};

document.addEventListener('hk:stranka', e => U._skus(e.detail.id));
document.addEventListener('hk:prihlaseny', () => setTimeout(() => U._skus(window.HK_STRANKA), 0));
// Obnova otvorenej stránky po zmene dát (najviac raz za 400 ms).
let _obnovT = null;
['hk:deals', 'hk:coupons', 'hk:comments', 'hk:visits', 'hk:clicks', 'hk:plan', 'hk:hlasenia'].forEach(ev => document.addEventListener(ev, () => {
  const id = window.HK_STRANKA, s = U._stranky[id];
  if (!s || !s.hotovo || !s.obnov || !s.obnov.includes(ev)) return;
  clearTimeout(_obnovT);
  _obnovT = setTimeout(() => { try { s.show(U._el(id)); } catch (e) { console.error(e); } }, 400);
}));
