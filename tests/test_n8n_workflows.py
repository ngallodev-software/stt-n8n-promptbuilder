from __future__ import annotations

import json
import unittest
from pathlib import Path


WORKFLOW_DIR = Path(__file__).resolve().parent.parent / "docs" / "planning" / "n8n_workflows"


class N8nWorkflowTests(unittest.TestCase):
    def test_workflow_json_files_parse_and_have_required_top_level_keys(self) -> None:
        workflow_files = sorted(WORKFLOW_DIR.glob("*.json"))
        self.assertGreaterEqual(len(workflow_files), 3)

        for workflow_file in workflow_files:
            with self.subTest(workflow_file=workflow_file.name):
                payload = json.loads(workflow_file.read_text(encoding="utf-8"))
                self.assertIn("name", payload)
                self.assertIn("nodes", payload)
                self.assertIn("connections", payload)
                self.assertIsInstance(payload["nodes"], list)
                self.assertGreater(len(payload["nodes"]), 0)

    def test_intake_workflow_expects_rich_watcher_payload(self) -> None:
        intake_path = WORKFLOW_DIR / "promptforge_intake_orchestration.json"
        payload = json.loads(intake_path.read_text(encoding="utf-8"))
        normalize_node = next(node for node in payload["nodes"] if node["name"] == "Normalize Payload")
        js_code = normalize_node["parameters"]["jsCode"]
        self.assertIn("final_prompt_markdown", js_code)
        self.assertIn("template_name", js_code)
        self.assertIn("contract_name", js_code)


if __name__ == "__main__":
    unittest.main()
