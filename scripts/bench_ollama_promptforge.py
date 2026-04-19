from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from promptforge_services.models import AgentTaskV1


DEFAULT_FIXTURES = Path("tests/fixtures/ollama_benchmark_cases.jsonl")
DEFAULT_SYSTEM_PROMPT = (
    "You convert PromptForge intake notes into one valid JSON object. "
    "Return JSON only, with no markdown fences or commentary."
)
DEFAULT_CONTEXT_TOKEN = "context-edge"
DEFAULT_MODEL = "llama3.1"

SCHEMA_HINT = json.dumps(
    {
        "contract_name": "agent_task_v1",
        "intent": "agent_task",
        "project_slug": "string",
        "prompt_type": ["general", "coding-cli", "delegation", "planning", "review"],
        "destination": ["chat", "cli", "obsidian_note", "queue_only"],
        "target_identifier": "string|null",
        "mode": ["draft", "queue", "auto_dispatch"],
        "requires_review": "boolean",
        "final_prompt_markdown": "string",
        "notes": ["string"],
    },
    indent=2,
)


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    prompt_text: str
    expected: dict[str, Any] = field(default_factory=dict)
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    context_fill_ratio: float = 0.0
    context_fill_chars: int | None = None
    context_fill_words: int | None = None
    context_fill_token: str = DEFAULT_CONTEXT_TOKEN
    notes: str = ""


@dataclass(frozen=True)
class BenchmarkSample:
    case_id: str
    run_index: int
    warmup: bool
    ok: bool
    request_ms: int
    http_status: int | None
    response_error: str | None
    response_json_valid: bool
    content_json_valid: bool
    parse_error: str | None
    contract_valid: bool
    contract_error: str | None
    contract_quality: float | None
    field_matches: dict[str, dict[str, Any]]
    prompt_eval_count: int | None
    prompt_eval_duration_ns: int | None
    eval_count: int | None
    eval_duration_ns: int | None
    total_duration_ns: int | None
    prompt_tokens_per_s: float | None
    generation_tokens_per_s: float | None
    end_to_end_tokens_per_s: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "run_index": self.run_index,
            "warmup": self.warmup,
            "ok": self.ok,
            "request_ms": self.request_ms,
            "http_status": self.http_status,
            "response_error": self.response_error,
            "response_json_valid": self.response_json_valid,
            "content_json_valid": self.content_json_valid,
            "parse_error": self.parse_error,
            "contract_valid": self.contract_valid,
            "contract_error": self.contract_error,
            "contract_quality": self.contract_quality,
            "field_matches": self.field_matches,
            "prompt_eval_count": self.prompt_eval_count,
            "prompt_eval_duration_ns": self.prompt_eval_duration_ns,
            "eval_count": self.eval_count,
            "eval_duration_ns": self.eval_duration_ns,
            "total_duration_ns": self.total_duration_ns,
            "prompt_tokens_per_s": self.prompt_tokens_per_s,
            "generation_tokens_per_s": self.generation_tokens_per_s,
            "end_to_end_tokens_per_s": self.end_to_end_tokens_per_s,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark a local Ollama chat endpoint with PromptForge-style prompts."
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:11434",
        help="Ollama base URL, such as http://localhost:11434.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Model name passed to Ollama.",
    )
    parser.add_argument(
        "--fixtures",
        default=str(DEFAULT_FIXTURES),
        help="JSONL benchmark fixture file.",
    )
    parser.add_argument(
        "--warmups",
        type=int,
        default=1,
        help="Warmup runs per case before collecting samples.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Sample runs per case after warmups.",
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=4096,
        help="Ollama context window passed through to options.num_ctx.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=256,
        help="Maximum output tokens passed through to options.num_predict.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="Per-request timeout.",
    )
    parser.add_argument(
        "--output-format",
        choices=("summary", "json"),
        default="summary",
        help="Human-readable summary or machine-readable JSON output.",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Use Ollama stream=true and assemble newline-delimited JSON chunks.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=0,
        help="Split the user prompt into fixed-size character chunks before synthesis.",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=0,
        help="Character overlap between adjacent prompt chunks.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only run the first N benchmark cases.",
    )
    args = parser.parse_args()

    cases = load_cases(Path(args.fixtures))
    if args.limit is not None:
        cases = cases[: args.limit]

    if not cases:
        print("No benchmark cases loaded.", file=sys.stderr)
        return 1
    if args.warmups < 0 or args.runs < 1:
        parser.error("--warmups must be >= 0 and --runs must be >= 1")
    if args.chunk_size < 0 or args.chunk_overlap < 0:
        parser.error("--chunk-size and --chunk-overlap must be >= 0")
    if args.chunk_size and args.chunk_overlap >= args.chunk_size:
        parser.error("--chunk-overlap must be smaller than --chunk-size")

    samples: list[BenchmarkSample] = []
    per_case: dict[str, list[BenchmarkSample]] = {case.case_id: [] for case in cases}

    for case in cases:
        for warmup_index in range(args.warmups):
            sample = run_case_sample(
                case,
                base_url=args.base_url,
                model=args.model,
                num_ctx=args.num_ctx,
                max_tokens=args.max_tokens,
                timeout_seconds=args.timeout_seconds,
                run_index=warmup_index + 1,
                warmup=True,
                stream=args.stream,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
            )
            per_case[case.case_id].append(sample)

        for run_index in range(args.runs):
            sample = run_case_sample(
                case,
                base_url=args.base_url,
                model=args.model,
                num_ctx=args.num_ctx,
                max_tokens=args.max_tokens,
                timeout_seconds=args.timeout_seconds,
                run_index=run_index + 1,
                warmup=False,
                stream=args.stream,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
            )
            per_case[case.case_id].append(sample)
            samples.append(sample)

    report = build_report(
        cases=cases,
        samples=samples,
        per_case=per_case,
        base_url=args.base_url,
        model=args.model,
        num_ctx=args.num_ctx,
        max_tokens=args.max_tokens,
        warmups=args.warmups,
        runs=args.runs,
    )

    if args.output_format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_summary(report)

    return 0


def load_cases(path: Path) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        raw = json.loads(stripped)
        cases.append(
            BenchmarkCase(
                case_id=raw["case_id"],
                prompt_text=raw.get("prompt_text") or raw.get("prompt") or "",
                expected=dict(raw.get("expected", {})),
                system_prompt=raw.get("system_prompt", DEFAULT_SYSTEM_PROMPT),
                context_fill_ratio=float(raw.get("context_fill_ratio", 0.0) or 0.0),
                context_fill_chars=raw.get("context_fill_chars"),
                context_fill_words=raw.get("context_fill_words"),
                context_fill_token=raw.get("context_fill_token", DEFAULT_CONTEXT_TOKEN),
                notes=raw.get("notes", ""),
            )
        )

    return cases


def build_report(
    *,
    cases: list[BenchmarkCase],
    samples: list[BenchmarkSample],
    per_case: dict[str, list[BenchmarkSample]],
    base_url: str,
    model: str,
    num_ctx: int,
    max_tokens: int,
    warmups: int,
    runs: int,
) -> dict[str, Any]:
    case_reports = [
        summarize_case(case, per_case.get(case.case_id, []), runs=runs)
        for case in cases
    ]
    return {
        "benchmark": "ollama_promptforge",
        "base_url": base_url,
        "model": model,
        "num_ctx": num_ctx,
        "max_tokens": max_tokens,
        "warmups": warmups,
        "runs": runs,
        "case_count": len(cases),
        "sample_count": len(samples),
        "cases": case_reports,
        "aggregate": summarize_samples(samples),
    }


def summarize_case(
    case: BenchmarkCase,
    samples_for_case: list[BenchmarkSample],
    *,
    runs: int,
) -> dict[str, Any]:
    sample_results = [sample for sample in samples_for_case if not sample.warmup]
    metrics = summarize_samples(sample_results)
    expected_fields = sorted(case.expected)
    return {
        "case_id": case.case_id,
        "notes": case.notes,
        "expected_fields": expected_fields,
        "expected_field_count": len(expected_fields),
        "sample_count": len(sample_results),
        "warmup_count": sum(1 for sample in samples_for_case if sample.warmup),
        "success_count": sum(1 for sample in sample_results if sample.ok),
        "response_json_valid_count": sum(1 for sample in sample_results if sample.response_json_valid),
        "content_json_valid_count": sum(1 for sample in sample_results if sample.content_json_valid),
        "contract_valid_count": sum(1 for sample in sample_results if sample.contract_valid),
        "field_match_count": sum(
            sum(1 for detail in sample.field_matches.values() if detail["matched"])
            for sample in sample_results
        ),
        "field_match_total": len(expected_fields) * len(sample_results),
        "metrics": metrics,
        "samples": [sample.to_dict() for sample in sample_results],
    }


def summarize_samples(samples: list[BenchmarkSample]) -> dict[str, Any]:
    relevant = [sample for sample in samples if sample.ok]
    latencies = [sample.request_ms for sample in relevant]
    prompt_rates = [sample.prompt_tokens_per_s for sample in relevant if sample.prompt_tokens_per_s is not None]
    generation_rates = [
        sample.generation_tokens_per_s
        for sample in relevant
        if sample.generation_tokens_per_s is not None
    ]
    end_to_end_rates = [
        sample.end_to_end_tokens_per_s
        for sample in relevant
        if sample.end_to_end_tokens_per_s is not None
    ]

    total_prompt_tokens = sum(sample.prompt_eval_count or 0 for sample in relevant)
    total_eval_tokens = sum(sample.eval_count or 0 for sample in relevant)
    total_prompt_duration_ns = sum(sample.prompt_eval_duration_ns or 0 for sample in relevant)
    total_eval_duration_ns = sum(sample.eval_duration_ns or 0 for sample in relevant)
    total_duration_ns = sum(sample.total_duration_ns or 0 for sample in relevant)

    return {
        "sample_count": len(samples),
        "success_count": sum(1 for sample in samples if sample.ok),
        "response_json_valid_count": sum(1 for sample in samples if sample.response_json_valid),
        "content_json_valid_count": sum(1 for sample in samples if sample.content_json_valid),
        "contract_valid_count": sum(1 for sample in samples if sample.contract_valid),
        "latency_ms": summarize_numbers(latencies),
        "prompt_tokens_per_s": summarize_numbers(prompt_rates),
        "generation_tokens_per_s": summarize_numbers(generation_rates),
        "end_to_end_tokens_per_s": summarize_numbers(end_to_end_rates),
        "totals": {
            "prompt_tokens": total_prompt_tokens,
            "generation_tokens": total_eval_tokens,
            "prompt_duration_ns": total_prompt_duration_ns,
            "generation_duration_ns": total_eval_duration_ns,
            "total_duration_ns": total_duration_ns,
        },
        "aggregate_rates": {
            "prompt_tokens_per_s": rate_from_counts(total_prompt_tokens, total_prompt_duration_ns),
            "generation_tokens_per_s": rate_from_counts(total_eval_tokens, total_eval_duration_ns),
            "end_to_end_tokens_per_s": rate_from_counts(
                total_prompt_tokens + total_eval_tokens,
                total_duration_ns,
            ),
        },
    }


def summarize_numbers(values: list[float | int]) -> dict[str, float | int | None]:
    if not values:
        return {"min": None, "p50": None, "p95": None, "max": None, "mean": None}

    ordered = sorted(float(value) for value in values)
    return {
        "min": ordered[0],
        "p50": percentile(ordered, 0.50),
        "p95": percentile(ordered, 0.95),
        "max": ordered[-1],
        "mean": statistics.fmean(ordered),
    }


def percentile(values: list[float], proportion: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    if proportion <= 0:
        return values[0]
    if proportion >= 1:
        return values[-1]
    index = (len(values) - 1) * proportion
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return values[lower]
    lower_value = values[lower]
    upper_value = values[upper]
    return lower_value + (upper_value - lower_value) * (index - lower)


def rate_from_counts(count: int, duration_ns: int) -> float | None:
    if count <= 0 or duration_ns <= 0:
        return None
    return count / (duration_ns / 1_000_000_000)


def build_user_prompt(case: BenchmarkCase, *, num_ctx: int) -> str:
    prompt_parts = [f"Schema:\n{SCHEMA_HINT}", case.prompt_text.strip()]
    filler = build_context_filler(case, num_ctx=num_ctx)
    if filler:
        prompt_parts.append(f"Context stress:\n{filler}")
    return "\n\n".join(part for part in prompt_parts if part.strip())


def build_request_body(
    case: BenchmarkCase,
    *,
    model: str,
    num_ctx: int,
    max_tokens: int,
    stream: bool = False,
    user_prompt: str | None = None,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": case.system_prompt},
            {
                "role": "user",
                "content": user_prompt if user_prompt is not None else build_user_prompt(case, num_ctx=num_ctx),
            },
        ],
        "options": {
            "temperature": 0,
            "num_ctx": num_ctx,
            "num_predict": max_tokens,
        },
        "stream": stream,
        "format": "json",
    }


def build_context_filler(case: BenchmarkCase, *, num_ctx: int) -> str:
    target_words: int | None = None
    if case.context_fill_words is not None:
        target_words = max(0, case.context_fill_words)
    elif case.context_fill_chars is not None:
        target_words = max(0, case.context_fill_chars // max(1, len(case.context_fill_token) + 5))
    elif case.context_fill_ratio > 0:
        target_words = max(0, int(num_ctx * case.context_fill_ratio))

    if not target_words:
        return ""

    words = [f"{case.context_fill_token}-{index:04d}" for index in range(1, target_words + 1)]
    lines = [" ".join(words[index : index + 16]) for index in range(0, len(words), 16)]
    return "\n".join(lines)


def split_text_chunks(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(text_length, start + chunk_size)
        chunks.append(text[start:end])
        if end >= text_length:
            break
        start = max(end - overlap, start + 1)
    return chunks


def build_chunk_user_prompt(
    case: BenchmarkCase,
    *,
    chunk_text: str,
    chunk_index: int,
    chunk_total: int,
) -> str:
    return "\n\n".join(
        part
        for part in (
            f"Chunk {chunk_index} of {chunk_total} from a larger PromptForge request.",
            "Use only this chunk. Return a compact JSON object with any facts that matter for the final synthesis.",
            f"Original task:\n{case.prompt_text.strip()}",
            f"Chunk text:\n{chunk_text.strip()}",
        )
        if part.strip()
    )


def build_synthesis_user_prompt(
    case: BenchmarkCase,
    *,
    chunk_outputs: list[str],
    num_ctx: int,
) -> str:
    prompt_parts = [
        f"Schema:\n{SCHEMA_HINT}",
        "You are given chunk-level model outputs from a PromptForge prompt. Synthesize one final JSON object that conforms to the schema.",
        f"Original task:\n{case.prompt_text.strip()}",
        "Chunk outputs:\n" + "\n\n".join(
            f"Chunk {index}:\n{chunk_output.strip()}" for index, chunk_output in enumerate(chunk_outputs, start=1)
        ),
    ]
    filler = build_context_filler(case, num_ctx=num_ctx)
    if filler:
        prompt_parts.append(f"Context stress:\n{filler}")
    return "\n\n".join(part for part in prompt_parts if part.strip())


def assemble_stream_response(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    if not chunks:
        raise ValueError("stream response was empty")

    final_chunk = chunks[-1]
    for chunk in reversed(chunks):
        if isinstance(chunk, dict) and chunk.get("done") is True:
            final_chunk = chunk
            break

    assembled: dict[str, Any] = dict(final_chunk)
    content_parts: list[str] = []
    for chunk in chunks:
        content_parts.append(extract_message_content(chunk))

    message = assembled.get("message")
    if not isinstance(message, dict):
        message = {}
    else:
        message = dict(message)
    message["content"] = "".join(content_parts)
    assembled["message"] = message
    return assembled


def perform_chat_request(
    *,
    base_url: str,
    request_body: dict[str, Any],
    timeout_seconds: float,
) -> tuple[dict[str, Any] | None, int | None, str | None]:
    http_status: int | None = None
    response_error: str | None = None
    response_json: dict[str, Any] | None = None
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            if request_body.get("stream"):
                with client.stream(
                    "POST",
                    f"{base_url.rstrip('/')}/api/chat",
                    json=request_body,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    http_status = response.status_code
                    response.raise_for_status()
                    streamed_chunks: list[dict[str, Any]] = []
                    for line in response.iter_lines():
                        if not line:
                            continue
                        if isinstance(line, bytes):
                            line = line.decode("utf-8")
                        chunk = json.loads(line)
                        if isinstance(chunk, dict):
                            streamed_chunks.append(chunk)
                    response_json = assemble_stream_response(streamed_chunks)
            else:
                response = client.post(
                    f"{base_url.rstrip('/')}/api/chat",
                    json=request_body,
                    headers={"Content-Type": "application/json"},
                )
                http_status = response.status_code
                response.raise_for_status()
                response_json = response.json()
    except httpx.HTTPError as exc:
        response_error = exc.__class__.__name__
    except ValueError as exc:
        response_error = f"invalid_json:{exc.__class__.__name__}"

    return response_json, http_status, response_error


def extract_usage_metrics(response_json: dict[str, Any]) -> tuple[int | None, int | None, int | None, int | None, int | None]:
    prompt_eval_count = as_int(response_json.get("prompt_eval_count"))
    prompt_eval_duration_ns = as_int(response_json.get("prompt_eval_duration"))
    eval_count = as_int(response_json.get("eval_count"))
    eval_duration_ns = as_int(response_json.get("eval_duration"))
    total_duration_ns = as_int(response_json.get("total_duration"))
    return (
        prompt_eval_count,
        prompt_eval_duration_ns,
        eval_count,
        eval_duration_ns,
        total_duration_ns,
    )


def run_case_sample(
    case: BenchmarkCase,
    *,
    base_url: str,
    model: str,
    num_ctx: int,
    max_tokens: int,
    timeout_seconds: float,
    run_index: int,
    warmup: bool,
    stream: bool = False,
    chunk_size: int = 0,
    chunk_overlap: int = 0,
) -> BenchmarkSample:
    start = time.perf_counter()
    http_status: int | None = None
    response_error: str | None = None
    response_json: dict[str, Any] | None = None
    prompt_eval_count: int | None = None
    prompt_eval_duration_ns: int | None = None
    eval_count: int | None = None
    eval_duration_ns: int | None = None
    total_duration_ns: int | None = None

    if chunk_size > 0:
        base_user_prompt = build_user_prompt(case, num_ctx=num_ctx)
        chunks = split_text_chunks(base_user_prompt, chunk_size=chunk_size, overlap=chunk_overlap)
        if not chunks:
            response_error = "empty_chunk_set"
        else:
            chunk_outputs: list[str] = []
            for chunk_index, chunk_text in enumerate(chunks, start=1):
                request_body = build_request_body(
                    case,
                    model=model,
                    num_ctx=num_ctx,
                    max_tokens=max_tokens,
                    stream=stream,
                    user_prompt=build_chunk_user_prompt(
                        case,
                        chunk_text=chunk_text,
                        chunk_index=chunk_index,
                        chunk_total=len(chunks),
                    ),
                )
                chunk_response, http_status, response_error = perform_chat_request(
                    base_url=base_url,
                    request_body=request_body,
                    timeout_seconds=timeout_seconds,
                )
                if chunk_response is None:
                    break
                if not isinstance(chunk_response, dict):
                    response_error = "invalid_response_type"
                    break
                chunk_outputs.append(extract_message_content(chunk_response))
                (
                    chunk_prompt_eval_count,
                    chunk_prompt_eval_duration_ns,
                    chunk_eval_count,
                    chunk_eval_duration_ns,
                    chunk_total_duration_ns,
                ) = extract_usage_metrics(chunk_response)
                prompt_eval_count = (prompt_eval_count or 0) + (chunk_prompt_eval_count or 0)
                prompt_eval_duration_ns = (prompt_eval_duration_ns or 0) + (chunk_prompt_eval_duration_ns or 0)
                eval_count = (eval_count or 0) + (chunk_eval_count or 0)
                eval_duration_ns = (eval_duration_ns or 0) + (chunk_eval_duration_ns or 0)
                total_duration_ns = (total_duration_ns or 0) + (chunk_total_duration_ns or 0)

            if response_error is None:
                synthesis_request = build_request_body(
                    case,
                    model=model,
                    num_ctx=num_ctx,
                    max_tokens=max_tokens,
                    stream=stream,
                    user_prompt=build_synthesis_user_prompt(
                        case,
                        chunk_outputs=chunk_outputs,
                        num_ctx=num_ctx,
                    ),
                )
                response_json, http_status, response_error = perform_chat_request(
                    base_url=base_url,
                    request_body=synthesis_request,
                    timeout_seconds=timeout_seconds,
                )
                if isinstance(response_json, dict):
                    (
                        synthesis_prompt_eval_count,
                        synthesis_prompt_eval_duration_ns,
                        synthesis_eval_count,
                        synthesis_eval_duration_ns,
                        synthesis_total_duration_ns,
                    ) = extract_usage_metrics(response_json)
                    prompt_eval_count = (prompt_eval_count or 0) + (synthesis_prompt_eval_count or 0)
                    prompt_eval_duration_ns = (prompt_eval_duration_ns or 0) + (synthesis_prompt_eval_duration_ns or 0)
                    eval_count = (eval_count or 0) + (synthesis_eval_count or 0)
                    eval_duration_ns = (eval_duration_ns or 0) + (synthesis_eval_duration_ns or 0)
                    total_duration_ns = (total_duration_ns or 0) + (synthesis_total_duration_ns or 0)
    else:
        request_body = build_request_body(
            case,
            model=model,
            num_ctx=num_ctx,
            max_tokens=max_tokens,
            stream=stream,
        )
        response_json, http_status, response_error = perform_chat_request(
            base_url=base_url,
            request_body=request_body,
            timeout_seconds=timeout_seconds,
        )
        if isinstance(response_json, dict):
            (
                prompt_eval_count,
                prompt_eval_duration_ns,
                eval_count,
                eval_duration_ns,
                total_duration_ns,
            ) = extract_usage_metrics(response_json)

    request_ms = max(0, int((time.perf_counter() - start) * 1000))
    if response_json is None:
        return BenchmarkSample(
            case_id=case.case_id,
            run_index=run_index,
            warmup=warmup,
            ok=False,
            request_ms=request_ms,
            http_status=http_status,
            response_error=response_error,
            response_json_valid=False,
            content_json_valid=False,
            parse_error="request_failed" if response_error else "empty_response",
            contract_valid=False,
            contract_error=None,
            contract_quality=None,
            field_matches={},
            prompt_eval_count=prompt_eval_count,
            prompt_eval_duration_ns=prompt_eval_duration_ns,
            eval_count=eval_count,
            eval_duration_ns=eval_duration_ns,
            total_duration_ns=total_duration_ns,
            prompt_tokens_per_s=None,
            generation_tokens_per_s=None,
            end_to_end_tokens_per_s=None,
        )

    response_json_valid = isinstance(response_json, dict)
    response_dict = response_json if response_json_valid else {}
    content = extract_message_content(response_dict)
    parsed_content, parse_error = parse_json_object(content)
    content_json_valid = parse_error is None and parsed_content is not None

    contract_valid = False
    contract_error: str | None = None
    field_matches: dict[str, dict[str, Any]] = {}
    contract_quality: float | None = None
    if content_json_valid and parsed_content is not None:
        try:
            contract = AgentTaskV1.model_validate(parsed_content)
            contract_valid = True
            actual_payload = contract.model_dump()
            matched_fields = 0
            for field_name, expected_value in case.expected.items():
                actual_value = actual_payload.get(field_name)
                matched = actual_value == expected_value
                field_matches[field_name] = {
                    "expected": expected_value,
                    "actual": actual_value,
                    "matched": matched,
                }
                if matched:
                    matched_fields += 1
            if case.expected:
                contract_quality = matched_fields / len(case.expected)
        except ValidationError as exc:
            contract_error = str(exc)

    prompt_tokens_per_s = rate_from_counts(prompt_eval_count or 0, prompt_eval_duration_ns or 0)
    generation_tokens_per_s = rate_from_counts(eval_count or 0, eval_duration_ns or 0)
    end_to_end_tokens_per_s = rate_from_counts(
        (prompt_eval_count or 0) + (eval_count or 0),
        total_duration_ns or 0,
    )

    return BenchmarkSample(
        case_id=case.case_id,
        run_index=run_index,
        warmup=warmup,
        ok=True,
        request_ms=request_ms,
        http_status=http_status,
        response_error=response_error,
        response_json_valid=response_json_valid,
        content_json_valid=content_json_valid,
        parse_error=parse_error,
        contract_valid=contract_valid,
        contract_error=contract_error,
        contract_quality=contract_quality,
        field_matches=field_matches,
        prompt_eval_count=prompt_eval_count,
        prompt_eval_duration_ns=prompt_eval_duration_ns,
        eval_count=eval_count,
        eval_duration_ns=eval_duration_ns,
        total_duration_ns=total_duration_ns,
        prompt_tokens_per_s=prompt_tokens_per_s,
        generation_tokens_per_s=generation_tokens_per_s,
        end_to_end_tokens_per_s=end_to_end_tokens_per_s,
    )


def extract_message_content(response_json: dict[str, Any]) -> str:
    message = response_json.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )

    content = response_json.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def parse_json_object(raw_output: str) -> tuple[dict[str, Any] | None, str | None]:
    stripped = raw_output.strip()
    if not stripped:
        return None, "json_object_not_found"

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None, "json_object_not_found"

    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error:{exc.msg}"
    if not isinstance(parsed, dict):
        return None, "json_object_not_found"
    return parsed, None


def as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def print_summary(report: dict[str, Any]) -> None:
    print("Ollama PromptForge benchmark")
    print(
        f"base_url={report['base_url']} model={report['model']} "
        f"cases={report['case_count']} samples={report['sample_count']} "
        f"warmups={report['warmups']} runs={report['runs']} num_ctx={report['num_ctx']}"
    )
    print()
    print(
        "aggregate "
        f"success={report['aggregate']['success_count']}/{report['sample_count']} "
        f"json_valid={report['aggregate']['content_json_valid_count']}/{report['sample_count']} "
        f"contract_valid={report['aggregate']['contract_valid_count']}/{report['sample_count']}"
    )
    print(
        "latency_ms "
        f"p50={format_stat(report['aggregate']['latency_ms']['p50'])} "
        f"p95={format_stat(report['aggregate']['latency_ms']['p95'])} "
        f"mean={format_stat(report['aggregate']['latency_ms']['mean'])}"
    )
    print(
        "prompt_tokens_per_s "
        f"rate={format_stat(report['aggregate']['aggregate_rates']['prompt_tokens_per_s'])} "
        f"p50={format_stat(report['aggregate']['prompt_tokens_per_s']['p50'])} "
        f"p95={format_stat(report['aggregate']['prompt_tokens_per_s']['p95'])}"
    )
    print(
        "generation_tokens_per_s "
        f"rate={format_stat(report['aggregate']['aggregate_rates']['generation_tokens_per_s'])} "
        f"p50={format_stat(report['aggregate']['generation_tokens_per_s']['p50'])} "
        f"p95={format_stat(report['aggregate']['generation_tokens_per_s']['p95'])}"
    )
    print(
        "end_to_end_tokens_per_s "
        f"rate={format_stat(report['aggregate']['aggregate_rates']['end_to_end_tokens_per_s'])} "
        f"p50={format_stat(report['aggregate']['end_to_end_tokens_per_s']['p50'])} "
        f"p95={format_stat(report['aggregate']['end_to_end_tokens_per_s']['p95'])}"
    )
    print()

    for case in report["cases"]:
        print(f"[{case['case_id']}]")
        print(
            f"success={case['success_count']}/{case['sample_count']} "
            f"json_valid={case['content_json_valid_count']}/{case['sample_count']} "
            f"contract_valid={case['contract_valid_count']}/{case['sample_count']}"
        )
        print(
            f"latency_ms p50={format_stat(case['metrics']['latency_ms']['p50'])} "
            f"p95={format_stat(case['metrics']['latency_ms']['p95'])} "
            f"mean={format_stat(case['metrics']['latency_ms']['mean'])}"
        )
        print(
            f"prompt_tokens_per_s rate={format_stat(case['metrics']['aggregate_rates']['prompt_tokens_per_s'])} "
            f"generation_tokens_per_s rate={format_stat(case['metrics']['aggregate_rates']['generation_tokens_per_s'])} "
            f"end_to_end_tokens_per_s rate={format_stat(case['metrics']['aggregate_rates']['end_to_end_tokens_per_s'])}"
        )
        if case["expected_field_count"]:
            print(
                f"field_match_rate={case['field_match_count']}/{case['field_match_total']}"
            )
        if case["notes"]:
            print(f"notes={case['notes']}")
        print()


def format_stat(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
