from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from promptforge_services.console_models import PromptGenerationRecord


class KanbanModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class KanbanManifestPreflightError(KanbanModel):
    code: str
    message: str
    field: str | None = None


class KanbanWorkspaceBinding(KanbanModel):
    kanban_base_url: str | None = Field(default=None, alias="kanbanBaseUrl")
    kanban_workspace_id: str | None = Field(default=None, alias="kanbanWorkspaceId")


class KanbanImportTask(KanbanModel):
    external_task_key: str = Field(alias="externalTaskKey")
    prompt: str
    title: str | None = None


class KanbanImportManifest(KanbanModel):
    version: Literal["v1"] = "v1"
    tasks: list[KanbanImportTask]
    links: list[dict[str, Any]] = Field(default_factory=list)
    start_task_external_keys: list[str] | None = Field(default=None, alias="startTaskExternalKeys")


class KanbanImportBuildResult(KanbanModel):
    ok: bool
    manifest: KanbanImportManifest | None = None
    errors: list[KanbanManifestPreflightError] = Field(default_factory=list)


class KanbanImportTaskMapping(KanbanModel):
    external_task_key: str = Field(alias="externalTaskKey")
    task_id: str = Field(alias="taskId")
    column_id: str = Field(alias="columnId")
    created: bool


class KanbanImportLinkResult(KanbanModel):
    from_external_task_key: str = Field(alias="fromExternalTaskKey")
    to_external_task_key: str = Field(alias="toExternalTaskKey")
    dependency_id: str = Field(alias="dependencyId")
    created: bool


class KanbanImportStartResult(KanbanModel):
    external_task_key: str = Field(alias="externalTaskKey")
    task_id: str = Field(alias="taskId")
    ok: bool
    summary: dict[str, Any] | None = None
    error: str | None = None


class KanbanImportError(KanbanModel):
    code: str
    message: str
    external_task_key: str | None = Field(default=None, alias="externalTaskKey")
    from_external_task_key: str | None = Field(default=None, alias="fromExternalTaskKey")
    to_external_task_key: str | None = Field(default=None, alias="toExternalTaskKey")


class KanbanImportResponse(KanbanModel):
    version: Literal["v1"]
    ok: bool
    applied: bool
    task_mappings: list[KanbanImportTaskMapping] = Field(alias="taskMappings")
    link_results: list[KanbanImportLinkResult] = Field(alias="linkResults")
    start_results: list[KanbanImportStartResult] = Field(alias="startResults")
    error: KanbanImportError | None = None


class KanbanPromptPreviewResponse(KanbanModel):
    prompt_generation_id: str = Field(alias="promptGenerationId")
    project_id: str | None = Field(default=None, alias="projectId")
    source_status: str = Field(alias="sourceStatus")
    kanban_base_url: str | None = Field(default=None, alias="kanbanBaseUrl")
    kanban_workspace_id: str | None = Field(default=None, alias="kanbanWorkspaceId")
    build: KanbanImportBuildResult


class KanbanPromptApplyResponse(KanbanModel):
    prompt_generation_id: str = Field(alias="promptGenerationId")
    project_id: str | None = Field(default=None, alias="projectId")
    kanban_base_url: str | None = Field(default=None, alias="kanbanBaseUrl")
    kanban_workspace_id: str | None = Field(default=None, alias="kanbanWorkspaceId")
    manifest: KanbanImportManifest | None = None
    result: KanbanImportResponse | None = None
    preflight_errors: list[KanbanManifestPreflightError] = Field(default_factory=list, alias="preflightErrors")


def derive_external_task_key(prompt_generation_id: str) -> str:
    return f"pf:pg:{prompt_generation_id.strip()}"


def validate_kanban_binding(binding: KanbanWorkspaceBinding | None) -> list[KanbanManifestPreflightError]:
    if binding is None:
        return [
            KanbanManifestPreflightError(
                code="kanban_binding_missing_base_url",
                message="Prompt Forge project runtime settings are missing kanbanBaseUrl.",
                field="kanbanBaseUrl",
            ),
            KanbanManifestPreflightError(
                code="kanban_binding_missing_workspace_id",
                message="Prompt Forge project runtime settings are missing kanbanWorkspaceId.",
                field="kanbanWorkspaceId",
            ),
        ]

    errors: list[KanbanManifestPreflightError] = []
    if not (binding.kanban_base_url or "").strip():
        errors.append(
            KanbanManifestPreflightError(
                code="kanban_binding_missing_base_url",
                message="Prompt Forge project runtime settings are missing kanbanBaseUrl.",
                field="kanbanBaseUrl",
            )
        )
    if not (binding.kanban_workspace_id or "").strip():
        errors.append(
            KanbanManifestPreflightError(
                code="kanban_binding_missing_workspace_id",
                message="Prompt Forge project runtime settings are missing kanbanWorkspaceId.",
                field="kanbanWorkspaceId",
            )
        )
    return errors


def build_kanban_import_manifest(
    source: PromptGenerationRecord | None,
    binding: KanbanWorkspaceBinding | None,
) -> KanbanImportBuildResult:
    errors = validate_kanban_binding(binding)
    if source is None:
        errors.append(
            KanbanManifestPreflightError(
                code="prompt_generation_not_found",
                message="Prompt generation record was not found.",
                field="promptGenerationId",
            )
        )
        return KanbanImportBuildResult(ok=False, errors=errors)

    prompt = source.final_prompt_markdown.strip()
    if not prompt:
        errors.append(
            KanbanManifestPreflightError(
                code="kanban_manifest_missing_prompt",
                message="Prompt generation does not have final_prompt_markdown content.",
                field="finalPromptMarkdown",
            )
        )
        return KanbanImportBuildResult(ok=False, errors=errors)

    if errors:
        return KanbanImportBuildResult(ok=False, errors=errors)

    manifest = KanbanImportManifest(
        tasks=[
            KanbanImportTask(
                externalTaskKey=derive_external_task_key(source.id),
                prompt=prompt,
            )
        ]
    )
    return KanbanImportBuildResult(ok=True, manifest=manifest)
