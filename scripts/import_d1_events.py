"""Import previously exported JSON event archives into D1, without deleting sources."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from armodel.repositories.database import Database


def import_events(db, source, kind):
    paths = sorted(source.rglob('*.json')) if source.is_dir() else [source]
    imported = 0
    for path in paths:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        events = value if isinstance(value, list) else [value]
        for index, event in enumerate(events):
            if not isinstance(event, dict):
                raise ValueError(f'Invalid event in {path.name}')
            material = kind + '/' + str(path.relative_to(source) if source.is_dir() else path.name) + '/' + str(index)
            material += json.dumps(event, sort_keys=True, ensure_ascii=False)
            storage_id = event.get('event_id') or hashlib.sha256(material.encode()).hexdigest()
            # Do not add fields to a signed audit payload; only its SQL row key is new.
            db.append_event(kind, event, storage_id=storage_id)
            imported += 1
    return imported


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--kind', choices=['analytics', 'audit', 'login'], required=True)
    target = parser.add_mutually_exclusive_group()
    target.add_argument('--gateway', default='http://127.0.0.1:8787')
    target.add_argument('--cloud', action='store_true', help='Recorded cloud D1 target (DPAPI token)')
    args = parser.parse_args()
    if args.cloud:
        from scripts.prepare_cloud_d1 import cloud_database
        database = cloud_database()
    elif urlsplit(args.gateway).hostname not in {'127.0.0.1', 'localhost'}:
        parser.error('Only loopback gateways or --cloud are permitted')
    else:
        database = Database(gateway_url=args.gateway)
    # Event IDs are deterministic and inserted with INSERT OR IGNORE, so a rerun never duplicates rows.
    print(f'Processed {import_events(database, args.source, args.kind)} events; source files retained')
