from __future__ import annotations

import base64
import json
import re
import uuid
from pathlib import Path
from typing import Any

from .helpers import bounded_float, bounded_int, validate_remote_path
from .service import _sandbox_handle, _secrets

_AGENT_REMOTE_PATH = "/tmp/modal-workspace-mcp/realtime_agent.py"
_EXEC_ID_RE = re.compile(r"^ex-[0-9a-f]{32}$")
_ALLOWED_SIGNALS = {"TERM", "INT", "HUP", "KILL"}


def _agent_source() -> str:
    return Path(__file__).with_name("realtime_agent.py").read_text(encoding="utf-8")


def _validate_exec_id(exec_id: str) -> str:
    if not _EXEC_ID_RE.fullmatch(exec_id):
        raise ValueError("exec_id 格式无效")
    return exec_id


def _run_agent(sb, *args: str, timeout: int = 30, secrets=None, env=None) -> dict[str, Any]:
    proc = sb.exec(
        "python3",
        _AGENT_REMOTE_PATH,
        *args,
        timeout=timeout,
        secrets=secrets,
        env=env or None,
    )
    proc.wait()
    stdout = proc.stdout.read()
    stderr = proc.stderr.read()
    if proc.returncode != 0:
        message = (stderr or stdout or "realtime agent command failed").strip()
        if "exec_id not found" in message:
            raise ValueError("exec_id 不存在于该 Sandbox")
        if "process is not running" in message:
            raise ValueError("目标实时进程已经结束")
        if "No such file or directory" in message and _AGENT_REMOTE_PATH in message:
            raise ValueError("该 Sandbox 尚未安装 realtime agent；请重新启动实时命令")
        raise RuntimeError(message)
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"realtime agent 返回了无效 JSON: {stdout[:1000]}") from exc


def _install_agent(sb) -> None:
    """每个 Sandbox 仅在启动首个 realtime exec 时安装 agent。

    write_text 会自动创建父目录。后续 events/input/status/cancel 直接执行已安装的 agent，
    避免在实时热路径重复 Filesystem RPC 和覆盖正在使用的脚本。
    """
    sb.filesystem.write_text(_agent_source(), _AGENT_REMOTE_PATH)


def sandbox_realtime_exec_start_impl(
    sandbox_id: str,
    command: str,
    workdir: str | None = None,
    secret_names: list[str] | None = None,
    env: dict[str, str | None] | None = None,
    pty: bool = False,
) -> dict[str, Any]:
    if not command.strip():
        raise ValueError("command 不能为空")
    if len(command) > 100_000:
        raise ValueError("command 过长")
    if workdir is not None:
        workdir = validate_remote_path(workdir)

    exec_id = f"ex-{uuid.uuid4().hex}"
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "command": command,
                "workdir": workdir,
                "pty": bool(pty),
            },
            ensure_ascii=False,
        ).encode("utf-8")
    ).decode("ascii")

    sb = _sandbox_handle(sandbox_id)
    try:
        _install_agent(sb)
        result = _run_agent(
            sb,
            "start",
            "--exec-id",
            exec_id,
            "--payload",
            payload,
            timeout=30,
            secrets=_secrets(secret_names),
            env=env,
        )
        return {
            "sandbox_id": sandbox_id,
            "exec_id": exec_id,
            "state": result.get("state", "starting"),
            "cursor": 0,
            "pty": bool(pty),
            "events_hint": f"/api/sandboxes/{sandbox_id}/realtime-execs/{exec_id}/events?cursor=0&wait_seconds=15",
        }
    finally:
        sb.detach()


def sandbox_realtime_exec_events_impl(
    sandbox_id: str,
    exec_id: str,
    cursor: int = 0,
    wait_seconds: float = 0,
    max_events: int = 100,
) -> dict[str, Any]:
    exec_id = _validate_exec_id(exec_id)
    cursor = bounded_int(cursor, minimum=0, maximum=2_147_483_647, field="cursor")
    wait_seconds = bounded_float(wait_seconds, minimum=0, maximum=20, field="wait_seconds")
    max_events = bounded_int(max_events, minimum=1, maximum=500, field="max_events")

    sb = _sandbox_handle(sandbox_id)
    try:
        result = _run_agent(
            sb,
            "events",
            "--exec-id",
            exec_id,
            "--cursor",
            str(cursor),
            "--max-events",
            str(max_events),
            "--wait-seconds",
            str(wait_seconds),
            timeout=max(30, int(wait_seconds) + 10),
        )
        result["sandbox_id"] = sandbox_id
        return result
    finally:
        sb.detach()


def sandbox_realtime_exec_status_impl(sandbox_id: str, exec_id: str) -> dict[str, Any]:
    exec_id = _validate_exec_id(exec_id)
    sb = _sandbox_handle(sandbox_id)
    try:
        result = _run_agent(sb, "status", "--exec-id", exec_id)
        result["sandbox_id"] = sandbox_id
        return result
    finally:
        sb.detach()


def sandbox_realtime_exec_input_impl(
    sandbox_id: str,
    exec_id: str,
    data: str = "",
    eof: bool = False,
) -> dict[str, Any]:
    exec_id = _validate_exec_id(exec_id)
    if len(data) > 100_000:
        raise ValueError("单次 stdin 输入不能超过 100000 字符")
    if not data and not eof:
        raise ValueError("data 与 eof 至少需要提供一个")
    data_b64 = base64.b64encode(data.encode("utf-8")).decode("ascii")

    sb = _sandbox_handle(sandbox_id)
    try:
        args = ["input", "--exec-id", exec_id, "--data-b64", data_b64]
        if eof:
            args.append("--eof")
        result = _run_agent(sb, *args)
        result["sandbox_id"] = sandbox_id
        return result
    finally:
        sb.detach()


def sandbox_realtime_exec_cancel_impl(
    sandbox_id: str,
    exec_id: str,
    signal_name: str = "TERM",
) -> dict[str, Any]:
    exec_id = _validate_exec_id(exec_id)
    signal_name = signal_name.upper().removeprefix("SIG")
    if signal_name not in _ALLOWED_SIGNALS:
        raise ValueError(f"signal_name 仅支持 {sorted(_ALLOWED_SIGNALS)}")

    sb = _sandbox_handle(sandbox_id)
    try:
        result = _run_agent(
            sb,
            "cancel",
            "--exec-id",
            exec_id,
            "--signal",
            signal_name,
        )
        result["sandbox_id"] = sandbox_id
        return result
    finally:
        sb.detach()
