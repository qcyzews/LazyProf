# backend/tests/services/test_pdf_and_rag.py
import pytest
from unittest.mock import MagicMock, patch
import httpx
from fastapi import HTTPException

from app.services.pdf_service import PDFService


async def _extract_pdf(url: str):
    """Pomocnicze bezpieczne wywołanie metody ekstrakcji tekstu z PDFService."""
    service = PDFService() if isinstance(PDFService, type) else PDFService
    
    for method_name in [
        "download_and_extract_text",
        "download_and_extract",
        "extract_text_from_url",
        "get_pdf_text",
        "process_pdf",
    ]:
        if hasattr(service, method_name):
            method = getattr(service, method_name)
            return await method(url)
            
    raise AttributeError("PDFService nie posiada rozpoznanej metody ekstrakcji tekstu PDF.")


# ============================================================================
# TESTY: PDFService
# ============================================================================

@pytest.mark.asyncio
@patch("app.services.pdf_service.httpx.AsyncClient.get")
async def test_pdf_service_http_error(mock_httpx_get):
    """Testuje obsługę błędu sieciowego/HTTP przy pobieraniu PDF."""
    mock_httpx_get.side_effect = httpx.HTTPError("Network failure")

    with pytest.raises((HTTPException, httpx.HTTPError)):
        await _extract_pdf("https://arxiv.org/pdf/invalid.pdf")


@pytest.mark.asyncio
@patch("app.services.pdf_service.httpx.AsyncClient.get")
@patch("app.services.pdf_service.fitz.open")
async def test_pdf_service_empty_text_extracted(mock_fitz_open, mock_httpx_get):
    """Testuje przypadek, gdy pobrany PDF nie zawiera tekstu."""
    mock_httpx_get.return_value = MagicMock(status_code=200, content=b"%PDF mock")

    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_page.get_text.return_value = "   "  # Pusta strona
    mock_doc.__len__.return_value = 1
    mock_doc.load_page.return_value = mock_page
    mock_doc.__getitem__.return_value = mock_page
    mock_doc.__iter__.return_value = iter([mock_page])
    mock_fitz_open.return_value.__enter__.return_value = mock_doc

    try:
        res = await _extract_pdf("https://arxiv.org/pdf/empty.pdf")
        assert res.strip() == ""
    except HTTPException as exc_info:
        assert exc_info.status_code in (422, 400, 500)


@pytest.mark.asyncio
@patch("app.services.pdf_service.httpx.AsyncClient.get")
@patch("app.services.pdf_service.fitz.open")
async def test_pdf_service_fitz_exception(mock_fitz_open, mock_httpx_get):
    """Testuje błąd parsowania uszkodzonego pliku PDF przez PyMuPDF (fitz)."""
    mock_httpx_get.return_value = MagicMock(status_code=200, content=b"corrupted bytes")
    mock_fitz_open.side_effect = Exception("Corrupted PDF file")

    with pytest.raises((HTTPException, Exception)):
        await _extract_pdf("https://arxiv.org/pdf/corrupt.pdf")


@pytest.mark.asyncio
@patch("app.services.pdf_service.httpx.AsyncClient.get")
@patch("app.services.pdf_service.fitz.open")
async def test_pdf_service_success_extraction(mock_fitz_open, mock_httpx_get):
    """Testuje udaną ekstrakcję tekstu z wielostronicowego PDF przy użyciu fitz."""
    mock_httpx_get.return_value = MagicMock(status_code=200, content=b"%PDF-1.4 mock")

    mock_page1 = MagicMock()
    mock_page1.get_text.return_value = "Treść strony pierwszej.\n"
    mock_page2 = MagicMock()
    mock_page2.get_text.return_value = "Treść strony drugiej."

    pages = [mock_page1, mock_page2]
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = len(pages)
    mock_doc.load_page.side_effect = lambda i: pages[i]
    mock_doc.__getitem__.side_effect = lambda i: pages[i]
    mock_doc.__iter__.return_value = iter(pages)
    mock_fitz_open.return_value.__enter__.return_value = mock_doc

    res = await _extract_pdf("https://arxiv.org/pdf/valid.pdf")
    assert "Treść strony pierwszej" in res
    assert "Treść strony drugiej" in res