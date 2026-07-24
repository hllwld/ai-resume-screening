import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings, get_settings
from .dify import DifyClient
from .export import build_workbook
from .feishu import FeishuAuthClient, FeishuAuthError
from .models import BatchCreate
from .quota import DailyQuota, QuotaExceeded
from .security import (
    FEISHU_STATE_COOKIE,
    LoginThrottle,
    Session,
    SessionManager,
    client_ip,
)
from .tasks import TaskStore

settings = get_settings()
store = TaskStore(settings)
client = DifyClient(settings)
feishu_client = FeishuAuthClient(settings)
quota = DailyQuota(settings)
sessions = SessionManager(settings)
login_throttle = LoginThrottle()


class LoginRequest(BaseModel):
    access_code: str = Field(min_length=1, max_length=256)


def production_configuration_errors(config: Settings) -> list[str]:
    errors = []
    if not config.dify_api_key:
        errors.append("DIFY_API_KEY")
    if not config.app_access_code and not config.feishu_login_enabled:
        errors.append("至少启用 APP_ACCESS_CODE 或 FEISHU_LOGIN_ENABLED")
    if config.app_access_code and len(config.app_access_code) < 12:
        errors.append("APP_ACCESS_CODE（启用时至少 12 个字符）")
    if len(config.session_secret) < 32:
        errors.append("SESSION_SECRET（至少 32 个字符）")
    if config.feishu_login_enabled:
        if not config.feishu_app_id:
            errors.append("FEISHU_APP_ID")
        if not config.feishu_app_secret:
            errors.append("FEISHU_APP_SECRET")
        if not config.feishu_redirect_uri.startswith("https://"):
            errors.append("FEISHU_REDIRECT_URI（生产环境必须使用 HTTPS）")
    return errors


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.environment == "production":
        errors = production_configuration_errors(settings)
        if errors:
            raise RuntimeError(f"生产环境缺少安全配置：{', '.join(errors)}")

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
    await feishu_client.close()


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


async def session_payload(session: Session, request: Request) -> dict:
    ip_address = client_ip(request, settings.trust_proxy_headers)
    current_quota = await quota.current(ip_address)
    return {
        "authenticated": session.authenticated or not sessions.auth_required,
        "auth_required": sessions.auth_required,
        "auth_methods": sessions.auth_methods,
        "auth_provider": session.auth_provider,
        "display_name": session.display_name,
        "expires_at": session.expires_at,
        "quota": current_quota.public_dict(),
    }


@app.get("/api/session")
async def get_session(request: Request, response: Response):
    session = sessions.from_request(request)
    if not session:
        session, token = sessions.issue(authenticated=not sessions.auth_required)
        sessions.set_cookie(response, token)
    return await session_payload(session, request)


@app.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    if not sessions.access_code_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="访问口令登录未启用",
        )
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
    session, token = sessions.issue(
        authenticated=True,
        auth_provider="access_code",
        display_name="口令访客",
    )
    sessions.set_cookie(response, token)
    return await session_payload(session, request)


@app.get("/api/auth/feishu/start")
async def start_feishu_login():
    if not sessions.feishu_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="飞书登录未启用",
        )
    state, state_token = sessions.create_oauth_state()
    response = RedirectResponse(
        feishu_client.authorization_url(state),
        status_code=status.HTTP_302_FOUND,
    )
    sessions.set_oauth_state_cookie(response, state_token)
    return response


@app.get("/api/auth/feishu/callback")
async def finish_feishu_login(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    def failed(error_code: str) -> RedirectResponse:
        response = RedirectResponse(
            f"/?auth_error={error_code}",
            status_code=status.HTTP_302_FOUND,
        )
        sessions.delete_oauth_state_cookie(response)
        return response

    if not sessions.feishu_enabled:
        return failed("disabled")
    state_token = request.cookies.get(FEISHU_STATE_COOKIE)
    if not sessions.verify_oauth_state(state, state_token):
        return failed("invalid_state")
    if error or not code:
        return failed("cancelled")
    try:
        user = await feishu_client.get_user(code)
    except FeishuAuthError as exc:
        return failed(exc.code)

    principal_id = sessions.principal_id("feishu", user.open_id)
    session, token = sessions.issue(
        authenticated=True,
        auth_provider="feishu",
        principal_id=principal_id,
        display_name=user.display_name[:80],
    )
    response = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    sessions.delete_oauth_state_cookie(response)
    sessions.set_cookie(response, token)
    return response


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
