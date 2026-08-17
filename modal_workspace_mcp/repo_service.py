from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from .helpers import bounded_int, validate_remote_path
from .workspace_service import (
    WORKSPACE_ROOT,
    workspace_exec_impl,
    workspace_realtime_exec_start_impl,
    workspace_resolve_impl,
    workspace_update_tags,
)

_GITHUB_PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_GIT_REF_RE = re.compile(r"^[A-Za-z0-9._/@+-]+$")


def normalize_github_repository(repository: str) -> tuple[str, str]:
    """返回 (owner/repo, https clone URL)，仅允许 github.com HTTPS 或 owner/repo。"""
    value = repository.strip()
    if not value:
        raise ValueError("repository 不能为空")

    if value.startswith("https://"):
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password:
            raise ValueError("P2 仅允许 https://github.com/OWNER/REPO GitHub 地址")
        if parsed.query or parsed.fragment:
            raise ValueError("GitHub repository URL 不能包含 query/fragment")
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        parts = path.split("/")
        if len(parts) != 2:
            raise ValueError("GitHub URL 必须精确指向 OWNER/REPO")
        owner, repo = parts
    else:
        value = value.removesuffix(".git").strip("/")
        parts = value.split("/")
        if len(parts) != 2:
            raise ValueError("repository 必须是 OWNER/REPO 或 github.com HTTPS URL")
        owner, repo = parts

    if not owner or not repo or not _GITHUB_PART_RE.fullmatch(owner) or not _GITHUB_PART_RE.fullmatch(repo):
        raise ValueError("GitHub owner/repo 包含不允许的字符")
    if owner.startswith("-") or repo.startswith("-"):
        raise ValueError("GitHub owner/repo 不能以 - 开头")

    slug = f"{owner}/{repo}"
    return slug, f"https://github.com/{slug}.git"


def validate_git_ref(ref: str | None) -> str | None:
    if ref is None:
        return None
    ref = ref.strip()
    if not ref:
        return None
    if len(ref) > 255 or ref.startswith("-") or not _GIT_REF_RE.fullmatch(ref):
        raise ValueError("Git ref 格式无效")
    if ".." in ref or "@{" in ref or ref.endswith(".") or ref.endswith("/"):
        raise ValueError("Git ref 包含不安全/无效序列")
    if ref.startswith("/") or "//" in ref or ref.endswith(".lock"):
        raise ValueError("Git ref 包含不安全/无效序列")
    return ref


def validate_repo_path(path: str | None) -> str:
    path = path or f"{WORKSPACE_ROOT}/repo"
    path = validate_remote_path(path, allow_root=False)
    root = PurePosixPath(WORKSPACE_ROOT)
    candidate = PurePosixPath(path)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Repo 路径必须位于 {WORKSPACE_ROOT} 下") from exc
    if candidate == root:
        raise ValueError("Repo 不能直接覆盖 Workspace 根目录")
    return str(candidate)


def _git_auth_prefix(use_github_token: bool) -> str:
    if not use_github_token:
        return ""
    # Secret 只通过环境变量 GH_TOKEN 注入；命令和事件中不会包含 token 值。
    return r'''
if [ -z "${GH_TOKEN:-}" ]; then
  echo 'GH_TOKEN is required but was not injected' >&2
  exit 78
fi
mw_askpass="$(mktemp)"
cleanup_askpass() { rm -f "$mw_askpass"; }
trap cleanup_askpass EXIT
cat >"$mw_askpass" <<'MWASKPASS'
#!/bin/sh
case "$1" in
  *Username*) printf '%s\n' 'x-access-token' ;;
  *) printf '%s\n' "$GH_TOKEN" ;;
esac
MWASKPASS
chmod 700 "$mw_askpass"
export GIT_ASKPASS="$mw_askpass"
export GIT_TERMINAL_PROMPT=0
'''.strip()


def repo_clone_impl(
    workspace_id: str,
    repository: str,
    ref: str | None = None,
    depth: int = 1,
    destination: str | None = None,
    secret_names: list[str] | None = None,
    use_github_token: bool = False,
) -> dict[str, Any]:
    slug, clone_url = normalize_github_repository(repository)
    ref = validate_git_ref(ref)
    depth = bounded_int(depth, minimum=1, maximum=10000, field="depth")
    destination = validate_repo_path(destination)
    parent = str(PurePosixPath(destination).parent)

    args = ["git", "clone", "--progress", "--depth", str(depth)]
    if ref:
        # clone 阶段的 ref 明确限定为 branch/tag；任意 commit SHA 可随后 repo_checkout。
        args.extend(["--branch", ref, "--single-branch"])
    args.extend([clone_url, destination])
    clone_cmd = " ".join(shlex.quote(part) for part in args)

    command = "\n".join(
        part
        for part in (
            "set -euo pipefail",
            _git_auth_prefix(use_github_token),
            f"mkdir -p {shlex.quote(parent)}",
            f"if [ -e {shlex.quote(destination)} ]; then echo 'destination already exists' >&2; exit 73; fi",
            clone_cmd,
            f"git -C {shlex.quote(destination)} rev-parse HEAD",
            f"git -C {shlex.quote(destination)} status --short --branch",
        )
        if part
    )

    # 这里记录的是“目标 Repo”。clone 是否成功由实时 exec 的 exit 事件决定。
    # 后续 repo_status 会校验目录和 Git 元数据，因此失败 clone 不会被误报为 ready。
    workspace_update_tags(
        workspace_id,
        {
            "repo-slug": slug,
            "repo-path": destination,
            "repo-ref": ref or "HEAD",
        },
    )
    result = workspace_realtime_exec_start_impl(
        workspace_id=workspace_id,
        command=command,
        workdir=WORKSPACE_ROOT,
        secret_names=secret_names,
        pty=False,
    )
    result.update(
        {
            "operation": "repo_clone",
            "repo_slug": slug,
            "repo_url": clone_url,
            "repo_path": destination,
            "requested_ref": ref,
            "depth": depth,
            "authenticated": bool(use_github_token),
        }
    )
    return result


def _repo_path_for_workspace(workspace_id: str, path: str | None = None) -> str:
    if path:
        return validate_repo_path(path)
    info = workspace_resolve_impl(workspace_id)
    repo_path = info.get("repo_path")
    if not repo_path:
        raise ValueError("该 Workspace 尚未记录 Repo；请先 repo_clone 或显式传 path")
    return validate_repo_path(repo_path)


def repo_fetch_impl(
    workspace_id: str,
    ref: str | None = None,
    path: str | None = None,
    secret_names: list[str] | None = None,
    use_github_token: bool = False,
) -> dict[str, Any]:
    ref = validate_git_ref(ref)
    repo_path = _repo_path_for_workspace(workspace_id, path)
    args = ["git", "-C", repo_path, "fetch", "--progress", "--prune", "origin"]
    if ref:
        args.append(ref)
    fetch_cmd = " ".join(shlex.quote(part) for part in args)
    command = "\n".join(
        part for part in ("set -euo pipefail", _git_auth_prefix(use_github_token), fetch_cmd) if part
    )
    result = workspace_realtime_exec_start_impl(
        workspace_id,
        command,
        workdir=repo_path,
        secret_names=secret_names,
    )
    result.update({"operation": "repo_fetch", "repo_path": repo_path, "ref": ref})
    return result


def repo_checkout_impl(
    workspace_id: str,
    ref: str,
    path: str | None = None,
) -> dict[str, Any]:
    ref = validate_git_ref(ref)
    if not ref:
        raise ValueError("ref 不能为空")
    repo_path = _repo_path_for_workspace(workspace_id, path)
    command = " ".join(
        shlex.quote(part)
        for part in ["git", "-C", repo_path, "checkout", "--progress", ref]
    )
    workspace_update_tags(workspace_id, {"repo-ref": ref})
    result = workspace_realtime_exec_start_impl(workspace_id, command, workdir=repo_path)
    result.update({"operation": "repo_checkout", "repo_path": repo_path, "ref": ref})
    return result


def repo_status_impl(workspace_id: str, path: str | None = None) -> dict[str, Any]:
    repo_path = _repo_path_for_workspace(workspace_id, path)
    q = shlex.quote(repo_path)
    command = f"""set -euo pipefail
printf 'HEAD='; git -C {q} rev-parse HEAD
printf 'BRANCH='; git -C {q} branch --show-current
printf 'REMOTE='; git -C {q} remote get-url origin
printf '%s\\n' '---STATUS---'
git -C {q} status --short --branch
""".strip()
    result = workspace_exec_impl(workspace_id, command, timeout_seconds=60, workdir=repo_path)
    if result["returncode"] != 0:
        return result

    lines = result["stdout"].splitlines()
    head = next((line[5:] for line in lines if line.startswith("HEAD=")), None)
    branch = next((line[7:] for line in lines if line.startswith("BRANCH=")), None)
    remote = next((line[7:] for line in lines if line.startswith("REMOTE=")), None)
    marker = lines.index("---STATUS---") if "---STATUS---" in lines else len(lines)
    status = "\n".join(lines[marker + 1 :])
    return {
        "workspace_id": workspace_id,
        "sandbox_id": result["sandbox_id"],
        "repo_path": repo_path,
        "head": head,
        "branch": branch,
        "remote": remote,
        "status": status,
        "clean": not any(
            line and not line.startswith("##")
            for line in status.splitlines()
        ),
    }


def repo_diff_impl(
    workspace_id: str,
    path: str | None = None,
    cached: bool = False,
    stat: bool = False,
) -> dict[str, Any]:
    repo_path = _repo_path_for_workspace(workspace_id, path)
    args = ["git", "-C", repo_path, "diff", "--no-ext-diff"]
    if cached:
        args.append("--cached")
    if stat:
        args.append("--stat")
    command = " ".join(shlex.quote(part) for part in args)
    result = workspace_exec_impl(workspace_id, command, timeout_seconds=120, workdir=repo_path)
    return {
        "workspace_id": workspace_id,
        "sandbox_id": result["sandbox_id"],
        "repo_path": repo_path,
        "returncode": result["returncode"],
        "diff": result["stdout"],
        "stderr": result["stderr"],
        "truncated": result.get("stdout_truncated", False),
    }
