from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from .config import Settings

FEISHU_AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
FEISHU_APP_TOKEN_URL = (
    "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal"
)
FEISHU_USER_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v1/access_token"
FEISHU_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


class FeishuAuthError(Exception):
    """A safe, user-facing category for a failed Feishu authentication step."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class FeishuUser:
    open_id: str
    display_name: str


class FeishuAuthClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.settings = settings
        self._client = httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=False,
            transport=transport,
        )

    def authorization_url(self, state: str) -> str:
        query = urlencode(
            {
                "app_id": self.settings.feishu_app_id,
                "redirect_uri": self.settings.feishu_redirect_uri,
                "state": state,
            }
        )
        return f"{FEISHU_AUTHORIZE_URL}?{query}"

    async def get_user(self, code: str) -> FeishuUser:
        try:
            app_token = await self._get_app_access_token()
            user_token = await self._get_user_access_token(code, app_token)
            return await self._get_user_info(user_token)
        except FeishuAuthError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise FeishuAuthError("provider_unavailable") from exc

    async def _get_app_access_token(self) -> str:
        response = await self._client.post(
            FEISHU_APP_TOKEN_URL,
            json={
                "app_id": self.settings.feishu_app_id,
                "app_secret": self.settings.feishu_app_secret,
            },
        )
        payload = self._success_payload(response)
        token = payload.get("app_access_token")
        if not isinstance(token, str) or not token:
            raise FeishuAuthError("provider_unavailable")
        return token

    async def _get_user_access_token(self, code: str, app_token: str) -> str:
        response = await self._client.post(
            FEISHU_USER_TOKEN_URL,
            headers={"Authorization": f"Bearer {app_token}"},
            json={"grant_type": "authorization_code", "code": code},
        )
        payload = self._success_payload(response)
        data = payload.get("data")
        token = data.get("access_token") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            raise FeishuAuthError("token_failed")
        return token

    async def _get_user_info(self, user_token: str) -> FeishuUser:
        response = await self._client.get(
            FEISHU_USER_INFO_URL,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        payload = self._success_payload(response)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise FeishuAuthError("user_unavailable")
        open_id = data.get("open_id")
        if not isinstance(open_id, str) or not open_id:
            raise FeishuAuthError("user_unavailable")
        name = data.get("name")
        display_name = name.strip() if isinstance(name, str) else ""
        return FeishuUser(open_id=open_id, display_name=display_name or "飞书用户")

    @staticmethod
    def _success_payload(response: httpx.Response) -> dict:
        if response.status_code >= 400:
            raise FeishuAuthError("provider_unavailable")
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("code", 0) != 0:
            raise FeishuAuthError("provider_unavailable")
        return payload

    async def close(self) -> None:
        await self._client.aclose()
