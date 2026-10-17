import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from './worker.mjs';

test('remote requests require credentials and never reach D1', async () => {
  const response = await worker.fetch(new Request('https://gateway.test/query', {method: 'POST', body: '{}'}), {});
  assert.equal(response.status, 401);
});

test('local development bypass is restricted to loopback', async () => {
  const response = await worker.fetch(new Request('https://gateway.test/query', {method: 'POST', body: '{}'}), {LOCAL_DEVELOPMENT: 'true'});
  assert.equal(response.status, 401);
});

test('rejects browser origins and unauthorized tables', async () => {
  const env = {GATEWAY_TOKEN: 'test-only'};
  const headers = {Authorization: 'Bearer test-only', Origin: 'https://browser.test'};
  let response = await worker.fetch(new Request('https://gateway.test/query', {method: 'POST', headers, body: '{}'}), env);
  assert.equal(response.status, 403);
  delete headers.Origin;
  response = await worker.fetch(new Request('https://gateway.test/query', {method: 'POST', headers,
    body: JSON.stringify({batch: [{sql: 'SELECT * FROM sqlite_schema', params: []}]})}), env);
  assert.equal(response.status, 400);
});

test('prepared statements preserve hostile parameter values and support upsert', async () => {
  let bound;
  const env = {GATEWAY_TOKEN: 'test-only', DB: {
    prepare(sql) {return {bind(...params) {bound = {sql, params}; return bound;}};},
    async batch(statements) {assert.equal(statements.length, 1); return [{success: true, results: []}];}
  }};
  const sql = 'INSERT INTO site_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value';
  const params = ['site_name', "Thai'; DROP TABLE models"];
  const response = await worker.fetch(new Request('https://gateway.test/query', {method: 'POST',
    headers: {Authorization: 'Bearer test-only'}, body: JSON.stringify({batch: [{sql, params}]})}), env);
  assert.equal(response.status, 200);
  assert.deepEqual(bound, {sql, params});
});

test('returns a conflict without disclosing database errors', async () => {
  const env = {LOCAL_DEVELOPMENT: 'true', DB: {
    prepare() {return {bind() {return {};}};},
    async batch() {throw new Error('D1_ERROR: STALE_REVISION sensitive detail');}
  }};
  const response = await worker.fetch(new Request('http://127.0.0.1/query', {method: 'POST',
    body: JSON.stringify({batch: [{sql: 'SELECT * FROM models', params: []}]})}), env);
  assert.equal(response.status, 409);
  assert.deepEqual(await response.json(), {error: 'STALE_REVISION'});
});

test('allows the admin user tables, including joined invite listings', async () => {
  const seen = [];
  const env = {GATEWAY_TOKEN: 'test-only', DB: {
    prepare(sql) {return {bind() {seen.push(sql); return {};}};},
    async batch(statements) {return statements.map(() => ({success: true, results: []}));}
  }};
  const batch = [
    {sql: 'SELECT id FROM admin_users WHERE username=? COLLATE NOCASE', params: ['owner']},
    {sql: 'SELECT i.kind FROM admin_invites i LEFT JOIN admin_users u ON u.id=i.user_id WHERE i.expires_at>?', params: ['x']},
  ];
  const response = await worker.fetch(new Request('https://gateway.test/query', {method: 'POST',
    headers: {Authorization: 'Bearer test-only'}, body: JSON.stringify({batch})}), env);
  assert.equal(response.status, 200);
  assert.equal(seen.length, 2);
});
