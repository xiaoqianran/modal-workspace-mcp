from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .fs_watch_service import (
    workspace_file_watch_cancel_impl,
    workspace_file_watch_events_impl,
    workspace_file_watch_list_impl,
    workspace_file_watch_start_impl,
    workspace_file_watch_status_impl,
)

router = APIRouter(prefix="/api", tags=["Workspace File Watch"])


class WorkspaceFileWatchStartRequest(BaseModel):
    path: str | None = None
    recursive: bool = True
    event_types: list[str] | None = None
    timeout_seconds: int = 600


@router.post(
    "/workspaces/{workspace_id}/file-watches",
    operation_id="startWorkspaceFileWatch",
)
def start_workspace_file_watch(workspace_id: str, body: WorkspaceFileWatchStartRequest):
    """启动原生 Modal filesystem.watch，并返回稳定 fw-* 与 cursor。"""
    return workspace_file_watch_start_impl(workspace_id=workspace_id, **body.model_dump())


@router.get(
    "/workspaces/{workspace_id}/file-watches",
    operation_id="listWorkspaceFileWatches",
)
def list_workspace_file_watches(workspace_id: str):
    """列出该 Workspace 最近登记的文件监听。"""
    return workspace_file_watch_list_impl(workspace_id)


@router.get(
    "/workspaces/{workspace_id}/file-watches/{watch_id}",
    operation_id="getWorkspaceFileWatchStatus",
)
def get_workspace_file_watch_status(workspace_id: str, watch_id: str):
    """读取 file watch 状态，不返回事件正文。"""
    return workspace_file_watch_status_impl(workspace_id, watch_id)


@router.get(
    "/workspaces/{workspace_id}/file-watches/{watch_id}/events",
    operation_id="getWorkspaceFileWatchEvents",
)
def get_workspace_file_watch_events(
    workspace_id: str,
    watch_id: str,
    cursor: int = 0,
    wait_seconds: float = 0,
    max_events: int = 100,
):
    """按 cursor 增量读取 Create/Modify/Remove/Access 事件，可 long-poll。"""
    return workspace_file_watch_events_impl(
        workspace_id,
        watch_id,
        cursor=cursor,
        wait_seconds=wait_seconds,
        max_events=max_events,
    )


@router.delete(
    "/workspaces/{workspace_id}/file-watches/{watch_id}",
    operation_id="cancelWorkspaceFileWatch",
)
def cancel_workspace_file_watch(workspace_id: str, watch_id: str):
    """取消独立 watcher FunctionCall。"""
    return workspace_file_watch_cancel_impl(workspace_id, watch_id)
