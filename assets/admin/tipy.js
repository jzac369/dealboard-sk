// ── Tipy medzi dealmi ("dávkovač") ─────────────────────────────────
// Admin nahrá obrázky, stránka ich zobrazuje medzi dealmi. Obrázok sa najprv
// zmenší v prehliadači (JPEG, max. 1200 px), uloží do tipy_cakaren a
// plánovač spustí workflow tipy-publikuj, ktoré z neho spraví súbor v
// assets/tipy/. Nastavenia tipov (zapnutie, váha, termín) sú v settings/tipy
// a menia sa hneď, bez čakania na publikovanie.
const U = window.HKU, HK = () => window.HK, { fs, esc } = U;

const MAX_SIRKA = 1200;
const MAX_BAJTOV = 700 * 1024;     // dokument vo Firestore má limit 1 MB
let tp = { tipy: [], prvy: 5, kazdych: 8 };

const noveId = () => Array.from({ length: 8 }, () => 'abcdefghjkmnpqrstuvwxyz23456789'[Math.floor(Math.random() * 31)]).join('');

async function nacitaj() {
  const s = await fs.getDoc(U.ref('settings', 'tipy'));
  const d = s.exists() ? s.data() : {};
  tp = { tipy: Array.isArray(d.tipy) ? d.tipy : [], prvy: Number(d.prvy) || 5, kazdych: Number(d.kazdych) || 8 };
}

async function uloz(popis) {
  await fs.setDoc(U.ref('settings', 'tipy'), { tipy: tp.tipy, prvy: tp.prvy, kazdych: tp.kazdych, upravene: fs.serverTimestamp() });
  HK().logChange('settings-tipy', 'tipy', popis);
}

// Zmenší obrázok a vráti data URL (JPEG). Skúša znižovať kvalitu, kým sa nezmestí do limitu.
async function zmensi(subor) {
  const url = await U.citajSubor(subor, 'url');
  const img = await new Promise((ok, zle) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => zle(new Error('Súbor nie je obrázok.')); i.src = url; });
  const w = Math.min(MAX_SIRKA, img.naturalWidth), h = Math.round(img.naturalHeight * w / img.naturalWidth);
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, w, h); g.drawImage(img, 0, 0, w, h);
  for (let q = 0.88; q >= 0.5; q -= 0.08) {
    const d = c.toDataURL('image/jpeg', q);
    if (d.length * 0.75 <= MAX_BAJTOV) return { dataUrl: d, w, h };
  }
  throw new Error('Obrázok je príliš veľký aj po zmenšení.');
}

async function publikuj(tichy) {
  try {
    await U.uloha('spusti_workflow', { workflow: 'tipy-publikuj.yml' }, () => {});
    if (!tichy) window.toast('Publikovanie spustené. Obrázky budú na stránke zhruba o 3–6 minút.');
  } catch (e) { window.toast('Publikovanie sa nepodarilo spustiť: ' + e.message, 'chyba'); }
}

function stav(t, dnes) {
  if (t.chyba) return ['chyba', 'Chyba: ' + t.chyba];
  if (!t.obrazok) return ['caka', 'Čaká na publikovanie'];
  if (!t.zap) return ['vyp', 'Vypnutý'];
  if (t.od && t.od > dnes) return ['vyp', 'Začne ' + t.od];
  if (t.do && t.do < dnes) return ['vyp', 'Skončil ' + t.do];
  return ['ok', 'Zobrazuje sa'];
}

U.stranka('tipy', {
  async init(el) {
    el.innerHTML = `
      <div class="hlaska info" style="margin-bottom:14px">Tipy sú obrázky s radami, kde a ako ušetriť. Zobrazujú sa medzi dealmi, nie sú
        reklama a odkaz je nepovinný. Nahraj ich viac naraz – poradie a to, ktorý sa komu ukáže, vyberie algoritmus.</div>
      <div class="tl-rad" style="margin-bottom:14px;gap:10px;flex-wrap:wrap">
        <button class="btn btn-save" id="tp-nahraj"><svg class="ix"><use href="#ix-plus"></use></svg> Nahrať obrázky</button>
        <button class="btn" id="tp-publikuj" title="Ak sa obrázok dlho nezobrazuje">Publikovať znova</button>
        <input type="file" id="tp-subory" accept="image/png,image/jpeg,image/webp" multiple hidden>
      </div>
      <div id="tp-stav"></div>
      <div class="rk-zoznam" id="tp-zoznam"></div>
      <h3 style="margin:22px 0 8px">Ako často sa tipy zobrazujú</h3>
      <form class="form-mriezka" id="tp-nast" style="max-width:520px">
        <label>Prvý tip po (dealoch)<input name="prvy" type="number" min="1" max="30" value="${tp.prvy}"></label>
        <label>Ďalšie po každých (dealoch)<input name="kazdych" type="number" min="3" max="50" value="${tp.kazdych}"></label>
        <div class="cela tl-rad"><button class="btn btn-save" type="submit">Uložiť</button></div>
      </form>
      <div class="settings-hint" style="max-width:720px;margin-top:14px">
        <b>Ako algoritmus vyberá:</b> poradie tipov sa pri každej návšteve zamieša podľa váhy – tip s váhou 3 sa dostane dopredu
        trikrát častejšie než s váhou 1. Tip, ktorý sa návštevníkovi už ukázal, má pri ďalšej návšteve nižšiu šancu
        (váha sa delí počtom zobrazení), takže sa striedajú všetky. Tip, ktorý návštevník zavrie, sa mu už nezobrazí nikdy.
        Naraz sa na stránke ukáže najviac jeden tip na uvedený počet dealov a žiaden sa nezopakuje.</div>`;

    el.querySelector('#tp-nahraj').addEventListener('click', () => el.querySelector('#tp-subory').click());
    el.querySelector('#tp-publikuj').addEventListener('click', e => U.akcia(e.currentTarget, () => publikuj()));

    el.querySelector('#tp-subory').addEventListener('change', async e => {
      const subory = [...e.target.files]; e.target.value = '';
      if (!subory.length) return;
      const stavEl = el.querySelector('#tp-stav');
      let ok = 0;
      for (const [i, f] of subory.entries()) {
        stavEl.innerHTML = `<div class="hlaska info">Nahrávam ${i + 1} z ${subory.length}…</div>`;
        try {
          const { dataUrl } = await zmensi(f);
          const id = noveId();
          await fs.setDoc(U.ref('tipy_cakaren', id), { dataUrl, vytvorene: fs.serverTimestamp() });
          tp.tipy.push({ id, nazov: f.name.replace(/\.[^.]+$/, '').slice(0, 60), alt: '', url: '', zap: true, vaha: 1, od: '', do: '', obrazok: '' });
          ok++;
        } catch (err) { window.toast(`${f.name}: ${err.message}`, 'chyba'); }
      }
      stavEl.innerHTML = '';
      if (ok) {
        await uloz(`Nahraných tipov: ${ok}`);
        await publikuj();
      }
      this.show(el);
    });

    el.querySelector('#tp-nast').addEventListener('submit', async e => {
      e.preventDefault();
      const f = e.target.elements;
      tp.prvy = Math.min(30, Math.max(1, Number(f.prvy.value) || 5));
      tp.kazdych = Math.min(50, Math.max(3, Number(f.kazdych.value) || 8));
      await U.akcia(e.submitter, async () => { await uloz('Zmenená frekvencia tipov'); window.toast('Uložené.'); });
    });

    el.addEventListener('change', async e => {
      const t = e.target.closest('[data-tp]'); if (!t) return;
      const tip = tp.tipy.find(x => x.id === t.dataset.id); if (!tip) return;
      const k = t.dataset.tp;
      if (k === 'zap') tip.zap = t.checked;
      else if (k === 'vaha') tip.vaha = Math.min(10, Math.max(1, Number(t.value) || 1));
      else tip[k] = t.value.trim();
      if (k === 'url' && tip.url && !/^(https:\/\/(www\.)?henkukaj\.sk\/|\/|#)/.test(tip.url)) {
        tip.url = ''; t.value = ''; window.toast('Odkaz smie viesť len na stránku HenKukaj.sk (tip nie je reklama).', 'chyba');
      }
      await uloz(`Upravený tip ${tip.nazov}`);
      this.show(el);
    });

    el.addEventListener('click', async e => {
      const b = e.target.closest('[data-tpz]'); if (!b) return;
      const tip = tp.tipy.find(x => x.id === b.dataset.id); if (!tip) return;
      if (!await window.potvrd(`Odstrániť tip „${tip.nazov}“? Obrázok sa zo stránky aj z repozitára zmaže.`)) return;
      tp.tipy = tp.tipy.filter(x => x.id !== tip.id);
      try { await fs.deleteDoc(U.ref('tipy_cakaren', tip.id)); } catch (err) { /* už nečaká */ }
      await uloz(`Odstránený tip ${tip.nazov}`);
      publikuj(true);   // zmaže súbor
      this.show(el);
    });
  },

  async show(el) {
    await nacitaj();
    const dnes = U.dnesIso();
    const cakajuce = tp.tipy.filter(t => !t.obrazok && !t.chyba).length;
    el.querySelector('#tp-stav').innerHTML = cakajuce
      ? `<div class="hlaska info">${cakajuce} tipov čaká na publikovanie (zvyčajne 3–6 minút). Stránku môžeš zatvoriť.</div>` : '';
    el.querySelector('#tp-zoznam').innerHTML = tp.tipy.length ? tp.tipy.map(t => {
      const [trieda, text] = stav(t, dnes);
      const img = t.obrazok ? `<img src="${esc(t.obrazok)}" alt="" loading="lazy">` : '<span class="settings-hint">…</span>';
      return `<div class="rk-karta${trieda === 'ok' ? '' : ' vyp'}">
        <div class="rk-obr">${img}</div>
        <div class="rk-info">
          <div class="form-mriezka" style="gap:6px">
            <label class="cela">Názov (len pre teba)<input data-tp="nazov" data-id="${esc(t.id)}" value="${esc(t.nazov)}" maxlength="60"></label>
            <label class="cela">Popis obrázka (pre nevidiacich; pri zdieľaní sa použije ako text)<input data-tp="alt" data-id="${esc(t.id)}" value="${esc(t.alt)}" maxlength="140"></label>
            <label class="cela">Odkaz na stránke (nepovinné, napr. https://henkukaj.sk/#kody)<input data-tp="url" data-id="${esc(t.id)}" value="${esc(t.url)}" maxlength="200"></label>
            <label>Váha<input data-tp="vaha" data-id="${esc(t.id)}" type="number" min="1" max="10" value="${Number(t.vaha) || 1}"></label>
            <label>Od<input data-tp="od" data-id="${esc(t.id)}" type="date" value="${esc(t.od || '')}"></label>
            <label>Do<input data-tp="do" data-id="${esc(t.id)}" type="date" value="${esc(t.do || '')}"></label>
          </div>
          <small class="tp-stav tp-${trieda}">${esc(text)}</small>
        </div>
        <div class="rk-akcie">
          <label class="zaskrt"><input type="checkbox" data-tp="zap" data-id="${esc(t.id)}"${t.zap ? ' checked' : ''}> Zapnutý</label>
          <button class="btn btn-reject" data-tpz data-id="${esc(t.id)}">Odstrániť</button>
        </div>
      </div>`;
    }).join('') : '<p class="vis-empty">Zatiaľ žiadne tipy. Nahraj prvé obrázky.</p>';
  },
});
