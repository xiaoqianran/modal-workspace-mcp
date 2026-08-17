# modal-workspace-mcp

`modal-workspace-mcp` 是一个**远程执行桥**：让 ChatGPT、GitHub Copilot 或其他 MCP Client 把本地无法完成的联网 Shell、依赖安装、Git 操作、GPU 任务、文件操作和 Modal Function 调用交给**你自己的 Modal 账户**。

它不是 IDE，也不是要把开发流程搬到另一个“工作区”。它只负责提供一组受控工具：Agent 需要计算/网络时调用 Modal，完成后结果返回原来的聊天或 Agent。

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
             你的 Modal
        ├── Modal Sandbox
        │   ├── apt / git / gh
        │   ├── curl / wget
        │   ├── pip / uv
        │   ├── CPU / GPU
        │   └── Filesystem API
        └── 已部署 Modal Functions
```

## 为什么它能解决“ChatGPT/GitHub 执行容器没有外网 DNS”

原执行容器不再负责 `apt`、`curl`、`git clone` 或 `pip install`。它只需要能访问你部署出来的 Modal HTTPS endpoint；真正访问 GitHub、PyPI、apt 源并执行命令的是 Modal Sandbox。

## v0.3：按 Modal 1.5+ 官方 API 重构

这一版以 Modal 当前 `llms.txt`、Sandbox / Filesystem / Networking / Named Image / FunctionCall / MCP / Continuous Deployment 文档为基准重新整理：

- `Sandbox.create` 支持 CPU/内存 **request + hard limit**、GPU、cloud、region、workdir。
- 支持 `outbound_cidr_allowlist`、`outbound_domain_allowlist`、`inbound_cidr_allowlist` 与 `block_network` 的互斥校验。
- 支持 `image_name`（Named Image）、`image_id` 和临时动态 apt/pip Image 三种模式。
- 使用最新 `Sandbox.filesystem.read_text/write_text/list_files/make_directory/remove/stat`，不再把所有文件操作都塞进 shell。
- `snapshot_filesystem` 暴露 TTL，并可直接 `publish_as` 发布成 Named Image。
- Modal Function 同时支持同步 `remote()` 与异步 `spawn()` / `FunctionCall.from_id().get()` / cancel。
- 新增长命令 job：安装、下载、编译可后台启动，再轮询日志，避免 ChatGPT Action 长 HTTP 请求阻塞。
- 网关采用纯 ASGI Bearer middleware，MCP 使用 FastMCP 官方 Streamable HTTP + stateless 模式。
- 新增独立 CI；部署 workflow 会在最前面检查必需的 GitHub Secrets。

## 工具

### Sandbox 生命周期与执行

| 工具 | 用途 |
|---|---|
| `sandbox_create` | 创建 Modal Sandbox |
| `sandbox_exec` | 同步执行短命令 |
| `sandbox_exec_start` | 启动后台长任务 |
| `sandbox_job_status` | 轮询后台任务和日志 |
| `sandbox_job_cancel` | 取消后台任务 |
| `sandbox_status` | 查询 Sandbox 状态 |
| `sandbox_list` | 列出本桥接器管理的 Sandbox |
| `sandbox_snapshot` | 文件系统快照为 Image，可发布 Named Image |
| `sandbox_terminate` | 终止 Sandbox |

### 文件系统

| 工具 | 用途 |
|---|---|
| `sandbox_file_read` | 读取 UTF-8 文本文件 |
| `sandbox_file_write` | 写入 UTF-8 文本文件 |
| `sandbox_file_list` | 列目录 |
| `sandbox_directory_create` | 建目录 |
| `sandbox_file_remove` | 删除文件/目录（拒绝删除 `/`） |

### Modal Functions / Apps

| 工具 | 用途 |
|---|---|
| `function_call` | 同步调用已部署 Function |
| `function_spawn` | 异步启动 Function |
| `function_call_get` | 轮询/等待 FunctionCall |
| `function_call_cancel` | 取消 FunctionCall |
| `app_get` | 查询 App |
| `app_list` | 列出 Apps |

## Sandbox Image 选择

### 1. 默认动态 Image

不传 `image_name/image_id` 时，会使用 Debian Slim，并预装：

```text
ca-certificates curl git git-lfs jq openssh-client ripgrep unzip wget uv
```

再叠加你传入的 `apt_packages` / `pip_packages`。

这种方式方便，但第一次遇到新的依赖组合可能需要构建 Image。

### 2. Named Image（推荐稳定使用）

如果已经发布例如 `agent-runtime:latest`：

```json
{
  "image_name": "agent-runtime:latest"
}
```

Named Image 不会在创建 Sandbox 的延迟敏感路径上隐式重建，更适合作为长期 Agent runtime。

也可以设置网关环境变量：

```text
MODAL_WORKSPACE_DEFAULT_IMAGE_NAME=agent-runtime:latest
```

### 3. Image ID

已有 Snapshot/Build 的 `im-...` 时可直接：

```json
{
  "image_id": "im-..."
}
```

## CPU / 内存硬上限

默认：

```text
CPU request = 2
CPU hard limit = 4
Memory request = 4096 MiB
Memory hard limit = 8192 MiB
```

创建 Sandbox 时可调整 `cpu/cpu_limit/memory_mib/memory_limit_mib`。这比只设置 request 更适合 Agent，防止失控任务无限抢资源。

## 网络

Modal Sandbox 默认可访问公网；本项目允许进一步限制：

```json
{
  "outbound_domain_allowlist": ["github.com", "*.githubusercontent.com", "pypi.org", "*.pythonhosted.org"]
}
```

或：

```json
{
  "outbound_cidr_allowlist": ["0.0.0.0/0"]
}
```

完全断网：

```json
{
  "block_network": true
}
```

`block_network=true` 与 CIDR/Domain/Inbound allowlist 不能同时使用，网关会提前拒绝这种配置。

## Secrets 和 Volumes：默认拒绝

Agent **不能任意读取你的 Modal Secrets/Volumes**。必须先在网关配置名称 allowlist：

```text
MODAL_WORKSPACE_ALLOWED_SECRETS=github-agent,huggingface-agent
MODAL_WORKSPACE_ALLOWED_VOLUMES=model-cache,workspace-cache
```

然后 Agent 只能请求这些“名称”，Secret 值不会成为 MCP/Action 参数。

例如：

```bash
modal secret create github-agent GH_TOKEN="$GH_TOKEN"
modal secret create huggingface-agent HF_TOKEN="$HF_TOKEN"
```

不要让 Agent 执行 `env`、`set`、`echo $TOKEN` 之类会打印 Secret 的命令。

## 部署

### GitHub Actions Secrets

仓库需要：

```text
MODAL_TOKEN_ID
MODAL_TOKEN_SECRET
MODAL_WORKSPACE_MCP_TOKEN
```

前两个只用于 GitHub Actions → Modal 部署；第三个是 ChatGPT/MCP Client 访问网关时使用的 Bearer token。

可选 GitHub Variables：

```text
MODAL_WORKSPACE_ALLOWED_SECRETS
MODAL_WORKSPACE_ALLOWED_VOLUMES
MODAL_WORKSPACE_DEFAULT_IMAGE_NAME
```

然后运行 **Deploy Modal Gateway** workflow，或向 `main` 推送网关代码触发部署。

也可以本地部署：

```bash
python -m pip install .
modal secret create modal-workspace-mcp-auth \
  MODAL_WORKSPACE_MCP_TOKEN='<你的强随机网关 token>'
modal deploy modal_app.py
```

部署成功后得到一个 `https://...modal.run` endpoint。

## ChatGPT 网页版：GPT Actions

同一个 endpoint 会公开 OpenAPI schema：

```text
https://YOUR-ENDPOINT.modal.run/action-openapi.json
```

在 GPT 编辑器中：

1. `Configure → Actions → Create new action`
2. 导入上面的 OpenAPI schema
3. Authentication 选择 **API key**
4. Auth Type 选择 **Bearer**
5. Key 填 `MODAL_WORKSPACE_MCP_TOKEN` 的值

首次建议测试：

```text
创建一个 30 分钟的 Modal Sandbox。
启动后台任务：apt-get update && apt-get install -y ffmpeg。
持续查询任务状态直到结束，再执行 ffmpeg -version。
最后终止 Sandbox。
```

长任务优先使用后台 job，而不是一次 `sandbox_exec` 阻塞很久。

## Remote MCP

MCP endpoint：

```text
https://YOUR-ENDPOINT.modal.run/mcp/
```

请求头：

```text
Authorization: Bearer <MODAL_WORKSPACE_MCP_TOKEN>
```

仓库根目录 `.mcp.json` 和 `plugins/modal-workspace/.mcp.json` 已包含 GitHub Copilot Remote MCP 配置模板。

## Snapshot / Named Image

Sandbox 配好环境后可：

```text
sandbox_snapshot(sandbox_id, ttl_seconds=2592000)
```

默认 Snapshot TTL 是 30 天。需要长期引用时可以传 `ttl_seconds=null`，或直接：

```text
publish_as="agent-runtime:latest"
```

以后创建 Sandbox 使用 `image_name="agent-runtime:latest"`，避免重复安装依赖。

## 安全边界

- `/mcp/` 与 `/api/*` 都必须 Bearer token。
- `/healthz`、`/privacy`、`/action-openapi.json` 公开，不暴露管理凭据。
- Secret/Volume 挂载默认 deny-by-default，只能使用配置过的名称 allowlist。
- Agent 不会拿到用于管理整个 Modal 账户的 `MODAL_TOKEN_ID/MODAL_TOKEN_SECRET`。
- 输出、文件读取、目录列表有上限，避免超大结果撑爆 Action/MCP context。
- 删除 API 拒绝直接删除 Sandbox 根目录 `/`。
- 建议为 GitHub/Hugging Face 等外部服务使用最小权限 token。

## 本地验证

```bash
python -m unittest discover -s tests -v
python -m compileall -q modal_workspace_mcp modal_app.py
```

完整 Modal E2E 需要可联网并已认证的 Modal 环境。

## 项目结构

```text
modal-workspace-mcp/
├── modal_app.py                       # Modal Web Function：MCP + GPT Actions
├── modal_workspace_mcp/
│   ├── action_api.py                  # REST / OpenAPI
│   ├── config.py
│   ├── helpers.py
│   ├── server.py                      # FastMCP tools
│   └── service.py                     # Modal SDK 实现
├── .github/workflows/
│   ├── ci.yml
│   └── deploy-modal.yml
├── plugins/modal-workspace/           # GitHub Copilot plugin
├── skills/modal-workspace/SKILL.md
├── examples/
└── tests/
```
