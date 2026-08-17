from __future__ import annotations

from typing import Any

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
            "短命令用 sandbox_exec；安装、下载、编译等长任务优先 sandbox_exec_start + sandbox_job_status。"
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
    def sandbox_exec(sandbox_id: str, command: str, timeout_seconds: int = 600, workdir: str | None = None, secret_names: list[str] | None = None, env: dict[str, str | None] | None = None, pty: bool = False) -> dict[str, Any]:
        """同步执行短命令并返回 stdout/stderr/exit code。"""
        return sandbox_exec_impl(**locals())

    @mcp.tool()
    def sandbox_exec_start(sandbox_id: str, command: str, workdir: str | None = None, secret_names: list[str] | None = None, env: dict[str, str | None] | None = None) -> dict[str, Any]:
        """在 Sandbox 中启动后台长任务；随后用 sandbox_job_status 轮询。"""
        return sandbox_exec_start_impl(**locals())

    @mcp.tool()
    def sandbox_job_status(sandbox_id: str, job_id: str) -> dict[str, Any]:
        """读取后台任务状态和当前 stdout/stderr。"""
        return sandbox_job_status_impl(sandbox_id, job_id)

    @mcp.tool()
    def sandbox_job_cancel(sandbox_id: str, job_id: str) -> dict[str, Any]:
        """取消后台任务。"""
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
    def sandbox_snapshot(sandbox_id: str, timeout_seconds: int = 55, ttl_seconds: int | None = 2592000, publish_as: str | None = None) -> dict[str, Any]:
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
    def sandbox_directory_create(sandbox_id: str, path: str, create_parents: bool = True) -> dict[str, Any]:
        """创建 Sandbox 目录。"""
        return sandbox_directory_create_impl(sandbox_id, path, create_parents)

    @mcp.tool()
    def sandbox_file_remove(sandbox_id: str, path: str, recursive: bool = False) -> dict[str, Any]:
        """删除 Sandbox 文件或目录；拒绝删除根目录。"""
        return sandbox_file_remove_impl(sandbox_id, path, recursive)

    @mcp.tool()
    def function_call(app_name: str, function_name: str, args: list[Any] | None = None, kwargs: dict[str, Any] | None = None, environment_name: str | None = None) -> Any:
        """同步调用已部署的 Modal Function。"""
        return function_call_impl(app_name, function_name, args, kwargs, environment_name)

    @mcp.tool()
    def function_spawn(app_name: str, function_name: str, args: list[Any] | None = None, kwargs: dict[str, Any] | None = None, environment_name: str | None = None) -> dict[str, Any]:
        """异步 spawn 已部署 Modal Function，并返回 FunctionCall ID。"""
        return function_spawn_impl(app_name, function_name, args, kwargs, environment_name)

    @mcp.tool()
    def function_call_get(function_call_id: str, timeout_seconds: float = 0) -> dict[str, Any]:
        """轮询或等待 Modal FunctionCall 结果。timeout_seconds=0 表示立即轮询。"""
        return function_call_get_impl(function_call_id, timeout_seconds)

    @mcp.tool()
    def function_call_cancel(function_call_id: str, terminate_containers: bool = False) -> dict[str, Any]:
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
