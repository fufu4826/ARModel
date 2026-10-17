"""D1 tables through a private Worker; SQLite is an explicit local test adapter."""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / 'cloudflare/d1/migrations'
SCHEMA = MIGRATIONS_DIR / '0001_initial.sql'
MIGRATIONS = sorted(MIGRATIONS_DIR.glob('[0-9][0-9][0-9][0-9]_*.sql'))
COLLECTIONS = {'models', 'projects', 'slider_items', 'site_settings', 'admin_accounts'}


class DatabaseError(RuntimeError):
    pass


class ConflictError(DatabaseError):
    pass


class Database:
    def __init__(self, *, local_path=None, gateway_url='', token='', opener=urlopen,
                 account_id='', database_id='', api_token=''):
        self.local_path = Path(local_path) if local_path else None
        self.gateway_url = gateway_url.rstrip('/')
        self.token = token
        self.opener = opener
        self.api_url = ''
        self.api_token = api_token
        if any((account_id, database_id, api_token)):
            if self.gateway_url or not (re.fullmatch(r'[a-fA-F0-9]{32}', account_id)
                                       and re.fullmatch(r'[a-fA-F0-9-]{36}', database_id)
                                       and api_token):
                raise DatabaseError('Complete, valid D1 API configuration is required')
            self.api_url = f'https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query'
        elif self.gateway_url:
            parsed = urlsplit(self.gateway_url)
            if parsed.scheme != 'https' and not (
                parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost'}
            ):
                raise DatabaseError('D1 gateway must use HTTPS (except loopback development)')
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise DatabaseError('Invalid D1 gateway URL')
            if parsed.hostname not in {'127.0.0.1', 'localhost'} and not token:
                raise DatabaseError('D1 gateway token is required')
        elif not self.local_path:
            raise DatabaseError('D1 gateway is not configured')

    def batch(self, statements, timeout=20):
        if self.gateway_url or self.api_url:
            payload = json.dumps({'batch': [{'sql': sql, 'params': [
                int(value) if isinstance(value, bool) else value for value in params
            ]} for sql, params in statements]}).encode()
            request = Request(self.api_url or self.gateway_url + '/query', data=payload, method='POST',
                              headers={'Content-Type': 'application/json',
                                       'Authorization': f'Bearer {self.api_token if self.api_url else self.token}'})
            try:
                with self.opener(request, timeout=timeout) as response:
                    value = json.load(response)
                if self.api_url and not value.get('success'):
                    if 'STALE_REVISION' in str(value.get('errors', [])):
                        raise ConflictError('Data changed; reload before saving')
                    raise DatabaseError('D1 query failed')
                results = value['result' if self.api_url else 'results']
                if len(results) != len(statements) or any(not r.get('success') for r in results):
                    raise DatabaseError('D1 query failed')
                return [r.get('results', []) for r in results]
            except HTTPError as exc:
                error_body = exc.read(65536).decode('utf-8', errors='replace') if exc.fp else ''
                if exc.code == 409 or 'STALE_REVISION' in error_body:
                    raise ConflictError('Data changed; reload before saving') from exc
                raise DatabaseError(f'D1 gateway unavailable (HTTP {exc.code})') from exc
            except (URLError, OSError, ValueError, KeyError, TypeError) as exc:
                raise DatabaseError('D1 gateway unavailable') from exc
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.local_path, timeout=20)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            for migration in MIGRATIONS:
                connection.executescript(migration.read_text(encoding='utf-8'))
            connection.execute('BEGIN IMMEDIATE')
            results = []
            for sql, params in statements:
                cursor = connection.execute(sql, params)
                results.append([dict(row) for row in cursor.fetchall()] if cursor.description else [])
            connection.commit()
            return results
        except sqlite3.Error as exc:
            connection.rollback()
            if 'STALE_REVISION' in str(exc):
                raise ConflictError('Data changed; reload before saving') from exc
            raise DatabaseError(str(exc)) from exc
        finally:
            connection.close()

    @staticmethod
    def _select(name):
        if name not in COLLECTIONS:
            raise DatabaseError('Unknown dataset')
        return f'SELECT * FROM {name}' + (' ORDER BY position' if name in {'projects', 'models', 'slider_items'} else '')

    def read(self, name):
        rows, revisions = self.batch([(self._select(name), []),
                                      ('SELECT version FROM dataset_versions WHERE name=?', [name])])
        if not revisions:
            raise DatabaseError('D1 schema is not initialized')
        return self._decode(name, rows), revisions[0]['version']

    def read_many(self, names):
        """Read several collections in one consistent batch (one network round trip)."""
        names = list(dict.fromkeys(names))
        results = self.batch([(self._select(name), []) for name in names] +
                             [('SELECT name,version FROM dataset_versions', [])])
        versions = {row['name']: row['version'] for row in results[-1]}
        if any(name not in versions for name in names):
            raise DatabaseError('D1 schema is not initialized')
        return {name: (self._decode(name, rows), versions[name]) for name, rows in zip(names, results)}

    @staticmethod
    def _decode(name, rows):
        if name == 'site_settings':
            value = {row['key']: row['value'] for row in rows}
        elif name == 'admin_accounts':
            value = {'admin_username': rows[0]['username'], 'admin_password_hash': rows[0]['password_hash']} if rows else {}
        else:
            value = []
            for row in rows:
                item = json.loads(row.pop('details'))
                row.pop('position')
                if 'visible' in row:
                    row['visible'] = bool(row['visible'])
                if 'active' in row:
                    row['active'] = bool(row['active'])
                item.update(row)
                if 'project_id' in item:
                    item['project_id'] = item['project_id'] or ''
                value.append(item)
        return value

    def save(self, name, value, expected=None):
        statements, revision = self.save_statements(name, value, expected)
        self.batch(statements)
        return revision

    def save_statements(self, name, value, expected=None):
        if name not in COLLECTIONS:
            raise DatabaseError('Unknown dataset')
        if expected is None:
            _, expected = self.read(name)
        statements = [('INSERT INTO write_guards(dataset,expected) VALUES (?,?)', [name, expected])]
        if name == 'site_settings':
            statements.append(('DELETE FROM site_settings', []))
            statements += [('INSERT INTO site_settings(key,value) VALUES (?,?)', [key, str(val)]) for key, val in value.items()]
        elif name == 'admin_accounts':
            statements.append(('DELETE FROM admin_accounts', []))
            if value.get('admin_password_hash'):
                statements.append(('INSERT INTO admin_accounts(id,username,password_hash) VALUES (1,?,?)', [value.get('admin_username') or 'admin', value['admin_password_hash']]))
        else:
            ids = [str(item['id']) for item in value]
            if len(set(ids)) != len(ids):
                raise DatabaseError('Duplicate IDs')
            for position, item in enumerate(value):
                columns = ['id', 'title', 'active'] if name == 'slider_items' else ['id', 'slug', 'name', 'description', 'visible']
                if name == 'models':
                    columns.append('project_id')
                fields = [item.get(key, True if key in {'active', 'visible'} else '') for key in columns]
                if name == 'models':
                    fields[-1] = fields[-1] or None
                details = {key: val for key, val in item.items() if key not in columns}
                columns += ['position', 'details']
                fields += [position, json.dumps(details, ensure_ascii=False)]
                updates = ','.join(f'{col}=excluded.{col}' for col in columns if col != 'id')
                statements.append((f"INSERT INTO {name} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) ON CONFLICT(id) DO UPDATE SET {updates}", fields))
            # Upsert first so replacing a collection does not temporarily delete linked rows.
            statements.append((f"DELETE FROM {name} WHERE id NOT IN (SELECT value FROM json_each(?))", [json.dumps(ids)]))
        statements += [('UPDATE dataset_versions SET version=version+1 WHERE name=?', [name]),
                       ('DELETE FROM write_guards WHERE dataset=?', [name])]
        return statements, expected + 1

    def append_event(self, kind, event, storage_id=None, timeout=20):
        timestamp = event.get('timestamp_utc') or event.get('timestamp')
        if not timestamp:
            raise DatabaseError('Event timestamp is required')
        event_id = str(storage_id or event.get('event_id') or uuid.uuid4().hex)
        self.batch([('INSERT OR IGNORE INTO events(id,kind,occurred_at,identity,payload) VALUES (?,?,?,?,?)',
                     [event_id, kind, timestamp, event.get('identity', ''), json.dumps(event, ensure_ascii=False)])],
                   timeout=timeout)

    def events(self, kind, limit=10000, identity=None, since=None):
        sql = 'SELECT payload FROM events WHERE kind=?'
        params = [kind]
        if identity is not None:
            sql += ' AND identity=?'
            params.append(identity)
        if since:
            sql += ' AND occurred_at>=?'
            params.append(since)
        sql += ' ORDER BY occurred_at DESC,id DESC LIMIT ?'
        params.append(limit)
        return [json.loads(row['payload']) for row in self.batch([(sql, params)])[0]]
