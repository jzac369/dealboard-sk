// ── Marketing: Facebook, UTM odkazy, SEO ──────────────────────────────
const U = window.HKU, HK = () => window.HK, { fs, esc } = U;

// ═══════════════════════════════════════════════════════════════════
// Facebook – plánovač príspevkov
// ═══════════════════════════════════════════════════════════════════
// Rovnaký text, aký skladá facebook_post.py pri automatickom zdieľaní.
function textPrispevku(d) {
  const c = v => (Number(v) || 0).toFixed(2).replace('.', ',');
  const r = [(d.title || '').trim()];
  if (d.zadarmo) r.push('Zadarmo');
  else if (d.dealPrice) {
    if (d.originalPrice && d.discountPercent) r.push(`Teraz ${c(d.dealPrice)} € namiesto ${c(d.originalPrice)} € (−${d.discountPercent} %)`);
    else r.push(`Cena ${c(d.dealPrice)} €`);
  } else if (d.discountPercent) r.push(`Zľava ${Math.round(d.discountPercent)} %`);
  if (d.store) r.push(`Predajca: ${d.store}`);
  r.push('', 'Viac na HenKukaj.sk');
  return r.join('\n');
}
function rychlyCas(k) {
  const d = new Date();
  if (k === 'dnes18') d.setHours(18, 0, 0, 0);
  if (k === 'zajtra9') { d.setDate(d.getDate() + 1); d.setHours(9, 0, 0, 0); }
  if (k === 'zajtra17') { d.setDate(d.getDate() + 1); d.setHours(17, 0, 0, 0); }
  if (k === 'o1h') { d.setTime(d.getTime() + 3600000); d.setSeconds(0, 0); }
  return d;
}
const fb = { posty: [], dealId: '' };
function za(t) {
  const m = Math.round((U.naDatum(t) - Date.now()) / 60000);
  if (m <= 0) return 'odosiela sa…';
  if (m < 60) return `o ${m} min`;
  if (m < 1440) return `o ${Math.round(m / 60)} h`;
  return `o ${Math.round(m / 1440)} d`;
}
function fbNahlad(d, text) {
  return `<div class="fbp">
    <div class="fbp-hlava"><span class="fbp-logo">H</span><div><b>HenKukaj.sk</b><small>Naplánované · <svg class="ix"><use href="#ix-facebook"></use></svg></small></div></div>
    <div class="fbp-text">${esc(text).replace(/\n/g, '<br>')}</div>
    ${d ? `<div class="fbp-odkaz">${d.imageUrl ? `<div class="fbp-obr" style="background-image:url('${esc(d.imageUrl).replace(/'/g, '%27')}')"></div>` : '<div class="fbp-obr fbp-bez">bez fotky – Facebook ukáže logo</div>'}
      <div class="fbp-meta"><small>HENKUKAJ.SK</small><b>${esc(d.title)} – HenKukaj.sk</b></div></div>` : ''}
  </div>`;
}
U.stranka('facebook', {
  init(el) {
    el.innerHTML = `
      <div class="fb-mriezka">
        <div class="karta">
          <h3 class="karta-nadpis">Nový príspevok</h3>
          <label class="pole-lab">Deal</label>
          <input type="search" id="fb-hladaj" placeholder="Hľadať medzi zverejnenými dealmi…">
          <select id="fb-deal" size="6" class="fb-deal"></select>
          <label class="pole-lab" for="fb-text">Text príspevku</label>
          <textarea id="fb-text" rows="7" maxlength="2000"></textarea>
          <label class="pole-lab" for="fb-cas">Kedy</label>
          <div class="riadok-pole"><input type="datetime-local" id="fb-cas">
            <span class="plan-rychlo">
              <button type="button" data-fbc="o1h">O hodinu</button><button type="button" data-fbc="dnes18">Dnes 18:00</button>
              <button type="button" data-fbc="zajtra9">Zajtra 9:00</button><button type="button" data-fbc="zajtra17">Zajtra 17:00</button></span></div>
          <div id="fb-pozor"></div>
          <div class="tl-rad" style="margin-top:12px"><button class="btn btn-save" id="fb-uloz"><svg class="ix"><use href="#ix-calendar"></use></svg> Naplánovať príspevok</button></div>
          <p class="settings-hint">Príspevok odíde do 5 minút od zvoleného času. Odkaz vedie na stránku dealu na henkukaj.sk
            (Facebook z nej vytiahne fotku a titulok) a má UTM značky, takže návštevy z neho uvidíš v Návštevnosti.</p>
        </div>
        <div class="karta"><div class="pole-lab">Náhľad</div><div id="fb-nahlad"></div></div>
      </div>
      <div class="karta"><h3 class="karta-nadpis">Naplánované</h3><div id="fb-plan"></div></div>
      <div class="karta"><h3 class="karta-nadpis">História</h3>
        <p class="settings-hint">Aj automatické zdieľanie (2 čerstvé dealy na beh) podľa rozvrhu v <a href="#planovac">Plánovači úloh</a>.</p>
        <div class="tab-wrap"><table class="tab"><thead><tr><th>Kedy</th><th>Príspevok</th><th>Stav</th><th></th></tr></thead><tbody id="fb-hist"></tbody></table></div></div>`;
    const sel = el.querySelector('#fb-deal'), txt = el.querySelector('#fb-text');
    const deal = () => HK().deals.find(d => d.id === sel.value);
    const nahlad = () => {
      const d = deal();
      el.querySelector('#fb-nahlad').innerHTML = fbNahlad(d, txt.value);
      el.querySelector('#fb-pozor').innerHTML = d && d.fbPosted
        ? '<div class="hlaska pozor">Tento deal už na Facebooku bol – opakovanie môže pôsobiť ako spam.</div>' : '';
    };
    this._zoznam = () => {
      const q = U.norm(el.querySelector('#fb-hladaj').value);
      const dealy = HK().deals.filter(d => d.status === 'approved' && !d.expired && (!q || U.norm(d.title + ' ' + d.store).includes(q)))
        .sort((a, b) => (U.naDatum(b.timestamp) || 0) - (U.naDatum(a.timestamp) || 0)).slice(0, 80);
      const pred = sel.value;
      sel.innerHTML = dealy.map(d => `<option value="${esc(d.id)}">${d.fbPosted ? '✓ ' : ''}${esc(d.title)} · ${esc(d.store || '')}</option>`).join('');
      if (dealy.some(d => d.id === pred)) sel.value = pred;
    };
    el.querySelector('#fb-hladaj').addEventListener('input', this._zoznam);
    sel.addEventListener('change', () => { const d = deal(); if (d) txt.value = textPrispevku(d); nahlad(); });
    txt.addEventListener('input', nahlad);
    el.querySelector('#fb-cas').value = U.doInputu(rychlyCas('zajtra9'));
    el.addEventListener('click', async e => {
      const q = e.target.closest('[data-fbc]');
      if (q) { el.querySelector('#fb-cas').value = U.doInputu(rychlyCas(q.dataset.fbc)); return; }
      const a = e.target.closest('[data-fba]');
      if (!a) return;
      const p = fb.posty.find(x => x.id === a.dataset.id);
      if (a.dataset.fba === 'zrus' && await window.potvrd('Zrušiť tento naplánovaný príspevok?')) {
        await fs.updateDoc(U.ref('fb_posty', p.id), { stav: 'zruseny' });
        window.toast('Príspevok zrušený.');
      }
      if (a.dataset.fba === 'uprav') {
        const t = U.okno('Upraviť príspevok', `<label class="pole-lab">Text</label><textarea id="fu-t" rows="7">${esc(p.text || '')}</textarea>
          <label class="pole-lab">Kedy</label><input type="datetime-local" id="fu-c" value="${U.doInputu(U.naDatum(p.sendAt))}">
          <div class="tl-rad" style="margin-top:14px"><button class="btn btn-save" id="fu-ok">Uložiť</button><button class="btn" data-zavriet>Zrušiť</button></div>`);
        t.querySelector('#fu-ok').onclick = async () => {
          const c = new Date(t.querySelector('#fu-c').value);
          if (isNaN(c) || c.getTime() < Date.now()) { window.toast('Čas musí byť v budúcnosti.', 'chyba'); return; }
          await fs.updateDoc(U.ref('fb_posty', p.id), { text: t.querySelector('#fu-t').value, sendAt: c, spustene: null });
          U.zavriOkno(); window.toast('Uložené.');
        };
      }
    });
    el.querySelector('#fb-uloz').addEventListener('click', e => U.akcia(e.currentTarget, async () => {
      const d = deal(), cas = new Date(el.querySelector('#fb-cas').value);
      if (!d) { window.toast('Vyber deal.', 'chyba'); return; }
      if (!txt.value.trim()) { window.toast('Napíš text príspevku.', 'chyba'); return; }
      if (isNaN(cas) || cas.getTime() < Date.now() - 60000) { window.toast('Čas musí byť v budúcnosti.', 'chyba'); return; }
      await fs.addDoc(U.kol('fb_posty'), { dealId: d.id, title: d.title || '', text: txt.value.trim(), sendAt: cas,
        stav: 'naplanovany', vytvorene: fs.serverTimestamp(), by: HK().email });
      HK().logChange(d.id, 'facebook', `${d.title} — príspevok ${U.casDlhy(cas)}`);
      window.toast(`Príspevok naplánovaný na ${U.casDlhy(cas)}.`);
    }));
    fs.onSnapshot(fs.query(U.kol('fb_posty'), fs.orderBy('vytvorene', 'desc'), fs.limit(150)), s => {
      fb.posty = s.docs.map(d => ({ ...d.data(), id: d.id }));
      this._kresli(el);
    }, e => console.warn('fb_posty:', e));
    this._zoznam();
    if (sel.options.length) { sel.selectedIndex = 0; txt.value = textPrispevku(deal()); }
    nahlad();
  },
  _kresli(el) {
    const plan = fb.posty.filter(p => p.stav === 'naplanovany').sort((a, b) => U.naDatum(a.sendAt) - U.naDatum(b.sendAt));
    el.querySelector('#fb-plan').innerHTML = plan.length ? plan.map(p => `<div class="fb-riadok">
        <div class="fb-kedy"><b>${esc(U.casDlhy(p.sendAt))}</b><small>${za(p.sendAt)}</small></div>
        <div class="fb-obs"><b>${esc(p.title || '')}</b><small>${esc((p.text || '').split('\n').slice(1, 3).join(' · '))}</small></div>
        <div class="tl-rad"><button class="btn" data-fba="uprav" data-id="${esc(p.id)}">Upraviť</button>
          <button class="btn btn-reject" data-fba="zrus" data-id="${esc(p.id)}">Zrušiť</button></div></div>`).join('')
      : '<p class="vis-empty">Nič nie je naplánované.</p>';
    const hist = fb.posty.filter(p => p.stav !== 'naplanovany').slice(0, 60);
    const STAV = { odoslany: ['badge-approved', 'Odoslané'], chyba: ['badge-rejected', 'Chyba'], zruseny: ['badge-archived', 'Zrušené'] };
    el.querySelector('#fb-hist').innerHTML = hist.length ? hist.map(p => {
      const [tr, t] = STAV[p.stav] || ['badge-archived', p.stav];
      return `<tr><td class="nowrap">${esc(U.cas(p.odoslane || p.sendAt || p.vytvorene))}</td>
        <td><b>${esc(p.title || '')}</b>${p.auto ? ' <span class="badge badge-archived">automaticky</span>' : ''}${p.chyba ? `<small class="chyba-t">${esc(p.chyba)}</small>` : ''}</td>
        <td><span class="badge ${tr}">${t}</span></td>
        <td class="r">${p.postId ? `<a class="btn btn-ic" href="https://www.facebook.com/${esc(p.postId)}" target="_blank" rel="noopener" title="Otvoriť na Facebooku"><svg class="ix"><use href="#ix-external"></use></svg></a>` : ''}</td></tr>`;
    }).join('') : '<tr><td colspan="4" class="vis-empty">Zatiaľ žiadne príspevky.</td></tr>';
    U.upozornenia('facebook', fb.posty.filter(p => p.stav === 'chyba' && U.naDatum(p.sendAt || p.vytvorene) > Date.now() - 3 * 86400000)
      .map(p => ({ text: `Príspevok na Facebook zlyhal: ${p.title || ''}`, href: '#facebook', typ: 'chyba' })));
  },
  show() { if (this._zoznam) this._zoznam(); },
});

// ═══════════════════════════════════════════════════════════════════
// UTM odkazy
// ═══════════════════════════════════════════════════════════════════
const CIELE = [['', 'Dealy (hlavná stránka)'], ['letenky', 'Letenky'], ['kody', 'Kupóny'], ['potraviny', 'Potraviny'], ['letaky', 'Letáky'], ['deal', 'Konkrétny deal'], ['vlastny', 'Vlastná adresa']];
const utm = { odkazy: [], obd: null };
function vykonKampane(source, campaign, r) {
  const v = HK().visits.filter(x => x.utmcampaign === campaign && (!source || x.utmsource === source) && (!r || (x.date >= r.od && x.date <= r.do)));
  const ludia = new Set(v.map(x => x.uid).filter(Boolean)).size;
  const kliky = v.reduce((a, x) => a + (x.clicks || 0), 0);
  const sKlikom = v.filter(x => (x.clicks || 0) > 0).length;
  return { navstev: v.length, ludia, kliky, miera: v.length ? Math.round(sKlikom / v.length * 100) : 0 };
}
U.stranka('utm', {
  obnov: ['hk:visits'],
  init(el) {
    el.innerHTML = `
      <div class="karta">
        <h3 class="karta-nadpis">Nový odkaz</h3>
        <form class="form-mriezka" id="utm-form" autocomplete="off">
          <label>Kam má odkaz viesť<select name="ciel">${CIELE.map(([k, t]) => `<option value="${k}">${t}</option>`).join('')}</select></label>
          <label class="utm-deal" hidden>Deal<select name="deal"></select></label>
          <label class="utm-vlastny cela" hidden>Adresa na henkukaj.sk<input name="vlastny" type="url" placeholder="https://henkukaj.sk/…"></label>
          <label>Zdroj (utm_source)<input name="source" list="utm-zdroje" placeholder="facebook" required></label>
          <label>Médium (utm_medium)<input name="medium" list="utm-media" placeholder="social"></label>
          <label>Kampaň (utm_campaign)<input name="campaign" placeholder="vianoce-2026" required></label>
          <label>Názov pre teba<input name="nazov" placeholder="Príspevok v skupine Zľavy SK"></label>
        </form>
        <datalist id="utm-zdroje">${['facebook', 'instagram', 'tiktok', 'google', 'newsletter', 'telegram', 'whatsapp', 'youtube', 'reddit', 'partner'].map(x => `<option value="${x}">`).join('')}</datalist>
        <datalist id="utm-media">${['social', 'cpc', 'email', 'referral', 'video', 'qr', 'banner'].map(x => `<option value="${x}">`).join('')}</datalist>
        <div class="utm-vysl"><code id="utm-url">—</code>
          <button class="btn" id="utm-kopiruj" type="button"><svg class="ix"><use href="#ix-copy"></use></svg> Kopírovať</button>
          <button class="btn btn-save" id="utm-uloz" type="button"><svg class="ix"><use href="#ix-save"></use></svg> Uložiť do zoznamu</button></div>
        <p class="settings-hint">Hodnoty píš malými písmenami bez medzier (medzery a diakritiku upravím sám). Stránka si zapamätá
          zdroj, médium a kampaň pri každej návšteve – výsledky vidíš nižšie aj v Návštevnosti.</p>
      </div>
      <div class="karta"><div class="riadok-pole"><h3 class="karta-nadpis" style="flex:1;margin:0">Výsledky odkazov</h3></div>
        <div id="utm-obd"></div>
        <div class="tab-wrap"><table class="tab"><thead><tr><th>Odkaz</th><th>Zdroj / kampaň</th><th class="n">Návštev</th><th class="n">Ľudí</th>
          <th class="n">Preklikov</th><th class="n">Preklikovosť</th><th></th></tr></thead><tbody id="utm-telo"></tbody></table></div>
        <h3 class="karta-nadpis" style="margin-top:18px">Ostatné kampane z návštev</h3>
        <div class="tab-wrap"><table class="tab"><thead><tr><th>Kampaň</th><th>Zdroj</th><th class="n">Návštev</th><th class="n">Preklikov</th><th class="n">Preklikovosť</th></tr></thead><tbody id="utm-ine"></tbody></table></div>
      </div>`;
    const form = el.querySelector('#utm-form'), f = n => form.elements[n];
    const slug = t => U.norm(t).trim().replace(/[^a-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);
    const url = () => {
      const ciel = f('ciel').value;
      let zak = 'https://henkukaj.sk/', hash = ciel && !['deal', 'vlastny'].includes(ciel) ? '#' + ciel : '';
      if (ciel === 'deal') { const d = HK().deals.find(x => x.id === f('deal').value); if (d) zak = U.adresaDealu(d); }
      if (ciel === 'vlastny') { const v = f('vlastny').value.trim(); if (/^https:\/\/(www\.)?henkukaj\.sk/i.test(v)) { const x = new URL(v); hash = x.hash; x.hash = ''; zak = x.toString(); } }
      const p = new URLSearchParams();
      if (slug(f('source').value)) p.set('utm_source', slug(f('source').value));
      if (slug(f('medium').value)) p.set('utm_medium', slug(f('medium').value));
      if (slug(f('campaign').value)) p.set('utm_campaign', slug(f('campaign').value));
      return zak + (zak.includes('?') ? '&' : '?') + p.toString() + hash;
    };
    const obnov = () => {
      f('deal').closest('label').hidden = f('ciel').value !== 'deal';
      f('vlastny').closest('label').hidden = f('ciel').value !== 'vlastny';
      el.querySelector('#utm-url').textContent = slug(f('source').value) && slug(f('campaign').value) ? url() : 'Vyplň zdroj a kampaň…';
    };
    f('deal').innerHTML = HK().deals.filter(d => d.status === 'approved' && !d.expired)
      .sort((a, b) => (U.naDatum(b.timestamp) || 0) - (U.naDatum(a.timestamp) || 0)).slice(0, 100)
      .map(d => `<option value="${esc(d.id)}">${esc(d.title)}</option>`).join('');
    form.addEventListener('input', obnov);
    obnov();
    el.querySelector('#utm-kopiruj').onclick = () => { if (slug(f('source').value) && slug(f('campaign').value)) U.kopiruj(url()); };
    el.querySelector('#utm-uloz').onclick = e => U.akcia(e.currentTarget, async () => {
      if (!slug(f('source').value) || !slug(f('campaign').value)) { window.toast('Vyplň zdroj a kampaň.', 'chyba'); return; }
      await fs.addDoc(U.kol('utm_odkazy'), { url: url(), nazov: f('nazov').value.trim() || slug(f('campaign').value),
        source: slug(f('source').value), medium: slug(f('medium').value), campaign: slug(f('campaign').value),
        vytvorene: fs.serverTimestamp(), by: HK().email });
      U.kopiruj(url());
      window.toast('Odkaz uložený a skopírovaný.');
      await this._nacitaj(el);
    });
    el.addEventListener('click', async e => {
      const b = e.target.closest('[data-utm]');
      if (!b) return;
      const o = utm.odkazy.find(x => x.id === b.dataset.id);
      if (b.dataset.utm === 'kopia') U.kopiruj(o.url);
      if (b.dataset.utm === 'zmaz' && await window.potvrd('Odstrániť odkaz zo zoznamu? (Návštevy z neho ostanú v štatistikách.)')) {
        await fs.deleteDoc(U.ref('utm_odkazy', o.id));
        await this._nacitaj(el);
      }
    });
    utm.obd = U.obdobie(el.querySelector('#utm-obd'), () => this.show(el), '90');
    return this._nacitaj(el);
  },
  async _nacitaj(el) {
    const s = await fs.getDocs(fs.query(U.kol('utm_odkazy'), fs.orderBy('vytvorene', 'desc')));
    utm.odkazy = s.docs.map(d => ({ ...d.data(), id: d.id }));
    this.show(el);
  },
  show(el) {
    if (!utm.obd) return;
    const r = utm.obd.rozsah();
    el.querySelector('#utm-telo').innerHTML = utm.odkazy.length ? utm.odkazy.map(o => {
      const v = vykonKampane(o.source, o.campaign, r);
      return `<tr><td><b>${esc(o.nazov)}</b><small class="utm-maly">${esc(o.url)}</small></td>
        <td>${esc(o.source)}${o.medium ? ' / ' + esc(o.medium) : ''}<small>${esc(o.campaign)}</small></td>
        <td class="n">${v.navstev}</td><td class="n">${v.ludia}</td><td class="n">${v.kliky}</td><td class="n">${v.miera} %</td>
        <td class="r nowrap"><button class="btn btn-ic" data-utm="kopia" data-id="${esc(o.id)}" title="Kopírovať"><svg class="ix"><use href="#ix-copy"></use></svg></button>
          <button class="btn btn-ic btn-delete" data-utm="zmaz" data-id="${esc(o.id)}" title="Odstrániť"><svg class="ix"><use href="#ix-trash"></use></svg></button></td></tr>`;
    }).join('') : '<tr><td colspan="7" class="vis-empty">Zatiaľ žiadne uložené odkazy.</td></tr>';
    const ulozene = new Set(utm.odkazy.map(o => o.source + '|' + o.campaign));
    const skup = {};
    HK().visits.filter(v => v.utmcampaign && v.date >= r.od && v.date <= r.do).forEach(v => {
      const k = (v.utmsource || '') + '|' + v.utmcampaign;
      if (!ulozene.has(k)) skup[k] = true;
    });
    const ine = Object.keys(skup).map(k => { const [s, c] = k.split('|'); return { s, c, ...vykonKampane(s, c, r) }; }).sort((a, b) => b.navstev - a.navstev);
    el.querySelector('#utm-ine').innerHTML = ine.length ? ine.map(x => `<tr><td>${esc(x.c)}</td><td>${esc(x.s || '–')}</td>
        <td class="n">${x.navstev}</td><td class="n">${x.kliky}</td><td class="n">${x.miera} %</td></tr>`).join('')
      : '<tr><td colspan="5" class="vis-empty">Žiadne ďalšie kampane v tomto období.</td></tr>';
  },
});

// ═══════════════════════════════════════════════════════════════════
// SEO
// ═══════════════════════════════════════════════════════════════════
const seo = { sitemap: null, robots: '', chyba: '' };
U.stranka('seo', {
  obnov: ['hk:deals', 'hk:clicks'],
  async init(el) {
    el.innerHTML = `<div class="kpi-row" id="seo-kpi"></div>
      <div class="seo-mriezka">
        <div class="karta"><h3 class="karta-nadpis">Sitemap a robots.txt</h3><div id="seo-sm"></div></div>
        <div class="karta"><h3 class="karta-nadpis">Nástroje Google</h3>
          <div class="seo-odkazy">
            <a class="btn" href="https://search.google.com/search-console?resource_id=sc-domain%3Ahenkukaj.sk" target="_blank" rel="noopener"><svg class="ix"><use href="#ix-external"></use></svg> Search Console</a>
            <a class="btn" href="https://pagespeed.web.dev/analysis?url=https%3A%2F%2Fhenkukaj.sk%2F" target="_blank" rel="noopener"><svg class="ix"><use href="#ix-external"></use></svg> PageSpeed Insights</a>
            <a class="btn" id="seo-rich" href="https://search.google.com/test/rich-results" target="_blank" rel="noopener"><svg class="ix"><use href="#ix-external"></use></svg> Test rozšírených výsledkov</a>
          </div>
          <p class="settings-hint">Search Console ukáže, ktoré stránky Google naozaj zaindexoval a na aké hľadania sa zobrazujú.</p></div>
      </div>
      <div class="karta"><h3 class="karta-nadpis">Na opravu</h3><div class="tabs" id="seo-tabs"></div><div id="seo-zoz"></div></div>
      <div class="karta"><h3 class="karta-nadpis">Najúspešnejšie dealy (prekliky)</h3><div id="seo-top"></div></div>`;
    el.addEventListener('click', e => {
      const t = e.target.closest('[data-seo]');
      if (t) { this._tab = t.dataset.seo; this.show(el); return; }
      const d = e.target.closest('[data-deal]');
      if (d) { e.preventDefault(); HK().otvorDeal(d.dataset.deal); }
    });
    try {
      const [sm, rb] = await Promise.all([fetch('sitemap.xml?t=' + Date.now()).then(r => r.text()), fetch('robots.txt?t=' + Date.now()).then(r => r.text())]);
      const x = new DOMParser().parseFromString(sm, 'application/xml');
      seo.sitemap = [...x.getElementsByTagName('url')].map(u => ({
        loc: (u.getElementsByTagName('loc')[0] || {}).textContent || '',
        lastmod: (u.getElementsByTagName('lastmod')[0] || {}).textContent || '',
      }));
      seo.robots = rb;
    } catch (e) { seo.chyba = e.message; }
  },
  _tab: 'popis',
  show(el) {
    const dealy = HK().deals.filter(d => d.status === 'approved');
    const sm = seo.sitemap || [];
    const vSm = new Set(sm.map(u => (u.loc.match(/-([A-Za-z0-9]{20})\/$/) || [])[1]).filter(Boolean));
    const dnes = U.dnesIso();
    const exp = d => d.expired || (d.validUntilISO && d.validUntilISO < dnes);
    const dniPo = d => {
      const od = d.validUntilISO ? new Date(d.validUntilISO + 'T12:00:00') : U.naDatum(d.timestamp);
      return od ? Math.floor((Date.now() - od.getTime()) / 86400000) : 0;
    };
    const noindex = dealy.filter(d => exp(d) && dniPo(d) > 30);
    const bezStranky = dealy.filter(d => !vSm.has(d.id) && !noindex.includes(d));
    const bezPopisu = dealy.filter(d => !exp(d) && (d.description || '').trim().length < 50);
    const dlhyNazov = dealy.filter(d => !exp(d) && (d.title || '').length > 70);
    const bezFotky = dealy.filter(d => !exp(d) && !d.imageUrl);
    const posl = sm.map(u => u.lastmod).filter(Boolean).sort().pop();
    el.querySelector('#seo-kpi').innerHTML =
      U.kpi('Adries v sitemape', seo.sitemap ? sm.length : '–', '', posl ? `aktualizované ${U.den(posl + 'T12:00:00')}` : '') +
      U.kpi('Stránok dealov', vSm.size, '', `zverejnených dealov: ${dealy.length}`) +
      U.kpi('S noindex', noindex.length, '', 'skončené pred 30+ dňami') +
      U.kpi('Bez stránky', bezStranky.length, '', 'vygenerujú sa do hodiny');
    const rb = seo.robots || '';
    el.querySelector('#seo-sm').innerHTML = seo.chyba ? `<div class="hlaska chyba">Sitemap sa nepodarilo načítať: ${esc(seo.chyba)}</div>` : `
      <ul class="seo-check">
        <li class="${sm.length ? 'ok' : 'zle'}">sitemap.xml – ${sm.length} adries <a href="sitemap.xml" target="_blank" rel="noopener">otvoriť</a></li>
        <li class="${/sitemap:\s*https:\/\/henkukaj\.sk\/sitemap\.xml/i.test(rb) ? 'ok' : 'zle'}">robots.txt odkazuje na sitemap</li>
        <li class="${/disallow:\s*\/admin\.html/i.test(rb) ? 'ok' : 'zle'}">admin je pre vyhľadávače zakázaný</li>
        <li class="${posl && posl >= U.isoPosun(dnes, -2) ? 'ok' : 'zle'}">sitemap je čerstvý (generuje sa každú hodinu)</li>
      </ul>`;
    const T = [['popis', 'Krátky alebo chýbajúci popis', bezPopisu], ['nazov', 'Dlhý názov (nad 70 znakov)', dlhyNazov],
      ['foto', 'Bez fotky', bezFotky], ['noindex', 'S noindex', noindex], ['stranka', 'Bez stránky', bezStranky]];
    el.querySelector('#seo-tabs').innerHTML = T.map(([k, t, z]) => `<button class="tab-btn${this._tab === k ? ' active' : ''}" data-seo="${k}">${t} (${z.length})</button>`).join('');
    const vyber = (T.find(x => x[0] === this._tab) || T[0])[2];
    const POPIS = { popis: 'Popis sa zobrazuje vo výsledkoch Google pod názvom. Aspoň 1 – 2 vety o produkte a cene.',
      nazov: 'Google v výsledkoch ukáže zhruba 60 – 70 znakov, zvyšok odstrihne.', foto: 'Bez fotky Facebook aj Google ukážu len logo.',
      noindex: 'Dlho skončené akcie majú noindex, aby Google neposielal ľudí na neplatné ponuky. Je to v poriadku; staré môžeš archivovať.',
      stranka: 'Stránky dealov generuje úloha každú hodinu a hneď po naplánovanom zverejnení.' }[this._tab];
    el.querySelector('#seo-zoz').innerHTML = `<p class="settings-hint" style="margin-bottom:8px">${POPIS}</p>` + (vyber.length
      ? `<div class="tab-wrap"><table class="tab"><tbody>${vyber.slice(0, 60).map(d => `<tr>
          <td><a href="#" class="odkaz" data-deal="${esc(d.id)}">${esc(d.title)}</a><small>${esc(d.store || '')} · ${(d.title || '').length} znakov · popis ${(d.description || '').length} znakov</small></td>
          <td class="r nowrap"><a class="btn btn-ic" href="${esc(U.adresaDealu(d))}" target="_blank" rel="noopener" title="Stránka dealu"><svg class="ix"><use href="#ix-external"></use></svg></a>
            <button class="btn" data-deal="${esc(d.id)}"><svg class="ix"><use href="#ix-pencil"></use></svg> Upraviť</button></td></tr>`).join('')}</tbody></table></div>`
      : '<p class="vis-empty">Nič na opravu.</p>');
    const top = dealy.map(d => [d, HK().clicks[d.id] || 0]).filter(x => x[1]).sort((a, b) => b[1] - a[1]).slice(0, 10);
    el.querySelector('#seo-top').innerHTML = U.pruhy(top.map(([d, n]) => [d.title, n,
      `<a href="${esc(U.adresaDealu(d))}" target="_blank" rel="noopener" title="Stránka dealu"><svg class="ix"><use href="#ix-external"></use></svg></a>`]),
      { prazdne: 'Zatiaľ žiadne prekliky.' });
    if (top[0]) el.querySelector('#seo-rich').href = 'https://search.google.com/test/rich-results?url=' + encodeURIComponent(U.adresaDealu(top[0][0]));
  },
});
