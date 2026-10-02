// ── Menu adminu ───────────────────────────────────────────────────────
// Celé ľavé menu sa skladá odtiaľto: skupiny, stránky, ikony a kľúčové
// slová pre vyhľadávanie. Stránky, ktoré ešte nemajú sekciu v admin.html,
// tu dostanú prázdnu kostru a naplní ich príslušný modul (assets/admin).
//
// Klasický skript (nie modul): musí bežať hneď, ešte pred prihlásením,
// aby menu a navigácia fungovali aj počas načítavania dát.
(function () {
  const I = {
    prehlad: 'M5 4h4a1 1 0 0 1 1 1v6a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1v-6a1 1 0 0 1 1 -1 M5 16h4a1 1 0 0 1 1 1v2a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1v-2a1 1 0 0 1 1 -1 M15 12h4a1 1 0 0 1 1 1v6a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1v-6a1 1 0 0 1 1 -1 M15 4h4a1 1 0 0 1 1 1v2a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1v-2a1 1 0 0 1 1 -1',
    dealy: 'M12 10.941c2.333 -3.308 .167 -7.823 -1 -8.941c0 3.395 -2.235 5.299 -3.667 6.706c-1.43 1.408 -2.333 3.294 -2.333 5.588c0 3.704 3.134 6.706 7 6.706c3.866 0 7 -3.002 7 -6.706c0 -1.712 -1.232 -4.403 -2.333 -5.588c-2.084 3.353 -3.257 3.353 -4.667 2.235',
    pridat: 'M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0 M9 12h6 M12 9v6',
    kalendar: 'M4 7a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2v-12z M16 3v4 M8 3v4 M4 11h16',
    kody: 'M15 5l0 2 M15 11l0 2 M15 17l0 2 M5 5h14a2 2 0 0 1 2 2v3a2 2 0 0 0 0 4v3a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-3a2 2 0 0 0 0 -4v-3a2 2 0 0 1 2 -2',
    komentare: 'M3 20l1.3 -3.9c-2.324 -3.437 -1.426 -7.872 2.1 -10.374c3.526 -2.501 8.59 -2.296 11.845 .48c3.255 2.777 3.695 7.266 1.029 10.501c-2.666 3.235 -7.615 4.215 -11.574 2.293l-4.7 1',
    platnost: 'M11.46 20.846a12 12 0 0 1 -7.96 -14.846a12 12 0 0 0 8.5 -3a12 12 0 0 0 8.5 3a12 12 0 0 1 -.09 7.06 M15 19l2 2l4 -4',
    letenky: 'M16 10h4a2 2 0 0 1 0 4h-4l-4 7h-3l2 -7h-4l-2 2h-3l2 -4l-2 -4h3l2 2h4l-2 -7h3l4 7',
    ucty: 'M5 7a4 4 0 1 0 8 0a4 4 0 1 0 -8 0 M3 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2 M16 3.13a4 4 0 0 1 0 7.75 M21 21v-2a4 4 0 0 0 -3 -3.85',
    reklamy: 'M3 7a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v10a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-10z M7 15v-4a2 2 0 0 1 4 0v4 M7 13l4 0 M17 9v6h-1.5a1.5 1.5 0 1 1 1.5 -1.5',
    affiliate: 'M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0 M14.8 9a2 2 0 0 0 -1.8 -1h-2a2 2 0 1 0 0 4h2a2 2 0 1 1 0 4h-2a2 2 0 0 1 -1.8 -1 M12 7v10',
    provizie: 'M5 21v-16a2 2 0 0 1 2 -2h10a2 2 0 0 1 2 2v16l-3 -2l-2 2l-2 -2l-2 2l-2 -2l-3 2 M14 8h-2.5a1.5 1.5 0 0 0 0 3h1a1.5 1.5 0 0 1 0 3h-2.5 M12 7v1 M12 14v1',
    prijmy: 'M4 19l16 0 M4 15l4 -6l4 2l4 -5l4 4',
    predajcovia: 'M3 21l18 0 M3 7v1a3 3 0 0 0 6 0v-1m0 1a3 3 0 0 0 6 0v-1m0 1a3 3 0 0 0 6 0v-1h-18l2 -4h14l2 4 M5 21l0 -10.15 M19 21l0 -10.15 M9 21v-4a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2v4',
    facebook: 'M7 10v4h3v7h4v-7h3l1 -4h-4v-2a1 1 0 0 1 1 -1h3v-4h-3a5 5 0 0 0 -5 5v2h-3',
    utm: 'M7.5 7.5m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0 M3 6v5.172a2 2 0 0 0 .586 1.414l7.71 7.71a2.41 2.41 0 0 0 3.408 0l5.592 -5.592a2.41 2.41 0 0 0 0 -3.408l-7.71 -7.71a2 2 0 0 0 -1.414 -.586h-5.172a3 3 0 0 0 -3 3z',
    seo: 'M21 12a9 9 0 1 0 -9 9 M3.6 9h16.8 M3.6 15h7.9 M11.5 3a17 17 0 0 0 0 18 M12.5 3a16.984 16.984 0 0 1 2.574 8.62 M15 18a3 3 0 1 0 6 0a3 3 0 1 0 -6 0 M20.2 20.2l1.8 1.8',
    navstevnost: 'M3 13a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v6a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1z M15 9a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v10a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1z M9 5a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v14a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1z M4 20h14',
    top: 'M8 21l8 0 M12 17l0 4 M7 4l10 0 M17 4v8a5 5 0 0 1 -10 0v-8 M3 9a2 2 0 1 0 4 0a2 2 0 1 0 -4 0 M17 9a2 2 0 1 0 4 0a2 2 0 1 0 -4 0',
    hladania: 'M3 10a7 7 0 1 0 14 0a7 7 0 1 0 -14 0 M21 21l-6 -6',
    pouzivanie: 'M8 13v-8.5a1.5 1.5 0 0 1 3 0v7.5 M11 11.5v-2a1.5 1.5 0 1 1 3 0v2.5 M14 10.5a1.5 1.5 0 0 1 3 0v1.5 M17 11.5a1.5 1.5 0 0 1 3 0v4.5a6 6 0 0 1 -6 6h-2a6 6 0 0 1 -5 -2.7l-3.5 -6a1.5 1.5 0 0 1 2.8 -1.7l1.7 1.7',
    planovac: 'M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0 M12 7v5l3 3',
    zdravie: 'M19.5 13.572l-7.5 7.428l-7.5 -7.428a5 5 0 1 1 7.5 -6.566a5 5 0 1 1 7.5 6.572 M3 13h2l2 3l2 -6l1 3h3',
    agent: 'M6 6a2 2 0 0 1 2 -2h8a2 2 0 0 1 2 2v4a2 2 0 0 1 -2 2h-8a2 2 0 0 1 -2 -2l0 -4 M12 2v2 M9 12v9 M15 12v9 M5 16l4 -2 M15 14l4 2 M9 18h6 M10 8v.01 M14 8v.01',
    admini: 'M12 3a12 12 0 0 0 8.5 3a12 12 0 0 1 -8.5 15a12 12 0 0 1 -8.5 -15a12 12 0 0 0 8.5 -3 M11 11a1 1 0 1 0 2 0a1 1 0 1 0 -2 0 M12 12l0 2.5',
    komunita: 'M12 17.75l-6.172 3.245l1.179 -6.873l-5 -4.867l6.9 -1l3.086 -6.253l3.086 6.253l6.9 1l-5 4.867l1.179 6.873z',
    emaily: 'M3 7a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v10a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-10z M3 7l9 6l9 -6',
    zaloha: 'M4 6c0 1.657 3.582 3 8 3s8 -1.343 8 -3s-3.582 -3 -8 -3s-8 1.343 -8 3 M4 6v6c0 1.657 3.582 3 8 3c1.118 0 2.183 -.086 3.15 -.241 M20 12v-6 M4 12v6c0 1.657 3.582 3 8 3c.157 0 .312 -.002 .466 -.005 M16 19h6 M19 16l3 3l-3 3',
    zaznam: 'M12 8l0 4l2 2 M3.05 11a9 9 0 1 1 .5 4m-.5 5v-5h5',
  };

  // m = vidí aj moderátor. k = kľúčové slová pre vyhľadávanie.
  const MENU = [
    { g: '', p: [
      { id: 'prehlad', n: 'Prehľad', d: 'Čo čaká na teba a ako sa darí stránke – na jednom mieste.', m: 1, k: 'dashboard domov úvod' },
    ] },
    { g: 'Obsah', p: [
      { id: 'dealy', n: 'Dealy', m: 1, k: 'schvaľovanie moderácia zamietnuť archív kvalita topovať žiar' },
      { id: 'pridat', n: 'Pridať z odkazu', d: 'Vlož adresu produktu – admin načíta názov, cenu a fotku a ty len skontroluješ.', k: 'nový deal url import vložiť' },
      { id: 'kalendar', n: 'Kalendár', d: 'Naplánované dealy, príspevky aj automatické úlohy. Filtrom "Čo zobraziť" vyberieš, čo vidieť; dealy a príspevky presunieš ťahaním na iný deň.', m: 1, k: 'plán naplánované zverejnenie týždeň mesiac' },
      { id: 'kody', n: 'Zľavové kódy', m: 1, k: 'kupóny coupon' },
      { id: 'komentare', n: 'Komentáre', m: 1, k: 'diskusia moderácia' },
      { id: 'platnost', n: 'Kontrola platnosti', d: 'Nefunkčné odkazy a skončené akcie na stránke – skontroluj ich jedným klikom.', k: 'exspirované mŕtve odkazy 404 skončené' },
    ] },
    { g: 'Stránka', p: [
      { id: 'letenky', n: 'Letenky', k: 'mapa lety ryanair' },
      { id: 'ucty', n: 'Účty a newsletter', k: 'registrácia používatelia odberatelia e-mail' },
      { id: 'emaily', n: 'E-maily', d: 'Odosielanie e-mailov z vlastnej schránky @henkukaj.sk: registrácia, uvítanie, upozornenia a skúšobný e-mail.', k: 'smtp email pošta registrácia overenie uvítanie heslo hostcreators' },
      { id: 'komunita', n: 'Komunita', d: 'Body, odznaky a rebríček prispievateľov. Komu dealy pôjdu na stránku bez čakania.', k: 'body odznaky rebríček prispievatelia dôvera overení používatelia gamifikácia' },
      { id: 'reklamy', n: 'Reklamné miesta', d: 'Bannery na stránke: zapni, vypni, striedaj a sleduj kliky.', k: 'banner reklama sledovanietv sponzor' },
    ] },
    { g: 'Zarábanie', p: [
      { id: 'affiliate', n: 'Affiliate', k: 'dognet chid kampane partnerské odkazy' },
      { id: 'provizie', n: 'Provízie', d: 'Import provízií z Dognetu (CSV) – zárobok podľa obchodu a mesiaca.', k: 'dognet csv import zárobok obchody' },
      { id: 'prijmy', n: 'Príjmy', d: 'Affiliate a AdSense po mesiacoch v jednom grafe.', k: 'adsense peniaze graf mesiac zisk' },
      { id: 'predajcovia', n: 'Predajcovia', k: 'obchody odkazy agent merchant' },
    ] },
    { g: 'Marketing', p: [
      { id: 'facebook', n: 'Facebook', d: 'Naplánuj príspevok: vyber deal, uprav text, zvoľ čas. Aj história odoslaných.', k: 'fb príspevok zdieľanie sociálne siete' },
      { id: 'utm', n: 'UTM odkazy', d: 'Vytvor odkaz pre kampaň a sleduj, koľko ľudí priniesol a koľko klikli.', k: 'kampaň utm_source odkaz sledovanie' },
      { id: 'seo', n: 'SEO', d: 'Sitemap, stránky s noindex, chýbajúce popisy a najúspešnejšie dealy.', k: 'google vyhľadávače sitemap noindex popis' },
    ] },
    { g: 'Analytika', p: [
      { id: 'navstevnost', n: 'Návštevnosť', k: 'návštevy štatistiky obdobie porovnanie zdroje' },
      { id: 'top', n: 'Najlepší obsah', d: 'Dealy, obchody a kategórie s najviac preklikmi vo zvolenom období.', k: 'prekliky top dealy obchody kategórie graf' },
      { id: 'hladania', n: 'Čo ľudia hľadajú', d: 'Hľadania na stránke – aj tie bez výsledku. Námety, aké dealy pridať.', k: 'vyhľadávanie hľadanie bez výsledku' },
      { id: 'pouzivanie', n: 'Používanie funkcií', d: 'Ktoré záložky, filtre a tlačidlá ľudia naozaj používajú.', k: 'kliky záložky filtre tlačidlá udalosti' },
    ] },
    { g: 'Automatizácia', p: [
      { id: 'planovac', n: 'Plánovač úloh', k: 'rozvrh časy spustiť cron' },
      { id: 'zdravie', n: 'Zdravie systému', d: 'Stav posledných behov všetkých úloh na GitHube, chyby a opakovanie.', k: 'github actions chyby beh workflow' },
      { id: 'agent', n: 'Nastavenia agenta', d: 'Zdroje, minimálna zľava, limity na obchod a kategóriu – bez zásahu do kódu.', k: 'deal hunter feedy zdroje zľava kvóty' },
    ] },
    { g: 'Systém', p: [
      { id: 'admini', n: 'Administrátori', d: 'Kto má prístup do adminu a s akou rolou.', k: 'moderátor role prístup používatelia' },
      { id: 'zaloha', n: 'Záloha', d: 'Stiahni zálohu dealov, kódov a nastavení do súboru, alebo ich obnov.', k: 'export import obnova backup' },
      { id: 'zaznam', n: 'Záznam zmien', m: 1, k: 'audit log história kto čo' },
    ] },
  ];
  const STRANKY = MENU.flatMap(g => g.p.map(p => ({ ...p, g: g.g })));
  window.HK_MENU = STRANKY;

  const ikona = id => `<svg class="ai" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${I[id] || I.prehlad}"/></svg>`;
  window.HK_IKONA = ikona;
  const esc = t => String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const norm = t => String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

  let zbalene = {};
  try { zbalene = JSON.parse(localStorage.getItem('adm_skupiny') || '{}'); } catch (e) {}

  // ── Kostry stránok, ktoré v admin.html ešte nie sú ──
  const main = document.querySelector('.adm-main .container');
  STRANKY.forEach(p => {
    if (document.querySelector(`.admin-page[data-page="${p.id}"]`)) return;
    const sec = document.createElement('section');
    sec.className = 'admin-section admin-page';
    sec.dataset.page = p.id;
    sec.innerHTML = `<h2 class="section-title">${esc(p.n)}</h2><p class="page-desc">${esc(p.d || '')}</p>
      <div class="pg" id="pg-${p.id}"><div class="pg-nacitavam">Načítavam…</div></div>`;
    main.appendChild(sec);
  });

  // ── Menu ──
  const nav = document.getElementById('adm-nav');
  function kresliMenu() {
    const rola = (window.HK && window.HK.rola) || 'admin';
    const pov = p => rola === 'admin' || p.m;
    nav.innerHTML = `<div class="nav-hladaj"><svg class="ix" aria-hidden="true"><use href="#ix-search"></use></svg>
        <input type="search" id="nav-q" placeholder="Hľadať v menu…" autocomplete="off" aria-label="Hľadať v menu">
        <kbd title="Rýchle hľadanie všade">Ctrl K</kbd></div>` +
      MENU.map(g => {
        const polozky = g.p.filter(pov);
        if (!polozky.length) return '';
        const zb = g.g && zbalene[g.g];
        return (g.g ? `<button type="button" class="grp${zb ? ' zbalena' : ''}" data-g="${esc(g.g)}">${esc(g.g)}<svg class="ix"><use href="#ix-chev"></use></svg></button>` : '') +
          `<div class="grp-p${zb ? ' zbalena' : ''}">` + polozky.map(p =>
            `<a href="#${p.id}" data-page="${p.id}" title="${esc(p.n)}" data-q="${esc(norm(p.n + ' ' + (p.k || '') + ' ' + g.g))}">${ikona(p.id)}<span class="txt">${esc(p.n)}</span><span class="badge" id="nb-${p.id}"></span></a>`).join('') +
          '</div>';
      }).join('') + `<p class="nav-prazdne" hidden>Nič sa nenašlo.</p>`;
    const aktivna = (location.hash || '').slice(1);
    nav.querySelectorAll('a').forEach(a => a.classList.toggle('on', a.dataset.page === aktivna));
  }
  window.HK_KRESLI_MENU = kresliMenu;
  kresliMenu();

  nav.addEventListener('click', e => {
    const g = e.target.closest('.grp');
    if (!g) return;
    const zb = !g.classList.contains('zbalena');
    g.classList.toggle('zbalena', zb);
    g.nextElementSibling.classList.toggle('zbalena', zb);
    zbalene[g.dataset.g] = zb;
    try { localStorage.setItem('adm_skupiny', JSON.stringify(zbalene)); } catch (err) {}
  });
  nav.addEventListener('input', e => {
    if (e.target.id !== 'nav-q') return;
    const q = norm(e.target.value.trim());
    nav.classList.toggle('hlada', !!q);
    let pocet = 0;
    nav.querySelectorAll('a[data-q]').forEach(a => {
      const ok = !q || q.split(/\s+/).every(w => a.dataset.q.includes(w));
      a.hidden = !ok;
      if (ok) pocet++;
    });
    nav.querySelectorAll('.grp').forEach(g => {
      g.hidden = !!q && ![...g.nextElementSibling.querySelectorAll('a')].some(a => !a.hidden);
    });
    nav.querySelector('.nav-prazdne').hidden = pocet > 0;
  });
  nav.addEventListener('keydown', e => {
    if (e.target.id !== 'nav-q') return;
    if (e.key === 'Enter') {
      const a = [...nav.querySelectorAll('a[data-q]')].find(x => !x.hidden);
      if (a) { location.hash = a.getAttribute('href'); e.target.value = ''; e.target.dispatchEvent(new Event('input', { bubbles: true })); }
    }
    if (e.key === 'Escape') { e.target.value = ''; e.target.dispatchEvent(new Event('input', { bubbles: true })); }
  });

  // ── Prepínanie stránok ──
  const mobil = () => window.matchMedia('(max-width: 760px)').matches;
  const tablet = () => window.matchMedia('(max-width: 1100px)').matches;
  let ulozeneMini = null;
  try { ulozeneMini = localStorage.getItem('adm_nav_mini'); } catch (e) {}
  if (ulozeneMini === '1' || (ulozeneMini === null && tablet() && !mobil())) document.body.classList.add('nav-mini');

  window.admMenu = function (otvor) {
    if (mobil()) {
      document.body.classList.toggle('nav-open', otvor === undefined ? !document.body.classList.contains('nav-open') : otvor);
      return;
    }
    const mini = !document.body.classList.contains('nav-mini');
    document.body.classList.toggle('nav-mini', mini);
    try { localStorage.setItem('adm_nav_mini', mini ? '1' : '0'); } catch (e) {}
  };

  function povolena(k) {
    const p = STRANKY.find(x => x.id === k);
    const rola = (window.HK && window.HK.rola) || 'admin';
    return !!p && (rola === 'admin' || p.m);
  }
  function ukaz(k) {
    if (!povolena(k)) k = 'prehlad';
    document.querySelectorAll('.admin-page').forEach(s => s.classList.toggle('on', s.dataset.page === k));
    nav.querySelectorAll('a').forEach(a => a.classList.toggle('on', a.dataset.page === k));
    const p = STRANKY.find(x => x.id === k);
    document.getElementById('adm-crumb').textContent = p ? (p.g ? p.g + ' · ' : '') + p.n : '';
    document.body.classList.remove('nav-open');
    try { localStorage.setItem('adm_strana', k); } catch (e) {}
    window.scrollTo(0, 0);
    window.HK_STRANKA = k;
    document.dispatchEvent(new CustomEvent('hk:stranka', { detail: { id: k } }));
    if (k === 'prehlad') prehlad();
  }
  window.HK_UKAZ = ukaz;

  // ── Prehľad + odznaky v menu ──
  const txt = id => { const el = document.getElementById(id); return el ? el.textContent.trim() : ''; };
  const cislo = id => parseInt(txt(id), 10) || 0;
  function prehlad() {
    const dealy = cislo('count-pending'), kody = cislo('coupcount-pending'), kom = cislo('ccount-pending');
    [['dealy', dealy], ['kody', kody], ['komentare', kom]].forEach(([k, n]) => {
      const b = document.getElementById('nb-' + k); if (b) b.textContent = n ? n : '';
    });
    zvoncek();
    const el = document.getElementById('ph-grid');
    if (!el || !document.querySelector('.admin-page[data-page="prehlad"].on')) return;
    const aff = window.HK_AFF || {}, plan = window.HK_PLAN || [];
    const admin = !window.HK || window.HK.rola !== 'moderator';
    const karta = (k, lab, num, sub, alert) => `<a class="ph-card" href="#${k}">
        <div class="ph-lab">${ikona(k)}${lab}</div><div class="ph-num${alert ? ' alert' : ''}">${num}</div><div class="ph-sub">${sub}</div></a>`;
    el.innerHTML =
      karta('dealy', 'Dealy na schválenie', dealy, `naplánované: <b>${cislo('count-planned')}</b> · zverejnené: <b>${cislo('count-approved')}</b>`, dealy > 0) +
      karta('kody', 'Kódy na schválenie', kody, 'zľavové kódy od návštevníkov', kody > 0) +
      karta('komentare', 'Komentáre na schválenie', kom, 'komentáre pri dealoch', kom > 0) +
      (admin ? karta('navstevnost', 'Návštevy dnes', txt('visits-today') || '–', `za 7 dní: <b>${txt('visits-7d') || '–'}</b>`) +
        karta('affiliate', 'Affiliate', aff.zap ? 'Zapnuté' : 'Vypnuté',
          `zarába <b>${aff.zarabaju ?? '–'} / ${aff.spolu ?? '–'}</b> dealov · kampaní: <b>${aff.domen ?? '–'}</b>`) +
        `<a class="ph-card" href="#planovac"><div class="ph-lab">${ikona('planovac')}Automatizácia</div>
          <div class="ph-list">${plan.length ? plan.map(u => `${u.zap ? '' : '⏸ '}<b>${u.nazov}</b> <span>· ${u.kedy}</span>`).join('<br>') : 'načítavam…'}</div></a>` : '');
  }

  // ── Zvonček s upozorneniami ──
  // Zdroje: čakajúce položky (z počtov v admine) a čokoľvek, čo moduly
  // zapíšu do window.HK_UPOZORNENIA[zdroj] = [{ text, href, typ }].
  window.HK_UPOZORNENIA = window.HK_UPOZORNENIA || {};
  function upozornenia() {
    const z = [];
    const dealy = cislo('count-pending'), kody = cislo('coupcount-pending'), kom = cislo('ccount-pending');
    const sk = (n, a, b, c) => `${n} ${n === 1 ? a : (n >= 2 && n <= 4 ? b : c)}`;
    if (dealy) z.push({ text: `${sk(dealy, 'deal čaká', 'dealy čakajú', 'dealov čaká')} na schválenie`, href: '#dealy', typ: 'info' });
    if (kody) z.push({ text: `${sk(kody, 'zľavový kód čaká', 'zľavové kódy čakajú', 'zľavových kódov čaká')} na schválenie`, href: '#kody', typ: 'info' });
    if (kom) z.push({ text: `${sk(kom, 'komentár čaká', 'komentáre čakajú', 'komentárov čaká')} na schválenie`, href: '#komentare', typ: 'info' });
    Object.values(window.HK_UPOZORNENIA).forEach(zoz => (zoz || []).forEach(u => z.push(u)));
    return z;
  }
  function zvoncek() {
    const z = upozornenia();
    const b = document.getElementById('adm-bell-n');
    if (b) {
      const chyby = z.filter(u => u.typ === 'chyba').length;
      b.textContent = z.length || '';
      b.classList.toggle('chyba', chyby > 0);
    }
    const panel = document.getElementById('adm-bell-panel');
    if (panel && !panel.hidden) kresliZvoncek();
  }
  function kresliZvoncek() {
    const z = upozornenia();
    document.getElementById('adm-bell-panel').innerHTML = `<div class="bell-head">Upozornenia</div>` +
      (z.length ? z.map(u => `<a class="bell-it ${esc(u.typ || 'info')}" href="${esc(u.href || '#prehlad')}">
        <svg class="ix"><use href="#ix-${u.typ === 'chyba' ? 'alert' : (u.typ === 'cas' ? 'clock' : 'bell')}"></use></svg><span>${esc(u.text)}</span></a>`).join('')
        : '<p class="bell-nic">Všetko je vybavené.</p>') +
      `<label class="bell-notif"><input type="checkbox" id="bell-notif"> Upozorniť aj notifikáciou prehliadača</label>`;
    const ch = document.getElementById('bell-notif');
    ch.checked = localStorage.getItem('adm_notif') === '1' && window.Notification && Notification.permission === 'granted';
    ch.onchange = async () => {
      if (ch.checked && window.Notification) {
        const p = await Notification.requestPermission();
        ch.checked = p === 'granted';
      }
      try { localStorage.setItem('adm_notif', ch.checked ? '1' : '0'); } catch (e) {}
    };
  }
  window.HK_ZVONCEK = zvoncek;
  document.getElementById('adm-bell').addEventListener('click', e => {
    e.stopPropagation();
    const panel = document.getElementById('adm-bell-panel');
    panel.hidden = !panel.hidden;
    if (!panel.hidden) kresliZvoncek();
  });
  document.addEventListener('click', e => {
    const panel = document.getElementById('adm-bell-panel');
    if (panel && !panel.hidden && !e.target.closest('#adm-bell-panel')) panel.hidden = true;
  });

  // Notifikácia prehliadača pri novom deale na schválenie, keď je admin
  // otvorený na pozadí (zapína sa v zvončeku).
  let poslednyPocet = null;
  setInterval(() => {
    const n = cislo('count-pending') + cislo('coupcount-pending') + cislo('ccount-pending');
    if (poslednyPocet !== null && n > poslednyPocet && document.hidden
        && localStorage.getItem('adm_notif') === '1' && window.Notification && Notification.permission === 'granted') {
      try { new Notification('HenKukaj admin', { body: `Na schválenie čaká ${n} položiek.`, tag: 'hk-admin' }); } catch (e) {}
    }
    poslednyPocet = n;
  }, 5000);

  // ── Rýchle hľadanie (Ctrl+K) ──
  // Stránky, dealy, kódy a príkazy na jednom mieste.
  const PRIKAZY = [
    { n: 'Pridať deal z odkazu', h: '#pridat', k: 'nový' },
    { n: 'Skontrolovať platnosť dealov teraz', h: '#platnost', k: 'kontrola odkazy' },
    { n: 'Naplánovať príspevok na Facebook', h: '#facebook', k: 'fb' },
    { n: 'Stiahnuť zálohu', h: '#zaloha', k: 'export' },
    { n: 'Vytvoriť UTM odkaz', h: '#utm', k: 'kampaň' },
    { n: 'Importovať provízie z Dognetu', h: '#provizie', k: 'csv' },
  ];
  let pal = null, palVysl = [], palI = 0;
  function otvorPaletu() {
    if (!pal) {
      pal = document.createElement('div');
      pal.className = 'pal-ov';
      pal.innerHTML = `<div class="pal" role="dialog" aria-label="Rýchle hľadanie">
          <div class="pal-in"><svg class="ix"><use href="#ix-search"></use></svg>
            <input type="text" id="pal-q" placeholder="Hľadaj stránku, deal, kód alebo príkaz…" autocomplete="off"><kbd>Esc</kbd></div>
          <div class="pal-list" id="pal-list"></div></div>`;
      document.body.appendChild(pal);
      pal.addEventListener('click', e => {
        if (e.target === pal) zavriPaletu();
        const it = e.target.closest('[data-i]');
        if (it) vyber(Number(it.dataset.i));
      });
      pal.querySelector('#pal-q').addEventListener('input', hladajPal);
      pal.querySelector('#pal-q').addEventListener('keydown', e => {
        if (e.key === 'ArrowDown') { palI = Math.min(palVysl.length - 1, palI + 1); kresliPal(); e.preventDefault(); }
        if (e.key === 'ArrowUp') { palI = Math.max(0, palI - 1); kresliPal(); e.preventDefault(); }
        if (e.key === 'Enter') vyber(palI);
        if (e.key === 'Escape') zavriPaletu();
      });
    }
    pal.hidden = false;
    const inp = pal.querySelector('#pal-q');
    inp.value = '';
    hladajPal();
    inp.focus();
  }
  function zavriPaletu() { if (pal) pal.hidden = true; }
  function hladajPal() {
    const q = norm(pal.querySelector('#pal-q').value.trim());
    const slova = q.split(/\s+/).filter(Boolean);
    const sedi = t => slova.every(w => norm(t).includes(w));
    const rola = (window.HK && window.HK.rola) || 'admin';
    const vysl = [];
    STRANKY.filter(p => rola === 'admin' || p.m).forEach(p => {
      if (!slova.length || sedi(p.n + ' ' + (p.k || '') + ' ' + p.g)) vysl.push({ typ: 'Stránka', n: p.n, sub: p.g, h: '#' + p.id, ik: p.id });
    });
    if (rola === 'admin') PRIKAZY.forEach(p => { if (!slova.length || sedi(p.n + ' ' + p.k)) vysl.push({ typ: 'Príkaz', n: p.n, h: p.h, ik: 'pridat' }); });
    if (slova.length && window.HK) {
      (window.HK.deals || []).filter(d => sedi(`${d.title} ${d.store}`)).slice(0, 8).forEach(d =>
        vysl.push({ typ: 'Deal', n: d.title || '(bez názvu)', sub: `${d.store || ''} · ${({ pending: 'na schválenie', approved: 'zverejnený', rejected: 'zamietnutý', archived: 'archív', planned: 'naplánovaný', scheduled: 'naplánovaný' })[d.status] || d.status}`, deal: d.id, ik: 'dealy' }));
      (window.HK.coupons || []).filter(c => sedi(`${c.code} ${c.store}`)).slice(0, 5).forEach(c =>
        vysl.push({ typ: 'Kód', n: c.code, sub: c.store, h: '#kody', ik: 'kody' }));
    }
    palVysl = vysl.slice(0, 30);
    palI = 0;
    kresliPal();
  }
  function kresliPal() {
    const el = pal.querySelector('#pal-list');
    el.innerHTML = palVysl.length ? palVysl.map((v, i) => `<div class="pal-it${i === palI ? ' on' : ''}" data-i="${i}">
        ${ikona(v.ik)}<span class="pal-n">${esc(v.n)}${v.sub ? `<small>${esc(v.sub)}</small>` : ''}</span><span class="pal-typ">${v.typ}</span></div>`).join('')
      : '<p class="pal-nic">Nič sa nenašlo.</p>';
    const on = el.querySelector('.on');
    if (on) on.scrollIntoView({ block: 'nearest' });
  }
  function vyber(i) {
    const v = palVysl[i];
    if (!v) return;
    zavriPaletu();
    if (v.deal) window.HK.otvorDeal(v.deal);
    else location.hash = v.h;
  }
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      if (document.getElementById('admin-view').style.display === 'none') return;
      e.preventDefault();
      otvorPaletu();
    }
  });
  document.getElementById('adm-hladaj').addEventListener('click', otvorPaletu);

  // Po prihlásení podľa roly prekreslíme menu (moderátor vidí menej).
  document.addEventListener('hk:prihlaseny', () => { kresliMenu(); ukaz((location.hash || '').slice(1) || 'prehlad'); });

  window.addEventListener('hashchange', () => ukaz(location.hash.slice(1)));
  let start = location.hash.slice(1);
  if (!start) { try { start = localStorage.getItem('adm_strana') || 'prehlad'; } catch (e) { start = 'prehlad'; } }
  ukaz(start);
  setInterval(prehlad, 2500);
  window.addEventListener('load', () => setTimeout(prehlad, 1500));
})();
