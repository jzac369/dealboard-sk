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
          if (v.imageUrl) f('imageUrl').value = v.imageUrl;
          if (v.description) f('description').value = v.description;
          if (v.url) f('url').value = cistaUrl(v.url);
          const chyba = [!v.title && 'názov', !v.dealPrice && 'cenu', !v.imageUrl && 'fotku'].filter(Boolean);
          stav.innerHTML = `<div class="hlaska ${chyba.length ? 'pozor' : 'ok'}">${chyba.length
            ? `Načítané, ale chýba ${chyba.join(', ')} – doplň ručne. Pôvodnú cenu e-shopy zvyčajne neuvádzajú.`
            : 'Údaje načítané. Doplň pôvodnú cenu a kategóriu a skontroluj zvyšok.'}${v.vypredane ? ' <b>Pozor: e-shop hlási, že produkt nie je skladom.</b>' : ''}</div>`;
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

function kalPolozky() {
  const p = [];
  HK().deals.forEach(d => {
    if (d.status === 'planned' && d.publishAt) p.push({ druh: 'deal', id: d.id, kedy: U.naDatum(d.publishAt), n: d.title, typ: 'Zverejnenie dealu', trieda: 'k-zver' });
    if (d.status === 'scheduled' && d.sendAt) p.push({ druh: 'deal', id: d.id, kedy: U.naDatum(d.sendAt), n: d.title, typ: 'Poslať na schválenie', trieda: 'k-schv' });
  });
  kal.fb.forEach(x => p.push({ druh: 'fb', id: x.id, kedy: U.naDatum(x.sendAt), n: x.title || (x.text || '').slice(0, 60), typ: 'Príspevok na Facebook', trieda: 'k-fb' }));
  kal.prip.forEach(x => p.push({ druh: 'prip', id: x.id, kedy: U.naDatum(x.sendAt), n: x.text, typ: 'Pripomienka do Telegramu', trieda: 'k-prip' }));
  return p.filter(x => x.kedy).sort((a, b) => a.kedy - b.kedy);
}
const denKluc = d => `${d.getFullYear()}-${U.pad(d.getMonth() + 1)}-${U.pad(d.getDate())}`;

function kalKresli() {
  const el = kal.el;
  if (!el) return;
  const polozky = kalPolozky();
  const m = kal.mesiac, rok = m.getFullYear(), mes = m.getMonth();
  const nazov = m.toLocaleDateString('sk-SK', { month: 'long', year: 'numeric' });
  const zac = new Date(rok, mes, 1);
  zac.setDate(zac.getDate() - ((zac.getDay() + 6) % 7));
  const dnes = denKluc(new Date());
  const poDnoch = {};
  polozky.forEach(x => (poDnoch[denKluc(x.kedy)] = poDnoch[denKluc(x.kedy)] || []).push(x));
  const chip = x => `<div class="k-chip ${x.trieda}" draggable="true" data-druh="${x.druh}" data-id="${esc(x.id)}" title="${esc(x.typ + ': ' + x.n)}">
      <b>${U.pad(x.kedy.getHours())}:${U.pad(x.kedy.getMinutes())}</b> ${esc(x.n)}</div>`;
  let bunky = '';
  for (let i = 0; i < 42; i++) {
    const d = new Date(zac); d.setDate(zac.getDate() + i);
    if (i >= 35 && d.getMonth() !== mes) break;
    const k = denKluc(d);
    bunky += `<div class="k-den${d.getMonth() !== mes ? ' iny' : ''}${k === dnes ? ' dnes' : ''}${k < dnes ? ' minule' : ''}" data-den="${k}">
      <div class="k-cislo">${d.getDate()}</div>${(poDnoch[k] || []).map(chip).join('')}</div>`;
  }
  const buduce = polozky.filter(x => x.kedy.getTime() >= Date.now() - 3600000);
  el.querySelector('#kal-telo').innerHTML = `
    <div class="kal-lista">
      <button class="btn btn-ic" data-kal="-1" aria-label="Predchádzajúci mesiac"><svg class="ix"><use href="#ix-chevl"></use></svg></button>
      <b class="kal-nazov">${esc(nazov)}</b>
      <button class="btn btn-ic" data-kal="1" aria-label="Ďalší mesiac"><svg class="ix"><use href="#ix-chevr"></use></svg></button>
      <button class="btn" data-kal="0">Dnes</button>
      <span class="kal-leg"><i class="k-zver"></i>zverejnenie <i class="k-schv"></i>na schválenie <i class="k-fb"></i>Facebook <i class="k-prip"></i>pripomienka</span>
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

function kalDetail(druh, id) {
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
  obnov: ['hk:deals'],
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
      const c = e.target.closest('.k-chip');
      if (c) kalDetail(c.dataset.druh, c.dataset.id);
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
      const x = kalPolozky().find(p => p.druh === tahany.druh && p.id === tahany.id);
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
