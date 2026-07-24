import asyncio
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.feishu import (
    FEISHU_APP_TOKEN_URL,
    FEISHU_USER_INFO_URL,
    FEISHU_USER_TOKEN_URL,
    FeishuAuthClient,
    FeishuAuthError,
    FeishuUser,
)
from app.main import (
    app,
    feishu_client,
    production_configuration_errors,
    settings,
)


def enable_feishu(monkeypatch) -> None:
    monkeypatch.setattr(settings, "feishu_login_enabled", True)
    monkeypatch.setattr(settings, "feishu_app_id", "cli_test")
    monkeypatch.setattr(settings, "feishu_app_secret", "test-secret")
    monkeypatch.setattr(
        settings,
        "feishu_redirect_uri",
        "https://testserver/api/auth/feishu/callback",
    )


def test_feishu_login_callback_creates_session_and_consumes_state(monkeypatch):
    enable_feishu(monkeypatch)

    async def fake_get_user(code: str) -> FeishuUser:
        assert code == "valid-code"
        return FeishuUser(open_id="ou_test_user", display_name="飞书测试用户")

    monkeypatch.setattr(feishu_client, "get_user", fake_get_user)
    with TestClient(
        app,
        base_url="https://testserver",
        follow_redirects=False,
    ) as test_client:
        start = test_client.get("/api/auth/feishu/start")
        assert start.status_code == 302
        location = urlparse(start.headers["location"])
        query = parse_qs(location.query)
        assert location.netloc == "accounts.feishu.cn"
        assert query["app_id"] == ["cli_test"]
        state = query["state"][0]

        callback_url = (
            f"/api/auth/feishu/callback?code=valid-code&state={state}"
        )
        callback = test_client.get(callback_url)
        assert callback.status_code == 302
        assert callback.headers["location"] == "/"

        session = test_client.get("/api/session").json()
        assert session["authenticated"] is True
        assert session["auth_provider"] == "feishu"
        assert session["display_name"] == "飞书测试用户"
        assert "principal_id" not in session
        assert "open_id" not in session
        assert session["auth_methods"] == {
            "feishu": True,
            "access_code": bool(settings.app_access_code),
        }

        logout = test_client.post("/api/auth/logout")
        assert logout.status_code == 204
        assert test_client.get("/api/session").json()["authenticated"] is False

        replay = test_client.get(callback_url)
        assert replay.status_code == 302
        assert replay.headers["location"] == "/?auth_error=invalid_state"


def test_feishu_callback_rejects_invalid_state_and_safe_provider_error(monkeypatch):
    enable_feishu(monkeypatch)

    async def failed_get_user(_: str) -> FeishuUser:
        raise FeishuAuthError("provider_unavailable")

    monkeypatch.setattr(feishu_client, "get_user", failed_get_user)
    with TestClient(
        app,
        base_url="https://testserver",
        follow_redirects=False,
    ) as test_client:
        invalid = test_client.get(
            "/api/auth/feishu/callback?code=secret-code&state=invalid"
        )
        assert invalid.headers["location"] == "/?auth_error=invalid_state"

        start = test_client.get("/api/auth/feishu/start")
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        failed = test_client.get(
            f"/api/auth/feishu/callback?code=secret-code&state={state}"
        )
        assert failed.headers["location"] == "/?auth_error=provider_unavailable"
        assert "secret-code" not in failed.headers["location"]

        cancelled_start = test_client.get("/api/auth/feishu/start")
        cancelled_state = parse_qs(
            urlparse(cancelled_start.headers["location"]).query
        )["state"][0]
        cancelled = test_client.get(
            f"/api/auth/feishu/callback?error=access_denied&state={cancelled_state}"
        )
        assert cancelled.headers["location"] == "/?auth_error=cancelled"


def test_feishu_client_uses_server_side_tokens_and_minimal_identity():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == FEISHU_APP_TOKEN_URL:
            assert b"test-secret" in request.content
            return httpx.Response(
                200,
                json={"code": 0, "app_access_token": "app-token"},
            )
        if str(request.url) == FEISHU_USER_TOKEN_URL:
            assert request.headers["authorization"] == "Bearer app-token"
            return httpx.Response(
                200,
                json={"code": 0, "data": {"access_token": "user-token"}},
            )
        if str(request.url) == FEISHU_USER_INFO_URL:
            assert request.headers["authorization"] == "Bearer user-token"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "open_id": "ou_test_user",
                        "name": "测试用户",
                        "email": "must-not-be-used@example.com",
                    },
                },
            )
        raise AssertionError(f"unexpected request: {request.url}")

    async def run() -> FeishuUser:
        auth_client = FeishuAuthClient(
            Settings(
                feishu_app_id="cli_test",
                feishu_app_secret="test-secret",
                feishu_redirect_uri="https://example.com/callback",
            ),
            transport=httpx.MockTransport(handler),
        )
        try:
            return await auth_client.get_user("authorization-code")
        finally:
            await auth_client.close()

    user = asyncio.run(run())
    assert user == FeishuUser(open_id="ou_test_user", display_name="测试用户")
    assert calls == [
        FEISHU_APP_TOKEN_URL,
        FEISHU_USER_TOKEN_URL,
        FEISHU_USER_INFO_URL,
    ]


def test_feishu_client_rejects_missing_identity_and_network_failure():
    def missing_identity(request: httpx.Request) -> httpx.Response:
        if str(request.url) == FEISHU_APP_TOKEN_URL:
            return httpx.Response(
                200,
                json={"code": 0, "app_access_token": "app-token"},
            )
        if str(request.url) == FEISHU_USER_TOKEN_URL:
            return httpx.Response(
                200,
                json={"code": 0, "data": {"access_token": "user-token"}},
            )
        return httpx.Response(200, json={"code": 0, "data": {"name": "无标识用户"}})

    async def run_missing_identity() -> str:
        auth_client = FeishuAuthClient(
            Settings(
                feishu_app_id="cli_test",
                feishu_app_secret="test-secret",
            ),
            transport=httpx.MockTransport(missing_identity),
        )
        try:
            await auth_client.get_user("authorization-code")
        except FeishuAuthError as exc:
            return exc.code
        finally:
            await auth_client.close()
        raise AssertionError("missing identity must fail")

    def network_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async def run_network_failure() -> str:
        auth_client = FeishuAuthClient(
            Settings(
                feishu_app_id="cli_test",
                feishu_app_secret="test-secret",
            ),
            transport=httpx.MockTransport(network_failure),
        )
        try:
            await auth_client.get_user("authorization-code")
        except FeishuAuthError as exc:
            return exc.code
        finally:
            await auth_client.close()
        raise AssertionError("network failure must fail")

    assert asyncio.run(run_missing_identity()) == "user_unavailable"
    assert asyncio.run(run_network_failure()) == "provider_unavailable"


def test_production_auth_configuration_validation():
    valid = Settings(
        environment="production",
        dify_api_key="dify-key",
        session_secret="s" * 32,
        feishu_login_enabled=True,
        feishu_app_id="cli_test",
        feishu_app_secret="app-secret",
        feishu_redirect_uri="https://zerodot.top/api/auth/feishu/callback",
    )
    assert production_configuration_errors(valid) == []

    invalid = valid.model_copy(
        update={
            "feishu_app_secret": "",
            "feishu_redirect_uri": "http://example.com/callback",
        }
    )
    errors = production_configuration_errors(invalid)
    assert "FEISHU_APP_SECRET" in errors
    assert "FEISHU_REDIRECT_URI（生产环境必须使用 HTTPS）" in errors
