from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from promptforge_services.models import ValidateRequest
from promptforge_services.pipeline import validate_request


DEFAULT_FIXTURES = Path("tests/fixtures/llamacpp_eval_cases.jsonl")
DEFAULT_PROMPT_DIR = Path("tests/fixtures/llamacpp_prompts")


@dataclass
class EvalCase:
    case_id: str
    control_text: str
    transcript_text: str
    expected: dict[str, Any]
    notes: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run local llama.cpp model against PromptForge structured-output fixtures."
    )
    parser.add_argument(
        "--backend",
        choices=("llama.cpp", "codex-exec", "openai-api"),
        default="llama.cpp",
        help="Inference backend. Codex backend defaults to local `codex exec`, not API.",
    )
    model_group = parser.add_mutually_exclusive_group(required=False)
    model_group.add_argument("--model", help="Path to GGUF model.")
    model_group.add_argument(
        "--hf",
        help="Hugging Face model reference passed to llama.cpp with `-hf`.",
    )
    parser.add_argument(
        "--llama-binary",
        default="llama-cli",
        help="llama.cpp binary. Example: llama-cli or /path/to/main",
    )
    parser.add_argument(
        "--codex-binary",
        default="codex",
        help="Codex CLI binary for `codex exec` backend.",
    )
    parser.add_argument(
        "--codex-model",
        default="gpt-5.4-mini",
        help="Model for `codex exec`. Defaults to gpt-5.4-mini instead of inheriting global Codex config.",
    )
    parser.add_argument(
        "--codex-reasoning-effort",
        choices=("low", "medium", "high"),
        default="low",
        help="Reasoning effort for `codex exec`.",
    )
    parser.add_argument(
        "--fixtures",
        default=str(DEFAULT_FIXTURES),
        help="JSONL fixture file.",
    )
    parser.add_argument(
        "--prompt-profile",
        choices=("compact", "full"),
        default="compact",
        help="Prompt template profile tuned outside llama.cpp.",
    )
    parser.add_argument(
        "--prompt-file",
        default=None,
        help="Optional custom prompt template file. Overrides --prompt-profile.",
    )
    parser.add_argument("--temp", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--repeat-penalty", type=float, default=1.05)
    parser.add_argument("--ctx-size", type=int, default=4096)
    parser.add_argument("--max-tokens", type=int, default=400)
    parser.add_argument(
        "--threads",
        type=int,
        default=max(1, (os.cpu_count() or 1) // 2),
        help="CPU threads for generation.",
    )
    parser.add_argument(
        "--threads-batch",
        type=int,
        default=max(1, (os.cpu_count() or 1) // 2),
        help="CPU threads for prompt processing batch.",
    )
    parser.add_argument(
        "--cpu-range",
        default=None,
        help="Optional llama.cpp CPU affinity range like 0-15.",
    )
    parser.add_argument(
        "--ngl",
        type=int,
        default=0,
        help="GPU layers. Use 999 to offload all supported layers.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only run first N cases.",
    )
    args = parser.parse_args()

    if args.backend == "llama.cpp" and not (args.model or args.hf):
        parser.error("--backend llama.cpp requires --model or --hf")
    if args.backend != "llama.cpp" and (args.model or args.hf):
        parser.error("--model/--hf only valid with --backend llama.cpp")
    if args.backend == "openai-api":
        parser.error("openai-api backend not implemented yet. Use codex-exec.")

    cases = load_cases(Path(args.fixtures))
    if args.limit is not None:
        cases = cases[: args.limit]

    if not cases:
        print("No eval cases loaded.", file=sys.stderr)
        return 1

    totals = {
        "cases": len(cases),
        "json_valid": 0,
        "validator_pass": 0,
        "project_slug": 0,
        "prompt_type": 0,
        "destination": 0,
        "target_identifier": 0,
        "mode": 0,
        "requires_review": 0,
    }

    results: list[dict[str, Any]] = []
    for case in cases:
        prompt = build_prompt(
            case,
            prompt_template=load_prompt_template(
                prompt_file=Path(args.prompt_file) if args.prompt_file else None,
                prompt_profile=args.prompt_profile,
            ),
        )
        raw_output = run_model(prompt, args)
        parsed, parse_error = parse_json_object(raw_output)

        result: dict[str, Any] = {
            "case_id": case.case_id,
            "raw_output": raw_output.strip(),
            "json_valid": parse_error is None,
            "parse_error": parse_error,
            "validator_pass": False,
            "validator_error": None,
            "field_matches": {},
        }

        if parse_error is None and parsed is not None:
            totals["json_valid"] += 1
            try:
                validated = validate_request(
                    ValidateRequest(contract_name="agent_task_v1", payload=parsed)
                )
                result["validator_pass"] = validated.valid
                result["validated_payload"] = validated.payload.model_dump()
                result["validator_warnings"] = validated.warnings
                totals["validator_pass"] += 1

                for field in (
                    "project_slug",
                    "prompt_type",
                    "destination",
                    "target_identifier",
                    "mode",
                    "requires_review",
                ):
                    actual = result["validated_payload"].get(field)
                    expected = case.expected.get(field)
                    matched = actual == expected
                    result["field_matches"][field] = {
                        "expected": expected,
                        "actual": actual,
                        "matched": matched,
                    }
                    if matched:
                        totals[field] += 1
            except (ValidationError, ValueError) as exc:
                result["validator_error"] = str(exc)

        results.append(result)

    print_report(results, totals)
    return 0


def load_cases(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        data = json.loads(stripped)
        cases.append(EvalCase(**data))
    return cases


def build_prompt(case: EvalCase, *, prompt_template: str) -> str:
    schema_json = json.dumps(
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
    return prompt_template.format(
        schema_json=schema_json,
        control_text=case.control_text,
        transcript_text=case.transcript_text,
    )


def load_prompt_template(*, prompt_file: Path | None, prompt_profile: str) -> str:
    if prompt_file is not None:
        return prompt_file.read_text(encoding="utf-8")
    template_path = DEFAULT_PROMPT_DIR / f"{prompt_profile}.txt"
    return template_path.read_text(encoding="utf-8")


def run_model(prompt: str, args: argparse.Namespace) -> str:
    if args.backend == "codex-exec":
        return run_codex_exec(prompt, args)

    cmd = [args.llama_binary]
    if args.hf:
        cmd.extend(["-hf", args.hf])
    else:
        cmd.extend(["-m", args.model])
    cmd.extend(
        [
            "-c",
            str(args.ctx_size),
            "-n",
            str(args.max_tokens),
            "-t",
            str(args.threads),
            "-tb",
            str(args.threads_batch),
            "--temp",
            str(args.temp),
            "--top-p",
            str(args.top_p),
            "--repeat-penalty",
            str(args.repeat_penalty),
            "-ngl",
            str(args.ngl),
            "-p",
            prompt,
        ]
    )
    if args.cpu_range:
        cmd.extend(["-Cr", args.cpu_range, "-Crb", args.cpu_range])
    completed = subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def run_codex_exec(prompt: str, args: argparse.Namespace) -> str:
    auth_path = Path.home() / ".codex" / "auth.json"
    if not auth_path.exists() and not os.environ.get("CODEX_API_KEY"):
        raise RuntimeError(
            "Codex auth missing. Run `codex login` for subscription/OAuth auth or set CODEX_API_KEY."
        )

    cmd = [
        args.codex_binary,
        "exec",
        "--cd",
        str(Path.cwd()),
        "--full-auto",
    ]
    if args.codex_model:
        cmd.extend(["-m", args.codex_model])
    cmd.extend(["-c", f'model_reasoning_effort="{args.codex_reasoning_effort}"'])
    cmd.append(prompt)

    completed = subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def parse_json_object(raw_output: str) -> tuple[dict[str, Any] | None, str | None]:
    stripped = raw_output.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None, "json_object_not_found"
    try:
        return json.loads(stripped[start : end + 1]), None
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error:{exc.msg}"


def print_report(results: list[dict[str, Any]], totals: dict[str, int]) -> None:
    print("PromptForge llama.cpp eval")
    print(f"cases={totals['cases']}")
    print(
        "summary "
        f"json_valid={totals['json_valid']}/{totals['cases']} "
        f"validator_pass={totals['validator_pass']}/{totals['cases']} "
        f"project_slug={totals['project_slug']}/{totals['cases']} "
        f"prompt_type={totals['prompt_type']}/{totals['cases']} "
        f"destination={totals['destination']}/{totals['cases']} "
        f"target_identifier={totals['target_identifier']}/{totals['cases']} "
        f"mode={totals['mode']}/{totals['cases']} "
        f"requires_review={totals['requires_review']}/{totals['cases']}"
    )
    print()

    for result in results:
        print(f"[{result['case_id']}]")
        print(
            f"json_valid={result['json_valid']} "
            f"validator_pass={result['validator_pass']}"
        )
        if result.get("parse_error"):
            print(f"parse_error={result['parse_error']}")
        if result.get("validator_error"):
            print(f"validator_error={result['validator_error']}")
        for field, detail in result.get("field_matches", {}).items():
            print(
                f"{field}: matched={detail['matched']} "
                f"expected={json.dumps(detail['expected'])} "
                f"actual={json.dumps(detail['actual'])}"
            )
        print()


if __name__ == "__main__":
    raise SystemExit(main())
