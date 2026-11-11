"""Role/method matrix tests with SQLite, ASGI requests, and mocked publishing only."""
import unittest
from unittest.mock import patch
import importlib.util
from pathlib import Path
from sqlalchemy import create_engine, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
import check_face_backend as base
from app import models, schemas
from app.routers import permissions_router, nfc_router, devices_router, hardware_router


class UserRoleTests(base.FaceBackendTests):
    def setUp(self):
        super().setUp()
        self.app.include_router(permissions_router.router)
        self.app.include_router(nfc_router.router)
        with self.Session() as db:
            device = db.get(models.Device, 'lock')
            device.face_verification_enabled = True; device.nfc_verification_enabled = True
            device.latitude = -7.05; device.longitude = 110.4; device.geofence_radius_m = 100
            device.access_window_enabled = False
            db.add(models.Device(id='foreign', name='Hidden', device_code='HIDDEN', owner_id='other'))
            db.add(models.Permission(id='grant', device_id='lock', user_id='member', granted_by='owner', can_unlock=True))
            db.add(models.NfcCard(id='other-card', device_id='lock', user_id='other', created_by='owner', card_uid='AA:FF', label='Private card'))
            db.add(models.AccessLog(device_id='lock', user_id='other', method=models.AccessMethod.nfc, result=models.AccessResult.success, note='Private history'))
            db.commit()

    def test_devices_and_logs_are_scoped(self):
        status, devices, _ = self.request('GET', '/devices/', 'member')
        self.assertEqual(status, 200)
        self.assertEqual([d['id'] for d in devices], ['lock'])
        self.assertEqual(devices[0]['owner_name'], 'owner')
        self.assertTrue(devices[0]['can_use_face']); self.assertTrue(devices[0]['can_use_nfc']); self.assertFalse(devices[0]['can_use_quick'])
        for user in ['member', 'owner']:
            self.assertEqual(self.request('GET', '/devices/foreign', user)[0], 403)
            self.assertEqual(self.request('GET', '/devices/foreign/logs', user)[0], 403)
        history = self.request('GET', '/devices/lock/logs', 'member')[1]
        self.assertEqual({log['user_id'] for log in history}, {'member'})
        self.assertEqual(len(self.request('GET', '/devices/lock/logs', 'owner')[1]), 2)

    def test_self_enrollment_and_card_registration_cannot_manage_others(self):
        descriptor = {'descriptors': [[1.0]+[0.0]*127]*3, 'user_id': 'other'}
        status, result, _ = self.request('PUT', '/auth/me/face-profile', 'member', descriptor)
        self.assertEqual(status, 200); self.assertEqual(result['user_id'], 'member')
        self.assertEqual(self.request('GET', '/auth/me/face-profile', 'other')[0], 404)
        self.assertEqual(self.request('PUT', '/auth/users/other/face-profile', 'member', descriptor)[0], 403)
        payload = {'device_id': 'lock', 'card_uid': 'AA:01', 'label': 'My card'}
        status, card, _ = self.request('POST', '/nfc-cards/', 'member', payload)
        self.assertEqual(status, 201); self.assertEqual(card['user_id'], 'member')
        self.assertEqual(self.request('GET', '/nfc-cards/', 'member')[1][0]['id'], card['id'])
        self.assertEqual(len(self.request('GET', '/nfc-cards/', 'member')[1]), 1)
        self.assertEqual(self.request('POST', '/nfc-cards/', 'member', {**payload, 'card_uid':'AA:02','user_email':'other@example.com'})[0], 403)
        self.assertEqual(self.request('POST', '/nfc-cards/', 'member', {**payload, 'device_id':'foreign'})[0], 403)
        self.assertEqual(self.request('PATCH', '/nfc-cards/'+card['id'], 'member', {'is_active':False})[0], 403)
        self.assertEqual(self.request('DELETE', '/nfc-cards/'+card['id'], 'member')[0], 403)

    def test_geofence_before_face_and_final_check(self):
        inside = {'latitude':-7.05,'longitude':110.4,'accuracy_m':5}
        outside = {**inside, 'latitude':-8.0}
        self.assertEqual(self.request('POST', '/devices/lock/face-precheck', 'member', inside)[0], 200)
        self.assertEqual(self.request('POST', '/devices/lock/face-precheck', 'member', outside)[0], 403)
        self.assertEqual(self.request('POST', '/devices/lock/face-precheck', 'member', {**inside,'accuracy_m':500})[0], 400)
        with patch.object(devices_router.mqtt_bridge, 'publish_unlock_command', return_value=True) as publish:
            self.assertEqual(self.request('POST', '/devices/lock/unlock', 'member', {**outside,'face_verified':True})[0], 403)
            publish.assert_not_called()
            self.assertEqual(self.request('POST', '/devices/lock/unlock', 'member', {**inside,'face_verified':True})[0], 200)

    def test_owner_controls_methods_and_direct_calls_cannot_bypass(self):
        with patch.object(devices_router.mqtt_bridge, 'publish_unlock_command', return_value=True) as publish:
            self.assertEqual(self.request('POST', '/devices/lock/quick-unlock', 'member')[0], 403)
            self.assertEqual(self.request('PATCH', '/permissions/grant', 'member', {'allow_quick':True})[0], 403)
            self.assertEqual(self.request('PATCH', '/permissions/grant', 'owner', {'allow_face':False,'allow_nfc':False})[0], 200)
            face = {'latitude':-7.05,'longitude':110.4,'accuracy_m':5,'face_verified':True}
            self.assertEqual(self.request('POST', '/devices/lock/face-precheck', 'member', face)[0], 403)
            self.assertEqual(self.request('PUT', '/auth/me/face-profile', 'member', {'descriptors':[[1.0]+[0.0]*127]*3})[0], 403)
            self.assertEqual(self.request('POST', '/devices/lock/unlock', 'member', face)[0], 403)
            self.assertEqual(self.request('POST', '/devices/lock/unlock', 'member', {'nfc_card_uid':'AA:FF'})[0], 403)
            self.assertEqual(self.request('POST', '/nfc-cards/', 'member', {'device_id':'lock','card_uid':'AA:03','label':'Not allowed'})[0], 403)
            publish.assert_not_called()
            self.request('PATCH', '/permissions/grant', 'owner', {'allow_nfc':True})
            self.assertEqual(self.request('POST', '/devices/lock/unlock', 'member', {**face,'nfc_card_uid':'INVALID'})[0], 403, 'An invalid NFC claim cannot bypass a denied face method')
            publish.assert_not_called()
            self.request('PATCH', '/permissions/grant', 'owner', {'allow_quick':True})
            self.assertEqual(self.request('POST', '/devices/lock/quick-unlock', 'member')[0], 200)
            self.assertEqual(publish.call_count, 1)
            self.request('PATCH', '/permissions/grant', 'owner', {'can_unlock':False})
            self.assertEqual(self.request('GET', '/devices/', 'member')[1], [])
            self.assertEqual(self.request('GET', '/devices/lock', 'member')[0], 403)

    def test_user_cannot_manage_owner_features(self):
        for method, path, body in [('POST','/devices/',{'device_code':'NEW','name':'Not allowed'}),('PATCH','/devices/lock/location',{'latitude':0,'longitude':0,'geofence_radius_m':100}),('DELETE','/devices/lock',None),('POST','/permissions/',{'device_id':'lock','user_email':'other@example.com'}),('DELETE','/permissions/grant',None)]:
            self.assertEqual(self.request(method,path,'member',body)[0],403)

    def test_hardware_obeys_method_revocation(self):
        with self.Session() as db:
            grant=db.get(models.Permission,'grant'); grant.allow_face=False; grant.allow_nfc=False
            db.add(models.NfcCard(device_id='lock',user_id='member',created_by='owner',card_uid='BB:01',label='User card'));db.commit()
            device=db.get(models.Device,'lock')
            face=hardware_router.face_verify(schemas.HardwareFaceVerifyIn(user_id='member',face_verified=True,latitude=-7.05,longitude=110.4,accuracy_m=5),device,db)
            self.assertFalse(face['unlock'])
            nfc=hardware_router.nfc_verify(schemas.HardwareNfcVerifyIn(card_uid='BB:01'),device,db)
            self.assertFalse(nfc['unlock'])

    def test_method_migration_preserves_existing_permissions(self):
        engine=create_engine('sqlite://')
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE permissions (id VARCHAR PRIMARY KEY)')
            connection.exec_driver_sql("INSERT INTO permissions (id) VALUES ('existing')")
            file=Path(__file__).resolve().parents[1]/'alembic/versions/e18b6a2d0419_add_method_permissions.py'
            spec=importlib.util.spec_from_file_location('method_migration',file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
                self.assertEqual(connection.exec_driver_sql('SELECT allow_face, allow_nfc, allow_quick FROM permissions').one(),(1,1,0))
                module.downgrade()
            self.assertEqual([c['name'] for c in inspect(connection).get_columns('permissions')],['id'])
        engine.dispose()

    def test_hardware_owner_cannot_open_another_owners_device(self):
        with self.Session() as db:
            device=db.get(models.Device,'foreign'); device.face_verification_enabled=True; device.nfc_verification_enabled=True
            db.add(models.NfcCard(device_id='foreign',user_id='owner',created_by='other',card_uid='CC:01',label='Foreign owner card')); db.commit()
            face=hardware_router.face_verify(schemas.HardwareFaceVerifyIn(user_id='owner',face_verified=True),device,db)
            nfc=hardware_router.nfc_verify(schemas.HardwareNfcVerifyIn(card_uid='CC:01'),device,db)
            self.assertFalse(face['unlock']);self.assertFalse(nfc['unlock'])


if __name__ == '__main__':
    unittest.main()
