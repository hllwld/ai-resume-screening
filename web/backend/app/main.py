import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import get_settings
from .dify import DifyClient
from .export import build_workbook
from .models import BatchCreate
from .quota import DailyQuota, QuotaExceeded
from .security import LoginThrottle, SessionManager, client_ip
from .tasks import TaskStore

settings = get_settings()
store = TaskStore(settings)
client = DifyClient(settings)
quota = DailyQuota(settings)
sessions = SessionManager(settings)
login_throttle = LoginThrottle()


class LoginRequest(BaseModel):
    access_code: str = Field(min_length=1, max_length=256)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.environment == "production":
        missing = []
        if not settings.dify_api_key:
            missing.append("DIFY_API_KEY")
        if not settings.app_access_code:
            missing.append("APP_ACCESS_CODE")
        if len(settings.session_secret) < 32:
            missing.append("SESSION_SECRET（至少 32 个字符）")
        if missing:
            raise RuntimeError(f"生产环境缺少安全配置：{', '.join(missing)}")
    async def cleanup_expired_tasks() -> None:
        while True:
            await asyncio.sleep(min(60, max(5, settings.task_ttl_seconds)))
            store.cleanup()

    cleanup_runner = asyncio.create_task(cleanup_expired_tasks())
    yield
    cleanup_runner.cancel()
    with suppress(asyncio.CancelledError):
        await cleanup_runner
    await client.close()


app = FastAPI(
    title="AI 简历评估工作台 API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None if settings.environment == "production" else "/redoc",
    openapi_url=None if settings.environment == "production" else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        [] if settings.environment == "production" else settings.cors_origin_list
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_request_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "请求内容过大"},
                )
        except ValueError:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Content-Length 无效"},
            )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if settings.session_cookie_secure:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/session")
async def get_session(request: Request, response: Response):
    session = sessions.from_request(request)
    if not session:
        session, token = sessions.issue(authenticated=not sessions.auth_required)
        sessions.set_cookie(response, token)
    ip_address = client_ip(request, settings.trust_proxy_headers)
    current_quota = await quota.current(ip_address)
    return {
        "authenticated": session.authenticated or not sessions.auth_required,
        "auth_required": sessions.auth_required,
        "expires_at": session.expires_at,
        "quota": current_quota.public_dict(),
    }


@app.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    ip_address = client_ip(request, settings.trust_proxy_headers)
    if not login_throttle.allow(ip_address):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="口令尝试次数过多，请稍后再试",
        )
    if not sessions.verify_access_code(payload.access_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="访问口令不正确",
        )
    session, token = sessions.issue(authenticated=True)
    sessions.set_cookie(response, token)
    current_quota = await quota.current(ip_address)
    return {
        "authenticated": True,
        "auth_required": sessions.auth_required,
        "expires_at": session.expires_at,
        "quota": current_quota.public_dict(),
    }


@app.post("/api/auth/logout", status_code=204)
async def logout(response: Response):
    sessions.delete_cookie(response)


@app.post("/api/batches", status_code=202)
async def create_batch(payload: BatchCreate, request: Request):
    session = sessions.require(request)
    store.cleanup()
    ip_address = client_ip(request, settings.trust_proxy_headers)
    try:
        current_quota = await quota.reserve(ip_address, len(payload.candidates))
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": str(exc),
                "quota": exc.snapshot.public_dict(),
            },
        ) from exc
    task = await store.create(payload, client, session.session_id)
    result = task.public_dict()
    result["quota"] = current_quota.public_dict()
    return result


@app.get("/api/batches/{task_id}")
async def get_batch(task_id: str, request: Request):
    session = sessions.require(request)
    store.cleanup()
    task = store.get_owned(task_id, session.session_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在、已过期或无权访问")
    return task.public_dict()


@app.post("/api/batches/{task_id}/cancel")
async def cancel_batch(task_id: str, request: Request):
    session = sessions.require(request)
    task = store.get_owned(task_id, session.session_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在、已过期或无权访问")
    return store.cancel(task_id).public_dict()


@app.delete("/api/batches/{task_id}", status_code=204)
async def delete_batch(task_id: str, request: Request):
    session = sessions.require(request)
    task = store.get_owned(task_id, session.session_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在、已过期或无权访问")
    await store.delete(task_id)


@app.get("/api/batches/{task_id}/export.xlsx")
async def export_batch(task_id: str, request: Request):
    session = sessions.require(request)
    task = store.get_owned(task_id, session.session_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在、已过期或无权访问")
    if not any(item.result for item in task.items):
        raise HTTPException(status_code=409, detail="暂无可导出的成功结果")
    data = build_workbook(task)
    filename = f"candidate-review-{task_id[:8]}.xlsx"
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
