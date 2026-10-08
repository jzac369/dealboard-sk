// ── Zarábanie: provízie (import CSV), reklamné miesta, príjmy ─────────
const U = window.HKU, HK = () => window.HK, { fs, esc } = U;

// Načítané provízie zdieľajú stránky Provízie a Príjmy.
let provizie = null;
async function nacitajProvizie(znova) {
  if (provizie && !znova) return provizie;
  const s = await fs.getDocs(U.kol('provizie'));
  provizie = s.docs.map(d => ({ ...d.data(), id: d.id }));
  return provizie;
}

// Názov kampane z Dognetu ("Alza.sk", "GymBeam SK") -> porovnanie s
// doménami dealov ("alza.sk", "gymbeam.sk").
const kluc = t => U.norm(t).replace(/^www\./, '').replace(/\.(sk|cz|com|eu|hu|pl|at|de)\b.*$/, '').replace(/[^a-z0-9]/g, '');
function preklikyObchodu(nazov) {
  const k = kluc(nazov);
  if (!k) return { kliky: 0, dealy: 0 };
  let kliky = 0, dealy = 0;
  HK().deals.forEach(d => {
    if (d.status !== 'approved' && d.status !== 'archived') return;
    if (kluc(U.host(d.url)) === k || kluc(d.store) === k) { dealy++; kliky += HK().clicks[d.id] || 0; }
  });
  return { kliky, dealy };
}

function cenaZTextu(t) {
  const s = String(t || '').replace(/\s| |€|eur/gi, '');
  const m = s.match(/-?\d+(?:[.,]\d{3})*(?:[.,]\d+)?/);
  if (!m) return null;
  let c = m[0];
  if (c.includes(',') && c.includes('.')) c = c.lastIndexOf(',') > c.lastIndexOf('.') ? c.replace(/\./g, '').replace(',', '.') : c.replace(/,/g, '');
  else if (c.includes(',')) c = c.replace(',', '.');
  const v = Number(c);
  return isNaN(v) ? null : v;
}
function datumZTextu(t) {
  t = String(t || '').trim();
  let m = t.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return `${m[1]}-${U.pad(m[2])}-${U.pad(m[3])}`;
  m = t.match(/^(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})/);
  if (m) return `${m[3]}-${U.pad(m[2])}-${U.pad(m[1])}`;
  m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (m) return `${m[3]}-${U.pad(m[1])}-${U.pad(m[2])}`;
  return null;
}
function stavZTextu(t) {
  const s = U.norm(t);
  if (/zamiet|declin|reject|storn|cancel|neschval|odmiet/.test(s)) return 'zamietnuta';
  if (/schval|approv|accept|potvrd|paid|vyplat|confirm/.test(s)) return 'schvalena';
  if (/cak|pend|new|nov|open|wait|spracov/.test(s)) return 'caka';
  return s ? 'caka' : 'schvalena';
}
async function hash(t) {
  const b = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(t));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('').slice(0, 24);
}

const STLPCE = [
  ['datum', 'Dátum', /datum|date|cas|vytvoren|created|time/],
  ['obchod', 'Obchod / kampaň', /kampan|campaign|inzerent|advertiser|obchod|program|merchant|eshop|shop/],
  ['suma', 'Provízia (€)', /provizi|commission|odmena|reward|payout|zarobok/],
  ['stav', 'Stav', /^stav|status|state/],
  ['tid', 'ID transakcie (odporúčané)', /^id$|transak|transaction|order.?id|objednav.*id|^tid/],
  ['url', 'Produkt / URL (nepovinné)', /url|odkaz|produkt|product|referer|landing/],
];

U.stranka('provizie', {
  async init(el) {
    el.innerHTML = `
      <div class="karta">
        <h3 class="karta-nadpis">Import z Dognetu</h3>
        <p class="settings-hint">V Dognete otvor <b>Reporty → Transakcie</b>, vyber obdobie a stiahni <b>CSV</b>. Súbor sem pretiahni alebo vyber.
          Opakovaný import tých istých transakcií nič nezdvojí – iba aktualizuje ich stav.</p>
        <label class="pv-drop" id="pv-drop"><svg class="ix"><use href="#ix-upload"></use></svg> Pretiahni CSV sem alebo <u>vyber súbor</u>
          <input type="file" id="pv-subor" accept=".csv,text/csv" hidden></label>
        <div id="pv-mapa"></div>
      </div>
      <div class="karta">
        <div class="riadok-pole"><h3 class="karta-nadpis" style="flex:1;margin:0">Prehľad</h3>
          <select id="pv-rok"></select></div>
        <div class="kpi-row" id="pv-kpi"></div>
        <div id="pv-graf"></div>
      </div>
      <div class="karta">
        <h3 class="karta-nadpis">Podľa obchodu</h3>
        <div class="tab-wrap"><table class="tab"><thead><tr><th>Obchod</th><th class="n">Transakcií</th><th class="n">Schválené</th><th class="n">Čakajúce</th>
          <th class="n">Dealov</th><th class="n">Preklikov</th><th class="n" title="Schválené aj čakajúce provízie delené preklikmi">€ / preklik</th></tr></thead>
          <tbody id="pv-obchody"></tbody></table></div>
        <p class="settings-hint">Prekliky sú zo zverejnených dealov daného obchodu na tvojej stránke (spolu za celé obdobie).
          Vysoké „€ / preklik“ = obchod, pri ktorom sa oplatí hľadať viac dealov.</p>
        <div class="tl-rad" style="margin-top:12px"><button class="btn btn-delete" id="pv-zmaz"><svg class="ix"><use href="#ix-trash"></use></svg> Vymazať všetky importované provízie</button></div>
      </div>`;
    const drop = el.querySelector('#pv-drop');
    ['dragover', 'dragenter'].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add('nad'); }));
    ['dragleave', 'drop'].forEach(t => drop.addEventListener(t, () => drop.classList.remove('nad')));
    drop.addEventListener('drop', e => { e.preventDefault(); if (e.dataTransfer.files[0]) this._subor(el, e.dataTransfer.files[0]); });
    el.querySelector('#pv-subor').addEventListener('change', e => e.target.files[0] && this._subor(el, e.target.files[0]));
    el.querySelector('#pv-rok').addEventListener('change', () => this.show(el));
    el.querySelector('#pv-zmaz').addEventListener('click', async e => {
      if (!await window.potvrd('Vymazať všetky importované provízie? Dajú sa znova naimportovať z CSV.')) return;
      await U.akcia(e.currentTarget, async () => {
        const vsetky = await nacitajProvizie(true);
        for (let i = 0; i < vsetky.length; i += 400) {
          const b = fs.writeBatch(U.db);
          vsetky.slice(i, i + 400).forEach(p => b.delete(U.ref('provizie', p.id)));
          await b.commit();
        }
        await nacitajProvizie(true);
        HK().logChange('provizie', 'provizie', `Vymazaných ${vsetky.length} provízií`);
        window.toast('Provízie vymazané.');
        this.show(el);
      });
    });
    await nacitajProvizie();
  },
  async _subor(el, subor) {
    const riadky = U.csv(await U.citajSubor(subor));
    if (riadky.length < 2) { window.toast('V súbore nie sú žiadne riadky.', 'chyba'); return; }
    const hlava = riadky[0].map(h => h.trim()), data = riadky.slice(1);
    const odhad = {};
    STLPCE.forEach(([k, , re]) => {
      const i = hlava.findIndex(h => re.test(U.norm(h)) && !Object.values(odhad).includes(hlava.indexOf(h)));
      odhad[k] = i;
    });
    const mapa = el.querySelector('#pv-mapa');
    mapa.innerHTML = `<div class="pv-mapovanie">
        <p class="settings-hint">Súbor <b>${esc(subor.name)}</b>: ${data.length} riadkov. Skontroluj, ktorý stĺpec je čo:</p>
        <div class="form-mriezka">${STLPCE.map(([k, n]) => `<label>${n}<select data-st="${k}">
          <option value="-1">— nie je —</option>${hlava.map((h, i) => `<option value="${i}"${odhad[k] === i ? ' selected' : ''}>${esc(h || `stĺpec ${i + 1}`)}</option>`).join('')}</select></label>`).join('')}</div>
        <div id="pv-ukazka"></div>
        <div class="tl-rad"><button class="btn btn-save" id="pv-import">Importovať</button><button class="btn" id="pv-zrus">Zrušiť</button></div></div>`;
    const prevod = () => {
      const st = {};
      mapa.querySelectorAll('[data-st]').forEach(s => { st[s.dataset.st] = Number(s.value); });
      const bunka = (r, k) => st[k] >= 0 ? (r[st[k]] || '').trim() : '';
      return data.map(r => ({
        datum: datumZTextu(bunka(r, 'datum')), obchod: bunka(r, 'obchod'), suma: cenaZTextu(bunka(r, 'suma')),
        stavText: bunka(r, 'stav'), stav: stavZTextu(bunka(r, 'stav')), tid: bunka(r, 'tid'), url: bunka(r, 'url'),
      })).filter(t => t.datum && t.suma !== null);
    };
    const ukazka = () => {
      const t = prevod();
      mapa.querySelector('#pv-ukazka').innerHTML = `<p class="settings-hint">Rozpoznaných transakcií: <b>${t.length}</b> z ${data.length}
          (spolu ${U.eur(t.reduce((a, x) => a + x.suma, 0))}).</p>
        <div class="tab-wrap"><table class="tab"><thead><tr><th>Dátum</th><th>Obchod</th><th class="n">Provízia</th><th>Stav</th></tr></thead><tbody>
        ${t.slice(0, 5).map(x => `<tr><td>${esc(x.datum)}</td><td>${esc(x.obchod)}</td><td class="n">${U.eur(x.suma)}</td><td>${esc(x.stav)}${x.stavText ? ` <small>(${esc(x.stavText)})</small>` : ''}</td></tr>`).join('')}
        </tbody></table></div>`;
      mapa.querySelector('#pv-import').textContent = `Importovať ${t.length} transakcií`;
      mapa.querySelector('#pv-import').disabled = !t.length;
    };
    mapa.addEventListener('change', ukazka);
    ukazka();
    mapa.querySelector('#pv-zrus').onclick = () => { mapa.innerHTML = ''; el.querySelector('#pv-subor').value = ''; };
    mapa.querySelector('#pv-import').onclick = e => U.akcia(e.currentTarget, async () => {
      const t = prevod();
      for (let i = 0; i < t.length; i += 400) {
        const b = fs.writeBatch(U.db);
        for (const x of t.slice(i, i + 400)) {
          const id = await hash(x.tid ? 'tid|' + x.tid : [x.datum, x.obchod, x.suma, x.url].join('|'));
          b.set(U.ref('provizie', id), { datum: x.datum, obchod: x.obchod, suma: x.suma, stav: x.stav, stavText: x.stavText,
            url: x.url || null, zdroj: 'dognet', importovane: fs.serverTimestamp() });
        }
        await b.commit();
      }
      HK().logChange('provizie', 'provizie', `Import ${t.length} transakcií (${subor.name})`);
      window.toast(`Naimportovaných ${t.length} transakcií.`);
      mapa.innerHTML = '';
      await nacitajProvizie(true);
      this.show(el);
    });
  },
  async show(el) {
    const vsetky = await nacitajProvizie();
    const roky = [...new Set(vsetky.map(p => p.datum.slice(0, 4)))].sort().reverse();
    const sel = el.querySelector('#pv-rok');
    const vybrany = sel.value || 'vsetko';
    sel.innerHTML = `<option value="vsetko">Celé obdobie</option>` + roky.map(r => `<option value="${r}">${r}</option>`).join('');
    sel.value = roky.includes(vybrany) || vybrany === 'vsetko' ? vybrany : 'vsetko';
    const zoz = vsetky.filter(p => sel.value === 'vsetko' || p.datum.startsWith(sel.value));
    const sucet = s => zoz.filter(p => p.stav === s).reduce((a, p) => a + p.suma, 0);
    el.querySelector('#pv-kpi').innerHTML = !vsetky.length
      ? '<p class="vis-empty">Zatiaľ žiadne provízie – naimportuj CSV z Dognetu.</p>'
      : U.kpi('Schválené', U.eur(sucet('schvalena'))) + U.kpi('Čakajúce', U.eur(sucet('caka'))) +
        U.kpi('Zamietnuté', U.eur(sucet('zamietnuta'))) + U.kpi('Transakcií', U.cislo(zoz.length));
    const mesiace = [...new Set(zoz.map(p => p.datum.slice(0, 7)))].sort();
    el.querySelector('#pv-graf').innerHTML = mesiace.length ? U.stlpce(mesiace.map(U.mesiac), [
      { n: 'Schválené', farba: '#1E7A3A', hodnoty: mesiace.map(m => zoz.filter(p => p.stav === 'schvalena' && p.datum.startsWith(m)).reduce((a, p) => a + p.suma, 0)) },
      { n: 'Čakajúce', farba: '#E8A33D', hodnoty: mesiace.map(m => zoz.filter(p => p.stav === 'caka' && p.datum.startsWith(m)).reduce((a, p) => a + p.suma, 0)) },
    ], { format: v => U.eur(v) }) : '';
    const obchody = {};
    zoz.forEach(p => {
      const o = obchody[p.obchod || '(neuvedené)'] = obchody[p.obchod || '(neuvedené)'] || { n: 0, sch: 0, cak: 0 };
      o.n++;
      if (p.stav === 'schvalena') o.sch += p.suma;
      if (p.stav === 'caka') o.cak += p.suma;
    });
    const riadky = Object.entries(obchody).sort((a, b) => (b[1].sch + b[1].cak) - (a[1].sch + a[1].cak));
    el.querySelector('#pv-obchody').innerHTML = riadky.length ? riadky.map(([n, o]) => {
      const pk = preklikyObchodu(n);
      return `<tr><td>${esc(n)}</td><td class="n">${o.n}</td><td class="n">${U.eur(o.sch)}</td><td class="n">${U.eur(o.cak)}</td>
        <td class="n">${pk.dealy || '–'}</td><td class="n">${pk.kliky || '–'}</td>
        <td class="n"><b>${pk.kliky ? U.eur((o.sch + o.cak) / pk.kliky, 3) : '–'}</b></td></tr>`;
    }).join('') : '<tr><td colspan="7" class="vis-empty">Zatiaľ žiadne dáta.</td></tr>';
  },
});

// ═══════════════════════════════════════════════════════════════════
// Reklamné miesta
// ═══════════════════════════════════════════════════════════════════
const MIESTA = { sidebar: 'Bočný panel (štvorec 250×250 / 300×250)', hore: 'Pod hlavičkou (pás, napr. 728×90)' };
const SLEDOVANIE_TV = {
  id: 'sledovanietv', nazov: 'SledovanieTV', miesto: 'sidebar', zap: true, vaha: 1, od: '', do: '',
  obrazok: 'https://login.dognet.sk/accounts/default1/banners/ccb20f25.jpg',
  url: 'https://go.dognet.com/?chid=BYWNg1rZ&url=https%3A%2F%2Fsledovanietv.sk%2Fott%2Fwelcome',
  alt: 'SledovanieTV.sk — televízia cez internet',
};
const rek = { bannery: null, kliky30: {} };
async function ulozReklamy(popis) {
  await fs.setDoc(U.ref('settings', 'reklamy'), { bannery: rek.bannery, upravene: fs.serverTimestamp() });
  HK().logChange('settings-reklamy', 'reklamy', popis);
}
function formularReklamy(b, ulozene) {
  const novy = !b;
  b = b || { id: Math.random().toString(36).slice(2, 10), nazov: '', miesto: 'sidebar', zap: true, vaha: 1, od: '', do: '', obrazok: '', url: '', alt: '' };
  const telo = U.okno(novy ? 'Nový banner' : 'Upraviť banner', `
    <form class="form-mriezka" id="rk-form">
      <label>Názov<input name="nazov" value="${esc(b.nazov)}" required maxlength="60"></label>
      <label>Miesto<select name="miesto">${Object.entries(MIESTA).map(([k, t]) => `<option value="${k}"${b.miesto === k ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select></label>
      <label class="cela">Obrázok (https://…)<input name="obrazok" type="url" value="${esc(b.obrazok)}" required></label>
      <label class="cela">Cieľový odkaz (https://… – napr. z Dognetu)<input name="url" type="url" value="${esc(b.url)}" required></label>
      <label class="cela">Popis obrázka (pre nevidiacich a vyhľadávače)<input name="alt" value="${esc(b.alt)}" maxlength="120"></label>
      <label>Zobrazovať od<input name="od" type="date" value="${esc(b.od)}"></label>
      <label>Zobrazovať do<input name="do" type="date" value="${esc(b.do)}"></label>
      <label>Váha pri striedaní<input name="vaha" type="number" min="1" max="10" value="${Number(b.vaha) || 1}"></label>
      <label class="zaskrt"><input name="zap" type="checkbox"${b.zap ? ' checked' : ''}> Zapnutý</label>
      <div class="cela rk-nahlad" id="rk-nahlad"></div>
      <div class="cela tl-rad"><button class="btn btn-save" type="submit">Uložiť</button><button class="btn" type="button" data-zavriet>Zrušiť</button></div>
    </form>
    <p class="settings-hint">Keď je na jednom mieste viac zapnutých bannerov, pri každej návšteve sa vyberie jeden – náhodne podľa váhy
      (váha 2 sa zobrazí dvakrát častejšie než 1).</p>`);
  const form = telo.querySelector('#rk-form');
  const nahlad = () => {
    const u = form.elements.obrazok.value.trim();
    telo.querySelector('#rk-nahlad').innerHTML = /^https:\/\//.test(u) ? `<img src="${esc(u)}" alt="">` : '';
  };
  form.addEventListener('input', nahlad);
  nahlad();
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const v = n => form.elements[n].value.trim();
    if (!/^https:\/\//i.test(v('obrazok')) || !/^https:\/\//i.test(v('url'))) { window.toast('Obrázok aj odkaz musia začínať https://', 'chyba'); return; }
    const novyB = { id: b.id, nazov: v('nazov'), miesto: v('miesto'), obrazok: v('obrazok'), url: v('url'), alt: v('alt'),
      od: v('od'), do: v('do'), vaha: Math.min(10, Math.max(1, Number(v('vaha')) || 1)), zap: form.elements.zap.checked };
    rek.bannery = novy ? [...rek.bannery, novyB] : rek.bannery.map(x => x.id === b.id ? novyB : x);
    await ulozReklamy(`${novy ? 'Pridaný' : 'Upravený'} banner ${novyB.nazov}`);
    U.zavriOkno();
    ulozene();
  });
}
U.stranka('reklamy', {
  obnov: ['hk:clicks'],
  async init(el) {
    el.innerHTML = `<div id="rk-info"></div><div class="tl-rad" style="margin-bottom:14px">
        <button class="btn btn-save" id="rk-novy"><svg class="ix"><use href="#ix-plus"></use></svg> Pridať banner</button></div>
      <div class="rk-zoznam" id="rk-zoznam"></div>
      <p class="settings-hint">Reklamné bannery na stránke sa vždy označia „Reklama“ a majú rel="sponsored". Zmeny sa prejavia hneď
        pri ďalšom otvorení stránky. Kliky sa počítajú pri každom banneri zvlášť.</p>`;
    const s = await fs.getDoc(U.ref('settings', 'reklamy'));
    rek.bannery = s.exists() && Array.isArray(s.data().bannery) ? s.data().bannery : null;
    try {
      const dni = await U.dni('kliky_den', U.isoPosun(U.dnesIso(), -29), U.dnesIso());
      Object.values(dni).forEach(den => Object.entries(den).forEach(([k, v]) => {
        if (k.startsWith('reklama-')) rek.kliky30[k.slice(8)] = (rek.kliky30[k.slice(8)] || 0) + (Number(v) || 0);
      }));
    } catch (e) { /* zatiaľ bez denných dát */ }
    el.querySelector('#rk-novy').addEventListener('click', () => {
      if (!rek.bannery) rek.bannery = [];
      formularReklamy(null, () => this.show(el));
    });
    el.addEventListener('click', async e => {
      const b = e.target.closest('[data-rk]');
      if (!b) return;
      const id = b.dataset.id, akcia = b.dataset.rk;
      if (akcia === 'prevziat') {
        rek.bannery = [SLEDOVANIE_TV];
        await ulozReklamy('Prevzatý banner SledovanieTV');
        window.toast('Banner prevzatý – teraz ho spravuješ tu.');
      } else if (akcia === 'uprav') {
        formularReklamy(rek.bannery.find(x => x.id === id), () => this.show(el));
        return;
      } else if (akcia === 'zap') {
        rek.bannery = rek.bannery.map(x => x.id === id ? { ...x, zap: b.checked } : x);
        await ulozReklamy(`Banner ${id} ${b.checked ? 'zapnutý' : 'vypnutý'}`);
      } else if (akcia === 'zmaz') {
        if (!await window.potvrd('Odstrániť tento banner zo stránky?')) return;
        rek.bannery = rek.bannery.filter(x => x.id !== id);
        await ulozReklamy(`Odstránený banner ${id}`);
      }
      this.show(el);
    });
  },
  show(el) {
    if (!rek.bannery) {
      el.querySelector('#rk-info').innerHTML = `<div class="hlaska info">Na stránke je zatiaľ banner SledovanieTV napísaný priamo v kóde.
        Prevezmi ho sem, aby si ho mohol vypnúť, meniť a pridávať ďalšie.
        <button class="btn btn-save" data-rk="prevziat" style="margin-left:8px">Prevziať aktuálny banner</button></div>`;
      el.querySelector('#rk-zoznam').innerHTML = '';
      return;
    }
    el.querySelector('#rk-info').innerHTML = '';
    const dnes = U.dnesIso();
    el.querySelector('#rk-zoznam').innerHTML = rek.bannery.length ? rek.bannery.map(b => {
      const aktivny = b.zap && (!b.od || b.od <= dnes) && (!b.do || b.do >= dnes);
      return `<div class="rk-karta${aktivny ? '' : ' vyp'}">
        <div class="rk-obr">${/^https:/.test(b.obrazok) ? `<img src="${esc(b.obrazok)}" alt="" loading="lazy">` : ''}</div>
        <div class="rk-info"><b>${esc(b.nazov)}</b>
          <small>${esc(MIESTA[b.miesto] || b.miesto)}${b.od || b.do ? ` · ${esc(b.od || '…')} – ${esc(b.do || '…')}` : ''} · váha ${b.vaha || 1}</small>
          <span class="badge ${aktivny ? 'badge-approved' : 'badge-archived'}">${aktivny ? 'Zobrazuje sa' : (b.zap ? 'Mimo obdobia' : 'Vypnutý')}</span>
          <div class="rk-cisla"><span><b>${HK().clicks['reklama-' + b.id] || 0}</b> klikov spolu</span><span><b>${rek.kliky30[b.id] || 0}</b> za 30 dní</span></div></div>
        <div class="rk-akcie">
          <label class="switch" title="Zapnúť / vypnúť"><input type="checkbox" data-rk="zap" data-id="${esc(b.id)}"${b.zap ? ' checked' : ''}><span class="slider"></span></label>
          <button class="btn btn-ic" data-rk="uprav" data-id="${esc(b.id)}" title="Upraviť"><svg class="ix"><use href="#ix-pencil"></use></svg></button>
          <button class="btn btn-ic btn-delete" data-rk="zmaz" data-id="${esc(b.id)}" title="Odstrániť"><svg class="ix"><use href="#ix-trash"></use></svg></button></div>
      </div>`;
    }).join('') : '<p class="vis-empty">Žiadne bannery – reklamné miesta na stránke sú prázdne a skryté.</p>';
  },
});

// ═══════════════════════════════════════════════════════════════════
// Príjmy
// ═══════════════════════════════════════════════════════════════════
const prij = { data: {} };
U.stranka('prijmy', {
  async init(el) {
    el.innerHTML = `<div class="kpi-row" id="pj-kpi"></div>
      <div class="karta"><h3 class="karta-nadpis">Posledných 12 mesiacov</h3><div id="pj-graf"></div></div>
      <div class="karta"><h3 class="karta-nadpis">Po mesiacoch</h3>
        <p class="settings-hint">Affiliate sa počíta z importovaných provízií (sekcia Provízie). AdSense a iné príjmy dopíš ručne –
          AdSense → Prehľady → Mesačne. Ukladá sa hneď po zmene.</p>
        <div class="tab-wrap"><table class="tab"><thead><tr><th>Mesiac</th><th class="n">Affiliate schválené</th><th class="n">Affiliate čakajúce</th>
          <th class="n">AdSense (€)</th><th class="n">Iné (€)</th><th class="n">Spolu</th></tr></thead><tbody id="pj-telo"></tbody></table></div></div>`;
    const s = await fs.getDoc(U.ref('financie', 'prijmy'));
    prij.data = (s.exists() && s.data().mesiace) || {};
    el.addEventListener('change', async e => {
      const i = e.target.closest('[data-pj]');
      if (!i) return;
      const m = i.dataset.m, k = i.dataset.pj, v = Math.max(0, Math.round((Number(i.value.replace(',', '.')) || 0) * 100) / 100);
      prij.data[m] = { ...(prij.data[m] || {}), [k]: v };
      try {
        await fs.setDoc(U.ref('financie', 'prijmy'), { mesiace: { [m]: { [k]: v } } }, { merge: true });
        window.toast('Uložené.');
        this.show(el);
      } catch (err) { window.toast('Nepodarilo sa uložiť: ' + err.message, 'chyba'); }
    });
  },
  async show(el) {
    const pv = await nacitajProvizie();
    const mesiace = [];
    const d = new Date();
    for (let i = 11; i >= 0; i--) { const x = new Date(d.getFullYear(), d.getMonth() - i, 1); mesiace.push(`${x.getFullYear()}-${U.pad(x.getMonth() + 1)}`); }
    const aff = (m, s) => pv.filter(p => p.stav === s && p.datum.startsWith(m)).reduce((a, p) => a + p.suma, 0);
    const riadky = mesiace.map(m => {
      const r = { m, sch: aff(m, 'schvalena'), cak: aff(m, 'caka'), ads: Number((prij.data[m] || {}).adsense) || 0, ine: Number((prij.data[m] || {}).ine) || 0 };
      r.spolu = r.sch + r.cak + r.ads + r.ine;
      return r;
    });
    const teraz = riadky[11], minuly = riadky[10], rok = riadky.reduce((a, r) => a + r.spolu, 0);
    el.querySelector('#pj-kpi').innerHTML =
      U.kpi('Tento mesiac', U.eur(teraz.spolu), U.zmena(teraz.spolu, minuly.spolu)) +
      U.kpi('Minulý mesiac', U.eur(minuly.spolu)) +
      U.kpi('Posledných 12 mesiacov', U.eur(rok)) +
      U.kpi('Priemer na mesiac', U.eur(rok / 12));
    el.querySelector('#pj-graf').innerHTML = U.stlpce(mesiace.map(U.mesiac), [
      { n: 'Affiliate schválené', farba: '#1E7A3A', hodnoty: riadky.map(r => r.sch) },
      { n: 'Affiliate čakajúce', farba: '#9BD3AE', hodnoty: riadky.map(r => r.cak) },
      { n: 'AdSense', farba: '#1A56C4', hodnoty: riadky.map(r => r.ads) },
      { n: 'Iné', farba: '#E8590C', hodnoty: riadky.map(r => r.ine) },
    ], { format: v => U.eur(v) });
    el.querySelector('#pj-telo').innerHTML = riadky.slice().reverse().map(r => `<tr>
        <td>${U.mesiac(r.m)}</td><td class="n">${U.eur(r.sch)}</td><td class="n">${U.eur(r.cak)}</td>
        <td class="n"><input class="pj-in" data-pj="adsense" data-m="${r.m}" inputmode="decimal" value="${r.ads ? String(r.ads).replace('.', ',') : ''}" placeholder="0"></td>
        <td class="n"><input class="pj-in" data-pj="ine" data-m="${r.m}" inputmode="decimal" value="${r.ine ? String(r.ine).replace('.', ',') : ''}" placeholder="0"></td>
        <td class="n"><b>${U.eur(r.spolu)}</b></td></tr>`).join('');
  },
});


// ═══════════════════════════════════════════════════════════════════
// eHUB - prehľad partnerského účtu (dáta dopĺňa plánovač do admin_info/ehub)
// ═══════════════════════════════════════════════════════════════════
const EH_STAV = { approved: 'Schválená', pending: 'Čaká na schválenie', declined: 'Zamietnutá', available: 'Dostupná' };
const EH_TX = { approved: 'Schválená', pending: 'Čaká', declined: 'Zamietnutá' };
const ehEur = n => (Number(n) || 0).toLocaleString('sk-SK', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
const ehKc = n => Math.round(Number(n) || 0).toLocaleString('sk-SK') + ' Kč';
// Hlavná suma v EUR a pôvodná v Kč (eHUB účtuje v českých korunách).
const ehSuma = (eur, czk) => `${ehEur(eur)} <small class="eh-kc">(${ehKc(czk)})</small>`;

U.stranka('ehub', {
  async init(el) {
    el.innerHTML = `
      <div id="eh-chyba"></div>
      <div class="karta">
        <div class="riadok-pole"><h3 class="karta-nadpis" style="flex:1;margin:0">Prehľad eHUB</h3>
          <span class="settings-hint" id="eh-cas" style="margin:0"></span>
          <button class="btn" id="eh-obnov"><svg class="ix"><use href="#ix-refresh"></use></svg> Obnoviť teraz</button></div>
        <div class="kpi-row" id="eh-kpi"></div>
        <p class="settings-hint" id="eh-kurz"></p>
        <p class="settings-hint">Údaje sťahuje plánovač z eHUB raz za hodinu (provízie sa v sieti potvrdzujú až po čase, kým inzerent
          objednávku neschváli).</p>
      </div>
      <div class="karta">
        <div class="riadok-pole"><h3 class="karta-nadpis" style="flex:1;margin:0">Kampane</h3>
          <select id="eh-stav"><option value="approved">Schválené</option><option value="pending">Čakajúce</option>
            <option value="declined">Zamietnuté</option><option value="available">Dostupné (neprihlásené)</option></select>
          <input type="search" id="eh-hladaj" placeholder="hľadať kampaň…" style="max-width:220px"></div>
        <div class="tab-wrap"><table class="tab"><thead><tr><th>Kampaň</th><th>Krajina</th><th>Kategória</th><th class="n">Provízia</th>
          <th class="n">Cookie (dni)</th><th>Feed</th><th>Stav</th></tr></thead><tbody id="eh-kampane"></tbody></table></div>
        <p class="settings-hint" id="eh-kampane-pozn"></p>
      </div>
      <div class="karta"><h3 class="karta-nadpis">Provízie podľa kampane</h3>
        <div class="tab-wrap"><table class="tab"><thead><tr><th>Kampaň</th><th class="n">Transakcií</th><th class="n">Tržby</th><th class="n">Provízia</th></tr></thead>
          <tbody id="eh-podla"></tbody></table></div>
        <div class="tab-wrap" style="margin-top:12px"><table class="tab"><thead><tr><th>Mesiac</th><th class="n">Provízia (bez zamietnutých)</th></tr></thead>
          <tbody id="eh-mesiace"></tbody></table></div></div>
      <div class="karta"><h3 class="karta-nadpis">Posledné transakcie</h3>
        <div class="tab-wrap"><table class="tab"><thead><tr><th>Dátum</th><th>Kampaň</th><th>Objednávka</th><th class="n">Suma</th><th class="n">Provízia</th>
          <th>Stav</th><th>Výplata</th></tr></thead><tbody id="eh-tx"></tbody></table></div></div>
      <div class="karta"><h3 class="karta-nadpis">Prekliky za 30 dní</h3>
        <div class="tab-wrap"><table class="tab"><thead><tr><th>Kampaň</th><th class="n">Preklikov</th></tr></thead><tbody id="eh-kliky"></tbody></table></div>
        <p class="settings-hint">Počítajú sa len prekliky cez eHUB odkazy. Kým nemáme eHUB odkazy na stránke, tu bude 0.</p></div>
      <div class="karta"><h3 class="karta-nadpis">Pripojenie</h3>
        <p class="settings-hint">API kľúč nájdeš v eHUB: <b>API → API kľúč</b>. Ukladá sa len do databázy v admin zóne, nie do kódu.
          Ak kľúč niekomu ukážeš, v eHUB ho môžeš „Pregenerovať“ a sem vložiť nový.</p>
        <div class="riadok-pole"><input type="password" id="eh-kluc" placeholder="API kľúč" autocomplete="off">
          <input type="text" id="eh-partner" placeholder="ID partnera" style="max-width:150px">
          <button class="btn btn-save" id="eh-uloz"><svg class="ix"><use href="#ix-save"></use></svg> Uložiť</button></div>
        <div class="settings-hint" id="eh-pripojenie"></div></div>`;
    el.querySelector('#eh-stav').addEventListener('change', () => this._kampane(el));
    el.querySelector('#eh-hladaj').addEventListener('input', () => this._kampane(el));
    el.querySelector('#eh-obnov').addEventListener('click', e => U.akcia(e.currentTarget, async () => {
      try {
        const v = await U.uloha('ehub_obnov', {}, (x, ms) => { el.querySelector('#eh-cas').textContent = U.textCakania(x, ms); });
        window.toast(`Obnovené: ${v.kampani} kampaní, ${v.transakcii} transakcií.`);
      } catch (err) { window.toast(err.message, 'chyba'); }
      await this.show(el);
    }));
    el.querySelector('#eh-uloz').addEventListener('click', e => U.akcia(e.currentTarget, async () => {
      const kluc = el.querySelector('#eh-kluc').value.trim();
      const partner = el.querySelector('#eh-partner').value.trim();
      const d = { upravene: fs.serverTimestamp() };
      if (kluc) d.apiKey = kluc;
      if (partner) d.publisherId = partner;
      if (!kluc && !partner) { window.toast('Vlož API kľúč alebo ID partnera.', 'chyba'); return; }
      await fs.setDoc(U.ref('nastavenia_admin', 'ehub'), d, { merge: true });
      HK().logChange('ehub', 'ehub', 'eHUB: zmenené pripojenie');
      el.querySelector('#eh-kluc').value = '';
      window.toast('Uložené. Klikni na „Obnoviť teraz“.');
      await this.show(el);
    }));
  },
  async show(el) {
    const [d, n] = await Promise.all([fs.getDoc(U.ref('admin_info', 'ehub')).catch(() => null),
      fs.getDoc(U.ref('nastavenia_admin', 'ehub')).catch(() => null)]);
    const nast = n && n.exists() ? n.data() : {};
    const kluc = nast.apiKey || '';
    el.querySelector('#eh-pripojenie').textContent = kluc
      ? `API kľúč je uložený (…${kluc.slice(-4)}), ID partnera ${nast.publisherId || '0506c0ea'}.`
      : 'API kľúč zatiaľ nie je uložený - bez neho sa nič nestiahne.';
    if (nast.publisherId) el.querySelector('#eh-partner').placeholder = nast.publisherId;
    this._d = d && d.exists() ? d.data() : null;
    const x = this._d;
    el.querySelector('#eh-chyba').innerHTML = x && x.chyba
      ? `<div class="hlaska chyba">Posledné obnovenie zlyhalo: ${esc(x.chyba)}</div>` : '';
    el.querySelector('#eh-cas').textContent = x && x.aktualizovane ? `Naposledy: ${U.pred(x.aktualizovane)}` : '';
    if (!x || !x.kampane) {
      el.querySelector('#eh-kpi').innerHTML = '<p class="vis-empty">Zatiaľ žiadne dáta. Ulož API kľúč dole a klikni na „Obnoviť teraz“.</p>';
      return;
    }
    const st = x.kampaniPodlaStavu || {}, tx = x.transakcie || {}, sv = tx.stavy || {};
    const schv = (sv.approved || {}).provizia || 0, cak = (sv.pending || {}).provizia || 0;
    const schvKc = (sv.approved || {}).proviziaCzk || 0, cakKc = (sv.pending || {}).proviziaCzk || 0;
    const bezZam = Object.entries(sv).filter(([k]) => k !== 'declined').map(([, v]) => v);
    const trzbyEur = bezZam.reduce((s, v) => s + (v.trzby || 0), 0), trzbyKc = bezZam.reduce((s, v) => s + (v.trzbyCzk || 0), 0);
    el.querySelector('#eh-kurz').textContent = x.kurz ? `Sumy v eHUB sú v Kč, prepočítané na € kurzom ECB z ${x.kurzDen || ''}: 1 € = ${String(x.kurz).replace('.', ',')} Kč.` : '';
    el.querySelector('#eh-kpi').innerHTML =
      U.kpi('Schválené kampane', U.cislo(st.approved || 0), '', `${st.pending || 0} čaká · ${st.declined || 0} zamietnutých`) +
      U.kpi('Provízia schválená', ehEur(schv), '', `${ehKc(schvKc)} · vyplatené ${ehEur(tx.vyplatene)} · čaká na výplatu ${ehEur(tx.schvaleneNevyplatene)}`) +
      U.kpi('Provízia čakajúca', ehEur(cak), '', `${ehKc(cakKc)} · ${(sv.pending || {}).pocet || 0} transakcií`) +
      U.kpi('Tržby inzerentov', ehEur(trzbyEur), '', `${ehKc(trzbyKc)} · bez zamietnutých`) +
      U.kpi('Prekliky (30 dní)', U.cislo((x.kliky || {}).spolu || 0), '', 'cez eHUB odkazy');
    this._kampane(el);
    el.querySelector('#eh-podla').innerHTML = (tx.kampane || []).map(k =>
      `<tr><td>${esc(k.nazov)}</td><td class="n">${k.pocet}</td><td class="n">${ehSuma(k.trzby, k.trzbyCzk)}</td><td class="n"><b>${ehSuma(k.provizia, k.proviziaCzk)}</b></td></tr>`).join('')
      || '<tr><td colspan="4" class="vis-empty">Zatiaľ žiadne transakcie.</td></tr>';
    el.querySelector('#eh-mesiace').innerHTML = Object.entries(tx.mesiace || {}).reverse().map(([m, v]) =>
      `<tr><td>${esc(m)}</td><td class="n">${ehSuma(v.eur, v.czk)}</td></tr>`).join('') || '<tr><td colspan="2" class="vis-empty">–</td></tr>';
    el.querySelector('#eh-tx').innerHTML = (tx.posledne || []).slice(0, 50).map(t =>
      `<tr><td>${esc(t.datum)}</td><td>${esc(t.kampan)}</td><td>${esc(t.objednavka || '–')}</td><td class="n">${ehSuma(t.suma, t.sumaCzk)}</td>
        <td class="n">${ehSuma(t.provizia, t.proviziaCzk)}</td><td>${esc(EH_TX[t.stav] || t.stav || '')}</td><td>${t.vyplata === 'paid' ? 'vyplatené' : 'nevyplatené'}</td></tr>`).join('')
      || '<tr><td colspan="7" class="vis-empty">Zatiaľ žiadne transakcie.</td></tr>';
    el.querySelector('#eh-kliky').innerHTML = ((x.kliky || {}).poKampani || []).map(k =>
      `<tr><td>${esc(k.nazov)}</td><td class="n">${k.pocet}</td></tr>`).join('') || '<tr><td colspan="2" class="vis-empty">Zatiaľ žiadne prekliky.</td></tr>';
  },
  _kampane(el) {
    const x = this._d;
    if (!x || !x.kampane) return;
    const stav = el.querySelector('#eh-stav').value, q = U.norm(el.querySelector('#eh-hladaj').value);
    const zoz = x.kampane.filter(k => k.stav === stav && (!q || U.norm(k.nazov || '').includes(q)));
    el.querySelector('#eh-kampane').innerHTML = zoz.slice(0, 120).map(k =>
      `<tr><td>${k.web ? `<a href="${esc(k.web)}" target="_blank" rel="noopener">${esc(k.nazov)}</a>` : esc(k.nazov)}</td><td>${esc(k.krajina || '')}</td>
        <td>${esc(k.kategoria || '')}</td><td class="n">${k.provizia != null ? esc(k.provizia + ' ' + k.jednotka) : '–'}</td>
        <td class="n">${k.cookie != null ? esc(k.cookie) : '–'}</td><td>${k.feed ? 'áno' : '–'}</td><td>${esc(EH_STAV[k.stav] || k.stav)}</td></tr>`).join('')
      || '<tr><td colspan="7" class="vis-empty">Nič nenájdené.</td></tr>';
    el.querySelector('#eh-kampane-pozn').textContent = zoz.length > 120 ? `Zobrazených prvých 120 z ${zoz.length}. Zúž hľadanie.` : `${zoz.length} kampaní.`;
  },
});
