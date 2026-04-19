from __future__ import annotations

import difflib
import re
from typing import Any

from jinja2 import Template

from promptforge_services.models import (
    AgentTaskV1,
    LLMProvidersHealthResponse,
    Mode,
    ParsedDirectives,
    PrepareDeliveryRequest,
    PrepareDeliveryResponse,
    PreparedDelivery,
    PreprocessRequest,
    PreprocessResponse,
    PromptType,
    RenderRequest,
    RenderResponse,
    ValidateRequest,
    ValidateResponse,
)
from promptforge_services.llm import llm_health_report

try:
    from mdformat import text as mdformat_text
except ImportError:  # pragma: no cover - optional runtime polish
    mdformat_text = None

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover - deterministic fallback
    fuzz = None

CONTROL_KEY_ALIASES = {
    "project": "project",
    "repo": "project",
    "workspace": "project",
    "prompt type": "prompt_type",
    "prompt kind": "prompt_type",
    "destination": "destination",
    "dest": "destination",
    "target": "target_identifier",
    "session": "target_identifier",
    "mode": "mode",
    "priority": "priority",
    "review": "requires_review",
    "requires review": "requires_review",
}

PROJECT_ALIASES = {
    "thtaxmachine": "the-tax-machine",
    "the tax machine": "the-tax-machine",
    "tax machine": "the-tax-machine",
    "prompt forge": "promptforge",
}

PROMPT_TYPE_ALIASES: dict[str, PromptType] = {
    "general": "general",
    "coding": "coding-cli",
    "coding-cli": "coding-cli",
    "coding cli": "coding-cli",
    "codingcli": "coding-cli",
    "delegation": "delegation",
    "planning": "planning",
    "review": "review",
}

DESTINATION_ALIASES = {
    "chat": "chat",
    "cli": "cli",
    "obsidian": "obsidian_note",
    "obsidian note": "obsidian_note",
    "obsidian_note": "obsidian_note",
    "queue": "queue_only",
    "queue only": "queue_only",
    "queue_only": "queue_only",
}

MODE_ALIASES: dict[str, Mode] = {
    "draft": "draft",
    "queue": "queue",
    "auto": "auto_dispatch",
    "auto dispatch": "auto_dispatch",
    "auto_dispatch": "auto_dispatch",
}

CODING_CLI_TEMPLATE = Template(
    "Project: {{ project_slug }}\n"
    "Target: {{ target_identifier or 'manual-review' }}\n"
    "Mode: {{ mode }}\n\n"
    "Task:\n"
    "{{ final_prompt_markdown }}"
)

GENERIC_TEMPLATE = Template(
    "Project: {{ project_slug }}\n"
    "Destination: {{ destination }}\n"
    "Mode: {{ mode }}\n"
    "{% if target_identifier %}Target: {{ target_identifier }}\n{% endif %}\n"
    "{{ final_prompt_markdown }}"
)


def parse_directives(control_text: str | None) -> ParsedDirectives:
    parsed = ParsedDirectives()
    if not control_text:
        return parsed

    for raw_line in control_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^(?P<key>.+?)\s+is\s+(?P<value>.+)$", line, re.IGNORECASE)
        if not match:
            parsed.warnings.append(f"ignored_directive:{line}")
            continue

        key = CONTROL_KEY_ALIASES.get(match.group("key").strip().lower())
        value = match.group("value").strip()
        if key is None:
            parsed.warnings.append(f"unknown_directive:{line}")
            continue

        if key == "requires_review":
            lowered = value.lower()
            if lowered in {"true", "yes", "1"}:
                parsed.requires_review = True
            elif lowered in {"false", "no", "0"}:
                parsed.requires_review = False
            else:
                parsed.warnings.append(f"invalid_review_value:{value}")
            continue

        setattr(parsed, key, value)
    return parsed


def preprocess_request(payload: PreprocessRequest) -> PreprocessResponse:
    directives = parse_directives(payload.control_text)
    warnings = list(directives.warnings)

    known_projects = _known_projects(payload)
    project_value = directives.project or str(payload.frontmatter.get("project", "inbox"))
    resolved_project, project_warning = _resolve_project(project_value, known_projects)
    if project_warning:
        warnings.append(project_warning)

    prompt_type = _resolve_alias(
        directives.prompt_type or str(payload.frontmatter.get("prompt_type", "general")),
        PROMPT_TYPE_ALIASES,
        "general",
    )
    destination = _resolve_alias(
        directives.destination or str(payload.frontmatter.get("destination", "queue_only")),
        DESTINATION_ALIASES,
        "queue_only",
    )
    mode = _resolve_alias(
        directives.mode or str(payload.frontmatter.get("mode", "queue")),
        MODE_ALIASES,
        "queue",
    )
    target_identifier = directives.target_identifier or _string_or_none(
        payload.frontmatter.get("target_identifier")
    )

    normalized_transcript = normalize_transcript(payload.transcript_text)

    requires_review = bool(payload.frontmatter.get("requires_review", False))
    requires_review = requires_review or bool(directives.requires_review) or project_warning is not None
    notes: list[str] = []

    if destination == "cli" and not target_identifier:
        destination = "queue_only"
        requires_review = True
        warning = "cli_target_missing"
        warnings.append(warning)
        notes.append("CLI delivery requested without a target; routed to manual review queue.")

    if project_warning:
        notes.append(f"Project could not be resolved confidently from directive: {project_value}")

    draft_structured_output = AgentTaskV1(
        contract_name="agent_task_v1",
        intent="agent_task",
        project_slug=resolved_project,
        prompt_type=prompt_type,
        destination=destination,
        target_identifier=target_identifier,
        mode=mode,
        requires_review=requires_review,
        final_prompt_markdown=normalized_transcript,
        notes=notes,
    )

    return PreprocessResponse(
        resolved_project=resolved_project,
        resolved_prompt_type=prompt_type,
        resolved_destination=destination,
        target_identifier=target_identifier,
        mode=mode,
        requires_review=requires_review,
        warnings=warnings,
        normalized_transcript=normalized_transcript,
        parsed_directives=directives,
        draft_structured_output=draft_structured_output,
    )


def validate_request(payload: ValidateRequest) -> ValidateResponse:
    if payload.contract_name != "agent_task_v1":
        raise ValueError(f"Unsupported contract: {payload.contract_name}")

    normalized_payload = dict(payload.payload)
    normalized_payload["contract_name"] = payload.contract_name
    normalized_payload["prompt_type"] = _resolve_alias(
        str(normalized_payload.get("prompt_type", "general")),
        PROMPT_TYPE_ALIASES,
        "general",
    )
    normalized_payload["destination"] = _resolve_alias(
        str(normalized_payload.get("destination", "queue_only")),
        DESTINATION_ALIASES,
        "queue_only",
    )
    normalized_payload["mode"] = _resolve_alias(
        str(normalized_payload.get("mode", "queue")),
        MODE_ALIASES,
        "queue",
    )
    normalized_payload["target_identifier"] = _string_or_none(
        normalized_payload.get("target_identifier")
    )

    warnings: list[str] = []
    notes = list(normalized_payload.get("notes", []))

    if normalized_payload["destination"] == "cli" and not normalized_payload["target_identifier"]:
        normalized_payload["destination"] = "queue_only"
        normalized_payload["requires_review"] = True
        notes.append("CLI delivery requested without a target; routed to manual review queue.")
        warnings.append("cli_target_missing")

    normalized_payload["notes"] = notes
    contract = AgentTaskV1.model_validate(normalized_payload)

    return ValidateResponse(
        contract_name=payload.contract_name,
        valid=True,
        warnings=warnings,
        payload=contract,
    )


def render_request(payload: RenderRequest) -> RenderResponse:
    validated = validate_request(
        ValidateRequest(contract_name=payload.contract_name, payload=payload.payload)
    ).payload

    if validated.prompt_type == "coding-cli":
        template_name = "coding-cli-default"
        rendered = CODING_CLI_TEMPLATE.render(**validated.model_dump())
    else:
        template_name = "generic-default"
        rendered = GENERIC_TEMPLATE.render(**validated.model_dump())

    rendered = _normalize_markdown(rendered)
    return RenderResponse(
        contract_name=payload.contract_name,
        template_name=template_name,
        final_prompt_markdown=rendered,
        payload=validated,
    )


def prepare_delivery_request(payload: PrepareDeliveryRequest) -> PrepareDeliveryResponse:
    validated = validate_request(
        ValidateRequest(contract_name=payload.contract_name, payload=payload.payload)
    ).payload

    if validated.destination == "cli":
        target_type = _resolve_cli_target_type(validated.target_identifier)
        target_identifier = validated.target_identifier or "manual-review"
    elif validated.destination == "chat":
        target_type = "chat_session"
        target_identifier = validated.target_identifier or "chat-queue"
    elif validated.destination == "obsidian_note":
        target_type = "obsidian_note"
        target_identifier = validated.target_identifier or "obsidian-writeback"
    else:
        target_type = "generic_queue"
        target_identifier = validated.target_identifier or "manual-review"

    delivery = PreparedDelivery(
        destination=validated.destination,
        target_type=target_type,
        target_identifier=target_identifier,
        mode=validated.mode,
        status="queued",
        priority=payload.priority,
        requires_review=validated.requires_review,
    )
    return PrepareDeliveryResponse(
        contract_name=payload.contract_name,
        delivery=delivery,
        payload=validated,
    )


def llm_providers_health() -> LLMProvidersHealthResponse:
    return llm_health_report()


def normalize_transcript(text: str) -> str:
    stripped = text.strip()
    stripped = re.sub(r"^(um+|uh+|like)\s+", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if not stripped:
        return stripped
    if stripped[-1] not in ".!?":
        stripped = f"{stripped}."
    return stripped[0].upper() + stripped[1:]


def _known_projects(payload: PreprocessRequest) -> list[str]:
    known = list(payload.known_projects)
    project = _string_or_none(payload.frontmatter.get("project"))
    if project:
        known.append(project)
    if "inbox" not in known:
        known.append("inbox")
    unique: list[str] = []
    for item in known:
        if item not in unique:
            unique.append(item)
    return unique


def _resolve_project(raw_value: str, known_projects: list[str]) -> tuple[str, str | None]:
    value = raw_value.strip()
    lowered = value.lower()
    if lowered in PROJECT_ALIASES:
        return PROJECT_ALIASES[lowered], None

    for candidate in known_projects:
        if lowered == candidate.lower():
            return candidate, None

    best_candidate, score = _best_match(value, known_projects)
    if best_candidate is not None and score >= 88:
        return best_candidate, None

    return "inbox", "project_match_below_threshold"


def _resolve_alias(raw_value: str, aliases: dict[str, str], default: str) -> str:
    lowered = raw_value.strip().lower()
    return aliases.get(lowered, default)


def _best_match(value: str, candidates: list[str]) -> tuple[str | None, float]:
    if not candidates:
        return None, 0.0

    if fuzz is not None:
        scored = [(candidate, float(fuzz.ratio(value, candidate))) for candidate in candidates]
        return max(scored, key=lambda item: item[1])

    scored = [
        (candidate, difflib.SequenceMatcher(None, value.lower(), candidate.lower()).ratio() * 100.0)
        for candidate in candidates
    ]
    return max(scored, key=lambda item: item[1])


def _normalize_markdown(text: str) -> str:
    if mdformat_text is None:
        return text.strip()
    return mdformat_text(text).strip()


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _resolve_cli_target_type(target_identifier: str | None) -> str:
    if not target_identifier:
        return "generic_queue"
    lowered = target_identifier.lower()
    if lowered.startswith("codex"):
        return "codex_session"
    return "claude_session"
