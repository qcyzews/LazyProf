from pydantic import BaseModel, Field
from typing import List, Optional, Dict

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