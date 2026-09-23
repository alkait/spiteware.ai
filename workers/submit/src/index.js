// Cloudflare Worker: the two forms on spiteware.ai, submit.html (a link) and contact.html (email, subject,
// message), each turned into one email to MAIL_TO. Nothing is stored. A post has to get past, in order: the
// Origin check, a per-address rate limit, a honeypot and a fill timer, a check of the fields, and Cloudflare
// Turnstile. Then Resend carries it. The JSON it takes and the two forms are a pair: change one, change the other.

const ORIGINS = ['https://spiteware.ai', 'http://localhost:4321', 'http://127.0.0.1:4321'];
// a message plus a Turnstile token (up to 2 KB) fits with room to spare
const MAX_BODY = 12000;
// a pasted link is quick, a script is quicker; three fields take longer
const MIN_FILL_MS = { submit: 1000, contact: 3000 };
const MAX_URL = 300;
const MAX_EMAIL = 254;
const MAX_SUBJECT = 120;
const MAX_MESSAGE = 5000;

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

    const kind = body.kind === 'contact' ? 'contact' : 'submit';
    // bots get a thank-you and nothing else, so they learn nothing
    if (body._gotcha || !(Number(body.t) >= MIN_FILL_MS[kind])) return jsonResponse({ ok: true }, 200, origin);

    const stamp = `${new Date().toISOString()}`;
    // plain text only: nothing a stranger typed is ever rendered as HTML
    let mail;
    if (kind === 'contact') {
      const email = str(body.email), subject = str(body.subject), message = str(body.body);
      if (!email || email.length > MAX_EMAIL || !isEmail(email)) return jsonResponse({ error: "That's not an email address." }, 400, origin);
      if (!subject || subject.length > MAX_SUBJECT || !oneLine(subject)) return jsonResponse({ error: 'The subject is empty or too long.' }, 400, origin);
      if (!message || message.length > MAX_MESSAGE) return jsonResponse({ error: 'The message is empty or too long.' }, 400, origin);
      mail = {
        from: env.MAIL_FROM,
        to: env.MAIL_TO,
        reply_to: email,
        subject: `[contact] ${subject}`,
        text: `From: ${email}\n\n${message}\n\n--\nSent from spiteware.ai/contact.html · ${stamp}`,
      };
    } else {
      const link = str(body.url);
      if (!link || link.length > MAX_URL || !isHttpUrl(link)) return jsonResponse({ error: "That's not a link." }, 400, origin);
      mail = {
        from: env.MAIL_FROM,
        to: env.MAIL_TO,
        subject: `[submit] ${new URL(link).hostname.replace(/^www\./, '')}`,
        text: `${link}\n\n--\nSent from spiteware.ai/submit.html · ${stamp}`,
      };
    }

    // after validation, because a Turnstile token only verifies once
    if (!(await passedTurnstile(body['cf-turnstile-response'], ip, env))) {
      return jsonResponse({ error: 'The bot check failed. Reload the page and try again.' }, 403, origin);
    }

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

function str(v) { return typeof v === 'string' ? v.trim() : ''; }

// No control characters, so it is safe in a subject line or a Reply-To.
function oneLine(v) { return !/[\u0000-\u001F\u007F]/.test(v); }

// One address, no whitespace, a dot in the domain. Resend does the rest.
function isEmail(v) { return oneLine(v) && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v); }

// A full http(s) link with no whitespace or control characters in it, so it is safe in a subject line.
function isHttpUrl(v) {
  if (/[\s\u0000-\u001F\u007F]/.test(v)) return false;
  try {
    const u = new URL(v);
    return (u.protocol === 'https:' || u.protocol === 'http:') && u.hostname.includes('.');
  } catch { return false; }
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
