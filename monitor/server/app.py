"""The dashboard's FastAPI app: localhost-only, read-only over monitoring data, every response re-redacted."""
import secrets

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

from monitor.server.jobs import JobRunner
from monitor.server.logs import LogStore
from monitor.server.routes_jobs import jobs_router
from monitor.server.routes_live import live_router
from monitor.server.routes_offline import offline_router
from monitor.server.settings import BUILD_HINT, ServerSettings

TOKEN_PLACEHOLDER = "__MONITOR_TOKEN__"


def token_guard(token: str):
    """Dependency for state-changing routes: the X-Monitor-Token header must equal this launch's token."""
    expected = token.encode()

    def require_token(x_monitor_token: str = Header(default="")):
        if not secrets.compare_digest(x_monitor_token.encode(), expected):
            raise HTTPException(status_code=403, detail="missing or invalid run token")

    return require_token


def create_app(settings: ServerSettings, *, scan_fn=None, eval_fn=None) -> FastAPI:
    if not settings.token:
        raise ValueError("ServerSettings.token must be a non-empty string")
    app = FastAPI(title="Agent Monitor dashboard", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    allowed_hosts = {f"127.0.0.1:{settings.port}", f"localhost:{settings.port}"}

    @app.middleware("http")
    async def host_check(request: Request, call_next):
        # DNS-rebinding defence: another site that resolves to 127.0.0.1 still sends its own Host header.
        if request.headers.get("host", "") not in allowed_hosts:
            return JSONResponse({"error": "forbidden host"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    # API routers are included here, before the page route below (which catches every other GET).
    app.include_router(live_router(settings, LogStore()))
    app.include_router(offline_router(settings))
    if scan_fn is None or eval_fn is None:
        from monitor.runs import run_eval, run_scan
        scan_fn, eval_fn = scan_fn or run_scan, eval_fn or run_eval
    app.state.jobs = JobRunner()
    app.include_router(jobs_router(settings, app.state.jobs, token_guard(settings.token), scan_fn, eval_fn))

    _add_page_route(app, settings)
    return app


def _add_page_route(app: FastAPI, settings: ServerSettings) -> None:
    dist = settings.dist().resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def page(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="no such API endpoint")
        index = dist / "index.html"
        if not index.is_file():
            return PlainTextResponse(f"The dashboard is not built. Run: {BUILD_HINT}", status_code=503)
        if path and path != "index.html":
            candidate = (dist / path).resolve()
            if candidate.is_file() and dist in candidate.parents:
                return FileResponse(candidate)
        return HTMLResponse(index.read_text().replace(TOKEN_PLACEHOLDER, settings.token))
