# /backend/app/models/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class SearchRequest(BaseModel):
    query: str = Field(..., json_schema_extra={"example": "Retrieval Augmented Generation"})
    max_results: int = Field(default=5, ge=1, le=20)

class ArticleMetadata(BaseModel):
    arxiv_id: str
    title: str
    authors: List[str]
    published: str
    summary: str
    pdf_url: str

class ProcessPdfRequest(BaseModel):
    pdf_url: str
    max_pages: Optional[int] = 15

class ProcessPdfResponse(BaseModel):
    arxiv_id: str
    extracted_characters: int
    text_preview: str

# 1. ArticleInput MUSI być zdefiniowany PRZED AnalyzeRequest
class ArticleInput(BaseModel):
    title: str
    arxiv_id: str
    pdf_url: str

class AnalyzeRequest(BaseModel):
    articles: List[ArticleInput]
    user_instruction: str

# 2. Wymuszenie jawnego zbudowania schematu Pydantic dla FastAPI
AnalyzeRequest.model_rebuild()

class TranslateRequest(BaseModel):
    text: str
    target_language: str = "Polish"
    # Opcjonalne metadane z istniejącego raportu:
    audit_trail: Optional[List[Any]] = Field(default_factory=list)
    arxiv_ids: Optional[List[str]] = Field(default_factory=list)
    is_valid: Optional[bool] = True

TranslateRequest.model_rebuild()
class ModeStatus(BaseModel):
    available: bool
    model_name: str
    remaining_rpd: int = Field(ge=0)
    max_rpd: int = Field(gt=0)

class StatusResponse(BaseModel):
    status: str = "ok"
    modes: Dict[str, ModeStatus]

class SearchResponse(BaseModel):
    original_query: str
    expanded_query: str
    articles: List[ArticleMetadata]

class QueryExpansionResponse(BaseModel):
    keywords: List[str] = Field(
        description="Lista 3-5 synonimów naukowych, pojęć powiązanych lub skrótów technicznych dla podanego zapytania."
    )


class CitationItem(BaseModel):
    arxiv_id: str = Field(
        ..., 
        description="The ArXiv paper identifier, e.g., '2601.05264'."
    )
    page: Optional[str] = Field(
        default="", 
        description="The explicit page number if found in chunk headers, e.g., '5'. Empty string if not present."
    )
    claim_summary: str = Field(
        ..., 
        description="Brief summary of the specific claim or insight referenced from this source."
    )

class SynthesisResponse(BaseModel):
    analysis_markdown: str = Field(
        ..., 
        description="Comprehensive analysis report formatted in Markdown. EVERY claim, comparison, or technical detail MUST include inline citations like [arXiv:ID] or [arXiv:ID, p. X]."
    )
    citations: List[CitationItem] = Field(
        default_factory=list, 
        description="Complete list of all paper citations used in the analysis."
    )