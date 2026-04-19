from __future__ import annotations

import unittest
from pathlib import Path

from scripts.eval_llamacpp_promptforge import (
    build_prompt,
    load_cases,
    load_prompt_template,
    parse_json_object,
)


class LlamaCppEvalTests(unittest.TestCase):
    def test_load_cases_reads_fixture_file(self) -> None:
        cases = load_cases(Path("tests/fixtures/llamacpp_eval_cases.jsonl"))
        self.assertGreaterEqual(len(cases), 4)
        self.assertEqual(cases[0].case_id, "retry_state_patch_plan")

    def test_build_prompt_contains_schema_and_inputs(self) -> None:
        case = load_cases(Path("tests/fixtures/llamacpp_eval_cases.jsonl"))[0]
        prompt = build_prompt(
            case,
            prompt_template=load_prompt_template(prompt_file=None, prompt_profile="compact"),
        )
        self.assertIn("Return JSON only", prompt)
        self.assertIn(case.control_text, prompt)
        self.assertIn(case.transcript_text, prompt)

    def test_load_prompt_template_reads_compact_profile(self) -> None:
        prompt = load_prompt_template(prompt_file=None, prompt_profile="compact")
        self.assertIn("{schema_json}", prompt)
        self.assertIn("{control_text}", prompt)

    def test_parse_json_object_extracts_json_from_wrapped_output(self) -> None:
        parsed, error = parse_json_object(
            'assistant\n{"contract_name":"agent_task_v1","intent":"agent_task"}\n'
        )
        self.assertIsNone(error)
        self.assertEqual(parsed["contract_name"], "agent_task_v1")

    def test_parse_json_object_rejects_missing_json(self) -> None:
        parsed, error = parse_json_object("no json here")
        self.assertIsNone(parsed)
        self.assertEqual(error, "json_object_not_found")


if __name__ == "__main__":
    unittest.main()
