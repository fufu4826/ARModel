"""Export D1 back to JSON files for rollback or backup, using SELECT statements only.

Writes projects/models/site_settings/slider_items in the legacy JSON layout, events per kind,
and a manifest with row counts, dataset revisions, and SHA-256 fingerprints. The admin
password hash is never exported. The output folder must be new or empty and outside data/.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from armodel.repositories.database import Database

DATASETS = ('projects', 'models', 'site_settings', 'slider_items')
EVENT_KINDS = ('analytics', 'audit', 'login')


def read_only(database):
    batch = database.batch

    def guarded(statements, *args, **kwargs):
        for sql, _ in statements:
            if sql.lstrip().split(None, 1)[0].upper() != 'SELECT':
                raise RuntimeError('Export refuses non-SELECT statements')
        return batch(statements, *args, **kwargs)

    database.batch = guarded
    return database


def dump(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def export(database, out):
    database = read_only(database)
    files = {}
    for name, (value, revision) in database.read_many(DATASETS).items():
        files[f'{name}.json'] = (dump(value), len(value), revision)
    for kind in EVENT_KINDS:
        rows = database.batch([('SELECT payload FROM events WHERE kind=? ORDER BY occurred_at,id', [kind])])[0]
        events = [json.loads(row['payload']) for row in rows]
        files[f'events/{kind}.json'] = (dump(events), len(events), None)
    manifest = {'exported_at_utc': datetime.now(timezone.utc).isoformat(), 'files': {}}
    for relative, (data, count, revision) in files.items():
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        manifest['files'][relative] = {'rows': count, 'revision': revision,
                                       'sha256': hashlib.sha256(data).hexdigest()}
    (out / 'manifest.json').write_bytes(dump(manifest))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='New or empty folder outside the repository data/')
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--cloud', action='store_true', help='Recorded cloud D1 target (DPAPI token)')
    target.add_argument('--local-path', type=Path, help='SQLite review/test database')
    args = parser.parse_args(argv)
    out = args.out.resolve()
    if out == (ROOT / 'data').resolve() or (ROOT / 'data').resolve() in out.parents:
        parser.error('Refusing to write into data/: the original snapshots must stay untouched')
    if out.exists() and any(out.iterdir()):
        parser.error('Output folder must be new or empty')
    if args.cloud:
        from scripts.prepare_cloud_d1 import cloud_database
        database = cloud_database()
    else:
        database = Database(local_path=args.local_path)
    manifest = export(database, out)
    for relative, info in manifest['files'].items():
        print(f"{relative}: {info['rows']} rows, sha256 {info['sha256'][:12]}")
    print(f'Exported to {out}; no data was changed')


if __name__ == '__main__':
    main()
