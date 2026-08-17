from typing import Any

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


def make_mcp_server():
    from fastmcp import FastMCP

    mcp = FastMCP(
        "modal-workspace-mcp",
        instructions=(
            "当本地执行环境缺少网络、系统依赖、GPU 或长期计算能力时，使用这些工具把任务交给用户的 Modal。"
            "需要观察安装、下载、编译、Git 或实验的实时进度时，优先使用 sandbox_realtime_exec_start，"
            "随后用 sandbox_realtime_exec_events 按 cursor 获取增量事件；需要交互时用 sandbox_realtime_exec_input。"
            "sandbox_exec 只用于很短的同步命令；旧 sandbox_exec_start/job_status 仅保留兼容。"
            "不要输出 Secret 值；只请求已经加入 allowlist 的 Secret 名称。"
        ),
    )

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
        """创建一个 Modal Sandbox。支持硬资源上限、GPU、Named Image/Image ID、网络策略、Secret/Volume。"""
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
        """同步执行很短的命令并返回 stdout/stderr/exit code。长命令优先 realtime exec。"""
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
        """立即启动实时命令并返回 exec_id/cursor；命令无需结束即可读取增量输出。"""
        return sandbox_realtime_exec_start_impl(**locals())

    @mcp.tool()
    def sandbox_realtime_exec_events(
        sandbox_id: str,
        exec_id: str,
        cursor: int = 0,
        wait_seconds: float = 0,
        max_events: int = 100,
    ) -> dict[str, Any]:
        """按 cursor 增量读取 stdout/stderr/status/exit 事件；wait_seconds 可做 long-poll。"""
        return sandbox_realtime_exec_events_impl(**locals())

    @mcp.tool()
    def sandbox_realtime_exec_status(sandbox_id: str, exec_id: str) -> dict[str, Any]:
        """获取实时进程状态、PID 和 return code。"""
        return sandbox_realtime_exec_status_impl(sandbox_id, exec_id)

    @mcp.tool()
    def sandbox_realtime_exec_input(
        sandbox_id: str,
        exec_id: str,
        data: str = "",
        eof: bool = False,
    ) -> dict[str, Any]:
        """向实时进程 stdin 发送文本；eof=true 结束标准输入。"""
        return sandbox_realtime_exec_input_impl(sandbox_id, exec_id, data, eof)

    @mcp.tool()
    def sandbox_realtime_exec_cancel(
        sandbox_id: str,
        exec_id: str,
        signal_name: str = "TERM",
    ) -> dict[str, Any]:
        """取消实时进程；支持 TERM/INT/HUP/KILL。"""
        return sandbox_realtime_exec_cancel_impl(sandbox_id, exec_id, signal_name)

    @mcp.tool()
    def sandbox_exec_start(
        sandbox_id: str,
        command: str,
        workdir: str | None = None,
        secret_names: list[str] | None = None,
        env: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        """旧版后台任务 API；新任务优先使用 sandbox_realtime_exec_start。"""
        return sandbox_exec_start_impl(**locals())

    @mcp.tool()
    def sandbox_job_status(sandbox_id: str, job_id: str) -> dict[str, Any]:
        """读取旧版后台任务状态和当前 stdout/stderr。"""
        return sandbox_job_status_impl(sandbox_id, job_id)

    @mcp.tool()
    def sandbox_job_cancel(sandbox_id: str, job_id: str) -> dict[str, Any]:
        """取消旧版后台任务。"""
        return sandbox_job_cancel_impl(sandbox_id, job_id)

    @mcp.tool()
    def sandbox_status(sandbox_id: str) -> dict[str, Any]:
        """查询 Sandbox 是否仍在运行。"""
        return sandbox_status_impl(sandbox_id)

    @mcp.tool()
    def sandbox_list(environment_name: str | None = None) -> list[dict[str, Any]]:
        """列出该桥接器管理的 Sandbox。"""
        return sandbox_list_impl(environment_name)

    @mcp.tool()
    def sandbox_terminate(sandbox_id: str) -> dict[str, Any]:
        """终止 Sandbox。"""
        return sandbox_terminate_impl(sandbox_id)

    @mcp.tool()
    def sandbox_snapshot(
        sandbox_id: str,
        timeout_seconds: int = 55,
        ttl_seconds: int | None = 2592000,
        publish_as: str | None = None,
    ) -> dict[str, Any]:
        """将 Sandbox 文件系统快照为 Modal Image，可选发布成 Named Image。"""
        return sandbox_snapshot_impl(sandbox_id, timeout_seconds, ttl_seconds, publish_as)

    @mcp.tool()
    def sandbox_file_read(sandbox_id: str, path: str) -> dict[str, Any]:
        """通过 Modal Sandbox Filesystem API 读取 UTF-8 文本文件。"""
        return sandbox_file_read_impl(sandbox_id, path)

    @mcp.tool()
    def sandbox_file_write(sandbox_id: str, path: str, content: str) -> dict[str, Any]:
        """写入 UTF-8 文本文件。"""
        return sandbox_file_write_impl(sandbox_id, path, content)

    @mcp.tool()
    def sandbox_file_list(sandbox_id: str, path: str = "/") -> dict[str, Any]:
        """列出 Sandbox 目录。"""
        return sandbox_file_list_impl(sandbox_id, path)

    @mcp.tool()
    def sandbox_directory_create(
        sandbox_id: str,
        path: str,
        create_parents: bool = True,
    ) -> dict[str, Any]:
        """创建 Sandbox 目录。"""
        return sandbox_directory_create_impl(sandbox_id, path, create_parents)

    @mcp.tool()
    def sandbox_file_remove(
        sandbox_id: str,
        path: str,
        recursive: bool = False,
    ) -> dict[str, Any]:
        """删除 Sandbox 文件或目录；拒绝删除根目录。"""
        return sandbox_file_remove_impl(sandbox_id, path, recursive)

    @mcp.tool()
    def function_call(
        app_name: str,
        function_name: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        environment_name: str | None = None,
    ) -> Any:
        """同步调用已部署的 Modal Function。"""
        return function_call_impl(app_name, function_name, args, kwargs, environment_name)

    @mcp.tool()
    def function_spawn(
        app_name: str,
        function_name: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        environment_name: str | None = None,
    ) -> dict[str, Any]:
        """异步 spawn 已部署 Modal Function，并返回 FunctionCall ID。"""
        return function_spawn_impl(app_name, function_name, args, kwargs, environment_name)

    @mcp.tool()
    def function_call_get(function_call_id: str, timeout_seconds: float = 0) -> dict[str, Any]:
        """轮询或等待 Modal FunctionCall 结果。timeout_seconds=0 表示立即轮询。"""
        return function_call_get_impl(function_call_id, timeout_seconds)

    @mcp.tool()
    def function_call_cancel(
        function_call_id: str,
        terminate_containers: bool = False,
    ) -> dict[str, Any]:
        """取消 Modal FunctionCall。"""
        return function_call_cancel_impl(function_call_id, terminate_containers)

    @mcp.tool()
    def app_get(app_name: str, environment_name: str | None = None) -> dict[str, Any]:
        """按名称查询 Modal App。"""
        return app_get_impl(app_name, environment_name)

    @mcp.tool()
    def app_list(environment_name: str | None = None) -> list[dict[str, Any]]:
        """列出网关可见的 Modal Apps。"""
        return app_list_impl(environment_name)

    return mcp
