from __future__ import annotations

import hmac
import re
from collections.abc import Iterable
from typing import Any

_SANDBOX_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,63}$")
_PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:@/=-]{0,199}$")


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
        raise ValueError(
            "Sandbox name must be 1-63 chars containing only letters, digits, '.', '_' or '-'."
        )
    return name


def validate_packages(packages: Iterable[str] | None, *, field: str) -> list[str]:
    if not packages:
        return []
    result: list[str] = []
    for value in packages:
        value = value.strip()
        if not _PACKAGE_RE.fullmatch(value):
            raise ValueError(f"Invalid {field} entry: {value!r}")
        result.append(value)
    if len(result) > 40:
        raise ValueError(f"{field} accepts at most 40 entries")
    return result


def require_allowlisted(requested: Iterable[str] | None, allowed: set[str], *, kind: str) -> list[str]:
    values = [v.strip() for v in (requested or []) if v.strip()]
    denied = sorted(set(values) - allowed)
    if denied:
        raise ValueError(f"Requested {kind}(s) are not allowlisted: {', '.join(denied)}")
    return values


def bounded_int(value: int, *, minimum: int, maximum: int, field: str) -> int:
    if value < minimum or value > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return value


def truncate_text(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    suffix = f"\n... [truncated {len(value) - limit} chars]"
    return value[:limit] + suffix, True


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    return repr(value)
