from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from .realtime_service import (
    sandbox_realtime_exec_cancel_impl,
    sandbox_realtime_exec_events_impl,
    sandbox_realtime_exec_input_impl,
    sandbox_realtime_exec_start_impl,
    sandbox_realtime_exec_status_impl,
)
from .repo_service import (
    repo_checkout_impl,
    repo_clone_impl,
    repo_diff_impl,
    repo_fetch_impl,
    repo_status_impl,
)
from .service import (
    app_get_impl,
    app_list_impl,
    function_call_cancel_impl,
    function_call_get_impl,
    function_call_impl,
    function_spawn_impl,
    sandbox_create_impl,
    sandbox_directory_create_impl,
    sandbox_exec_impl,
    sandbox_exec_start_impl,
    sandbox_file_list_impl,
    sandbox_file_read_impl,
    sandbox_file_remove_impl,
    sandbox_file_write_impl,
    sandbox_job_cancel_impl,
    sandbox_job_status_impl,
    sandbox_list_impl,
    sandbox_snapshot_impl,
    sandbox_status_impl,
    sandbox_terminate_impl,
)
from .workspace_service import (
    workspace_create_impl,
    workspace_exec_impl,
    workspace_get_impl,
    workspace_list_impl,
    workspace_realtime_exec_cancel_impl,
    workspace_realtime_exec_events_impl,
    workspace_realtime_exec_input_impl,
    workspace_realtime_exec_start_impl,
    workspace_realtime_exec_status_impl,
    workspace_terminate_impl,
)

router = APIRouter(prefix="/api", tags=["Modal 远程执行"])


class SandboxCreateRequest(BaseModel):
    name: str | None = None
    timeout_seconds: int = 3600
    idle_timeout_seconds: int | None = 900
    cpu: float = 2.0
    cpu_limit: float | None = 4.0
    memory_mib: int = 4096
    memory_limit_mib: int | None = 8192
    gpu: str | None = None
    cloud: str | None = None
    region: str | list[str] | None = None
    workdir: str | None = None
    image_name: str | None = None
    image_id: str | None = None
    apt_packages: list[str] | None = None
    pip_packages: list[str] | None = None
    secret_names: list[str] | None = None
    volumes: dict[str, str] | None = None
    env: dict[str, str | None] | None = None
    tags: dict[str, str] | None = None
    block_network: bool = False
    outbound_cidr_allowlist: list[str] | None = None
    outbound_domain_allowlist: list[str] | None = None
    inbound_cidr_allowlist: list[str] | None = None
    environment_name: str | None = None


class WorkspaceCreateRequest(BaseModel):
    name: str | None = None
    timeout_seconds: int = 3600
    idle_timeout_seconds: int | None = 900
    cpu: float = 2.0
    cpu_limit: float | None = 4.0
    memory_mib: int = 4096
    memory_limit_mib: int | None = 8192
    gpu: str | None = None
    cloud: str | None = None
    region: str | list[str] | None = None
    image_name: str | None = None
    image_id: str | None = None
    apt_packages: list[str] | None = None
    pip_packages: list[str] | None = None
    secret_names: list[str] | None = None
    volumes: dict[str, str] | None = None
    env: dict[str, str | None] | None = None
    tags: dict[str, str] | None = None
    block_network: bool = False
    outbound_cidr_allowlist: list[str] | None = None
    outbound_domain_allowlist: list[str] | None = None
    inbound_cidr_allowlist: list[str] | None = None
    environment_name: str | None = None


class SandboxExecRequest(BaseModel):
    command: str = Field(min_length=1, max_length=100_000)
    timeout_seconds: int = 600
    workdir: str | None = None
    secret_names: list[str] | None = None
    env: dict[str, str | None] | None = None
    pty: bool = False


class RealtimeExecStartRequest(BaseModel):
    command: str = Field(min_length=1, max_length=100_000)
    workdir: str | None = None
    secret_names: list[str] | None = None
    env: dict[str, str | None] | None = None
    pty: bool = False


class RealtimeExecInputRequest(BaseModel):
    data: str = Field(default="", max_length=100_000)
    eof: bool = False


class RealtimeExecCancelRequest(BaseModel):
    signal_name: str = "TERM"


class SandboxJobStartRequest(BaseModel):
    command: str = Field(min_length=1, max_length=100_000)
    workdir: str | None = None
    secret_names: list[str] | None = None
    env: dict[str, str | None] | None = None


class RepoCloneRequest(BaseModel):
    repository: str = Field(min_length=3, max_length=500)
    ref: str | None = None
    depth: int = 1
    destination: str | None = None
    secret_names: list[str] | None = None
    use_github_token: bool = False


class RepoFetchRequest(BaseModel):
    ref: str | None = None
    path: str | None = None
    secret_names: list[str] | None = None
    use_github_token: bool = False


class RepoCheckoutRequest(BaseModel):
    ref: str = Field(min_length=1, max_length=255)
    path: str | None = None


class SnapshotRequest(BaseModel):
    timeout_seconds: int = 55
    ttl_seconds: int | None = 30 * 24 * 3600
    publish_as: str | None = None


class FileWriteRequest(BaseModel):
    path: str
    content: str


class DirectoryCreateRequest(BaseModel):
    path: str
    create_parents: bool = True


class FileRemoveRequest(BaseModel):
    path: str
    recursive: bool = False


class FunctionCallRequest(BaseModel):
    app_name: str
    function_name: str
    args: list[Any] | None = None
    kwargs: dict[str, Any] | None = None
    environment_name: str | None = None


# ---------------------------------------------------------------------------
# Workspace-first API. GPT/Agent 新工作流应优先使用这些 operationId。
# ---------------------------------------------------------------------------


@router.post("/workspaces", operation_id="createRemoteWorkspace")
def create_workspace(body: WorkspaceCreateRequest):
    """创建实时 Remote Workspace。返回稳定 ws-* ID；内部 Sandbox ID 仅作诊断。"""
    return workspace_create_impl(**body.model_dump())


@router.get("/workspaces", operation_id="listRemoteWorkspaces")
def list_workspaces(environment_name: str | None = None):
    """列出当前在线 Remote Workspaces。"""
    return workspace_list_impl(environment_name)


@router.get("/workspaces/{workspace_id}", operation_id="getRemoteWorkspace")
def get_workspace(workspace_id: str, environment_name: str | None = None):
    """通过 ws-* 找回对应 Modal Sandbox、Repo 和运行状态。"""
    return workspace_get_impl(workspace_id, environment_name)


@router.delete("/workspaces/{workspace_id}", operation_id="terminateRemoteWorkspace")
def terminate_workspace(workspace_id: str):
    """终止 Workspace 对应的 Modal Sandbox。"""
    return workspace_terminate_impl(workspace_id)


@router.post("/workspaces/{workspace_id}/exec", operation_id="executeInRemoteWorkspace")
def execute_in_workspace(workspace_id: str, body: SandboxExecRequest):
    """在 Workspace 默认目录同步执行短命令。"""
    return workspace_exec_impl(workspace_id=workspace_id, **body.model_dump())


@router.post("/workspaces/{workspace_id}/realtime-execs", operation_id="startRealtimeWorkspaceExec")
def start_workspace_realtime_exec(workspace_id: str, body: RealtimeExecStartRequest):
    """在 Workspace 启动实时命令，立即返回 exec_id。"""
    return workspace_realtime_exec_start_impl(workspace_id=workspace_id, **body.model_dump())


@router.get(
    "/workspaces/{workspace_id}/realtime-execs/{exec_id}/events",
    operation_id="getRealtimeWorkspaceExecEvents",
)
def get_workspace_realtime_events(
    workspace_id: str,
    exec_id: str,
    cursor: int = 0,
    wait_seconds: float = 0,
    max_events: int = 100,
):
    """按 cursor 增量读取 Workspace 实时事件。"""
    return workspace_realtime_exec_events_impl(
        workspace_id,
        exec_id,
        cursor=cursor,
        wait_seconds=wait_seconds,
        max_events=max_events,
    )


@router.get(
    "/workspaces/{workspace_id}/realtime-execs/{exec_id}",
    operation_id="getRealtimeWorkspaceExecStatus",
)
def get_workspace_realtime_status(workspace_id: str, exec_id: str):
    return workspace_realtime_exec_status_impl(workspace_id, exec_id)


@router.post(
    "/workspaces/{workspace_id}/realtime-execs/{exec_id}/input",
    operation_id="sendRealtimeWorkspaceExecInput",
)
def send_workspace_realtime_input(
    workspace_id: str,
    exec_id: str,
    body: RealtimeExecInputRequest,
):
    return workspace_realtime_exec_input_impl(workspace_id, exec_id, body.data, body.eof)


@router.post(
    "/workspaces/{workspace_id}/realtime-execs/{exec_id}/cancel",
    operation_id="cancelRealtimeWorkspaceExec",
)
def cancel_workspace_realtime_exec(
    workspace_id: str,
    exec_id: str,
    body: RealtimeExecCancelRequest,
):
    return workspace_realtime_exec_cancel_impl(workspace_id, exec_id, body.signal_name)


@router.post("/workspaces/{workspace_id}/repo/clone", operation_id="cloneGitHubRepoToWorkspace")
def clone_repo_to_workspace(workspace_id: str, body: RepoCloneRequest):
    """安全构造 git clone 并实时返回 clone stderr/stdout 事件；支持公开/私有 GitHub。"""
    return repo_clone_impl(workspace_id=workspace_id, **body.model_dump())


@router.post("/workspaces/{workspace_id}/repo/fetch", operation_id="fetchWorkspaceGitRepo")
def fetch_workspace_repo(workspace_id: str, body: RepoFetchRequest):
    """实时 git fetch --progress。"""
    return repo_fetch_impl(workspace_id=workspace_id, **body.model_dump())


@router.post("/workspaces/{workspace_id}/repo/checkout", operation_id="checkoutWorkspaceGitRef")
def checkout_workspace_repo(workspace_id: str, body: RepoCheckoutRequest):
    """实时 checkout branch/tag/commit/ref。"""
    return repo_checkout_impl(workspace_id=workspace_id, **body.model_dump())


@router.get("/workspaces/{workspace_id}/repo/status", operation_id="getWorkspaceGitStatus")
def get_workspace_repo_status(workspace_id: str, path: str | None = None):
    return repo_status_impl(workspace_id, path)


@router.get("/workspaces/{workspace_id}/repo/diff", operation_id="getWorkspaceGitDiff")
def get_workspace_repo_diff(
    workspace_id: str,
    path: str | None = None,
    cached: bool = False,
    stat: bool = False,
):
    return repo_diff_impl(workspace_id, path, cached, stat)


# ---------------------------------------------------------------------------
# Raw Sandbox API kept for compatibility / low-level escape hatch.
# ---------------------------------------------------------------------------


@router.post("/sandboxes", operation_id="createModalSandbox")
def create_sandbox(body: SandboxCreateRequest):
    return sandbox_create_impl(**body.model_dump())


@router.post("/sandboxes/{sandbox_id}/exec", operation_id="executeInModalSandbox")
def execute_in_sandbox(sandbox_id: str, body: SandboxExecRequest):
    return sandbox_exec_impl(sandbox_id=sandbox_id, **body.model_dump())


@router.post("/sandboxes/{sandbox_id}/realtime-execs", operation_id="startRealtimeSandboxExec")
def start_realtime_exec(sandbox_id: str, body: RealtimeExecStartRequest):
    return sandbox_realtime_exec_start_impl(sandbox_id=sandbox_id, **body.model_dump())


@router.get(
    "/sandboxes/{sandbox_id}/realtime-execs/{exec_id}/events",
    operation_id="getRealtimeSandboxExecEvents",
)
def get_realtime_exec_events(
    sandbox_id: str,
    exec_id: str,
    cursor: int = 0,
    wait_seconds: float = 0,
    max_events: int = 100,
):
    return sandbox_realtime_exec_events_impl(
        sandbox_id,
        exec_id,
        cursor=cursor,
        wait_seconds=wait_seconds,
        max_events=max_events,
    )


@router.get(
    "/sandboxes/{sandbox_id}/realtime-execs/{exec_id}",
    operation_id="getRealtimeSandboxExecStatus",
)
def get_realtime_exec_status(sandbox_id: str, exec_id: str):
    return sandbox_realtime_exec_status_impl(sandbox_id, exec_id)


@router.post(
    "/sandboxes/{sandbox_id}/realtime-execs/{exec_id}/input",
    operation_id="sendRealtimeSandboxExecInput",
)
def send_realtime_exec_input(sandbox_id: str, exec_id: str, body: RealtimeExecInputRequest):
    return sandbox_realtime_exec_input_impl(sandbox_id, exec_id, body.data, body.eof)


@router.post(
    "/sandboxes/{sandbox_id}/realtime-execs/{exec_id}/cancel",
    operation_id="cancelRealtimeSandboxExec",
)
def cancel_realtime_exec(sandbox_id: str, exec_id: str, body: RealtimeExecCancelRequest):
    return sandbox_realtime_exec_cancel_impl(sandbox_id, exec_id, body.signal_name)


@router.post("/sandboxes/{sandbox_id}/jobs", operation_id="startModalSandboxJob")
def start_sandbox_job(sandbox_id: str, body: SandboxJobStartRequest):
    return sandbox_exec_start_impl(sandbox_id=sandbox_id, **body.model_dump())


@router.get("/sandboxes/{sandbox_id}/jobs/{job_id}", operation_id="getModalSandboxJob")
def get_sandbox_job(sandbox_id: str, job_id: str):
    return sandbox_job_status_impl(sandbox_id, job_id)


@router.delete("/sandboxes/{sandbox_id}/jobs/{job_id}", operation_id="cancelModalSandboxJob")
def cancel_sandbox_job(sandbox_id: str, job_id: str):
    return sandbox_job_cancel_impl(sandbox_id, job_id)


@router.get("/sandboxes/{sandbox_id}", operation_id="getModalSandboxStatus")
def get_sandbox_status(sandbox_id: str):
    return sandbox_status_impl(sandbox_id)


@router.get("/sandboxes", operation_id="listModalSandboxes")
def list_sandboxes(environment_name: str | None = None):
    return sandbox_list_impl(environment_name)


@router.delete("/sandboxes/{sandbox_id}", operation_id="terminateModalSandbox")
def terminate_sandbox(sandbox_id: str):
    return sandbox_terminate_impl(sandbox_id)


@router.post("/sandboxes/{sandbox_id}/snapshot", operation_id="snapshotModalSandbox")
def snapshot_sandbox(sandbox_id: str, body: SnapshotRequest):
    return sandbox_snapshot_impl(sandbox_id, **body.model_dump())


@router.get("/sandboxes/{sandbox_id}/file", operation_id="readModalSandboxFile")
def read_sandbox_file(sandbox_id: str, path: str = Query(...)):
    return sandbox_file_read_impl(sandbox_id, path)


@router.post("/sandboxes/{sandbox_id}/file", operation_id="writeModalSandboxFile")
def write_sandbox_file(sandbox_id: str, body: FileWriteRequest):
    return sandbox_file_write_impl(sandbox_id, body.path, body.content)


@router.get("/sandboxes/{sandbox_id}/files", operation_id="listModalSandboxFiles")
def list_sandbox_files(sandbox_id: str, path: str = "/"):
    return sandbox_file_list_impl(sandbox_id, path)


@router.post("/sandboxes/{sandbox_id}/directories", operation_id="createModalSandboxDirectory")
def create_sandbox_directory(sandbox_id: str, body: DirectoryCreateRequest):
    return sandbox_directory_create_impl(sandbox_id, body.path, body.create_parents)


@router.post("/sandboxes/{sandbox_id}/remove", operation_id="removeModalSandboxPath")
def remove_sandbox_path(sandbox_id: str, body: FileRemoveRequest):
    return sandbox_file_remove_impl(sandbox_id, body.path, body.recursive)


@router.post("/functions/call", operation_id="callModalFunction")
def call_function(body: FunctionCallRequest):
    return function_call_impl(**body.model_dump())


@router.post("/functions/spawn", operation_id="spawnModalFunction")
def spawn_function(body: FunctionCallRequest):
    return function_spawn_impl(**body.model_dump())


@router.get("/function-calls/{function_call_id}", operation_id="getModalFunctionCall")
def get_function_call(function_call_id: str, timeout_seconds: float = 0):
    return function_call_get_impl(function_call_id, timeout_seconds)


@router.delete("/function-calls/{function_call_id}", operation_id="cancelModalFunctionCall")
def cancel_function_call(function_call_id: str, terminate_containers: bool = False):
    return function_call_cancel_impl(function_call_id, terminate_containers)


@router.get("/apps/{app_name}", operation_id="getModalApp")
def get_app(app_name: str, environment_name: str | None = None):
    return app_get_impl(app_name, environment_name)


@router.get("/apps", operation_id="listModalApps")
def list_apps(environment_name: str | None = None):
    return app_list_impl(environment_name)
