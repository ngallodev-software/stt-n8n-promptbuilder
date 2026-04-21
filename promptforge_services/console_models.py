from __future__ import annotations

from enum import Enum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from promptforge_services.models import (
    Destination,
    DeliveryStatus as DeliveryStatusValue,
    LLMMode,
    Mode,
    PromptType,
    TargetType,
)

RecordScope = Literal["global", "user", "project"]
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
ConsoleRole = Literal["viewer", "operator", "admin"]
CodexReasoningEffort = Literal["low", "medium", "high"]


class Scope(str, Enum):
    GLOBAL = "global"
    PROJECT = "project"


class RulesetScope(str, Enum):
    GLOBAL = "global"
    PROJECT = "project"


class DeliveryStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ConsoleRoleValue(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


EnumT = TypeVar("EnumT", bound=Enum)


def _coerce_enum(enum_cls: type[EnumT], value: Any) -> EnumT:
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError as exc:
            raise ValueError(f"invalid {enum_cls.__name__}") from exc
    raise ValueError(f"invalid {enum_cls.__name__}")


class DeliveryStatusRequest(StrictBaseModel):
    status: DeliveryStatus

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, value: Any) -> DeliveryStatus:
        return _coerce_enum(DeliveryStatus, value)


class RulePatchRequest(StrictBaseModel):
    enabled: bool | None = None
    priority: int | None = None


class RuleCreateRequest(StrictBaseModel):
    ruleset_id: str = Field(alias="rulesetId")
    rule_type: RuleType = Field(alias="ruleType")
    priority: int = 100
    enabled: bool = True
    match_conditions_json: dict[str, Any] = Field(default_factory=dict, alias="matchConditionsJson")
    action_json: dict[str, Any] = Field(default_factory=dict, alias="actionJson")
    notes: str | None = None


class RuleDryRunRequest(StrictBaseModel):
    sample_text: str = Field(alias="sampleText")
    context: dict[str, Any] = Field(default_factory=dict)


class RuleDryRunDiagnostic(StrictBaseModel):
    rule_id: str = Field(alias="ruleId")
    ruleset_id: str = Field(alias="rulesetId")
    name: str
    rule_type: RuleType = Field(alias="ruleType")
    priority: int
    enabled: bool
    matched: bool
    applied: bool
    skipped_reason: str | None = Field(default=None, alias="skippedReason")
    warnings: list[str] = Field(default_factory=list)
    input_text: str = Field(alias="inputText")
    output_text: str = Field(alias="outputText")
    effect_summary: dict[str, Any] = Field(default_factory=dict, alias="effectSummary")


class RuleDryRunSummary(StrictBaseModel):
    ruleset_id: str = Field(alias="rulesetId")
    total_rules: int = Field(alias="totalRules")
    matched_rules: int = Field(alias="matchedRules")
    applied_rules: int = Field(alias="appliedRules")
    skipped_rules: int = Field(alias="skippedRules")
    failed_rules: int = Field(alias="failedRules")
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuleDryRunResponse(StrictBaseModel):
    original_input: str = Field(alias="originalInput")
    transformed_output: str = Field(alias="transformedOutput")
    matched_rules: list[RuleDryRunDiagnostic] = Field(alias="matchedRules")
    skipped_rules: list[RuleDryRunDiagnostic] = Field(alias="skippedRules")
    failed_rules: list[RuleDryRunDiagnostic] = Field(alias="failedRules")
    summary: RuleDryRunSummary


class DictionaryUpsertRequest(StrictBaseModel):
    id: str | None = None
    scope: Scope | None = None
    project_id: str | None = None
    source_term: str | None = None
    normalized_term: str | None = None
    description: str | None = None

    @field_validator("scope", mode="before")
    @classmethod
    def _validate_scope(cls, value: Any) -> Scope | None:
        if value is None:
            return None
        return _coerce_enum(Scope, value)


class TemplateActivateRequest(StrictBaseModel):
    family: str


class PromptTemplateCreateRequest(StrictBaseModel):
    name: str
    prompt_type: str = Field(alias="promptType")
    scope: Scope = Scope.GLOBAL
    project_id: str | None = Field(default=None, alias="projectId")
    version: int = 1
    template_family_key: str = Field(alias="templateFamilyKey")
    body: str
    is_active: bool = Field(default=False, alias="isActive")

    @field_validator("scope", mode="before")
    @classmethod
    def _validate_scope(cls, value: Any) -> Scope:
        return _coerce_enum(Scope, value)


class PromptTemplatePatchRequest(StrictBaseModel):
    name: str | None = None
    prompt_type: str | None = Field(default=None, alias="promptType")
    scope: Scope | None = None
    project_id: str | None = Field(default=None, alias="projectId")
    version: int | None = None
    template_family_key: str | None = Field(default=None, alias="templateFamilyKey")
    body: str | None = None
    is_active: bool | None = Field(default=None, alias="isActive")

    @field_validator("scope", mode="before")
    @classmethod
    def _validate_scope(cls, value: Any) -> Scope | None:
        if value is None:
            return None
        return _coerce_enum(Scope, value)


class PromptPriorityRequest(StrictBaseModel):
    priority: Priority

    @field_validator("priority", mode="before")
    @classmethod
    def _validate_priority(cls, value: Any) -> Priority:
        return _coerce_enum(Priority, value)


class ConsoleRuntimeSettings(StrictBaseModel):
    obsidianVaultPath: str
    webhookUrl: str
    llmMode: LLMMode
    codexBinary: str
    codexReasoningEffort: CodexReasoningEffort
    openaiBaseUrl: str
    anthropicBaseUrl: str
    llmAssistEnabled: bool = False


class SecretSettingMetadata(StrictBaseModel):
    configured: bool
    last_rotated_at: str | None = None


class ConsoleSettingsPermissions(StrictBaseModel):
    can_update_runtime: bool
    can_rotate_secrets: bool
    can_purge_archived_notes: bool


class ConsoleSettingsResponse(StrictBaseModel):
    scope: Scope
    project_id: str | None = None
    runtime: ConsoleRuntimeSettings
    secrets: dict[str, SecretSettingMetadata]
    permissions: ConsoleSettingsPermissions
    updated_at: str


class ConsoleRuntimePatchRequest(StrictBaseModel):
    scope: Scope = Scope.GLOBAL
    project_id: str | None = None
    runtime: dict[str, Any]

    @field_validator("scope", mode="before")
    @classmethod
    def _validate_scope(cls, value: Any) -> Scope:
        return _coerce_enum(Scope, value)


class ConsoleSecretsPatchRequest(StrictBaseModel):
    scope: Scope = Scope.GLOBAL
    project_id: str | None = None
    secrets: dict[str, str]

    @field_validator("scope", mode="before")
    @classmethod
    def _validate_scope(cls, value: Any) -> Scope:
        return _coerce_enum(Scope, value)


class PurgeArchivedNotesRequest(StrictBaseModel):
    confirm: str


class PurgeArchivedNotesResponse(StrictBaseModel):
    ok: bool = True
    deleted_counts: dict[str, int] = Field(alias="deletedCounts")
    requested_at: str = Field(alias="requestedAt")


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
    scope: RecordScope
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
    session_identifier: str | None = None
    status: DeliveryStatusValue
    destination: Destination
    mode: Mode
    priority: PriorityLevel
    retry_count: int
    dispatch_request_json: dict[str, Any] = Field(default_factory=dict)
    dispatch_response_json: dict[str, Any] = Field(default_factory=dict)
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
    scope: RecordScope
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
    scope: RecordScope
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
    scope: RecordScope
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
    target_identifier: str
    destination: Destination
    scope: RecordScope
    project_id: str | None = None
    enabled: bool
    is_sensitive: bool
    requires_confirmation: bool
    environment: str
    validation_status: str
    validation_detail: str | None = None
    updated_at: str


class DeliveryTargetDispatchRequest(StrictBaseModel):
    delivery_id: str | None = None
    prompt_generation_id: str | None = Field(default=None, alias="promptGenerationId")
    target_session_identifier: str | None = Field(default=None, alias="targetSessionIdentifier")
    payload_content: str | None = Field(default=None, alias="payloadContent")
    payload_json: dict[str, Any] = Field(default_factory=dict, alias="payloadJson")
    priority: PriorityLevel | None = None
    mode: Mode | None = None
    environment: str | None = None
    dry_run: bool = Field(default=False, alias="dryRun")


class DeliveryTargetDispatchResponse(StrictBaseModel):
    delivery_id: str = Field(alias="deliveryId")
    target_id: str = Field(alias="targetId")
    target_type: TargetType = Field(alias="targetType")
    accepted: bool
    status: str
    machine_status: str = Field(alias="machineStatus")
    external_identifier: str | None = Field(default=None, alias="externalIdentifier")
    session_identifier: str | None = Field(default=None, alias="sessionIdentifier")
    prompt_generation_id: str | None = Field(default=None, alias="promptGenerationId")
    requested_at: str = Field(alias="requestedAt")
    dispatched_at: str | None = Field(default=None, alias="dispatchedAt")
    updated_at: str = Field(alias="updatedAt")
    retry_count: int = Field(alias="retryCount")
    warnings: list[str] = Field(default_factory=list)
    error_text: str | None = Field(default=None, alias="errorText")
    request_summary: dict[str, Any] = Field(default_factory=dict, alias="requestSummary")
    response_summary: dict[str, Any] = Field(default_factory=dict, alias="responseSummary")


class DeliveryTargetHealthResponse(StrictBaseModel):
    target_id: str = Field(alias="targetId")
    target_type: TargetType = Field(alias="targetType")
    health_status: str = Field(alias="healthStatus")
    detail: str | None = None
    attached: bool | None = None
    busy: bool | None = None
    reachable: bool | None = None
    stale: bool | None = None
    updated_at: str = Field(alias="updatedAt")


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
    queued: int
    dispatching: int
    failed_last_24h: int


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


class HealthResponse(StrictBaseModel):
    db: Literal["ok", "error"]
    vault: Literal["ok", "error"]
    watcher: Literal["running", "unknown"]


class WorkflowErrorRecord(StrictBaseModel):
    id: str
    note_path: str | None = None
    delivery_id: str | None = None
    error_type: str
    error_message: str
    failed_at: str
    dismissed_at: str | None = None
    created_at: str


class WorkflowErrorListResponse(StrictBaseModel):
    errors: list[WorkflowErrorRecord]
