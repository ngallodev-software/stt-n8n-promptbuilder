from __future__ import annotations

import unittest

from promptforge_services.models import PreprocessRequest, RenderRequest, ValidateRequest
from promptforge_services.models import PrepareDeliveryRequest
from promptforge_services.pipeline import llm_providers_health
from promptforge_services.pipeline import (
    prepare_delivery_request,
    preprocess_request,
    render_request,
    validate_request,
)


class ServicesPipelineTests(unittest.TestCase):
    def test_preprocess_canonicalizes_seeded_example(self) -> None:
        response = preprocess_request(
            PreprocessRequest(
                frontmatter={
                    "project": "inbox",
                    "destination": "queue_only",
                    "prompt_type": "general",
                    "mode": "queue",
                },
                control_text=(
                    "project is thtaxmachine\n"
                    "prompt type is codingcli\n"
                    "destination is cli\n"
                    "target is claude-tax-main"
                ),
                transcript_text=(
                    "um figure out why the retry state transitions do not line up "
                    "with the review and error policy and prepare a patch plan"
                ),
            )
        )

        self.assertEqual(response.resolved_project, "the-tax-machine")
        self.assertEqual(response.resolved_prompt_type, "coding-cli")
        self.assertEqual(response.resolved_destination, "cli")
        self.assertEqual(response.target_identifier, "claude-tax-main")
        self.assertEqual(
            response.normalized_transcript,
            "Figure out why the retry state transitions do not line up with the review and error policy and prepare a patch plan.",
        )

    def test_validate_routes_cli_without_target_to_review_queue(self) -> None:
        response = validate_request(
            ValidateRequest(
                contract_name="agent_task_v1",
                payload={
                    "intent": "agent_task",
                    "project_slug": "inbox",
                    "prompt_type": "codingcli",
                    "destination": "cli",
                    "target_identifier": "",
                    "mode": "queue",
                    "requires_review": False,
                    "final_prompt_markdown": "Compare the retry states to the review rules.",
                    "notes": [],
                },
            )
        )

        self.assertTrue(response.valid)
        self.assertEqual(response.payload.destination, "queue_only")
        self.assertTrue(response.payload.requires_review)
        self.assertIn("cli_target_missing", response.warnings)

    def test_render_formats_coding_cli_prompt(self) -> None:
        response = render_request(
            RenderRequest(
                contract_name="agent_task_v1",
                payload={
                    "intent": "agent_task",
                    "project_slug": "the-tax-machine",
                    "prompt_type": "coding-cli",
                    "destination": "cli",
                    "target_identifier": "claude-tax-main",
                    "mode": "queue",
                    "requires_review": False,
                    "final_prompt_markdown": "Investigate the retry transitions and produce a patch plan.",
                    "notes": [],
                },
            )
        )

        self.assertEqual(response.template_name, "coding-cli-default")
        self.assertIn("Project: the-tax-machine", response.final_prompt_markdown)
        self.assertIn("Target: claude-tax-main", response.final_prompt_markdown)
        self.assertIn("Task:", response.final_prompt_markdown)

    def test_prepare_delivery_routes_review_queue(self) -> None:
        response = prepare_delivery_request(
            PrepareDeliveryRequest(
                contract_name="agent_task_v1",
                payload={
                    "intent": "agent_task",
                    "project_slug": "inbox",
                    "prompt_type": "coding-cli",
                    "destination": "queue_only",
                    "target_identifier": "",
                    "mode": "queue",
                    "requires_review": True,
                    "final_prompt_markdown": "Compare the retry states to the review rules.",
                    "notes": [],
                },
            )
        )

        self.assertEqual(response.delivery.target_type, "generic_queue")
        self.assertEqual(response.delivery.target_identifier, "manual-review")
        self.assertTrue(response.delivery.requires_review)

    def test_llm_health_helper_defaults_to_disabled(self) -> None:
        response = llm_providers_health()
        self.assertFalse(response.enabled)
        self.assertEqual(response.mode, "deterministic_only")
        self.assertGreaterEqual(len(response.providers), 1)


if __name__ == "__main__":
    unittest.main()
