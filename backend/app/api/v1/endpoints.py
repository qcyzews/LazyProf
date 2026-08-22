# /backend/app/api/v1/endpoints.py
import json
import logging
import markdown
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Response, status
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field
from weasyprint import HTML

from app.graph.workflow import app_graph

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
from app.services.pdf_service import PDFService, clean_arxiv_id
from app.services.rag_engine import rag_engine
from app.services.quota_service import quota_service
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.propagate = True  # Przekazuje logi wyżej do Uvicorna

router = APIRouter()


# --- SCHEMAS ---

class MultiPaperGroundedRequest(BaseModel):
    arxiv_ids: List[str] = Field(
        ..., 
        json_schema_extra={"example": ["1706.03762", "2106.09685"]}, 
        description="Lista identyfikatorów arXiv do analizy"
    )
    user_instruction: str = Field(
        ..., 
        json_schema_extra={"example": "Porównaj architekturę i wyniki opisane w artykułach."},
        description="Zapytanie lub instrukcja dla agenta"
    )
    mode: Optional[str] = "fast"  

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
    logger.info(f"Received /search request: query='{payload.query}', max_results={payload.max_results}")
    try:
        results = await SearchService.search_with_expansion(
            query=payload.query,
            max_results=payload.max_results,
            user_mode="fast"
        )
        return results
    except Exception as e:
        logger.error(f"Search Service Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Błąd podczas wyszukiwania artykułów: {str(e)}")


@router.post("/parse-pdf", response_model=ProcessPdfResponse)
async def parse_pdf(payload: ProcessPdfRequest):
    """Downloads PDF from arXiv into RAM and extracts text."""
    logger.info(f"Received /parse-pdf request: pdf_url='{payload.pdf_url}', max_pages={payload.max_pages}")
    try:
        extracted_text = await PDFService.extract_text_from_url(
            pdf_url=payload.pdf_url, 
            max_pages=payload.max_pages
        )
        
        arxiv_id = clean_arxiv_id(payload.pdf_url)
        
        return ProcessPdfResponse(
            arxiv_id=arxiv_id,
            extracted_characters=len(extracted_text),
            text_preview=extracted_text[:500] + "..."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF Processing Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Nie udało się przetworzyć pliku PDF: {str(e)}")


# --- ENDPOINTY STRUMIENIOWE (SSE) ---

@router.post("/analyze-stream")
async def analyze_and_stream(payload: AnalyzeRequest):
    """Streams analysis workflow via SSE (Map-Reduce stage)."""
    logger.info(f"Received /analyze-stream request: {len(payload.articles)} articles, user_instruction='{payload.user_instruction}'")
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
    """Streams live Markdown translation and returns complete report structure at the end."""
    logger.info(f"Received /translate-stream request: target_language='{payload.target_language}'")
    #print(f"DEBUG: received /translate-stream request: target_language='{payload.target_language}', text: {payload.text}", flush=True) 
    
    async def event_generator():
        accumulated_translation = ""
        try:
            # 1. Informujemy frontend o starcie tłumaczenia i RESETUJEMY bufor tekstu
            yield {
                "event": "status",
                "data": json.dumps({
                    "step": "translating", 
                    "message": f"Tłumaczenie raportu na język: {payload.target_language}...",
                    "reset_stream": True  # 👈 Informuje frontend, by wyczyścił angielski tekst
                })
            }

            # 2. Strumieniujemy tokeny tłumaczenia
            async for token in rag_engine.stream_translation(payload.text, payload.target_language):
                # Upewniamy się, że token jest czystym stringiem
                clean_token = token if isinstance(token, str) else str(token)
                accumulated_translation += clean_token
                # --- DODAJ TE LOGI ---
                #print(f"DEBUG CHUNK TYPE: {type(token)}", flush=True)
                #print(f"DEBUG CHUNK REPR: {repr(token)}", flush=True)
                yield {
                    "event": "token",
                    "data": json.dumps({"token": clean_token})
                }

            # 3. Emitujemy pełny zdarzenie 'report' z nową treścią i starymi metadanymi
            yield {
                "event": "report",
                "data": json.dumps({
                    "analysis_markdown": accumulated_translation,
                    "is_valid": payload.is_valid,
                    "audit_trail": payload.audit_trail,
                    "arxiv_ids": payload.arxiv_ids
                })
            }

            # 4. Zakończenie
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
    logger.info(f"Received /export-pdf request: markdown length={len(payload.markdown)} characters")
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
        raise HTTPException(status_code=500, detail=f"Błąd podczas generowania pliku PDF: {str(e)}")


# --- LANGGRAPH GROUNDED AGENT ---

@router.post("/run-grounded-analysis", response_model=MultiPaperGroundedResponse)
async def run_grounded_analysis(request: MultiPaperGroundedRequest):
    """Uruchamia ugruntowaną weryfikację LangGraph z pętlą self-correction."""
    logger.info(f"Received /run-grounded-analysis request: arxiv_ids={request.arxiv_ids}, user_instruction='{request.user_instruction}', mode='{request.mode}'")
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
        
        #final_state = await multi_paper_graph.ainvoke(initial_state)

        return MultiPaperGroundedResponse(
            arxiv_ids=final_state.get("arxiv_ids", request.arxiv_ids),
            total_attempts=final_state.get("retry_count", 0),
            is_valid=final_state.get("is_valid", False),
            analysis_markdown=final_state.get("analysis_markdown", ""),
            audit_trail=final_state.get("audit_trail", [])
        )
    except Exception as e:
        logger.error(f"LangGraph Processing Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Błąd przetwarzania grafu LangGraph: {str(e)}")


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


@router.post("/run-grounded-analysis-stream")
async def run_grounded_analysis_stream(request: MultiPaperGroundedRequest):
    """Uruchamia ugruntowaną weryfikację LangGraph z pętlą self-correction i strumieniowaniem SSE."""
    #print(f"Received /run-grounded-analysis-stream request: arxiv_ids={request.arxiv_ids}, user_instruction='{request.user_instruction}', mode='{request.mode}'",flush=True) 
    async def event_generator():
        try:
            initial_state = {
                "arxiv_ids": request.arxiv_ids,
                "user_instruction": request.user_instruction or "",
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

            yield {
                "event": "status",
                "data": json.dumps({
                    "step": "init",
                    "message": "Starting paper verification and analysis pipeline..."
                })
            }

            current_node = None

            async for event in app_graph.astream_events(initial_state, version="v2"):
                kind = event.get("event")
                # Wyciągamy dokładną nazwę węzła z metadanych LangGraph (fallback do event.get("name"))
                name = event.get("metadata", {}).get("langgraph_node") or event.get("name")

                #print(f"📡 [SSE GENERATOR] Event: {kind}, Node: {name}, langgraph_node: {event.get('metadata', {}).get('langgraph_node')}",flush=True)

                # Emisja statusu TYLKO przy wejściu do NOWEGO węzła grafu
                if kind == "on_chain_start" and name and name != current_node:
                    current_node = name
                    is_retry_generation = (name == "generate_synthesis") # jeśli generujemy synteze, to czyscimy stream
            
                    yield {
                        "event": "status",
                        "data": json.dumps({
                            "step": name,
                            "message": f"Processing step: {name}...",
                            "reset_stream": is_retry_generation
                        })
                    }

                # Strumieniowanie tokenów TYLKO z węzła generatora syntezy (zostawione pass zgodnie z planem)
                elif kind == "on_chat_model_stream" and current_node == "generate_synthesis":
                    pass

                # Emitowanie zweryfikowanego, końcowego raportu z węzła formatującego
                elif kind == "on_chain_end" and name == "format_final_report":
                    output = event.get("data", {}).get("output", {})
                    final_markdown = output.get("analysis_markdown", "")
                    print(f"DEBUG: Final output length: {len(str(output))}",flush=True)
                    if isinstance(output, dict):
                        yield {
                            "event": "status",
                            "data": json.dumps({
                                "step": name,
                                "message": f"Generowanie raportu końcowego",
                                "reset_stream": True
                            })
                        }
                        await asyncio.sleep(0.05)
                        print(f"📡 [SSE GENERATOR] Emitting final report with length: {len(final_markdown)} characters.",flush=True)
                        yield {
                            "event": "report",
                            "data": json.dumps({
                                "analysis_markdown": final_markdown,
                                "is_valid": output.get("is_valid", False),
                                "audit_trail": output.get("audit_trail", []),
                                "arxiv_ids": output.get("arxiv_ids", [])
                            })
                        }
                        print("📡 [SSE GENERATOR] Final report emitted successfully.",flush=True)
                    else:
                        logger.info(f"📡 [SSE GENERATOR] Unexpected output format from format_final_report: {output}")

            yield {
                "event": "complete",
                "data": json.dumps({"status": "done"})
            }

        except Exception as stream_err:
            #print(f"SSE LangGraph Pipeline Error: {str(stream_err)}", exc_info=True)
            logger.error(f"SSE LangGraph Pipeline Error: {str(stream_err)}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({
                    "message": "An error occurred during paper analysis in LangGraph.",
                    "detail": str(stream_err)
                })
            }
            yield {
                "event": "complete",
                "data": json.dumps({"status": "error_terminated"})
            }

    return EventSourceResponse(event_generator(), headers=SSE_HEADERS)