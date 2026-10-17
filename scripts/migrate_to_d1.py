"""Import an immutable JSON snapshot into an EMPTY local D1/SQLite database."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from armodel.repositories.database import Database


def import_snapshot(database, source):
    datasets = {}
    fingerprints = {}
    for name in ('projects', 'models', 'site_settings', 'slider_items'):
        path = source / (name + '.json')
        data = path.read_bytes()
        datasets[name] = json.loads(data.decode('utf-8-sig'))
        fingerprints[path.name] = hashlib.sha256(data).hexdigest()
        current, version = database.read(name)
        if current or version:
            raise ValueError('Destination is not empty; refusing to replace existing data')
    for name in ('projects', 'models', 'slider_items'):
        ids = [item['id'] for item in datasets[name]]
        if len(set(ids)) != len(ids):
            raise ValueError(f'Duplicate IDs in {name}')
    project_ids = {item['id'] for item in datasets['projects']}
    if any(item.get('project_id') and item['project_id'] not in project_ids for item in datasets['models']):
        raise ValueError('Invalid model/project relationship')
    statements = []
    for name, value in datasets.items():
        batch, _ = database.save_statements(name, value, expected=0)
        statements.extend(batch)
    # One D1 batch: all records are committed together, or all are rolled back.
    database.batch(statements)
    for name, original in datasets.items():
        restored, _ = database.read(name)
        if isinstance(original, dict):
            if restored != original:
                raise ValueError(f'Post-import verification failed: {name}')
        else:
            if len(restored) != len(original):
                raise ValueError(f'Post-import count mismatch: {name}')
            for before, after in zip(original, restored):
                if any(after.get(key) != value for key, value in before.items()):
                    raise ValueError(f'Post-import field mismatch: {name}/{before["id"]}')
    return {'counts': {name: len(value) for name, value in datasets.items()},
            'source_sha256': fingerprints, 'verified_all_original_fields': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('data'))
    target = parser.add_mutually_exclusive_group()
    target.add_argument('--local-path', type=Path, default=None)
    target.add_argument('--gateway', default='')
    args = parser.parse_args()
    if args.gateway and urlsplit(args.gateway).hostname not in {'127.0.0.1', 'localhost'}:
        parser.error('This review importer permits loopback gateways only; remote import requires a reviewed release procedure')
    database = Database(gateway_url=args.gateway, local_path=None if args.gateway else args.local_path or args.source / 'armodel.sqlite3')
    print(json.dumps(import_snapshot(database, args.source), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
