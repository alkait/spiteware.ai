// Proxies the Google Analytics 4 Data API for /analytics.html, so the service account key
// never reaches a browser. One GET /analytics?period=… runs every report the page shows,
// and the answer is cached for three hours.
// Secrets: GA4_PROPERTY_ID, GCP_CLIENT_EMAIL, GCP_PRIVATE_KEY. Var: GA4_TIMEZONE.

const CACHE_TTL = 10800;
const TOKEN_URI = 'https://oauth2.googleapis.com/token';
const PERIODS = { today: [0, 1, 'Today'], yesterday: [1, 1, 'Yesterday'], '7d': [0, 7, 'Last 7 days'], '30d': [0, 30, 'Last 30 days'], '90d': [0, 90, 'Last 90 days'] };

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders() });
    if (url.pathname === '/analytics' && request.method === 'GET') return handleAnalytics(url, ctx, env);
    return new Response('Not Found', { status: 404 });
  }
};

async function handleAnalytics(url, ctx, env) {
  try {
    const range = parsePeriod(url.searchParams.get('period') || '7d', url.searchParams.get('start'), url.searchParams.get('end'), env.GA4_TIMEZONE);
    if (!range) return jsonResponse({ error: 'Invalid period. Use: today, yesterday, 7d, 30d, 90d, or custom with start & end params' }, 400);
    const { startDate, endDate, prevStartDate, prevEndDate, label } = range;

    // skipping the cache is for `wrangler dev` only: in production it would let anyone burn the GA4 quota
    const noCache = url.searchParams.get('nocache') === '1' && ['localhost', '127.0.0.1'].includes(url.hostname);
    const cacheRequest = new Request(`${url.origin}/analytics?_ck=ga4-v1-${startDate}-${endDate}`);
    if (!noCache) {
      const cached = await caches.default.match(cacheRequest);
      if (cached) return jsonResponse({ ...(await cached.json()), cached: true });
    }

    const accessToken = await getAccessToken(env);
    const apiUrl = `https://analyticsdata.googleapis.com/v1beta/properties/${env.GA4_PROPERTY_ID}:runReport`;
    const headers = { 'Authorization': `Bearer ${accessToken}`, 'Content-Type': 'application/json' };
    const dateRanges = [{ startDate, endDate }];

    async function report(body) {
      const res = await fetch(apiUrl, { method: 'POST', headers, body: JSON.stringify({ dateRanges, ...body }) });
      if (!res.ok) throw new ApiError(res.status, await res.text());
      return res.json();
    }
    const top = (dimension, metric, limit, where) => report({
      dimensions: [{ name: dimension }],
      metrics: [{ name: metric }],
      orderBys: [{ metric: { metricName: metric }, desc: true }],
      ...(limit ? { limit } : {}),
      ...(where ? { dimensionFilter: { filter: { fieldName: where[0], stringFilter: { value: where[1], matchType: 'EXACT' } } } } : {})
    });
    const sourcesOf = channel => top('sessionSource', 'sessions', 5, ['sessionDefaultChannelGroup', channel]);
    const osOf = device => top('operatingSystem', 'sessions', 5, ['deviceCategory', device]);

    // two batches: GA4 allows ten concurrent requests per property
    const [totalsData, pagesData, countriesData, channelsData, referrersData, searchData, socialData] = await Promise.all([
      report({
        dateRanges: [{ startDate, endDate }, { startDate: prevStartDate, endDate: prevEndDate }],
        metrics: [{ name: 'activeUsers' }, { name: 'sessions' }, { name: 'screenPageViews' }, { name: 'averageSessionDuration' }],
        keepEmptyRows: true
      }),
      report({
        dimensions: [{ name: 'pageTitle' }, { name: 'pagePath' }],
        metrics: [{ name: 'screenPageViews' }],
        orderBys: [{ metric: { metricName: 'screenPageViews' }, desc: true }],
        limit: 10
      }),
      top('countryId', 'activeUsers', 10),
      top('sessionDefaultChannelGroup', 'sessions', 6),
      sourcesOf('Referral'),
      sourcesOf('Organic Search'),
      sourcesOf('Organic Social')
    ]);
    const [videoData, devicesData, osDesktopData, osMobileData, osTabletData, newVsReturningData, dailyData] = await Promise.all([
      sourcesOf('Organic Video'),
      top('deviceCategory', 'sessions'),
      osOf('desktop'),
      osOf('mobile'),
      osOf('tablet'),
      report({ dimensions: [{ name: 'newVsReturning' }], metrics: [{ name: 'activeUsers' }] }),
      report({
        dimensions: [{ name: 'date' }],
        metrics: [{ name: 'activeUsers' }, { name: 'sessions' }, { name: 'screenPageViews' }],
        orderBys: [{ dimension: { dimensionName: 'date' }, desc: false }],
        keepEmptyRows: true
      })
    ]);

    const { current: totals, previous: previousTotals } = parseTotalsWithComparison(totalsData);
    const result = {
      period: label, startDate, endDate, totals, previousTotals,
      newVsReturning: parseNewVsReturning(newVsReturningData),
      dailyBreakdown: parseDailyBreakdown(dailyData),
      topPages: parseTopPages(pagesData),
      topCountries: parseTopCountries(countriesData),
      topChannels: parseTopDimension(channelsData, 'sessions', true),
      channelSources: {
        'Referral': parseTopDimension(referrersData, 'sessions'),
        'Organic Search': parseTopDimension(searchData, 'sessions'),
        'Organic Social': parseTopDimension(socialData, 'sessions'),
        'Organic Video': parseTopDimension(videoData, 'sessions')
      },
      topDevices: parseTopDimension(devicesData, 'sessions', true),
      osPerDevice: {
        desktop: parseTopDimension(osDesktopData, 'sessions'),
        mobile: parseTopDimension(osMobileData, 'sessions'),
        tablet: parseTopDimension(osTabletData, 'sessions')
      },
      fetchTime: new Date().toISOString()
    };

    const responseToCache = new Response(JSON.stringify(result), {
      headers: { 'Content-Type': 'application/json', 'Cache-Control': `public, max-age=${CACHE_TTL}` }
    });
    ctx.waitUntil(caches.default.put(cacheRequest, responseToCache));

    return jsonResponse({ ...result, cached: false });

  } catch (error) {
    if (error instanceof ApiError) return jsonResponse({ error: 'GA4 API error', status: error.status, details: error.message }, error.status);
    return jsonResponse({ error: 'Internal server error', message: error.message }, 500);
  }
}

class ApiError extends Error {
  constructor(status, body) { super(body); this.status = status; }
}

// Dates are YYYY-MM-DD strings throughout, and the arithmetic is done in UTC so it can't slip a day.
const shift = (date, days) => new Date(Date.parse(date + 'T00:00:00Z') + days * 86400000).toISOString().slice(0, 10);

function todayIn(timeZone) {
  try { return new Intl.DateTimeFormat('en-CA', { timeZone: timeZone || 'UTC' }).format(new Date()); }
  catch { return new Date().toISOString().slice(0, 10); }
}

// The previous range is the same number of days, ending the day before this one starts.
function parsePeriod(period, customStart, customEnd, timeZone) {
  const today = todayIn(timeZone);
  let startDate, endDate, days, label;
  if (PERIODS[period]) {
    const [ago, span, name] = PERIODS[period];
    endDate = shift(today, -ago); days = span; label = name;
    startDate = shift(endDate, 1 - days);
  } else if (period === 'custom') {
    const dateRe = /^\d{4}-\d{2}-\d{2}$/;
    if (!dateRe.test(customStart || '') || !dateRe.test(customEnd || '')) return null;
    if (isNaN(Date.parse(customStart)) || isNaN(Date.parse(customEnd)) || customStart > customEnd || customStart > today) return null;
    days = Math.round((Date.parse(customEnd) - Date.parse(customStart)) / 86400000) + 1;
    if (days > 365) return null;
    startDate = customStart; endDate = customEnd > today ? today : customEnd; label = 'Custom';
  } else return null;
  return { startDate, endDate, prevStartDate: shift(startDate, -days), prevEndDate: shift(startDate, -1), label };
}

function parseTotalsRow(row) {
  return {
    users: parseInt(row.metricValues[0].value || 0),
    sessions: parseInt(row.metricValues[1].value || 0),
    pageViews: parseInt(row.metricValues[2].value || 0),
    avgSessionDuration: Math.round(parseFloat(row.metricValues[3].value || 0))
  };
}

const EMPTY_TOTALS = { users: 0, sessions: 0, pageViews: 0, avgSessionDuration: 0 };

function parseTotalsWithComparison(data) {
  let current = { ...EMPTY_TOTALS };
  let previous = { ...EMPTY_TOTALS };
  for (const row of data.rows || []) {
    const range = row.dimensionValues && row.dimensionValues[0] ? row.dimensionValues[0].value : 'date_range_0';
    if (range === 'date_range_0') current = parseTotalsRow(row);
    else if (range === 'date_range_1') previous = parseTotalsRow(row);
  }
  return { current, previous };
}

function parseNewVsReturning(data) {
  const result = { new: 0, returning: 0 };
  (data.rows || []).forEach(row => {
    const type = row.dimensionValues[0].value;
    if (type in result) result[type] = parseInt(row.metricValues[0].value || 0);
  });
  return result;
}

function parseDailyBreakdown(data) {
  return (data.rows || []).map(row => {
    const raw = row.dimensionValues[0].value;
    return {
      date: raw.slice(0, 4) + '-' + raw.slice(4, 6) + '-' + raw.slice(6, 8),
      users: parseInt(row.metricValues[0].value || 0),
      sessions: parseInt(row.metricValues[1].value || 0),
      pageViews: parseInt(row.metricValues[2].value || 0)
    };
  }).sort((a, b) => a.date.localeCompare(b.date));
}

const countryNames = new Intl.DisplayNames(['en'], { type: 'region' });

function parseTopCountries(data) {
  return (data.rows || []).map(row => {
    const code = row.dimensionValues[0].value || '';
    let name;
    try { name = countryNames.of(code); } catch { name = code; }
    return { code, name: name || code, users: parseInt(row.metricValues[0].value || 0) };
  });
}

function parseTopPages(data) {
  return (data.rows || []).map(row => ({
    name: row.dimensionValues[0].value || '(not set)',
    path: row.dimensionValues[1].value || '/',
    pageViews: parseInt(row.metricValues[0].value || 0)
  }));
}

// GA4's channel and device names, in plain words
const LABELS = {
  'Direct': 'Direct',
  'Organic Search': 'Search engines',
  'Referral': 'Other sites',
  'Organic Social': 'Social',
  'Paid Search': 'Paid search',
  'Paid Social': 'Paid social',
  'Email': 'Email',
  'Display': 'Display ads',
  'Affiliates': 'Affiliates',
  'Organic Video': 'Video',
  'Paid Video': 'Paid video',
  'Organic Shopping': 'Shopping',
  'Paid Shopping': 'Paid shopping',
  'Unassigned': 'Unassigned',
  '(not set)': 'Unknown',
  'desktop': 'Desktop',
  'mobile': 'Phone',
  'tablet': 'Tablet',
  'smart tv': 'TV'
};

// `key` is GA4's own value, so the page can ask for a row's breakdown whatever the label says
function parseTopDimension(data, metricLabel, labelled) {
  return (data.rows || []).map(row => {
    const key = row.dimensionValues[0].value || '(not set)';
    return { key, name: labelled ? (LABELS[key] || key) : key, [metricLabel]: parseInt(row.metricValues[0].value || 0) };
  });
}

// --- GA4 JWT Auth ---

async function getAccessToken(env) {
  const jwt = await createJWT(env);
  const response = await fetch(TOKEN_URI, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `grant_type=${encodeURIComponent('urn:ietf:params:oauth:grant-type:jwt-bearer')}&assertion=${jwt}`
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Token exchange failed: ${err}`);
  }

  const data = await response.json();
  return data.access_token;
}

async function createJWT(env) {
  const now = Math.floor(Date.now() / 1000);

  const header = { alg: 'RS256', typ: 'JWT' };
  const payload = {
    iss: env.GCP_CLIENT_EMAIL,
    scope: 'https://www.googleapis.com/auth/analytics.readonly',
    aud: TOKEN_URI,
    iat: now,
    exp: now + 3600
  };

  const signingInput = `${b64url(JSON.stringify(header))}.${b64url(JSON.stringify(payload))}`;
  const key = await importPrivateKey(env.GCP_PRIVATE_KEY);
  const signature = await crypto.subtle.sign({ name: 'RSASSA-PKCS1-v1_5' }, key, new TextEncoder().encode(signingInput));

  return `${signingInput}.${b64urlBuffer(signature)}`;
}

async function importPrivateKey(pem) {
  const pemBody = pem
    .replace(/\\n/g, '\n')
    .replace('-----BEGIN PRIVATE KEY-----', '')
    .replace('-----END PRIVATE KEY-----', '')
    .replace(/\s/g, '');

  const binaryDer = Uint8Array.from(atob(pemBody), c => c.charCodeAt(0));

  return crypto.subtle.importKey('pkcs8', binaryDer, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['sign']);
}

function b64url(str) {
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function b64urlBuffer(buf) {
  let binary = '';
  new Uint8Array(buf).forEach(b => binary += String.fromCharCode(b));
  return b64url(binary);
}

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
  };
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: { 'Content-Type': 'application/json', ...corsHeaders() }
  });
}
