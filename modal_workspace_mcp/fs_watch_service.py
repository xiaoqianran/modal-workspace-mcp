from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from .config import GATEWAY_APP_NAME
from .helpers import bounded_int, validate_remote_path

FS_WATCH_DICT_NAME = "modal-workspace-fs-watch"
WORKSPACE_ROOT = "/workspace"
MAX_WATCH_EVENTS = 2048
MAX_WATCHES_PER_WORKSPACE = 64
_WATCH_ID_RE = re.compile(r"^fw-[0-9a-f]{32}$")
_ALLOWED_EVENT_TYPES = frozenset({"unknown", "access", "create", "modify", "remove"})
_TERMINAL_STATES = frozenset({"finished", "failed", "cancelled"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_watch_id(watch_id: str) -> str:
    if not _WATCH_ID_RE.fullmatch(watch_id):
        raise ValueError("watch_id 格式无效，必须是 fw- 加 32 位十六进制")
    return watch_id


def validate_watch_path(path: str) -> str:
    path = validate_remote_path(path, allow_root=False)
    root = PurePosixPath(WORKSPACE_ROOT)
    candidate = PurePosixPath(path)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"监听路径必须位于 {WORKSPACE_ROOT} 下") from exc
    return str(candidate)


def normalize_event_types(event_types: list[str] | None) -> list[str]:
    if event_types is None:
        return ["create", "modify", "remove"]
    normalized: list[str] = []
    for raw in event_types:
        value = str(raw).strip().lower()
        if not value or value not in _ALLOWED_EVENT_TYPES:
            raise ValueError("event_types 仅支持 unknown/access/create/modify/remove")
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        raise ValueError("event_types 不能为空")
    return normalized


def new_watch_state(
    *,
    watch_id: str,
    workspace_id: str,
    sandbox_id: str,
    path: str,
    recursive: bool,
    event_types: list[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    return {
        "watch_id": validate_watch_id(watch_id),
        "workspace_id": workspace_id,
        "sandbox_id": sandbox_id,
        "path": validate_watch_path(path),
        "recursive": bool(recursive),
        "event_types": normalize_event_types(event_types),
        "timeout_seconds": timeout_seconds,
        "state": "starting",
        "events": [],
        "base_cursor": 0,
        "next_cursor": 0,
        "dropped_events": 0,
        "function_call_id": None,
        "created_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "reason": None,
        "error": None,
    }


def append_watch_event(
    state: dict[str, Any],
    *,
    event_type: str,
    paths: list[str],
    timestamp: str | None = None,
) -> dict[str, Any]:
    event_type = normalize_event_types([event_type])[0]
    seq = int(state.get("next_cursor", 0))
    event = {
        "seq": seq,
        "timestamp": timestamp or utc_now(),
        "type": event_type,
        "paths": [str(path) for path in paths],
    }
    events = list(state.get("events") or [])
    events.append(event)
    state["next_cursor"] = seq + 1

    if len(events) > MAX_WATCH_EVENTS:
        dropped = len(events) - MAX_WATCH_EVENTS
        events = events[dropped:]
        state["dropped_events"] = int(state.get("dropped_events", 0)) + dropped

    state["events"] = events
    state["base_cursor"] = events[0]["seq"] if events else state["next_cursor"]
    return event


def slice_watch_events(
    state: dict[str, Any],
    *,
    cursor: int = 0,
    max_events: int = 100,
) -> dict[str, Any]:
    cursor = bounded_int(cursor, minimum=0, maximum=2**63 - 1, field="cursor")
    max_events = bounded_int(max_events, minimum=1, maximum=500, field="max_events")
    base_cursor = int(state.get("base_cursor", 0))
    current_next = int(state.get("next_cursor", 0))
    if cursor > current_next:
        raise ValueError("cursor 超过当前 next_cursor")

    cursor_expired = cursor < base_cursor
    effective_cursor = max(cursor, base_cursor)
    available = [
        event
        for event in (state.get("events") or [])
        if int(event.get("seq", -1)) >= effective_cursor
    ][:max_events]
    next_cursor = int(available[-1]["seq"]) + 1 if available else effective_cursor
    return {
        "events": available,
        "next_cursor": next_cursor,
        "base_cursor": base_cursor,
        "cursor_expired": cursor_expired,
        "has_more": next_cursor < current_next,
    }


def _watch_key(watch_id: str) -> str:
    return f"watch:{validate_watch_id(watch_id)}"


def _workspace_index_key(workspace_id: str) -> str:
    return f"workspace:{workspace_id}:watches"


def _watch_store():
    import modal

    return modal.Dict.from_name(FS_WATCH_DICT_NAME, create_if_missing=True)


def _load_watch_state(watch_id: str) -> dict[str, Any]:
    store = _watch_store()
    state = store.get(_watch_key(watch_id))
    if not isinstance(state, dict):
        raise ValueError(f"File watch {watch_id} 不存在或已过期")
    return dict(state)


def _save_watch_state(state: dict[str, Any]) -> None:
    _watch_store().put(_watch_key(state["watch_id"]), state)


def _assert_watch_workspace(state: dict[str, Any], workspace_id: str) -> None:
    if state.get("workspace_id") != workspace_id:
        raise ValueError("watch_id 不属于该 Workspace")


def filesystem_watch_worker_impl(
    sandbox_id: str,
    watch_id: str,
    path: str,
    recursive: bool,
    event_types: list[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    import modal
    from modal.types import FileWatchEventType

    watch_id = validate_watch_id(watch_id)
    path = validate_watch_path(path)
    event_types = normalize_event_types(event_types)
    timeout_seconds = bounded_int(
        timeout_seconds, minimum=1, maximum=3600, field="timeout_seconds"
    )
    store = _watch_store()
    key = _watch_key(watch_id)
    state = store.get(key)
    if not isinstance(state, dict):
        raise ValueError(f"File watch {watch_id} 初始化状态不存在")
    state = dict(state)
    state["state"] = "running"
    state["started_at"] = utc_now()
    store.put(key, state)

    filter_values = [
        getattr(FileWatchEventType, event_type.capitalize()) for event_type in event_types
    ]
    sb = modal.Sandbox.from_id(sandbox_id)
    try:
        for event in sb.filesystem.watch(
            path,
            recursive=bool(recursive),
            filter=filter_values,
            timeout=timeout_seconds,
        ):
            latest = store.get(key)
            if isinstance(latest, dict):
                state = dict(latest)
            if state.get("state") == "cancelled":
                break
            append_watch_event(
                state,
                event_type=event.type.name.lower(),
                paths=list(event.paths),
            )
            store.put(key, state)

        latest = store.get(key)
        if isinstance(latest, dict):
            state = dict(latest)
        if state.get("state") not in _TERMINAL_STATES:
            state["state"] = "finished"
            state["reason"] = "watch_timeout_or_stream_closed"
            state["finished_at"] = utc_now()
            store.put(key, state)
        return {
            "watch_id": watch_id,
            "state": state.get("state"),
            "next_cursor": state.get("next_cursor", 0),
        }
    except Exception as exc:
        latest = store.get(key)
        if isinstance(latest, dict):
            state = dict(latest)
        state["state"] = "failed"
        state["error"] = str(exc)[:4000]
        state["finished_at"] = utc_now()
        store.put(key, state)
        raise
    finally:
        sb.detach()


def workspace_file_watch_start_impl(
    workspace_id: str,
    path: str | None = None,
    recursive: bool = True,
    event_types: list[str] | None = None,
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    import modal

    from .workspace_service import workspace_resolve_impl

    timeout_seconds = bounded_int(
        timeout_seconds, minimum=1, maximum=3600, field="timeout_seconds"
    )
    info = workspace_resolve_impl(workspace_id)
    watch_path = validate_watch_path(
        path or info.get("repo_path") or info.get("root") or WORKSPACE_ROOT
    )
    normalized_types = normalize_event_types(event_types)
    watch_id = f"fw-{uuid.uuid4().hex}"
    state = new_watch_state(
        watch_id=watch_id,
        workspace_id=workspace_id,
        sandbox_id=info["sandbox_id"],
        path=watch_path,
        recursive=recursive,
        event_types=normalized_types,
        timeout_seconds=timeout_seconds,
    )
    store = _watch_store()
    store.put(_watch_key(watch_id), state)

    index_key = _workspace_index_key(workspace_id)
    index = list(store.get(index_key, []) or [])
    index = [value for value in index if isinstance(value, str)]
    if len(index) >= MAX_WATCHES_PER_WORKSPACE:
        raise ValueError("该 Workspace 的 file watch 数量已达到上限")
    index.append(watch_id)
    store.put(index_key, index)

    try:
        worker = modal.Function.from_name(GATEWAY_APP_NAME, "filesystem_watch_worker")
        call = worker.spawn(
            info["sandbox_id"],
            watch_id,
            watch_path,
            bool(recursive),
            normalized_types,
            timeout_seconds,
        )
        latest = store.get(_watch_key(watch_id))
        if isinstance(latest, dict):
            state = dict(latest)
        state["function_call_id"] = call.object_id
        store.put(_watch_key(watch_id), state)
    except Exception as exc:
        state["state"] = "failed"
        state["error"] = str(exc)[:4000]
        state["finished_at"] = utc_now()
        store.put(_watch_key(watch_id), state)
        raise

    return {
        "workspace_id": workspace_id,
        "sandbox_id": info["sandbox_id"],
        "watch_id": watch_id,
        "path": watch_path,
        "recursive": bool(recursive),
        "event_types": normalized_types,
        "state": state.get("state", "starting"),
        "cursor": 0,
        "status_endpoint_hint": f"/api/workspaces/{workspace_id}/file-watches/{watch_id}",
        "events_endpoint_hint": f"/api/workspaces/{workspace_id}/file-watches/{watch_id}/events",
    }


def workspace_file_watch_events_impl(
    workspace_id: str,
    watch_id: str,
    cursor: int = 0,
    wait_seconds: float = 0,
    max_events: int = 100,
) -> dict[str, Any]:
    wait_seconds = max(0.0, min(float(wait_seconds), 20.0))
    deadline = time.monotonic() + wait_seconds
    while True:
        state = _load_watch_state(watch_id)
        _assert_watch_workspace(state, workspace_id)
        batch = slice_watch_events(state, cursor=cursor, max_events=max_events)
        if batch["events"] or state.get("state") in _TERMINAL_STATES:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(0.2)

    return {
        "workspace_id": workspace_id,
        "watch_id": watch_id,
        "path": state.get("path"),
        "state": state.get("state"),
        "error": state.get("error"),
        "dropped_events": int(state.get("dropped_events", 0)),
        **batch,
    }


def workspace_file_watch_status_impl(
    workspace_id: str,
    watch_id: str,
) -> dict[str, Any]:
    state = _load_watch_state(watch_id)
    _assert_watch_workspace(state, workspace_id)
    return {key: value for key, value in state.items() if key != "events"}


def workspace_file_watch_list_impl(workspace_id: str) -> list[dict[str, Any]]:
    store = _watch_store()
    watch_ids = list(store.get(_workspace_index_key(workspace_id), []) or [])
    result: list[dict[str, Any]] = []
    for watch_id in watch_ids[-MAX_WATCHES_PER_WORKSPACE:]:
        try:
            state = _load_watch_state(watch_id)
        except ValueError:
            continue
        if state.get("workspace_id") != workspace_id:
            continue
        result.append({key: value for key, value in state.items() if key != "events"})
    return result


def workspace_file_watch_cancel_impl(
    workspace_id: str,
    watch_id: str,
) -> dict[str, Any]:
    import modal

    state = _load_watch_state(watch_id)
    _assert_watch_workspace(state, workspace_id)
    if state.get("state") in _TERMINAL_STATES:
        return {
            "workspace_id": workspace_id,
            "watch_id": watch_id,
            "cancelled": state.get("state") == "cancelled",
            "state": state.get("state"),
        }

    call_id = state.get("function_call_id")
    if call_id:
        try:
            modal.FunctionCall.from_id(call_id).cancel(terminate_containers=True)
        except Exception:
            pass
    state["state"] = "cancelled"
    state["reason"] = "cancelled_by_client"
    state["finished_at"] = utc_now()
    _save_watch_state(state)
    return {
        "workspace_id": workspace_id,
        "watch_id": watch_id,
        "cancelled": True,
        "state": "cancelled",
    }


def workspace_file_watch_cancel_all_impl(workspace_id: str) -> dict[str, Any]:
    cancelled: list[str] = []
    for item in workspace_file_watch_list_impl(workspace_id):
        watch_id = item.get("watch_id")
        if not watch_id or item.get("state") in _TERMINAL_STATES:
            continue
        workspace_file_watch_cancel_impl(workspace_id, watch_id)
        cancelled.append(watch_id)
    return {"workspace_id": workspace_id, "cancelled_watch_ids": cancelled}
