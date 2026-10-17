"""Create a Werkzeug password hash from a password typed in the terminal (not echoed).

Writes {"admin_username", "admin_password_hash"} to a private file outside the repository
(default ~/.armodel-secrets/admin-account.json). Neither the password nor the hash is printed.
Then import it with: python scripts/import_admin_to_d1.py --cloud --source <that file>
"""
import argparse
import getpass
import json
import re
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None, prompt=getpass.getpass):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', required=True)
    parser.add_argument('--out', type=Path, default=Path.home() / '.armodel-secrets' / 'admin-account.json')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}', args.username):
        parser.error('Username must be 3-64 letters, digits, ".", "_" or "-"')
    out = args.out.resolve()
    if ROOT.resolve() in out.parents:
        parser.error('Refusing to write credentials inside the repository')
    password = prompt('New admin password (not shown): ')
    if len(password) < 12:
        parser.error('Use at least 12 characters')
    if prompt('Repeat password: ') != password:
        parser.error('Passwords do not match')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'admin_username': args.username,
                               'admin_password_hash': generate_password_hash(password)}), encoding='utf-8')
    print(f'Saved username and password hash to {out} (nothing secret printed)')


if __name__ == '__main__':
    sys.exit(main())
