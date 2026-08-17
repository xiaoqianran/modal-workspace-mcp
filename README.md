# modal-workspace-mcp

`modal-workspace-mcp` 是一个部署在你自己 Modal 账户里的 **实时 Remote Workspace 网关**。

它让 ChatGPT、GitHub Copilot 或其他 MCP Client 把本地无法完成的联网 Shell、`git clone`、依赖安装、编译、GPU 实验、文件操作和 Modal Function 调用交给 Modal Sandbox，并把运行中的输出按增量事件实时取回。

```text
ChatGPT / GitHub Copilot / MCP Client
                │
                │ HTTPS + Bearer
                ▼
        modal-workspace-mcp
        ├── /mcp/                 Remote MCP
        └── /api/*                GPT Actions / REST
                │
                ▼
             Modal Sandbox
        ├── realtime process runtime
        ├── apt / git / curl / wget
        ├── pip / uv
        ├── CPU / GPU
        └── Filesystem API
```

## v0.4：实时 Runtime P0

v0.4 把执行模型从“提交命令，结束后一次性返回日志”升级为：

```text
start
  ↓
立即得到 exec_id
  ↓
events(cursor=0, wait=15)
  ↓
只返回新增 stdout/stderr/status/exit
  ↓
更新 cursor
  ↓
继续 long-poll
```

实时进程支持：

- `stdout` / `stderr` 增量事件；
- 单调递增 `seq` / `cursor`，不会每次重复返回全部历史日志；
- `wait_seconds` long-poll：没有新事件时等待，有事件立即返回；
- 跨请求发送 `stdin`；
- PTY 模式；
- TERM / INT / HUP / KILL 取消整个进程组；
- Gateway 重连 Sandbox 后仍能继续查询同一个 `exec_id`。

P0 的事件存储和进程代理运行在 Sandbox 内，不依赖 Gateway 容器内存。Modal `Sandbox.from_id()` 可以跨请求重新连接 Sandbox，但 Modal 当前没有公开的 `ContainerProcess.from_id()`，因此不能把短生命周期的 Python process handle 当作持久实时协议；v0.4 使用 Sandbox 内常驻 worker + append-only event stream 解决这个问题。

### 事件格式

```json
{
  "seq": 3,
  "timestamp": "2026-08-18T00:00:00+00:00",
  "type": "stdout",
  "data": "Receiving objects: 42%\n"
}
```

当前事件类型：

```text
status
stdout
stderr
error
exit
```

## 实时工具

### GPT Actions / REST

| operationId | 用途 |
|---|---|
| `startRealtimeSandboxExec` | 启动实时进程，立即返回 `exec_id` |
| `getRealtimeSandboxExecEvents` | 使用 cursor 增量读取事件，可 long-poll |
| `getRealtimeSandboxExecStatus` | 查询进程状态 / PID / return code |
| `sendRealtimeSandboxExecInput` | 发送 stdin / EOF |
| `cancelRealtimeSandboxExec` | TERM / INT / HUP / KILL |

### MCP

对应 MCP tools：

```text
sandbox_realtime_exec_start
sandbox_realtime_exec_events
sandbox_realtime_exec_status
sandbox_realtime_exec_input
sandbox_realtime_exec_cancel
```

旧的：

```text
sandbox_exec_start
sandbox_job_status
sandbox_job_cancel
```

仍保留兼容，但新工作流应优先使用 realtime exec。

## 一个真正的实时例子

先创建 Sandbox，再启动：

```bash
for i in $(seq 1 10); do
  echo "step=$i"
  sleep 1
done
```

`startRealtimeSandboxExec` 会立即返回：

```json
{
  "sandbox_id": "sb-...",
  "exec_id": "ex-...",
  "state": "starting",
  "cursor": 0
}
```

然后调用：

```text
getRealtimeSandboxExecEvents(
  cursor=0,
  wait_seconds=15
)
```

应该在命令结束前就看到：

```text
step=1
```

返回 `next_cursor` 后继续请求下一批，而不是重新下载完整 stdout。

## GitHub 仓库拉取 / 中转

这正是项目的主要用途之一。

例如：

```text
创建一个 Modal Sandbox，
实时执行：
  git clone --progress https://github.com/OWNER/REPO.git /workspace/repo
然后实时返回 clone 进度，完成后执行 git status 和 git rev-parse HEAD。
```

当前无需专门 Repo API 就已经可以工作：Git 是在 Modal Sandbox 内执行的，所以即使 ChatGPT 自身执行容器没有 GitHub DNS / 外网，也不影响 Sandbox 拉取公开仓库。

下一阶段会在实时 Runtime 上增加正式 Workspace / Repo 层：

```text
workspace_create
repo_clone
repo_fetch
repo_checkout
repo_status
repo_diff
```

Git 只是 Workspace 的一个 Source，不会成为整个项目的最高层抽象。

## 私有 GitHub 仓库

不要把 GitHub Token 写进命令或仓库 URL。

推荐：

```text
GitHub token
   ↓
Modal Secret
   ↓
MODAL_WORKSPACE_ALLOWED_SECRETS allowlist
   ↓
Sandbox secret_names
```

例如先创建 Modal Secret：

```bash
modal secret create github-agent GH_TOKEN="$GH_TOKEN"
```

GitHub Variables：

```text
MODAL_WORKSPACE_ALLOWED_SECRETS=github-agent
```

之后 Agent 只传 Secret 名称，不传 Secret 值。

## Sandbox 生命周期与基础工具

| 工具 | 用途 |
|---|---|
| `sandbox_create` | 创建 Modal Sandbox |
| `sandbox_exec` | 同步执行很短的命令 |
| `sandbox_status` | 查询 Sandbox 状态 |
| `sandbox_list` | 列出本桥接器管理的 Sandbox |
| `sandbox_snapshot` | 文件系统快照为 Image，可发布 Named Image |
| `sandbox_terminate` | 终止 Sandbox |

## 文件系统

使用 Modal 当前 Filesystem API：

| 工具 | 用途 |
|---|---|
| `sandbox_file_read` | 读取 UTF-8 文本文件 |
| `sandbox_file_write` | 写入 UTF-8 文本文件 |
| `sandbox_file_list` | 列目录 |
| `sandbox_directory_create` | 建目录 |
| `sandbox_file_remove` | 删除文件/目录（拒绝删除 `/`） |

## Modal Functions / Apps

| 工具 | 用途 |
|---|---|
| `function_call` | 同步调用已部署 Function |
| `function_spawn` | 异步启动 Function |
| `function_call_get` | 轮询/等待 FunctionCall |
| `function_call_cancel` | 取消 FunctionCall |
| `app_get` | 查询 App |
| `app_list` | 列出 Apps |

## 默认 Sandbox Image

不传 `image_name/image_id` 时使用 Debian Slim，并预装：

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

因此默认就可以：

```text
git clone
curl / wget
uv / pip
apt
```

实时 Runtime 依赖 Sandbox 内存在 `python3`；默认 Image 满足这一条件。如果使用自定义 Named Image，也应保留 Python 3。

## Named Image

稳定使用时推荐预构建 Named Image，例如：

```text
modal-workspace-base:latest
modal-workspace-cuda:latest
modal-workspace-3d:latest
```

然后设置：

```text
MODAL_WORKSPACE_DEFAULT_IMAGE_NAME=modal-workspace-base:latest
```

避免每次 Workspace 启动都重新安装相同系统依赖。

## CPU / 内存

默认：

```text
CPU request      = 2
CPU hard limit   = 4
Memory request   = 4096 MiB
Memory hard limit= 8192 MiB
```

创建 Sandbox 时可调整：

```text
cpu
cpu_limit
memory_mib
memory_limit_mib
gpu
cloud
region
```

## 网络

Modal Sandbox 默认允许公网访问，也支持：

```json
{
  "outbound_domain_allowlist": [
    "github.com",
    "*.githubusercontent.com",
    "pypi.org",
    "*.pythonhosted.org"
  ]
}
```

完全断网：

```json
{
  "block_network": true
}
```

## Secrets / Volumes：默认拒绝

未配置时：

```text
MODAL_WORKSPACE_ALLOWED_SECRETS = 空
MODAL_WORKSPACE_ALLOWED_VOLUMES = 空
MODAL_WORKSPACE_DEFAULT_IMAGE_NAME = None
```

因此默认不会允许 Agent 随意挂载账户里的 Secret 或 Volume。

需要时配置 GitHub Variables：

```text
MODAL_WORKSPACE_ALLOWED_SECRETS=github-agent,huggingface-agent
MODAL_WORKSPACE_ALLOWED_VOLUMES=model-cache,workspace-cache
MODAL_WORKSPACE_DEFAULT_IMAGE_NAME=modal-workspace-base:latest
```

## 部署

必需 GitHub Actions Secrets：

```text
MODAL_TOKEN_ID
MODAL_TOKEN_SECRET
MODAL_WORKSPACE_MCP_TOKEN
```

`main` 更新后 **Deploy Modal Gateway** 会：

```text
安装项目
→ 验证 Modal auth
→ 更新网关 Secret
→ modal deploy
→ /healthz + /api/apps smoke test
→ 创建真实 Sandbox
→ 验证“进程结束前收到 stdout”
→ 发送 stdin
→ 验证实时输出
→ 自动 terminate 测试 Sandbox
```

也就是说 v0.4 的部署成功不再只代表“代码能 import”，而会真实验证 Modal 实时链路。

## ChatGPT 网页版：GPT Actions

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

推荐给 GPT 的行为说明：

```text
很短的命令使用 executeInModalSandbox。
安装、下载、Git clone、编译、实验等需要看到过程的任务，优先使用 startRealtimeSandboxExec。
拿到 exec_id 后持续调用 getRealtimeSandboxExecEvents，并始终把 next_cursor 作为下一次 cursor。
需要交互输入时使用 sendRealtimeSandboxExecInput。
任务完成后及时 terminate Sandbox。
```

## Remote MCP

```text
https://YOUR-ENDPOINT.modal.run/mcp/
```

请求：

```text
Authorization: Bearer <MODAL_WORKSPACE_MCP_TOKEN>
```

## Snapshot / 恢复

实时运行时使用 Sandbox；需要保存环境时：

```text
sandbox_snapshot
```

之后可以从 Image / Named Image 继续创建新的 Sandbox。

长期设计：

```text
在线状态 = Sandbox
稳定环境 = Named Image
会话状态 = Snapshot
大文件/cache/artifact = Volume
```

## 下一阶段

v0.4 只是实时底座 P0。接下来按这个顺序继续：

```text
P0 Realtime Runtime       ← 当前
 ↓
P1 Workspace abstraction
 ↓
P2 Realtime Git / Repo
 ↓
P3 Filesystem watch
 ↓
P4 Snapshot / Resume / Fork
 ↓
P5 Experiment + GPU metrics
 ↓
P6 Artifact / GitHub 回传
```

未来 Web UI / CLI 会使用 WebSocket；ChatGPT GPT Actions 继续使用 `cursor + long-poll`，两者共享同一套 Event Protocol。

## 安全边界

- `/mcp/` 与 `/api/*` 必须 Bearer token。
- `/healthz`、`/privacy`、`/action-openapi.json` 公开，但不暴露管理凭据。
- Secret / Volume deny-by-default。
- 不要在命令字符串中明文放 token。
- 实时 stdin、输出和 API 参数都有长度限制。
- 删除 API 拒绝直接删除 Sandbox 根目录 `/`。
- 实验完成后及时 terminate Sandbox。

## 测试

```bash
python -m unittest discover -s tests -v
python -m compileall -q modal_workspace_mcp modal_app.py
```

`tests/test_realtime_agent.py` 会验证：

1. 命令没有结束时就已经能够读到第一段 stdout；
2. stdin 跨请求输入后，子进程能实时收到并输出。

部署 workflow 还会执行真实 Modal Sandbox E2E。

## 项目结构

```text
modal-workspace-mcp/
├── modal_app.py
├── modal_workspace_mcp/
│   ├── action_api.py
│   ├── config.py
│   ├── helpers.py
│   ├── realtime_agent.py        # Sandbox 内运行的实时 worker
│   ├── realtime_service.py      # Gateway → realtime agent
│   ├── server.py                # FastMCP tools
│   └── service.py               # Modal 基础能力
├── .github/workflows/
│   ├── ci.yml
│   └── deploy-modal.yml         # 含真实 realtime E2E
├── plugins/
├── skills/
├── examples/
└── tests/
```
