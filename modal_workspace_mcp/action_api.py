from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .service import (
    app_get_impl,
    app_list_impl,
    function_call_impl,
    sandbox_create_impl,
    sandbox_exec_impl,
    sandbox_list_impl,
    sandbox_snapshot_impl,
    sandbox_status_impl,
    sandbox_terminate_impl,
)

router = APIRouter(prefix="/api", tags=["Modal workspace"])


class SandboxCreateRequest(BaseModel):
    name: str | None = None
    timeout_seconds: int = 3600
    idle_timeout_seconds: int | None = 900
    cpu: float = 2.0
    memory_mib: int = 4096
    gpu: str | None = None
    apt_packages: list[str] | None = None
    pip_packages: list[str] | None = None
    secret_names: list[str] | None = None
    volumes: dict[str, str] | None = None
    block_network: bool = False
    outbound_domain_allowlist: list[str] | None = None
    region: str | None = None


class SandboxExecRequest(BaseModel):
    command: str = Field(min_length=1, max_length=100_000)
    timeout_seconds: int = 600
    workdir: str | None = None
    secret_names: list[str] | None = None
    pty: bool = False


class FunctionCallRequest(BaseModel):
    app_name: str
    function_name: str
    args: list[Any] | None = None
    kwargs: dict[str, Any] | None = None
    environment_name: str | None = None


@router.post("/sandboxes", operation_id="createModalSandbox")
def create_sandbox(body: SandboxCreateRequest):
    """Create a detached Modal Sandbox for remote Linux/GPU execution."""
    return sandbox_create_impl(**body.model_dump())


@router.post("/sandboxes/{sandbox_id}/exec", operation_id="executeInModalSandbox")
def execute_in_sandbox(sandbox_id: str, body: SandboxExecRequest):
    """Run a shell command inside a Modal Sandbox and return stdout/stderr/exit code."""
    return sandbox_exec_impl(sandbox_id=sandbox_id, **body.model_dump())


@router.get("/sandboxes/{sandbox_id}", operation_id="getModalSandboxStatus")
def get_sandbox_status(sandbox_id: str):
    """Check whether a Modal Sandbox is running."""
    return sandbox_status_impl(sandbox_id)


@router.get("/sandboxes", operation_id="listModalSandboxes")
def list_sandboxes():
    """List Sandboxes managed by modal-workspace-mcp."""
    return sandbox_list_impl()


@router.delete("/sandboxes/{sandbox_id}", operation_id="terminateModalSandbox")
def terminate_sandbox(sandbox_id: str):
    """Terminate a Modal Sandbox."""
    return sandbox_terminate_impl(sandbox_id)


@router.post("/sandboxes/{sandbox_id}/snapshot", operation_id="snapshotModalSandbox")
def snapshot_sandbox(sandbox_id: str):
    """Snapshot the Sandbox filesystem to a reusable Modal Image."""
    return sandbox_snapshot_impl(sandbox_id)


@router.post("/functions/call", operation_id="callModalFunction")
def call_function(body: FunctionCallRequest):
    """Call an already-deployed Modal Function."""
    return function_call_impl(**body.model_dump())


@router.get("/apps/{app_name}", operation_id="getModalApp")
def get_app(app_name: str, environment_name: str | None = None):
    """Resolve a Modal App by name."""
    return app_get_impl(app_name, environment_name)


@router.get("/apps", operation_id="listModalApps")
def list_apps(environment_name: str | None = None):
    """List Modal Apps visible to the gateway."""
    return app_list_impl(environment_name)
