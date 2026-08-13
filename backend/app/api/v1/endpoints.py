import json
import logging
from typing import List
import arxiv
from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.models.schemas import (
    ArticleMetadata, 
    SearchRequest, 
    ProcessPdfRequest, 
    ProcessPdfResponse,
    AnalyzeRequest
)
from app.services.pdf_service import PDFService
from app.services.rag_engine import RAGEngine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/search", response_model=List[ArticleMetadata])
async def search_arxiv(payload: SearchRequest):
    """Przeszukuje arXiv API na podstawie zapytania użytkownika."""
    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=payload.query,
            max_results=payload.max_results,
            sort_by=arxiv.SortCriterion.Relevance
        )

        results = []
        for result in client.results(search):
            paper_id = result.entry_id.split('/')[-1]
            results.append(
                ArticleMetadata(
                    arxiv_id=paper_id,
                    title=result.title.replace("\n", " "),
                    authors=[a.name for a in result.authors],
                    published=result.published.strftime("%Y-%m-%d"),
                    summary=result.summary.replace("\n", " "),
                    pdf_url=result.pdf_url
                )
            )
        return results
    except Exception as e:
        logger.error(f"Błąd arXiv API: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Błąd arXiv API: {str(e)}")


@router.post("/parse-pdf", response_model=ProcessPdfResponse)
async def parse_pdf(payload: ProcessPdfRequest):
    """Pobiera plik PDF z arXiv do RAM i wyciąga z niego tekst."""
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
        logger.error(f"Błąd przetwarzania PDF: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Błąd przetwarzania PDF: {str(e)}")


# --- ENDPOINT ANALIZY I STRUMIENIOWANIA (SSE) ---
@router.post("/analyze-stream")
async def analyze_and_stream(payload: AnalyzeRequest):
    """
    Nawiązuje natychmiastowe połączenie SSE i strumieniuje:
    1. Status pobierania PDF-ów
    2. Status etapu Map Stage
    3. Tokeny raportu końcowego z etapu Reduce Stage (Gemini)
    """
    rag_engine = RAGEngine()

    async def event_generator():
        try:
            # Krok 1: Pobieranie tekstów z wybranych artykułów
            yield {
                "event": "status",
                "data": json.dumps({
                    "step": "downloading", 
                    "message": f"Pobieranie i ekstrahowanie treści {len(payload.articles)} artykułów..."
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

            # Krok 2: Map Stage (analiza równoległa z Gemini)
            yield {
                "event": "status",
                "data": json.dumps({
                    "step": "map", 
                    "message": "Analizowanie zgromadzonych artykułów (Map Stage)..."
                })
            }

            map_summaries = await rag_engine.run_map_stage_parallel(
                articles_data, 
                payload.user_instruction
            )

            # Krok 3: Reduce Stage (Generowanie raportu końcowego przez Gemini)
            yield {
                "event": "status",
                "data": json.dumps({
                    "step": "reduce", 
                    "message": "Generowanie syntezy końcowej przez Gemini..."
                })
            }

            async for token in rag_engine.stream_reduce_stage(map_summaries, payload.user_instruction):
                yield {
                    "event": "token",
                    "data": json.dumps({"content": token})
                }

            # Krok 4: Sygnał zakończenia
            yield {
                "event": "complete",
                "data": json.dumps({"status": "done"})
            }

        except Exception as stream_err:
            logger.error(f"Błąd w trakcie wykonywania potoku SSE: {str(stream_err)}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({
                    "message": "Wystąpił błąd podczas przetwarzania.",
                    "detail": str(stream_err)
                })
            }

    return EventSourceResponse(event_generator())