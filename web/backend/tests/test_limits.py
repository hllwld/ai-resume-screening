import pytest
from pydantic import ValidationError

from app.models import BatchCreate, CandidateInput


def candidate(index: int, text_length: int = 100) -> CandidateInput:
    return CandidateInput(
        client_id=f"candidate-{index}",
        file_name=f"candidate-{index}.pdf",
        resume_text="简" * text_length,
    )


def test_single_resume_text_limit_is_60000_characters():
    assert len(candidate(1, 60000).resume_text) == 60000
    with pytest.raises(ValidationError):
        candidate(1, 60001)


def test_batch_accepts_at_most_10_resumes():
    payload = {
        "job_description": "这是一个长度足够的岗位描述，用来验证批量数量限制。",
        "candidates": [
            {
                "client_id": item.client_id,
                "file_name": item.file_name,
                "resume_text": item.resume_text,
            }
            for item in (candidate(index) for index in range(11))
        ],
    }
    with pytest.raises(ValidationError):
        BatchCreate.model_validate(payload)
