from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from promptforge_services.models import Destination, DeliveryStatus, Mode, PromptType, TargetType

Scope = Literal["global", "user", "project"]
NoteStatus = Literal["new", "imported", "processing", "processed", "error", "archived"]
RevisionKind = Literal[
    "raw",
    "directive_stripped",
    "deterministic_preprocessed",
    "llm_cleaned",
    "llm_structured_source",
    "final_rendered_prompt",
]
ProducerType = Literal["human", "watcher", "python", "llm", "renderer", "system"]
PromptGenerationStatus = Literal[
    "created",
    "preprocessed",
    "transforming",
    "structured_validating",
    "rendered",
    "failed",
]
ProcessingStatus = Literal["running", "completed", "failed"]
PriorityLevel = Literal["low", "normal", "high", "urgent"]
CaptureType = Literal["voice", "text", "import"]
RuleType = Literal["cleanup", "expansion", "routing", "formatting", "safety", "terminology"]
LogLevel = Literal["debug", "info", "warn", "error"]


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class PaginationMeta(StrictBaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool


T = TypeVar("T")


class PaginatedResponse(StrictBaseModel, Generic[T]):
    pagination: PaginationMeta


class ProjectRecord(StrictBaseModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    created_at: str
    updated_at: str


class ProjectListResponse(PaginatedResponse[ProjectRecord]):
    projects: list[ProjectRecord]


class ProjectDetailResponse(StrictBaseModel):
    project: ProjectRecord


class IntakeNoteRecord(StrictBaseModel):
    id: str
    project_id: str | None = None
    note_relative_path: str
    status: NoteStatus
    watch_eligible: bool
    source_device: str
    body_text: str
    frontmatter_original: dict[str, Any]
    frontmatter_current: dict[str, Any]
    metadata_json: dict[str, Any]
    created_at: str
    updated_at: str


class IntakeNoteListResponse(PaginatedResponse[IntakeNoteRecord]):
    intake_notes: list[IntakeNoteRecord] = Field(alias="intakeNotes")


class IntakeNoteDetailResponse(StrictBaseModel):
    intake_note: IntakeNoteRecord = Field(alias="note")


class UtteranceRecord(StrictBaseModel):
    id: str
    intake_note_id: str
    raw_text: str
    directive_text: str | None = None
    project_id: str | None = None
    scope: Scope
    capture_type: CaptureType
    created_at: str


class TranscriptRevisionRecord(StrictBaseModel):
    id: str
    utterance_id: str
    revision_kind: RevisionKind
    content_text: str
    producer_type: ProducerType
    producer_name: str
    template_profile: str | None = None
    quality_score: float | None = None
    metadata_json: dict[str, Any]
    created_at: str


class PromptGenerationRecord(StrictBaseModel):
    id: str
    intake_note_id: str
    status: PromptGenerationStatus
    requires_review: bool
    prompt_type: PromptType
    ruleset_id: str | None = None
    template_id: str | None = None
    destination: Destination
    mode: Mode
    priority: PriorityLevel
    structured_output_json: dict[str, Any]
    final_prompt_markdown: str
    validation_warnings: list[str]
    created_at: str
    updated_at: str


class DeliveryRecord(StrictBaseModel):
    id: str
    prompt_generation_id: str
    target_id: str | None = None
    status: DeliveryStatus
    destination: Destination
    mode: Mode
    priority: PriorityLevel
    retry_count: int
    failure_text: str | None = None
    ack_text: str | None = None
    created_at: str
    updated_at: str


class ProcessingRunRecord(StrictBaseModel):
    id: str
    intake_note_id: str
    status: ProcessingStatus
    stage_name: str
    error_text: str | None = None
    trace_json: dict[str, Any]
    created_at: str
    updated_at: str


class NoteLineageResponse(StrictBaseModel):
    intake_note: IntakeNoteRecord
    utterances: list[UtteranceRecord]
    revisions: list[TranscriptRevisionRecord]
    prompt_generations: list[PromptGenerationRecord] = Field(alias="promptGenerations")
    deliveries: list[DeliveryRecord]
    processing_runs: list[ProcessingRunRecord] = Field(alias="processingRuns")


class PromptListResponse(PaginatedResponse[PromptGenerationRecord]):
    prompt_generations: list[PromptGenerationRecord] = Field(alias="promptGenerations")


class PromptDetailResponse(StrictBaseModel):
    prompt_generation: PromptGenerationRecord


class DeliveryListResponse(PaginatedResponse[DeliveryRecord]):
    deliveries: list[DeliveryRecord]


class DeliveryDetailResponse(StrictBaseModel):
    delivery: DeliveryRecord


class RuleSetRecord(StrictBaseModel):
    id: str
    name: str
    scope: Scope
    project_id: str | None = None
    active: bool
    description: str | None = None
    updated_at: str


class RuleRecord(StrictBaseModel):
    id: str
    ruleset_id: str
    name: str
    rule_type: RuleType
    priority: int
    enabled: bool
    pattern: str
    replacement: str
    description: str | None = None
    updated_at: str


class RulesetListResponse(PaginatedResponse[RuleSetRecord]):
    rulesets: list[RuleSetRecord]


class RulesetDetailResponse(StrictBaseModel):
    ruleset: RuleSetRecord
    rules: list[RuleRecord]


class RuleListResponse(PaginatedResponse[RuleRecord]):
    rules: list[RuleRecord]


class RuleDetailResponse(StrictBaseModel):
    rule: RuleRecord


class DictionaryTermRecord(StrictBaseModel):
    id: str
    scope: Scope
    project_id: str | None = None
    source_term: str
    normalized_term: str
    description: str | None = None
    created_at: str
    updated_at: str


class DictionaryTermListResponse(PaginatedResponse[DictionaryTermRecord]):
    term_dictionary: list[DictionaryTermRecord] = Field(alias="termDictionary")


class DictionaryTermDetailResponse(StrictBaseModel):
    term: DictionaryTermRecord


class PromptTemplateRecord(StrictBaseModel):
    id: str
    name: str
    prompt_type: str
    scope: Scope
    project_id: str | None = None
    version: int
    is_active: bool
    template_family_key: str
    body: str
    updated_at: str


class PromptTemplateListResponse(PaginatedResponse[PromptTemplateRecord]):
    prompt_templates: list[PromptTemplateRecord] = Field(alias="promptTemplates")


class PromptTemplateDetailResponse(StrictBaseModel):
    prompt_template: PromptTemplateRecord


class DeliveryTargetRecord(StrictBaseModel):
    id: str
    name: str
    target_type: TargetType
    destination: Destination
    scope: Scope
    project_id: str | None = None
    enabled: bool
    is_sensitive: bool
    requires_confirmation: bool
    environment: str
    validation_status: str
    updated_at: str


class DeliveryTargetListResponse(PaginatedResponse[DeliveryTargetRecord]):
    delivery_targets: list[DeliveryTargetRecord] = Field(alias="deliveryTargets")


class DeliveryTargetDetailResponse(StrictBaseModel):
    delivery_target: DeliveryTargetRecord


class LogRecord(StrictBaseModel):
    id: str
    service: str
    level: LogLevel
    message: str
    timestamp: str
    intake_note_id: str | None = None
    utterance_id: str | None = None
    prompt_generation_id: str | None = None
    delivery_id: str | None = None
    fields: dict[str, Any]


class LogListResponse(PaginatedResponse[LogRecord]):
    logs: list[LogRecord]


class LogDetailResponse(StrictBaseModel):
    log: LogRecord


class QueueDepthResponse(StrictBaseModel):
    queue_depth: int
    queued_count: int
    dispatching_count: int
    observed_at: str


class ThroughputSummaryResponse(StrictBaseModel):
    project_id: str | None = None
    project_slug: str | None = None
    window_start: str
    window_end: str
    completed_count: int
    failed_count: int
    throughput_per_hour: float


class SlaSummaryResponse(StrictBaseModel):
    project_id: str | None = None
    project_slug: str | None = None
    window_start: str
    window_end: str
    target_seconds: int
    on_time_count: int
    breached_count: int
    on_time_rate: float


class ErrorFingerprintRecord(StrictBaseModel):
    fingerprint: str
    service: str | None = None
    level: LogLevel
    count: int
    first_seen_at: str
    last_seen_at: str
    sample_message: str | None = None
    sample_context: dict[str, Any] = Field(default_factory=dict)


class ErrorFingerprintListResponse(PaginatedResponse[ErrorFingerprintRecord]):
    error_fingerprints: list[ErrorFingerprintRecord] = Field(alias="errorFingerprints")
