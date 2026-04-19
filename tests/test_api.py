from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from promptforge_services.api import app


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["supported_contracts"], ["agent_task_v1"])

    def test_providers_health_endpoint(self) -> None:
        response = self.client.get("/providers/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("providers", body)
        self.assertFalse(body["enabled"])
        self.assertEqual(body["mode"], "deterministic_only")

    def test_prepare_delivery_endpoint(self) -> None:
        response = self.client.post(
            "/prepare-delivery",
            json={
                "contract_name": "agent_task_v1",
                "payload": {
                    "intent": "agent_task",
                    "project_slug": "the-tax-machine",
                    "prompt_type": "coding-cli",
                    "destination": "cli",
                    "target_identifier": "claude-tax-main",
                    "mode": "queue",
                    "requires_review": False,
                    "final_prompt_markdown": "Investigate retry transitions.",
                    "notes": [],
                },
                "priority": "high",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["delivery"]["target_type"], "claude_session")
        self.assertEqual(body["delivery"]["priority"], "high")


if __name__ == "__main__":
    unittest.main()
