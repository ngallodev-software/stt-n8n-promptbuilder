from __future__ import annotations

from enum import Enum
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel

VOICE_ROUTE_ROOT = "Inbox/Voice"


class RouteFamily(str, Enum):
    KANBAN = "kanban"
    QUEUE = "queue"
    REVIEW = "review"


KNOWN_ROUTE_FAMILIES = {family.value for family in RouteFamily}


class VoiceRouteResolution(BaseModel):
    source_root: str = VOICE_ROUTE_ROOT
    source_folder: str
    source_path: str
    route_family: str | None = None
    route_target: str | None = None
    route_context: str = ""
    supported: bool = False
    reason: str | None = None

    def as_frontmatter(self) -> dict[str, Any]:
        return {
            "source_root": self.source_root,
            "source_folder": self.source_folder,
            "source_path": self.source_path,
            "route_family": self.route_family,
            "route_target": self.route_target,
            "route_context": self.route_context,
            "supported": self.supported,
            "reason": self.reason,
        }

    def as_log_summary(self) -> str:
        family = self.route_family or "unknown"
        target = self.route_target or "—"
        context = self.route_context or "—"
        return f"family={family} target={target} context={context}"


def normalize_voice_route_root(watch_folder: str) -> str:
    normalized = watch_folder.strip().strip("/")
    return normalized or VOICE_ROUTE_ROOT


def resolve_voice_route(relative_path: str, watch_folder: str) -> VoiceRouteResolution:
    normalized_root = normalize_voice_route_root(watch_folder)
    route_source = PurePosixPath(relative_path).parent.as_posix()
    if route_source == ".":
        route_source = ""

    if route_source == normalized_root:
        return VoiceRouteResolution(
            source_root=normalized_root,
            source_folder=route_source or normalized_root,
            source_path=relative_path,
            route_family=None,
            route_target=None,
            route_context="",
            supported=False,
            reason="missing_route_family",
        )

    root_prefix = f"{normalized_root}/"
    if not route_source.startswith(root_prefix):
        return VoiceRouteResolution(
            source_root=normalized_root,
            source_folder=route_source or relative_path,
            source_path=relative_path,
            route_family=None,
            route_target=None,
            route_context="",
            supported=False,
            reason="outside_watch_folder",
        )

    tail = route_source[len(root_prefix) :]
    segments = [segment for segment in tail.split("/") if segment]
    if not segments:
        return VoiceRouteResolution(
            source_root=normalized_root,
            source_folder=route_source,
            source_path=relative_path,
            route_family=None,
            route_target=None,
            route_context="",
            supported=False,
            reason="missing_route_family",
        )

    family = segments[0].strip()
    if family not in KNOWN_ROUTE_FAMILIES:
        return VoiceRouteResolution(
            source_root=normalized_root,
            source_folder=route_source,
            source_path=relative_path,
            route_family=family or None,
            route_target=None,
            route_context="/".join(segments[1:]),
            supported=False,
            reason="unsupported_route_family",
        )

    if family == "kanban":
        if len(segments) < 2 or not segments[1].strip():
            return VoiceRouteResolution(
                source_root=normalized_root,
                source_folder=route_source,
                source_path=relative_path,
                route_family=family,
                route_target=None,
                route_context="/".join(segments[2:]),
                supported=False,
                reason="missing_route_target",
            )
        target = segments[1].strip()
        context = "/".join(segments[2:])
    else:
        target = None
        context = "/".join(segments[1:])

    return VoiceRouteResolution(
        source_root=normalized_root,
        source_folder=route_source,
        source_path=relative_path,
        route_family=family,
        route_target=target,
        route_context=context,
        supported=True,
        reason=None,
    )
