from __future__ import annotations

import re
import uuid
from typing import Any

from .config import MANAGED_BY_TAG
from .helpers import json_safe
from .realtime_service import (
    sandbox_realtime_exec_cancel_impl,
    sandbox_realtime_exec_events_impl,
    sandbox_realtime_exec_input_impl,
    sandbox_realtime_exec_start_impl,
    sandbox_realtime_exec_status_impl,
)
from .service import (
    _sandbox_app,
    sandbox_create_impl,
    sandbox_exec_impl,
    sandbox_terminate_impl,
)

_WORKSPACE_ID_RE = re.compile(r"^ws-[0-9a-f]{32}$")
WORKSPACE_ROOT = "/workspace"


def validate_workspace_id(workspace_id: str) -> str:
    if not _WORKSPACE_ID_RE.fullmatch(workspace_id):
        raise ValueError("workspace_id 格式无效，必须是 ws- 加 32 位十六进制")
    return workspace_id


def _workspace_tags(workspace_id: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    tags = {
        "managed-by": MANAGED_BY_TAG,
        "workspace-id": workspace_id,
        "workspace-root": WORKSPACE_ROOT,
    }
    for key, value in (extra or {}).items():
        # sandbox_create_impl 会再次做 tag 长度检查。
        tags[str(key)] = str(value)
    return tags


def _workspace_sandbox(workspace_id: str, environment_name: str | None = None):
    """通过 Modal 原生 Sandbox tags 找回在线 Workspace 对应的 Sandbox。"""
    import modal

    workspace_id = validate_workspace_id(workspace_id)
    app = _sandbox_app(environment_name)
    matches = list(
        modal.Sandbox.list(
            app_id=app.app_id,
            tags={"managed-by": MANAGED_BY_TAG, "workspace-id": workspace_id},
        )
    )
    if not matches:
        raise ValueError(f"Workspace {workspace_id} 不存在或已离线/终止")
    if len(matches) > 1:
        for sb in matches:
            sb.detach()
        raise RuntimeError(f"Workspace {workspace_id} 映射到多个 Sandbox，状态异常")
    return matches[0]


def workspace_resolve_impl(
    workspace_id: str,
    environment_name: str | None = None,
) -> dict[str, Any]:
    sb = _workspace_sandbox(workspace_id, environment_name)
    try:
        tags = json_safe(sb.get_tags())
        returncode = sb.poll()
        return {
            "workspace_id": workspace_id,
            "sandbox_id": sb.object_id,
            "running": returncode is None,
            "returncode": returncode,
            "root": tags.get("workspace-root", WORKSPACE_ROOT),
            "repo_path": tags.get("repo-path"),
            "repo_slug": tags.get("repo-slug"),
            "repo_ref": tags.get("repo-ref"),
            "tags": tags,
        }
    finally:
        sb.detach()


def workspace_sandbox_id(
    workspace_id: str,
    environment_name: str | None = None,
) -> str:
    sb = _workspace_sandbox(workspace_id, environment_name)
    try:
        return sb.object_id
    finally:
        sb.detach()


def workspace_update_tags(
    workspace_id: str,
    updates: dict[str, str | None],
    environment_name: str | None = None,
) -> dict[str, str]:
    sb = _workspace_sandbox(workspace_id, environment_name)
    try:
        tags = dict(sb.get_tags())
        for key, value in updates.items():
            if value is None:
                tags.pop(key, None)
            else:
                tags[str(key)] = str(value)
        sb.set_tags(tags)
        return tags
    finally:
        sb.detach()


def workspace_create_impl(
    name: str | None = None,
    timeout_seconds: int = 3600,
    idle_timeout_seconds: int | None = 900,
    cpu: float = 2.0,
    cpu_limit: float | None = 4.0,
    memory_mib: int = 4096,
    memory_limit_mib: int | None = 8192,
    gpu: str | None = None,
    cloud: str | None = None,
    region: str | list[str] | None = None,
    image_name: str | None = None,
    image_id: str | None = None,
    apt_packages: list[str] | None = None,
    pip_packages: list[str] | None = None,
    secret_names: list[str] | None = None,
    volumes: dict[str, str] | None = None,
    env: dict[str, str | None] | None = None,
    tags: dict[str, str] | None = None,
    block_network: bool = False,
    outbound_cidr_allowlist: list[str] | None = None,
    outbound_domain_allowlist: list[str] | None = None,
    inbound_cidr_allowlist: list[str] | None = None,
    environment_name: str | None = None,
) -> dict[str, Any]:
    workspace_id = f"ws-{uuid.uuid4().hex}"
    sandbox_name = name or f"workspace-{workspace_id[3:15]}"
    result = sandbox_create_impl(
        name=sandbox_name,
        timeout_seconds=timeout_seconds,
        idle_timeout_seconds=idle_timeout_seconds,
        cpu=cpu,
        cpu_limit=cpu_limit,
        memory_mib=memory_mib,
        memory_limit_mib=memory_limit_mib,
        gpu=gpu,
        cloud=cloud,
        region=region,
        workdir=None,
        image_name=image_name,
        image_id=image_id,
        apt_packages=apt_packages,
        pip_packages=pip_packages,
        secret_names=secret_names,
        volumes=volumes,
        env=env,
        tags=_workspace_tags(workspace_id, tags),
        block_network=block_network,
        outbound_cidr_allowlist=outbound_cidr_allowlist,
        outbound_domain_allowlist=outbound_domain_allowlist,
        inbound_cidr_allowlist=inbound_cidr_allowlist,
        environment_name=environment_name,
    )
    sandbox_id = result["sandbox_id"]
    try:
        init = sandbox_exec_impl(
            sandbox_id=sandbox_id,
            command=f"mkdir -p {WORKSPACE_ROOT}",
            timeout_seconds=30,
        )
        if init["returncode"] != 0:
            raise RuntimeError(init["stderr"] or "初始化 Workspace 根目录失败")
    except Exception:
        try:
            sandbox_terminate_impl(sandbox_id)
        finally:
            raise

    return {
        "workspace_id": workspace_id,
        "sandbox_id": sandbox_id,
        "root": WORKSPACE_ROOT,
        "running": True,
        "gpu": gpu,
        "cpu": cpu,
        "memory_mib": memory_mib,
        "image_mode": result.get("image_mode"),
    }


def workspace_get_impl(
    workspace_id: str,
    environment_name: str | None = None,
) -> dict[str, Any]:
    return workspace_resolve_impl(workspace_id, environment_name)


def workspace_list_impl(environment_name: str | None = None) -> list[dict[str, Any]]:
    import modal

    app = _sandbox_app(environment_name)
    workspaces: list[dict[str, Any]] = []
    for sb in modal.Sandbox.list(app_id=app.app_id, tags={"managed-by": MANAGED_BY_TAG}):
        try:
            tags = json_safe(sb.get_tags())
            workspace_id = tags.get("workspace-id")
            if not workspace_id:
                continue
            returncode = sb.poll()
            workspaces.append(
                {
                    "workspace_id": workspace_id,
                    "sandbox_id": sb.object_id,
                    "running": returncode is None,
                    "returncode": returncode,
                    "root": tags.get("workspace-root", WORKSPACE_ROOT),
                    "repo_path": tags.get("repo-path"),
                    "repo_slug": tags.get("repo-slug"),
                    "repo_ref": tags.get("repo-ref"),
                }
            )
        finally:
            sb.detach()
    return workspaces


def _workspace_default_workdir(workspace_id: str) -> tuple[str, str]:
    info = workspace_resolve_impl(workspace_id)
    return info["sandbox_id"], info.get("repo_path") or info.get("root") or WORKSPACE_ROOT


def workspace_exec_impl(
    workspace_id: str,
    command: str,
    timeout_seconds: int = 600,
    workdir: str | None = None,
    secret_names: list[str] | None = None,
    env: dict[str, str | None] | None = None,
    pty: bool = False,
) -> dict[str, Any]:
    sandbox_id, default_workdir = _workspace_default_workdir(workspace_id)
    result = sandbox_exec_impl(
        sandbox_id=sandbox_id,
        command=command,
        timeout_seconds=timeout_seconds,
        workdir=workdir or default_workdir,
        secret_names=secret_names,
        env=env,
        pty=pty,
    )
    result["workspace_id"] = workspace_id
    return result


def workspace_realtime_exec_start_impl(
    workspace_id: str,
    command: str,
    workdir: str | None = None,
    secret_names: list[str] | None = None,
    env: dict[str, str | None] | None = None,
    pty: bool = False,
) -> dict[str, Any]:
    sandbox_id, default_workdir = _workspace_default_workdir(workspace_id)
    result = sandbox_realtime_exec_start_impl(
        sandbox_id=sandbox_id,
        command=command,
        workdir=workdir or default_workdir,
        secret_names=secret_names,
        env=env,
        pty=pty,
    )
    result["workspace_id"] = workspace_id
    return result


def workspace_realtime_exec_events_impl(
    workspace_id: str,
    exec_id: str,
    cursor: int = 0,
    wait_seconds: float = 0,
    max_events: int = 100,
) -> dict[str, Any]:
    sandbox_id = workspace_sandbox_id(workspace_id)
    result = sandbox_realtime_exec_events_impl(
        sandbox_id=sandbox_id,
        exec_id=exec_id,
        cursor=cursor,
        wait_seconds=wait_seconds,
        max_events=max_events,
    )
    result["workspace_id"] = workspace_id
    return result


def workspace_realtime_exec_status_impl(workspace_id: str, exec_id: str) -> dict[str, Any]:
    sandbox_id = workspace_sandbox_id(workspace_id)
    result = sandbox_realtime_exec_status_impl(sandbox_id, exec_id)
    result["workspace_id"] = workspace_id
    return result


def workspace_realtime_exec_input_impl(
    workspace_id: str,
    exec_id: str,
    data: str = "",
    eof: bool = False,
) -> dict[str, Any]:
    sandbox_id = workspace_sandbox_id(workspace_id)
    result = sandbox_realtime_exec_input_impl(sandbox_id, exec_id, data, eof)
    result["workspace_id"] = workspace_id
    return result


def workspace_realtime_exec_cancel_impl(
    workspace_id: str,
    exec_id: str,
    signal_name: str = "TERM",
) -> dict[str, Any]:
    sandbox_id = workspace_sandbox_id(workspace_id)
    result = sandbox_realtime_exec_cancel_impl(sandbox_id, exec_id, signal_name)
    result["workspace_id"] = workspace_id
    return result


def workspace_terminate_impl(workspace_id: str) -> dict[str, Any]:
    sandbox_id = workspace_sandbox_id(workspace_id)
    result = sandbox_terminate_impl(sandbox_id)
    result["workspace_id"] = workspace_id
    return result
