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


class SandboxExecRequest(BaseModel):
    command: str = Field(min_length=1, max_length=100_000)
    timeout_seconds: int = 600
    workdir: str | None = None
    secret_names: list[str] | None = None
    env: dict[str, str | None] | None = None
    pty: bool = False


class SandboxJobStartRequest(BaseModel):
    command: str = Field(min_length=1, max_length=100_000)
    workdir: str | None = None
    secret_names: list[str] | None = None
    env: dict[str, str | None] | None = None


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


@router.post("/sandboxes", operation_id="createModalSandbox")
def create_sandbox(body: SandboxCreateRequest):
    """创建 Modal Sandbox；支持 GPU、硬资源上限、Named Image、网络/Secret/Volume 策略。"""
    return sandbox_create_impl(**body.model_dump())


@router.post("/sandboxes/{sandbox_id}/exec", operation_id="executeInModalSandbox")
def execute_in_sandbox(sandbox_id: str, body: SandboxExecRequest):
    """同步运行短命令并返回 stdout/stderr/exit code。"""
    return sandbox_exec_impl(sandbox_id=sandbox_id, **body.model_dump())


@router.post("/sandboxes/{sandbox_id}/realtime-execs", operation_id="startRealtimeSandboxExec")
def start_realtime_exec(sandbox_id: str, body: RealtimeExecStartRequest):
    """启动实时命令并立即返回 exec_id；后续使用 cursor 增量读取 stdout/stderr 事件。"""
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
    """按 cursor 返回增量事件；wait_seconds>0 时进行 long-poll，新事件出现立即返回。"""
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
    """获取实时进程当前状态、PID 和 return code。"""
    return sandbox_realtime_exec_status_impl(sandbox_id, exec_id)


@router.post(
    "/sandboxes/{sandbox_id}/realtime-execs/{exec_id}/input",
    operation_id="sendRealtimeSandboxExecInput",
)
def send_realtime_exec_input(sandbox_id: str, exec_id: str, body: RealtimeExecInputRequest):
    """向仍在运行的实时进程发送 stdin；eof=true 可结束标准输入。"""
    return sandbox_realtime_exec_input_impl(sandbox_id, exec_id, body.data, body.eof)


@router.post(
    "/sandboxes/{sandbox_id}/realtime-execs/{exec_id}/cancel",
    operation_id="cancelRealtimeSandboxExec",
)
def cancel_realtime_exec(sandbox_id: str, exec_id: str, body: RealtimeExecCancelRequest):
    """向整个进程组发送 TERM/INT/HUP/KILL。"""
    return sandbox_realtime_exec_cancel_impl(sandbox_id, exec_id, body.signal_name)


@router.post("/sandboxes/{sandbox_id}/jobs", operation_id="startModalSandboxJob")
def start_sandbox_job(sandbox_id: str, body: SandboxJobStartRequest):
    """兼容旧版后台任务 API。新工作流优先使用 realtime-execs。"""
    return sandbox_exec_start_impl(sandbox_id=sandbox_id, **body.model_dump())


@router.get("/sandboxes/{sandbox_id}/jobs/{job_id}", operation_id="getModalSandboxJob")
def get_sandbox_job(sandbox_id: str, job_id: str):
    """获取旧版后台任务状态与当前日志。"""
    return sandbox_job_status_impl(sandbox_id, job_id)


@router.delete("/sandboxes/{sandbox_id}/jobs/{job_id}", operation_id="cancelModalSandboxJob")
def cancel_sandbox_job(sandbox_id: str, job_id: str):
    """取消旧版后台任务。"""
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
