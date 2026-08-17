"""Sandbox 内实时进程代理。

该文件会由 Gateway 写入目标 Sandbox，再由 Sandbox 内的 Python 直接执行。
它只依赖 Python 标准库，负责：
- 后台启动 bash 命令；
- 将 stdout/stderr 立即写成带递增 seq 的 JSONL 事件；
- 通过 append-only stdin 队列接收跨 HTTP 请求的输入；
- 提供 cursor 增量读取、状态查询与取消。

这是 P0 的可靠实时传输层。后续 WebSocket/Workspace Agent 复用相同事件协议。
"""

from __future__ import annotations

import argparse
import base64
import errno
import json
import os
import pathlib
import pty
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(os.getenv("MODAL_WORKSPACE_REALTIME_ROOT", "/tmp/modal-workspace-mcp/realtime"))
MAX_EVENT_DATA = 16 * 1024


def _exec_dir(exec_id: str) -> pathlib.Path:
    return ROOT / exec_id


def _atomic_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: pathlib.Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(default or {})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventWriter:
    def __init__(self, root: pathlib.Path):
        self.path = root / "events.jsonl"
        self.lock = threading.Lock()
        self.seq = 0

    def emit(self, event_type: str, data: Any = None, **extra: Any) -> int:
        with self.lock:
            self.seq += 1
            event: dict[str, Any] = {
                "seq": self.seq,
                "timestamp": _now(),
                "type": event_type,
            }
            if data is not None:
                event["data"] = data
            event.update(extra)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
                f.flush()
            return self.seq


def _write_status(root: pathlib.Path, **updates: Any) -> dict[str, Any]:
    status_path = root / "status.json"
    status = _read_json(status_path)
    status.update(updates)
    status["updated_at"] = _now()
    _atomic_json(status_path, status)
    return status


def _read_chunks(stream, emit, event_type: str) -> None:
    try:
        while True:
            if hasattr(stream, "read1"):
                chunk = stream.read1(MAX_EVENT_DATA)
            else:
                chunk = stream.read(MAX_EVENT_DATA)
            if not chunk:
                break
            emit(event_type, chunk.decode("utf-8", errors="replace"))
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _read_pty(master_fd: int, emit) -> None:
    while True:
        try:
            chunk = os.read(master_fd, MAX_EVENT_DATA)
        except OSError as exc:
            if exc.errno == errno.EIO:
                break
            raise
        if not chunk:
            break
        emit("stdout", chunk.decode("utf-8", errors="replace"))


def _stdin_pump(root: pathlib.Path, proc: subprocess.Popen[bytes], master_fd: int | None) -> None:
    queue_path = root / "stdin.jsonl"
    offset = 0
    while proc.poll() is None:
        try:
            with queue_path.open("r", encoding="utf-8") as f:
                f.seek(offset)
                while True:
                    line = f.readline()
                    if not line:
                        break
                    offset = f.tell()
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    raw = base64.b64decode(item.get("data_b64", ""))
                    if raw:
                        try:
                            if master_fd is not None:
                                os.write(master_fd, raw)
                            elif proc.stdin is not None:
                                proc.stdin.write(raw)
                                proc.stdin.flush()
                        except (BrokenPipeError, OSError):
                            return
                    if item.get("eof"):
                        try:
                            if master_fd is not None:
                                os.write(master_fd, b"\x04")
                            elif proc.stdin is not None:
                                proc.stdin.close()
                        except (BrokenPipeError, OSError):
                            pass
                        return
        except FileNotFoundError:
            pass
        time.sleep(0.05)


def _run_worker(exec_id: str, payload: dict[str, Any]) -> int:
    root = _exec_dir(exec_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / "stdin.jsonl").touch(exist_ok=True)
    events = EventWriter(root)

    command = str(payload["command"])
    workdir = payload.get("workdir") or None
    use_pty = bool(payload.get("pty", False))

    _write_status(
        root,
        exec_id=exec_id,
        state="starting",
        command=command,
        workdir=workdir,
        pty=use_pty,
        created_at=_now(),
        returncode=None,
    )
    events.emit("status", state="starting")

    master_fd: int | None = None
    slave_fd: int | None = None
    try:
        if use_pty:
            master_fd, slave_fd = pty.openpty()
            proc = subprocess.Popen(
                ["bash", "-lc", command],
                cwd=workdir,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                close_fds=True,
            )
            os.close(slave_fd)
            slave_fd = None
        else:
            proc = subprocess.Popen(
                ["bash", "-lc", command],
                cwd=workdir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                bufsize=0,
            )

        _write_status(root, state="running", pid=proc.pid, pgid=proc.pid)
        events.emit("status", state="running", pid=proc.pid)

        readers: list[threading.Thread] = []
        if use_pty:
            assert master_fd is not None
            readers.append(threading.Thread(target=_read_pty, args=(master_fd, events.emit), daemon=True))
        else:
            assert proc.stdout is not None and proc.stderr is not None
            readers.append(
                threading.Thread(target=_read_chunks, args=(proc.stdout, events.emit, "stdout"), daemon=True)
            )
            readers.append(
                threading.Thread(target=_read_chunks, args=(proc.stderr, events.emit, "stderr"), daemon=True)
            )

        for thread in readers:
            thread.start()
        input_thread = threading.Thread(
            target=_stdin_pump,
            args=(root, proc, master_fd),
            daemon=True,
        )
        input_thread.start()

        returncode = proc.wait()
        for thread in readers:
            thread.join(timeout=2)

        final_state = "cancelled" if _read_json(root / "status.json").get("cancel_requested") else "finished"
        _write_status(root, state=final_state, returncode=returncode, finished_at=_now())
        events.emit("exit", returncode=returncode, state=final_state)
        return returncode
    except Exception as exc:
        _write_status(root, state="failed", error=str(exc), returncode=255, finished_at=_now())
        events.emit("error", data=str(exc))
        events.emit("exit", returncode=255, state="failed")
        return 255
    finally:
        for fd in (master_fd, slave_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass


def _decode_payload(value: str) -> dict[str, Any]:
    return json.loads(base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8"))


def cmd_start(args: argparse.Namespace) -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    root = _exec_dir(args.exec_id)
    if root.exists():
        raise SystemExit("exec_id already exists")
    root.mkdir(parents=True)
    payload = _decode_payload(args.payload)
    encoded = args.payload
    log = (root / "agent.log").open("ab", buffering=0)
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "worker", "--exec-id", args.exec_id, "--payload", encoded],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
        close_fds=True,
    )
    print(json.dumps({"exec_id": args.exec_id, "state": "starting"}))
    return 0


def _events_after(root: pathlib.Path, cursor: int, limit: int) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    next_cursor = cursor
    try:
        with (root / "events.jsonl").open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                seq = int(item.get("seq", 0))
                if seq <= cursor:
                    continue
                events.append(item)
                next_cursor = max(next_cursor, seq)
                if len(events) >= limit:
                    break
    except FileNotFoundError:
        pass
    return events, next_cursor


def cmd_events(args: argparse.Namespace) -> int:
    root = _exec_dir(args.exec_id)
    if not root.exists():
        raise SystemExit("exec_id not found")
    deadline = time.monotonic() + max(0.0, args.wait_seconds)
    terminal_states = {"finished", "failed", "cancelled"}
    while True:
        events, next_cursor = _events_after(root, args.cursor, args.max_events)
        status = _read_json(root / "status.json", {"state": "starting"})
        if events or status.get("state") in terminal_states or time.monotonic() >= deadline:
            print(
                json.dumps(
                    {
                        "exec_id": args.exec_id,
                        "events": events,
                        "cursor": args.cursor,
                        "next_cursor": next_cursor,
                        "state": status.get("state", "unknown"),
                        "returncode": status.get("returncode"),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        time.sleep(0.1)


def cmd_status(args: argparse.Namespace) -> int:
    root = _exec_dir(args.exec_id)
    if not root.exists():
        raise SystemExit("exec_id not found")
    status = _read_json(root / "status.json", {"exec_id": args.exec_id, "state": "starting"})
    print(json.dumps(status, ensure_ascii=False))
    return 0


def cmd_input(args: argparse.Namespace) -> int:
    root = _exec_dir(args.exec_id)
    if not root.exists():
        raise SystemExit("exec_id not found")
    status = _read_json(root / "status.json")
    if status.get("state") in {"finished", "failed", "cancelled"}:
        raise SystemExit("process is not running")
    item = {"data_b64": args.data_b64 or "", "eof": bool(args.eof), "timestamp": _now()}
    with (root / "stdin.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(item) + "\n")
        f.flush()
    print(json.dumps({"exec_id": args.exec_id, "accepted": True, "eof": bool(args.eof)}))
    return 0


def cmd_cancel(args: argparse.Namespace) -> int:
    root = _exec_dir(args.exec_id)
    if not root.exists():
        raise SystemExit("exec_id not found")
    status = _read_json(root / "status.json")
    pid = status.get("pgid") or status.get("pid")
    if not pid:
        _write_status(root, cancel_requested=True)
        print(json.dumps({"exec_id": args.exec_id, "cancel_requested": True, "signal": args.signal}))
        return 0
    sig = getattr(signal, f"SIG{args.signal.upper()}", None)
    if sig is None:
        raise SystemExit("unsupported signal")
    _write_status(root, cancel_requested=True)
    try:
        os.killpg(int(pid), sig)
    except ProcessLookupError:
        pass
    print(json.dumps({"exec_id": args.exec_id, "cancel_requested": True, "signal": args.signal.upper()}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start")
    p.add_argument("--exec-id", required=True)
    p.add_argument("--payload", required=True)
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("worker")
    p.add_argument("--exec-id", required=True)
    p.add_argument("--payload", required=True)
    p.set_defaults(func=lambda a: _run_worker(a.exec_id, _decode_payload(a.payload)))

    p = sub.add_parser("events")
    p.add_argument("--exec-id", required=True)
    p.add_argument("--cursor", type=int, default=0)
    p.add_argument("--max-events", type=int, default=100)
    p.add_argument("--wait-seconds", type=float, default=0)
    p.set_defaults(func=cmd_events)

    p = sub.add_parser("status")
    p.add_argument("--exec-id", required=True)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("input")
    p.add_argument("--exec-id", required=True)
    p.add_argument("--data-b64", default="")
    p.add_argument("--eof", action="store_true")
    p.set_defaults(func=cmd_input)

    p = sub.add_parser("cancel")
    p.add_argument("--exec-id", required=True)
    p.add_argument("--signal", default="TERM")
    p.set_defaults(func=cmd_cancel)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
