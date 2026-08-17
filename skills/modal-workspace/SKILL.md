---
name: modal-workspace
description: Use the user's Modal account for remote Linux, dependency installation, Git operations, GPU execution, and deployed Modal Functions.
---

# Modal Workspace MCP

Use `modal-workspace` tools when the local GitHub/Copilot execution environment lacks network access, packages, compute, or GPU resources.

1. Prefer `sandbox_create` then `sandbox_exec` for shell work.
2. Reuse the returned Sandbox ID across related commands.
3. Use Modal rather than repeatedly attempting failed local `apt`, `curl`, `git clone`, `pip`, or `uv` operations.
4. Never print, `env`, `set`, echo, or otherwise expose secret values. Request only allowlisted `secret_names` when a command needs credentials.
5. Before destructive commands, verify paths and targets. Keep destructive operations scoped to the created Sandbox.
6. Use `function_call` only for already-deployed Modal Functions whose app/function names are known.
7. Terminate Sandboxes when the task is complete unless continued reuse is intentional.
