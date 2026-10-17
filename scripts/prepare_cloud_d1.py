"""Prepare a separate cloud D1 target without deploying or switching the live site."""
import argparse
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from armodel.repositories.database import Database, MIGRATIONS
from scripts.migrate_to_d1 import import_snapshot


def stored_token():
    """Decrypt only in memory under the Windows user who saved the credential."""
    command = r"""$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Security;
    $p=Join-Path $env:USERPROFILE '.armodel-secrets\cloudflare-d1-token.dpapi';
    $b=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($p),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser);
    [Console]::Out.Write([Text.Encoding]::UTF8.GetString($b))"""
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or not result.stdout.strip().startswith('cfat_'):
        raise RuntimeError('Unable to decrypt the local D1 credential')
    return result.stdout.strip()


def cloud_database():
    """Open the recorded cloud target; IDs come from ~/.armodel-secrets, the token from DPAPI."""
    import tomllib
    target = tomllib.loads((Path.home() / '.armodel-secrets/d1-target.toml').read_text(encoding='utf-8'))
    return Database(account_id=target['account_id'], database_id=target['database_id'], api_token=stored_token())


def schema_initialized(database):
    rows = database.batch([("SELECT name FROM sqlite_master WHERE type='table' AND name='dataset_versions'", [])])[0]
    return bool(rows)


def api(account, token, method='GET', payload=None):
    request = Request(f'https://api.cloudflare.com/client/v4/accounts/{account}/d1/database',
                      method=method, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    with urlopen(request, timeout=30) as response:
        value = json.load(response)
    if not value.get('success'):
        raise RuntimeError('Cloudflare D1 management request failed')
    return value['result']


def schema_statements(paths=None):
    """Split migration files into statements; all are idempotent (IF NOT EXISTS / OR IGNORE)."""
    statements = []
    for path in paths or MIGRATIONS:
        pending = ''
        for line in path.read_text(encoding='utf-8').splitlines(keepends=True):
            if not pending and line.lstrip().startswith('--'):
                continue
            pending += line
            if sqlite3.complete_statement(pending):
                statements.append((pending, []))
                pending = ''
        if pending.strip():
            raise ValueError(f'Incomplete schema statement in {path.name}')
    return statements


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account', required=True)
    parser.add_argument('--name', default='armodel-production')
    parser.add_argument('--create', action='store_true')
    parser.add_argument('--import-snapshot', action='store_true')
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1] / 'data')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-fA-F0-9]{32}', args.account):
        parser.error('Invalid account ID')
    token = stored_token()
    matches = [item for item in api(args.account, token) if item['name'] == args.name]
    created = False
    if not matches:
        if not args.create:
            parser.error('D1 target does not exist; explicit --create required')
        target = api(args.account, token, 'POST', {'name': args.name, 'primary_location_hint': 'apac'})
        created = True
    elif len(matches) == 1:
        target = matches[0]
    else:
        raise RuntimeError('Ambiguous D1 database name')
    database = Database(account_id=args.account, database_id=target['uuid'], api_token=token)
    # The schema is idempotent (IF NOT EXISTS / INSERT OR IGNORE) and never resets data. It also runs
    # for an existing target that has no schema yet, e.g. after creation succeeded but initialization failed.
    if created or not schema_initialized(database):
        database.batch(schema_statements())
    if args.import_snapshot:
        report = import_snapshot(database, args.source)
        print(json.dumps(report, ensure_ascii=True, indent=2))
    folder = Path.home() / '.armodel-secrets'
    metadata = folder / 'd1-target.toml'
    content = f'account_id = "{args.account}"\ndatabase_id = "{target["uuid"]}"\n'
    if metadata.exists() and metadata.read_text(encoding='utf-8') != content:
        raise RuntimeError('A different local D1 target is configured; refusing overwrite')
    metadata.write_text(content, encoding='utf-8')
    print(f'D1 target ready: {target["name"]} ({target["uuid"]}); no deployment performed')


if __name__ == '__main__':
    main()
