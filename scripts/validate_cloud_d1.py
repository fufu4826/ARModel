"""Verify all migrated fields and Flask pages with JSON file access forbidden."""
import builtins
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_cloud_d1_review import configure
from armodel.repositories.database import ConflictError, DatabaseError
import app as module


def validate():
    root = Path(__file__).resolve().parents[1]
    source = {name: json.loads((root / 'data' / f'{name}.json').read_text(encoding='utf-8'))
              for name in ('projects', 'models', 'site_settings', 'slider_items')}
    configure()
    database = module.get_database()
    for name, original in source.items():
        restored, _ = database.read(name)
        if isinstance(original, dict):
            assert restored == original, f'Field mismatch: {name}'
        else:
            assert len(original) == len(restored), f'Count mismatch: {name}'
            for before, after in zip(original, restored):
                assert all(after.get(key) == value for key, value in before.items()), f'Field mismatch: {name}/{before["id"]}'
        print(f'PASS all original fields: {name} ({len(original)})')
    assert database.batch([('PRAGMA foreign_key_check', [])]) == [[]]
    marker = 'migration-check-' + uuid.uuid4().hex
    try:
        database.batch([
            ('INSERT INTO projects(id,position,details) VALUES (?,?,?)', [marker, 999, '{}']),
            ('INSERT INTO models(id,project_id,position,details) VALUES (?,?,?,?)', [marker, marker + '-missing', 999, '{}']),
        ])
    except DatabaseError:
        pass
    else:
        raise AssertionError('Foreign-key transaction did not fail')
    assert database.batch([('SELECT id FROM projects WHERE id=?', [marker])]) == [[]]
    try:
        database.batch([
            ('INSERT INTO projects(id,position,details) VALUES (?,?,?)', [marker, 999, '{}']),
            ('INSERT INTO write_guards(dataset,expected) VALUES (?,?)', ['projects', -1]),
        ])
    except ConflictError:
        pass
    else:
        raise AssertionError('Stale-write transaction did not fail')
    assert database.batch([('SELECT id FROM projects WHERE id=?', [marker])]) == [[]]
    original_open = builtins.open
    original_path_open = Path.open

    def forbidden(file):
        return isinstance(file, (str, Path)) and Path(file).suffix.lower() in {'.json', '.jsonl'}

    def guarded_open(file, *args, **kwargs):
        if forbidden(file):
            raise AssertionError('Runtime attempted JSON file storage')
        return original_open(file, *args, **kwargs)

    def guarded_path_open(path, *args, **kwargs):
        if forbidden(path):
            raise AssertionError('Runtime attempted JSON file storage')
        return original_path_open(path, *args, **kwargs)

    with patch('builtins.open', guarded_open), patch.object(Path, 'open', guarded_path_open), \
            patch.object(module, 'analytics_tracking_enabled', return_value=False):
        client = module.app.test_client()
        paths = ['/home', '/', '/models', '/admin/login', '/health']
        paths += [f'/models/{source["models"][0]["id"]}', f'/projects/{source["projects"][0]["id"]}']
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200, f'{path}: {response.status_code}'
            print(f'PASS cloud D1 with JSON files blocked: {path}')
    print('PASS D1 cloud: all source fields, foreign keys, atomic rollback, stale-write rejection; no live-site switch')


if __name__ == '__main__':
    validate()
