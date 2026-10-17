"""Compare cloud D1 with the JSON snapshots using SELECT statements only.

Checks every field value and its type, record order, keys added by D1, foreign keys,
and dataset revisions. Prints no credential or password hash. Never writes.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_cloud_d1 import cloud_database

DATASETS = ('projects', 'models', 'site_settings', 'slider_items')
# Columns D1 always materializes; the runtime normalizers already default them this way.
MATERIALIZED_DEFAULTS = {'visible': True, 'active': True}


def read_only(database):
    """Refuse any statement that is not a SELECT or a read-only PRAGMA, then return the database."""
    batch = database.batch

    def guarded(statements):
        for sql, _ in statements:
            head = sql.lstrip().split(None, 1)[0].upper()
            if head not in {'SELECT', 'PRAGMA'} or (head == 'PRAGMA' and '=' in sql):
                raise RuntimeError(f'Refusing non-read statement: {head}')
        return batch(statements)

    database.batch = guarded
    return database


def same(a, b):
    return type(a) is type(b) and a == b


def compare(name, original, restored):
    problems = []
    if isinstance(original, dict):
        for key in original.keys() | restored.keys():
            if not same(original.get(key), restored.get(key)):
                problems.append(f'{name}.{key}')
        return problems
    if [item['id'] for item in original] != [item['id'] for item in restored]:
        problems.append(f'{name}: ID order differs')
    for before, after in zip(original, restored):
        for key, value in before.items():
            if key not in after or not same(after[key], value):
                problems.append(f'{name}/{before["id"]}.{key}')
        for key in after.keys() - before.keys():
            if not (key in MATERIALIZED_DEFAULTS and same(after[key], MATERIALIZED_DEFAULTS[key])):
                problems.append(f'{name}/{before["id"]}: unexpected key {key}')
    return problems


def main():
    root = Path(__file__).resolve().parents[1]
    source = {name: json.loads((root / 'data' / f'{name}.json').read_text(encoding='utf-8')) for name in DATASETS}
    database = read_only(cloud_database())
    restored = database.read_many(DATASETS)
    failures = []
    for name in DATASETS:
        value, revision = restored[name]
        problems = compare(name, source[name], value)
        failures += problems
        size = len(source[name])
        print(f'{"PASS" if not problems else "FAIL"} {name}: {size} source / {len(value)} D1, revision {revision}')
    fk = database.batch([('PRAGMA foreign_key_check', [])])[0]
    print(f'{"PASS" if not fk else "FAIL"} foreign_key_check: {len(fk)} violations')
    project_ids = {item['id'] for item in source['projects']}
    linked = sum(1 for item in restored['models'][0] if item.get('project_id') in project_ids)
    print(f'INFO models linked to an existing project: {linked}/{len(restored["models"][0])}')
    for problem in failures[:50]:
        print('  mismatch:', problem)
    if failures or fk:
        raise SystemExit(1)
    print('PASS every source field and type matches cloud D1 (read-only check)')


if __name__ == '__main__':
    main()
