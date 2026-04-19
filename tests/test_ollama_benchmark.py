from __future__ import annotations

import unittest
from pathlib import Path

from scripts.bench_ollama_promptforge import (
    assemble_stream_response,
    BenchmarkCase,
    BenchmarkSample,
    build_request_body,
    build_user_prompt,
    load_cases,
    split_text_chunks,
    summarize_case,
    summarize_samples,
)


class OllamaBenchmarkTests(unittest.TestCase):
    def test_load_cases_reads_fixture_file(self) -> None:
        cases = load_cases(Path("tests/fixtures/ollama_benchmark_cases.jsonl"))
        self.assertEqual(len(cases), 4)
        self.assertEqual(cases[0].case_id, "retry_state_patch_plan")
        self.assertGreater(cases[2].context_fill_ratio, 0.0)
        self.assertIn("promptforge-edge", cases[2].context_fill_token)

    def test_build_request_body_is_deterministic_and_contains_filler(self) -> None:
        case = load_cases(Path("tests/fixtures/ollama_benchmark_cases.jsonl"))[2]
        request_body = build_request_body(
            case,
            model="llama3.1",
            num_ctx=64,
            max_tokens=128,
        )

        self.assertEqual(request_body["model"], "llama3.1")
        self.assertEqual(request_body["options"]["temperature"], 0)
        self.assertEqual(request_body["options"]["num_ctx"], 64)
        self.assertEqual(request_body["options"]["num_predict"], 128)
        self.assertFalse(request_body["stream"])
        self.assertEqual(request_body["format"], "json")
        self.assertIn(case.system_prompt, request_body["messages"][0]["content"])

        user_content = request_body["messages"][1]["content"]
        self.assertIn("Schema:", user_content)
        self.assertIn(case.prompt_text, user_content)
        self.assertIn(case.context_fill_token, user_content)

    def test_build_user_prompt_uses_schema_and_context_edge_filler(self) -> None:
        case = load_cases(Path("tests/fixtures/ollama_benchmark_cases.jsonl"))[3]
        prompt = build_user_prompt(case, num_ctx=100)

        self.assertIn("contract_name", prompt)
        self.assertIn(case.prompt_text, prompt)
        self.assertIn("Context stress:", prompt)
        self.assertIn(case.context_fill_token, prompt)

    def test_split_text_chunks_uses_fixed_size_windows_with_overlap(self) -> None:
        chunks = split_text_chunks("abcdefghij", chunk_size=4, overlap=1)

        self.assertEqual(chunks, ["abcd", "defg", "ghij"])

    def test_assemble_stream_response_uses_final_metrics_and_combines_content(self) -> None:
        assembled = assemble_stream_response(
            [
                {"message": {"content": "{\"contract_name\":"}, "done": False},
                {"message": {"content": "\"agent_task_v1\"}"}, "done": True, "total_duration": 42, "prompt_eval_count": 7, "prompt_eval_duration": 11, "eval_count": 5, "eval_duration": 13},
            ]
        )

        self.assertEqual(assembled["message"]["content"], "{\"contract_name\":\"agent_task_v1\"}")
        self.assertEqual(assembled["total_duration"], 42)
        self.assertEqual(assembled["prompt_eval_count"], 7)
        self.assertEqual(assembled["eval_count"], 5)

    def test_summarize_samples_computes_percentiles_and_rates(self) -> None:
        samples = [
            make_sample(case_id="case-a", run_index=index, latency_ms=latency)
            for index, latency in enumerate((10, 20, 30, 40, 50), start=1)
        ]
        summary = summarize_samples(samples)

        self.assertEqual(summary["sample_count"], 5)
        self.assertEqual(summary["success_count"], 5)
        self.assertEqual(summary["latency_ms"]["p50"], 30.0)
        self.assertEqual(summary["latency_ms"]["p95"], 48.0)
        self.assertEqual(summary["aggregate_rates"]["prompt_tokens_per_s"], 100.0)
        self.assertEqual(summary["aggregate_rates"]["generation_tokens_per_s"], 100.0)
        self.assertEqual(summary["aggregate_rates"]["end_to_end_tokens_per_s"], 100.0)

    def test_summarize_case_counts_field_matches(self) -> None:
        case = load_cases(Path("tests/fixtures/ollama_benchmark_cases.jsonl"))[0]
        samples = [
            make_sample(
                case_id=case.case_id,
                run_index=1,
                latency_ms=12,
                expected=case.expected,
            ),
            make_sample(
                case_id=case.case_id,
                run_index=2,
                latency_ms=15,
                expected=case.expected,
            ),
        ]
        summary = summarize_case(case, samples, runs=2)

        self.assertEqual(summary["sample_count"], 2)
        self.assertEqual(summary["field_match_count"], len(case.expected) * 2)
        self.assertEqual(summary["field_match_total"], len(case.expected) * 2)
        self.assertEqual(summary["metrics"]["success_count"], 2)


def make_sample(
    *,
    case_id: str,
    run_index: int,
    latency_ms: int,
    expected: dict[str, object] | None = None,
) -> BenchmarkSample:
    expected = expected or {}
    field_matches = {
        key: {"expected": value, "actual": value, "matched": True}
        for key, value in expected.items()
    }
    return BenchmarkSample(
        case_id=case_id,
        run_index=run_index,
        warmup=False,
        ok=True,
        request_ms=latency_ms,
        http_status=200,
        response_error=None,
        response_json_valid=True,
        content_json_valid=True,
        parse_error=None,
        contract_valid=True,
        contract_error=None,
        contract_quality=1.0 if expected else None,
        field_matches=field_matches,
        prompt_eval_count=100,
        prompt_eval_duration_ns=1_000_000_000,
        eval_count=100,
        eval_duration_ns=1_000_000_000,
        total_duration_ns=2_000_000_000,
        prompt_tokens_per_s=100.0,
        generation_tokens_per_s=100.0,
        end_to_end_tokens_per_s=100.0,
    )


if __name__ == "__main__":
    unittest.main()
