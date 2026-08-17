# modal-workspace-mcp

A remote MCP bridge that lets GitHub Copilot, Copilot CLI, and other MCP clients use **your Modal account** for Linux execution, dependency installation, Git operations, GPU jobs, and calls to deployed Modal Functions.

This project is deliberately a **bridge**, not an IDE or hosted developer workspace.

```text
GitHub Copilot / MCP client
          |
          | Streamable HTTP MCP + Bearer token
          v
https://...modal.run/mcp/
          |
          v
modal-workspace-mcp gateway
          |
          +--> Modal Sandbox --> apt / git / curl / uv / pip / GPU / Internet
          |
          +--> deployed Modal Function
```

## V1 tools

- `sandbox_create` — create a detached Sandbox with configurable CPU/RAM/GPU, apt/pip packages, network policy, allowlisted Secrets and Volumes.
- `sandbox_exec` — execute `bash -lc` commands and return exit code/stdout/stderr.
- `sandbox_status` — check whether a Sandbox is running.
- `sandbox_list` — list Sandboxes managed by this MCP.
- `sandbox_snapshot` — snapshot the Sandbox filesystem to a Modal Image.
- `sandbox_terminate` — terminate a Sandbox.
- `function_call` — invoke an already-deployed Modal Function by app/function name.
- `app_get` — resolve a named Modal App and dashboard URL.
- `app_list` — list Modal Apps through the official `modal app list --json` CLI surface.

## Why this solves the GitHub-container DNS problem

The GitHub agent does **not** execute `apt`, `curl`, `git clone`, or `pip` locally. It only makes an MCP HTTP request to your Modal endpoint. The actual network and shell operations happen inside a Modal Sandbox.

## 1. Configure the gateway token

Generate a random token locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Create a Modal Secret named `modal-workspace-mcp-auth` containing that value:

```bash
modal secret create modal-workspace-mcp-auth MODAL_WORKSPACE_MCP_TOKEN='<generated-token>'
```

The same gateway Secret can also carry non-secret configuration such as allowlists, so the deployed Function receives them as environment variables.

Do not commit the token.

## 2. Optional: allow Sandbox Secrets and Volumes

The MCP refuses arbitrary Secret/Volume mounting by default. Configure allowlists on the gateway Function if you need them.

Environment variables understood by the server:

```text
MODAL_WORKSPACE_ALLOWED_SECRETS=github-agent,huggingface-agent
MODAL_WORKSPACE_ALLOWED_VOLUMES=model-cache,workspace-cache
MODAL_WORKSPACE_SANDBOX_APP=modal-workspace-sandboxes
MODAL_WORKSPACE_MAX_OUTPUT_CHARS=120000
```

For example, create credentials as separate Modal Secrets:

```bash
modal secret create github-agent GH_TOKEN="$GH_TOKEN"
modal secret create huggingface-agent HF_TOKEN="$HF_TOKEN"
```

Then update the gateway Secret so those *Secret names* are explicitly allowlisted (their values are still kept in the separate Secrets):

```bash
modal secret create modal-workspace-mcp-auth \
  MODAL_WORKSPACE_MCP_TOKEN='<generated-token>' \
  MODAL_WORKSPACE_ALLOWED_SECRETS='github-agent,huggingface-agent'
```

## 3. Deploy

With Modal authenticated locally:

```bash
uv sync
uv run modal deploy modal_app.py
```

Modal will print the public Web Function URL. The MCP endpoint is that URL plus `/mcp/`.

Health check:

```bash
curl https://YOUR-ENDPOINT.modal.run/healthz
```

For MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
```

Use Streamable HTTP, URL:

```text
https://YOUR-ENDPOINT.modal.run/mcp/
```

and header:

```text
Authorization: Bearer <generated-token>
```

## 4. GitHub Copilot cloud agent

Configure these **Agents** values in the target GitHub repository:

```text
COPILOT_MCP_MODAL_URL=https://YOUR-ENDPOINT.modal.run
COPILOT_MCP_MODAL_GATEWAY_TOKEN=<generated-token>
```

Then use the repository MCP configuration from `.mcp.json`:

```json
{
  "mcpServers": {
    "modal-workspace": {
      "type": "http",
      "url": "${COPILOT_MCP_MODAL_URL}/mcp/",
      "headers": {
        "Authorization": "Bearer ${COPILOT_MCP_MODAL_GATEWAY_TOKEN}"
      },
      "tools": [
        "sandbox_create",
        "sandbox_exec",
        "sandbox_status",
        "sandbox_list",
        "sandbox_snapshot",
        "sandbox_terminate",
        "function_call",
        "app_get",
        "app_list"
      ]
    }
  }
}
```

GitHub Copilot cloud agent supports remote HTTP MCP servers and substitution of Agents secrets/variables prefixed with `COPILOT_MCP_`. OAuth-based remote MCP is deliberately not used here; the gateway uses a Bearer token.

## 4A. Install as a GitHub Copilot plugin

This repository is also a small Copilot plugin marketplace. After publishing it on GitHub, a target repository can enable the plugin with `.github/copilot/settings.json` using the template in `examples/github-copilot-settings.json`:

```json
{
  "enabledPlugins": {
    "modal-workspace@modal-workspace-mcp": true
  },
  "extraKnownMarketplaces": {
    "modal-workspace-mcp": {
      "source": {
        "source": "github",
        "repo": "xiaoqianran/modal-workspace-mcp"
      }
    }
  }
}
```

The marketplace entry points to `plugins/modal-workspace/`, whose `.mcp.json` connects Copilot to the deployed Modal HTTP MCP endpoint. For first debugging, you can also configure the same remote MCP directly in the repository's Copilot MCP settings before testing plugin installation.

## 5. First end-to-end test

Ask Copilot to do the equivalent of:

```text
1. Call sandbox_create with timeout_seconds=1800.
2. Call sandbox_exec on the returned sandbox_id with:
   apt-get update && apt-get install -y ffmpeg && git --version && curl -I https://github.com
3. Return the exit code and the last part of stdout/stderr.
4. Call sandbox_terminate.
```

A stronger test:

```text
Create a Modal Sandbox, clone a public GitHub repository into /root/repo,
install its dependencies, run its tests, report results, then terminate the Sandbox.
Do not use the local GitHub agent shell for network operations.
```

## Security model

- The HTTP MCP endpoint requires a bearer token.
- Sandbox Secret and Volume mounting is deny-by-default and allowlist-based.
- Secret **values** are never accepted as MCP tool arguments.
- Output is truncated to avoid runaway MCP responses.
- Sandboxes are tagged and isolated under a dedicated Modal App.
- Keep destructive operations inside the Sandbox.
- Prefer a dedicated GitHub token with minimum repository permissions rather than a broad personal token.

## Local validation

The repository contains dependency-free helper tests:

```bash
python -m unittest discover -s tests -v
python -m compileall modal_workspace_mcp modal_app.py
```

Full MCP/Modal integration testing requires Internet access and an authenticated Modal account.
