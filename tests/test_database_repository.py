import io
import json
from urllib.error import HTTPError
from unittest.mock import Mock

import pytest

from armodel.repositories.database import ConflictError, Database, DatabaseError
from scripts.migrate_to_d1 import import_snapshot


@pytest.fixture
def db(tmp_path):
    return Database(local_path=tmp_path / 'test.sqlite3')


def test_relational_integrity_and_transaction_rollback(db):
    db.save('projects', [{'id': 'p', 'name': 'Project'}])
    with pytest.raises(DatabaseError):
        db.save('models', [{'id': 'valid', 'project_id': 'p'}, {'id': 'bad', 'project_id': 'missing'}])
    assert db.read('models') == ([], 0)
    db.save('models', [{'id': 'm', 'project_id': 'p'}])
    with pytest.raises(DatabaseError):
        db.save('projects', [])
    assert db.read('projects')[0][0]['id'] == 'p'


def test_two_editors_cannot_overwrite_each_other(db):
    db.save('site_settings', {'site_name': 'Before'})
    _, first_revision = db.read('site_settings')
    _, second_revision = db.read('site_settings')
    db.save('site_settings', {'site_name': 'First editor'}, first_revision)
    with pytest.raises(ConflictError):
        db.save('site_settings', {'site_name': 'Stale editor'}, second_revision)
    assert db.read('site_settings')[0]['site_name'] == 'First editor'
    assert db.batch([('SELECT * FROM write_guards', [])])[0] == []


def test_thai_media_fields_and_empty_collection_round_trip(db):
    original = {'id': 'p', 'slug': 'phuphan', 'name': 'ภูพาน', 'description': 'คำอธิบาย',
                'cover_image': 'https://media.example.r2.dev/รูป.png', 'visible': False}
    db.save('projects', [original])
    assert db.read('projects')[0] == [original]
    db.save('projects', [])
    assert db.read('projects')[0] == []


def test_more_than_one_hundred_ids_uses_bounded_parameters(db):
    db.save('projects', [{'id': str(i)} for i in range(140)])
    assert len(db.read('projects')[0]) == 140


def test_gateway_uses_bound_parameters_and_does_not_write_files(tmp_path):
    response = io.BytesIO(json.dumps({'results': [{'success': True, 'results': [{'value': 'ok'}]}]}).encode())
    opener = Mock(return_value=response)
    db = Database(gateway_url='https://gateway.example', token='test-only-token', opener=opener)
    sql = 'SELECT value FROM site_settings WHERE key=?'
    value = "quote'; DELETE FROM models"
    assert db.batch([(sql, [value])]) == [[{'value': 'ok'}]]
    request = opener.call_args.args[0]
    assert json.loads(request.data)['batch'] == [{'sql': sql, 'params': [value]}]
    assert request.get_header('Authorization') == 'Bearer test-only-token'
    assert not list(tmp_path.iterdir())


def test_gateway_failure_and_conflict_never_fall_back_to_sqlite(tmp_path):
    for code, exception in [(409, ConflictError), (503, DatabaseError)]:
        db = Database(gateway_url='https://gateway.example', token='test', local_path=tmp_path / 'unused.sqlite3',
                      opener=Mock(side_effect=HTTPError('https://gateway.example/query', code, 'failure', {}, None)))
        with pytest.raises(exception):
            db.read('models')
    assert not (tmp_path / 'unused.sqlite3').exists()


def test_gateway_rejects_insecure_remote_transport():
    with pytest.raises(DatabaseError):
        Database(gateway_url='http://public.example', token='test')
    with pytest.raises(DatabaseError):
        Database(gateway_url='https://gateway.example')


def test_snapshot_import_preserves_original_and_refuses_second_import(db, tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    datasets = {'projects': [{'id': 'p', 'name': 'ภูพาน'}],
                'models': [{'id': 'm', 'project_id': 'p', 'model_url': 'https://media.example.r2.dev/m.glb'}],
                'slider_items': [], 'site_settings': {'site_name': 'ภูพาน'}}
    for name, value in datasets.items():
        (source / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    before = {path.name: path.read_bytes() for path in source.iterdir()}
    report = import_snapshot(db, source)
    assert report['verified_all_original_fields']
    assert report['counts']['models'] == 1
    assert before == {path.name: path.read_bytes() for path in source.iterdir()}
    with pytest.raises(ValueError, match='not empty'):
        import_snapshot(db, source)


def test_import_batch_rolls_back_projects_when_model_slug_is_duplicate(db, tmp_path):
    for name, value in {
        'projects': [{'id': 'p'}], 'site_settings': {}, 'slider_items': [],
        'models': [{'id': 'a', 'slug': 'same', 'project_id': 'p'}, {'id': 'b', 'slug': 'same', 'project_id': 'p'}],
    }.items():
        (tmp_path / (name + '.json')).write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(DatabaseError):
        import_snapshot(db, tmp_path)
    assert db.read('projects') == ([], 0)
    assert db.read('models') == ([], 0)


def test_linked_collection_batch_rolls_back_when_second_revision_is_stale(db):
    db.save('projects', [{'id': 'p'}])
    db.save('models', [{'id': 'm', 'project_id': 'p'}])
    delete_models, _ = db.save_statements('models', [])
    stale_projects, _ = db.save_statements('projects', [], expected=0)
    with pytest.raises(ConflictError):
        db.batch(delete_models + stale_projects)
    assert db.read('models')[0][0]['id'] == 'm'
    assert db.read('projects')[0][0]['id'] == 'p'


def test_archive_import_is_repeatable_without_modifying_signed_payload(db, tmp_path):
    from scripts.import_d1_events import import_events
    event = {'timestamp_utc': '2026-10-16T00:00:00+00:00', 'signature': 'original-signature', 'summary_th': 'ทดสอบ'}
    path = tmp_path / 'audit.json'
    path.write_text(json.dumps(event), encoding='utf-8')
    import_events(db, path, 'audit')
    import_events(db, path, 'audit')
    assert db.events('audit') == [event]


def test_import_existing_admin_hash_and_reject_overwrite(db):
    from werkzeug.security import check_password_hash, generate_password_hash
    from scripts.import_admin_to_d1 import import_admin
    password_hash = generate_password_hash('test-only-password')
    from armodel.repositories.admin_users import owner
    import_admin(db, 'curator', password_hash)
    account = owner(db)
    assert account['username'] == 'curator' and account['role'] == 'owner'
    assert check_password_hash(account['password_hash'], 'test-only-password')
    with pytest.raises(ValueError, match='มีเจ้าของระบบอยู่แล้ว'):
        import_admin(db, 'other', password_hash)


def test_runtime_upload_without_r2_never_writes_local_files(tmp_path):
    import app as module
    from unittest.mock import patch
    from werkzeug.datastructures import FileStorage
    from werkzeug.exceptions import ServiceUnavailable
    with module.app.test_request_context(), patch.dict(module.app.config, {'TESTING': False}), patch.object(module, 'r2_upload_configured', return_value=False):
        with pytest.raises(ServiceUnavailable):
            module.save_upload(FileStorage(stream=io.BytesIO(b'test'), filename='test.glb'), tmp_path, 'model', {'.glb'})
    assert not list(tmp_path.iterdir())


def test_normal_runtime_requires_d1_and_cannot_create_local_database(tmp_path):
    import app as module
    from unittest.mock import patch
    with patch.dict(module.app.config, {'TESTING': False, 'D1_GATEWAY_URL': '', 'D1_GATEWAY_TOKEN': '', 'D1_LOCAL_PATH': tmp_path / 'blocked.sqlite3'}), patch.dict(module.os.environ, {}, clear=True):
        with pytest.raises(DatabaseError):
            module.get_database()
    assert not (tmp_path / 'blocked.sqlite3').exists()


def test_cloud_d1_api_preserves_parameter_binding():
    response = io.BytesIO(json.dumps({'success': True, 'result': [
        {'success': True, 'results': [{'value': 'ok'}]}]}).encode())
    opener = Mock(return_value=response)
    database = Database(account_id='a' * 32, database_id='11111111-1111-1111-1111-111111111111',
                        api_token='test-only', opener=opener)
    assert database.batch([('SELECT value FROM site_settings WHERE key=?', ['site_name'])]) == [[{'value': 'ok'}]]
    request = opener.call_args.args[0]
    assert request.full_url.startswith('https://api.cloudflare.com/client/v4/accounts/')
    assert request.get_header('Authorization') == 'Bearer test-only'
    assert json.loads(request.data)['batch'][0]['params'] == ['site_name']


def test_cloud_d1_errors_are_sanitized_and_never_fall_back(tmp_path):
    for message, expected in [('STALE_REVISION', ConflictError), ('private details', DatabaseError)]:
        response = io.BytesIO(json.dumps({'success': False, 'errors': [{'message': message}]}).encode())
        database = Database(account_id='a' * 32, database_id='11111111-1111-1111-1111-111111111111',
                            api_token='test-only', local_path=tmp_path / 'unused.sqlite3',
                            opener=Mock(return_value=response))
        with pytest.raises(expected) as error:
            database.batch([('SELECT 1', [])])
        assert 'private details' not in str(error.value)
    assert not list(tmp_path.iterdir())


def test_cloud_d1_rejects_partial_configuration_and_mixed_backends():
    with pytest.raises(DatabaseError):
        Database(account_id='a' * 32)
    with pytest.raises(DatabaseError):
        Database(account_id='a' * 32, database_id='11111111-1111-1111-1111-111111111111',
                 api_token='test', gateway_url='https://gateway.example')


def test_schema_parser_keeps_trigger_whole():
    from scripts.prepare_cloud_d1 import schema_statements
    statements = schema_statements()
    assert any('BEGIN SELECT RAISE' in sql and 'END;' in sql for sql, _ in statements)
    assert all(not params for _, params in statements)


def test_remote_boolean_parameters_are_sqlite_integers():
    opener = Mock(return_value=io.BytesIO(json.dumps({'success': True, 'result': [
        {'success': True, 'results': []}]}).encode()))
    database = Database(account_id='a' * 32, database_id='11111111-1111-1111-1111-111111111111',
                        api_token='test-only', opener=opener)
    database.batch([('SELECT ?,?,?', [True, False, None])])
    params = json.loads(opener.call_args.args[0].data)['batch'][0]['params']
    assert params == [1, 0, None]
    assert type(params[0]) is int


def test_health_identifies_direct_cloud_d1():
    import app as module
    from unittest.mock import patch
    database = Mock(gateway_url='', api_url='https://api.cloudflare.com/query')
    database.batch.return_value = [[{'version': 1}]]
    with patch.object(module, 'get_database', return_value=database):
        response = module.app.test_client().get('/health')
    assert response.status_code == 200
    assert response.json['database'] == 'd1'
