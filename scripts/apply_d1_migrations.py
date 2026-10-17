"""Apply the additive D1 migrations (cloudflare/d1/migrations) to the recorded cloud target.

Every statement is idempotent (CREATE ... IF NOT EXISTS / INSERT OR IGNORE); nothing is
dropped or overwritten. `--dry-run` (default) only reports missing tables. `--apply` writes,
so run it only with explicit approval. Prints no credential or password hash.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_cloud_d1 import cloud_database, schema_statements

EXPECTED_TABLES = ('dataset_versions', 'projects', 'models', 'slider_items', 'site_settings', 'admin_accounts',
                   'events', 'write_guards', 'admin_users', 'admin_invites', 'api_keys')


def table_report(database):
    rows = database.batch([("SELECT name FROM sqlite_master WHERE type='table'", [])])[0]
    present = {row['name'] for row in rows}
    return [name for name in EXPECTED_TABLES if name not in present]


def owner_summary(database):
    try:
        rows = database.batch([("SELECT username, role FROM admin_users WHERE role='owner'", [])])[0]
    except Exception:
        return 'admin_users not readable yet'
    return f"owner: {rows[0]['username']}" if rows else 'owner: (none)'


def main(argv=None, database=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', default=True)
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    database = database or cloud_database()
    missing = table_report(database)
    print('Missing tables:', ', '.join(missing) if missing else 'none')
    if not args.apply:
        print('Dry run only; nothing was written. Re-run with --apply after approval.')
        return missing
    database.batch(schema_statements())
    missing = table_report(database)
    if missing:
        raise SystemExit(f'Migration incomplete; still missing: {", ".join(missing)}')
    print('Applied all migrations;', owner_summary(database))
    return missing


if __name__ == '__main__':
    main()
