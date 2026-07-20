"""Helpers for resolving API base URLs from environment values and OpenAPI server definitions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


def _expand_url_template(url: str, pod: str) -> str:
    """Expand common POD placeholders in a URL template."""
    if not url:
        return url
    return (
        url.replace("${POD}", pod)
        .replace("{POD}", pod)
        .replace("{pod}", pod)
    )


def resolve_api_base_url(
    spec_path: Optional[str | Path] = None,
    *,
    pod: Optional[str] = None,
    env_url: Optional[str] = None,
    fallback_template: Optional[str] = None,
) -> str:
    """Resolve an API base URL from the environment or the OpenAPI server definitions."""
    resolved_pod = (pod or os.getenv("POD") or "us001").strip().lower()

    if env_url:
        expanded = _expand_url_template(env_url, resolved_pod)
        if expanded.startswith("http"):
            return expanded.rstrip("/")

    if spec_path:
        spec_file = Path(spec_path)
        if spec_file.exists():
            with spec_file.open("r", encoding="utf-8") as handle:
                spec = json.load(handle)

            for server in spec.get("servers", []):
                server_url = _expand_url_template(server.get("url", ""), resolved_pod)
                if not server_url:
                    continue
                description = (server.get("description") or "").lower()
                if resolved_pod in description:
                    return server_url.rstrip("/")
                if resolved_pod in server_url.lower():
                    return server_url.rstrip("/")

    if fallback_template:
        return _expand_url_template(fallback_template, resolved_pod).rstrip("/")

    return _expand_url_template(env_url or "", resolved_pod).rstrip("/")
