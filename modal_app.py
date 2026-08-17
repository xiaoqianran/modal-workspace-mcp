from __future__ import annotations

import hmac
import os

import modal

from modal_workspace_mcp.config import GATEWAY_SECRET_NAME

app = modal.App("modal-workspace-mcp")

gateway_image = modal.Image.debian_slim(python_version="3.12").uv_pip_install(
    "fastapi==0.115.14",
    "fastmcp==2.10.6",
    "pydantic==2.11.10",
)


@app.function(
    image=gateway_image,
    secrets=[modal.Secret.from_name(GATEWAY_SECRET_NAME)],
    timeout=3600,
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from starlette.middleware.base import BaseHTTPMiddleware

    from modal_workspace_mcp.server import make_mcp_server

    class BearerAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Health is intentionally public; all MCP traffic is authenticated.
            if request.url.path.startswith("/mcp"):
                expected = os.getenv("MODAL_WORKSPACE_MCP_TOKEN")
                auth = request.headers.get("authorization", "")
                supplied = auth[7:] if auth.startswith("Bearer ") else ""
                if not expected:
                    return JSONResponse(
                        {"error": "gateway authentication is not configured"}, status_code=503
                    )
                if not supplied or not hmac.compare_digest(supplied, expected):
                    return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    mcp = make_mcp_server()
    mcp_app = mcp.http_app(transport="streamable-http", stateless_http=True)

    api = FastAPI(lifespan=mcp_app.router.lifespan_context)
    api.add_middleware(BearerAuthMiddleware)

    @api.get("/healthz")
    async def healthz():
        return {"ok": True, "service": "modal-workspace-mcp"}

    api.mount("/", mcp_app, name="mcp")
    return api
