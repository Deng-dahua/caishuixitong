from __future__ import annotations

import base64
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import llm_credentials
import security
from llm_config import get_llm_config, public_llm_status
from request_context import reset_current_user_id, set_current_user_id


class LLMCredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "security.db"
        self.database_patch = patch.object(security, "SECURITY_DB", self.database)
        self.master_patch = patch.dict(
            os.environ,
            {
                "APP_LLM_MASTER_KEY": base64.urlsafe_b64encode(
                    bytes(range(32))
                ).decode("ascii")
            },
        )
        self.database_patch.start()
        self.master_patch.start()
        security.init_security_db()
        llm_credentials.init_llm_credentials_db()
        self.alice_id = security.create_user(
            "alice",
            "Alice-Secure-Pass-2026!",
            role="user",
        )
        self.bob_id = security.create_user(
            "bob",
            "Bob-Secure-Pass-2026!",
            role="user",
        )

    def tearDown(self):
        self.master_patch.stop()
        self.database_patch.stop()
        self.temp.cleanup()

    def test_secret_is_encrypted_and_never_listed(self):
        raw_key = "sk-secret-value-that-must-not-appear"
        created = llm_credentials.create_or_replace_credential(
            self.alice_id,
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key=raw_key,
            set_default=True,
        )
        self.assertEqual(created["last4"], "pear")
        self.assertNotIn(raw_key.encode("utf-8"), self.database.read_bytes())

        listed = llm_credentials.list_credentials(self.alice_id)
        self.assertEqual(len(listed), 1)
        self.assertNotIn("key", listed[0])
        self.assertNotIn("secret_cipher", listed[0])

        decrypted = llm_credentials.get_default_credential(self.alice_id)
        self.assertEqual(decrypted["key"], raw_key)
        self.assertIsNone(llm_credentials.get_default_credential(self.bob_id))
        with self.assertRaises(ValueError):
            llm_credentials.get_credential_secret(self.bob_id, created["id"])

    def test_each_user_has_an_independent_default_provider(self):
        alice_deepseek = llm_credentials.create_or_replace_credential(
            self.alice_id,
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key="alice-deepseek-key-0001",
        )
        alice_kimi = llm_credentials.create_or_replace_credential(
            self.alice_id,
            provider="kimi",
            model="kimi-k3",
            api_key="alice-kimi-key-0002",
        )
        llm_credentials.set_default_credential(self.alice_id, alice_kimi["id"])
        llm_credentials.create_or_replace_credential(
            self.bob_id,
            provider="qwen",
            model="qwen-plus",
            api_key="bob-qwen-key-0003",
        )

        alice_token = set_current_user_id(self.alice_id)
        try:
            alice_config = get_llm_config()
            alice_status = public_llm_status()
        finally:
            reset_current_user_id(alice_token)
        bob_token = set_current_user_id(self.bob_id)
        try:
            bob_config = get_llm_config()
        finally:
            reset_current_user_id(bob_token)

        self.assertEqual(alice_config["provider"], "kimi")
        self.assertEqual(alice_config["key"], "alice-kimi-key-0002")
        self.assertEqual(alice_status["last4"], "0002")
        self.assertEqual(bob_config["provider"], "qwen")
        self.assertEqual(bob_config["key"], "bob-qwen-key-0003")
        self.assertNotEqual(alice_deepseek["id"], alice_kimi["id"])

    def test_rotation_delete_and_audit_do_not_expose_plaintext(self):
        created = llm_credentials.create_or_replace_credential(
            self.alice_id,
            provider="zhipu",
            model="glm-5.2",
            api_key="zhipu-old-secret-0001",
        )
        rotated = llm_credentials.create_or_replace_credential(
            self.alice_id,
            provider="zhipu",
            model="glm-5.2",
            api_key="zhipu-new-secret-0002",
        )
        self.assertEqual(rotated["id"], created["id"])
        self.assertEqual(
            llm_credentials.get_default_credential(self.alice_id)["key"],
            "zhipu-new-secret-0002",
        )

        connection = sqlite3.connect(self.database)
        try:
            audit_blob = "\n".join(
                row[0]
                for row in connection.execute(
                    "SELECT details FROM llm_credential_audit ORDER BY id"
                )
            )
        finally:
            connection.close()
        self.assertNotIn("zhipu-old-secret", audit_blob)
        self.assertNotIn("zhipu-new-secret", audit_blob)

        llm_credentials.delete_credential(self.alice_id, created["id"])
        self.assertEqual(llm_credentials.list_credentials(self.alice_id), [])
        self.assertIsNone(llm_credentials.get_default_credential(self.alice_id))

    def test_provider_endpoint_is_fixed_and_model_identifier_is_validated(self):
        with self.assertRaises(ValueError):
            llm_credentials.create_or_replace_credential(
                self.alice_id,
                provider="custom",
                model="model",
                api_key="some-valid-secret",
            )
        with self.assertRaises(ValueError):
            llm_credentials.create_or_replace_credential(
                self.alice_id,
                provider="doubao",
                model="bad model name",
                api_key="some-valid-secret",
            )


if __name__ == "__main__":
    unittest.main()
