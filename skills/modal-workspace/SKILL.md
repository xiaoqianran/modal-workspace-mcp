---
name: modal-workspace
description: 当本地执行环境无法联网、缺依赖、缺 GPU 或不适合长任务时，使用用户自己的 Modal 进行远程执行。
---

# Modal Workspace MCP

1. 本地 `apt/curl/git/pip/uv` 因网络或权限失败时，不要反复重试本地容器，改用 `sandbox_create` + Modal 工具。
2. 短命令使用 `sandbox_exec`；安装、下载、编译、长测试使用 `sandbox_exec_start`，再轮询 `sandbox_job_status`。
3. 同一任务尽量复用 `sandbox_id`，任务完成后 `sandbox_terminate`。
4. 读写普通文本文件优先使用 `sandbox_file_*`，不要为了简单文件操作拼复杂 shell quoting。
5. 不得通过 `env`、`echo`、`set`、日志或聊天正文泄露 Secret。需要凭据时只传已 allowlist 的 `secret_names`。
6. 需要稳定低延迟创建 Sandbox 时优先使用 Named Image (`image_name`)；临时依赖才用 `apt_packages/pip_packages` 动态构建。
7. 可使用 `function_spawn` + `function_call_get` 处理已部署 Modal Function 的异步调用。
8. 删除路径前核对目标；网关拒绝删除 Sandbox 根目录 `/`。
