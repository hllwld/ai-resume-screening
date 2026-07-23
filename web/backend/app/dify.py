import asyncio
import json
import re
from typing import Any

import httpx

from .config import Settings
from .models import EvaluationResult


class DifyError(RuntimeError):
    pass


def _extract_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise DifyError("Dify 未返回可解析的结果")

    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", value, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise DifyError("模型输出不是合法 JSON") from exc
    if not isinstance(parsed, dict):
        raise DifyError("模型结果必须是 JSON 对象")
    return parsed


def normalize_dify_response(payload: dict[str, Any]) -> EvaluationResult:
    data = payload.get("data", payload)
    outputs = data.get("outputs", data)
    if not isinstance(outputs, dict):
        raise DifyError("Dify 响应缺少 outputs")

    candidate: dict[str, Any]
    if isinstance(outputs.get("parsed_json"), str):
        candidate = _extract_json(outputs["parsed_json"])
    elif isinstance(outputs.get("result"), (str, dict)):
        candidate = _extract_json(outputs["result"])
    else:
        candidate = outputs

    # 兼容当前 DSL 已展平的字段。
    if "dimension_scores" not in candidate and "skill_match" in outputs:
        candidate["dimension_scores"] = {
            "skill_match": outputs.get("skill_match", 0),
            "experience_relevance": outputs.get("experience_relevance", 0),
            "project_relevance": outputs.get("project_relevance", 0),
            "overall_quality": outputs.get("overall_quality", 0),
        }
    for key in ("candidate_name", "match_score", "recommendation"):
        if key not in candidate and key in outputs:
            candidate[key] = outputs[key]

    return EvaluationResult.model_validate(candidate)


class DifyClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.dify_base_url.rstrip("/"),
            timeout=settings.dify_timeout_seconds,
            headers={
                "Authorization": f"Bearer {settings.dify_api_key}",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def evaluate(
        self,
        resume_text: str,
        job_description: str,
        custom_instructions: str,
        user_id: str,
    ) -> EvaluationResult:
        if not self.settings.dify_api_key:
            raise DifyError("后端尚未配置 DIFY_API_KEY")

        body = {
            "inputs": {
                "resume_text": resume_text,
                "job_description": job_description,
                "custom_instructions": custom_instructions,
            },
            "response_mode": "blocking",
            "user": user_id,
        }
        retryable = {429, 500, 502, 503, 504}
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                response = await self._client.post("/workflows/run", json=body)
                if response.status_code in retryable:
                    raise httpx.HTTPStatusError(
                        f"Dify 暂时不可用（{response.status_code}）",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return normalize_dify_response(response.json())
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                if attempt == 2 or (status is not None and status not in retryable):
                    break
                await asyncio.sleep(2**attempt)

        if isinstance(last_error, httpx.HTTPStatusError):
            raise DifyError(
                f"Dify 请求失败（HTTP {last_error.response.status_code}）"
            ) from last_error
        raise DifyError("Dify 网络请求失败或超时") from last_error
