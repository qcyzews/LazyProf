# /backend/app/api/v1/endpoints.py
import json
import logging
import markdown
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Response, status
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field
from weasyprint import HTML

from app.graph.workflow import multi_paper_graph

from app.models.schemas import (
    ArticleMetadata, 
    SearchRequest, 
    ProcessPdfRequest, 
    ProcessPdfResponse,
    AnalyzeRequest,
    TranslateRequest,
    StatusResponse,
    SearchResponse
)
from app.services.pdf_service import PDFService
from app.services.rag_engine import RAGEngine
from app.services.quota_service import quota_service
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)
router = APIRouter()


# --- SCHEMAS ---

class MultiPaperGroundedRequest(BaseModel):
    arxiv_ids: List[str] = Field(
        ..., 
        example=["1706.03762", "2106.09685"], 
        description="Lista identyfikatorów arXiv do analizy"
    )
    user_instruction: str = Field(
        ..., 
        example="Porównaj architekturę i wyniki opisane w artykułach.",
        description="Zapytanie lub instrukcja dla agenta"
    )

class MultiPaperGroundedResponse(BaseModel):
    arxiv_ids: List[str]
    total_attempts: int
    is_valid: bool
    analysis_markdown: str
    audit_trail: Optional[List[Dict[str, Any]]] = []

class ExportPdfRequest(BaseModel):
    markdown: str = Field(..., min_length=1, max_length=150000, description="Treść raportu w formacie Markdown")


# --- HELPER DO NAGŁÓWKÓW SSE ---

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


# --- ENDPOINTY ZAPYTAN I EKSTRAKCJI ---

@router.post("/search", response_model=SearchResponse)
async def search_arxiv(payload: SearchRequest):
    """Searches arXiv API using SearchService with LLM query expansion."""
    try:
        results = await SearchService.search_with_expansion(
            query=payload.query,
            max_results=payload.max_results,
            user_mode="fast"  # Lub pobierane z payload jeśli masz takie pole
        )
        return results
    except Exception as e:
        logger.error(f"Search Service Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Błąd podczas wyszukiwania artykułów.")


@router.post("/parse-pdf", response_model=ProcessPdfResponse)
async def parse_pdf(payload: ProcessPdfRequest):
    """Downloads PDF from arXiv into RAM and extracts text."""
    try:
        extracted_text = await PDFService.extract_text_from_url(
            pdf_url=payload.pdf_url, 
            max_pages=payload.max_pages
        )
        
        arxiv_id = payload.pdf_url.split('/')[-1].replace('.pdf', '')
        
        return ProcessPdfResponse(
            arxiv_id=arxiv_id,
            extracted_characters=len(extracted_text),
            text_preview=extracted_text[:500] + "..."
        )
    except Exception as e:
        logger.error(f"PDF Processing Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Nie udało się przetworzyć pliku PDF.")


# --- ENDPOINTY STRUMIENIOWE (SSE) ---

@router.post("/analyze-stream")
async def analyze_and_stream(payload: AnalyzeRequest):
    """Streams analysis workflow via SSE (Map-Reduce stage)."""
    rag_engine = RAGEngine()

    async def event_generator():
        try:
            yield {
                "event": "status",
                "data": json.dumps({
                    "step": "downloading", 
                    "message": f"Pobieranie i parsowanie {len(payload.articles)} prac naukowych..."
                })
            }

            articles_data = []
            for art in payload.articles:
                text = await PDFService.extract_text_from_url(art.pdf_url)
                articles_data.append({
                    "title": art.title,
                    "arxiv_id": art.arxiv_id,
                    "text": text
                })

            yield {
                "event": "status",
                "data": json.dumps({
                    "step": "map", 
                    "message": "Analiza poszczególnych artykułów w trybie równoległym (Map Stage)..."
                })
            }

            map_summaries = await rag_engine.run_map_stage_parallel(
                articles_data, 
                payload.user_instruction
            )

            yield {
                "event": "status",
                "data": json.dumps({
                    "step": "reduce", 
                    "message": "Generowanie końcowego raportu porównawczego (Reduce Stage)..."
                })
            }

            async for token in rag_engine.stream_reduce_stage(map_summaries, payload.user_instruction):
                yield {
                    "event": "token",
                    "data": json.dumps({"content": token})
                }

            yield {
                "event": "complete",
                "data": json.dumps({"status": "done"})
            }

        except Exception as stream_err:
            logger.error(f"SSE Pipeline Error: {str(stream_err)}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({
                    "message": "Wystąpił błąd podczas przetwarzania prac.",
                    "detail": str(stream_err)
                })
            }
            yield {
                "event": "complete",
                "data": json.dumps({"status": "error_terminated"})
            }

    return EventSourceResponse(event_generator(), headers=SSE_HEADERS)


@router.post("/translate-stream")
async def translate_and_stream(payload: TranslateRequest):
    """Streams live Markdown translation of a report into the specified target language."""
    rag_engine = RAGEngine()

    async def event_generator():
        try:
            yield {
                "event": "status",
                "data": json.dumps({
                    "step": "translating", 
                    "message": f"Tłumaczenie raportu na język: {payload.target_language}..."
                })
            }

            async for token in rag_engine.stream_translation(payload.text, payload.target_language):
                yield {
                    "event": "token",
                    "data": json.dumps({"content": token})
                }

            yield {
                "event": "complete",
                "data": json.dumps({"status": "done"})
            }

        except Exception as stream_err:
            logger.error(f"Translation SSE Error: {str(stream_err)}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({
                    "message": "Wystąpił błąd podczas tłumaczenia.",
                    "detail": str(stream_err)
                })
            }

    return EventSourceResponse(event_generator(), headers=SSE_HEADERS)


# --- EXPORT DO PDF ---

@router.post("/export-pdf")
async def export_pdf(payload: ExportPdfRequest):
    """Converts a Markdown report into a styled PDF document using WeasyPrint."""
    try:
        html_content = markdown.markdown(
            payload.markdown, 
            extensions=['extra', 'tables', 'fenced_code']
        )

        full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        @page {{
            size: A4;
            margin: 20mm 15mm;
            @bottom-right {{
                content: "Strona " counter(page) " z " counter(pages);
                font-size: 9pt;
                color: #64748b;
            }}
        }}
        body {{
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            font-size: 10pt;
            line-height: 1.6;
            color: #1e293b;
        }}
        h1 {{ font-size: 18pt; color: #0f172a; margin-bottom: 12px; border-bottom: 2px solid #6366f1; padding-bottom: 6px; }}
        h2 {{ font-size: 14pt; color: #1e1b4b; margin-top: 18px; margin-bottom: 8px; border-left: 4px solid #6366f1; padding-left: 8px; }}
        h3 {{ font-size: 11pt; color: #334155; margin-top: 14px; margin-bottom: 6px; }}
        p {{ margin-bottom: 10px; text-align: justify; }}
        ul, ol {{ margin-bottom: 10px; padding-left: 20px; }}
        li {{ margin-bottom: 4px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 14px 0;
            font-size: 9pt;
        }}
        th, td {{
            border: 1px solid #cbd5e1;
            padding: 6px 10px;
            text-align: left;
        }}
        th {{
            background-color: #f1f5f9;
            font-weight: bold;
            color: #0f172a;
        }}
        tr:nth-child(even) {{
            background-color: #f8fafc;
        }}
        code {{
            font-family: 'Courier New', Courier, monospace;
            background-color: #f1f5f9;
            padding: 2px 4px;
            font-size: 8.5pt;
            border-radius: 3px;
        }}
    </style>
</head>
<body>
    {html_content}
</body>
</html>"""

        pdf_bytes = HTML(string=full_html).write_pdf()

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=LazyProf_Report.pdf"}
        )
    except Exception as e:
        logger.error(f"PDF Export Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Błąd podczas generowania pliku PDF.")


# --- LANGGRAPH GROUNDED AGENT ---

@router.post("/run-grounded-analysis", response_model=MultiPaperGroundedResponse)
async def run_grounded_analysis(request: MultiPaperGroundedRequest):
    """Uruchamia ugruntowaną weryfikację LangGraph z pętlą self-correction."""
    try:
        initial_state = {
            "arxiv_ids": request.arxiv_ids,
            "user_instruction": request.user_instruction,
            "mode": getattr(request, "mode", "fast"),
            "papers_data": {},
            "papers_metadata": {},
            "analysis_markdown": "",
            "verification_errors": [],
            "judge_feedback": "",
            "retry_count": 0,
            "is_valid": False,
            "audit_trail": []
        }
        
        final_state = await multi_paper_graph.ainvoke(initial_state)

        return MultiPaperGroundedResponse(
            arxiv_ids=final_state.get("arxiv_ids", request.arxiv_ids),
            total_attempts=final_state.get("retry_count", 0),
            is_valid=final_state.get("is_valid", False),
            analysis_markdown=final_state.get("analysis_markdown", ""),
            audit_trail=final_state.get("audit_trail", [])
        )
    except Exception as e:
        logger.error(f"LangGraph Processing Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Błąd przetwarzania grafu LangGraph.")


# --- STATUS SYSTEMU ---

@router.get("/status", response_model=StatusResponse)
async def get_system_status():
    """Zwraca status systemu oraz dostępność trybów prędkości na podstawie RPD."""
    try:
        modes_status = await quota_service.get_available_modes_status()
        return {
            "status": "ok",
            "modes": modes_status
        }
    except Exception as e:
        logger.error(f"Status Check Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Nie udało się pobrać statusu systemu.")