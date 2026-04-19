from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from promptforge_services.models import PrepareDeliveryResponse, PreprocessResponse, RenderResponse


class ParsedNote(BaseModel):
    vault_path: str
    relative_path: str
    title: str
    frontmatter: dict
    body_markdown: str
    control_text: str | None
    transcript_text: str | None
    note_hash: str


class EligibilityResult(BaseModel):
    eligible: bool
    reasons: list[str] = Field(default_factory=list)


class StoredIntakeNote(BaseModel):
    id: str
    note_relative_path: str
    note_hash: str
    status: Literal["imported", "skipped"]


class StoredUtterance(BaseModel):
    id: str
    intake_note_id: str
    raw_text: str


class StoredPromptGeneration(BaseModel):
    id: str
    utterance_id: str
    status: str


class StoredDelivery(BaseModel):
    id: str
    prompt_generation_id: str
    status: str
    target_identifier: str
    error_text: str | None = None


class StoredProcessingRun(BaseModel):
    id: str
    utterance_id: str
    status: str


class StoredLLMRun(BaseModel):
    id: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    mode: Literal["review", "inference"] | None = None
    latency_ms: int | None = None
    token_usage_json: dict[str, Any] | None = None
    fallback_chain: list[str] | None = None
    summary: str | None = None
    findings_json: dict[str, Any] | list[Any] | None = None
    raw_response_json: dict[str, Any] | None = None


class ImportBundle(BaseModel):
    note: ParsedNote
    preprocess: PreprocessResponse
    render: RenderResponse
    delivery: PrepareDeliveryResponse
    llm_runs: list[StoredLLMRun] = Field(default_factory=list)


class ImportResult(BaseModel):
    imported: bool
    skipped_reason: str | None = None
    intake_note: StoredIntakeNote | None = None
    utterance: StoredUtterance | None = None
    prompt_generation: StoredPromptGeneration | None = None
    delivery: StoredDelivery | None = None
    processing_run: StoredProcessingRun | None = None


class WebhookPayload(BaseModel):
    intake_note_id: str
    utterance_id: str
    prompt_generation_id: str
    delivery_id: str
    contract_name: str
    project_slug: str
    prompt_type: str
    destination: str
    target_type: str
    target_identifier: str
    mode: str
    priority: str
    delivery_status: str
    requires_review: bool
    template_name: str
    final_prompt_markdown: str
