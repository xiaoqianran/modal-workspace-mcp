import os

import modal

from modal_workspace_mcp.config import GATEWAY_APP_NAME, GATEWAY_SECRET_NAME

app = modal.App(GATEWAY_APP_NAME)

gateway_image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install(
        "modal==1.5.4",
        "fastapi==0.115.14",
        "fastmcp==2.10.6",
        "pydantic==2.11.10",
    )
    .add_local_python_source("modal_workspace_mcp")
)


@app.function(
    image=gateway_image,
    secrets=[modal.Secret.from_name(GATEWAY_SECRET_NAME)],
    timeout=3600,
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, PlainTextResponse

    from modal_workspace_mcp.action_api import router as action_router
    from modal_workspace_mcp.helpers import require_bearer_token
    from modal_workspace_mcp.server import make_mcp_server

    class GatewayAuthMiddleware:
        """纯 ASGI Bearer 鉴权，避免 BaseHTTPMiddleware 干扰 MCP streaming。"""

        def __init__(self, inner):
            self.inner = inner

        async def __call__(self, scope, receive, send):
            if scope.get("type") != "http":
                return await self.inner(scope, receive, send)
            path = scope.get("path", "")
            protected = path.startswith("/mcp") or path.startswith("/api")
            if not protected:
                return await self.inner(scope, receive, send)
            headers = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in scope.get("headers", [])
            }
            expected = os.getenv("MODAL_WORKSPACE_MCP_TOKEN")
            if not expected:
                response = JSONResponse(
                    {"error": "网关尚未配置 MODAL_WORKSPACE_MCP_TOKEN"},
                    status_code=503,
                )
                return await response(scope, receive, send)
            if not require_bearer_token(headers.get("authorization"), expected):
                response = JSONResponse({"error": "unauthorized"}, status_code=401)
                return await response(scope, receive, send)
            return await self.inner(scope, receive, send)

    mcp = make_mcp_server()
    mcp_app = mcp.http_app(transport="streamable-http", stateless_http=True)

    api = FastAPI(
        title="Modal Workspace Gateway",
        version="0.5.0",
        description=(
            "实时 Remote Workspace：稳定 ws-*、增量事件流、GitHub Repo clone/fetch/checkout/status/diff，"
            "以及底层 Modal Sandbox / Function 能力。"
        ),
        lifespan=mcp_app.router.lifespan_context,
    )
    api.include_router(action_router)

    @api.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError):
        return JSONResponse(
            {"error": str(exc), "type": exc.__class__.__name__},
            status_code=400,
        )

    @api.exception_handler(Exception)
    async def modal_error_handler(_: Request, exc: Exception):
        try:
            from modal import exception as modal_exc

            mapping = (
                (modal_exc.NotFoundError, 404),
                (modal_exc.AlreadyExistsError, 409),
                (modal_exc.ConflictError, 409),
                (modal_exc.PermissionDeniedError, 403),
                (modal_exc.AuthError, 401),
                (modal_exc.ResourceExhaustedError, 429),
                (modal_exc.TimeoutError, 504),
            )
            for kind, status in mapping:
                if isinstance(exc, kind):
                    return JSONResponse(
                        {"error": str(exc), "type": exc.__class__.__name__},
                        status_code=status,
                    )
        except Exception:
            pass
        return JSONResponse(
            {"error": str(exc), "type": exc.__class__.__name__},
            status_code=502,
        )

    @api.get("/", include_in_schema=False)
    async def root():
        return {
            "ok": True,
            "service": "modal-workspace-mcp",
            "version": "0.5.0",
            "mode": "realtime-workspace-repo",
            "health": "/healthz",
            "mcp": "/mcp/",
            "gpt_actions_schema": "/action-openapi.json",
        }

    @api.get("/healthz", include_in_schema=False)
    async def healthz():
        return {
            "ok": True,
            "service": "modal-workspace-mcp",
            "version": "0.5.0",
            "realtime_exec": True,
            "workspace": True,
            "github_repo": True,
            "mcp": "/mcp/",
            "gpt_actions_schema": "/action-openapi.json",
        }

    @api.get("/privacy", include_in_schema=False, response_class=PlainTextResponse)
    async def privacy():
        return (
            "modal-workspace-mcp 是私有远程执行桥。请求被转发到服务所有者的 Modal 账户。"
            "请不要在聊天提示词、命令或普通参数中明文发送密钥；使用 Modal Secret allowlist。"
        )

    @api.get("/action-openapi.json", include_in_schema=False)
    async def action_openapi(request: Request):
        schema = api.openapi()
        schema["servers"] = [{"url": str(request.base_url).rstrip("/")}]
        schema.setdefault("components", {}).setdefault("securitySchemes", {})[
            "GatewayBearer"
        ] = {
            "type": "http",
            "scheme": "bearer",
        }
        schema["security"] = [{"GatewayBearer": []}]
        schema["info"]["x-privacy-policy-url"] = str(request.url_for("privacy"))
        return JSONResponse(schema, headers={"Cache-Control": "no-store"})

    api.mount("/", mcp_app, name="mcp")
    return GatewayAuthMiddleware(api)
