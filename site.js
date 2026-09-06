(() => {
  const $ = (q, r=document) => r.querySelector(q);
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  window.SW = { esc };

  // Marquee: duplicate content so it loops seamlessly
  const t = $('#ticker'); if (t) t.innerHTML += t.innerHTML;

  // Card renderer shared by the home grid and the catalog
  SW.card = a => `<a class="card" href="${esc(a.url)}" target="_blank" rel="noopener">
    <div class="card__top"><div class="card__icon">${esc(a.icon||'🔧')}</div>
      <div class="kills">replaces<s>${esc(a.replaces.name)} · ${esc(a.replaces.price)}</s></div></div>
    <h3>${esc(a.name)}</h3><p>${esc(a.tagline)}</p>
    <blockquote class="card__grudge">“${esc(a.grudge.quote)}”</blockquote>
    <div class="chips">${(a.tags||[]).map(t=>`<span class="chip">${esc(t)}</span>`).join('')}${a.vibe_coded?'<span class="chip chip--vibe">vibe coded</span>':''}</div>
    <div class="card__meta"><span>by ${esc(a.builder.name)}</span><span title="spite score">🔥 ${esc(a.spite_score)}/10</span></div></a>`;

  SW.sortSpite = apps => apps.slice().sort((a,b)=>(b.spite_score-a.spite_score)||(b.added>a.added?1:-1));

  // Load the catalog once; pages subscribe via SW.ready(fn)
  const subs = [];
  SW.ready = fn => SW.apps ? fn(SW.apps) : subs.push(fn);
  fetch('data/apps.json').then(r=>r.json()).then(apps => {
    SW.apps = apps;
    document.querySelectorAll('[data-apps]').forEach(el=>el.textContent=apps.length.toLocaleString('en-US'));
    document.querySelectorAll('[data-from-apps]').forEach(el=>el.dataset.count=apps.length);
    const victims = new Set(apps.map(a=>(a.replaces?.name||'').trim().toLowerCase()).filter(Boolean)).size;
    document.querySelectorAll('[data-from-victims]').forEach(el=>el.dataset.count=victims);
    subs.forEach(fn=>fn(apps));
  }).catch(()=>{ const g=$('#grid'); if(g) g.innerHTML='<div class="card"><h3>No spite loaded</h3><p>data/apps.json failed to load. Are you opening this from file://? Serve it over http.</p></div>'; });

  // Home grid: top 6 by spite, then a "see all" card
  const grid = $('#grid');
  if (grid && grid.dataset.limit) SW.ready(apps => {
    const top = SW.sortSpite(apps).slice(0, +grid.dataset.limit);
    grid.innerHTML = top.map(SW.card).join('') +
      `<a class="card card--more" href="apps.html"><div>see all ${apps.length} grudges →<small>updated whenever someone gets mad</small></div></a>`;
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
