from __future__ import annotations

from typing import Any

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


def make_mcp_server():
    from fastmcp import FastMCP

    mcp = FastMCP(
        "modal-workspace-mcp",
        instructions=(
            "Use Modal for remote Linux execution, dependency installation, Git operations, "
            "GPU jobs and calls to already-deployed Modal Functions. Never print secret values."
        ),
    )

    @mcp.tool()
    def sandbox_create(name: str | None = None, timeout_seconds: int = 3600, idle_timeout_seconds: int | None = 900, cpu: float = 2.0, memory_mib: int = 4096, gpu: str | None = None, apt_packages: list[str] | None = None, pip_packages: list[str] | None = None, secret_names: list[str] | None = None, volumes: dict[str, str] | None = None, block_network: bool = False, outbound_domain_allowlist: list[str] | None = None, region: str | None = None) -> dict[str, Any]:
        """Create a detached Modal Sandbox and return its ID."""
        return sandbox_create_impl(name=name, timeout_seconds=timeout_seconds, idle_timeout_seconds=idle_timeout_seconds, cpu=cpu, memory_mib=memory_mib, gpu=gpu, apt_packages=apt_packages, pip_packages=pip_packages, secret_names=secret_names, volumes=volumes, block_network=block_network, outbound_domain_allowlist=outbound_domain_allowlist, region=region)

    @mcp.tool()
    def sandbox_exec(sandbox_id: str, command: str, timeout_seconds: int = 600, workdir: str | None = None, secret_names: list[str] | None = None, pty: bool = False) -> dict[str, Any]:
        """Execute a shell command inside an existing Modal Sandbox."""
        return sandbox_exec_impl(sandbox_id=sandbox_id, command=command, timeout_seconds=timeout_seconds, workdir=workdir, secret_names=secret_names, pty=pty)

    @mcp.tool()
    def sandbox_status(sandbox_id: str) -> dict[str, Any]:
        """Return whether a Sandbox is still running and its return code if finished."""
        return sandbox_status_impl(sandbox_id)

    @mcp.tool()
    def sandbox_list() -> list[dict[str, Any]]:
        """List Sandboxes created under the dedicated modal-workspace-mcp Sandbox App."""
        return sandbox_list_impl()

    @mcp.tool()
    def sandbox_terminate(sandbox_id: str) -> dict[str, Any]:
        """Terminate a Modal Sandbox."""
        return sandbox_terminate_impl(sandbox_id)

    @mcp.tool()
    def sandbox_snapshot(sandbox_id: str) -> dict[str, Any]:
        """Snapshot a Sandbox filesystem to a Modal Image and return the Image ID."""
        return sandbox_snapshot_impl(sandbox_id)

    @mcp.tool()
    def function_call(app_name: str, function_name: str, args: list[Any] | None = None, kwargs: dict[str, Any] | None = None, environment_name: str | None = None) -> Any:
        """Call an already-deployed Modal Function by app and function name."""
        return function_call_impl(app_name, function_name, args, kwargs, environment_name)

    @mcp.tool()
    def app_get(app_name: str, environment_name: str | None = None) -> dict[str, Any]:
        """Look up one deployed Modal App and return its ID and dashboard URL."""
        return app_get_impl(app_name, environment_name)

    @mcp.tool()
    def app_list(environment_name: str | None = None) -> list[dict[str, Any]]:
        """List Modal Apps visible to the gateway."""
        return app_list_impl(environment_name)

    return mcp
