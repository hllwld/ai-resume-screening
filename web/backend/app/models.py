from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ItemStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


class BatchStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    cancelled = "cancelled"


class CandidateInput(BaseModel):
    client_id: str = Field(min_length=1, max_length=100)
    file_name: str = Field(min_length=1, max_length=255)
    resume_text: str = Field(min_length=100, max_length=60000)


class BatchCreate(BaseModel):
    job_description: str = Field(min_length=20, max_length=20000)
    custom_instructions: str = Field(default="", max_length=2000)
    candidates: list[CandidateInput] = Field(min_length=1, max_length=10)

    @field_validator("candidates")
    @classmethod
    def unique_ids(cls, candidates: list[CandidateInput]) -> list[CandidateInput]:
        ids = [item.client_id for item in candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("client_id 必须唯一")
        return candidates


class DimensionScores(BaseModel):
    skill_match: int = Field(ge=0, le=100)
    experience_relevance: int = Field(ge=0, le=100)
    project_relevance: int = Field(ge=0, le=100)
    overall_quality: int = Field(ge=0, le=100)


class Evidence(BaseModel):
    skill_match: list[str] = Field(default_factory=list)
    experience_relevance: list[str] = Field(default_factory=list)
    project_relevance: list[str] = Field(default_factory=list)
    overall_quality: list[str] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    candidate_name: str = "未提供"
    match_score: int = Field(ge=0, le=100)
    dimension_scores: DimensionScores
    recommendation: Literal["interview", "manual_review", "supplement", "reject"]
    matched_skills: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    evidence: Evidence = Field(default_factory=Evidence)
    recommended_interview_questions: list[str] = Field(default_factory=list)
    human_review_note: str = ""


class BatchItem(BaseModel):
    item_id: str
    client_id: str
    file_name: str
    status: ItemStatus = ItemStatus.pending
    result: EvaluationResult | None = None
    error: str | None = None
    attempts: int = 0


class BatchTask(BaseModel):
    task_id: str
    owner_id: str
    status: BatchStatus = BatchStatus.pending
    job_description: str
    custom_instructions: str = ""
    items: list[BatchItem]
    created_at: str
    updated_at: str
    cancelled: bool = False

    def summary(self) -> dict[str, int]:
        counts = {status.value: 0 for status in ItemStatus}
        for item in self.items:
            counts[item.status.value] += 1
        return counts

    def public_dict(self) -> dict[str, Any]:
        data = self.model_dump(
            mode="json",
            exclude={"owner_id", "job_description", "custom_instructions"},
        )
        data["summary"] = self.summary()
        return data
