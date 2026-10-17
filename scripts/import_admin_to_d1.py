"""Set the D1 owner account (admin_users) from an EXISTING password hash.

The hash is never printed. An existing account is replaced only with
--replace-existing <current username>, which must name the account being replaced.
"""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from armodel.repositories import admin_users
from armodel.repositories.database import Database


def import_admin(db, username, password_hash, replace_existing=''):
    """Create the single owner in admin_users, or replace it only when its username is named."""
    try:
        admin_users.create_owner(db, username, password_hash, replace_username=replace_existing)
    except admin_users.AccountError as exc:
        raise ValueError(str(exc)) from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Existing private config containing a password hash; never printed')
    parser.add_argument('--username', help='Administrator username (overrides the source file)')
    parser.add_argument('--replace-existing', default='', metavar='CURRENT_USERNAME',
                        help='Replace the existing account; must match its current username')
    target = parser.add_mutually_exclusive_group()
    target.add_argument('--gateway', default='http://127.0.0.1:8787', help='Loopback review gateway')
    target.add_argument('--cloud', action='store_true',
                        help='Recorded cloud D1 target (~/.armodel-secrets/d1-target.toml + DPAPI token)')
    args = parser.parse_args(argv)
    config = json.loads(args.source.read_text(encoding='utf-8-sig')) if args.source else {}
    username = args.username or config.get('admin_username') or os.environ.get('ADMIN_USERNAME') or ''
    password_hash = config.get('admin_password_hash') or os.environ.get('ADMIN_PASSWORD_HASH') or ''
    if args.cloud:
        from scripts.prepare_cloud_d1 import cloud_database
        database = cloud_database()
    else:
        if urlsplit(args.gateway).hostname not in {'127.0.0.1', 'localhost'}:
            parser.error('Only loopback gateways or --cloud are permitted')
        database = Database(gateway_url=args.gateway)
    import_admin(database, username, password_hash, args.replace_existing)
    action = f'Replaced administrator {args.replace_existing} with' if args.replace_existing else 'Imported'
    print(f'{action} {username} (hash not shown); source configuration unchanged')


if __name__ == '__main__':
    main()
