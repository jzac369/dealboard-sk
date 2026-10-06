// ── Analytika: najlepší obsah, hľadania, používanie funkcií ──────────
const U = window.HKU, HK = () => window.HK, { fs, esc } = U;

function dniVRozsahu(od, doD) {
  const z = [];
  for (let d = od; d <= doD; d = U.isoPosun(d, 1)) z.push(d);
  return z.length > 400 ? z.slice(-400) : z;
}
const kratkyDen = iso => `${Number(iso.slice(8))}. ${Number(iso.slice(5, 7))}.`;

// ═══════════════════════════════════════════════════════════════════
// Najlepší obsah (prekliky po dňoch z kliky_den)
// ═══════════════════════════════════════════════════════════════════
const top = { obd: null };
function druhKluca(k) { return k.startsWith('letenky-') ? 'letenky' : (k.startsWith('reklama-') ? 'reklama' : 'deal'); }
U.stranka('top', {
  obnov: ['hk:deals'],
  init(el) {
    el.innerHTML = `<div id="top-obd"></div><div id="top-info"></div>
      <div class="kpi-row" id="top-kpi"></div>
      <div class="karta"><h3 class="karta-nadpis">Prekliky po dňoch</h3><div id="top-graf"></div></div>
      <div class="dve-karty">
        <div class="karta"><h3 class="karta-nadpis">Dealy</h3><div id="top-dealy"></div></div>
        <div class="karta"><h3 class="karta-nadpis">Obchody</h3><div id="top-obchody"></div></div>
        <div class="karta"><h3 class="karta-nadpis">Kategórie</h3><div id="top-kat"></div></div>
        <div class="karta"><h3 class="karta-nadpis">Letenky – trasy</h3><div id="top-let"></div></div>
      </div>`;
    el.addEventListener('click', e => { const a = e.target.closest('[data-deal]'); if (a) { e.preventDefault(); HK().otvorDeal(a.dataset.deal); } });
    top.obd = U.obdobie(el.querySelector('#top-obd'), () => this.show(el), '30');
  },
  async show(el) {
    const r = top.obd.rozsah();
    let dni, pred;
    try {
      [dni, pred] = await Promise.all([U.dni('kliky_den', r.od, r.do), U.dni('kliky_den', r.predOd, r.predDo)]);
    } catch (e) { el.querySelector('#top-info').innerHTML = `<div class="hlaska chyba">${esc(e.message)}</div>`; return; }
    const sucet = {}, poDnoch = {};
    Object.entries(dni).forEach(([den, m]) => Object.entries(m).forEach(([k, v]) => {
      v = Number(v) || 0;
      sucet[k] = (sucet[k] || 0) + v;
      const p = poDnoch[den] = poDnoch[den] || { deal: 0, letenky: 0, reklama: 0 };
      p[druhKluca(k)] += v;
    }));
    const spoluPred = Object.values(pred).reduce((a, m) => a + Object.values(m).reduce((b, v) => b + (Number(v) || 0), 0), 0);
    const nieje = !Object.keys(dni).length;
    // Bez denných dát (pred spustením merania) aspoň súčty za celé obdobie.
    if (nieje) Object.entries(HK().clicks).forEach(([k, v]) => { sucet[k] = v; });
    el.querySelector('#top-info').innerHTML = nieje ? `<div class="hlaska info">Za toto obdobie ešte nie sú prekliky po dňoch
      (merajú sa od 1. 10. 2026). Nižšie sú súčty za celé obdobie od spustenia stránky.</div>` : '';
    const podla = d => Object.entries(sucet).filter(([k]) => druhKluca(k) === d);
    const spolu = Object.values(sucet).reduce((a, v) => a + v, 0);
    const naDealy = podla('deal').reduce((a, [, v]) => a + v, 0);
    el.querySelector('#top-kpi').innerHTML =
      U.kpi('Prekliky spolu', U.cislo(spolu), nieje ? '' : U.zmena(spolu, spoluPred)) +
      U.kpi('Na dealy', U.cislo(naDealy), '', `${podla('deal').length} rôznych dealov`) +
      U.kpi('Na letenky', U.cislo(podla('letenky').reduce((a, [, v]) => a + v, 0))) +
      U.kpi('Na reklamy', U.cislo(podla('reklama').reduce((a, [, v]) => a + v, 0)));
    const osa = dniVRozsahu(r.od, r.do).slice(-90);
    el.querySelector('#top-graf').innerHTML = nieje ? '<p class="vis-empty">Graf sa ukáže, keď pribudnú prekliky po dňoch.</p>' :
      U.stlpce(osa.map(kratkyDen), [
        { n: 'Dealy', farba: '#E8590C', hodnoty: osa.map(d => (poDnoch[d] || {}).deal || 0) },
        { n: 'Letenky', farba: '#1A56C4', hodnoty: osa.map(d => (poDnoch[d] || {}).letenky || 0) },
        { n: 'Reklamy', farba: '#8A5A00', hodnoty: osa.map(d => (poDnoch[d] || {}).reklama || 0) },
      ]);
    const dealy = Object.fromEntries(HK().deals.map(d => [d.id, d]));
    const tDealy = podla('deal').sort((a, b) => b[1] - a[1]).slice(0, 12).map(([id, v]) => {
      const d = dealy[id];
      return [d ? d.title : '(vymazaný deal)', v, d ? `<a href="#" data-deal="${esc(id)}" title="Otvoriť v admine"><svg class="ix"><use href="#ix-external"></use></svg></a>` : ''];
    });
    el.querySelector('#top-dealy').innerHTML = U.pruhy(tDealy, { prazdne: 'Žiadne prekliky.' });
    const agr = fn => {
      const m = {};
      podla('deal').forEach(([id, v]) => { const d = dealy[id]; const k = d ? fn(d) : null; if (k) m[k] = (m[k] || 0) + v; });
      return Object.entries(m).sort((a, b) => b[1] - a[1]);
    };
    el.querySelector('#top-obchody').innerHTML = U.pruhy(agr(d => d.store || U.host(d.url)), { prazdne: 'Žiadne prekliky.' });
    el.querySelector('#top-kat').innerHTML = U.pruhy(agr(d => d.category || 'Iné'), { prazdne: 'Žiadne prekliky.' });
    el.querySelector('#top-let').innerHTML = U.pruhy(podla('letenky').sort((a, b) => b[1] - a[1])
      .map(([k, v]) => [k.slice(8).replace('-', ' → '), v]), { prazdne: 'Žiadne prekliky na letenky.' });
  },
});

// ═══════════════════════════════════════════════════════════════════
// Čo ľudia hľadajú
// ═══════════════════════════════════════════════════════════════════
const hl = { obd: null, sekcia: '', data: [], kluc: '' };
const SEKCIE = { '': 'Všade', dealy: 'Dealy', kody: 'Kupóny', potraviny: 'Potraviny' };
U.stranka('hladania', {
  init(el) {
    el.innerHTML = `<div id="hl-obd"></div>
      <div class="kpi-row" id="hl-kpi"></div>
      <div class="tabs" id="hl-tabs"></div>
      <div class="dve-karty">
        <div class="karta"><h3 class="karta-nadpis">Najčastejšie hľadania</h3><div id="hl-top"></div></div>
        <div class="karta"><h3 class="karta-nadpis">Bez výsledku – námety na dealy</h3>
          <p class="settings-hint" style="margin-bottom:8px">Toto ľudia hľadali a nenašli. Keď nájdeš dobrý deal, pridaj ho.</p><div id="hl-nic"></div></div>
      </div>
      <div class="karta"><h3 class="karta-nadpis">Hľadania po dňoch</h3><div id="hl-graf"></div></div>
      <p class="settings-hint">Ukladá sa len text hľadania, sekcia a počet výsledkov – nič, čo by identifikovalo človeka.
        To isté hľadanie sa počíta raz za návštevu.</p>`;
    el.addEventListener('click', e => {
      const t = e.target.closest('[data-hls]');
      if (t) { hl.sekcia = t.dataset.hls; this._kresli(el); }
    });
    hl.obd = U.obdobie(el.querySelector('#hl-obd'), () => this.show(el), '30');
  },
  async show(el) {
    const r = hl.obd.rozsah();
    const kluc = r.predOd + r.do;
    if (hl.kluc !== kluc) {
      try {
        const s = await fs.getDocs(fs.query(U.kol('hladania'), fs.where('date', '>=', r.predOd), fs.where('date', '<=', r.do)));
        hl.data = s.docs.map(d => d.data());
        hl.kluc = kluc; hl.r = r;
      } catch (e) { el.querySelector('#hl-kpi').innerHTML = `<div class="hlaska chyba">${esc(e.message)}</div>`; return; }
    }
    this._kresli(el);
  },
  _kresli(el) {
    const r = hl.r;
    const vSekcii = x => !hl.sekcia || x.sekcia === hl.sekcia;
    const teraz = hl.data.filter(x => x.date >= r.od && vSekcii(x)), pred = hl.data.filter(x => x.date < r.od && vSekcii(x));
    const skup = {};
    teraz.forEach(x => {
      const k = U.norm(x.q).replace(/\s+/g, ' ').trim();
      const g = skup[k] = skup[k] || { q: x.q, n: 0, vysl: 0, nic: 0, sekcie: new Set() };
      g.n++; g.vysl += x.pocet || 0; if (!x.pocet) g.nic++; g.sekcie.add(x.sekcia);
    });
    const zoz = Object.values(skup).sort((a, b) => b.n - a.n);
    const nic = teraz.filter(x => !x.pocet).length;
    el.querySelector('#hl-kpi').innerHTML =
      U.kpi('Hľadaní', U.cislo(teraz.length), U.zmena(teraz.length, pred.length)) +
      U.kpi('Rôznych výrazov', U.cislo(zoz.length)) +
      U.kpi('Bez výsledku', teraz.length ? Math.round(nic / teraz.length * 100) + ' %' : '–', '', `${nic} hľadaní`);
    el.querySelector('#hl-tabs').innerHTML = Object.entries(SEKCIE).map(([k, t]) =>
      `<button class="tab-btn${hl.sekcia === k ? ' active' : ''}" data-hls="${k}">${t}</button>`).join('');
    el.querySelector('#hl-top').innerHTML = U.pruhy(zoz.map(g => [g.q, g.n, `<small>Ø ${Math.round(g.vysl / g.n)} výsl.</small>`]), { max: 25, prazdne: 'Zatiaľ nikto nič nehľadal.' });
    const bez = zoz.filter(g => g.nic).sort((a, b) => b.nic - a.nic);
    el.querySelector('#hl-nic').innerHTML = bez.length ? `<div class="tab-wrap"><table class="tab"><tbody>${bez.slice(0, 25).map(g => `<tr>
        <td><b>${esc(g.q)}</b><small>${[...g.sekcie].map(s => SEKCIE[s] || s).join(', ')}</small></td><td class="n">${g.nic}×</td>
        <td class="r"><a class="btn" href="#pridat"><svg class="ix"><use href="#ix-plus"></use></svg> Pridať deal</a></td></tr>`).join('')}</tbody></table></div>`
      : '<p class="vis-empty">Všetko, čo ľudia hľadali, aj našli.</p>';
    const osa = dniVRozsahu(r.od, r.do).slice(-90);
    const poDnoch = {}, nicDen = {};
    teraz.forEach(x => { poDnoch[x.date] = (poDnoch[x.date] || 0) + 1; if (!x.pocet) nicDen[x.date] = (nicDen[x.date] || 0) + 1; });
    el.querySelector('#hl-graf').innerHTML = U.stlpce(osa.map(kratkyDen), [
      { n: 'S výsledkom', farba: '#1A56C4', hodnoty: osa.map(d => (poDnoch[d] || 0) - (nicDen[d] || 0)) },
      { n: 'Bez výsledku', farba: '#C0392B', hodnoty: osa.map(d => nicDen[d] || 0) },
    ]);
  },
});

// ═══════════════════════════════════════════════════════════════════
// Používanie funkcií
// ═══════════════════════════════════════════════════════════════════
const NAZVY = {
  zalozka_deals: 'Dealy', zalozka_coupons: 'Kupóny', zalozka_food: 'Potraviny', zalozka_leaflets: 'Letáky', zalozka_flights: 'Letenky',
  letenky_filter_z: 'Odkiaľ', letenky_filter_druh: 'Kam (mesto / more)', letenky_filter_cena: 'Rozpočet', letenky_filter_kedy: 'Kedy',
  letenky_filter_typ: 'Dĺžka cesty', letenky_filter_mesiac: 'Mesiac odletu', letenky_rezervacia: 'Klik na Rezervovať',
  preklik_deal: 'Preklik na deal', kategoria: 'Výber kategórie', triedenie_new: 'Triedenie: najnovšie', triedenie_votes: 'Triedenie: najhorúcejšie',
  triedenie_discount: 'Triedenie: najväčšia zľava', pridaj_deal_otvorenie: 'Otvorenie „Pridaj deal“', kod_kopirovanie: 'Skopírovanie kódu',
  ucet_otvorenie: 'Otvorenie účtu', hladanie_dealy: 'Hľadanie v dealoch', hladanie_kody: 'Hľadanie v kódoch', hladanie_potraviny: 'Hľadanie v potravinách',
  reklama_klik: 'Klik na reklamu',
};
const SKUPINY = [
  ['Záložky', k => k.startsWith('zalozka_')],
  ['Dealy', k => ['preklik_deal', 'kategoria', 'pridaj_deal_otvorenie'].includes(k) || k.startsWith('triedenie_')],
  ['Letenky', k => k.startsWith('letenky_')],
  ['Hľadanie', k => k.startsWith('hladanie_')],
  ['Ostatné', () => true],
];
const pz = { obd: null };
U.stranka('pouzivanie', {
  init(el) {
    el.innerHTML = `<div id="pz-obd"></div><div class="kpi-row" id="pz-kpi"></div>
      <div class="karta"><h3 class="karta-nadpis">Aktivita po dňoch</h3><div id="pz-graf"></div></div>
      <div class="dve-karty" id="pz-skupiny"></div>
      <p class="settings-hint">Počíta sa, koľkokrát ľudia funkciu použili (nie koľko ľudí). Meria sa od 1. 10. 2026.</p>`;
    pz.obd = U.obdobie(el.querySelector('#pz-obd'), () => this.show(el), '30');
  },
  async show(el) {
    const r = pz.obd.rozsah();
    let dni, pred;
    try { [dni, pred] = await Promise.all([U.dni('pouzitie', r.od, r.do), U.dni('pouzitie', r.predOd, r.predDo)]); }
    catch (e) { el.querySelector('#pz-kpi').innerHTML = `<div class="hlaska chyba">${esc(e.message)}</div>`; return; }
    const sucet = {}, spoluDen = {};
    Object.entries(dni).forEach(([den, m]) => Object.entries(m).forEach(([k, v]) => {
      sucet[k] = (sucet[k] || 0) + (Number(v) || 0);
      spoluDen[den] = (spoluDen[den] || 0) + (Number(v) || 0);
    }));
    const sucetPred = {};
    Object.values(pred).forEach(m => Object.entries(m).forEach(([k, v]) => { sucetPred[k] = (sucetPred[k] || 0) + (Number(v) || 0); }));
    const spolu = Object.values(sucet).reduce((a, v) => a + v, 0), spoluP = Object.values(sucetPred).reduce((a, v) => a + v, 0);
    const zal = Object.entries(sucet).filter(([k]) => k.startsWith('zalozka_')).sort((a, b) => b[1] - a[1])[0];
    const flt = Object.entries(sucet).filter(([k]) => k.startsWith('letenky_filter_')).sort((a, b) => b[1] - a[1])[0];
    el.querySelector('#pz-kpi').innerHTML =
      U.kpi('Akcií spolu', U.cislo(spolu), U.zmena(spolu, spoluP)) +
      U.kpi('Najobľúbenejšia záložka', zal ? esc(NAZVY[zal[0]] || zal[0]) : '–', '', zal ? `${U.cislo(zal[1])}× otvorená` : '') +
      U.kpi('Najpoužívanejší filter leteniek', flt ? esc(NAZVY[flt[0]] || flt[0]) : '–', '', flt ? `${U.cislo(flt[1])}×` : '') +
      U.kpi('Skopírované kódy', U.cislo(sucet.kod_kopirovanie || 0), U.zmena(sucet.kod_kopirovanie || 0, sucetPred.kod_kopirovanie || 0));
    const osa = dniVRozsahu(r.od, r.do).slice(-90);
    el.querySelector('#pz-graf').innerHTML = Object.keys(dni).length
      ? U.stlpce(osa.map(kratkyDen), [{ n: 'Akcie', farba: '#E8590C', hodnoty: osa.map(d => spoluDen[d] || 0) }])
      : '<p class="vis-empty">Za toto obdobie ešte nie sú dáta.</p>';
    const pouzite = new Set();
    el.querySelector('#pz-skupiny').innerHTML = SKUPINY.map(([n, fn]) => {
      const p = Object.entries(sucet).filter(([k]) => !pouzite.has(k) && fn(k)).sort((a, b) => b[1] - a[1]);
      p.forEach(([k]) => pouzite.add(k));
      if (!p.length) return '';
      return `<div class="karta"><h3 class="karta-nadpis">${n}</h3>${U.pruhy(p.map(([k, v]) => [NAZVY[k] || k.replace(/_/g, ' '), v,
        sucetPred[k] !== undefined ? U.zmena(v, sucetPred[k]) : '']), { max: 15 })}</div>`;
    }).join('') || '<div class="karta"><p class="vis-empty">Zatiaľ žiadne dáta.</p></div>';
  },
});
