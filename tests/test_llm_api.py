from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class LLMApiIntegrationTests(unittest.TestCase):
    def test_authenticated_users_manage_only_their_own_credentials(self):
        root = Path(__file__).resolve().parents[1]
        script = textwrap.dedent(
            """
            from fastapi.testclient import TestClient
            import security
            from main import app

            with TestClient(app) as client:
                login = client.post(
                    "/api/auth/login",
                    json={
                        "username": "integrationadmin",
                        "password": "Integration-Test-2026!",
                    },
                )
                assert login.status_code == 200, login.text
                csrf = client.cookies.get("csrf_token")
                headers = {"X-CSRF-Token": csrf}

                providers = client.get("/api/llm/providers")
                assert providers.status_code == 200, providers.text
                provider_ids = {item["id"] for item in providers.json()["providers"]}
                assert {"deepseek", "doubao", "qwen", "zhipu", "kimi"} <= provider_ids

                raw_key = "integration-secret-key-0001"
                saved = client.post(
                    "/api/me/llm-credentials",
                    headers=headers,
                    json={
                        "provider": "deepseek",
                        "model": "deepseek-v4-flash",
                        "api_key": raw_key,
                        "set_default": True,
                    },
                )
                assert saved.status_code == 200, saved.text
                assert raw_key not in saved.text
                assert "secret_cipher" not in saved.text

                listed = client.get("/api/me/llm-credentials")
                assert listed.status_code == 200, listed.text
                item = listed.json()["credentials"][0]
                assert item["last4"] == "0001"
                assert item["is_default"] is True
                assert "key" not in item

                status = client.get("/api/apikey")
                assert status.status_code == 200, status.text
                assert status.json()["provider"] == "deepseek"
                assert status.json()["last4"] == "0001"

                security.create_user(
                    "seconduser",
                    "Second-User-Pass-2026!",
                    role="user",
                )

            with TestClient(app) as second:
                login = second.post(
                    "/api/auth/login",
                    json={
                        "username": "seconduser",
                        "password": "Second-User-Pass-2026!",
                    },
                )
                assert login.status_code == 200, login.text
                listed = second.get("/api/me/llm-credentials")
                assert listed.status_code == 200, listed.text
                assert listed.json()["credentials"] == []
                status = second.get("/api/apikey")
                assert status.json()["has_key"] is False
            """
        )
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment.update(
                {
                    "APP_DATA_DIR": directory,
                    "APP_COOKIE_SECURE": "0",
                    "APP_ALLOWED_ORIGINS": "http://testserver",
                    "APP_ADMIN_USERNAME": "integrationadmin",
                    "APP_ADMIN_PASSWORD": "Integration-Test-2026!",
                    "APP_LLM_MASTER_KEY": base64.urlsafe_b64encode(
                        bytes(range(32))
                    ).decode("ascii"),
                }
            )
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=90,
            )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
