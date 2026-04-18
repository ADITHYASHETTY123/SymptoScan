from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class SymptomRequest(BaseModel):
    symptoms: str = Field(..., min_length=5, max_length=2000)
    age: Optional[int] = Field(default=None, ge=0, le=120)
    age_group: Optional[str] = Field(default=None, max_length=32)
    sex: Optional[str] = Field(default=None, max_length=32)
    duration: Optional[str] = Field(default=None, max_length=120)

    @field_validator("symptoms")
    @classmethod
    def normalize_symptoms(cls, value: str) -> str:
        return " ".join(value.split())


class SymptomCheckResult(BaseModel):
    probable_conditions: List[str]
    recommended_next_steps: List[str]
    warning_signs: List[str]
    recognized_symptoms: List[str] = []
    confidence_score: float = 0.0
    confidence_level: str = "low"
    confidence_note: str = ""
    educational_disclaimer: str


class SymptomResponse(BaseModel):
    analysis: SymptomCheckResult
    source: str = Field(..., description="Origin of the answer such as hybrid_agent, hybrid_llm, or rule_based")
    created_at: datetime


class HistoryRecord(BaseModel):
    id: int
    symptoms: str
    source: str
    probable_conditions: List[str]
    recommended_next_steps: List[str]
    warning_signs: List[str]
    recognized_symptoms: List[str] = []
    confidence_score: float = 0.0
    confidence_level: str = "low"
    confidence_note: str = ""
    created_at: datetime
