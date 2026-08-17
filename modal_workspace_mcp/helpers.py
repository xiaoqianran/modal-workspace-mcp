from __future__ import annotations

import dataclasses
import hmac
import ipaddress
import re
from collections.abc import Iterable
from datetime import date, datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

_SANDBOX_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,63}$")
_PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:@/=-]{0,199}$")
_IMAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_IMAGE_ID_RE = re.compile(r"^im-[A-Za-z0-9_-]+$")
_JOB_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_DOMAIN_RE = re.compile(
    r"^(?:\*|(?:\*\.)?(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)$"
)


def require_bearer_token(authorization: str | None, expected_token: str | None) -> bool:
    if not expected_token or not authorization:
        return False
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return False
    return hmac.compare_digest(authorization[len(prefix) :], expected_token)


def validate_sandbox_name(name: str | None) -> str | None:
    if name is None:
        return None
    if not _SANDBOX_NAME_RE.fullmatch(name):
        raise ValueError("Sandbox 名称必须为 1-63 个字符，只能包含字母、数字、.、_、-。")
    return name


def validate_packages(packages: Iterable[str] | None, *, field: str) -> list[str]:
    if not packages:
        return []
    result: list[str] = []
    for raw in packages:
        value = raw.strip()
        if not _PACKAGE_RE.fullmatch(value):
            raise ValueError(f"非法 {field} 项：{value!r}")
        result.append(value)
    if len(result) > 40:
        raise ValueError(f"{field} 最多允许 40 项")
    return result


def validate_remote_path(path: str, *, allow_root: bool = True) -> str:
    if not path or not path.startswith("/"):
        raise ValueError("远程路径必须是绝对路径")
    normalized = str(PurePosixPath(path))
    if not allow_root and normalized == "/":
        raise ValueError("拒绝对 Sandbox 根目录 / 执行该操作")
    if len(normalized) > 4096:
        raise ValueError("远程路径过长")
    return normalized


def validate_image_name(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not _IMAGE_NAME_RE.fullmatch(value):
        raise ValueError("image_name 格式非法")
    return value


def validate_image_id(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not _IMAGE_ID_RE.fullmatch(value):
        raise ValueError("image_id 必须是以 im- 开头的 Modal Image ID")
    return value


def validate_job_id(value: str) -> str:
    if not _JOB_ID_RE.fullmatch(value):
        raise ValueError("job_id 格式非法")
    return value


def validate_domains(values: Iterable[str] | None) -> list[str] | None:
    if values is None:
        return None
    result: list[str] = []
    for raw in values:
        value = raw.strip().lower()
        if not _DOMAIN_RE.fullmatch(value):
            raise ValueError(f"非法域名 allowlist 项：{raw!r}")
        result.append(value)
    if len(result) > 100:
        raise ValueError("域名 allowlist 最多允许 100 项")
    return result


def validate_cidrs(values: Iterable[str] | None, *, field: str) -> list[str] | None:
    if values is None:
        return None
    result: list[str] = []
    for raw in values:
        value = raw.strip()
        try:
            result.append(str(ipaddress.ip_network(value, strict=False)))
        except ValueError as exc:
            raise ValueError(f"非法 {field} CIDR：{raw!r}") from exc
    if len(result) > 100:
        raise ValueError(f"{field} 最多允许 100 项")
    return result


def require_allowlisted(requested: Iterable[str] | None, allowed: set[str], *, kind: str) -> list[str]:
    values = [v.strip() for v in (requested or []) if v.strip()]
    denied = sorted(set(values) - allowed)
    if denied:
        raise ValueError(f"请求的 {kind} 未加入网关 allowlist：{', '.join(denied)}")
    return values


def bounded_int(value: int, *, minimum: int, maximum: int, field: str) -> int:
    if value < minimum or value > maximum:
        raise ValueError(f"{field} 必须在 {minimum} 到 {maximum} 之间")
    return value


def bounded_float(value: float, *, minimum: float, maximum: float, field: str) -> float:
    value = float(value)
    if value < minimum or value > maximum:
        raise ValueError(f"{field} 必须在 {minimum} 到 {maximum} 之间")
    return value


def truncate_text(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    suffix = f"\n... [已截断 {len(value) - limit} 个字符]"
    return value[:limit] + suffix, True


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return json_safe(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if dataclasses.is_dataclass(value):
        return json_safe(dataclasses.asdict(value))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return json_safe(model_dump())
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if hasattr(value, "__dict__"):
        return json_safe(vars(value))
    return repr(value)
