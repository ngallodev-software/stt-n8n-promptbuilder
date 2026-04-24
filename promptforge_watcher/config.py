import os

from pydantic import BaseModel, Field


class WatcherConfig(BaseModel):
    database_url: str | None = os.getenv("PROMPTFORGE_DATABASE_URL")
    vault_path: str = os.getenv("PROMPTFORGE_VAULT_PATH", "/vault")
    watch_folder: str = os.getenv("PROMPTFORGE_WATCH_FOLDER", "Inbox/Voice")
    processed_folder: str = os.getenv("PROMPTFORGE_PROCESSED_FOLDER", "Processed/Voice")
    error_folder: str = os.getenv("PROMPTFORGE_ERROR_FOLDER", "Processing/Error")
    webhook_url: str = os.getenv("PROMPTFORGE_N8N_WEBHOOK_URL", "http://n8n:5678/webhook/promptforge-intake")
    webhook_enabled: bool = os.getenv("PROMPTFORGE_WEBHOOK_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    kanban_base_url: str = os.getenv("PROMPTFORGE_KANBAN_BASE_URL", "http://127.0.0.1:3484")
    kanban_workspace_id: str = os.getenv("PROMPTFORGE_KANBAN_WORKSPACE_ID", "")
    stabilization_seconds: float = Field(
        default=float(os.getenv("PROMPTFORGE_STABILIZATION_SECONDS", "0.5")),
        ge=0.0,
    )
