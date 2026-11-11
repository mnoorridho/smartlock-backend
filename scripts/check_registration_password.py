"""Isolated registration checks; never changes the running server's user accounts."""
import unittest
from fastapi.exceptions import RequestValidationError
import check_face_backend as base
from app.main import registration_validation_error
from app import schemas


class RegistrationPasswordTests(base.FaceBackendTests):
    def setUp(self):
        super().setUp()
        self.app.add_exception_handler(RequestValidationError, registration_validation_error)

    def test_missing_requirements_are_rejected_without_exposing_password(self):
        for password, missing in [('Ab1', '6 karakter'), ('abcde1', 'huruf besar'),
                                  ('ABCDE1', 'huruf kecil'), ('Abcdef', 'angka'),
                                  ('Aa1💡', '6 karakter')]:
            with self.subTest(missing=missing):
                status, body, _ = self.request('POST', '/auth/register', payload={
                    'name': 'Password check', 'email': 'password-check@example.com', 'password': password})
                self.assertEqual(status, 422)
                self.assertIn(missing, body['detail'])
                self.assertNotIn(password, body['detail'])
                self.assertNotIn('input', body)
        with self.Session() as db:
            self.assertEqual(db.query(base.models.User).filter_by(email='password-check@example.com').count(), 0)

    def test_valid_password_registers_and_login_schema_keeps_legacy_compatibility(self):
        status, body, _ = self.request('POST', '/auth/register', payload={
            'name': 'Password check', 'email': 'password-check@example.com', 'password': 'Abcde1'})
        self.assertEqual(status, 201)
        self.assertNotIn('password', body)
        self.assertEqual(schemas.UserLogin(email='legacy@example.com', password='legacy').password, 'legacy')


if __name__ == '__main__':
    unittest.main()
