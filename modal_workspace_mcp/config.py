from __future__ import annotations

import os

GATEWAY_APP_NAME = os.getenv("MODAL_WORKSPACE_GATEWAY_APP", "modal-workspace-mcp")
SANDBOX_APP_NAME = os.getenv("MODAL_WORKSPACE_SANDBOX_APP", "modal-workspace-sandboxes")
GATEWAY_SECRET_NAME = os.getenv("MODAL_WORKSPACE_GATEWAY_SECRET", "modal-workspace-mcp-auth")
DEFAULT_IMAGE_NAME = os.getenv("MODAL_WORKSPACE_DEFAULT_IMAGE_NAME") or None
MANAGED_BY_TAG = "modal-workspace-mcp"

MAX_OUTPUT_CHARS = int(os.getenv("MODAL_WORKSPACE_MAX_OUTPUT_CHARS", "120000"))
MAX_FILE_CHARS = int(os.getenv("MODAL_WORKSPACE_MAX_FILE_CHARS", "500000"))
MAX_LIST_ENTRIES = int(os.getenv("MODAL_WORKSPACE_MAX_LIST_ENTRIES", "500"))
JOB_ROOT = "/tmp/modal-workspace-mcp/jobs"

DEFAULT_APT_PACKAGES = (
    "ca-certificates",
    "curl",
    "git",
    "git-lfs",
    "jq",
    "openssh-client",
    "ripgrep",
    "unzip",
    "wget",
)
DEFAULT_PIP_PACKAGES = ("uv",)


def _csv_env(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def allowed_secret_names() -> set[str]:
    """允许 Agent 注入 Sandbox 的 Modal Secret 名称。"""
    return _csv_env("MODAL_WORKSPACE_ALLOWED_SECRETS")


def allowed_volume_names() -> set[str]:
    """允许 Agent 挂载到 Sandbox 的 Modal Volume 名称。"""
    return _csv_env("MODAL_WORKSPACE_ALLOWED_VOLUMES")
