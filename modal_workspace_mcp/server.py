from typing import Any

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


def make_mcp_server():
    from fastmcp import FastMCP

    mcp = FastMCP(
        "modal-workspace-mcp",
        instructions=(
            "优先把 Modal 当作实时 Remote Workspace 使用，而不是裸 Sandbox。"
            "新任务先 workspace_create，随后使用 workspace_* 或 repo_*；用户不需要记住 sb-*。"
            "Git clone/fetch/checkout、安装、编译、实验等过程使用实时 exec，并始终把 next_cursor 作为下一次 cursor。"
            "workspace_exec 只用于很短的同步命令；sandbox_* 作为底层兼容/逃生接口。"
            "不要输出 Secret 值。私有 GitHub 只通过 allowlist 中的 Modal Secret 注入 GH_TOKEN。"
        ),
    )

    # ------------------------------------------------------------------
    # Workspace-first tools
    # ------------------------------------------------------------------

    @mcp.tool()
    def workspace_create(
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
        """创建实时 Remote Workspace，返回稳定 ws-*；内部 Sandbox ID 仅作诊断。"""
        return workspace_create_impl(**locals())

    @mcp.tool()
    def workspace_get(workspace_id: str, environment_name: str | None = None) -> dict[str, Any]:
        """查询 Workspace、对应 Sandbox、Repo 与运行状态。"""
        return workspace_get_impl(workspace_id, environment_name)

    @mcp.tool()
    def workspace_list(environment_name: str | None = None) -> list[dict[str, Any]]:
        """列出当前在线 Remote Workspaces。"""
        return workspace_list_impl(environment_name)

    @mcp.tool()
    def workspace_exec(
        workspace_id: str,
        command: str,
        timeout_seconds: int = 600,
        workdir: str | None = None,
        secret_names: list[str] | None = None,
        env: dict[str, str | None] | None = None,
        pty: bool = False,
    ) -> dict[str, Any]:
        """在 Workspace 默认目录执行很短的同步命令。"""
        return workspace_exec_impl(**locals())

    @mcp.tool()
    def workspace_realtime_exec_start(
        workspace_id: str,
        command: str,
        workdir: str | None = None,
        secret_names: list[str] | None = None,
        env: dict[str, str | None] | None = None,
        pty: bool = False,
    ) -> dict[str, Any]:
        """在 Workspace 启动实时进程并立即返回 exec_id/cursor。"""
        return workspace_realtime_exec_start_impl(**locals())

    @mcp.tool()
    def workspace_realtime_exec_events(
        workspace_id: str,
        exec_id: str,
        cursor: int = 0,
        wait_seconds: float = 0,
        max_events: int = 100,
    ) -> dict[str, Any]:
        """按 cursor 增量读取 Workspace stdout/stderr/status/exit。"""
        return workspace_realtime_exec_events_impl(**locals())

    @mcp.tool()
    def workspace_realtime_exec_status(workspace_id: str, exec_id: str) -> dict[str, Any]:
        return workspace_realtime_exec_status_impl(workspace_id, exec_id)

    @mcp.tool()
    def workspace_realtime_exec_input(
        workspace_id: str,
        exec_id: str,
        data: str = "",
        eof: bool = False,
    ) -> dict[str, Any]:
        """向 Workspace 实时进程发送 stdin。"""
        return workspace_realtime_exec_input_impl(workspace_id, exec_id, data, eof)

    @mcp.tool()
    def workspace_realtime_exec_cancel(
        workspace_id: str,
        exec_id: str,
        signal_name: str = "TERM",
    ) -> dict[str, Any]:
        return workspace_realtime_exec_cancel_impl(workspace_id, exec_id, signal_name)

    @mcp.tool()
    def workspace_terminate(workspace_id: str) -> dict[str, Any]:
        """终止 Workspace 与其底层 Sandbox。"""
        return workspace_terminate_impl(workspace_id)

    # ------------------------------------------------------------------
    # GitHub Repo tools on top of Workspace
    # ------------------------------------------------------------------

    @mcp.tool()
    def repo_clone(
        workspace_id: str,
        repository: str,
        ref: str | None = None,
        depth: int = 1,
        destination: str | None = None,
        secret_names: list[str] | None = None,
        use_github_token: bool = False,
    ) -> dict[str, Any]:
        """实时 clone GitHub Repo；repository 只接受 OWNER/REPO 或 github.com HTTPS URL。"""
        return repo_clone_impl(**locals())

    @mcp.tool()
    def repo_fetch(
        workspace_id: str,
        ref: str | None = None,
        path: str | None = None,
        secret_names: list[str] | None = None,
        use_github_token: bool = False,
    ) -> dict[str, Any]:
        """实时 git fetch --progress。"""
        return repo_fetch_impl(**locals())

    @mcp.tool()
    def repo_checkout(
        workspace_id: str,
        ref: str,
        path: str | None = None,
    ) -> dict[str, Any]:
        """实时 checkout branch/tag/commit/ref。"""
        return repo_checkout_impl(**locals())

    @mcp.tool()
    def repo_status(workspace_id: str, path: str | None = None) -> dict[str, Any]:
        """返回 HEAD、branch、remote、git status 和 clean 状态。"""
        return repo_status_impl(workspace_id, path)

    @mcp.tool()
    def repo_diff(
        workspace_id: str,
        path: str | None = None,
        cached: bool = False,
        stat: bool = False,
    ) -> dict[str, Any]:
        """读取 Workspace Git diff。"""
        return repo_diff_impl(workspace_id, path, cached, stat)

    # ------------------------------------------------------------------
    # Raw Sandbox compatibility tools
    # ------------------------------------------------------------------

    @mcp.tool()
    def sandbox_create(
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
        workdir: str | None = None,
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
        return sandbox_create_impl(**locals())

    @mcp.tool()
    def sandbox_exec(
        sandbox_id: str,
        command: str,
        timeout_seconds: int = 600,
        workdir: str | None = None,
        secret_names: list[str] | None = None,
        env: dict[str, str | None] | None = None,
        pty: bool = False,
    ) -> dict[str, Any]:
        return sandbox_exec_impl(**locals())

    @mcp.tool()
    def sandbox_realtime_exec_start(
        sandbox_id: str,
        command: str,
        workdir: str | None = None,
        secret_names: list[str] | None = None,
        env: dict[str, str | None] | None = None,
        pty: bool = False,
    ) -> dict[str, Any]:
        return sandbox_realtime_exec_start_impl(**locals())

    @mcp.tool()
    def sandbox_realtime_exec_events(
        sandbox_id: str,
        exec_id: str,
        cursor: int = 0,
        wait_seconds: float = 0,
        max_events: int = 100,
    ) -> dict[str, Any]:
        return sandbox_realtime_exec_events_impl(**locals())

    @mcp.tool()
    def sandbox_realtime_exec_status(sandbox_id: str, exec_id: str) -> dict[str, Any]:
        return sandbox_realtime_exec_status_impl(sandbox_id, exec_id)

    @mcp.tool()
    def sandbox_realtime_exec_input(
        sandbox_id: str,
        exec_id: str,
        data: str = "",
        eof: bool = False,
    ) -> dict[str, Any]:
        return sandbox_realtime_exec_input_impl(sandbox_id, exec_id, data, eof)

    @mcp.tool()
    def sandbox_realtime_exec_cancel(
        sandbox_id: str,
        exec_id: str,
        signal_name: str = "TERM",
    ) -> dict[str, Any]:
        return sandbox_realtime_exec_cancel_impl(sandbox_id, exec_id, signal_name)

    @mcp.tool()
    def sandbox_exec_start(
        sandbox_id: str,
        command: str,
        workdir: str | None = None,
        secret_names: list[str] | None = None,
        env: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        return sandbox_exec_start_impl(**locals())

    @mcp.tool()
    def sandbox_job_status(sandbox_id: str, job_id: str) -> dict[str, Any]:
        return sandbox_job_status_impl(sandbox_id, job_id)

    @mcp.tool()
    def sandbox_job_cancel(sandbox_id: str, job_id: str) -> dict[str, Any]:
        return sandbox_job_cancel_impl(sandbox_id, job_id)

    @mcp.tool()
    def sandbox_status(sandbox_id: str) -> dict[str, Any]:
        return sandbox_status_impl(sandbox_id)

    @mcp.tool()
    def sandbox_list(environment_name: str | None = None) -> list[dict[str, Any]]:
        return sandbox_list_impl(environment_name)

    @mcp.tool()
    def sandbox_terminate(sandbox_id: str) -> dict[str, Any]:
        return sandbox_terminate_impl(sandbox_id)

    @mcp.tool()
    def sandbox_snapshot(
        sandbox_id: str,
        timeout_seconds: int = 55,
        ttl_seconds: int | None = 2592000,
        publish_as: str | None = None,
    ) -> dict[str, Any]:
        return sandbox_snapshot_impl(sandbox_id, timeout_seconds, ttl_seconds, publish_as)

    @mcp.tool()
    def sandbox_file_read(sandbox_id: str, path: str) -> dict[str, Any]:
        return sandbox_file_read_impl(sandbox_id, path)

    @mcp.tool()
    def sandbox_file_write(sandbox_id: str, path: str, content: str) -> dict[str, Any]:
        return sandbox_file_write_impl(sandbox_id, path, content)

    @mcp.tool()
    def sandbox_file_list(sandbox_id: str, path: str = "/") -> dict[str, Any]:
        return sandbox_file_list_impl(sandbox_id, path)

    @mcp.tool()
    def sandbox_directory_create(
        sandbox_id: str,
        path: str,
        create_parents: bool = True,
    ) -> dict[str, Any]:
        return sandbox_directory_create_impl(sandbox_id, path, create_parents)

    @mcp.tool()
    def sandbox_file_remove(
        sandbox_id: str,
        path: str,
        recursive: bool = False,
    ) -> dict[str, Any]:
        return sandbox_file_remove_impl(sandbox_id, path, recursive)

    @mcp.tool()
    def function_call(
        app_name: str,
        function_name: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        environment_name: str | None = None,
    ) -> Any:
        return function_call_impl(app_name, function_name, args, kwargs, environment_name)

    @mcp.tool()
    def function_spawn(
        app_name: str,
        function_name: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        environment_name: str | None = None,
    ) -> dict[str, Any]:
        return function_spawn_impl(app_name, function_name, args, kwargs, environment_name)

    @mcp.tool()
    def function_call_get(function_call_id: str, timeout_seconds: float = 0) -> dict[str, Any]:
        return function_call_get_impl(function_call_id, timeout_seconds)

    @mcp.tool()
    def function_call_cancel(
        function_call_id: str,
        terminate_containers: bool = False,
    ) -> dict[str, Any]:
        return function_call_cancel_impl(function_call_id, terminate_containers)

    @mcp.tool()
    def app_get(app_name: str, environment_name: str | None = None) -> dict[str, Any]:
        return app_get_impl(app_name, environment_name)

    @mcp.tool()
    def app_list(environment_name: str | None = None) -> list[dict[str, Any]]:
        return app_list_impl(environment_name)

    return mcp
