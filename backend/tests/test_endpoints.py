# /backend/tests/test_endpoints.py
import json
import pytest
import codecs
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import router


# --- FIXTURES ---

@pytest.fixture
def test_app():
    """Tworzy instancję aplikacji FastAPI z podpiętym routerem endpointów."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
async def client(test_app):
    """Asynchroniczny klient testowy HTTP dla FastAPI."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), 
        base_url="http://test"
    ) as ac:
        yield ac


# --- TESTY ENDPOINTU /search ---

@pytest.mark.asyncio
@patch("app.api.v1.endpoints.SearchService.search_with_expansion", new_callable=AsyncMock)
async def test_search_arxiv_success(mock_search, client):
    mock_search.return_value = {
        "original_query": "transformer",
        "expanded_query": "transformer attention models",
        "articles": [
            {
                "arxiv_id": "1706.03762",
                "title": "Attention Is All You Need",
                "authors": ["Ashish Vaswani"],
                "summary": "Abstract...",
                "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
                "published": "2017-06-12",
            }
        ],
    }

    payload = {"query": "transformer", "max_results": 5}
    response = await client.post("/search", json=payload)

    assert response.status_code == 200
    data = response.json()
    
    # POPRAWIONE ASERCJE:
    assert data["original_query"] == "transformer"
    assert data["expanded_query"] == "transformer attention models"
    assert len(data["articles"]) == 1
    assert data["articles"][0]["arxiv_id"] == "1706.03762"
    
    mock_search.assert_awaited_once_with(query="transformer", max_results=5, user_mode="fast")


@pytest.mark.asyncio
@patch("app.api.v1.endpoints.SearchService.search_with_expansion", new_callable=AsyncMock)
async def test_search_arxiv_error(mock_search, client):
    mock_search.side_effect = Exception("arXiv API Timeout")

    payload = {"query": "error query", "max_results": 5}
    response = await client.post("/search", json=payload)

    assert response.status_code == 500
    assert "Błąd podczas wyszukiwania" in response.json()["detail"]


# --- TESTY ENDPOINTU /parse-pdf ---

@pytest.mark.asyncio
@patch("app.api.v1.endpoints.clean_arxiv_id")
@patch("app.api.v1.endpoints.PDFService.extract_text_from_url", new_callable=AsyncMock)
async def test_parse_pdf_success(mock_extract, mock_clean_id, client):
    mock_extract.return_value = "Oto wyciągnięty tekst z pliku PDF." * 20
    mock_clean_id.return_value = "1706.03762"

    payload = {"pdf_url": "https://arxiv.org/pdf/1706.03762.pdf", "max_pages": 3}
    response = await client.post("/parse-pdf", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["arxiv_id"] == "1706.03762"
    assert data["extracted_characters"] > 0
    assert "Oto wyciągnięty tekst" in data["text_preview"]
    mock_extract.assert_awaited_once_with(pdf_url="https://arxiv.org/pdf/1706.03762.pdf", max_pages=3)


@pytest.mark.asyncio
@patch("app.api.v1.endpoints.PDFService.extract_text_from_url", new_callable=AsyncMock)
async def test_parse_pdf_http_exception(mock_extract, client):
    mock_extract.side_effect = HTTPException(status_code=400, detail="Nieprawidłowy adres URL PDF")

    payload = {"pdf_url": "https://invalid-url.com/paper.pdf"}
    response = await client.post("/parse-pdf", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Nieprawidłowy adres URL PDF"


# --- TESTY STRUMIENIOWANIA /analyze-stream (SSE) ---

@pytest.mark.asyncio
@patch("app.api.v1.endpoints.rag_engine")
@patch("app.api.v1.endpoints.PDFService.extract_text_from_url", new_callable=AsyncMock)
async def test_analyze_stream_success(mock_extract_pdf, mock_rag, client):
    mock_extract_pdf.return_value = "Treść artykułu"
    mock_rag.run_map_stage_parallel = AsyncMock(return_value=["Podsumowanie 1"])

    async def mock_stream_reduce(*args, **kwargs):
        yield "Analiza "
        yield "porównawcza."

    mock_rag.stream_reduce_stage = mock_stream_reduce

    payload = {
        "articles": [
            {
                "title": "Paper 1",
                "arxiv_id": "1706.03762",
                "authors": ["Author"],
                "summary": "Summary",
                "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
                "published": "2017-06-12"
            }
        ],
        "user_instruction": "Porównaj metody."
    }

    response = await client.post("/analyze-stream", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    content = response.text
    assert "downloading" in content
    assert "map" in content
    assert "reduce" in content
    assert "Analiza " in content
    assert "done" in content


@pytest.mark.asyncio
@patch("app.api.v1.endpoints.PDFService.extract_text_from_url", new_callable=AsyncMock)
async def test_analyze_stream_error(mock_extract_pdf, client):
    mock_extract_pdf.side_effect = Exception("Błąd pobierania pliku PDF")

    payload = {
        "articles": [
            {
                "title": "Paper 1",
                "arxiv_id": "1706.03762",
                "authors": ["Author"],
                "summary": "Summary",
                "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
                "published": "2017-06-12"
            }
        ],
        "user_instruction": "Przeanalizuj"
    }

    response = await client.post("/analyze-stream", json=payload)
    assert response.status_code == 200
    content = response.text
    decoded_content = codecs.decode(response.text, "unicode_escape")
    assert "event: error" in decoded_content
    assert "Wystąpił błąd podczas przetwarzania prac." in decoded_content


# --- TESTY STRUMIENIOWANIA /translate-stream (SSE) ---

@pytest.mark.asyncio
@patch("app.api.v1.endpoints.rag_engine")
async def test_translate_stream_success(mock_rag, client):
    async def mock_stream_trans(*args, **kwargs):
        yield "To jest "
        yield "tłumaczenie."

    mock_rag.stream_translation = mock_stream_trans

    payload = {
        "text": "This is a report.",
        "target_language": "pl",
        "is_valid": True,
        "audit_trail": [],
        "arxiv_ids": ["1706.03762"]
    }

    response = await client.post("/translate-stream", json=payload)
    assert response.status_code == 200

    content = response.text
    decoded_content = codecs.decode(response.text, "unicode_escape")
    assert "translating" in decoded_content
    assert "To jest " in decoded_content
    assert "event: report" in decoded_content
    assert "To jest tłumaczenie." in decoded_content
    assert "complete" in decoded_content


# --- TESTY EKSPORTU PDF /export-pdf ---

@pytest.mark.asyncio
@patch("app.api.v1.endpoints.HTML")
async def test_export_pdf_success(mock_html_cls, client):
    mock_html_instance = MagicMock()
    mock_html_instance.write_pdf.return_value = b"%PDF-1.4 Mocked PDF Content"
    mock_html_cls.return_value = mock_html_instance

    payload = {"markdown": "# Raport\n\n- Punkt 1\n- Punkt 2"}
    response = await client.post("/export-pdf", json=payload)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment; filename=LazyProf_Report.pdf" in response.headers["content-disposition"]
    assert response.content == b"%PDF-1.4 Mocked PDF Content"


@pytest.mark.asyncio
async def test_export_pdf_validation_error(client):
    # Puste pole markdown powinno wyrzucić błąd walidacji pydantic (min_length=1)
    payload = {"markdown": ""}
    response = await client.post("/export-pdf", json=payload)
    assert response.status_code == 422


# --- TESTY ENDPOINTU /status ---

@pytest.mark.asyncio
@patch("app.api.v1.endpoints.quota_service.get_available_modes_status", new_callable=AsyncMock)
async def test_get_status_success(mock_get_status, client):
    mock_get_status.return_value = {
        "fast": {
            "available": True,
            "remaining": 500,
            "model_name": "gemini-3.1-flash-lite",
            "remaining_rpd": 500,
            "max_rpd": 500,
        },
        "medium": {
            "available": True,
            "remaining": 500,
            "model_name": "gemini-3.1-flash-lite",
            "remaining_rpd": 500,
            "max_rpd": 500,
        },
        "high": {
            "available": True,
            "remaining": 20,
            "model_name": "gemini-3.5-flash",
            "remaining_rpd": 20,
            "max_rpd": 20,
        },
    }

    response = await client.get("/status")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["modes"]["fast"]["available"] is True


@pytest.mark.asyncio
@patch("app.api.v1.endpoints.quota_service.get_available_modes_status", new_callable=AsyncMock)
async def test_get_status_error(mock_get_status, client):
    mock_get_status.side_effect = Exception("Redis connection error")

    response = await client.get("/status")

    assert response.status_code == 500
    assert "Nie udało się pobrać statusu systemu." in response.json()["detail"]


# --- TESTY STRUMIENIOWANIA LANGGRAPH /run-grounded-analysis-stream (SSE) ---

@pytest.mark.asyncio
@patch("app.api.v1.endpoints.app_graph")
async def test_run_grounded_analysis_stream_success(mock_graph, client):
    async def mock_astream_events(*args, **kwargs):
        # 1. Start węzła syntezy
        yield {
            "event": "on_chain_start",
            "name": "generate_synthesis",
            "metadata": {"langgraph_node": "generate_synthesis"}
        }
        # 2. Koniec ostatniego węzła z wynikiem
        yield {
            "event": "on_chain_end",
            "name": "format_final_report",
            "metadata": {"langgraph_node": "format_final_report"},
            "data": {
                "output": {
                    "analysis_markdown": "# Ostateczny Raport",
                    "is_valid": True,
                    "audit_trail": [],
                    "arxiv_ids": ["1706.03762"]
                }
            }
        }

    mock_graph.astream_events = mock_astream_events

    payload = {
        "arxiv_ids": ["1706.03762"],
        "user_instruction": "Przeanalizuj papier",
        "mode": "fast"
    }

    response = await client.post("/run-grounded-analysis-stream", json=payload)

    assert response.status_code == 200
    content = response.text
    assert "Starting paper verification" in content
    assert "Processing step: generate_synthesis" in content
    assert "event: report" in content
    assert "# Ostateczny Raport" in content
    assert "status\": \"done\"" in content