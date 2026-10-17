"""Exercise Flask CRUD against Wrangler's LOCAL D1 without uploading real R2 files."""
import io
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as module
from armodel.repositories.database import ConflictError, DatabaseError


def main():
    module.app.config.update(TESTING=True, D1_GATEWAY_URL='http://127.0.0.1:8787')
    db = module.get_database()
    before_models, _ = db.read('models')
    before_projects, _ = db.read('projects')
    marker = 'D1-LOCAL-QA-' + uuid.uuid4().hex
    client = module.app.test_client()
    with client.session_transaction() as session:
        session['admin'] = True
        session['csrf_token'] = marker
    client.environ_base['HTTP_X_CSRF_TOKEN'] = marker
    project_id = None
    try:
        with patch.object(module, 'analytics_tracking_enabled', return_value=False):
            assert client.get('/home').status_code == 200
            response = client.post('/admin/projects', data={'name': marker, 'visible': 'on'})
            assert response.status_code == 302
            project_id = next(row['id'] for row in db.read('projects')[0] if row['name'] == marker)
            with (
                patch.object(module, 'is_vercel_runtime', return_value=True),
                patch.object(module, 'd1_configured', return_value=True),
                patch.object(module, 'r2_upload_configured', return_value=True),
                patch.object(module, 'r2_upload_bytes', side_effect=lambda data, key, *args: 'https://review.example.r2.dev/' + key) as upload,
            ):
                response = client.post('/admin/models', data={
                    'name': marker, 'project_id': project_id, 'visible': 'on',
                    'model_file': (io.BytesIO(b'local-test-only'), 'review.glb'),
                }, content_type='multipart/form-data')
                assert response.status_code == 302
                assert upload.call_count == 1
            model = next(row for row in db.read('models')[0] if row['name'] == marker)
            assert model['model_url'].startswith('https://review.example.r2.dev/models/')
            response = client.post(f'/admin/models/{model["id"]}/edit',
                                   data={'name': marker + '-edited', 'project_id': project_id, 'visible': 'on'})
            assert response.status_code == 302
            assert client.get(f'/models/{model["id"]}').status_code == 200
            assert any(row['name'] == marker + '-edited' for row in db.read('models')[0])
            projects, revision = db.read('projects')
            db.save('projects', projects, revision)
            try:
                db.save('projects', projects, revision)
            except ConflictError:
                pass
            else:
                raise AssertionError('Stale revision accepted')
            try:
                db.batch([
                    ('INSERT INTO projects(id,position,details) VALUES (?,?,?)', [marker, 9999, '{}']),
                    ('INSERT INTO models(id,project_id,position,details) VALUES (?,?,?,?)', [marker, 'missing-' + marker, 9999, '{}']),
                ])
            except DatabaseError:
                pass
            else:
                raise AssertionError('Foreign key violation accepted')
            assert not db.batch([('SELECT id FROM projects WHERE id=?', [marker])])[0]
            assert client.post(f'/admin/projects/{project_id}/delete').status_code == 302
            project_id = None
        assert {row['id'] for row in db.read('models')[0]} == {row['id'] for row in before_models}
        assert {row['id'] for row in db.read('projects')[0]} == {row['id'] for row in before_projects}
        print('PASS local D1: Flask read/create/edit/delete, mocked R2 upload, stale-write rejection, FK rollback, original IDs preserved')
    finally:
        if project_id:
            client.post(f'/admin/projects/{project_id}/delete')


if __name__ == '__main__':
    main()
