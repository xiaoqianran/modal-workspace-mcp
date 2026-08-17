from __future__ import annotations

import os

APP_NAME = os.getenv("MODAL_WORKSPACE_SANDBOX_APP", "modal-workspace-sandboxes")
GATEWAY_SECRET_NAME = os.getenv("MODAL_WORKSPACE_GATEWAY_SECRET", "modal-workspace-mcp-auth")
MAX_OUTPUT_CHARS = int(os.getenv("MODAL_WORKSPACE_MAX_OUTPUT_CHARS", "120000"))

DEFAULT_APT_PACKAGES = (
    "ca-certificates",
    "curl",
    "git",
    "jq",
    "ripgrep",
    "unzip",
    "wget",
)


def _csv_env(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def allowed_secret_names() -> set[str]:
    """Modal Secret names an agent is allowed to inject into Sandboxes."""
    return _csv_env("MODAL_WORKSPACE_ALLOWED_SECRETS")


def allowed_volume_names() -> set[str]:
    """Modal Volume names an agent is allowed to mount into Sandboxes."""
    return _csv_env("MODAL_WORKSPACE_ALLOWED_VOLUMES")
