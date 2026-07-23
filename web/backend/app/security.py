import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, Response, status

from .config import Settings

SESSION_COOKIE = "resume_review_session"


@dataclass(frozen=True)
class Session:
    session_id: str
    authenticated: bool
    expires_at: int


class SessionManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._secret = (settings.session_secret or secrets.token_urlsafe(48)).encode()

    @property
    def auth_required(self) -> bool:
        return bool(self.settings.app_access_code)

    def _signature(self, payload: str) -> str:
        return hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()

    def issue(self, authenticated: bool) -> tuple[Session, str]:
        session = Session(
            session_id=secrets.token_urlsafe(24),
            authenticated=authenticated,
            expires_at=int(time.time()) + self.settings.session_ttl_seconds,
        )
        payload = (
            f"{session.session_id}.{session.expires_at}."
            f"{1 if session.authenticated else 0}"
        )
        return session, f"{payload}.{self._signature(payload)}"

    def parse(self, token: str | None) -> Session | None:
        if not token:
            return None
        try:
            session_id, expires_at_text, authenticated_text, signature = token.split(".", 3)
            payload = f"{session_id}.{expires_at_text}.{authenticated_text}"
            if not hmac.compare_digest(signature, self._signature(payload)):
                return None
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
        if not self.auth_required:
            return True
        return hmac.compare_digest(access_code, self.settings.app_access_code)

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
            # Render sits directly in front of the app. The right-most address cannot
            # be supplied without passing through that trusted proxy.
            return addresses[-1]
    return request.client.host if request.client else "unknown"
