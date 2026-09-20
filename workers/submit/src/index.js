// Cloudflare Worker: the form on spiteware.ai/submit.html, turned into one email to hello@spiteware.ai.
// Nothing is stored. A submission has to get past, in order: the Origin check, a per-address rate limit,
// a honeypot and a fill timer, field validation, and Cloudflare Turnstile. Then Resend carries it.
// The JSON it takes and the form in submit.html are a pair: change one, change the other.

const ORIGINS = ['https://spiteware.ai', 'http://localhost:4321', 'http://127.0.0.1:4321'];
const MAX_BODY = 8000;
// nobody fills seven fields in under three seconds
const MIN_FILL_MS = 3000;

// name → [label in the email, max length, kind]
const FIELDS = {
  url:      ['App',          300, 'url'],
  repo:     ['Repo',         300, 'url'],
  replaces: ['Replaces',      80, 'line'],
  price:    ['It wanted',     40, 'line'],
  why:      ['Why',          600, 'text'],
  source:   ['Said it here', 300, 'url'],
  name:     ['From',          60, 'line'],
  email:    ['Email',        120, 'email'],
};
const REQUIRED = ['url', 'why'];

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const allowed = ORIGINS.includes(origin);

    if (request.method === 'OPTIONS') return new Response(null, { status: allowed ? 204 : 403, headers: corsHeaders(origin) });
    if (request.method !== 'POST') return jsonResponse({ error: 'POST only.' }, 405, origin);
    // a browser on the site always sends it; curl and other people's pages don't
    if (!allowed) return jsonResponse({ error: 'Wrong origin.' }, 403, origin);

    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    const { success } = await env.LIMITER.limit({ key: ip });
    if (!success) return jsonResponse({ error: 'Slow down. Try again in a minute.' }, 429, origin);

    const raw = await request.text();
    if (raw.length > MAX_BODY) return jsonResponse({ error: 'Too long.' }, 413, origin);
    let body;
    try { body = JSON.parse(raw); } catch { body = null; }
    if (!body || typeof body !== 'object' || Array.isArray(body)) return jsonResponse({ error: 'Bad JSON.' }, 400, origin);

    // bots get a thank-you and nothing else, so they learn nothing
    if (body._gotcha || !(Number(body.t) >= MIN_FILL_MS)) return jsonResponse({ ok: true }, 200, origin);

    const { fields, error } = clean(body);
    if (error) return jsonResponse({ error }, 400, origin);

    // after validation, because a Turnstile token only verifies once
    if (!(await passedTurnstile(body['cf-turnstile-response'], ip, env))) {
      return jsonResponse({ error: 'The bot check failed. Reload the page and try again.' }, 403, origin);
    }

    const mail = {
      from: env.MAIL_FROM,
      to: env.MAIL_TO,
      subject: subjectFor(fields),
      // plain text only: nothing a stranger typed is ever rendered as HTML
      text: textFor(fields),
    };
    if (fields.email) mail.reply_to = fields.email;

    // set in .dev.vars only: `wrangler dev` must never send, so it logs the email instead
    if (env.DRY_RUN) {
      console.log(JSON.stringify(mail, null, 2));
      return jsonResponse({ ok: true, dry: true }, 200, origin);
    }

    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(mail),
    });
    if (!res.ok) {
      console.error('Resend', res.status, await res.text());
      return jsonResponse({ error: `That didn't send. Email ${env.MAIL_TO} instead.` }, 502, origin);
    }
    return jsonResponse({ ok: true }, 200, origin);
  }
};

// Trim, cap and type-check every known field; anything else in the body is dropped.
function clean(body) {
  const fields = {};
  for (const [name, [label, max, kind]] of Object.entries(FIELDS)) {
    let v = typeof body[name] === 'string' ? body[name] : '';
    // control characters out; single-line fields lose their newlines too, so nothing can forge a header or a row
    v = v.replace(kind === 'text' ? /[\u0000-\u0009\u000B-\u001F\u007F]/g : /[\u0000-\u001F\u007F]/g, ' ').trim();
    if (!v) {
      if (REQUIRED.includes(name)) return { error: `${label} is missing.` };
      continue;
    }
    if (v.length > max) return { error: `${label} is too long (${max} characters at most).` };
    if (kind === 'url' && !isHttpUrl(v)) return { error: `${label} has to be a full link, starting with https://.` };
    if (kind === 'email' && !/^[^\s@<>",;]+@[^\s@<>",;]+\.[^\s@<>",;]+$/.test(v)) return { error: `${label} doesn't look like an address.` };
    fields[name] = v;
  }
  return { fields };
}

function isHttpUrl(v) {
  try {
    const u = new URL(v);
    return (u.protocol === 'https:' || u.protocol === 'http:') && u.hostname.includes('.');
  } catch { return false; }
}

async function passedTurnstile(token, ip, env) {
  if (typeof token !== 'string' || !token || token.length > 2048) return false;
  const res = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ secret: env.TURNSTILE_SECRET, response: token, remoteip: ip }),
  });
  if (!res.ok) return false;
  return (await res.json()).success === true;
}

function subjectFor(f) {
  let host = f.url;
  try { host = new URL(f.url).hostname.replace(/^www\./, ''); } catch {}
  const victim = f.replaces ? ` replaces ${f.replaces}${f.price ? ' · ' + f.price : ''}` : '';
  return `[submit] ${host}${victim}`.slice(0, 160);
}

function textFor(f) {
  const rows = Object.entries(FIELDS)
    .filter(([name]) => f[name] && name !== 'why')
    .map(([name, [label]]) => `${(label + ':').padEnd(14)}${f[name]}`);
  return [
    ...rows,
    '',
    'Why, in their words:',
    f.why,
    '',
    '--',
    `Sent from spiteware.ai/submit.html · ${new Date().toISOString()}`,
    f.email ? 'Reply goes to the submitter.' : 'No email given: there is nobody to reply to.',
  ].join('\n');
}

function corsHeaders(origin) {
  return {
    'Access-Control-Allow-Origin': ORIGINS.includes(origin) ? origin : ORIGINS[0],
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    'Vary': 'Origin',
  };
}

function jsonResponse(data, status, origin) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...corsHeaders(origin) }
  });
}
