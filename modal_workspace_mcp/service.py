from __future__ import annotations

import json
import subprocess
from typing import Any

from .config import (
    APP_NAME,
    DEFAULT_APT_PACKAGES,
    MAX_OUTPUT_CHARS,
    allowed_secret_names,
    allowed_volume_names,
)
from .helpers import (
    bounded_int,
    json_safe,
    require_allowlisted,
    truncate_text,
    validate_packages,
    validate_sandbox_name,
)


def _sandbox_app():
    import modal

    return modal.App.lookup(APP_NAME, create_if_missing=True)


def _secrets(names: list[str] | None):
    import modal

    names = require_allowlisted(names, allowed_secret_names(), kind="secret")
    return [modal.Secret.from_name(name) for name in names]


def _volumes(volume_names: dict[str, str] | None):
    import modal

    if not volume_names:
        return {}
    allowed = allowed_volume_names()
    mounts = {}
    for mount_path, volume_name in volume_names.items():
        if not mount_path.startswith("/"):
            raise ValueError(f"Volume mount path must be absolute: {mount_path}")
        require_allowlisted([volume_name], allowed, kind="volume")
        mounts[mount_path] = modal.Volume.from_name(volume_name)
    return mounts


def _make_image(apt_packages: list[str] | None, pip_packages: list[str] | None):
    import modal

    apt = list(DEFAULT_APT_PACKAGES)
    apt.extend(validate_packages(apt_packages, field="apt_packages"))
    pip = ["uv"]
    pip.extend(validate_packages(pip_packages, field="pip_packages"))

    image = modal.Image.debian_slim(python_version="3.12").apt_install(*dict.fromkeys(apt))
    if pip:
        image = image.uv_pip_install(*dict.fromkeys(pip))
    return image


def _sandbox_handle(sandbox_id: str):
    import modal

    if not sandbox_id.startswith("sb-"):
        raise ValueError("sandbox_id must be a Modal Sandbox ID beginning with 'sb-'")
    return modal.Sandbox.from_id(sandbox_id)


def sandbox_create_impl(
    name: str | None = None,
    timeout_seconds: int = 3600,
    idle_timeout_seconds: int | None = 900,
    cpu: float = 2.0,
    memory_mib: int = 4096,
    gpu: str | None = None,
    apt_packages: list[str] | None = None,
    pip_packages: list[str] | None = None,
    secret_names: list[str] | None = None,
    volumes: dict[str, str] | None = None,
    block_network: bool = False,
    outbound_domain_allowlist: list[str] | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    import modal

    name = validate_sandbox_name(name)
    timeout_seconds = bounded_int(timeout_seconds, minimum=60, maximum=86400, field="timeout_seconds")
    if idle_timeout_seconds is not None:
        idle_timeout_seconds = bounded_int(
            idle_timeout_seconds, minimum=60, maximum=86400, field="idle_timeout_seconds"
        )
    memory_mib = bounded_int(memory_mib, minimum=256, maximum=262144, field="memory_mib")
    if cpu <= 0 or cpu > 64:
        raise ValueError("cpu must be > 0 and <= 64")
    if block_network and outbound_domain_allowlist:
        raise ValueError("block_network cannot be combined with outbound_domain_allowlist")

    kwargs: dict[str, Any] = {
        "app": _sandbox_app(),
        "image": _make_image(apt_packages, pip_packages),
        "name": name,
        "tags": {"managed-by": "modal-workspace-mcp"},
        "timeout": timeout_seconds,
        "idle_timeout": idle_timeout_seconds,
        "cpu": cpu,
        "memory": memory_mib,
        "secrets": _secrets(secret_names),
        "volumes": _volumes(volumes),
        "block_network": block_network,
        "verbose": True,
    }
    if gpu:
        kwargs["gpu"] = gpu
    if outbound_domain_allowlist is not None:
        kwargs["outbound_domain_allowlist"] = outbound_domain_allowlist
    if region:
        kwargs["region"] = region

    sb = modal.Sandbox.create(**kwargs)
    result = {
        "sandbox_id": sb.object_id,
        "name": name,
        "app": APP_NAME,
        "network": "blocked" if block_network else "enabled",
        "gpu": gpu,
        "timeout_seconds": timeout_seconds,
    }
    sb.detach()
    return result


def sandbox_exec_impl(
    sandbox_id: str,
    command: str,
    timeout_seconds: int = 600,
    workdir: str | None = None,
    secret_names: list[str] | None = None,
    pty: bool = False,
) -> dict[str, Any]:
    timeout_seconds = bounded_int(timeout_seconds, minimum=1, maximum=3600, field="timeout_seconds")
    if not command.strip():
        raise ValueError("command must not be empty")
    if len(command) > 100_000:
        raise ValueError("command is too large")
    if workdir is not None and not workdir.startswith("/"):
        raise ValueError("workdir must be an absolute path")

    sb = _sandbox_handle(sandbox_id)
    try:
        process = sb.exec(
            "bash",
            "-lc",
            command,
            timeout=timeout_seconds,
            workdir=workdir,
            secrets=_secrets(secret_names),
            pty=pty,
        )
        process.wait()
        stdout = process.stdout.read()
        stderr = "" if pty else process.stderr.read()
        stdout, stdout_truncated = truncate_text(stdout, MAX_OUTPUT_CHARS)
        stderr, stderr_truncated = truncate_text(stderr, MAX_OUTPUT_CHARS)
        return {
            "sandbox_id": sandbox_id,
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
    finally:
        sb.detach()


def sandbox_status_impl(sandbox_id: str) -> dict[str, Any]:
    sb = _sandbox_handle(sandbox_id)
    try:
        returncode = sb.poll()
        return {
            "sandbox_id": sandbox_id,
            "running": returncode is None,
            "returncode": returncode,
            "tags": json_safe(sb.get_tags()),
        }
    finally:
        sb.detach()


def sandbox_list_impl() -> list[dict[str, Any]]:
    import modal

    app = _sandbox_app()
    result: list[dict[str, Any]] = []
    for sb in modal.Sandbox.list(app_id=app.app_id, tags={"managed-by": "modal-workspace-mcp"}):
        try:
            returncode = sb.poll()
            result.append(
                {
                    "sandbox_id": sb.object_id,
                    "running": returncode is None,
                    "returncode": returncode,
                    "tags": json_safe(sb.get_tags()),
                }
            )
        finally:
            sb.detach()
    return result


def sandbox_terminate_impl(sandbox_id: str) -> dict[str, Any]:
    sb = _sandbox_handle(sandbox_id)
    try:
        sb.terminate(wait=True)
        return {"sandbox_id": sandbox_id, "terminated": True, "returncode": sb.returncode}
    finally:
        sb.detach()


def sandbox_snapshot_impl(sandbox_id: str) -> dict[str, Any]:
    sb = _sandbox_handle(sandbox_id)
    try:
        image = sb.snapshot_filesystem(timeout=55)
        return {"sandbox_id": sandbox_id, "image_id": image.object_id}
    finally:
        sb.detach()


def function_call_impl(
    app_name: str,
    function_name: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    environment_name: str | None = None,
) -> Any:
    import modal

    fn = modal.Function.from_name(app_name, function_name, environment_name=environment_name)
    return json_safe(fn.remote(*(args or []), **(kwargs or {})))


def app_get_impl(app_name: str, environment_name: str | None = None) -> dict[str, Any]:
    import modal

    app = modal.App.lookup(app_name, environment_name=environment_name, create_if_missing=False)
    return {"name": app_name, "app_id": app.app_id, "dashboard_url": app.get_dashboard_url()}


def app_list_impl(environment_name: str | None = None) -> list[dict[str, Any]]:
    cmd = ["modal", "app", "list", "--json"]
    if environment_name:
        cmd.extend(["--env", environment_name])
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "modal app list failed")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected modal app list output: {completed.stdout[:500]}") from exc
