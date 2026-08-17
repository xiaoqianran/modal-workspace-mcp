# modal-workspace-mcp

`modal-workspace-mcp` 是一个部署在你自己 Modal 账户里的 **实时 Remote Workspace 网关**。

它的目标不是“远程执行一条命令”，而是让 ChatGPT、GitHub Copilot、MCP Client 或未来 Web UI 获得一个可以持续使用的远程实验工作区：

```text
ChatGPT / Copilot / MCP Client
              │
              │ HTTPS + Bearer
              ▼
      modal-workspace-mcp
      ├── /api/*   GPT Actions / REST
      └── /mcp/    Remote MCP
              │
              ▼
        Remote Workspace (ws-*)
              │
        Modal Sandbox (sb-*)
      ├── realtime process runtime
      ├── GitHub clone / fetch / checkout
      ├── apt / curl / wget
      ├── uv / pip / Python
      ├── CPU / GPU
      └── Filesystem
```

> 对上层 Agent 来说，`ws-*` 是主要对象；`sb-*` 只是底层实现和诊断信息。

## v0.5：Workspace-first + Realtime GitHub

v0.5 在已经上线的 v0.4 实时 Runtime 上增加两层：

```text
P0 Realtime Runtime       ✅
P1 Workspace abstraction  ✅
P2 Realtime Git / Repo    ✅
P3 Filesystem watch       下一阶段
P4 Snapshot / Resume      下一阶段
P5 Experiment / GPU       下一阶段
```

### Workspace

每个在线 Workspace 有稳定 ID：

```text
ws-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Gateway 使用 Modal Sandbox 原生 tags 把 `ws-*` 映射到实际 `sb-*`：

```text
managed-by=modal-workspace-mcp
workspace-id=ws-...
workspace-root=/workspace
repo-slug=OWNER/REPO      # clone 后
repo-path=/workspace/repo # clone 后
repo-ref=main/HEAD/...    # clone/checkout 后
```

因此不同 HTTP 请求、GPT Action 调用或 MCP 调用都能仅凭 `workspace_id` 找回同一个实时环境。

当前 v0.5 的 Workspace 是**在线态抽象**：Sandbox 终止后该 Workspace 离线。长期恢复/分叉会在 P4 通过 Snapshot + Volume 实现，不假装已经有永久 Workspace 数据库。

## 推荐使用流程

### 1. 创建 Workspace

GPT Action：

```text
createRemoteWorkspace
```

MCP：

```text
workspace_create
```

返回：

```json
{
  "workspace_id": "ws-...",
  "sandbox_id": "sb-...",
  "root": "/workspace",
  "running": true
}
```

后续尽量只使用 `workspace_id`。

### 2. 实时拉取 GitHub 仓库

GPT Action：

```text
cloneGitHubRepoToWorkspace
```

MCP：

```text
repo_clone
```

示例参数：

```json
{
  "workspace_id": "ws-...",
  "repository": "xiaoqianran/modal-workspace-mcp",
  "ref": "main",
  "depth": 1
}
```

默认 clone 到：

```text
/workspace/repo
```

立即返回：

```json
{
  "workspace_id": "ws-...",
  "exec_id": "ex-...",
  "cursor": 0,
  "operation": "repo_clone"
}
```

然后持续读取：

```text
getRealtimeWorkspaceExecEvents
```

或 MCP：

```text
workspace_realtime_exec_events
```

始终把上一批的 `next_cursor` 作为下一次 `cursor`。

`git clone --progress` 的 stdout/stderr 会作为增量事件返回，所以大仓库、LFS、下载、编译不会等到任务结束才一次性看到日志。

### 3. 查看 Repo

```text
getWorkspaceGitStatus
getWorkspaceGitDiff
fetchWorkspaceGitRepo
checkoutWorkspaceGitRef
```

对应 MCP：

```text
repo_status
repo_diff
repo_fetch
repo_checkout
```

`repo_status` 返回结构化信息：

```json
{
  "head": "40位commit SHA",
  "branch": "main",
  "remote": "https://github.com/OWNER/REPO.git",
  "status": "## main...origin/main",
  "clean": true
}
```

### 4. 在 Repo 里实时实验

clone 成功后，Workspace 默认 workdir 自动变为 Repo 路径。

例如：

```text
startRealtimeWorkspaceExec
command = "uv sync && uv run pytest -q"
```

无需再告诉 Agent `/workspace/repo`。

## 实时 Runtime

实时执行不是“不断返回整个日志”，而是 append-only event stream：

```text
start
  ↓
exec_id + cursor=0
  ↓
events(cursor=0, wait_seconds=...)
  ↓
只返回新增事件
  ↓
next_cursor
  ↓
继续 long-poll
```

事件：

```json
{
  "seq": 42,
  "timestamp": "...",
  "type": "stdout",
  "data": "Receiving objects: 57%\n"
}
```

类型：

```text
status
stdout
stderr
error
exit
```

支持：

- stdout / stderr 增量读取；
- cursor；
- long-poll；
- stdin；
- PTY；
- TERM / INT / HUP / KILL；
- Gateway 跨请求重新连接同一个 Sandbox 后继续读取。

生产 E2E 已实际验证：进程阻塞等待 stdin 时，Gateway 已经能先取得 stdout；随后另一个 HTTP 请求发送 stdin，再由后续 cursor 请求取得完成事件。

## Workspace API

### GPT Actions / REST

| operationId | 用途 |
|---|---|
| `createRemoteWorkspace` | 创建在线 Workspace |
| `listRemoteWorkspaces` | 列出在线 Workspace |
| `getRemoteWorkspace` | 用 `ws-*` 查询状态/Repo |
| `terminateRemoteWorkspace` | 终止 Workspace |
| `executeInRemoteWorkspace` | 很短的同步命令 |
| `startRealtimeWorkspaceExec` | 启动实时命令 |
| `getRealtimeWorkspaceExecEvents` | cursor 增量事件 |
| `getRealtimeWorkspaceExecStatus` | 进程状态 |
| `sendRealtimeWorkspaceExecInput` | stdin / EOF |
| `cancelRealtimeWorkspaceExec` | 发送信号取消 |
| `cloneGitHubRepoToWorkspace` | 实时 clone GitHub Repo |
| `fetchWorkspaceGitRepo` | 实时 fetch |
| `checkoutWorkspaceGitRef` | 实时 checkout |
| `getWorkspaceGitStatus` | HEAD / branch / remote / status |
| `getWorkspaceGitDiff` | diff / cached / stat |

Raw `sandbox_*` API 仍保留，作为底层兼容和 escape hatch。

## MCP tools

推荐的新工具：

```text
workspace_create
workspace_get
workspace_list
workspace_exec
workspace_realtime_exec_start
workspace_realtime_exec_events
workspace_realtime_exec_status
workspace_realtime_exec_input
workspace_realtime_exec_cancel
workspace_terminate

repo_clone
repo_fetch
repo_checkout
repo_status
repo_diff
```

旧 `sandbox_*` 工具继续可用。

## GitHub 中转的安全边界

Repo API 不允许 Agent 任意把字符串拼成 `git clone` shell。

`repository` 只接受：

```text
OWNER/REPO
https://github.com/OWNER/REPO
https://github.com/OWNER/REPO.git
```

拒绝：

```text
非 github.com host
URL 内 username/password/token
query / fragment
多余路径
越界 destination
危险 Git ref
```

Git 参数会在服务端验证并 shell quote。

### 私有 GitHub

不要这样：

```text
https://TOKEN@github.com/OWNER/REPO.git
```

推荐创建 Modal Secret：

```bash
modal secret create github-agent GH_TOKEN="$GH_TOKEN"
```

GitHub Variable：

```text
MODAL_WORKSPACE_ALLOWED_SECRETS=github-agent
```

调用 clone/fetch：

```json
{
  "secret_names": ["github-agent"],
  "use_github_token": true
}
```

Gateway 只把 Secret **名称**传给 Modal。Sandbox 内临时 `GIT_ASKPASS` 从环境变量 `$GH_TOKEN` 读取凭据；token 值不会拼进 clone URL、API response 或事件日志。

## 默认 Workspace 环境

未指定 Named Image 时使用 Debian Slim，并预装：

```text
ca-certificates
curl
git
git-lfs
jq
openssh-client
ripgrep
unzip
wget
uv
```

所以默认 Workspace 就能：

```text
git clone
curl / wget
uv / pip
apt
Python
```

默认资源：

```text
CPU request       2
CPU hard limit    4
Memory request    4096 MiB
Memory hard limit 8192 MiB
```

可按 Workspace 调整 `cpu / cpu_limit / memory / gpu / cloud / region`。

## Secrets / Volumes：默认拒绝

未配置时：

```text
MODAL_WORKSPACE_ALLOWED_SECRETS = 空
MODAL_WORKSPACE_ALLOWED_VOLUMES = 空
MODAL_WORKSPACE_DEFAULT_IMAGE_NAME = None
```

公开 GitHub clone 不需要任何 Secret。

可选 GitHub Variables：

```text
MODAL_WORKSPACE_ALLOWED_SECRETS=github-agent,huggingface-agent
MODAL_WORKSPACE_ALLOWED_VOLUMES=model-cache,workspace-cache
MODAL_WORKSPACE_DEFAULT_IMAGE_NAME=modal-workspace-base:latest
```

## Named Image / Snapshot / Volume

推荐长期边界：

```text
Named Image = 稳定软件环境
Sandbox     = 当前在线 Workspace
Snapshot    = 会话保存/恢复/分叉（P4）
Volume      = dataset / cache / artifact（P4+）
Git         = 源码版本
```

当前已有底层 `sandbox_snapshot`，但 v0.5 还没有把它包装成 `workspace_save/resume/fork`；这会在 P4 做，而不是把未完成能力写成已完成。

## 部署

必需 GitHub Actions Secrets：

```text
MODAL_TOKEN_ID
MODAL_TOKEN_SECRET
MODAL_WORKSPACE_MCP_TOKEN
```

`main` 变更后 Deploy workflow 会真实执行：

```text
install
→ Modal auth
→ deploy
→ /healthz
→ /api/apps
→ createRemoteWorkspace
→ 用 ws-* 重新解析 Sandbox tag
→ Workspace realtime stdout + stdin
→ cloneGitHubRepoToWorkspace
→ cursor 拉取 clone events
→ getWorkspaceGitStatus
→ 验证 HEAD / remote / repo metadata
→ terminateRemoteWorkspace
```

因此“Deploy success”代表线上 Workspace + GitHub 中转链路真的跑过，不只是 import/compile 成功。

## ChatGPT GPT Actions

OpenAPI：

```text
https://YOUR-ENDPOINT.modal.run/action-openapi.json
```

认证：

```text
API Key
Auth Type: Bearer
Key: MODAL_WORKSPACE_MCP_TOKEN
```

推荐给 GPT 的核心指令：

```text
优先使用 Remote Workspace，而不是直接操作 raw Sandbox。
新任务先 createRemoteWorkspace。
GitHub 仓库使用 cloneGitHubRepoToWorkspace，不要自己拼带 token 的 git URL。
安装、下载、Git、编译、实验优先使用 realtime 操作。
每次读取事件都把 next_cursor 用作下一次 cursor。
任务完成后 terminateRemoteWorkspace，除非用户明确要求保持在线。
```

## Remote MCP

```text
https://YOUR-ENDPOINT.modal.run/mcp/
```

请求头：

```text
Authorization: Bearer <MODAL_WORKSPACE_MCP_TOKEN>
```

## 下一阶段

```text
P0 Realtime Runtime       ✅
P1 Workspace abstraction  ✅ v0.5
P2 Realtime Git / Repo    ✅ v0.5
 ↓
P3 Filesystem watch
 ↓
P4 workspace_save / resume / fork + Volume
 ↓
P5 Experiment + GPU metrics
 ↓
P6 Artifact / GitHub branch / PR 回传
 ↓
WebSocket UI / browser terminal
```

## 测试

```bash
python -m unittest discover -s tests -v
python -m compileall -q modal_workspace_mcp modal_app.py
```

测试包括：

- 实时 stdout 必须在进程结束前出现；
- stdin roundtrip；
- Workspace ID 校验；
- GitHub Repo URL / ref / path 安全校验；
- 私有 Git askpass 不包含 token 值；
- Modal Sandbox tags API contract；
- Workspace/Repo Action operationId contract；
- 生产真实 Workspace + GitHub clone E2E。

## 项目结构

```text
modal-workspace-mcp/
├── modal_app.py
├── modal_workspace_mcp/
│   ├── action_api.py
│   ├── config.py
│   ├── helpers.py
│   ├── realtime_agent.py
│   ├── realtime_service.py
│   ├── workspace_service.py
│   ├── repo_service.py
│   ├── server.py
│   └── service.py
├── .github/workflows/
│   ├── ci.yml
│   └── deploy-modal.yml
├── tests/
├── plugins/
├── skills/
└── examples/
```
