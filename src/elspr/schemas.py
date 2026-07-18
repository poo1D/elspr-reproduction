"""Stable JSONL schemas used throughout the reproduction pipeline."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base model that rejects undocumented fields."""

    model_config = ConfigDict(extra="forbid")


class Outcome(StrEnum):
    """Normalized result for the response shown on the left."""

    WIN = "win"
    LOSE = "lose"
    TIE = "tie"
    INVALID = "invalid"


class PairRelationLabel(StrEnum):
    """Tie-aware relation for one unordered response pair."""

    A_OVER_B = "a_over_b"
    B_OVER_A = "b_over_a"
    TIE = "tie"


class ResponseRecord(StrictModel):
    """One model response to one instruction."""

    question_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    instruction: str
    model_id: str = Field(min_length=1)
    response: str
    generation_config: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(min_length=1)


class JudgmentRecord(StrictModel):
    """One ordered pairwise judgment."""

    question_id: str = Field(min_length=1)
    left_model: str = Field(min_length=1)
    right_model: str = Field(min_length=1)
    left_response: str
    right_response: str
    verdict: str
    normalized_left_outcome: Outcome
    judge_model: str = Field(min_length=1)
    prompt_template_id: str = Field(min_length=1)
    raw_output: str
    status: Literal["ok", "invalid"]
    created_at: datetime

    @model_validator(mode="after")
    def validate_models_and_status(self) -> "JudgmentRecord":
        if self.left_model == self.right_model:
            raise ValueError("left_model and right_model must differ")
        if self.status == "ok" and self.normalized_left_outcome is Outcome.INVALID:
            raise ValueError("status='ok' cannot have an invalid outcome")
        if (
            self.status == "invalid"
            and self.normalized_left_outcome is not Outcome.INVALID
        ):
            raise ValueError("status='invalid' requires outcome='invalid'")
        return self


class PairRelation(StrictModel):
    """Aggregated relation for two presentation orders."""

    question_id: str = Field(min_length=1)
    model_a: str = Field(min_length=1)
    model_b: str = Field(min_length=1)
    j_ab: Outcome
    j_ba: Outcome
    relation: PairRelationLabel

    @model_validator(mode="after")
    def validate_canonical_order(self) -> "PairRelation":
        if self.model_a >= self.model_b:
            raise ValueError("model_a and model_b must use ascending canonical order")
        if Outcome.INVALID in (self.j_ab, self.j_ba):
            raise ValueError("invalid judgments cannot form a pair relation")
        return self


class GraphEdge(StrictModel):
    """One serializable directed edge."""

    source: str
    target: str
    relation: str = "preference"
    reconstructed: bool = False


class GraphRecord(StrictModel):
    """Stable JSON representation of one question graph."""

    question_id: str = Field(min_length=1)
    nodes: list[str]
    edges: list[GraphEdge]
