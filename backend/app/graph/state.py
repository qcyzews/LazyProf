# backend/app/graph/state.py
import operator
from typing import Annotated, List, Dict, TypedDict, Optional, Any
from pydantic import BaseModel, Field


class ArticleInput(BaseModel):
    arxiv_id: str
    title: str
    pdf_url: str


class PaperAnalysis(BaseModel):
    arxiv_id: str
    title: str
    summary: str
    methodology: str
    key_findings: List[str]
    limitations: List[str]


class JudgeEvaluation(BaseModel):
    is_grounded: bool = Field(
        description="True if all claims are supported by the source text, False otherwise."
    )
    errors: List[str] = Field(
        default_factory=list,
        description="List of specific claims that contradict or lack support in the source text."
    )


class AttemptRecord(TypedDict):
    attempt_number: int
    rejected_analysis: str
    errors: List[str]
    judge_feedback: str


class MultiPaperState(TypedDict):
    arxiv_ids: List[str]
    user_instruction: str
    mode: Optional[str]  # "fast" lub "exact"
    expanded_keywords: Optional[List[str]]
    papers_data: Dict[str, List[Dict[str, Any]]]
    papers_metadata: Dict[str, Dict[str, Any]]
    analysis_markdown: str
    verification_errors: List[str]
    judge_feedback: str
    retry_count: int
    is_valid: bool
    audit_trail: List[AttemptRecord]