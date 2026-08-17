from __future__ import annotations

import json
import subprocess
import uuid
from typing import Any

from .config import (
    DEFAULT_APT_PACKAGES,
    DEFAULT_IMAGE_NAME,
    DEFAULT_PIP_PACKAGES,
    JOB_ROOT,
    MANAGED_BY_TAG,
    MAX_FILE_CHARS,
    MAX_LIST_ENTRIES,
    MAX_OUTPUT_CHARS,
    SANDBOX_APP_NAME,
    allowed_secret_names,
    allowed_volume_names,
)
from .helpers import (
    bounded_float,
    bounded_int,
    json_safe,
    require_allowlisted,
    truncate_text,
    validate_cidrs,
    validate_domains,
    validate_image_id,
    validate_image_name,
    validate_job_id,
    validate_packages,
    validate_remote_path,
    validate_sandbox_name,
)


def _sandbox_app(environment_name: str | None = None):
    import modal

    return modal.App.lookup(
        SANDBOX_APP_NAME,
        environment_name=environment_name,
        create_if_missing=True,
    )


def _secrets(names: list[str] | None, environment_name: str | None = None):
    import modal

    names = require_allowlisted(names, allowed_secret_names(), kind="Secret")
    return [modal.Secret.from_name(name, environment_name=environment_name) for name in names]


def _volumes(volume_names: dict[str, str] | None, environment_name: str | None = None):
    import modal

    if not volume_names:
        return {}
    allowed = allowed_volume_names()
    mounts: dict[str, Any] = {}
    for raw_mount_path, volume_name in volume_names.items():
        mount_path = validate_remote_path(raw_mount_path, allow_root=False)
        require_allowlisted([volume_name], allowed, kind="Volume")
        mounts[mount_path] = modal.Volume.from_name(
            volume_name,
            environment_name=environment_name,
        )
    return mounts


def _inline_image(apt_packages: list[str] | None, pip_packages: list[str] | None):
    import modal

    apt = list(DEFAULT_APT_PACKAGES)
    apt.extend(validate_packages(apt_packages, field="apt_packages"))
    pip = list(DEFAULT_PIP_PACKAGES)
    pip.extend(validate_packages(pip_packages, field="pip_packages"))

    image = modal.Image.debian_slim(python_version="3.12").apt_install(*dict.fromkeys(apt))
    if pip:
        image = image.uv_pip_install(*dict.fromkeys(pip))
    return image


def _resolve_image(
    *,
    image_name: str | None,
    image_id: str | None,
    apt_packages: list[str] | None,
    pip_packages: list[str] | None,
):
    import modal

    image_name = validate_image_name(image_name)
    image_id = validate_image_id(image_id)
    if image_name and image_id:
        raise ValueError("image_name 与 image_id 不能同时指定")
    if (image_name or image_id) and (apt_packages or pip_packages):
        raise ValueError("使用 image_name/image_id 时不能同时请求动态 apt/pip Image 构建")
    if image_id:
        return modal.Image.from_id(image_id), "image_id"
    if image_name:
        return modal.Image.from_name(image_name), "named_image"
    if DEFAULT_IMAGE_NAME and not apt_packages and not pip_packages:
        return modal.Image.from_name(DEFAULT_IMAGE_NAME), "default_named_image"
    return _inline_image(apt_packages, pip_packages), "inline_image"


def _sandbox_handle(sandbox_id: str):
    import modal

    if not sandbox_id.startswith("sb-"):
        raise ValueError("sandbox_id 必须是以 sb- 开头的 Modal Sandbox ID")
    return modal.Sandbox.from_id(sandbox_id)


def _resource_pair(request: float | int, limit: float | int | None, *, field: str):
    if limit is None:
        return request
    if limit < request:
        raise ValueError(f"{field}_limit 不能小于 {field} request")
    return (request, limit)


def sandbox_create_impl(
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
    import modal

    name = validate_sandbox_name(name)
    timeout_seconds = bounded_int(timeout_seconds, minimum=60, maximum=86400, field="timeout_seconds")
    if idle_timeout_seconds is not None:
        idle_timeout_seconds = bounded_int(
            idle_timeout_seconds, minimum=60, maximum=86400, field="idle_timeout_seconds"
        )
    cpu = bounded_float(cpu, minimum=0.125, maximum=64, field="cpu")
    if cpu_limit is not None:
        cpu_limit = bounded_float(cpu_limit, minimum=0.125, maximum=128, field="cpu_limit")
    memory_mib = bounded_int(memory_mib, minimum=128, maximum=262144, field="memory_mib")
    if memory_limit_mib is not None:
        memory_limit_mib = bounded_int(
            memory_limit_mib, minimum=128, maximum=524288, field="memory_limit_mib"
        )
    if workdir is not None:
        workdir = validate_remote_path(workdir)

    outbound_cidr_allowlist = validate_cidrs(
        outbound_cidr_allowlist, field="outbound_cidr_allowlist"
    )
    outbound_domain_allowlist = validate_domains(outbound_domain_allowlist)
    inbound_cidr_allowlist = validate_cidrs(
        inbound_cidr_allowlist, field="inbound_cidr_allowlist"
    )
    if block_network and any(
        value is not None
        for value in (outbound_cidr_allowlist, outbound_domain_allowlist, inbound_cidr_allowlist)
    ):
        raise ValueError("block_network=True 不能与网络 allowlist 同时使用")

    image, image_mode = _resolve_image(
        image_name=image_name,
        image_id=image_id,
        apt_packages=apt_packages,
        pip_packages=pip_packages,
    )
    sandbox_tags = {"managed-by": MANAGED_BY_TAG}
    for key, value in (tags or {}).items():
        if len(key) > 100 or len(value) > 500:
            raise ValueError("tag key/value 过长")
        sandbox_tags[str(key)] = str(value)

    kwargs: dict[str, Any] = {
        "app": _sandbox_app(environment_name),
        "image": image,
        "name": name,
        "tags": sandbox_tags,
        "timeout": timeout_seconds,
        "idle_timeout": idle_timeout_seconds,
        "workdir": workdir,
        "cpu": _resource_pair(cpu, cpu_limit, field="cpu"),
        "memory": _resource_pair(memory_mib, memory_limit_mib, field="memory_mib"),
        "secrets": _secrets(secret_names, environment_name),
        "volumes": _volumes(volumes, environment_name),
        "env": env or None,
        "block_network": block_network,
        "outbound_cidr_allowlist": outbound_cidr_allowlist,
        "outbound_domain_allowlist": outbound_domain_allowlist,
        "inbound_cidr_allowlist": inbound_cidr_allowlist,
        "verbose": False,
    }
    if gpu:
        kwargs["gpu"] = gpu
    if cloud:
        kwargs["cloud"] = cloud
    if region:
        kwargs["region"] = region

    sb = modal.Sandbox.create(**kwargs)
    try:
        return {
            "sandbox_id": sb.object_id,
            "name": name,
            "app": SANDBOX_APP_NAME,
            "image_mode": image_mode,
            "image_name": image_name or (DEFAULT_IMAGE_NAME if image_mode == "default_named_image" else None),
            "image_id": image_id,
            "network": "blocked" if block_network else "enabled_or_allowlisted",
            "gpu": gpu,
            "cpu": cpu,
            "cpu_limit": cpu_limit,
            "memory_mib": memory_mib,
            "memory_limit_mib": memory_limit_mib,
            "timeout_seconds": timeout_seconds,
        }
    finally:
        sb.detach()


def sandbox_exec_impl(
    sandbox_id: str,
    command: str,
    timeout_seconds: int = 600,
    workdir: str | None = None,
    secret_names: list[str] | None = None,
    env: dict[str, str | None] | None = None,
    pty: bool = False,
) -> dict[str, Any]:
    timeout_seconds = bounded_int(timeout_seconds, minimum=1, maximum=3600, field="timeout_seconds")
    if not command.strip():
        raise ValueError("command 不能为空")
    if len(command) > 100_000:
        raise ValueError("command 过长")
    if workdir is not None:
        workdir = validate_remote_path(workdir)

    sb = _sandbox_handle(sandbox_id)
    try:
        process = sb.exec(
            "bash",
            "-lc",
            command,
            timeout=timeout_seconds,
            workdir=workdir,
            secrets=_secrets(secret_names),
            env=env or None,
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


def sandbox_exec_start_impl(
    sandbox_id: str,
    command: str,
    workdir: str | None = None,
    secret_names: list[str] | None = None,
    env: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """在 Sandbox 内启动可轮询的后台 shell job。"""
    if not command.strip() or len(command) > 100_000:
        raise ValueError("command 不能为空且长度不能超过 100000")
    if workdir is not None:
        workdir = validate_remote_path(workdir)

    job_id = uuid.uuid4().hex
    job_dir = f"{JOB_ROOT}/{job_id}"
    wrapper = """
set -eu
mkdir -p "$MW_JOB_DIR"
printf '%s' "$MW_JOB_COMMAND" > "$MW_JOB_DIR/command"
printf '%s' 'running' > "$MW_JOB_DIR/state"
(
  set +e
  if [ -n "${MW_JOB_WORKDIR:-}" ]; then
    cd "$MW_JOB_WORKDIR" || exit 200
  fi
  bash -lc "$MW_JOB_COMMAND"
  rc=$?
  printf '%s' "$rc" > "$MW_JOB_DIR/returncode"
  printf '%s' 'finished' > "$MW_JOB_DIR/state"
  exit "$rc"
) >"$MW_JOB_DIR/stdout" 2>"$MW_JOB_DIR/stderr" </dev/null &
pid=$!
printf '%s' "$pid" > "$MW_JOB_DIR/pid"
printf '%s\\n' "$pid"
""".strip()
    merged_env: dict[str, str | None] = dict(env or {})
    merged_env.update(
        {
            "MW_JOB_DIR": job_dir,
            "MW_JOB_COMMAND": command,
            "MW_JOB_WORKDIR": workdir or "",
        }
    )
    sb = _sandbox_handle(sandbox_id)
    try:
        proc = sb.exec(
            "bash",
            "-lc",
            wrapper,
            timeout=30,
            secrets=_secrets(secret_names),
            env=merged_env,
        )
        proc.wait()
        stderr = proc.stderr.read()
        if proc.returncode != 0:
            raise RuntimeError(stderr or "启动后台 job 失败")
        return {
            "sandbox_id": sandbox_id,
            "job_id": job_id,
            "pid": proc.stdout.read().strip(),
            "state": "running",
            "status_endpoint_hint": f"/api/sandboxes/{sandbox_id}/jobs/{job_id}",
        }
    finally:
        sb.detach()


def sandbox_job_status_impl(sandbox_id: str, job_id: str) -> dict[str, Any]:
    job_id = validate_job_id(job_id)
    job_dir = f"{JOB_ROOT}/{job_id}"
    script = r'''
set -eu
job="$1"
if [ ! -d "$job" ]; then exit 44; fi
state=$(cat "$job/state" 2>/dev/null || printf unknown)
pid=$(cat "$job/pid" 2>/dev/null || true)
rc=$(cat "$job/returncode" 2>/dev/null || true)
if [ "$state" = running ] && [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
  if [ -z "$rc" ]; then rc=255; printf '%s' "$rc" > "$job/returncode"; fi
  state=finished; printf '%s' "$state" > "$job/state"
fi
python - "$state" "$pid" "$rc" "$job" <<'PY2'
import json, pathlib, sys
state, pid, rc, root = sys.argv[1:]
p = pathlib.Path(root)
def read(name):
    f = p / name
    return f.read_text(errors='replace') if f.exists() else ''
print(json.dumps({"state": state, "pid": pid, "returncode": int(rc) if rc else None,
                  "stdout": read("stdout"), "stderr": read("stderr")}, ensure_ascii=False))
PY2
'''.strip()
    sb = _sandbox_handle(sandbox_id)
    try:
        p = sb.exec("bash", "-lc", script, "job-status", job_dir, timeout=30)
        p.wait()
        if p.returncode == 44:
            raise ValueError("job_id 不存在于该 Sandbox")
        if p.returncode != 0:
            raise RuntimeError(p.stderr.read() or "读取 job 状态失败")
        result = json.loads(p.stdout.read())
        result["sandbox_id"] = sandbox_id
        result["job_id"] = job_id
        result["stdout"], result["stdout_truncated"] = truncate_text(result["stdout"], MAX_OUTPUT_CHARS)
        result["stderr"], result["stderr_truncated"] = truncate_text(result["stderr"], MAX_OUTPUT_CHARS)
        return result
    finally:
        sb.detach()


def sandbox_job_cancel_impl(sandbox_id: str, job_id: str) -> dict[str, Any]:
    job_id = validate_job_id(job_id)
    job_dir = f"{JOB_ROOT}/{job_id}"
    script = r'''
set -eu
job="$1"
[ -d "$job" ] || exit 44
pid=$(cat "$job/pid" 2>/dev/null || true)
if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then kill "$pid" 2>/dev/null || true; fi
printf '%s' 'cancelled' > "$job/state"
printf '%s' '130' > "$job/returncode"
'''.strip()
    sb = _sandbox_handle(sandbox_id)
    try:
        p = sb.exec("bash", "-lc", script, "job-cancel", job_dir, timeout=15)
        p.wait()
        if p.returncode == 44:
            raise ValueError("job_id 不存在于该 Sandbox")
        if p.returncode != 0:
            raise RuntimeError(p.stderr.read() or "取消 job 失败")
        return {"sandbox_id": sandbox_id, "job_id": job_id, "cancelled": True}
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


def sandbox_list_impl(environment_name: str | None = None) -> list[dict[str, Any]]:
    import modal

    app = _sandbox_app(environment_name)
    result: list[dict[str, Any]] = []
    for sb in modal.Sandbox.list(app_id=app.app_id, tags={"managed-by": MANAGED_BY_TAG}):
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


def sandbox_snapshot_impl(
    sandbox_id: str,
    timeout_seconds: int = 55,
    ttl_seconds: int | None = 30 * 24 * 3600,
    publish_as: str | None = None,
) -> dict[str, Any]:
    timeout_seconds = bounded_int(timeout_seconds, minimum=1, maximum=3600, field="timeout_seconds")
    if ttl_seconds is not None:
        ttl_seconds = bounded_int(ttl_seconds, minimum=60, maximum=365 * 24 * 3600, field="ttl_seconds")
    publish_as = validate_image_name(publish_as)
    sb = _sandbox_handle(sandbox_id)
    try:
        image = sb.snapshot_filesystem(timeout=timeout_seconds, ttl=ttl_seconds)
        if publish_as:
            image.publish(publish_as)
        return {
            "sandbox_id": sandbox_id,
            "image_id": image.object_id,
            "ttl_seconds": ttl_seconds,
            "published_as": publish_as,
        }
    finally:
        sb.detach()


def sandbox_file_read_impl(sandbox_id: str, path: str) -> dict[str, Any]:
    path = validate_remote_path(path)
    sb = _sandbox_handle(sandbox_id)
    try:
        info = sb.filesystem.stat(path)
        if getattr(info, "size", 0) > MAX_FILE_CHARS * 4:
            raise ValueError("文件过大，拒绝直接通过 MCP/Action 读取")
        content = sb.filesystem.read_text(path)
        content, truncated = truncate_text(content, MAX_FILE_CHARS)
        return {"sandbox_id": sandbox_id, "path": path, "content": content, "truncated": truncated, "info": json_safe(info)}
    finally:
        sb.detach()


def sandbox_file_write_impl(sandbox_id: str, path: str, content: str) -> dict[str, Any]:
    path = validate_remote_path(path, allow_root=False)
    if len(content) > MAX_FILE_CHARS:
        raise ValueError(f"单次写入最多 {MAX_FILE_CHARS} 字符")
    sb = _sandbox_handle(sandbox_id)
    try:
        sb.filesystem.write_text(content, path)
        return {"sandbox_id": sandbox_id, "path": path, "written_chars": len(content)}
    finally:
        sb.detach()


def sandbox_file_list_impl(sandbox_id: str, path: str) -> dict[str, Any]:
    path = validate_remote_path(path)
    sb = _sandbox_handle(sandbox_id)
    try:
        entries = list(sb.filesystem.list_files(path))
        truncated = len(entries) > MAX_LIST_ENTRIES
        entries = entries[:MAX_LIST_ENTRIES]
        return {"sandbox_id": sandbox_id, "path": path, "entries": json_safe(entries), "truncated": truncated}
    finally:
        sb.detach()


def sandbox_directory_create_impl(sandbox_id: str, path: str, create_parents: bool = True) -> dict[str, Any]:
    path = validate_remote_path(path, allow_root=False)
    sb = _sandbox_handle(sandbox_id)
    try:
        sb.filesystem.make_directory(path, create_parents=create_parents)
        return {"sandbox_id": sandbox_id, "path": path, "created": True}
    finally:
        sb.detach()


def sandbox_file_remove_impl(sandbox_id: str, path: str, recursive: bool = False) -> dict[str, Any]:
    path = validate_remote_path(path, allow_root=False)
    sb = _sandbox_handle(sandbox_id)
    try:
        sb.filesystem.remove(path, recursive=recursive)
        return {"sandbox_id": sandbox_id, "path": path, "removed": True, "recursive": recursive}
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


def function_spawn_impl(
    app_name: str,
    function_name: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    environment_name: str | None = None,
) -> dict[str, Any]:
    import modal

    fn = modal.Function.from_name(app_name, function_name, environment_name=environment_name)
    call = fn.spawn(*(args or []), **(kwargs or {}))
    return {"function_call_id": call.object_id, "app_name": app_name, "function_name": function_name}


def function_call_get_impl(function_call_id: str, timeout_seconds: float = 0) -> dict[str, Any]:
    import modal
    from modal.exception import TimeoutError as ModalTimeoutError

    if not function_call_id.startswith("fc-"):
        raise ValueError("function_call_id 必须以 fc- 开头")
    timeout_seconds = bounded_float(timeout_seconds, minimum=0, maximum=3600, field="timeout_seconds")
    call = modal.FunctionCall.from_id(function_call_id)
    try:
        return {"function_call_id": function_call_id, "ready": True, "result": json_safe(call.get(timeout=timeout_seconds))}
    except ModalTimeoutError:
        return {"function_call_id": function_call_id, "ready": False, "result": None}


def function_call_cancel_impl(function_call_id: str, terminate_containers: bool = False) -> dict[str, Any]:
    import modal

    if not function_call_id.startswith("fc-"):
        raise ValueError("function_call_id 必须以 fc- 开头")
    call = modal.FunctionCall.from_id(function_call_id)
    call.cancel(terminate_containers=terminate_containers)
    return {"function_call_id": function_call_id, "cancelled": True}


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
        raise RuntimeError(completed.stderr.strip() or "modal app list 失败")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"无法解析 modal app list 输出：{completed.stdout[:500]}") from exc
