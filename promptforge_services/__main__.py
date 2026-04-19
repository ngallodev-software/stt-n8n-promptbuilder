from __future__ import annotations

import os

import uvicorn


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    uvicorn.run(
        "promptforge_services.api:app",
        host=os.getenv("PROMPTFORGE_HOST", "0.0.0.0"),
        port=int(os.getenv("PROMPTFORGE_PORT", "8090")),
        reload=False,
        access_log=_env_bool("PROMPTFORGE_UVICORN_ACCESS_LOG", False),
    )


if __name__ == "__main__":
    main()
