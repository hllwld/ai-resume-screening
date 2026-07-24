import time

from fastapi.testclient import TestClient

from app.main import app, client, settings
from app.models import DimensionScores, EvaluationResult


def establish_session(test_client: TestClient) -> None:
    response = test_client.get("/api/session")
    assert response.status_code == 200
    if not response.json()["authenticated"]:
        response = test_client.post(
            "/api/auth/login",
            json={"access_code": settings.app_access_code},
        )
    assert response.status_code == 200
    assert response.json()["authenticated"] is True


def test_health_does_not_expose_key():
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "api_key" not in response.json()


def test_built_frontend_is_served():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "简历评估工作台" in response.text


def test_batch_rejects_short_resume():
    with TestClient(app) as test_client:
        establish_session(test_client)
        response = test_client.post(
            "/api/batches",
            json={
                "job_description": "这是一个长度足够的测试岗位说明，用于检查输入校验。",
                "custom_instructions": "",
                "candidates": [
                    {
                        "client_id": "1",
                        "file_name": "short.pdf",
                        "resume_text": "太短",
                    }
                ],
            },
        )
    assert response.status_code == 422


def test_batch_success_and_excel_download(monkeypatch):
    async def fake_evaluate(*_args, **_kwargs):
        return EvaluationResult(
            candidate_name="测试候选人",
            match_score=82,
            dimension_scores=DimensionScores(
                skill_match=85,
                experience_relevance=78,
                project_relevance=88,
                overall_quality=75,
            ),
            recommendation="interview",
            matched_skills=["Python", "RAG"],
            human_review_note="结果仅供人工复核",
        )

    monkeypatch.setattr(client, "evaluate", fake_evaluate)
    with TestClient(app) as test_client:
        establish_session(test_client)
        response = test_client.post(
            "/api/batches",
            json={
                "job_description": "招聘 AI 应用工程师，要求熟悉 Python、RAG、API 集成与工作流评测。",
                "custom_instructions": "重点关注 RAG 项目经验",
                "candidates": [
                    {
                        "client_id": "candidate-1",
                        "file_name": "candidate.pdf",
                        "resume_text": "候选人拥有 Python、SQL、RAG 和 Prompt Engineering 项目经验，负责 API 集成、评测集设计、工作流开发、结果验证和项目复盘。" * 2,
                    }
                ],
            },
        )
        assert response.status_code == 202
        task_id = response.json()["task_id"]
        for _ in range(20):
            task_response = test_client.get(f"/api/batches/{task_id}")
            if task_response.json()["status"] == "completed":
                break
            time.sleep(0.02)
        payload = task_response.json()
        assert payload["summary"]["success"] == 1
        assert payload["items"][0]["result"]["match_score"] == 82

        export_response = test_client.get(f"/api/batches/{task_id}/export.xlsx")
        assert export_response.status_code == 200
        assert export_response.content.startswith(b"PK")

        with TestClient(app) as other_client:
            establish_session(other_client)
            forbidden = other_client.get(f"/api/batches/{task_id}")
        assert forbidden.status_code == 404

        delete_response = test_client.delete(f"/api/batches/{task_id}")
        assert delete_response.status_code == 204
        assert test_client.get(f"/api/batches/{task_id}").status_code == 404
