import logging
import time

from fastapi import FastAPI, HTTPException, Request

from promptforge_services.models import (
    PrepareDeliveryRequest,
    PrepareDeliveryResponse,
    PreprocessRequest,
    PreprocessResponse,
    LLMProvidersHealthResponse,
    RenderRequest,
    RenderResponse,
    ValidateRequest,
    ValidateResponse,
)
from promptforge_services.pipeline import (
    prepare_delivery_request,
    preprocess_request,
    render_request,
    llm_providers_health,
    validate_request,
)
from promptforge_services.console_api import router as console_router

app = FastAPI(title="PromptForge Services")
_http_logger = logging.getLogger("promptforge.http")


@app.middleware("http")
async def _log_non_health_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    path = request.url.path
    if path not in {"/health", "/_healthz", "/providers/health"}:
        duration_ms = (time.perf_counter() - start) * 1000.0
        _http_logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            path,
            response.status_code,
            duration_ms,
        )
    return response


@app.get("/_healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "supported_contracts": ["agent_task_v1"]}


@app.get("/providers/health", response_model=LLMProvidersHealthResponse)
def providers_health() -> LLMProvidersHealthResponse:
    return llm_providers_health()


@app.post("/preprocess", response_model=PreprocessResponse)
def preprocess(payload: PreprocessRequest) -> PreprocessResponse:
    return preprocess_request(payload)


@app.post("/validate", response_model=ValidateResponse)
def validate(payload: ValidateRequest) -> ValidateResponse:
    try:
        return validate_request(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/render", response_model=RenderResponse)
def render(payload: RenderRequest) -> RenderResponse:
    try:
        return render_request(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/prepare-delivery", response_model=PrepareDeliveryResponse)
def prepare_delivery(payload: PrepareDeliveryRequest) -> PrepareDeliveryResponse:
    try:
        return prepare_delivery_request(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


app.include_router(console_router)
