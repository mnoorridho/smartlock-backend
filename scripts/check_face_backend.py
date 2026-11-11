"""Isolated ASGI + SQLite tests. Never connects to PostgreSQL/MQTT or a real lock."""
import asyncio
import json
import unittest
from datetime import datetime
from pathlib import Path
import importlib.util
from unittest.mock import patch

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app import models, auth
from app.database import Base, get_db
from app.routers import auth_router, devices_router, dashboard_router


class FaceBackendTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.app = FastAPI()
        for router in (auth_router, devices_router, dashboard_router):
            self.app.include_router(router.router)
        def session():
            with self.Session() as db:
                yield db
        self.app.dependency_overrides[get_db] = session
        with self.Session() as db:
            for uid, role in [('owner', models.UserRole.owner), ('member', models.UserRole.user), ('other', models.UserRole.user)]:
                db.add(models.User(id=uid, name=uid, email=uid+'@example.com', password_hash='unused', role=role, is_active=True))
            db.add(models.Device(id='lock', device_code='TEST', name='Test lock', owner_id='owner'))
            db.add(models.AccessLog(id='log', device_id='lock', user_id='member', transaction_id='tx-test', result=models.AccessResult.success, method=models.AccessMethod.face))
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    def request(self, method, path, user=None, payload=None):
        raw = json.dumps(payload).encode() if payload is not None else b''
        headers = [(b'content-type', b'application/json')]
        if user:
            headers.append((b'authorization', ('Bearer '+auth.create_access_token({'sub': user})).encode()))
        scope = {'type': 'http', 'http_version': '1.1', 'method': method, 'scheme': 'http', 'path': path, 'raw_path': path.encode(), 'query_string': b'', 'headers': headers, 'server': ('test', 80), 'client': ('127.0.0.1', 1), 'root_path': ''}
        messages = []
        async def receive():
            return {'type': 'http.request', 'body': raw, 'more_body': False}
        async def send(message):
            messages.append(message)
        asyncio.run(self.app(scope, receive, send))
        status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
        data = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
        return status, json.loads(data) if data and not path.startswith('/dashboard') else data, messages

    def test_owner_enrollment_private_reference_and_revocation(self):
        payload = {'descriptors': [[1.0]+[0.0]*127]*3, 'model_version': 'face-api-1.7.15'}
        self.assertEqual(self.request('GET', '/auth/me/face-profile', 'member')[0], 404)
        self.assertEqual(self.request('GET', '/auth/me/face-profile/status', 'member')[1]['registered'], False)
        self.assertEqual(self.request('PUT', '/auth/users/member/face-profile', 'member', payload)[0], 403)
        self.assertEqual(self.request('PUT', '/auth/users/member/face-profile', 'owner', payload)[0], 200)
        status, profile, messages = self.request('GET', '/auth/me/face-profile', 'member')
        self.assertEqual(status, 200)
        self.assertEqual(profile['descriptors'], payload['descriptors'])
        self.assertEqual(profile['user_id'], 'member')
        self.assertEqual(profile['user_name'], 'member')
        single_photo = {**payload, 'descriptors': payload['descriptors'][:1]}
        self.assertEqual(self.request('PUT', '/auth/users/member/face-profile', 'owner', single_photo)[0], 200)
        self.assertEqual(len(self.request('GET', '/auth/me/face-profile', 'member')[1]['descriptors']), 1)
        status, metadata, status_messages = self.request('GET', '/auth/me/face-profile/status', 'member')
        self.assertEqual(status, 200)
        self.assertTrue(metadata['registered'])
        self.assertNotIn('descriptors', metadata)
        self.assertIn((b'cache-control', b'no-store'), status_messages[0]['headers'])
        self.assertIn((b'cache-control', b'no-store'), messages[0]['headers'])
        self.assertEqual(self.request('GET', '/auth/me/face-profile', 'other')[0], 404)
        self.assertEqual(self.request('GET', '/auth/me/face-profile')[0], 401)
        self.assertEqual(self.request('DELETE', '/auth/users/member/face-profile', 'member')[0], 403)
        self.assertEqual(self.request('DELETE', '/auth/users/member/face-profile', 'owner')[0], 204)
        self.assertEqual(self.request('GET', '/auth/me/face-profile', 'member')[0], 404)

    def test_diagnostics_are_private_bounded_metadata_only(self):
        payload={'client_version':'test-diagnostic','mode':'unlock','stage':'quality','reason':'test marker','face_count':1,'detector_score':.7}
        self.assertEqual(self.request('POST','/auth/me/face-diagnostics','member',payload)[0],204)
        records=self.request('GET','/auth/me/face-diagnostics','member')[1]['records']
        self.assertEqual(records[-1]['reason'],'test marker')
        self.assertLessEqual(len(records),10)
        self.assertEqual(self.request('GET','/auth/me/face-diagnostics','other')[1]['records'],[])
        self.assertEqual(self.request('GET','/auth/me/face-diagnostics')[0],401)
        self.assertEqual(self.request('POST','/auth/me/face-diagnostics','member',{**payload,'image':'data:image/jpeg;base64,abc'})[0],422)
        self.assertEqual(self.request('POST','/auth/me/face-diagnostics','member',{**payload,'descriptor':[1,2]})[0],422)

    def test_bad_descriptors_are_rejected(self):
        for descriptors in [[], [[1.0]*127]*3, [[0.0]*128]*3, [['NaN']*128]*3, [[3.0]*128]*3, [[1.0]+[0.0]*127, [0.0,1.0]+[0.0]*126, [1.0]+[0.0]*127]]:
            self.assertEqual(self.request('PUT', '/auth/users/member/face-profile', 'owner', {'descriptors': descriptors})[0], 422)

    def test_exact_command_ownership(self):
        with self.Session() as db:
            db.add(models.Permission(device_id='lock', user_id='member', granted_by='owner', can_unlock=True)); db.commit()
        self.assertEqual(self.request('GET', '/devices/lock/commands/tx-test', 'member')[1]['result'], 'success')
        self.assertEqual(self.request('GET', '/devices/lock/commands/tx-test', 'owner')[0], 200)
        self.assertEqual(self.request('GET', '/devices/lock/commands/tx-test', 'other')[0], 403)
        self.assertEqual(self.request('GET', '/devices/lock/commands/wrong', 'member')[0], 404)

    def test_quick_requires_explicit_owner_grant_and_normal_unlock_verifies(self):
        with self.Session() as db:
            device = db.get(models.Device, 'lock')
            device.face_verification_enabled = True
            device.nfc_verification_enabled = True
            db.add(models.Permission(device_id='lock', user_id='member', granted_by='owner', can_unlock=True))
            db.commit()
        with patch.object(devices_router.mqtt_bridge, 'publish_unlock_command') as publish:
            self.assertEqual(self.request('POST', '/devices/lock/quick-unlock', 'member')[0], 403)
            self.assertEqual(self.request('POST', '/devices/lock/unlock', 'owner')[0], 400)
            publish.assert_not_called()

    def test_only_allowlisted_assets_are_served(self):
        for filename in ['face-unlock.js', 'face-unlock-core.js', 'face-unlock.css', 'user-portal.js', 'user-portal.css']:
            self.assertEqual(self.request('GET', '/dashboard-assets/'+filename)[0], 200)
        self.assertEqual(self.request('GET', '/dashboard-assets/config.py')[0], 404)

    def test_migration_is_additive(self):
        engine = create_engine('sqlite://')
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE users (id VARCHAR PRIMARY KEY)')
            connection.exec_driver_sql("INSERT INTO users(id) VALUES ('existing')")
            file = Path(__file__).resolve().parents[1] / 'alembic/versions/c4d91e830af2_add_face_profiles.py'
            spec = importlib.util.spec_from_file_location('face_migration', file)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
                self.assertEqual(connection.exec_driver_sql('SELECT id FROM users').scalar(), 'existing')
                module.downgrade()
        engine.dispose()


if __name__ == '__main__':
    unittest.main()
