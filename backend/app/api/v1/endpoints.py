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
    AnalyzeRequest,
    TranslateRequest
)
from app.services.pdf_service import PDFService
from app.services.rag_engine import RAGEngine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/search", response_model=List[ArticleMetadata])
async def search_arxiv(payload: SearchRequest):
    """Searches arXiv API based on user query."""
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
        logger.error(f"arXiv API Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"arXiv API Error: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"PDF Processing Error: {str(e)}")


@router.post("/analyze-stream")
async def analyze_and_stream(payload: AnalyzeRequest):
    """
    Streams analysis workflow via SSE:
    1. Status: Downloading papers
    2. Status: Map stage (parallel extraction)
    3. Status/Tokens: Reduce stage (Gemini final synthesis)
    """
    rag_engine = RAGEngine()

    async def event_generator():
        try:
            # Step 1: Downloading PDFs
            yield {
                "event": "status",
                "data": json.dumps({
                    "step": "downloading", 
                    "message": f"Downloading and parsing {len(payload.articles)} research paper(s)..."
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

            # Step 2: Map Stage
            yield {
                "event": "status",
                "data": json.dumps({
                    "step": "map", 
                    "message": "Analyzing individual papers concurrently (Map Stage)..."
                })
            }

            map_summaries = await rag_engine.run_map_stage_parallel(
                articles_data, 
                payload.user_instruction
            )

            # Step 3: Reduce Stage
            yield {
                "event": "status",
                "data": json.dumps({
                    "step": "reduce", 
                    "message": "Generating final comparative report with Gemini..."
                })
            }

            async for token in rag_engine.stream_reduce_stage(map_summaries, payload.user_instruction):
                yield {
                    "event": "token",
                    "data": json.dumps({"content": token})
                }

            # Step 4: Completion signal
            yield {
                "event": "complete",
                "data": json.dumps({"status": "done"})
            }

        except Exception as stream_err:
            logger.error(f"SSE Pipeline Error: {str(stream_err)}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({
                    "message": "An error occurred during paper processing.",
                    "detail": str(stream_err)
                })
            }

    return EventSourceResponse(event_generator())


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
                    "message": f"Translating report into {payload.target_language}..."
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
                    "message": "An error occurred during translation.",
                    "detail": str(stream_err)
                })
            }

    return EventSourceResponse(event_generator())