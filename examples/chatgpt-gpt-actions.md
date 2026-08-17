# ChatGPT Plus: use GPT Actions

ChatGPT Plus can create custom GPTs with Actions. Full custom MCP write/execute access in ChatGPT web is currently reserved for Business/Enterprise/Edu, so Plus should use this repo's REST/OpenAPI compatibility layer.

After deploying `modal_app.py`, suppose Modal prints:

```text
https://YOUR-ENDPOINT.modal.run
```

In ChatGPT:

1. Open **GPTs → Create → Configure → Actions → Create new action**.
2. Import this schema URL:

```text
https://YOUR-ENDPOINT.modal.run/action-openapi.json
```

3. Authentication: **API key → Bearer**.
4. Set the API key to the same value stored in Modal Secret `MODAL_WORKSPACE_MCP_TOKEN`.
5. Test `createModalSandbox`, then `executeInModalSandbox`.

Suggested first prompt:

```text
Create a Modal Sandbox. Run: apt-get update && apt-get install -y git curl && git --version && curl -I https://github.com . Return stdout/stderr, then terminate the Sandbox.
```

The REST Action API and the MCP server use the same underlying implementation, so behavior stays aligned.
