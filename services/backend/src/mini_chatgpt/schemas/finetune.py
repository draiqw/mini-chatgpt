"""Дообучение: постановка задачи и её статус."""

from pydantic import BaseModel, Field


class FinetuneRequest(BaseModel):
    dataset: str = Field(
        min_length=1,
        max_length=10_000,
    )
    epochs: int = Field(
        default=3,
        ge=1,
        le=5,
    )


class JobCreated(BaseModel):
    job_id: str


class JobStatus(BaseModel):
    job_id: str
    state: str  # PENDING | PROGRESS | SUCCESS | FAILURE
    epoch: int | None = None
    epochs: int | None = None
    step: int | None = None
    steps: int | None = None
    loss: float | None = None
    adapter: str | None = None  # имя сохранённых весов, когда SUCCESS
    error: str | None = None
