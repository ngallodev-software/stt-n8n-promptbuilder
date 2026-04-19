from __future__ import annotations

import httpx

from promptforge_services.models import PrepareDeliveryResponse, RenderResponse
from promptforge_watcher.models import ImportResult, WebhookPayload


def build_webhook_payload(
    result: ImportResult,
    *,
    project_slug: str,
    prompt_type: str,
    destination: str,
    mode: str,
    requires_review: bool,
    render: RenderResponse,
    delivery: PrepareDeliveryResponse,
) -> WebhookPayload:
    if not all(
        [
            result.intake_note,
            result.utterance,
            result.prompt_generation,
            result.delivery,
        ]
    ):
        raise ValueError("Cannot build webhook payload for an incomplete import result")

    return WebhookPayload(
        intake_note_id=result.intake_note.id,
        utterance_id=result.utterance.id,
        prompt_generation_id=result.prompt_generation.id,
        delivery_id=result.delivery.id,
        contract_name=render.contract_name,
        project_slug=project_slug,
        prompt_type=prompt_type,
        destination=destination,
        target_type=delivery.delivery.target_type,
        target_identifier=result.delivery.target_identifier,
        mode=mode,
        priority=delivery.delivery.priority,
        delivery_status=result.delivery.status,
        requires_review=requires_review,
        template_name=render.template_name,
        final_prompt_markdown=render.final_prompt_markdown,
    )


def post_webhook(url: str, payload: WebhookPayload, *, timeout_seconds: float = 5.0) -> None:
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(url, json=payload.model_dump())
        response.raise_for_status()
