import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, Response, status

from .config import Settings

SESSION_COOKIE = "resume_review_session"
FEISHU_STATE_COOKIE = "resume_review_feishu_state"
OAUTH_STATE_TTL_SECONDS = 600


@dataclass(frozen=True)
class Session:
    session_id: str
    authenticated: bool
    expires_at: int
    auth_provider: str | None = None
    principal_id: str | None = None
    display_name: str | None = None


class SessionManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._secret = (settings.session_secret or secrets.token_urlsafe(48)).encode()

    @property
    def auth_required(self) -> bool:
        return self.access_code_enabled or self.feishu_enabled

    @property
    def access_code_enabled(self) -> bool:
        return bool(self.settings.app_access_code)

    @property
    def feishu_enabled(self) -> bool:
        return self.settings.feishu_login_enabled

    @property
    def auth_methods(self) -> dict[str, bool]:
        return {
            "feishu": self.feishu_enabled,
            "access_code": self.access_code_enabled,
        }

    def _signature(self, payload: str) -> str:
        return hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _encode(payload: dict) -> str:
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    @staticmethod
    def _decode(payload: str) -> dict:
        padding = "=" * (-len(payload) % 4)
        value = json.loads(base64.urlsafe_b64decode(payload + padding))
        if not isinstance(value, dict):
            raise ValueError("session payload must be an object")
        return value

    def issue(
        self,
        authenticated: bool,
        *,
        auth_provider: str | None = None,
        principal_id: str | None = None,
        display_name: str | None = None,
    ) -> tuple[Session, str]:
        session = Session(
            session_id=secrets.token_urlsafe(24),
            authenticated=authenticated,
            expires_at=int(time.time()) + self.settings.session_ttl_seconds,
            auth_provider=auth_provider,
            principal_id=principal_id,
            display_name=display_name,
        )
        payload = self._encode(
            {
                "v": 2,
                "sid": session.session_id,
                "exp": session.expires_at,
                "auth": session.authenticated,
                "provider": session.auth_provider,
                "principal": session.principal_id,
                "name": session.display_name,
            }
        )
        return session, f"{payload}.{self._signature(payload)}"

    def parse(self, token: str | None) -> Session | None:
        if not token:
            return None
        try:
            payload, signature = token.rsplit(".", 1)
            if not hmac.compare_digest(signature, self._signature(payload)):
                return None
            if payload.count(".") == 2:
                return self._parse_legacy(payload)
            data = self._decode(payload)
            if data.get("v") != 2:
                return None
            expires_at = int(data["exp"])
            if expires_at <= int(time.time()):
                return None
            return Session(
                session_id=str(data["sid"]),
                authenticated=data.get("auth") is True,
                expires_at=expires_at,
                auth_provider=(
                    str(data["provider"]) if data.get("provider") is not None else None
                ),
                principal_id=(
                    str(data["principal"])
                    if data.get("principal") is not None
                    else None
                ),
                display_name=(
                    str(data["name"]) if data.get("name") is not None else None
                ),
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return None

    def _parse_legacy(self, payload: str) -> Session | None:
        try:
            session_id, expires_at_text, authenticated_text = payload.split(".", 2)
            payload = f"{session_id}.{expires_at_text}.{authenticated_text}"
            expires_at = int(expires_at_text)
            if expires_at <= int(time.time()):
                return None
            return Session(
                session_id=session_id,
                authenticated=authenticated_text == "1",
                expires_at=expires_at,
            )
        except (TypeError, ValueError):
            return None

    def from_request(self, request: Request) -> Session | None:
        return self.parse(request.cookies.get(SESSION_COOKIE))

    def require(self, request: Request) -> Session:
        session = self.from_request(request)
        if not session or (self.auth_required and not session.authenticated):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="请先输入访问口令",
            )
        return session

    def verify_access_code(self, access_code: str) -> bool:
        if not self.access_code_enabled:
            return False
        return hmac.compare_digest(access_code, self.settings.app_access_code)

    def principal_id(self, provider: str, external_id: str) -> str:
        digest = hmac.new(
            self._secret,
            f"{provider}:{external_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return digest[:32]

    def create_oauth_state(self) -> tuple[str, str]:
        state = secrets.token_urlsafe(32)
        payload = self._encode(
            {
                "v": 1,
                "state": state,
                "exp": int(time.time()) + OAUTH_STATE_TTL_SECONDS,
            }
        )
        return state, f"{payload}.{self._signature(payload)}"

    def verify_oauth_state(self, state: str | None, token: str | None) -> bool:
        if not state or not token:
            return False
        try:
            payload, signature = token.rsplit(".", 1)
            if not hmac.compare_digest(signature, self._signature(payload)):
                return False
            data = self._decode(payload)
            return (
                data.get("v") == 1
                and int(data["exp"]) > int(time.time())
                and isinstance(data.get("state"), str)
                and hmac.compare_digest(state, data["state"])
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return False

    def set_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            max_age=self.settings.session_ttl_seconds,
            httponly=True,
            secure=self.settings.session_cookie_secure,
            samesite="strict",
            path="/",
        )

    def delete_cookie(self, response: Response) -> None:
        response.delete_cookie(
            SESSION_COOKIE,
            path="/",
            secure=self.settings.session_cookie_secure,
            httponly=True,
            samesite="strict",
        )

    def set_oauth_state_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            key=FEISHU_STATE_COOKIE,
            value=token,
            max_age=OAUTH_STATE_TTL_SECONDS,
            httponly=True,
            secure=self.settings.session_cookie_secure,
            samesite="lax",
            path="/api/auth/feishu/callback",
        )

    def delete_oauth_state_cookie(self, response: Response) -> None:
        response.delete_cookie(
            FEISHU_STATE_COOKIE,
            path="/api/auth/feishu/callback",
            secure=self.settings.session_cookie_secure,
            httponly=True,
            samesite="lax",
        )


class LoginThrottle:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, ip_address: str) -> bool:
        now = time.monotonic()
        attempts = self._attempts[ip_address]
        while attempts and attempts[0] <= now - self.window_seconds:
            attempts.popleft()
        if len(attempts) >= self.max_attempts:
            return False
        attempts.append(now)
        return True


def client_ip(request: Request, trust_proxy_headers: bool) -> str:
    if trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        addresses = [value.strip() for value in forwarded.split(",") if value.strip()]
        if addresses:
            # A trusted reverse proxy sits directly in front of the app. The
            # right-most address cannot be supplied without passing through it.
            return addresses[-1]
    return request.client.host if request.client else "unknown"
