from __future__ import annotations

from typing import Any

from .fs_watch_service import (
    workspace_file_watch_cancel_impl,
    workspace_file_watch_events_impl,
    workspace_file_watch_list_impl,
    workspace_file_watch_start_impl,
    workspace_file_watch_status_impl,
)


def register_fs_watch_tools(mcp) -> None:
    @mcp.tool()
    def workspace_file_watch_start(
        workspace_id: str,
        path: str | None = None,
        recursive: bool = True,
        event_types: list[str] | None = None,
        timeout_seconds: int = 600,
    ) -> dict[str, Any]:
        """监听 Workspace 内文件变化，返回 fw-* 和 cursor。默认 Create/Modify/Remove。"""
        return workspace_file_watch_start_impl(**locals())

    @mcp.tool()
    def workspace_file_watch_events(
        workspace_id: str,
        watch_id: str,
        cursor: int = 0,
        wait_seconds: float = 0,
        max_events: int = 100,
    ) -> dict[str, Any]:
        """按 cursor 增量读取文件变化事件；wait_seconds 可 long-poll。"""
        return workspace_file_watch_events_impl(**locals())

    @mcp.tool()
    def workspace_file_watch_status(workspace_id: str, watch_id: str) -> dict[str, Any]:
        """读取 file watch 当前状态和 cursor 元数据。"""
        return workspace_file_watch_status_impl(workspace_id, watch_id)

    @mcp.tool()
    def workspace_file_watch_list(workspace_id: str) -> list[dict[str, Any]]:
        """列出 Workspace 最近的 file watches。"""
        return workspace_file_watch_list_impl(workspace_id)

    @mcp.tool()
    def workspace_file_watch_cancel(workspace_id: str, watch_id: str) -> dict[str, Any]:
        """取消 file watch。"""
        return workspace_file_watch_cancel_impl(workspace_id, watch_id)
