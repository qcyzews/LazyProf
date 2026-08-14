import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check_main():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

@patch("app.api.v1.endpoints.arxiv.Client")
def test_search_arxiv_success(mock_arxiv_client):
    mock_result = MagicMock()
    mock_result.entry_id = "http://arxiv.org/abs/1706.03762v1"
    mock_result.title = "Attention Is All You Need"
    mock_result.authors = [MagicMock(name="Ashish Vaswani")]
    mock_result.authors[0].name = "Ashish Vaswani"
    mock_result.published.strftime.return_value = "2017-06-12"
    mock_result.summary = "Abstract text"
    mock_result.pdf_url = "http://arxiv.org/pdf/1706.03762v1"

    mock_client_inst = MagicMock()
    mock_client_inst.results.return_value = [mock_result]
    mock_arxiv_client.return_value = mock_client_inst

    response = client.post("/api/v1/search", json={"query": "transformer", "max_results": 1})
    assert response.status_code == 200
    assert len(response.json()) == 1

@patch("app.api.v1.endpoints.arxiv.Client", side_effect=Exception("ArXiv error"))
def test_search_arxiv_error(mock_arxiv_client):
    response = client.post("/api/v1/search", json={"query": "test"})
    assert response.status_code == 500

@patch("app.api.v1.endpoints.PDFService.extract_text_from_url", new_callable=AsyncMock)
def test_parse_pdf_success(mock_extract):
    mock_extract.return_value = "Sample extracted text from paper."
    response = client.post("/api/v1/parse-pdf", json={"pdf_url": "http://arxiv.org/pdf/2106.09685.pdf"})
    assert response.status_code == 200

@patch("app.api.v1.endpoints.PDFService.extract_text_from_url", new_callable=AsyncMock)
@patch("app.api.v1.endpoints.RAGEngine")
def test_analyze_stream_endpoint(mock_rag_cls, mock_extract):
    mock_extract.return_value = "Extracted text content."
    mock_rag = MagicMock()
    mock_rag.run_map_stage_parallel = AsyncMock(return_value=["Summary 1"])

    async def mock_generator(*args, **kwargs):
        yield "Token 1 "

    mock_rag.stream_reduce_stage = mock_generator
    mock_rag_cls.return_value = mock_rag

    payload = {
        "articles": [{
            "arxiv_id": "1706.03762",
            "title": "Test Title",
            "authors": ["Author"],
            "published": "2020-01-01",
            "summary": "Summary",
            "pdf_url": "http://arxiv.org/pdf/1706.03762.pdf"
        }],
        "user_instruction": "Summarize"
    }
    response = client.post("/api/v1/analyze-stream", json=payload)
    assert response.status_code == 200

@patch("app.api.v1.endpoints.RAGEngine")
def test_translate_stream_endpoint(mock_rag_cls):
    mock_rag = MagicMock()

    async def mock_trans_gen(*args, **kwargs):
        yield "Tłumaczenie "

    mock_rag.stream_translation = mock_trans_gen
    mock_rag_cls.return_value = mock_rag

    payload = {"text": "Hello world", "target_language": "Polish"}
    response = client.post("/api/v1/translate-stream", json=payload)
    assert response.status_code == 200

@patch("app.api.v1.endpoints.HTML")
def test_export_pdf_endpoint(mock_html):
    mock_html.return_value.write_pdf.return_value = b"%PDF-1.4 mock pdf content"
    response = client.post("/api/v1/export-pdf", json={"markdown": "# Test Title\nContent"})
    assert response.status_code == 200

def test_export_pdf_empty_error():
    response = client.post("/api/v1/export-pdf", json={"markdown": ""})
    assert response.status_code == 400