from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Destination = Literal["chat", "cli", "obsidian_note", "queue_only"]
PromptType = Literal["general", "coding-cli", "delegation", "planning", "review"]
Mode = Literal["draft", "queue", "auto_dispatch"]
TargetType = Literal[
    "none",
    "chat_session",
    "claude_session",
    "codex_session",
    "obsidian_note",
    "generic_queue",
]
DeliveryStatus = Literal["not_started", "queued", "dispatching", "delivered", "acked", "failed"]
LLMMode = Literal[
    "deterministic_only",
    "deterministic_plus_review",
    "llm_inference_optional",
]
LLMTaskKind = Literal["review", "inference"]


class BaseContract(BaseModel):
    contract_name: str
    requires_review: bool = False
    notes: list[str] = Field(default_factory=list)


class AgentTaskV1(BaseContract):
    contract_name: Literal["agent_task_v1"]
    intent: Literal["agent_task"]
    project_slug: str
    prompt_type: PromptType
    destination: Destination
    target_identifier: str | None = None
    mode: Mode = "queue"
    final_prompt_markdown: str

    @field_validator("project_slug", "final_prompt_markdown")
    @classmethod
    def _ensure_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must be non-empty")
        return value

    @field_validator("target_identifier")
    @classmethod
    def _normalize_target_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ParsedDirectives(BaseModel):
    project: str | None = None
    prompt_type: str | None = None
    destination: str | None = None
    target_identifier: str | None = None
    mode: str | None = None
    priority: str | None = None
    requires_review: bool | None = None
    warnings: list[str] = Field(default_factory=list)


class PreprocessRequest(BaseModel):
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    control_text: str | None = None
    transcript_text: str
    known_projects: list[str] = Field(
        default_factory=lambda: ["inbox", "the-tax-machine", "promptforge"]
    )


class PreprocessResponse(BaseModel):
    resolved_project: str
    resolved_prompt_type: PromptType
    resolved_destination: Destination
    target_identifier: str | None = None
    mode: Mode
    requires_review: bool = False
    warnings: list[str] = Field(default_factory=list)
    normalized_transcript: str
    parsed_directives: ParsedDirectives
    draft_structured_output: AgentTaskV1


class ValidateRequest(BaseModel):
    contract_name: Literal["agent_task_v1"]
    payload: dict[str, Any]


class ValidateResponse(BaseModel):
    contract_name: Literal["agent_task_v1"]
    valid: bool
    warnings: list[str] = Field(default_factory=list)
    payload: AgentTaskV1


class RenderRequest(BaseModel):
    contract_name: Literal["agent_task_v1"]
    payload: dict[str, Any]


class RenderResponse(BaseModel):
    contract_name: Literal["agent_task_v1"]
    template_name: str
    final_prompt_markdown: str
    payload: AgentTaskV1


class PrepareDeliveryRequest(BaseModel):
    contract_name: Literal["agent_task_v1"]
    payload: dict[str, Any]
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


class PreparedDelivery(BaseModel):
    destination: Destination
    target_type: TargetType
    target_identifier: str
    mode: Mode
    status: DeliveryStatus = "queued"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    requires_review: bool = False


class PrepareDeliveryResponse(BaseModel):
    contract_name: Literal["agent_task_v1"]
    delivery: PreparedDelivery
    payload: AgentTaskV1


class LLMProviderHealth(BaseModel):
    provider_name: str
    provider_family: str
    configured: bool
    available: bool
    model_name: str | None = None
    base_url: str | None = None
    detail: str | None = None


class LLMProvidersHealthResponse(BaseModel):
    enabled: bool
    mode: LLMMode
    review_provider: str | None = None
    inference_provider: str | None = None
    providers: list[LLMProviderHealth] = Field(default_factory=list)
