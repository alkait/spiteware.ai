(() => {
  const $ = (q, r=document) => r.querySelector(q);
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  window.SW = { esc };

  // Tag vocabulary — mirrors the closed list in criteria.md. Rows render in this order,
  // so a tag keeps its spot on the bar as the catalog grows.
  // Derived from booleans on each app, not from typed tags.
  SW.DERIVED = [['open-source', a => a.open_source], ['vibe coded', a => a.vibe_coded]];
  SW.FACETS = [
    ["where it runs", ["macos","ios","windows","web","desktop","browser-extension"]],
    ["how it's free", ["self-hosted","local-first","byo-key","privacy"]],
    ["what it does",  ["ai","career","dev-tools","dictation","finance","forms","games","health",
                       "images","learning","marketing","productivity","travel","utilities","video","writing"]],
  ];

  // Nav: a link to a section of the page you're on takes the marker while that
  // section is in the URL (#submit), otherwise the page's own link keeps it.
  const nav = $('nav[aria-label="Main"]');
  if (nav) {
    const links = [...nav.querySelectorAll('a')];
    const dflt = links.find(a => a.hasAttribute('aria-current'));
    const path = p => p.replace(/index\.html$/, '');
    const syncNav = () => {
      const here = links.find(a => a.hash && a.hash === location.hash && path(a.pathname) === path(location.pathname));
      links.forEach(a => a === (here || dflt) ? a.setAttribute('aria-current', a === here ? 'true' : 'page')
                                             : a.removeAttribute('aria-current'));
    };
    addEventListener('hashchange', syncNav); syncNav();
  }

  // Mobile menu: below 700px the nav is a panel behind a button. The button only
  // exists once JS is here, so a no-JS phone still gets the plain wrapped nav.
  const menuBtn = $('#menubtn'), header = $('header');
  if (menuBtn && header) {
    document.documentElement.classList.add('js');
    const setOpen = v => { header.classList.toggle('is-open', v); menuBtn.setAttribute('aria-expanded', String(v)); };
    menuBtn.addEventListener('click', () => setOpen(!header.classList.contains('is-open')));
    // Tapping a link, hitting escape, or growing past the breakpoint all close it.
    nav?.addEventListener('click', e => { if (e.target.closest('a')) setOpen(false); });
    addEventListener('keydown', e => { if (e.key === 'Escape') setOpen(false); });
    matchMedia('(min-width:700px)').addEventListener('change', () => setOpen(false));
  }

  // Marquee: duplicate content so it loops seamlessly
  const t = $('#ticker'); if (t) t.innerHTML += t.innerHTML;

  // Card renderer shared by the home grid and the catalog
  // `added` is a plain YYYY-MM-DD string. Slicing it beats new Date(): that parses as
  // UTC midnight, so a negative-offset zone renders the day before — and on the 1st,
  // the wrong month.
  const MON = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
  SW.month = d => /^\d{4}-\d{2}-\d{2}/.test(d||'') ? `${MON[+d.slice(5,7)-1]} ${d.slice(0,4)}` : '';
  SW.victim = a => { const r=a.replaces||{}; const n=(r.name||'').trim(), p=(r.price||'').trim(); return esc(n&&p ? `${n} · ${p}` : n ? n : p ? `a paywall · ${p}` : 'a paywall'); };
  // Hall of fame address and avatar account. scripts/pages.py writes the pages and
  // mirrors both of these, plus SW.victim and SW.card: change one, change the other.
  SW.fame = a => `/hall-of-fame/${encodeURIComponent(a.builder.handle.toLowerCase())}/${encodeURIComponent(a.slug)}/`;
  SW.gh = a => (/^https:\/\/github\.com\/([^\/]+)\/?$/.exec(a.builder.url || '') || [])[1] || (a.repo || '').split('/')[0];
  SW.card = a => `<a class="card" href="${SW.fame(a)}">
    ${a.added ? `<time class="card__date" datetime="${esc(a.added)}" title="added to the catalog">${SW.month(a.added)}</time>` : ''}
    <div class="card__top"><div class="card__icon">${esc(a.icon||'🔧')}</div>
      <div class="kills">replaces<s>${SW.victim(a)}</s></div></div>
    <h3>${esc(a.name)}</h3><p>${esc(a.tagline)}</p>
    <blockquote class="card__grudge">“${esc(a.grudge.quote)}”</blockquote>
    <div class="chips">${(a.tags||[]).map(t=>`<span class="chip">${esc(t)}</span>`).join('')}${a.open_source?'<span class="chip">open-source</span>':''}${a.vibe_coded?'<span class="chip chip--vibe">vibe coded</span>':''}</div>
    <div class="card__meta"><span>by ${esc(a.builder.name)}</span><span title="spite score">🔥 ${esc(a.spite_score)}/10</span></div></a>`;

  // Newest first; spite score only breaks ties inside the same day.
  SW.sortRecent = apps => apps.slice().sort((a,b)=>(b.added>a.added?1:b.added<a.added?-1:0)||(b.spite_score-a.spite_score));

  // Load the catalog once; pages subscribe via SW.ready(fn)
  const subs = [];
  SW.ready = fn => SW.apps ? fn(SW.apps) : subs.push(fn);
  // An app that got taken down stays in the file with status "dead" (scripts/links.py --bury):
  // it keeps its hall of fame page, and drops off every list and count here.
  fetch('/data/apps.json').then(r=>r.json()).then(all => {
    const apps = SW.apps = all.filter(a => a.status !== 'dead');
    document.querySelectorAll('[data-apps]').forEach(el=>el.textContent=apps.length.toLocaleString('en-US'));
    document.querySelectorAll('[data-from-apps]').forEach(el=>el.dataset.count=apps.length);
    const victims = new Set(apps.map(a=>(a.replaces?.name||'').trim().toLowerCase()).filter(Boolean)).size;
    document.querySelectorAll('[data-from-victims]').forEach(el=>el.dataset.count=victims);
    subs.forEach(fn=>fn(apps));
  }).catch(()=>{ const g=$('#grid'); if(g) g.innerHTML='<div class="card"><h3>No spite loaded</h3><p>data/apps.json failed to load. Are you opening this from file://? Serve it over http.</p></div>'; });

  // Home grid: this week's additions, newest first, then a "see all" card
  const grid = $('#grid');
  if (grid && grid.dataset.limit) SW.ready(apps => {
    // "this week" means the real last 7 days, so the section empties out after a dry
    // week rather than calling month-old apps fresh. Newest first inside the window.
    const since = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
    const fresh = apps.filter(a => a.added >= since);
    const top = SW.sortRecent(fresh).slice(0, +grid.dataset.limit);
    const quiet = `<div class="dry">Nobody got mad this week.<small>the all-time pettiest are one click away →</small></div>`;
    grid.innerHTML = (top.length ? top.map(SW.card).join('') : quiet) +
      `<a class="card card--more" href="apps.html"><div>see all ${apps.length} grudges →<small>updated whenever someone gets mad</small></div></a>`;
  });

  // A deleted GitHub account 404s; fall back to an initial tile rather than a broken image.
  const hues = ['var(--pink)','var(--yellow)','var(--blue)','var(--green)','var(--orange)','var(--purple)'];
  SW.noFace = (img, who) => {
    const d = document.createElement('div');
    d.className = 'gcard__fb';
    d.style.background = hues[who.length % hues.length];
    d.textContent = who[0].toUpperCase();
    img.replaceWith(d);
  };
  // The hall of fame pages ship their avatars in the HTML, so the image may have
  // already failed by the time this runs.
  document.querySelectorAll('img[data-who]').forEach(img => {
    const fb = () => SW.noFace(img, img.dataset.who);
    if (img.complete && !img.naturalWidth && img.src) fb(); else img.addEventListener('error', fb);
  });

  // "copy link" on a hall of fame page
  document.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', () => {
    navigator.clipboard?.writeText(b.dataset.copy).then(() => {
      const was = b.textContent; b.textContent = 'copied ✓';
      setTimeout(() => { b.textContent = was; }, 1600);
    });
  }));

  // Hall of fame: a deck of grudge cards in the hero. Only apps with a repo are dealt,
  // because the builder's GitHub avatar is what makes the card. "Next" flings the top
  // card off and deals a fresh one underneath, so the pile never runs out.
  const deck = $('#deck'), deckN = $('#deckn'), deckBtn = $('#decknext');
  if (deck) SW.ready(apps => {
    const pool = apps.filter(a => a.repo);
    for (let i = pool.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [pool[i], pool[j]] = [pool[j], pool[i]]; }
    const rm = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const total = pool.length;
    let idx = 0, shown = 0;

    const make = a => {
      const who = SW.gh(a);
      const price = (a.replaces.price || '').split(' ')[0];
      const quote = esc(a.grudge.quote).replace(/(\$[\d.,]+(?:\s*\/\s*\w+)?)/, '<em>$1</em>');
      const el = document.createElement('article');
      el.className = 'gcard';
      el.innerHTML = `
        <div class="gcard__who">
          <a class="gcard__pic" href="https://github.com/${esc(who)}" target="_blank" rel="noopener" title="@${esc(who)} on GitHub">
            <img class="gcard__av" src="https://github.com/${esc(who)}.png?size=320" alt="" width="150" height="150">
            <span class="gcard__at">@${esc(who)}</span>
          </a>
          <div class="gcard__by"><b>${esc(a.builder.name)}</b>built ${esc(a.name)}<br>${SW.month(a.added)}</div>
        </div>
        <p class="gcard__q">\u201c${quote}\u201d</p>
        <div class="gcard__foot">
          ${a.replaces.name ? `<span class="kills">replaces<s>${esc(a.replaces.name)}${price ? ' · ' + esc(price) : ''}</s></span>` : ''}
          <a class="gcard__go" href="${SW.fame(a)}">${esc(a.name)} \u2192</a>
          <span class="gcard__score" title="spite score">\ud83d\udd25 ${esc(a.spite_score)}/10</span>
        </div>`;
      el.querySelector('img').addEventListener('error', function () { SW.noFace(this, who); });
      return el;
    };
    const deal = () => make(pool[idx++ % total]);

    // Three cards: the top one, then two peeking out behind it.
    const cards = [deal(), deal(), deal()];
    const layout = () => {
      cards.forEach((c, i) => { c.className = 'gcard gcard--' + (i + 1); c.setAttribute('aria-hidden', i ? 'true' : 'false'); });
      shown++;
      deckN.textContent = `grudge ${((shown - 1) % total) + 1} / ${total}`;
    };
    deck.textContent = '';
    cards.slice().reverse().forEach(c => deck.appendChild(c));
    layout();

    let busy = false;
    deckBtn.addEventListener('click', () => {
      if (busy) return;
      const top = cards.shift();
      const fresh = deal();
      cards.push(fresh);
      deck.insertBefore(fresh, deck.firstChild); // bottom of the pile
      if (rm) { top.remove(); layout(); return; }
      busy = true;
      top.className = 'gcard gcard--out';
      top.setAttribute('aria-hidden', 'true');
      layout();
      setTimeout(() => { top.remove(); busy = false; }, 380);
    });
  });

  // Visitor counter (placeholder until backend exists): seed + per-browser increment
  const odo = $('#odo');
  if (odo) {
    let n = 48213;
    try { const k='sw_visits'; const v=(+localStorage.getItem(k)||0)+1; localStorage.setItem(k,v); n += v; } catch(e){}
    const show = v => { odo.innerHTML = String(v).padStart(6,'0').split('').map(d=>`<span>${d}</span>`).join(''); };
    show(0);
    const start = performance.now(), dur = 900;
    const tick = now => { const p=Math.min(1,(now-start)/dur), e=1-Math.pow(1-p,3); show(Math.round(n*e)); if(p<1) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  }

  // Count-up stats when they scroll into view
  const compact = new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1});
  const fmt = (el,v) => (el.dataset.prefix||'') + ('compact' in el.dataset ? compact.format(v) : v.toLocaleString('en-US')) + (el.dataset.suffix||'');
  const els = document.querySelectorAll('[data-count]');
  const rm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const io = new IntersectionObserver(entries => entries.forEach(en => {
    if(!en.isIntersecting) return; io.unobserve(en.target);
    const el=en.target, target=+el.dataset.count;
    if(rm||!target){ el.textContent=fmt(el,target); return; }
    const s=performance.now(), d=1200;
    const f = now => { const p=Math.min(1,(now-s)/d), e=1-Math.pow(1-p,4); el.textContent=fmt(el,Math.round(target*e)); if(p<1) requestAnimationFrame(f); };
    requestAnimationFrame(f);
  }), {threshold:.4});
  els.forEach(el=>io.observe(el));
})();
