const TABLES = new Set(['projects', 'models', 'slider_items', 'site_settings',
  'admin_accounts', 'admin_users', 'admin_invites', 'dataset_versions', 'write_guards', 'events',
  'json_each']);

async function sameToken(a, b) {
  const encode = new TextEncoder();
  const left = new Uint8Array(await crypto.subtle.digest('SHA-256', encode.encode(a)));
  const right = new Uint8Array(await crypto.subtle.digest('SHA-256', encode.encode(b)));
  let difference = 0;
  for (let i = 0; i < left.length; i++) difference |= left[i] ^ right[i];
  return difference === 0;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const local = env.LOCAL_DEVELOPMENT === 'true' &&
      ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname);
    if (!local && (!env.GATEWAY_TOKEN ||
      !(await sameToken(request.headers.get('authorization') || '', `Bearer ${env.GATEWAY_TOKEN}`)))) {
      return new Response('Unauthorized', {status: 401});
    }
    if (request.method !== 'POST' || url.pathname !== '/query') {
      return new Response('Not found', {status: 404});
    }
    // This server-to-server endpoint deliberately has no browser CORS policy.
    if (request.headers.has('origin')) return new Response('Forbidden', {status: 403});
    const body = await request.text();
    if (body.length > 2_000_000) return new Response('Payload too large', {status: 413});
    let batch;
    try {
      batch = JSON.parse(body).batch;
      if (!Array.isArray(batch) || !batch.length || batch.length > 500) throw new Error();
      for (const statement of batch) {
        if (typeof statement.sql !== 'string' || !Array.isArray(statement.params) ||
          !/^(SELECT|INSERT|UPDATE|DELETE)\s/i.test(statement.sql) ||
          /;|--|\/\*/.test(statement.sql)) throw new Error();
        const names = [...statement.sql.matchAll(/\b(?:FROM|INTO|JOIN)\s+(\w+)/gi)].map(m => m[1]);
        const update = statement.sql.match(/^UPDATE\s+(\w+)/i);
        if (update) names.push(update[1]);
        if (!names.length || names.some(name => !TABLES.has(name))) throw new Error();
      }
    } catch {
      return new Response('Invalid query batch', {status: 400});
    }
    try {
      const statements = batch.map(s => env.DB.prepare(s.sql).bind(...s.params));
      const results = await env.DB.batch(statements);
      return Response.json({results}, {headers: {'Cache-Control': 'no-store'}});
    } catch (error) {
      const stale = String(error).includes('STALE_REVISION');
      return Response.json({error: stale ? 'STALE_REVISION' : 'DATABASE_ERROR'},
        {status: stale ? 409 : 503, headers: {'Cache-Control': 'no-store'}});
    }
  }
};
