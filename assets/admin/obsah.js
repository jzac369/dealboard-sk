// ── Obsah: pridanie z odkazu, kalendár, kontrola platnosti, fotky ────
const U = window.HKU, HK = () => window.HK, { fs, esc } = U;
const KATEGORIE = ['Elektronika', 'Dom & Záhrada', 'Móda', 'Hračky', 'Šport', 'Jedlo & Nápoje', 'Cestovanie', 'Iné'];

// Z odkazu odstránime sledovacie parametre (utm, fbclid…) - deal má
// viesť na čistú adresu, affiliate obal pridáva stránka sama.
function cistaUrl(u) {
  try {
    const x = new URL(u.trim());
    [...x.searchParams.keys()].forEach(k => {
      if (/^(utm_|fbclid|gclid|gbraid|wbraid|mc_|_ga|ref$|srsltid)/i.test(k)) x.searchParams.delete(k);
    });
    x.hash = '';
    return x.toString();
  } catch (e) { return u.trim(); }
}

// ═══════════════════════════════════════════════════════════════════
// Pridať deal z odkazu
// ═══════════════════════════════════════════════════════════════════
U.stranka('pridat', {
  init(el) {
    el.innerHTML = `
      <div class="karta">
        <label class="pole-lab" for="pr-url">Adresa produktu v e-shope</label>
        <div class="riadok-pole">
          <input type="url" id="pr-url" placeholder="https://www.alza.sk/…" autocomplete="off">
          <button class="btn btn-save" id="pr-nacitaj" type="button"><svg class="ix"><use href="#ix-download"></use></svg> Načítať údaje</button>
        </div>
        <p class="settings-hint">Stránku otvorí plánovač (z prehliadača sa do cudzieho e-shopu pozrieť nedá) a vytiahne z nej názov,
          cenu, fotku a popis. Niektoré e-shopy automatické čítanie nedovolia – vtedy údaje doplň ručne nižšie.</p>
        <div id="pr-stav"></div>
      </div>
      <div class="pr-mriezka">
        <form class="karta" id="pr-form" autocomplete="off">
          <div class="form-mriezka">
            <label class="cela">Názov<input type="text" name="title" maxlength="199" required></label>
            <label>Obchod<input type="text" name="store" maxlength="60" required></label>
            <label>Kategória<select name="category">${KATEGORIE.map(k => `<option>${esc(k)}</option>`).join('')}</select></label>
            <label>Cena teraz (€)<input name="dealPrice" type="number" step="0.01" min="0"></label>
            <label>Pôvodná cena (€)<input name="originalPrice" type="number" step="0.01" min="0"></label>
            <label class="cela">Odkaz na produkt<input name="url" type="url" required></label>
            <label class="cela">Fotka (adresa obrázka)<input name="imageUrl" type="url" placeholder="https://…"></label>
            <label class="cela">Popis<textarea name="description" rows="3" maxlength="2000"></textarea></label>
            <label>Platí do (nepovinné)<input name="validUntilISO" type="date"></label>
            <label class="zaskrt"><input name="zadarmo" type="checkbox"> Zadarmo</label>
          </div>
          <div id="pr-dup"></div>
          <div id="pr-kvalita"></div>
          <fieldset class="pr-stav-vyber">
            <legend>Čo s dealom</legend>
            <label><input type="radio" name="kam" value="pending" checked> Na schválenie</label>
            <label><input type="radio" name="kam" value="approved"> Zverejniť hneď</label>
            <label><input type="radio" name="kam" value="planned"> Zverejniť neskôr
              <input type="datetime-local" name="publishAt"></label>
          </fieldset>
          <div class="tl-rad">
            <button class="btn btn-save" type="submit"><svg class="ix"><use href="#ix-save"></use></svg> Uložiť deal</button>
            <button class="btn" type="reset">Vymazať formulár</button>
          </div>
        </form>
        <div class="karta pr-nahlad"><div class="pole-lab">Náhľad karty</div><div id="pr-karta"></div></div>
      </div>`;
    const form = el.querySelector('#pr-form');
    const f = n => form.elements[n];
    const draft = () => ({
      title: f('title').value.trim(), store: f('store').value.trim(), category: f('category').value,
      dealPrice: Number(f('dealPrice').value) || 0, originalPrice: Number(f('originalPrice').value) || null,
      url: cistaUrl(f('url').value), imageUrl: f('imageUrl').value.trim() || null,
      description: f('description').value.trim(), validUntilISO: f('validUntilISO').value || null,
      zadarmo: f('zadarmo').checked, status: 'pending', id: '__novy__',
    });
    const obnov = () => {
      const d = draft();
      const zlava = d.originalPrice > d.dealPrice && d.dealPrice > 0 ? Math.round((1 - d.dealPrice / d.originalPrice) * 100) : 0;
      el.querySelector('#pr-karta').innerHTML = `<div class="pv-card">
          ${d.imageUrl ? `<img class="pv-img" src="${esc(d.imageUrl)}" alt="">` : '<div class="pv-img-empty"><svg class="ix"><use href="#ix-archive"></use></svg></div>'}
          <div class="pv-body"><div class="pv-store">${esc(d.store || 'obchod')}</div>
            <div class="pv-title">${esc(d.title || '(názov dealu)')}</div>
            <div class="pv-prices"><span class="pv-now">${d.zadarmo ? 'Zadarmo' : U.eur(d.dealPrice)}</span>
              ${d.originalPrice > d.dealPrice ? `<span class="pv-was">${U.eur(d.originalPrice)}</span>` : ''}
              ${zlava ? `<span class="pv-off">−${zlava} %</span>` : ''}</div></div></div>`;
      const kv = HK().kontrolaKvality(d).filter(x => x[1] !== 'Možná duplicita');
      el.querySelector('#pr-kvalita').innerHTML = kv.length
        ? `<div class="kv">${kv.map(([t, x]) => `<span class="kv-${t}">${esc(x)}</span>`).join('')}</div>` : '';
      // duplicita: rovnaká adresa alebo takmer rovnaký názov
      const host = U.host(d.url), slova = new Set(U.norm(d.title).split(/[^a-z0-9]+/).filter(w => w.length > 3));
      const dup = d.url && HK().deals.find(x => ['approved', 'pending', 'planned'].includes(x.status) && (
        cistaUrl(x.url || '') === d.url ||
        (slova.size >= 3 && U.host(x.url) === host && (() => {
          const ich = new Set(U.norm(x.title).split(/[^a-z0-9]+/).filter(w => w.length > 3));
          let sp = 0; slova.forEach(w => { if (ich.has(w)) sp++; });
          return sp / Math.min(slova.size, ich.size || 1) >= 0.8;
        })())));
      el.querySelector('#pr-dup').innerHTML = dup
        ? `<div class="hlaska pozor"><svg class="ix"><use href="#ix-alert"></use></svg> Podobný deal už existuje:
            <a href="#" data-deal="${esc(dup.id)}">${esc(dup.title)}</a> (${esc(dup.status)})</div>` : '';
    };
    form.addEventListener('input', obnov);
    form.addEventListener('reset', () => setTimeout(obnov, 0));
    el.addEventListener('click', e => {
      const a = e.target.closest('[data-deal]');
      if (a) { e.preventDefault(); HK().otvorDeal(a.dataset.deal); }
    });
    obnov();

    // Načítanie cez plánovač
    el.querySelector('#pr-nacitaj').addEventListener('click', async (e) => {
      const url = el.querySelector('#pr-url').value.trim();
      if (!/^https?:\/\//i.test(url)) { window.toast('Vlož celú adresu začínajúcu https://', 'chyba'); return; }
      const stav = el.querySelector('#pr-stav');
      f('url').value = cistaUrl(url);
      await U.akcia(e.currentTarget, async () => {
        stav.innerHTML = `<div class="hlaska info"><span class="tocka"></span> ${esc(U.textCakania('caka', 0))}</div>`;
        try {
          const v = await U.uloha('nacitaj_url', { url }, (st, ms) => {
            stav.innerHTML = `<div class="hlaska info"><span class="tocka"></span> ${esc(U.textCakania(st, ms))}</div>`;
          });
          if (v.title) f('title').value = v.title;
          if (v.store) f('store').value = v.store;
          if (v.dealPrice) f('dealPrice').value = v.dealPrice;
          if (v.originalPrice) f('originalPrice').value = v.originalPrice;
          if (v.imageUrl) f('imageUrl').value = v.imageUrl;
          if (v.description) f('description').value = v.description;
          if (v.url) f('url').value = cistaUrl(v.url);
          const chyba = [!v.title && 'názov', !v.dealPrice && 'cenu', !v.imageUrl && 'fotku'].filter(Boolean);
          stav.innerHTML = `<div class="hlaska ${chyba.length ? 'pozor' : 'ok'}">${chyba.length
            ? `Načítané, ale chýba ${chyba.join(', ')} – doplň ručne.${v.originalPrice ? '' : ' Pôvodnú cenu stránka neuvádza.'}`
            : (v.originalPrice ? 'Údaje načítané aj s pôvodnou cenou. Doplň kategóriu a skontroluj zvyšok.'
              : 'Údaje načítané. Stránka pôvodnú cenu neuvádza - doplň ju a kategóriu a skontroluj zvyšok.')}${v.vypredane ? ' <b>Pozor: e-shop hlási, že produkt nie je skladom.</b>' : ''}</div>`;
          obnov();
        } catch (err) {
          stav.innerHTML = `<div class="hlaska chyba">${esc(err.message)}</div>`;
        }
      });
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const d = draft();
      if (!d.title || !d.store || !/^https?:\/\//i.test(d.url)) { window.toast('Vyplň názov, obchod a odkaz.', 'chyba'); return; }
      const kam = form.querySelector('[name=kam]:checked').value;
      let publishAt = null;
      if (kam === 'planned') {
        publishAt = new Date(f('publishAt').value);
        if (isNaN(publishAt) || publishAt.getTime() < Date.now() + 60000) { window.toast('Čas zverejnenia musí byť v budúcnosti.', 'chyba'); return; }
      }
      const chyby = HK().kontrolaKvality(d).filter(x => x[0] === 'chyba' && x[1] !== 'Možná duplicita').map(x => x[1]);
      if (chyby.length && !await window.potvrd(`Kontrola kvality: ${chyby.join(', ')}. Napriek tomu uložiť?`)) return;
      const zaznam = {
        title: d.title, store: d.store, category: d.category, url: d.url, imageUrl: d.imageUrl,
        description: d.description, dealPrice: d.dealPrice, originalPrice: d.originalPrice,
        discountPercent: d.originalPrice > d.dealPrice && d.dealPrice > 0 ? Math.round((1 - d.dealPrice / d.originalPrice) * 100) : 0,
        currency: '€', status: kam, votes: 0, comments: 0, author: 'HenKukaj',
        addedBy: HK().email, timestamp: fs.serverTimestamp(),
      };
      if (d.validUntilISO) zaznam.validUntilISO = d.validUntilISO;
      if (d.zadarmo) zaznam.zadarmo = true;
      if (publishAt) zaznam.publishAt = publishAt;
      await U.akcia(form.querySelector('[type=submit]'), async () => {
        const ref = await fs.addDoc(U.kol('deals'), zaznam);
        await HK().logChange(ref.id, 'pridany', d.title);
        window.toast(kam === 'approved' ? 'Deal je zverejnený.' : (kam === 'planned' ? `Deal sa zverejní ${U.casDlhy(publishAt)}.` : 'Deal čaká na schválenie.'));
        form.reset();
        el.querySelector('#pr-url').value = '';
        el.querySelector('#pr-stav').innerHTML = `<div class="hlaska ok">Uložené. <a href="#" data-deal="${ref.id}">Otvoriť v zozname dealov</a></div>`;
      });
    });
  },
});

// ═══════════════════════════════════════════════════════════════════
// Kalendár naplánovaného obsahu
// ═══════════════════════════════════════════════════════════════════
const kal = { mesiac: (() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); })(), fb: [], prip: [], el: null };

// Automatické úlohy. Časy sú z Plánovača úloh (settings/schedule); keď
// v ňom úloha časy nemá, platia predvolené z planovac.py.
const PREDVOLENE_CASY = {
  agent: ['07:30', '12:30', '18:30'], letenky: ['07:30'], ziar: ['06:10'],
  facebook: ['09:00', '17:00'], mapa: ['05:30'], potraviny: ['07:15', '13:00'],
};
// Úlohy s pevným rozvrhom priamo v GitHube (nemenia sa v admine).
const PEVNE_ULOHY = [
  { id: 'stranky', nazov: 'Generovanie stránok dealov a sitemap', popis: 'Každú hodinu (a hneď po naplánovanom zverejnení). Rozvrh je pevne v GitHube.' },
  { id: 'telegram', nazov: 'Schvaľovanie z Telegramu', popis: 'Beží nepretržite – každú hodinu sa reťaz obnoví. Rozvrh je pevne v GitHube.' },
];
// Filtre: k = kľúč, n = názov, t = trieda farby.
function kalFiltre() {
  const ulohy = (HK().planUlohy || []).map(u => ({ k: 'u-' + u.id, n: u.nazov, t: 'k-sys', skupina: 'auto' }));
  return [
    { k: 'zver', n: 'Zverejnenie dealov', t: 'k-zver', skupina: 'obsah' },
    { k: 'schv', n: 'Poslanie na schválenie', t: 'k-schv', skupina: 'obsah' },
    { k: 'fb', n: 'Príspevky na Facebook', t: 'k-fb', skupina: 'obsah' },
    { k: 'prip', n: 'Pripomienky', t: 'k-prip', skupina: 'obsah' },
    ...ulohy,
    ...PEVNE_ULOHY.map(u => ({ k: 'p-' + u.id, n: u.nazov, t: 'k-sys', skupina: 'auto' })),
  ];
}
const KAL_PREDVOLENE_VYPNUTE = ['p-telegram', 'p-stranky'];
function kalZapnute() {
  let v = null;
  try { v = JSON.parse(localStorage.getItem('adm_kal_filter') || 'null'); } catch (e) {}
  const vsetky = kalFiltre().map(f => f.k);
  const vyp = new Set(v ? v.vypnute : KAL_PREDVOLENE_VYPNUTE);
  return new Set(vsetky.filter(k => !vyp.has(k)));
}
function kalUlozFilter(zapnute) {
  const vyp = kalFiltre().map(f => f.k).filter(k => !zapnute.has(k));
  try { localStorage.setItem('adm_kal_filter', JSON.stringify({ vypnute: vyp })); } catch (e) {}
}

// Opakované úlohy v rozsahu dní (od dnes - minulé behy tu nemajú zmysel).
function kalSystemove(od, doD) {
  const p = [], plan = HK().plan || {}, jobs = plan.jobs || {}, stav = plan.stav || {}, runNow = plan.runNow || {};
  const dnes = new Date(); dnes.setHours(0, 0, 0, 0);
  const zac = new Date(Math.max(od.getTime(), dnes.getTime()));
  for (let d = new Date(zac); d <= doD; d.setDate(d.getDate() + 1)) {
    (HK().planUlohy || []).forEach(u => {
      const j = jobs[u.id] || {};
      if (j.enabled === false) return;
      const casy = Array.isArray(j.times) ? j.times : (PREDVOLENE_CASY[u.id] || []);
      casy.forEach(t => {
        const [h, m] = String(t).split(':').map(Number);
        if (isNaN(h) || isNaN(m)) return;
        const kedy = new Date(d); kedy.setHours(h, m, 0, 0);
        p.push({ druh: 'sys', id: u.id, kluc: 'u-' + u.id, kedy, n: u.nazov, typ: u.lokalne ? 'Automatická úloha (tvoj počítač)' : 'Automatická úloha (cloud)',
          trieda: 'k-sys', pevne: false, popis: u.popis, posledny: stav[u.id] && stav[u.id].lastRun, cakaSpustenie: !!runNow[u.id] });
      });
    });
    PEVNE_ULOHY.forEach(u => {
      const kedy = new Date(d); kedy.setHours(0, 0, 0, 0);
      p.push({ druh: 'sys', id: u.id, kluc: 'p-' + u.id, kedy, n: u.nazov, typ: 'Systémová úloha', trieda: 'k-sys', pevne: true,
        popis: u.popis, celyDen: true });
    });
  }
  return p;
}

function kalPolozky(od, doD) {
  const p = [];
  HK().deals.forEach(d => {
    if (d.status === 'planned' && d.publishAt) p.push({ druh: 'deal', id: d.id, kedy: U.naDatum(d.publishAt), n: d.title, typ: 'Zverejnenie dealu', trieda: 'k-zver' });
    if (d.status === 'scheduled' && d.sendAt) p.push({ druh: 'deal', id: d.id, kedy: U.naDatum(d.sendAt), n: d.title, typ: 'Poslať na schválenie', trieda: 'k-schv' });
  });
  kal.fb.forEach(x => p.push({ druh: 'fb', id: x.id, kedy: U.naDatum(x.sendAt), n: x.title || (x.text || '').slice(0, 60), typ: 'Príspevok na Facebook', trieda: 'k-fb' }));
  kal.prip.forEach(x => p.push({ druh: 'prip', id: x.id, kedy: U.naDatum(x.sendAt), n: x.text, typ: 'Pripomienka do Telegramu', trieda: 'k-prip' }));
  p.forEach(x => { x.kluc = { 'k-zver': 'zver', 'k-schv': 'schv', 'k-fb': 'fb', 'k-prip': 'prip' }[x.trieda]; });
  if (od && doD && HK().rola === 'admin') p.push(...kalSystemove(od, doD));
  const zap = kalZapnute();
  return p.filter(x => x.kedy && zap.has(x.kluc)).sort((a, b) => a.kedy - b.kedy);
}
const denKluc = d => `${d.getFullYear()}-${U.pad(d.getMonth() + 1)}-${U.pad(d.getDate())}`;

function kalKresli() {
  const el = kal.el;
  if (!el) return;
  const m = kal.mesiac, rok = m.getFullYear(), mes = m.getMonth();
  const nazov = m.toLocaleDateString('sk-SK', { month: 'long', year: 'numeric' });
  const zac = new Date(rok, mes, 1);
  zac.setDate(zac.getDate() - ((zac.getDay() + 6) % 7));
  const koniec = new Date(zac); koniec.setDate(zac.getDate() + 41); koniec.setHours(23, 59, 59);
  const polozky = kalPolozky(zac, koniec);
  const dnes = denKluc(new Date());
  const poDnoch = {};
  polozky.forEach(x => (poDnoch[denKluc(x.kedy)] = poDnoch[denKluc(x.kedy)] || []).push(x));
  const chip = x => `<div class="k-chip ${x.trieda}" ${x.druh === 'sys' ? '' : 'draggable="true"'} data-druh="${x.druh}" data-id="${esc(x.id)}" data-kedy="${x.kedy.getTime()}" title="${esc(x.typ + ': ' + x.n)}">
      ${x.druh === 'sys' ? '<svg class="ix"><use href="#ix-settings"></use></svg>' : ''}<b>${x.celyDen ? 'každú h' : U.pad(x.kedy.getHours()) + ':' + U.pad(x.kedy.getMinutes())}</b> ${esc(x.n)}</div>`;
  let bunky = '';
  for (let i = 0; i < 42; i++) {
    const d = new Date(zac); d.setDate(zac.getDate() + i);
    if (i >= 35 && d.getMonth() !== mes) break;
    const k = denKluc(d);
    bunky += `<div class="k-den${d.getMonth() !== mes ? ' iny' : ''}${k === dnes ? ' dnes' : ''}${k < dnes ? ' minule' : ''}" data-den="${k}">
      <div class="k-cislo">${d.getDate()}</div>${(poDnoch[k] || []).map(chip).join('')}</div>`;
  }
  // Zoznam: obsah na celý mesiac dopredu, automatické úlohy len na 2 dni
  // (opakujú sa každý deň a inak by zaplnili celý zoznam).
  const o48 = Date.now() + 48 * 3600000;
  const buduce = kalPolozky(new Date(), new Date(Date.now() + 60 * 86400000))
    .filter(x => x.kedy.getTime() >= Date.now() - (x.celyDen ? 86400000 : 3600000) && (x.druh !== 'sys' || x.kedy.getTime() < o48));
  const zap = kalZapnute();
  const filtre = kalFiltre().filter(f => HK().rola === 'admin' || f.skupina === 'obsah');
  const fChip = f => `<label class="kf-chip kf-${f.t}${zap.has(f.k) ? ' on' : ''}"><input type="checkbox" data-kf="${esc(f.k)}"${zap.has(f.k) ? ' checked' : ''}><i></i>${esc(f.n)}</label>`;
  el.querySelector('#kal-telo').innerHTML = `
    <div class="kal-lista">
      <button class="btn btn-ic" data-kal="-1" aria-label="Predchádzajúci mesiac"><svg class="ix"><use href="#ix-chevl"></use></svg></button>
      <b class="kal-nazov">${esc(nazov)}</b>
      <button class="btn btn-ic" data-kal="1" aria-label="Ďalší mesiac"><svg class="ix"><use href="#ix-chevr"></use></svg></button>
      <button class="btn" data-kal="0">Dnes</button>
      <button class="btn kal-filter-tl" data-kal-filter><svg class="ix"><use href="#ix-settings"></use></svg> Čo zobraziť (${zap.size}/${filtre.length})</button>
    </div>
    <div class="kal-filter"${kal.filterOtvoreny ? '' : ' hidden'}>
      <div class="kf-skupina"><b>Obsah</b>${filtre.filter(f => f.skupina === 'obsah').map(fChip).join('')}</div>
      ${HK().rola === 'admin' ? `<div class="kf-skupina"><b>Automatické a systémové úlohy</b>${filtre.filter(f => f.skupina === 'auto').map(fChip).join('')}</div>` : ''}
      <div class="tl-rad"><button class="btn" data-kf-vsetko="1">Zobraziť všetko</button><button class="btn" data-kf-vsetko="0">Skryť všetko</button>
        ${HK().rola === 'admin' ? '<a class="btn" href="#planovac">Upraviť časy úloh v Plánovači</a>' : ''}</div>
    </div>
    <div class="kal-mriezka"><div class="k-hl">Po</div><div class="k-hl">Ut</div><div class="k-hl">St</div><div class="k-hl">Št</div><div class="k-hl">Pi</div><div class="k-hl">So</div><div class="k-hl">Ne</div>${bunky}</div>
    <div class="kal-zoznam">
      <h3>Najbližšie naplánované</h3>
      ${buduce.length ? buduce.slice(0, 40).map(x => `<div class="kz-r"><span class="kz-cas">${esc(U.casDlhy(x.kedy))}</span>${chip(x)}</div>`).join('')
        : '<p class="vis-empty">Nič nie je naplánované. Deal naplánuješ tlačidlom „Neskôr“ pri schvaľovaní, príspevok v sekcii Facebook.</p>'}
    </div>`;
}

async function kalPresun(druh, id, novy) {
  if (novy.getTime() < Date.now() + 60000) { window.toast('Do minulosti sa presunúť nedá.', 'chyba'); return; }
  try {
    if (druh === 'deal') {
      const d = HK().deals.find(x => x.id === id);
      if (!d) return;
      const pole = d.status === 'scheduled' ? 'sendAt' : 'publishAt';
      await fs.updateDoc(U.ref('deals', id), { [pole]: novy });
      await HK().logChange(id, 'planned', `${d.title || ''} — presunuté na ${U.casDlhy(novy)}`);
    } else if (druh === 'fb') {
      await fs.updateDoc(U.ref('fb_posty', id), { sendAt: novy, spustene: null });
    } else {
      await fs.updateDoc(U.ref('pripomienky', id), { sendAt: novy });
    }
    window.toast(`Presunuté na ${U.casDlhy(novy)}.`);
  } catch (e) { window.toast('Presun sa nepodaril: ' + e.message, 'chyba'); }
}

function kalDetailSys(x) {
  const telo = U.okno(x.typ, `
    <p class="okno-nazov">${esc(x.n)}</p>
    <p class="settings-hint">${esc(x.popis || '')}</p>
    <p class="settings-hint" style="margin-top:8px">${x.celyDen ? 'Beží každú hodinu.' : `Naplánované: <b>${esc(U.casDlhy(x.kedy))}</b> (beh začne do 5 minút od tohto času).`}
      ${x.posledny ? `<br>Naposledy prebehla ${esc(U.casDlhy(x.posledny))}.` : ''}${x.cakaSpustenie ? '<br><b>Čaká na ručné spustenie.</b>' : ''}</p>
    <div class="tl-rad" style="margin-top:14px">
      ${x.pevne ? '<a class="btn" href="#zdravie">Stav behov v Zdraví systému</a>'
        : `<button class="btn btn-save" id="ks-spust"${x.cakaSpustenie ? ' disabled' : ''}><svg class="ix"><use href="#ix-play"></use></svg> Spustiť teraz</button>
           <a class="btn" href="#planovac">Zmeniť časy v Plánovači</a>`}
      <button class="btn" data-zavriet>Zavrieť</button></div>`);
  const b = telo.querySelector('#ks-spust');
  if (b) b.onclick = async () => { await window.runJobNow(x.id); window.toast('Úloha sa spustí do 5 minút.'); U.zavriOkno(); };
  telo.querySelectorAll('a[href^="#"]').forEach(a => a.addEventListener('click', () => U.zavriOkno()));
}

function kalDetail(druh, id, kedy) {
  if (druh === 'sys') {
    const d = new Date(Number(kedy)); const od = new Date(d); od.setHours(0, 0, 0, 0); const doD = new Date(d); doD.setHours(23, 59, 59);
    const x = kalSystemove(od, doD).find(p => p.id === id && Math.abs(p.kedy - d) < 60000);
    if (x) kalDetailSys(x);
    return;
  }
  const x = kalPolozky().find(p => p.druh === druh && p.id === id);
  if (!x) return;
  const telo = U.okno(x.typ, `
    <p class="okno-nazov">${esc(x.n)}</p>
    <label class="pole-lab">Čas</label>
    <div class="riadok-pole"><input type="datetime-local" id="kd-cas" value="${U.doInputu(x.kedy)}"><button class="btn btn-save" id="kd-ulozit">Uložiť čas</button></div>
    <div class="tl-rad" style="margin-top:16px">
      ${druh === 'deal' ? `<button class="btn" id="kd-otvor"><svg class="ix"><use href="#ix-external"></use></svg> Otvoriť deal</button>
        ${x.trieda === 'k-zver' ? '<button class="btn btn-approve" id="kd-hned">Zverejniť hneď</button>' : '<button class="btn btn-approve" id="kd-hned">Poslať na schválenie hneď</button>'}
        <button class="btn btn-reject" id="kd-zrus">Zrušiť plán (vrátiť na schválenie)</button>` : ''}
      ${druh === 'fb' ? '<a class="btn" href="#facebook">Otvoriť sekciu Facebook</a><button class="btn btn-reject" id="kd-zrus">Zrušiť príspevok</button>' : ''}
      ${druh === 'prip' ? '<button class="btn btn-reject" id="kd-zrus">Zmazať pripomienku</button>' : ''}
    </div>`);
  telo.querySelector('#kd-ulozit').onclick = async () => {
    const v = new Date(telo.querySelector('#kd-cas').value);
    if (isNaN(v)) return;
    await kalPresun(druh, id, v);
    U.zavriOkno();
  };
  const b = s => telo.querySelector(s);
  if (b('#kd-otvor')) b('#kd-otvor').onclick = () => { U.zavriOkno(); HK().otvorDeal(id); };
  if (b('#kd-hned')) b('#kd-hned').onclick = async () => {
    U.zavriOkno();
    if (x.trieda === 'k-zver') await window.publishNow(id); else await window.sendForApprovalNow(id);
    window.toast('Hotovo.');
  };
  if (b('#kd-zrus')) b('#kd-zrus').onclick = async () => {
    if (!await window.potvrd('Naozaj zrušiť?')) return;
    U.zavriOkno();
    if (druh === 'deal') await window.restoreDeal(id);
    else if (druh === 'fb') await fs.updateDoc(U.ref('fb_posty', id), { stav: 'zruseny' });
    else await fs.deleteDoc(U.ref('pripomienky', id));
    window.toast('Zrušené.');
  };
}

U.stranka('kalendar', {
  obnov: ['hk:deals', 'hk:plan'],
  init(el) {
    kal.el = el;
    el.innerHTML = '<div id="kal-telo"></div>';
    if (HK().rola === 'admin') {
      fs.onSnapshot(fs.query(U.kol('fb_posty'), fs.where('stav', '==', 'naplanovany')), s => {
        kal.fb = s.docs.map(d => ({ ...d.data(), id: d.id }));
        kalKresli();
      }, () => {});
      fs.onSnapshot(fs.query(U.kol('pripomienky'), fs.where('odoslane', '==', false)), s => {
        kal.prip = s.docs.map(d => ({ ...d.data(), id: d.id }));
        kalKresli();
      }, () => {});
    }
    el.addEventListener('click', e => {
      const n = e.target.closest('[data-kal]');
      if (n) {
        const k = Number(n.dataset.kal);
        kal.mesiac = k === 0 ? (() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); })()
          : new Date(kal.mesiac.getFullYear(), kal.mesiac.getMonth() + k, 1);
        kalKresli();
        return;
      }
      if (e.target.closest('[data-kal-filter]')) { kal.filterOtvoreny = !kal.filterOtvoreny; kalKresli(); return; }
      const vs = e.target.closest('[data-kf-vsetko]');
      if (vs) { kalUlozFilter(new Set(vs.dataset.kfVsetko === '1' ? kalFiltre().map(f => f.k) : [])); kalKresli(); return; }
      const c = e.target.closest('.k-chip');
      if (c) kalDetail(c.dataset.druh, c.dataset.id, c.dataset.kedy);
    });
    el.addEventListener('change', e => {
      const ch = e.target.closest('[data-kf]');
      if (!ch) return;
      const zap = kalZapnute();
      if (ch.checked) zap.add(ch.dataset.kf); else zap.delete(ch.dataset.kf);
      kalUlozFilter(zap);
      kalKresli();
    });
    // Ťahanie myšou: deň sa zmení, hodina ostane.
    let tahany = null;
    el.addEventListener('dragstart', e => {
      const c = e.target.closest('.k-chip');
      if (!c) return;
      tahany = { druh: c.dataset.druh, id: c.dataset.id };
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', c.dataset.id);
      c.classList.add('tahany');
    });
    el.addEventListener('dragend', () => { el.querySelectorAll('.tahany, .k-ciel').forEach(x => x.classList.remove('tahany', 'k-ciel')); });
    el.addEventListener('dragover', e => {
      const d = e.target.closest('.k-den');
      if (!d || !tahany) return;
      e.preventDefault();
      el.querySelectorAll('.k-ciel').forEach(x => x !== d && x.classList.remove('k-ciel'));
      d.classList.add('k-ciel');
    });
    el.addEventListener('drop', e => {
      const d = e.target.closest('.k-den');
      if (!d || !tahany) return;
      e.preventDefault();
      const x = tahany.druh === 'sys' ? null : kalPolozky().find(p => p.druh === tahany.druh && p.id === tahany.id);
      tahany = null;
      if (!x) return;
      const [r, m, den] = d.dataset.den.split('-').map(Number);
      const novy = new Date(x.kedy);
      novy.setFullYear(r, m - 1, den);
      if (denKluc(novy) === denKluc(x.kedy)) return;
      kalPresun(x.druh, x.id, novy);
    });
  },
  show() { kalKresli(); },
});

// ═══════════════════════════════════════════════════════════════════
// Kontrola platnosti
// ═══════════════════════════════════════════════════════════════════
const plat = { filter: 'vsetky' };
function platProblemy() {
  const dnes = U.dnesIso(), pred30 = Date.now() - 30 * 86400000;
  return HK().deals.filter(d => d.status === 'approved' && !d.expired).map(d => {
    const k = d.kontrola || {}, dovody = [];
    if (k.stav === 'mrtvy') dovody.push(['mrtvy', 'Nefunkčný odkaz – ' + (k.dovod || '')]);
    if (k.stav === 'neiste') dovody.push(['neiste', 'Neoverený – ' + (k.dovod || '')]);
    if (d.validUntilISO && d.validUntilISO < dnes) dovody.push(['skoncene', `Akcia skončila ${U.den(d.validUntilISO + 'T12:00:00')}`]);
    const t = U.naDatum(d.timestamp);
    if (!d.validUntilISO && t && t.getTime() < pred30) dovody.push(['stare', `Zverejnený ${U.pred(t)} – over, či ešte platí`]);
    return { d, dovody, k };
  }).filter(x => x.dovody.length);
}
U.stranka('platnost', {
  obnov: ['hk:deals'],
  init(el) {
    el.innerHTML = `
      <div class="kpi-row" id="pl-kpi"></div>
      <div class="karta riadok-pole">
        <div style="flex:1"><b>Skontrolovať všetky zverejnené dealy</b>
          <p class="settings-hint" id="pl-posledna"></p></div>
        <button class="btn btn-save" id="pl-spust"><svg class="ix"><use href="#ix-refresh"></use></svg> Skontrolovať teraz</button>
      </div>
      <div id="pl-stav"></div>
      <div class="tabs" id="pl-tabs"></div>
      <div class="tl-rad" id="pl-hromadne" style="margin-bottom:10px"></div>
      <div class="tab-wrap"><table class="tab"><thead><tr><th>Deal</th><th>Problém</th><th class="r">Akcie</th></tr></thead><tbody id="pl-telo"></tbody></table></div>
      <p class="settings-hint">Kontrola otvorí odkaz každého zverejneného dealu. „Nefunkčný“ = e-shop odpovedal, že stránka neexistuje (404/410).
        „Neoverený“ = e-shop kontrolu odmietol (ochrana proti robotom) – over ručne. Akcie s dátumom platnosti sa po skončení označia samy.</p>`;
    el.querySelector('#pl-spust').addEventListener('click', e => U.akcia(e.currentTarget, async () => {
      const st = el.querySelector('#pl-stav');
      st.innerHTML = `<div class="hlaska info"><span class="tocka"></span> ${esc(U.textCakania('caka', 0))}</div>`;
      try {
        const v = await U.uloha('kontrola_platnosti', {}, (s, ms) => {
          st.innerHTML = `<div class="hlaska info"><span class="tocka"></span> ${esc(s === 'bezi' ? 'Kontrolujem odkazy – pri stovke dealov to trvá asi minútu…' : U.textCakania(s, ms))}</div>`;
        });
        st.innerHTML = `<div class="hlaska ${v.mrtvych ? 'pozor' : 'ok'}">Skontrolovaných ${v.skontrolovanych} dealov:
          ${v.mrtvych} nefunkčných, ${v.neistych} neoverených${v.exspirovanychPodlaDatumu ? `, ${v.exspirovanychPodlaDatumu} skončených podľa dátumu označených automaticky` : ''}.</div>`;
      } catch (err) { st.innerHTML = `<div class="hlaska chyba">${esc(err.message)}</div>`; }
    }));
    el.addEventListener('click', async e => {
      const t = e.target.closest('[data-pf]');
      if (t) { plat.filter = t.dataset.pf; this.show(el); return; }
      const b = e.target.closest('[data-pa]');
      if (!b) return;
      const id = b.dataset.id;
      if (b.dataset.pa === 'exp') { await window.toggleExpiredDeal(id, true); window.toast('Označené ako exspirované.'); }
      if (b.dataset.pa === 'skry') await window.rejectDeal(id);
      if (b.dataset.pa === 'otvor') HK().otvorDeal(id);
      if (b.dataset.pa === 'ok') { await fs.updateDoc(U.ref('deals', id), { kontrola: { stav: 'ok', dovod: 'overené ručne', kedy: new Date() } }); window.toast('Označené ako v poriadku.'); }
      if (b.dataset.pa === 'vsetky-mrtve') {
        const ids = platProblemy().filter(x => x.dovody.some(d => d[0] === 'mrtvy' || d[0] === 'skoncene')).map(x => x.d.id);
        if (!ids.length || !await window.potvrd(`Označiť ${ids.length} dealov ako exspirované?`)) return;
        for (const i of ids) await window.toggleExpiredDeal(i, true);
        window.toast(`Označených ${ids.length} dealov.`);
      }
    });
  },
  show(el) {
    const vsetky = platProblemy();
    const pocet = k => vsetky.filter(x => x.dovody.some(d => d[0] === k)).length;
    const zver = HK().deals.filter(d => d.status === 'approved');
    el.querySelector('#pl-kpi').innerHTML =
      U.kpi('Zverejnených dealov', zver.length, '', `platných: ${zver.filter(d => !d.expired).length}`) +
      U.kpi('Nefunkčné odkazy', pocet('mrtvy')) + U.kpi('Neoverené', pocet('neiste')) +
      U.kpi('Skončené akcie', pocet('skoncene')) + U.kpi('Staré (30+ dní)', pocet('stare'));
    const kedy = zver.map(d => U.naDatum(d.kontrola && d.kontrola.kedy)).filter(Boolean).sort((a, b) => b - a)[0];
    el.querySelector('#pl-posledna').textContent = kedy ? `Posledná kontrola: ${U.casDlhy(kedy)} (${U.pred(kedy)}).` : 'Kontrola odkazov ešte neprebehla.';
    const F = [['vsetky', 'Všetky problémy', vsetky.length], ['mrtvy', 'Nefunkčné', pocet('mrtvy')], ['neiste', 'Neoverené', pocet('neiste')], ['skoncene', 'Skončené', pocet('skoncene')], ['stare', 'Staré', pocet('stare')]];
    el.querySelector('#pl-tabs').innerHTML = F.map(([k, t, n]) => `<button class="tab-btn${plat.filter === k ? ' active' : ''}" data-pf="${k}">${t} (${n})</button>`).join('');
    el.querySelector('#pl-hromadne').innerHTML = pocet('mrtvy') + pocet('skoncene')
      ? `<button class="btn" data-pa="vsetky-mrtve"><svg class="ix"><use href="#ix-clock"></use></svg> Označiť všetky nefunkčné a skončené ako exspirované</button>` : '';
    const zoz = vsetky.filter(x => plat.filter === 'vsetky' || x.dovody.some(d => d[0] === plat.filter));
    el.querySelector('#pl-telo').innerHTML = zoz.length ? zoz.map(({ d, dovody }) => `<tr>
        <td><a href="#" data-pa="otvor" data-id="${d.id}" class="odkaz">${esc(d.title || '')}</a><small>${esc(d.store || '')}</small></td>
        <td>${dovody.map(([k, t]) => `<span class="kv-${k === 'mrtvy' || k === 'skoncene' ? 'chyba' : 'pozor'}">${esc(t)}</span>`).join(' ')}</td>
        <td class="r nowrap">
          <a class="btn btn-ic" href="${esc(HK().safeUrl(d.url))}" target="_blank" rel="noopener" title="Otvoriť u predajcu"><svg class="ix"><use href="#ix-external"></use></svg></a>
          <button class="btn btn-ic" data-pa="ok" data-id="${d.id}" title="Je v poriadku"><svg class="ix"><use href="#ix-check"></use></svg></button>
          <button class="btn" data-pa="exp" data-id="${d.id}">Exspirované</button>
          <button class="btn btn-reject" data-pa="skry" data-id="${d.id}">Skryť</button></td></tr>`).join('')
      : '<tr><td colspan="3" class="vis-empty">Žiadne problémy – všetko vyzerá v poriadku.</td></tr>';
  },
});

// ═══════════════════════════════════════════════════════════════════
// Hlásenia: "Našli ste na stránke chybu?" a nahlásenie neplatného dealu
// zo stránky - predtým šli mailom, teraz sú tu, aby sa nedali stratiť
// v schránke a dalo sa ich jednoducho označiť ako vybavené.
// ═══════════════════════════════════════════════════════════════════
const hla = { filter: 'nove' };
U.stranka('hlasenia', {
  obnov: ['hk:hlasenia', 'hk:deals'],
  init(el) {
    el.innerHTML = `
      <div class="kpi-row" id="hl-kpi"></div>
      <div class="tabs" id="hl-tabs"></div>
      <div id="hl-list"></div>`;
    el.addEventListener('click', async e => {
      const t = e.target.closest('[data-hf]');
      if (t) { hla.filter = t.dataset.hf; this.show(el); return; }
      const b = e.target.closest('[data-ha]');
      if (!b) return;
      const id = b.dataset.id;
      if (b.dataset.ha === 'vybav') await fs.updateDoc(U.ref('hlasenia', id), { stav: 'vybavene' });
      if (b.dataset.ha === 'otvor-znova') await fs.updateDoc(U.ref('hlasenia', id), { stav: 'nove' });
      if (b.dataset.ha === 'vymaz') {
        if (!await window.potvrd('Natrvalo vymazať toto hlásenie?')) return;
        await fs.deleteDoc(U.ref('hlasenia', id));
      }
      if (b.dataset.ha === 'deal') HK().otvorDeal(b.dataset.dealid);
    });
  },
  show(el) {
    const vsetky = HK().hlasenia;
    const pocet = s => vsetky.filter(x => x.stav === s).length;
    el.querySelector('#hl-kpi').innerHTML =
      U.kpi('Nové', pocet('nove')) + U.kpi('Vybavené', pocet('vybavene')) + U.kpi('Spolu', vsetky.length);
    el.querySelector('#hl-tabs').innerHTML = [['nove', 'Nové'], ['vybavene', 'Vybavené']]
      .map(([k, t]) => `<button class="tab-btn${hla.filter === k ? ' active' : ''}" data-hf="${k}">${t} (${pocet(k)})</button>`).join('');
    const zoz = vsetky.filter(x => x.stav === hla.filter);
    const TYP = { chyba: 'Chyba na stránke', neplatny_deal: 'Neplatný deal' };
    el.querySelector('#hl-list').innerHTML = zoz.length ? zoz.map(h => {
      const deal = h.dealId ? HK().deals.find(d => d.id === h.dealId) : null;
      return `<div class="deal-row">
        <div class="row-header">
          <div class="row-info">
            <div class="row-title"><span class="badge badge-pending">${esc(TYP[h.typ] || h.typ)}</span> <small>${U.casDlhy(h.timestamp)} (${U.pred(h.timestamp)})</small></div>
            ${h.dealTitle || deal ? `<div class="row-sub">Deal: <em>${esc((deal && deal.title) || h.dealTitle || '')}</em></div>` : ''}
            ${h.stranka ? `<div class="row-sub">Stránka: <a href="${esc(h.stranka)}" target="_blank" rel="noopener">${esc(h.stranka)}</a></div>` : ''}
            ${h.text ? `<div class="comment-body-text">${esc(h.text)}</div>` : ''}
          </div>
          <div class="row-actions">
            ${h.dealId ? `<button class="btn btn-ic" data-ha="deal" data-id="${h.id}" data-dealid="${h.dealId}" title="Otvoriť deal"><svg class="ix"><use href="#ix-external"></use></svg></button>` : ''}
            ${h.stav === 'nove'
              ? `<button class="btn btn-approve" data-ha="vybav" data-id="${h.id}"><svg class="ix"><use href="#ix-check"></use></svg> Vybaviť</button>`
              : `<button class="btn" data-ha="otvor-znova" data-id="${h.id}">Otvoriť znova</button>`}
            <button class="btn btn-delete" data-ha="vymaz" data-id="${h.id}"><svg class="ix"><use href="#ix-trash"></use></svg> Vymazať</button>
          </div>
        </div>
      </div>`;
    }).join('') : `<div class="empty">Žiadne hlásenia v tejto kategórii.</div>`;
  },
});

// ═══════════════════════════════════════════════════════════════════
// Editor fotky dealu: orezanie, výmena, náhľad karty a Facebooku
// ═══════════════════════════════════════════════════════════════════
const POMERY = [['karta', 'Karta 4 : 3', 4 / 3], ['fb', 'Facebook 1,91 : 1', 1.91], ['stvorec', 'Štvorec 1 : 1', 1]];
window.fotoEditor = function (id) {
  const d = HK().deals.find(x => x.id === id);
  if (!d) return;
  const telo = U.okno('Fotka dealu', `
    <div class="fe">
      <div class="fe-l">
        <div class="fe-pomery">${POMERY.map(([k, t], i) => `<button type="button" class="btn${i === 0 ? ' on' : ''}" data-pomer="${k}">${t}</button>`).join('')}</div>
        <div class="fe-platno"><canvas id="fe-c"></canvas><div class="fe-tip">Ťahaj myšou pre posun, kolieskom alebo posuvníkom priblíž.</div></div>
        <label class="fe-zoom">Priblíženie <input type="range" id="fe-z" min="1" max="4" step="0.01" value="1"></label>
        <div class="riadok-pole">
          <input type="url" id="fe-url" placeholder="Adresa iného obrázka (https://…)">
          <button class="btn" id="fe-nacitaj" type="button">Načítať</button>
          <label class="btn"><svg class="ix"><use href="#ix-upload"></use></svg> Nahrať súbor<input type="file" id="fe-subor" accept="image/*" hidden></label>
        </div>
        <div id="fe-hlaska"></div>
      </div>
      <div class="fe-r">
        <div class="pole-lab">Na stránke</div>
        <div class="fe-karta"><canvas id="fe-pk"></canvas><div><small>${esc(d.store || '')}</small><b>${esc(d.title || '')}</b><span>${U.eur(d.dealPrice)}</span></div></div>
        <div class="pole-lab" style="margin-top:14px">Na Facebooku</div>
        <div class="fe-fb"><canvas id="fe-pf"></canvas><div class="fe-fb-t"><small>HENKUKAJ.SK</small><b>${esc(d.title || '')} – HenKukaj.sk</b>
          <span>${esc((d.description || `${d.title} v obchode ${d.store}.`).slice(0, 110))}</span></div></div>
      </div>
    </div>
    <div class="tl-rad fe-tl">
      <button class="btn btn-save" id="fe-ulozit"><svg class="ix"><use href="#ix-save"></use></svg> Uložiť orezanú fotku</button>
      <button class="btn" id="fe-adresa" hidden>Uložiť len novú adresu (bez orezania)</button>
      <button class="btn" data-zavriet>Zrušiť</button>
    </div>`, { siroke: true });
  const c = telo.querySelector('#fe-c'), ctx = c.getContext('2d');
  const st = { img: null, pomer: 4 / 3, zoom: 1, cx: 0, cy: 0, cudzi: false, zdroj: d.imageUrl || '' };
  const hlaska = (t, typ = 'info') => { telo.querySelector('#fe-hlaska').innerHTML = t ? `<div class="hlaska ${typ}">${t}</div>` : ''; };

  function velkost() {
    const w = Math.min(telo.querySelector('.fe-platno').clientWidth || 520, 560);
    c.width = Math.round(w); c.height = Math.round(w / st.pomer);
  }
  function mierka() { return Math.max(c.width / st.img.width, c.height / st.img.height) * st.zoom; }
  function obmedz() {
    const s = mierka(), pw = c.width / s / 2, ph = c.height / s / 2;
    st.cx = Math.min(Math.max(st.cx, pw), st.img.width - pw);
    st.cy = Math.min(Math.max(st.cy, ph), st.img.height - ph);
  }
  function kresli(cie = ctx, w = c.width, h = c.height) {
    if (!st.img) return;
    const s = mierka() * (w / c.width);
    cie.fillStyle = '#fff'; cie.fillRect(0, 0, w, h);
    cie.drawImage(st.img, w / 2 - st.cx * s, h / 2 - st.cy * s, st.img.width * s, st.img.height * s);
  }
  function nahlady() {
    // Náhľady kreslíme z pôvodného obrázka (funguje aj pri cudzom obrázku).
    const pk = telo.querySelector('#fe-pk'), pf = telo.querySelector('#fe-pf');
    pk.width = 160; pk.height = 120; pf.width = 382; pf.height = 200;
    const zober = (cv, pomer) => {
      const x = cv.getContext('2d');
      if (!st.img) return;
      if (Math.abs(pomer - st.pomer) < 0.01) { kresli(x, cv.width, cv.height); return; }
      // iný pomer než orezávame: stred ostane, ako to orieže stránka/FB
      const s = Math.max(cv.width / st.img.width, cv.height / st.img.height);
      x.fillStyle = '#fff'; x.fillRect(0, 0, cv.width, cv.height);
      x.drawImage(st.img, cv.width / 2 - st.cx * s, cv.height / 2 - st.cy * s, st.img.width * s, st.img.height * s);
    };
    zober(pk, 4 / 3); zober(pf, 1.91);
  }
  function prekresli() { if (!st.img) return; obmedz(); kresli(); nahlady(); }

  function nacitaj(src, cudziPokus = true) {
    if (!src) { hlaska('Deal zatiaľ nemá fotku – nahraj súbor alebo vlož adresu obrázka.'); return; }
    const im = new Image();
    if (cudziPokus && !src.startsWith('data:')) im.crossOrigin = 'anonymous';
    im.onload = () => {
      st.img = im; st.zoom = 1; st.cx = im.width / 2; st.cy = im.height / 2;
      st.cudzi = !cudziPokus && !src.startsWith('data:');
      telo.querySelector('#fe-z').value = 1;
      velkost(); prekresli();
      hlaska(st.cudzi ? 'Tento obrázok e-shop nedovoľuje orezať priamo v prehliadači. Môžeš uložiť len jeho adresu, alebo ho stiahni (pravý klik → Uložiť obrázok) a nahraj ako súbor.' : '', 'pozor');
      telo.querySelector('#fe-ulozit').disabled = st.cudzi;
    };
    im.onerror = () => {
      if (cudziPokus && !src.startsWith('data:')) nacitaj(src, false);
      else hlaska('Obrázok sa nepodarilo načítať. Skontroluj adresu.', 'chyba');
    };
    im.src = src;
  }

  telo.querySelector('.fe-pomery').addEventListener('click', e => {
    const b = e.target.closest('[data-pomer]');
    if (!b) return;
    telo.querySelectorAll('[data-pomer]').forEach(x => x.classList.toggle('on', x === b));
    st.pomer = POMERY.find(p => p[0] === b.dataset.pomer)[2];
    velkost(); prekresli();
  });
  telo.querySelector('#fe-z').addEventListener('input', e => { st.zoom = Number(e.target.value); prekresli(); });
  c.addEventListener('wheel', e => {
    e.preventDefault();
    st.zoom = Math.min(4, Math.max(1, st.zoom * (e.deltaY < 0 ? 1.08 : 0.93)));
    telo.querySelector('#fe-z').value = st.zoom;
    prekresli();
  }, { passive: false });
  let tah = null;
  c.addEventListener('pointerdown', e => { tah = { x: e.clientX, y: e.clientY }; c.setPointerCapture(e.pointerId); });
  c.addEventListener('pointermove', e => {
    if (!tah || !st.img) return;
    const s = mierka() * (c.getBoundingClientRect().width / c.width);
    st.cx -= (e.clientX - tah.x) / s; st.cy -= (e.clientY - tah.y) / s;
    tah = { x: e.clientX, y: e.clientY };
    prekresli();
  });
  c.addEventListener('pointerup', () => { tah = null; });
  telo.querySelector('#fe-nacitaj').addEventListener('click', () => {
    const u = telo.querySelector('#fe-url').value.trim();
    if (!/^https:\/\//i.test(u)) { hlaska('Adresa obrázka musí začínať https://', 'chyba'); return; }
    st.zdroj = u;
    telo.querySelector('#fe-adresa').hidden = false;
    nacitaj(u);
  });
  telo.querySelector('#fe-subor').addEventListener('change', async e => {
    const f = e.target.files[0];
    if (!f) return;
    if (!f.type.startsWith('image/')) { hlaska('Vyber obrázok (JPG, PNG, WebP).', 'chyba'); return; }
    st.zdroj = '';
    telo.querySelector('#fe-adresa').hidden = true;
    nacitaj(await U.citajSubor(f, 'url'));
  });
  telo.querySelector('#fe-adresa').addEventListener('click', async e => U.akcia(e.currentTarget, async () => {
    await fs.updateDoc(U.ref('deals', id), { imageUrl: st.zdroj });
    await HK().logChange(id, 'foto', d.title || null);
    window.toast('Adresa fotky uložená.');
    U.zavriOkno();
  }));
  telo.querySelector('#fe-ulozit').addEventListener('click', async e => U.akcia(e.currentTarget, async () => {
    if (!st.img) return;
    // Výstup najviac 800 px na šírku a ~180 kB - fotka je uložená priamo
    // v databáze a stránka ju načítava v zozname dealov.
    const W = 800, H = Math.round(W / st.pomer);
    const out = document.createElement('canvas');
    out.width = W; out.height = H;
    kresli(out.getContext('2d'), W, H);
    let q = 0.85, url;
    try {
      url = out.toDataURL('image/jpeg', q);
      while (url.length > 180 * 1024 && q > 0.4) { q -= 0.1; url = out.toDataURL('image/jpeg', q); }
    } catch (err) {
      hlaska('Tento obrázok sa nedá orezať (e-shop to nepovoľuje). Stiahni ho a nahraj ako súbor.', 'chyba');
      return;
    }
    await fs.updateDoc(U.ref('deals', id), { imageUrl: url });
    await HK().logChange(id, 'foto', d.title || null);
    window.toast('Fotka uložená. Na Facebooku sa prejaví po vygenerovaní stránky dealu (do hodiny).');
    U.zavriOkno();
  }));
  setTimeout(() => { velkost(); nacitaj(st.zdroj); }, 30);
};
