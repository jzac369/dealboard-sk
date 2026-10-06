// ── Systém: zdravie úloh, nastavenia agenta, záloha, administrátori ───
const U = window.HKU, HK = () => window.HK, { fs, esc } = U;
const REPO = 'jzac369/dealboard-sk';

// ═══════════════════════════════════════════════════════════════════
// Zdravie systému (GitHub Actions)
// ═══════════════════════════════════════════════════════════════════
// Repozitár je verejný, takže zoznam behov sa dá čítať bez tokenu (limit
// 60 dotazov za hodinu z jednej IP - preto výsledok na 2 minúty držíme).
// Spustenie a opakovanie behu robí plánovač (admin_ulohy), lebo na to
// token treba a do stránky nepatrí.
async function behy(znova) {
  try {
    const c = JSON.parse(sessionStorage.getItem('hk_behy') || 'null');
    if (!znova && c && Date.now() - c.t < 120000) return c.d;
  } catch (e) {}
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/runs?per_page=100`, { headers: { Accept: 'application/vnd.github+json' } });
  if (r.status === 403) throw new Error('GitHub dočasne obmedzil počet dotazov – skús o pár minút.');
  if (!r.ok) throw new Error('GitHub odpovedal chybou ' + r.status);
  const d = (await r.json()).workflow_runs || [];
  try { sessionStorage.setItem('hk_behy', JSON.stringify({ t: Date.now(), d })); } catch (e) {}
  return d;
}
const subor = run => (run.path || '').split('/').pop();
const trvanie = run => {
  const s = (new Date(run.updated_at) - new Date(run.run_started_at || run.created_at)) / 1000;
  return s < 60 ? `${Math.round(s)} s` : `${Math.round(s / 60)} min`;
};
function stavBehu(run) {
  if (run.status !== 'completed') return ['bezi', run.status === 'queued' ? 'v rade' : 'beží'];
  if (run.conclusion === 'success') return ['ok', 'v poriadku'];
  if (run.conclusion === 'cancelled' || run.conclusion === 'skipped') return ['nic', run.conclusion === 'cancelled' ? 'zrušený' : 'preskočený'];
  return ['chyba', 'zlyhal'];
}
function upozorneniaZBehov(runs) {
  const z = [];
  const posledne = {};
  runs.forEach(r => { const k = subor(r); if (!posledne[k]) posledne[k] = r; });
  Object.values(posledne).forEach(r => {
    if (stavBehu(r)[0] === 'chyba' && Date.now() - new Date(r.updated_at) < 3 * 86400000)
      z.push({ text: `Úloha „${r.name}“ naposledy zlyhala (${U.pred(r.updated_at)})`, href: '#zdravie', typ: 'chyba' });
  });
  const pl = posledne['planovac.yml'];
  if (pl && pl.status === 'completed' && Date.now() - new Date(pl.updated_at) > 40 * 60000)
    z.push({ text: 'Plánovač nebeží – automatické úlohy sa nespúšťajú', href: '#zdravie', typ: 'chyba' });
  return z;
}
async function skontrolujBehy() {
  if (!HK() || HK().rola !== 'admin') return;
  try { U.upozornenia('github', upozorneniaZBehov(await behy())); } catch (e) { /* bez siete ticho */ }
}

const zd = { ulohy: [] };
U.stranka('zdravie', {
  async init(el) {
    el.innerHTML = `<div class="riadok-pole" style="margin-bottom:12px"><div style="flex:1" id="zd-suhrn"></div>
        <button class="btn" id="zd-obnov"><svg class="ix"><use href="#ix-refresh"></use></svg> Obnoviť</button></div>
      <div class="zd-mriezka" id="zd-ulohy"></div>
      <div class="karta"><h3 class="karta-nadpis">Chyby za posledných 7 dní</h3><div id="zd-chyby"></div></div>
      <div class="karta"><h3 class="karta-nadpis">Úlohy zadané z adminu</h3><div id="zd-admin"></div></div>
      <p class="settings-hint">Spustenie a opakovanie behu vykoná plánovač do pár sekúnd. Podrobný záznam behu otvoríš ikonou vedľa neho.</p>`;
    el.querySelector('#zd-obnov').addEventListener('click', e => U.akcia(e.currentTarget, () => this.show(el, true)));
    el.addEventListener('click', async e => {
      const b = e.target.closest('[data-zd]');
      if (!b) return;
      await U.akcia(b, async () => {
        if (b.dataset.zd === 'spust') {
          await U.uloha('spusti_workflow', { workflow: b.dataset.wf }, () => {});
          window.toast('Úloha spustená. Objaví sa tu o chvíľu.');
        } else {
          await U.uloha('zopakuj_beh', { runId: b.dataset.run }, () => {});
          window.toast('Neúspešné časti behu sa spúšťajú znova.');
        }
        setTimeout(() => this.show(el, true), 8000);
      });
    });
    fs.onSnapshot(fs.query(U.kol('admin_ulohy'), fs.orderBy('vytvorene', 'desc'), fs.limit(15)), s => {
      zd.ulohy = s.docs.map(d => ({ ...d.data(), id: d.id }));
      const TYP = { nacitaj_url: 'Načítanie odkazu', kontrola_platnosti: 'Kontrola platnosti', spusti_workflow: 'Spustenie úlohy', zopakuj_beh: 'Opakovanie behu' };
      const ST = { caka: ['badge-pending', 'čaká'], bezi: ['badge-planned', 'beží'], hotovo: ['badge-approved', 'hotovo'], chyba: ['badge-rejected', 'chyba'] };
      const t = el.querySelector('#zd-admin');
      if (t) t.innerHTML = zd.ulohy.length ? `<div class="tab-wrap"><table class="tab"><tbody>${zd.ulohy.map(u => {
        const [tr, tx] = ST[u.stav] || ['badge-archived', u.stav];
        return `<tr><td class="nowrap">${esc(U.cas(u.vytvorene))}</td><td>${esc(TYP[u.typ] || u.typ)}<small>${esc((u.vstup && (u.vstup.url || u.vstup.workflow || u.vstup.runId)) || '')}</small>
          ${u.chyba ? `<small class="chyba-t">${esc(u.chyba)}</small>` : ''}</td><td><span class="badge ${tr}">${tx}</span></td></tr>`;
      }).join('')}</tbody></table></div>` : '<p class="vis-empty">Zatiaľ žiadne.</p>';
    }, () => {});
  },
  async show(el, znova) {
    let runs;
    try { runs = await behy(znova); }
    catch (e) { el.querySelector('#zd-suhrn').innerHTML = `<div class="hlaska chyba">${esc(e.message)}</div>`; return; }
    U.upozornenia('github', upozorneniaZBehov(runs));
    const podla = {};
    runs.forEach(r => { (podla[subor(r)] = podla[subor(r)] || []).push(r); });
    const chybne = Object.values(podla).filter(z => stavBehu(z[0])[0] === 'chyba').length;
    el.querySelector('#zd-suhrn').innerHTML = chybne
      ? `<div class="hlaska chyba"><svg class="ix"><use href="#ix-alert"></use></svg> ${U.sklon(chybne, 'úloha má', 'úlohy majú', 'úloh má')} posledný beh neúspešný.</div>`
      : '<div class="hlaska ok"><svg class="ix"><use href="#ix-check"></use></svg> Všetky úlohy naposledy prebehli v poriadku.</div>';
    el.querySelector('#zd-ulohy').innerHTML = Object.entries(podla).sort((a, b) => a[1][0].name.localeCompare(b[1][0].name, 'sk')).map(([wf, z]) => {
      const p = z[0], [st, stTxt] = stavBehu(p);
      const dokoncene = z.filter(r => r.status === 'completed' && r.conclusion !== 'cancelled' && r.conclusion !== 'skipped').slice(0, 10);
      const ok = dokoncene.filter(r => r.conclusion === 'success').length;
      return `<div class="zd-karta zd-${st}">
        <div class="zd-hlava"><b>${esc(p.name)}</b><span class="zd-stav">${stTxt}</span></div>
        <div class="zd-info">Naposledy ${esc(U.pred(p.run_started_at || p.created_at))}${p.status === 'completed' ? ` · trvanie ${trvanie(p)}` : ''}
          · ${p.event === 'schedule' ? 'podľa cronu' : (p.event === 'workflow_dispatch' ? 'spustené plánovačom / ručne' : esc(p.event))}</div>
        <div class="zd-bodky" title="Posledných ${dokoncene.length} behov: ${ok} v poriadku">${dokoncene.slice().reverse().map(r => `<i class="${r.conclusion === 'success' ? 'ok' : 'chyba'}"></i>`).join('')}
          <small>${dokoncene.length ? Math.round(ok / dokoncene.length * 100) + ' % úspešných' : ''}</small></div>
        <div class="tl-rad">
          ${['planovac.yml', 'pages-build-deployment'].includes(wf) || !wf.endsWith('.yml') ? '' : `<button class="btn" data-zd="spust" data-wf="${esc(wf)}"><svg class="ix"><use href="#ix-play"></use></svg> Spustiť</button>`}
          ${st === 'chyba' ? `<button class="btn" data-zd="opakuj" data-run="${p.id}"><svg class="ix"><use href="#ix-refresh"></use></svg> Zopakovať</button>` : ''}
          <a class="btn btn-ic" href="${esc(p.html_url)}" target="_blank" rel="noopener" title="Záznam behu na GitHube"><svg class="ix"><use href="#ix-external"></use></svg></a></div>
      </div>`;
    }).join('');
    const tyzden = runs.filter(r => stavBehu(r)[0] === 'chyba' && Date.now() - new Date(r.updated_at) < 7 * 86400000);
    el.querySelector('#zd-chyby').innerHTML = tyzden.length ? `<div class="tab-wrap"><table class="tab"><tbody>${tyzden.map(r => `<tr>
        <td class="nowrap">${esc(U.cas(r.updated_at))}</td><td><b>${esc(r.name)}</b><small>${esc(r.display_title || '')}</small></td>
        <td class="r nowrap"><button class="btn" data-zd="opakuj" data-run="${r.id}">Zopakovať</button>
          <a class="btn btn-ic" href="${esc(r.html_url)}" target="_blank" rel="noopener" title="Záznam behu"><svg class="ix"><use href="#ix-external"></use></svg></a></td></tr>`).join('')}</tbody></table></div>`
      : '<p class="vis-empty">Žiadne chyby.</p>';
  },
});

// ═══════════════════════════════════════════════════════════════════
// Nastavenia agenta (settings/agent)
// ═══════════════════════════════════════════════════════════════════
const PREDVOLENE_AGENT = {
  zdroje: ['zlacnene', 'feeds', 'shop_feeds'], minZlava: 25, maxZlava: 95, minCena: 15, maxNaBeh: 5, maxNaDen: 10, maxNaObchod: 4,
  znovaPoDnochZverejnene: 7, znovaPoDnochZamietnute: 10,
  maxNaKategoriu: 3, podielObmedzenych: 0.2, feedMinPokles: 20, obmedzeneKategorie: ['Jedlo & Nápoje'], blokovaneKategorie: [],
  vylucenaSlova: ['vzorka', 'vzorky', 'sample'],
};
const NAZVY_ZDROJOV = { zlacnene: 'zlacnene.sk – letáky a akcie', feeds: 'Produktové feedy (Dognet)', shop_feeds: 'Feedy e-shopov' };
const CISLA = [
  ['minZlava', 'Minimálna zľava', '%', 0, 95, 'Pod touto zľavou agent položku ani nezváži.'],
  ['maxZlava', 'Maximálna zľava', '%', 5, 100, 'Nad ňou to býva chyba v dátach, nie deal.'],
  ['minCena', 'Minimálna cena', '€', 0, 100000, 'Odfiltruje drobnosti typu jogurt za 1 €.'],
  ['maxNaBeh', 'Návrhov na jeden beh', '', 1, 50, 'Agent beží dvakrát denne — ráno a večer.'],
  ['maxNaDen', 'Tvrdý strop na deň', '', 1, 100,
   'Viac návrhov za deň nepríde ani pri poruche. Počíta sa v databáze, nie na beh.'],
  ['znovaPoDnochZverejnene', 'Zverejnený deal ponúknuť znova po', 'dňoch', 1, 365,
   'Dovtedy ho agent nenavrhne druhýkrát.'],
  ['znovaPoDnochZamietnute', 'Zamietnutý deal ponúknuť znova po', 'dňoch', 1, 365,
   'Aby sa to, čo si raz zamietol, nevracalo do Telegramu.'],
  ['maxNaObchod', 'Najviac z jedného obchodu', 'na beh', 1, 50, 'Aby výber nevyzeral ako leták jedného reťazca.'],
  ['maxNaKategoriu', 'Najviac z jednej kategórie', 'na beh', 1, 50, ''],
  ['feedMinPokles', 'Pokles ceny vo feede', '%', 0, 95, 'O koľko musí cena klesnúť pod doteraz najnižšiu videnú.'],
];
U.stranka('agent', {
  async init(el) {
    const [n, i] = await Promise.all([fs.getDoc(U.ref('settings', 'agent')), fs.getDoc(U.ref('admin_info', 'agent')).catch(() => null)]);
    const info = i && i.exists() ? i.data() : null;
    const P = { ...PREDVOLENE_AGENT, ...((info && info.predvolene) || {}) };
    const v = { ...P, vypnuteFeedy: [], ...(n.exists() ? n.data() : {}) };
    const zdroje = (info && info.zdroje) || P.zdroje;
    const feedy = (info && info.feedy) || [];
    const kategorie = (info && info.kategorie) || ['Elektronika', 'Dom & Záhrada', 'Móda', 'Hračky', 'Šport', 'Jedlo & Nápoje', 'Cestovanie', 'Iné'];
    el.innerHTML = `
      ${info ? `<p class="settings-hint">Agent naposledy načítal nastavenia ${esc(U.pred(info.aktualizovane))}. Zmeny platia od jeho najbližšieho behu.</p>`
        : '<div class="hlaska info">Zoznam zdrojov a feedov sa doplní po najbližšom behu agenta. Nastavenia nižšie môžeš upraviť už teraz.</div>'}
      <form id="ag-form">
        <div class="karta"><h3 class="karta-nadpis">Zdroje</h3>
          <div class="ag-volby">${zdroje.map(z => `<label class="zaskrt"><input type="checkbox" name="zdroj" value="${esc(z)}"${v.zdroje.includes(z) ? ' checked' : ''}> ${esc(NAZVY_ZDROJOV[z] || z)}</label>`).join('')}</div>
          ${feedy.length ? `<h4 class="ag-pod">Produktové feedy</h4><div class="ag-volby">${feedy.map(f => `<label class="zaskrt"><input type="checkbox" name="feed" value="${esc(f)}"${v.vypnuteFeedy.includes(f) ? '' : ' checked'}> ${esc(f)}</label>`).join('')}</div>
            <p class="settings-hint">Celé adresy feedov sú v tajných nastaveniach GitHubu (obsahujú partnerské ID) – tu je len doména.</p>` : ''}
        </div>
        <div class="karta"><h3 class="karta-nadpis">Výber dealov</h3>
          <div class="ag-cisla">${CISLA.map(([k, t, j, mn, mx, h]) => `<label><span>${t}</span>
            <span class="ag-in"><input type="number" name="${k}" min="${mn}" max="${mx}" step="${k === 'minCena' ? '0.5' : '1'}" value="${v[k]}" placeholder="${P[k]}">${j ? `<em>${j}</em>` : ''}</span>
            <small>${h}${Number(v[k]) !== Number(P[k]) ? ` Predvolené: ${P[k]}.` : ''}</small></label>`).join('')}
            <label><span>Podiel obmedzených kategórií</span><span class="ag-in"><input type="number" name="podielObmedzenych" min="0" max="100" step="5" value="${Math.round(v.podielObmedzenych * 100)}"><em>%</em></span>
              <small>Koľko z jedného behu smú tvoriť kategórie nižšie označené ako obmedzené.</small></label>
          </div></div>
        <div class="karta" id="fd-karta">
          <h3 class="karta-nadpis">Feedy obchodov</h3>
          <p class="settings-hint">Odkiaľ agent berie produkty. Feed je zoznam tovaru, ktorý e-shop sám zverejňuje pre porovnávače –
            je to jediná spoľahlivá cesta k elektronike, lekárňam či drogérii: Alza, Dr. Max, Notino aj Allegro priame sťahovanie
            blokujú (HTTP 403), takže bez feedu sa k ich tovaru nedostaneme.</p>
          <p class="settings-hint"><b>Kde feed vziať:</b> v <a href="https://www.dognet.sk/" target="_blank" rel="noopener">Dognete</a>
            otvor kampaň obchodu → <b>Produktové feedy</b> (alebo <b>XML feed</b>) a skopíruj adresu. Je v nej tvoje partnerské ID,
            takže z takých dealov rovno zarábaš. Tieto adresy vidí len admin, na stránku sa nedostanú.</p>
          <div id="fd-zoznam"></div>
          <div class="riadok-pole" style="margin-top:10px">
            <input type="url" id="fd-url" placeholder="https://… adresa XML feedu">
            <input type="text" id="fd-nazov" placeholder="názov obchodu (napr. Alza.sk)" style="max-width:220px">
            <button class="btn" type="button" id="fd-test"><svg class="ix"><use href="#ix-check"></use></svg> Otestovať</button>
            <button class="btn btn-save" type="button" id="fd-pridaj"><svg class="ix"><use href="#ix-plus"></use></svg> Pridať</button>
          </div>
          <div id="fd-stav"></div>
        </div>
        <div class="karta"><h3 class="karta-nadpis">Kategórie</h3>
          <div class="tab-wrap"><table class="tab"><thead><tr><th>Kategória</th><th>Obmedzená (strop podielu)</th><th>Zakázaná</th></tr></thead><tbody>
          ${kategorie.map(k => `<tr><td>${esc(k)}</td><td><input type="checkbox" name="obmedzena" value="${esc(k)}"${v.obmedzeneKategorie.includes(k) ? ' checked' : ''}></td>
            <td><input type="checkbox" name="blokovana" value="${esc(k)}"${v.blokovaneKategorie.includes(k) ? ' checked' : ''}></td></tr>`).join('')}</tbody></table></div>
          <label class="pole-lab" style="margin-top:12px">Vylúčené slová v názve (oddeľ čiarkou)</label>
          <input type="text" name="slova" value="${esc(v.vylucenaSlova.join(', '))}" style="width:100%">
        </div>
        <div class="tl-rad"><button class="btn btn-save" type="submit"><svg class="ix"><use href="#ix-save"></use></svg> Uložiť nastavenia</button>
          <button class="btn" type="button" id="ag-reset">Vrátiť predvolené</button></div>
      </form>`;
    // ── Feedy obchodov ──
    const fdRef = U.ref('nastavenia_admin', 'feedy');
    let vlastneFeedy = [];
    const fdKresli = () => {
      el.querySelector('#fd-zoznam').innerHTML = vlastneFeedy.length ? vlastneFeedy.map(f => `<div class="fd-r${f.zap === false ? ' vyp' : ''}">
          <label class="switch" title="${f.zap === false ? 'Zapnúť' : 'Vypnúť'}"><input type="checkbox" data-fd="zap" data-id="${esc(f.id)}"${f.zap === false ? '' : ' checked'}><span class="slider"></span></label>
          <div class="fd-i"><b>${esc(f.nazov || f.domena || 'feed')}</b><small>${esc(f.url)}</small>
            ${f.poloziek ? `<small>${U.cislo(f.poloziek)} položiek · ${esc(f.format || '')}${f.overene ? ' · overené ' + esc(U.den(f.overene)) : ''}</small>` : ''}</div>
          <div class="tl-rad"><button class="btn" data-fd="test" data-id="${esc(f.id)}">Otestovať</button>
            <button class="btn btn-ic btn-delete" data-fd="zmaz" data-id="${esc(f.id)}" title="Odstrániť"><svg class="ix"><use href="#ix-trash"></use></svg></button></div>
        </div>`).join('') : '<p class="vis-empty">Zatiaľ žiadny vlastný feed. Agent berie len zdroje vyššie.</p>';
    };
    const fdUloz = async (popis) => {
      await fs.setDoc(fdRef, { feedy: vlastneFeedy, upravene: fs.serverTimestamp() }, { merge: true });
      HK().logChange('agent', 'agent', 'Feedy: ' + popis);
    };
    const fdStav = (html) => { el.querySelector('#fd-stav').innerHTML = html; };
    const fdOtestuj = async (url, btn) => U.akcia(btn, async () => {
      fdStav(`<div class="hlaska info"><span class="tocka"></span> ${esc(U.textCakania('caka', 0))}</div>`);
      try {
        const v = await U.uloha('test_feed', { url }, (x, ms) => fdStav(
          `<div class="hlaska info"><span class="tocka"></span> ${esc(x === 'bezi' ? 'Sťahujem feed, pri veľkom to trvá aj minútu…' : U.textCakania(x, ms))}</div>`));
        fdStav(`<div class="hlaska ok"><div><b>Feed funguje.</b> ${U.cislo(v.poloziek)} produktov vo formáte ${esc(v.format)},
          obchod: ${v.domeny.map(d => esc(d.domena)).join(', ')}.
          ${v.sPovodnouCenou ? 'Feed uvádza aj pôvodnú cenu.' : 'Feed neuvádza pôvodnú cenu – zľavu určí sledovanie cien, prvé dealy prídu o pár dní.'}
          <br><small>${v.ukazka.map(u => esc(`${u.nazov} – ${u.cena} €`)).join('<br>')}</small></div></div>`);
        return v;
      } catch (e) {
        fdStav(`<div class="hlaska chyba">${esc(e.message)}</div>`);
        return null;
      }
    });
    el.querySelector('#fd-test').addEventListener('click', e =>
      fdOtestuj(el.querySelector('#fd-url').value.trim(), e.currentTarget));
    el.querySelector('#fd-pridaj').addEventListener('click', async e => {
      const url = el.querySelector('#fd-url').value.trim();
      const nazov = el.querySelector('#fd-nazov').value.trim();
      if (!/^https?:\/\//i.test(url)) { window.toast('Vlož adresu feedu.', 'chyba'); return; }
      if (vlastneFeedy.some(f => f.url === url)) { window.toast('Tento feed už v zozname je.', 'chyba'); return; }
      const v = await fdOtestuj(url, e.currentTarget);
      if (!v) return;
      vlastneFeedy = [...vlastneFeedy, { id: Math.random().toString(36).slice(2, 10), url, nazov, zap: true,
        domena: (v.domeny[0] || {}).domena || '', poloziek: v.poloziek, format: v.format, overene: new Date() }];
      await fdUloz(`pridaný ${nazov || url}`);
      el.querySelector('#fd-url').value = ''; el.querySelector('#fd-nazov').value = '';
      fdKresli();
      window.toast('Feed pridaný. Agent ho použije pri najbližšom behu.');
    });
    el.addEventListener('click', async e => {
      const b = e.target.closest('[data-fd]');
      if (!b || b.dataset.fd === 'zap') return;
      const f = vlastneFeedy.find(x => x.id === b.dataset.id);
      if (!f) return;
      if (b.dataset.fd === 'test') { await fdOtestuj(f.url, b); return; }
      if (!await window.potvrd(`Odstrániť feed ${f.nazov || f.url}? Agent z neho prestane brať dealy.`)) return;
      vlastneFeedy = vlastneFeedy.filter(x => x.id !== f.id);
      await fdUloz(`odstránený ${f.nazov || f.url}`);
      fdKresli();
    });
    el.addEventListener('change', async e => {
      const b = e.target.closest('[data-fd="zap"]');
      if (!b) return;
      vlastneFeedy = vlastneFeedy.map(x => x.id === b.dataset.id ? { ...x, zap: b.checked } : x);
      await fdUloz(`${b.checked ? 'zapnutý' : 'vypnutý'} feed`);
      fdKresli();
    });
    try {
      const d = await fs.getDoc(fdRef);
      vlastneFeedy = (d.exists() && Array.isArray(d.data().feedy)) ? d.data().feedy : [];
    } catch (err) { /* prvé otvorenie */ }
    fdKresli();

    const form = el.querySelector('#ag-form');
    const zaskrtnute = n => [...form.querySelectorAll(`[name="${n}"]:checked`)].map(x => x.value);
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const d = {
        zdroje: zaskrtnute('zdroj'), vypnuteFeedy: feedy.filter(f => !zaskrtnute('feed').includes(f)),
        obmedzeneKategorie: zaskrtnute('obmedzena'), blokovaneKategorie: zaskrtnute('blokovana'),
        vylucenaSlova: form.elements.slova.value.split(',').map(x => x.trim()).filter(Boolean),
        podielObmedzenych: Math.min(1, Math.max(0, (Number(form.elements.podielObmedzenych.value) || 0) / 100)),
      };
      CISLA.forEach(([k, , , mn, mx]) => { const x = Number(form.elements[k].value); d[k] = isNaN(x) || form.elements[k].value === '' ? P[k] : Math.min(mx, Math.max(mn, x)); });
      if (!d.zdroje.length) { window.toast('Zapni aspoň jeden zdroj.', 'chyba'); return; }
      if (d.minZlava >= d.maxZlava) { window.toast('Minimálna zľava musí byť menšia než maximálna.', 'chyba'); return; }
      await U.akcia(form.querySelector('[type=submit]'), async () => {
        await fs.setDoc(U.ref('settings', 'agent'), { ...d, upravene: fs.serverTimestamp(), upravil: HK().email });
        HK().logChange('settings-agent', 'agent', 'Agent: ' + JSON.stringify(d).slice(0, 300));
        window.toast('Uložené. Platí od najbližšieho behu agenta.');
      });
    });
    el.querySelector('#ag-reset').addEventListener('click', async () => {
      if (!await window.potvrd('Vrátiť všetky nastavenia agenta na predvolené hodnoty?')) return;
      await fs.setDoc(U.ref('settings', 'agent'), { upravene: fs.serverTimestamp(), upravil: HK().email });
      HK().logChange('settings-agent', 'agent', 'Agent: predvolené nastavenia');
      window.toast('Vrátené na predvolené.');
      U._stranky.agent.pripravene = null;
      U._skus('agent');
    });
  },
});

// ═══════════════════════════════════════════════════════════════════
// Záloha a obnova
// ═══════════════════════════════════════════════════════════════════
const KOLEKCIE = [
  ['deals', 'Dealy', true], ['komentare', 'Komentáre k dealom', true], ['coupons', 'Kupóny', true],
  ['settings', 'Nastavenia stránky', true], ['merchants', 'Predajcovia', true], ['fb_posty', 'Príspevky na Facebook', true],
  ['utm_odkazy', 'UTM odkazy', true], ['provizie', 'Provízie', true], ['financie', 'Príjmy', true],
  ['admini', 'Administrátori', true], ['pripomienky', 'Pripomienky', true], ['audit_log', 'Záznam zmien (môže byť veľký)', false],
  ['users', 'Registrovaní používatelia (osobné údaje!)', false],
];
// Časové pečiatky Firestore -> {__ts: ms} a späť, aby sa dali uložiť do JSON.
const doJson = v => {
  if (v && typeof v.toMillis === 'function') return { __ts: v.toMillis() };
  if (v instanceof Date) return { __ts: v.getTime() };
  if (Array.isArray(v)) return v.map(doJson);
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, doJson(x)]));
  return v;
};
const zJson = v => {
  if (v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 1 && typeof v.__ts === 'number') return fs.Timestamp.fromMillis(v.__ts);
  if (Array.isArray(v)) return v.map(zJson);
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, zJson(x)]));
  return v;
};
U.stranka('zaloha', {
  init(el) {
    let posledna = null;
    try { posledna = localStorage.getItem('adm_zaloha'); } catch (e) {}
    el.innerHTML = `
      <div class="karta"><h3 class="karta-nadpis">Stiahnuť zálohu</h3>
        <p class="settings-hint">${posledna ? `Posledná záloha z tohto prehliadača: <b>${esc(U.casDlhy(Number(posledna)))}</b>.` : 'Z tohto prehliadača ešte záloha nebola stiahnutá.'}
          Súbor ulož mimo počítača (napr. na Disk Google alebo OneDrive).</p>
        <div class="ag-volby">${KOLEKCIE.map(([k, n, z]) => `<label class="zaskrt"><input type="checkbox" name="zk" value="${k}"${z ? ' checked' : ''}> ${esc(n)}</label>`).join('')}</div>
        <div class="tl-rad" style="margin-top:12px"><button class="btn btn-save" id="zl-stiahni"><svg class="ix"><use href="#ix-download"></use></svg> Stiahnuť zálohu (JSON)</button></div>
        <div id="zl-stav"></div></div>
      <div class="karta"><h3 class="karta-nadpis">Obnoviť zo zálohy</h3>
        <p class="settings-hint">Vyber súbor zálohy. Najprv uvidíš, čo obsahuje, a vyberieš, čo obnoviť. „Doplniť chýbajúce“ nič neprepíše –
          vráti len to, čo medzičasom zmizlo. „Prepísať“ vráti dokumenty presne do stavu zo zálohy.</p>
        <label class="pv-drop"><svg class="ix"><use href="#ix-upload"></use></svg> Vybrať súbor zálohy<input type="file" id="zl-subor" accept=".json,application/json" hidden></label>
        <div id="zl-obnova"></div></div>`;
    el.querySelector('#zl-stiahni').addEventListener('click', e => U.akcia(e.currentTarget, async () => {
      const vybrane = [...el.querySelectorAll('[name=zk]:checked')].map(x => x.value);
      const st = el.querySelector('#zl-stav');
      const z = { verzia: 1, stranka: 'henkukaj.sk', vytvorene: new Date().toISOString(), kolekcie: {}, komentare: [] };
      for (const k of vybrane) {
        st.innerHTML = `<div class="hlaska info"><span class="tocka"></span> Načítavam ${esc(k)}…</div>`;
        if (k === 'komentare') {
          const s = await fs.getDocs(fs.collectionGroup(U.db, 'comments'));
          z.komentare = s.docs.map(d => ({ dealId: d.ref.parent.parent.id, id: d.id, data: doJson(d.data()) }));
          continue;
        }
        try {
          const s = await fs.getDocs(U.kol(k));
          z.kolekcie[k] = Object.fromEntries(s.docs.map(d => [d.id, doJson(d.data())]));
        } catch (err) { z.kolekcie[k] = {}; console.warn('Záloha', k, err); }
      }
      const pocty = Object.entries(z.kolekcie).map(([k, v]) => `${k}: ${Object.keys(v).length}`).join(', ') + (vybrane.includes('komentare') ? `, komentáre: ${z.komentare.length}` : '');
      U.stiahni(`henkukaj-zaloha-${U.dnesIso()}.json`, JSON.stringify(z), 'application/json');
      try { localStorage.setItem('adm_zaloha', String(Date.now())); } catch (err) {}
      st.innerHTML = `<div class="hlaska ok">Záloha stiahnutá (${esc(pocty)}).</div>`;
      U.upozornenia('zaloha', []);
    }));
    el.querySelector('#zl-subor').addEventListener('change', async e => {
      const f = e.target.files[0];
      if (!f) return;
      let z;
      try { z = JSON.parse(await U.citajSubor(f)); } catch (err) { window.toast('Súbor nie je platná záloha.', 'chyba'); return; }
      if (!z || !z.kolekcie) { window.toast('Súbor nie je záloha z HenKukaj adminu.', 'chyba'); return; }
      const ob = el.querySelector('#zl-obnova');
      const moze = k => k !== 'users' && (k !== 'admini' || HK().jeMajitel);
      const riadky = Object.entries(z.kolekcie).map(([k, v]) => [k, Object.keys(v).length]);
      if (z.komentare && z.komentare.length) riadky.push(['komentare', z.komentare.length]);
      ob.innerHTML = `<p class="settings-hint">Záloha z <b>${esc(U.casDlhy(z.vytvorene))}</b>:</p>
        <div class="ag-volby">${riadky.map(([k, n]) => `<label class="zaskrt"><input type="checkbox" name="zo" value="${k}"${moze(k) ? '' : ' disabled'}>
          ${esc((KOLEKCIE.find(x => x[0] === k) || [k, k])[1])} – ${n}${moze(k) ? '' : ' (nedá sa obnoviť z adminu)'}</label>`).join('')}</div>
        <div class="tl-rad" style="margin-top:10px"><label class="zaskrt"><input type="radio" name="rezim" value="doplnit" checked> Doplniť chýbajúce</label>
          <label class="zaskrt"><input type="radio" name="rezim" value="prepisat"> Prepísať</label></div>
        <div class="tl-rad" style="margin-top:10px"><button class="btn btn-save" id="zl-obnov">Obnoviť vybrané</button></div><div id="zl-ob-stav"></div>`;
      ob.querySelector('#zl-obnov').addEventListener('click', ev => U.akcia(ev.currentTarget, async () => {
        const vyb = [...ob.querySelectorAll('[name=zo]:checked')].map(x => x.value);
        const rezim = ob.querySelector('[name=rezim]:checked').value;
        if (!vyb.length) { window.toast('Vyber, čo obnoviť.', 'chyba'); return; }
        if (!await window.potvrd(rezim === 'prepisat' ? 'Prepísať dokumenty stavom zo zálohy? Novšie zmeny v nich sa stratia.' : 'Doplniť chýbajúce dokumenty zo zálohy?')) return;
        const st = ob.querySelector('#zl-ob-stav');
        let zapisane = 0;
        for (const k of vyb) {
          st.innerHTML = `<div class="hlaska info"><span class="tocka"></span> Obnovujem ${esc(k)}…</div>`;
          const polozky = k === 'komentare'
            ? z.komentare.map(c => [['deals', c.dealId, 'comments', c.id], c.data])
            : Object.entries(z.kolekcie[k]).map(([id, d]) => [[k, id], d]);
          let existuju = new Set();
          if (rezim === 'doplnit') {
            if (k === 'komentare') {
              const s = await fs.getDocs(fs.collectionGroup(U.db, 'comments'));
              existuju = new Set(s.docs.map(d => d.ref.path));
            } else {
              const s = await fs.getDocs(U.kol(k));
              existuju = new Set(s.docs.map(d => d.ref.path));
            }
          }
          const naZapis = polozky.filter(([c]) => !existuju.has(c.join('/')));
          for (let i = 0; i < naZapis.length; i += 400) {
            const b = fs.writeBatch(U.db);
            naZapis.slice(i, i + 400).forEach(([c, d]) => b.set(fs.doc(U.db, ...c), zJson(d)));
            await b.commit();
          }
          zapisane += naZapis.length;
        }
        HK().logChange('zaloha', 'zaloha', `Obnova (${rezim}): ${vyb.join(', ')} – ${zapisane} dokumentov`);
        st.innerHTML = `<div class="hlaska ok">Hotovo – obnovených ${zapisane} dokumentov.</div>`;
      }));
    });
  },
});
// Pripomenutie zálohy v zvončeku, keď posledná je staršia než 30 dní.
function pripomenZalohu() {
  if (!HK() || HK().rola !== 'admin') return;
  let p = null;
  try { p = Number(localStorage.getItem('adm_zaloha')) || null; } catch (e) {}
  U.upozornenia('zaloha', !p || Date.now() - p > 30 * 86400000
    ? [{ text: p ? `Posledná záloha je ${U.pred(p).replace('pred ', '')} stará` : 'Ešte si nestiahol zálohu', href: '#zaloha', typ: 'cas' }] : []);
}

// ═══════════════════════════════════════════════════════════════════
// Administrátori
// ═══════════════════════════════════════════════════════════════════
const ROLY = { admin: 'Administrátor', moderator: 'Moderátor' };
U.stranka('admini', {
  async init(el) {
    el.innerHTML = `
      <div class="karta"><h3 class="karta-nadpis">Ľudia s prístupom</h3>
        <div class="tab-wrap"><table class="tab"><thead><tr><th>E-mail</th><th>Rola</th><th>Pridaný</th><th class="n">Akcií za 30 dní</th><th></th></tr></thead><tbody id="ad-telo"></tbody></table></div>
        <div id="ad-pridat"></div></div>
      <div class="karta"><h3 class="karta-nadpis">Čo kto smie</h3>
        <div class="tab-wrap"><table class="tab"><thead><tr><th></th><th>Moderátor</th><th>Administrátor</th></tr></thead><tbody>
          <tr><td>Schvaľovať, upravovať a plánovať dealy, kupóny a komentáre</td><td>áno</td><td>áno</td></tr>
          <tr><td>Kalendár a Záznam zmien</td><td>áno</td><td>áno</td></tr>
          <tr><td>Mazať dealy a kupóny natrvalo</td><td>nie</td><td>áno</td></tr>
          <tr><td>Nastavenia, affiliate, reklamy, agent, plánovač</td><td>nie</td><td>áno</td></tr>
          <tr><td>Návštevnosť, provízie, príjmy, registrovaní používatelia</td><td>nie</td><td>áno</td></tr>
          <tr><td>Pridávať a odoberať ľudí</td><td>nie</td><td>len majiteľ</td></tr></tbody></table></div>
        <p class="settings-hint">Nový človek si najprv vytvorí účet na henkukaj.sk (Prihlásiť sa → Registrácia) a potvrdí e-mail.
          Potom ho sem pridaj – do adminu sa prihlási tým istým e-mailom a heslom. Každá jeho zmena sa zapíše do Záznamu zmien.</p></div>`;
    el.addEventListener('click', async e => {
      const b = e.target.closest('[data-ad]');
      if (!b) return;
      const email = b.dataset.email;
      if (b.dataset.ad === 'zaznam') {
        location.hash = '#zaznam';
        setTimeout(() => { const s = document.getElementById('log-kto'); if (s) { s.value = email; window.renderAuditLog(); } }, 300);
      }
      if (b.dataset.ad === 'odober' && await window.potvrd(`Odobrať prístup ${email}?`)) {
        await fs.deleteDoc(U.ref('admini', email));
        HK().logChange('admini', 'admini', `Odobratý prístup: ${email}`);
        this.show(el);
      }
    });
    el.addEventListener('change', async e => {
      const s = e.target.closest('[data-rola]');
      if (!s) return;
      await fs.updateDoc(U.ref('admini', s.dataset.rola), { rola: s.value });
      HK().logChange('admini', 'admini', `${s.dataset.rola}: rola ${s.value}`);
      window.toast('Rola zmenená.');
    });
  },
  async show(el) {
    const [s, log] = await Promise.all([
      fs.getDocs(U.kol('admini')),
      fs.getDocs(fs.query(U.kol('audit_log'), fs.where('timestamp', '>=', new Date(Date.now() - 30 * 86400000)), fs.limit(5000))).catch(() => null),
    ]);
    const akcie = {};
    if (log) log.forEach(d => { const b = (d.data().by || '').toLowerCase(); akcie[b] = (akcie[b] || 0) + 1; });
    const maj = HK().jeMajitel;
    const riadok = (email, rola, kedy, pevny) => `<tr><td><b>${esc(email)}</b></td>
      <td>${pevny ? '<span class="badge badge-planned">Majiteľ</span>' : (maj ? `<select data-rola="${esc(email)}">${Object.entries(ROLY).map(([k, t]) => `<option value="${k}"${rola === k ? ' selected' : ''}>${t}</option>`).join('')}</select>` : esc(ROLY[rola] || rola))}</td>
      <td>${esc(kedy ? U.den(kedy) : '–')}</td><td class="n">${akcie[email] || 0}</td>
      <td class="r nowrap"><button class="btn" data-ad="zaznam" data-email="${esc(email)}">Záznam zmien</button>
        ${!pevny && maj ? `<button class="btn btn-ic btn-delete" data-ad="odober" data-email="${esc(email)}" title="Odobrať prístup"><svg class="ix"><use href="#ix-trash"></use></svg></button>` : ''}</td></tr>`;
    el.querySelector('#ad-telo').innerHTML = riadok('foresttt11@outlook.com', 'admin', null, true) +
      s.docs.map(d => riadok(d.id, d.data().rola, d.data().pridane, false)).join('');
    const p = el.querySelector('#ad-pridat');
    if (!maj) { p.innerHTML = '<p class="settings-hint">Ľudí pridáva a odoberá len majiteľ.</p>'; return; }
    if (p.dataset.hotovo) return;
    p.dataset.hotovo = '1';
    p.innerHTML = `<form class="riadok-pole" id="ad-form" style="margin-top:14px">
        <input type="email" name="email" placeholder="e-mail človeka" required style="flex:2">
        <select name="rola">${Object.entries(ROLY).map(([k, t]) => `<option value="${k}"${k === 'moderator' ? ' selected' : ''}>${t}</option>`).join('')}</select>
        <button class="btn btn-save" type="submit"><svg class="ix"><use href="#ix-plus"></use></svg> Pridať</button></form>`;
    p.querySelector('#ad-form').addEventListener('submit', async e => {
      e.preventDefault();
      const email = e.target.elements.email.value.trim().toLowerCase(), rola = e.target.elements.rola.value;
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { window.toast('Zadaj platný e-mail.', 'chyba'); return; }
      await fs.setDoc(U.ref('admini', email), { rola, pridane: fs.serverTimestamp(), pridal: HK().email });
      HK().logChange('admini', 'admini', `Pridaný ${email} (${ROLY[rola]})`);
      e.target.reset();
      window.toast(`${email} má prístup ako ${ROLY[rola].toLowerCase()}.`);
      this.show(el);
    });
  },
});

// ═══════════════════════════════════════════════════════════════════
// Zvonček: pripomienky na najbližší deň, chyby úloh, záloha
// ═══════════════════════════════════════════════════════════════════
document.addEventListener('hk:prihlaseny', () => {
  if (HK().rola !== 'admin') return;
  skontrolujBehy();
  pripomenZalohu();
  setInterval(skontrolujBehy, 10 * 60000);
  fs.onSnapshot(fs.query(U.kol('pripomienky'), fs.where('odoslane', '==', false)), s => {
    const do24 = Date.now() + 86400000;
    U.upozornenia('pripomienky', s.docs.map(d => d.data()).filter(p => U.naDatum(p.sendAt) && U.naDatum(p.sendAt).getTime() < do24)
      .map(p => ({ text: `Pripomienka ${U.casDlhy(p.sendAt)}: ${(p.text || '').slice(0, 70)}`, href: '#kalendar', typ: 'cas' })));
  }, () => {});
  // Letenková mapa: staré ceny = úloha neprebehla.
  fetch('assets/letenky/ceny.json?t=' + Date.now()).then(r => r.json()).then(d => {
    const h = (Date.now() - new Date(d.vytvorene)) / 3600000;
    U.upozornenia('letenky', h > 30 ? [{ text: `Ceny leteniek sú ${Math.round(h)} h staré`, href: '#zdravie', typ: 'chyba' }] : []);
  }).catch(() => {});
});

// ═══════════════════════════════════════════════════════════════════
// E-maily (vlastná schránka @henkukaj.sk cez SMTP)
// ═══════════════════════════════════════════════════════════════════
// Heslo k schránke sa v admine nezadáva ani neukladá: Firebase ho má vo
// svojej konzole (overovacie e-maily) a plánovač v tajných nastaveniach
// GitHubu (uvítanie, upozornenia, skúšobný e-mail).
// Automatické e-maily idú zo samostatnej schránky noreply@ - info@ ostáva
// na bežnú poštu a odpovede ľudí sa do nej dostanú cez Reply-To.
const EMAIL_PREDVOLENE = {
  odosielatelMeno: 'HenKukaj.sk', odosielatelEmail: 'noreply@henkukaj.sk', smtpHost: 'smtp.hostcreators.sk', smtpPort: 465,
  sifrovanie: 'ssl', pouzivatel: 'noreply@henkukaj.sk', odpovedNa: 'info@henkukaj.sk',
  uvitanieZap: false, uvitaniePredmet: 'Vitaj na HenKukaj.sk',
  uvitanieText: 'Ahoj {meno},\n\nďakujeme za registráciu na HenKukaj.sk. Odteraz si môžeš ukladať dealy, nastaviť si obľúbené letiská a odoberať novinky.\n\nNajlepšie zľavy dňa nájdeš na https://henkukaj.sk\n\nTím HenKukaj.sk',
  novaRegistraciaZap: false, novaRegistraciaKomu: 'info@henkukaj.sk',
  strazcaZap: true, strazcaPredmet: 'Našli sme deal, ktorý strážiš: {co}',
  letenkyZap: true, letenkyPredmet: 'Lacná letenka z {letisko} za {cena} €',
  overeniePredmet: 'Potvrď svoj e-mail na HenKukaj.sk',
  overenieText: 'Ahoj{meno},\n\nvitaj na HenKukaj.sk! Ešte jeden klik a máš hotovo – potvrď, že tento e-mail patrí tebe.\n\nPotom si môžeš ukladať dealy, nastaviť si strážcu zliav a dostávať len to, čo ťa naozaj zaujíma.\n\nAk si sa neregistroval ty, tento e-mail pokojne zahoď. Bez potvrdenia sa nič nestane.\n\nTím HenKukaj.sk',
  hesloPredmet: 'Nové heslo na HenKukaj.sk',
  hesloText: 'Ahoj{meno},\n\nposlali sme ti odkaz na nastavenie nového hesla. Platí hodinu a použiť sa dá raz.\n\nAk si o zmenu nežiadal, nemusíš robiť nič – tvoje pôvodné heslo ostáva v platnosti.\n\nTím HenKukaj.sk',
};

// JS verzia emaily._html() z Pythonu - rovnaký vzhľad (logo, oranžový
// pruh, odseky, voliteľné tlačidlo, pätička), aby náhľad v admine
// zodpovedal tomu, čo naozaj príde do schránky. Zámerne len inline
// štýly, nech sa to nebije so štýlmi admin stránky.
function emailNahladHtml(text, tlacidlo) {
  const e = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  let bezpecne = e(text).replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" style="color:#C44C0A;text-decoration:underline">$1</a>');
  const casti = bezpecne.split('\n\n').filter(o => o.trim());
  let kam = casti.length;
  if (casti.length && /^(Tím|S pozdravom|Tvoj tím)/.test(casti[casti.length - 1].replace(/^\s+/, ''))) kam -= 1;
  const odsek = o => `<p style="margin:0 0 14px">${o.replace(/\n/g, '<br>')}</p>`;
  const odseky = casti.slice(0, kam).map(odsek).join('');
  const podpis = casti.slice(kam).map(odsek).join('');
  let cta = '';
  if (tlacidlo) {
    cta = `<table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 18px"><tr>
      <td style="background:#E8590C;border-radius:10px"><a href="#" style="display:inline-block;padding:13px 26px;color:#ffffff;
      font-weight:700;font-size:15px;text-decoration:none">${e(tlacidlo)}</a></td></tr></table>`;
  }
  return `<div style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #E4E4E1;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">
    <div style="background:#ffffff;padding:18px 22px 12px;text-align:center">
      <img src="images/logo.png" alt="HenKukaj.sk" width="170" style="width:170px;max-width:70%;height:auto;border:0"></div>
    <div style="height:4px;background:#E8590C"></div>
    <div style="padding:22px;color:#1A1A1A;font-size:14px;line-height:1.6">${odseky}${cta}${podpis}</div>
    <div style="padding:14px 22px;border-top:1px solid #E4E4E1;background:#FAFAF8;color:#8A8A85;font-size:11px;line-height:1.6">
      <b style="color:#C44C0A">HenKukaj.sk</b> · najlepšie zľavy zo slovenských a českých e-shopov<br>
      Píš nám na info@henkukaj.sk</div>
  </div>`;
}
// Pripojí "Náhľad" prepínač k editovateľnej šablóne - zobrazí/schová
// kartu a drží ju presnú podľa aktuálneho obsahu polí (aj počas písania).
function pripojNahlad(form, id, predmetPole, textPole, tlacidlo, vzorky) {
  const wrap = form.querySelector(`#${id}-nahlad-wrap`);
  const telo = form.querySelector(`#${id}-nahlad`);
  if (!wrap || !telo) return;
  const dosad = t => Object.entries(vzorky || {}).reduce((s, [k, v]) => s.replaceAll(`{${k}}`, v), t);
  const prekresli = () => {
    if (wrap.hidden) return;
    telo.innerHTML = emailNahladHtml(dosad(form.elements[textPole].value), tlacidlo);
  };
  form.elements[textPole].addEventListener('input', prekresli);
  form.querySelector(`[data-nahlad-tog="${id}"]`)?.addEventListener('click', () => {
    wrap.hidden = !wrap.hidden;
    prekresli();
  });
}
const kopia = t => `<button type="button" class="btn btn-ic" data-kopia="${esc(t)}" title="Kopírovať"><svg class="ix"><use href="#ix-copy"></use></svg></button>`;
U.stranka('emaily', {
  async init(el) {
    const s = await fs.getDoc(U.ref('nastavenia_admin', 'email'));
    const n = { ...EMAIL_PREDVOLENE, ...(s.exists() ? s.data() : {}) };
    const riadok = (lab, hod) => `<tr><td>${lab}</td><td><code>${esc(hod)}</code></td><td class="r">${kopia(hod)}</td></tr>`;
    el.innerHTML = `
      <div class="karta">
        <h3 class="karta-nadpis">Krok 0 – schránka na odosielanie</h3>
        <p class="settings-hint">Automatické e-maily je lepšie posielať zo samostatnej schránky (napr. <b>noreply@henkukaj.sk</b>), nie z info@:
          má vlastné heslo (keby uniklo, info@ ostane v bezpečí), do info@ nechodia nedoručenky a odpovede ľudí aj tak dorazia
          na info@ (nastavenie „Odpovede posielať na“). Schránku vytvoríš v administrácii hostingu Hostcreators.</p>
      </div>
      <div class="karta">
        <h3 class="karta-nadpis">Krok 1 – e-maily pri registrácii (Firebase)</h3>
        <p class="settings-hint">Overenie e-mailu a obnovu hesla posiela Firebase. Bez tohto nastavenia chodia z adresy
          <code>noreply@dealboard-e60bf.firebaseapp.com</code> a často končia v spame. Po nastavení pôjdu z <b>${esc(n.odosielatelEmail)}</b>.</p>
        <ol class="em-kroky">
          <li>Otvor <a href="https://console.firebase.google.com/project/dealboard-e60bf/authentication/emails" target="_blank" rel="noopener">Firebase → Authentication → Templates</a>.</li>
          <li>Klikni na <b>SMTP settings</b>, zapni <b>Enable</b> a vyplň:</li>
        </ol>
        <div class="tab-wrap"><table class="tab"><tbody>
          ${riadok('Sender address', n.odosielatelEmail)}${riadok('SMTP server host', n.smtpHost)}${riadok('SMTP server port', String(n.smtpPort))}
          ${riadok('SMTP account username', n.pouzivatel)}${riadok('SMTP security mode', n.sifrovanie === 'ssl' ? 'SSL' : 'STARTTLS')}
          <tr><td>SMTP account password</td><td colspan="2"><i>heslo k schránke – zadaj ho sám, nikam inam ho nepíš</i></td></tr></tbody></table></div>
        <ol class="em-kroky" start="3">
          <li>Ulož (<b>Save</b>). Potom pri <b>Email address verification</b> a <b>Password reset</b> klikni na ceruzku,
            nastav <b>Sender name</b> na <code>${esc(n.odosielatelMeno)}</code>, <b>Reply-to</b> na <code>${esc(n.odpovedNa)}</code>
            a jazyk šablóny (<b>Template language</b>) na <b>Slovak</b>.</li>
          <li>Vyskúšaj: na <a href="https://henkukaj.sk/?nahlad=ucet" target="_blank" rel="noopener">stránke</a> si daj „Zabudnuté heslo“ – e-mail by mal prísť od ${esc(n.odosielatelEmail)}.</li>
        </ol>
      </div>
      <div class="karta">
        <h3 class="karta-nadpis">Krok 2 – heslo pre plánovač (GitHub)</h3>
        <p class="settings-hint">Uvítacie e-maily, upozornenia a skúšobný e-mail posiela plánovač. Heslo potrebuje v tajných nastaveniach
          GitHubu – tam ho nevidí nikto, ani stránka.</p>
        <ol class="em-kroky">
          <li>Otvor <a href="https://github.com/jzac369/dealboard-sk/settings/secrets/actions/new" target="_blank" rel="noopener">GitHub → Settings → Secrets → New repository secret</a>.</li>
          <li><b>Name:</b> <code>SMTP_PASSWORD</code> ${kopia('SMTP_PASSWORD')} · <b>Secret:</b> heslo k schránke · <b>Add secret</b>.</li>
          <li>Plánovač si heslo načíta pri najbližšom reštarte (najneskôr do 6 h). Daj mi vedieť a reštartujem ho hneď.</li>
        </ol>
      </div>
      <div class="karta">
        <h3 class="karta-nadpis">Krok 3 – e-maily o účte</h3>
        <div class="hlaska ok"><svg class="ix"><use href="#ix-check"></use></svg> <span><b>Netreba nič nastavovať, dá sa len upraviť.</b>
          Potvrdenie e-mailu aj odkaz na nové heslo posielame sami z <b>noreply@henkukaj.sk</b> v našom vzhľade - predmet aj text
          upravíš nižšie v sekcii "Potvrdenie e-mailu a heslo", odkaz vedie na <a href="/ucet-akcia.html?nahlad=overeny" target="_blank" rel="noopener">našu stránku</a>.</span></div>
        <p class="settings-hint">Firebase má pre tento projekt úpravu svojich šablón zakázanú („Email template updates are currently
          unavailable for this project“) – jeho e-maily by chodili po anglicky, podpísané „dealboard-e60bf“ a s odkazom na
          dealboard-e60bf.firebaseapp.com. Preto si od neho pýtame len jednorazový odkaz a e-mail zostavíme a pošleme sami.
          Výnimka je nižšie - tú jedinú ešte posiela Firebase vlastným textom.</p>
        <div id="em-sablony"></div>
      </div>
      <form class="karta" id="em-form" autocomplete="off">
        <h3 class="karta-nadpis">Odosielateľ</h3>
        <div class="form-mriezka">
          <label>Meno odosielateľa<input type="text" name="odosielatelMeno" value="${esc(n.odosielatelMeno)}"></label>
          <label>E-mail odosielateľa<input type="email" name="odosielatelEmail" value="${esc(n.odosielatelEmail)}"></label>
          <label>SMTP server<input type="text" name="smtpHost" value="${esc(n.smtpHost)}"></label>
          <label>Port<input type="number" name="smtpPort" value="${esc(n.smtpPort)}"></label>
          <label>Šifrovanie<select name="sifrovanie"><option value="ssl"${n.sifrovanie === 'ssl' ? ' selected' : ''}>SSL (port 465)</option>
            <option value="starttls"${n.sifrovanie === 'starttls' ? ' selected' : ''}>STARTTLS (port 587)</option></select></label>
          <label>Prihlasovacie meno<input type="text" name="pouzivatel" value="${esc(n.pouzivatel)}"></label>
          <label class="cela">Odpovede posielať na<input type="email" name="odpovedNa" value="${esc(n.odpovedNa)}"></label>
        </div>
        <h3 class="karta-nadpis" style="margin-top:18px">Automatické e-maily</h3>
        <label class="zaskrt"><input type="checkbox" name="uvitanieZap"${n.uvitanieZap ? ' checked' : ''}> Uvítací e-mail po overení registrácie</label>
        <div class="form-mriezka" style="margin:10px 0 14px">
          <label class="cela">Predmet<input type="text" name="uvitaniePredmet" value="${esc(n.uvitaniePredmet)}" maxlength="120"></label>
          <label class="cela">Text (<code>{meno}</code> sa nahradí menom)<textarea name="uvitanieText" rows="7">${esc(n.uvitanieText)}</textarea></label>
          <div class="cela"><button class="btn" type="button" data-nahlad-tog="uvit"><svg class="ix"><use href="#ix-eye"></use></svg> Náhľad</button>
            <div id="uvit-nahlad-wrap" hidden style="margin-top:10px"><div id="uvit-nahlad"></div></div></div>
        </div>
        <label class="zaskrt"><input type="checkbox" name="novaRegistraciaZap"${n.novaRegistraciaZap ? ' checked' : ''}> Upozorniť ma e-mailom na každú novú registráciu</label>
        <div class="form-mriezka" style="margin-top:10px"><label>Na adresu<input type="email" name="novaRegistraciaKomu" value="${esc(n.novaRegistraciaKomu)}"></label></div>
        <h3 class="karta-nadpis" style="margin-top:18px">Potvrdenie e-mailu a heslo</h3>
        <p class="settings-hint">Tieto dva posielame sami namiesto Firebase (pozri Krok 3 vyššie) - tlačidlo v e-maile
          vždy vedie na jednorazový odkaz, text okolo neho je tento.</p>
        <div class="form-mriezka" style="margin:10px 0 14px">
          <label class="cela">Predmet - Potvrdenie e-mailu<input type="text" name="overeniePredmet" value="${esc(n.overeniePredmet)}" maxlength="120"></label>
          <label class="cela">Text (<code>{meno}</code> sa nahradí menom, tlačidlo "Potvrdiť e-mail" sa pridá samo)<textarea name="overenieText" rows="6">${esc(n.overenieText)}</textarea></label>
          <div class="cela"><button class="btn" type="button" data-nahlad-tog="over"><svg class="ix"><use href="#ix-eye"></use></svg> Náhľad</button>
            <div id="over-nahlad-wrap" hidden style="margin-top:10px"><div id="over-nahlad"></div></div></div>
        </div>
        <div class="form-mriezka" style="margin:10px 0 14px">
          <label class="cela">Predmet - Zabudnuté heslo<input type="text" name="hesloPredmet" value="${esc(n.hesloPredmet)}" maxlength="120"></label>
          <label class="cela">Text (<code>{meno}</code> sa nahradí menom, tlačidlo "Nastaviť nové heslo" sa pridá samo)<textarea name="hesloText" rows="6">${esc(n.hesloText)}</textarea></label>
          <div class="cela"><button class="btn" type="button" data-nahlad-tog="hes"><svg class="ix"><use href="#ix-eye"></use></svg> Náhľad</button>
            <div id="hes-nahlad-wrap" hidden style="margin-top:10px"><div id="hes-nahlad"></div></div></div>
        </div>
        <h3 class="karta-nadpis" style="margin-top:18px">Pre registrovaných</h3>
        <label class="zaskrt"><input type="checkbox" name="strazcaZap"${n.strazcaZap ? ' checked' : ''}> Strážca dealov – e-mail, keď pribudne deal, ktorý si človek dal strážiť</label>
        <div class="form-mriezka" style="margin:10px 0 14px">
          <label class="cela">Predmet (<code>{co}</code> = čo stráži)<input type="text" name="strazcaPredmet" value="${esc(n.strazcaPredmet)}" maxlength="120"></label>
          <div class="cela settings-hint" id="strazca-nahlad">Náhľad predmetu: <b></b></div>
        </div>
        <label class="zaskrt"><input type="checkbox" name="letenkyZap"${n.letenkyZap ? ' checked' : ''}> Lacné letenky z jeho letiska – najviac jeden e-mail denne</label>
        <div class="form-mriezka" style="margin-top:10px">
          <label class="cela">Predmet (<code>{letisko}</code>, <code>{cena}</code>)<input type="text" name="letenkyPredmet" value="${esc(n.letenkyPredmet)}" maxlength="120"></label>
          <div class="cela settings-hint" id="letenky-nahlad">Náhľad predmetu: <b></b></div>
        </div>
        <p class="settings-hint" style="margin-top:10px">Telo e-mailu pri strážcovi a letenkách zostavuje plánovač sám
          zo zoznamu nájdených dealov/letov - nedá sa vopred napísať, len predmet.</p>
        <p class="settings-hint" style="margin-top:10px">Posielajú sa len na overené adresy a len tým, ktorí si strážcu alebo hranicu ceny
          sami nastavili vo svojom účte. Nastavenia komunity sú v sekcii <a href="#komunita">Komunita</a>.</p>
        <p class="settings-hint" style="margin-top:10px">Posielajú sa len pri registráciách od zapnutia – doterajší používatelia nič nedostanú.
          Plánovač kontroluje nové registrácie každých 5 minút.</p>
        <div class="tl-rad" style="margin-top:12px"><button class="btn btn-save" type="submit"><svg class="ix"><use href="#ix-save"></use></svg> Uložiť</button></div>
      </form>
      <div class="karta"><h3 class="karta-nadpis">Skúšobný e-mail</h3>
        <div class="riadok-pole"><input type="email" id="em-test" value="${esc(HK().email || '')}">
          <button class="btn btn-save" id="em-posli" type="button"><svg class="ix"><use href="#ix-send"></use></svg> Poslať skúšobný e-mail</button></div>
        <div id="em-stav"></div></div>
      <div class="karta"><h3 class="karta-nadpis">Odoslané e-maily</h3><div id="em-log"></div></div>`;
    el.addEventListener('click', async e => {
      const k = e.target.closest('[data-kopia]');
      if (k) { e.preventDefault(); U.kopiruj(k.dataset.kopia); return; }
      const b = e.target.closest('[data-em-znova]');
      if (!b || !await window.potvrd('Povoliť odoslanie tohto e-mailu znova? Plánovač ho skúsi do 5 minút.')) return;
      await fs.deleteDoc(U.ref('email_log', b.dataset.emZnova));
      window.toast('Plánovač ho skúsi poslať znova.');
    });
    // Šablóny pre Firebase sú hotové súbory v assets/emaily; generuje ich
    // sablony_emailov.py tým istým vzhľadom ako ostatné naše e-maily.
    fetch('assets/emaily/zoznam.json?t=' + Date.now()).then(r => r.json()).then(zoz => {
      const t = el.querySelector('#em-sablony');
      if (!t) return;
      t.innerHTML = zoz.map(x => `<div class="em-sablona${x.firebase ? '' : ' nase'}">
        <div><b>${esc(x.nazov)}</b><small>${esc(x.kde)}</small>
          <div class="em-pre">Predmet: <b>${esc(x.predmet)}</b></div></div>
        <div class="tl-rad">${x.firebase ? kopia(x.predmet) + `<button class="btn" type="button" data-sablona="${esc(x.kluc)}">
          <svg class="ix"><use href="#ix-copy"></use></svg> Kopírovať HTML</button>` : '<span class="badge badge-approved">rieši plánovač</span>'}
          <a class="btn btn-ic" href="assets/emaily/${esc(x.kluc)}.html" target="_blank" rel="noopener" title="Pozrieť"><svg class="ix"><use href="#ix-eye"></use></svg></a></div></div>`).join('');
    }).catch(() => {});
    el.addEventListener('click', async e => {
      const b = e.target.closest('[data-sablona]');
      if (!b) return;
      await U.akcia(b, async () => {
        U.kopiruj(await (await fetch(`assets/emaily/${b.dataset.sablona}.html?t=` + Date.now())).text());
      });
    });

    const form = el.querySelector('#em-form');
    pripojNahlad(form, 'uvit', 'uvitaniePredmet', 'uvitanieText', null, { meno: ' Jana' });
    pripojNahlad(form, 'over', 'overeniePredmet', 'overenieText', 'Potvrdiť e-mail', { meno: ' Jana' });
    pripojNahlad(form, 'hes', 'hesloPredmet', 'hesloText', 'Nastaviť nové heslo', { meno: ' Jana' });
    // Strážca a letenky nemajú telo na úpravu (zostavuje ho plánovač zo
    // zoznamu nájdených dealov/letov) - ukážeme aspoň živý náhľad predmetu.
    const nahladPredmetu = (pole, id, vzorky) => {
      const prekresli = () => {
        let t = form.elements[pole].value;
        Object.entries(vzorky).forEach(([k, v]) => { t = t.replaceAll(`{${k}}`, v); });
        el.querySelector(`#${id}-nahlad b`).textContent = t;
      };
      form.elements[pole].addEventListener('input', prekresli);
      prekresli();
    };
    nahladPredmetu('strazcaPredmet', 'strazca', { co: 'PS5 Slim' });
    nahladPredmetu('letenkyPredmet', 'letenky', { letisko: 'Bratislavy', cena: '24,99' });
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const f = k => form.elements[k];
      const d = {};
      ['odosielatelMeno', 'odosielatelEmail', 'smtpHost', 'sifrovanie', 'pouzivatel', 'odpovedNa', 'uvitaniePredmet', 'uvitanieText',
        'novaRegistraciaKomu', 'strazcaPredmet', 'letenkyPredmet', 'overeniePredmet', 'overenieText', 'hesloPredmet', 'hesloText']
        .forEach(k => { d[k] = f(k).value.trim(); });
      d.strazcaZap = f('strazcaZap').checked;
      d.letenkyZap = f('letenkyZap').checked;
      d.smtpPort = Number(f('smtpPort').value) || 465;
      d.uvitanieZap = f('uvitanieZap').checked;
      d.novaRegistraciaZap = f('novaRegistraciaZap').checked;
      // Čas zapnutia: e-maily dostanú len registrácie od tejto chvíle.
      if (d.uvitanieZap && !n.uvitanieZap) d.uvitanieOd = new Date();
      if (d.novaRegistraciaZap && !n.novaRegistraciaZap) d.novaRegistraciaOd = new Date();
      await U.akcia(form.querySelector('[type=submit]'), async () => {
        await fs.setDoc(U.ref('nastavenia_admin', 'email'), { ...d, upravene: fs.serverTimestamp() }, { merge: true });
        Object.assign(n, d);
        HK().logChange('email', 'ucty', 'E-maily: nastavenia uložené');
        window.toast('Uložené.');
      });
    });
    el.querySelector('#em-posli').addEventListener('click', e => U.akcia(e.currentTarget, async () => {
      const komu = el.querySelector('#em-test').value.trim(), st = el.querySelector('#em-stav');
      st.innerHTML = `<div class="hlaska info"><span class="tocka"></span> ${esc(U.textCakania('caka', 0))}</div>`;
      try {
        await U.uloha('test_email', { komu }, (x, ms) => { st.innerHTML = `<div class="hlaska info"><span class="tocka"></span> ${esc(U.textCakania(x, ms))}</div>`; });
        st.innerHTML = `<div class="hlaska ok">E-mail odoslaný na ${esc(komu)}. Ak nepríde do pár minút, pozri spam.</div>`;
      } catch (err) {
        st.innerHTML = `<div class="hlaska chyba">${esc(err.message)}${/SMTP_PASSWORD/.test(err.message) ? ' – dokonči krok 2.' : ''}</div>`;
      }
    }));
    fs.onSnapshot(fs.query(U.kol('email_log'), fs.orderBy('kedy', 'desc'), fs.limit(50)), sn => {
      const TYP = { test: 'Skúšobný', uvitanie: 'Uvítanie', 'nova-registracia': 'Nová registrácia',
        strazca: 'Strážca dealov', letenky: 'Lacné letenky', overenie: 'Potvrdenie e-mailu', heslo: 'Zabudnuté heslo' };
      const t = el.querySelector('#em-log');
      if (t) t.innerHTML = sn.size ? `<div class="tab-wrap"><table class="tab"><tbody>${sn.docs.map(d => {
        const x = d.data();
        return `<tr><td class="nowrap">${esc(U.cas(x.kedy))}</td><td>${esc(TYP[x.typ] || x.typ)}<small>${esc(x.komu || '')}${x.pouzivatel ? ' · ' + esc(x.pouzivatel) : ''}</small>
          ${x.chyba ? `<small class="chyba-t">${esc(x.chyba)}</small>` : ''}</td>
          <td><span class="badge ${x.ok ? 'badge-approved' : 'badge-rejected'}">${x.ok ? 'odoslané' : 'chyba'}</span></td>
          <td class="r">${!x.ok && x.typ === 'uvitanie' ? `<button class="btn" data-em-znova="${esc(d.id)}">Poslať znova</button>` : ''}</td></tr>`;
      }).join('')}</tbody></table></div>` : '<p class="vis-empty">Zatiaľ žiadne.</p>';
    }, () => {});
  },
});

// ═══════════════════════════════════════════════════════════════════
// Komunita: body, odznaky, rebríček a dôveryhodní prispievatelia
// ═══════════════════════════════════════════════════════════════════
// Body počíta plánovač raz za hodinu (komunita.py) - admin tu nastavuje
// pravidlá a vidí výsledok. Dôvera znamená, že dealy od toho človeka idú
// na stránku rovno; vymáhajú ju aj pravidlá databázy.
const KOM_PREDVOLENE = {
  zapnute: true, bodyZaDeal: 10, bodyZaHlas: 1, bodyZa5Preklikov: 1, bodyZaZamietnuty: -5,
  doveraZapnuta: false, doveraMinDealov: 5, doveraMinUspesnost: 80, doveraMinBodov: 50,
};
const KOM_POLIA = [
  ['bodyZaDeal', 'Body za zverejnený deal', -50, 100],
  ['bodyZaHlas', 'Body za hlas od ľudí', 0, 10],
  ['bodyZa5Preklikov', 'Body za každých 5 preklikov', 0, 10],
  ['bodyZaZamietnuty', 'Body za zamietnutý deal', -50, 0],
];
const KOM_DOVERA = [
  ['doveraMinDealov', 'Zverejnených dealov aspoň', 1, 500],
  ['doveraMinUspesnost', 'Úspešnosť aspoň (%)', 0, 100],
  ['doveraMinBodov', 'Bodov aspoň', 0, 10000],
];
U.stranka('komunita', {
  async init(el) {
    const s = await fs.getDoc(U.ref('nastavenia_admin', 'komunita'));
    const n = { ...KOM_PREDVOLENE, ...(s.exists() ? s.data() : {}) };
    el.innerHTML = `
      <div class="kpi-row" id="km-kpi"></div>
      <form class="karta" id="km-form">
        <h3 class="karta-nadpis">Body a odznaky</h3>
        <label class="zaskrt"><input type="checkbox" name="zapnute"${n.zapnute ? ' checked' : ''}> Zbierať body a odznaky za pridané dealy</label>
        <div class="ag-cisla" style="margin-top:12px">${KOM_POLIA.map(([k, t, mn, mx]) => `<label><span>${t}</span>
          <span class="ag-in"><input type="number" name="${k}" min="${mn}" max="${mx}" value="${n[k]}"></span></label>`).join('')}</div>
        <p class="settings-hint" style="margin-top:10px">Odznaky sa udeľujú podľa bodov: 🌱 Nováčik (0), 🔎 Lovec zliav (50),
          ⭐ Skúsený lovec (200), 🏅 Majster zliav (500), 👑 Legenda (1500). Človek ich vidí vo svojom účte a odznak sa ukazuje
          aj pri jeho mene na karte dealu.</p>
        <h3 class="karta-nadpis" style="margin-top:20px">Dôveryhodní prispievatelia</h3>
        <label class="zaskrt"><input type="checkbox" name="doveraZapnuta"${n.doveraZapnuta ? ' checked' : ''}> Zverejňovať dealy od overených ľudí bez čakania na schválenie</label>
        <div class="ag-cisla" style="margin-top:12px">${KOM_DOVERA.map(([k, t, mn, mx]) => `<label><span>${t}</span>
          <span class="ag-in"><input type="number" name="${k}" min="${mn}" max="${mx}" value="${n[k]}"></span></label>`).join('')}</div>
        <p class="settings-hint" style="margin-top:10px">Všetky tri podmienky musia platiť naraz. Úspešnosť je podiel zverejnených
          z rozhodnutých dealov toho človeka. Komu podmienky prestanú vychádzať, dôveru automaticky stratí.
          Ich dealy sa normálne zobrazia v <a href="#dealy">Dealoch</a> a dajú sa kedykoľvek skryť.</p>
        <div class="tl-rad" style="margin-top:12px"><button class="btn btn-save" type="submit"><svg class="ix"><use href="#ix-save"></use></svg> Uložiť</button>
          <button class="btn" type="button" id="km-prepocet"><svg class="ix"><use href="#ix-refresh"></use></svg> Prepočítať teraz</button></div>
        <div id="km-stav"></div>
      </form>
      <div class="karta"><h3 class="karta-nadpis">Rebríček</h3>
        <div class="tab-wrap"><table class="tab"><thead><tr><th>#</th><th>Prispievateľ</th><th class="n">Body</th><th class="n">Dealov</th>
          <th class="n">Hlasov</th><th class="n">Preklikov</th><th class="n">Úspešnosť</th><th></th></tr></thead>
          <tbody id="km-zoznam"></tbody></table></div></div>
      <div class="karta"><h3 class="karta-nadpis">Dôveru majú</h3><div id="km-dovera"></div></div>`;
    const form = el.querySelector('#km-form');
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const d = { zapnute: form.elements.zapnute.checked, doveraZapnuta: form.elements.doveraZapnuta.checked };
      [...KOM_POLIA, ...KOM_DOVERA].forEach(([k, , mn, mx]) => {
        d[k] = Math.max(mn, Math.min(mx, Math.round(Number(form.elements[k].value) || 0)));
      });
      await U.akcia(form.querySelector('[type=submit]'), async () => {
        await fs.setDoc(U.ref('nastavenia_admin', 'komunita'), { ...d, upravene: fs.serverTimestamp() }, { merge: true });
        Object.assign(n, d);
        HK().logChange('komunita', 'ucty', 'Komunita: ' + JSON.stringify(d).slice(0, 200));
        window.toast('Uložené. Prejaví sa pri najbližšom prepočte (do hodiny).');
      });
    });
    el.querySelector('#km-prepocet').addEventListener('click', e => U.akcia(e.currentTarget, async () => {
      // Plánovač prepočítava raz za hodinu; zmazaním značky ho prinútime
      // prepočítať pri najbližšej kontrole (do 5 minút).
      await fs.setDoc(U.ref('nastavenia_admin', 'komunita_stav'), { poslednyBeh: null }, { merge: true });
      el.querySelector('#km-stav').innerHTML = '<div class="hlaska info">Plánovač prepočíta body do 5 minút.</div>';
    }));
    el.addEventListener('click', async e => {
      const b = e.target.closest('[data-km]');
      if (!b) return;
      const uid = b.dataset.uid, meno = b.dataset.meno || '';
      if (b.dataset.km === 'dovera-daj') {
        if (!await window.potvrd(`Dať ${meno} dôveru? Jeho ďalšie dealy pôjdu na stránku rovno, bez schvaľovania.`)) return;
        await fs.setDoc(U.ref('duveryhodni', uid), { meno, od: fs.serverTimestamp(), dovod: 'ručne z adminu', pridal: HK().email });
        HK().logChange('komunita', 'ucty', `Dôvera udelená: ${meno}`);
      } else if (b.dataset.km === 'dovera-vezmi') {
        if (!await window.potvrd(`Odobrať ${meno} dôveru? Jeho dealy budú znova čakať na schválenie.`)) return;
        await fs.deleteDoc(U.ref('duveryhodni', uid));
        HK().logChange('komunita', 'ucty', `Dôvera odobratá: ${meno}`);
      }
      this.show(el);
    });
  },
  async show(el) {
    const [ludia, dovera, reb] = await Promise.all([
      fs.getDocs(U.kol('prispevatelia')),
      fs.getDocs(U.kol('duveryhodni')),
      fs.getDoc(U.ref('verejne', 'rebricek')).catch(() => null),
    ]);
    const zoz = ludia.docs.map(d => ({ ...d.data(), uid: d.id })).sort((a, b) => (b.body || 0) - (a.body || 0));
    const maju = new Map(dovera.docs.map(d => [d.id, d.data()]));
    const kedy = reb && reb.exists() ? reb.data().aktualizovane : null;
    el.querySelector('#km-kpi').innerHTML =
      U.kpi('Prispievateľov', zoz.length, '', kedy ? `prepočítané ${U.pred(kedy)}` : 'ešte neprepočítané') +
      U.kpi('Dealov od ľudí', zoz.reduce((a, x) => a + (x.dealy || 0), 0)) +
      U.kpi('Hlasov spolu', zoz.reduce((a, x) => a + (x.hlasy || 0), 0)) +
      U.kpi('S dôverou', maju.size);
    el.querySelector('#km-zoznam').innerHTML = zoz.length ? zoz.map((x, i) => `<tr>
        <td>${i + 1}.</td><td><b>${esc(x.odznak || '')} ${esc(x.meno || '')}</b><small>${esc(x.odznakNazov || '')}</small></td>
        <td class="n"><b>${U.cislo(x.body || 0)}</b></td><td class="n">${x.dealy || 0}</td><td class="n">${x.hlasy || 0}</td>
        <td class="n">${x.kliky || 0}</td><td class="n">${x.uspesnost || 0} %</td>
        <td class="r nowrap">${maju.has(x.uid)
          ? '<span class="badge badge-approved">dôvera</span>'
          : `<button class="btn" data-km="dovera-daj" data-uid="${esc(x.uid)}" data-meno="${esc(x.meno || '')}">Dať dôveru</button>`}</td></tr>`).join('')
      : '<tr><td colspan="8" class="vis-empty">Zatiaľ žiadni prispievatelia. Body sa počítajú len za dealy od prihlásených ľudí.</td></tr>';
    el.querySelector('#km-dovera').innerHTML = maju.size ? `<div class="tab-wrap"><table class="tab"><tbody>${[...maju].map(([uid, d]) => `<tr>
        <td><b>${esc(d.meno || uid)}</b><small>${esc(d.dovod || '')}${d.od ? ' · ' + esc(U.den(d.od)) : ''}</small></td>
        <td class="r"><button class="btn btn-reject" data-km="dovera-vezmi" data-uid="${esc(uid)}" data-meno="${esc(d.meno || '')}">Odobrať</button></td></tr>`).join('')}</tbody></table></div>`
      : '<p class="vis-empty">Nikto zatiaľ nemá dôveru. Dealy od ľudí čakajú na tvoje schválenie.</p>';
  },
});
