"""UI review server on a throwaway SQLite copy of the JSON snapshot (no cloud, no R2 writes).

Uses the test-only SQLite adapter, so it is for looking at pages, never for real data.
A random local-only admin password is written next to the temporary database.
"""
import argparse
import os
import secrets
import sys
import tempfile
from pathlib import Path

os.environ['ARMODEL_ANALYTICS_ENABLED'] = '0'
for name in ('D1_GATEWAY_URL', 'D1_GATEWAY_TOKEN', 'D1_ACCOUNT_ID', 'D1_DATABASE_ID', 'D1_API_TOKEN', 'VERCEL'):
    os.environ.pop(name, None)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from werkzeug.security import generate_password_hash
from armodel.repositories import admin_users
from armodel.repositories.database import Database
from scripts.migrate_to_d1 import import_snapshot
from app import app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5018)
    args = parser.parse_args()
    workdir = Path(tempfile.mkdtemp(prefix='armodel-snapshot-review-'))
    database_path = workdir / 'review.sqlite3'
    database = Database(local_path=database_path)
    import_snapshot(database, ROOT / 'data')
    password = secrets.token_urlsafe(18)
    admin_users.create_owner(database, 'local-review', generate_password_hash(password))
    (workdir / 'local-review-login.txt').write_text(f'username: local-review\npassword: {password}\n', encoding='utf-8')
    app.config.update(TESTING=True, D1_LOCAL_PATH=database_path, SECRET_KEY=secrets.token_urlsafe(32))
    print(f'Snapshot review database: {database_path}')
    print(f'Local-only admin login saved in: {workdir / "local-review-login.txt"}')
    app.run(host='127.0.0.1', port=args.port, debug=False)


if __name__ == '__main__':
    main()
