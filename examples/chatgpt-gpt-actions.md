# 在 ChatGPT 网页版中使用

部署后，同一个 Modal Web Function 同时提供：

- `GET /action-openapi.json`：给自定义 GPT 的 Actions 导入。
- `/api/*`：GPT Actions 调用的 REST API。
- `/mcp/`：给支持 Remote MCP 的客户端。

## GPT Actions

1. 打开 GPT 编辑器，进入 **Configure → Actions → Create new action**。
2. 导入 `https://你的-endpoint.modal.run/action-openapi.json`。
3. Authentication 选择 **API key**。
4. Auth Type 选择 **Bearer**。
5. API key 填与 Modal Secret `MODAL_WORKSPACE_MCP_TOKEN` 相同的网关 token。

首次测试建议：

```text
创建一个 30 分钟的 Modal Sandbox；启动后台任务执行 apt-get update && apt-get install -y ffmpeg；
轮询任务直到完成；运行 ffmpeg -version；最后终止 Sandbox。
```

长任务优先走 `startModalSandboxJob` / `getModalSandboxJob`，不要让一次 HTTP Action 长时间阻塞。
