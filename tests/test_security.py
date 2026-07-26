from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import security


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "security.db"
        self.database_patch = patch.object(security, "SECURITY_DB", self.database)
        self.database_patch.start()
        security.init_security_db()

    def tearDown(self):
        self.database_patch.stop()
        self.temp.cleanup()

    def test_password_hash_and_authentication(self):
        user_id = security.create_user("auditor", "Strong-Passphrase-2026", company_ids=[2, 7])
        self.assertGreater(user_id, 0)
        self.assertIsNone(security.authenticate("auditor", "wrong-password"))
        user = security.authenticate("auditor", "Strong-Passphrase-2026")
        self.assertEqual(user["company_ids"], [2, 7])

    def test_raw_session_token_is_not_persisted(self):
        security.create_user("admin", "Admin-Passphrase-2026!", role="admin")
        user = security.authenticate("admin", "Admin-Passphrase-2026!")
        token, csrf = security.create_session(user, client_fingerprint="test-agent")
        blob = self.database.read_bytes()
        self.assertNotIn(token.encode(), blob)
        self.assertNotIn(csrf.encode(), blob)
        session = security.get_session(token, client_fingerprint="test-agent")
        self.assertTrue(session.is_admin)
        self.assertTrue(security.csrf_is_valid(session, csrf))

    def test_tenant_boundary_and_revocation(self):
        security.create_user("limited", "Limited-Passphrase-2026!", company_ids=[3])
        user = security.authenticate("limited", "Limited-Passphrase-2026!")
        token, _ = security.create_session(user)
        session = security.get_session(token)
        self.assertTrue(session.can_access_company(3))
        self.assertFalse(session.can_access_company(4))
        self.assertFalse(security.select_company(token, 4, session))
        self.assertTrue(security.select_company(token, 3, session))
        security.revoke_session(token)
        self.assertIsNone(security.get_session(token))

    def test_expired_session_is_rejected(self):
        security.create_user("expiry", "Expiry-Passphrase-2026!", company_ids=[1])
        user = security.authenticate("expiry", "Expiry-Passphrase-2026!")
        token, _ = security.create_session(user)
        connection = sqlite3.connect(self.database)
        try:
            connection.execute("UPDATE sessions SET expires_at=?", (int(time.time()) - 1,))
            connection.commit()
        finally:
            connection.close()
        self.assertIsNone(security.get_session(token))

    def test_public_paths_are_exact_and_data_is_protected(self):
        self.assertTrue(security.is_public_path("/api/auth/login"))
        self.assertFalse(security.is_public_path("/api/auth/login/extra"))
        self.assertTrue(security.is_public_path("/static/js/security.js"))
        self.assertFalse(security.is_public_path("/static/rules.json"))
        self.assertTrue(security.is_protected_static_path("/static/rules.json"))


if __name__ == "__main__":
    unittest.main()
