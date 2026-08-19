# backend/tests/services/test_pdf_and_rag.py
import pytest
from unittest.mock import MagicMock, patch
import httpx
from fastapi import HTTPException

from app.services.pdf_service import PDFService, clean_arxiv_id


# ============================================================================
# TESTY: clean_arxiv_id
# ============================================================================

def test_clean_arxiv_id_regex_matches():
    """Testuje dopasowania regex dla standardowych formatów arXiv ID."""
    assert clean_arxiv_id("1706.03762") == "1706.03762"
    assert clean_arxiv_id("1706.03762v2") == "1706.03762v2"
    assert clean_arxiv_id("math-ph/0103001") == "math-ph/0103001"
    assert clean_arxiv_id("https://arxiv.org/abs/1706.03762") == "1706.03762"


def test_clean_arxiv_id_fallback_parsing():
    """Testuje zapasowe czyszczenie dla ścieżek i nazw plików niemających standardowego ID."""
    assert clean_arxiv_id("https://example.com/custom_paper.pdf") == "custom_paper"
    assert clean_arxiv_id(" [custom_file.pdf] ") == "custom_file"


# ============================================================================
# TESTY: PDFService.extract_text_from_url
# ============================================================================

@pytest.mark.asyncio
@patch("app.services.pdf_service.httpx.AsyncClient.get")
@patch("app.services.pdf_service.fitz.open")
async def test_extract_text_from_url_success(mock_fitz_open, mock_httpx_get):
    """Testuje udane wyciąganie tekstu ze stron z pominięciem pustych stron."""
    mock_httpx_get.return_value = MagicMock(
        status_code=200, 
        content=b"%PDF mock", 
        raise_for_status=MagicMock()
    )

    page1 = MagicMock()
    page1.get_text.return_value = "Wstęp do artykułu."
    page2 = MagicMock()
    page2.get_text.return_value = "   "  # Pusta strona do pominięcia
    page3 = MagicMock()
    page3.get_text.return_value = "Wnioski końcowe."

    pages = [page1, page2, page3]
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = len(pages)
    mock_doc.load_page.side_effect = lambda i: pages[i]
    mock_fitz_open.return_value.__enter__.return_value = mock_doc

    result = await PDFService.extract_text_from_url("https://arxiv.org/pdf/1706.03762.pdf", max_pages=15)

    assert "--- STRONA 1 ---" in result
    assert "Wstęp do artykułu." in result
    assert "STRONA 2" not in result  # Pusta strona pominięta
    assert "--- STRONA 3 ---" in result
    assert "Wnioski końcowe." in result


# ============================================================================
# TESTY: PDFService.extract_pages_from_url
# ============================================================================

@pytest.mark.asyncio
@patch("app.services.pdf_service.httpx.AsyncClient.get")
@patch("app.services.pdf_service.fitz.open")
async def test_extract_pages_from_url_success(mock_fitz_open, mock_httpx_get):
    """Testuje zwracanie ustrukturyzowanej listy stron."""
    mock_httpx_get.return_value = MagicMock(
        status_code=200, 
        content=b"%PDF mock", 
        raise_for_status=MagicMock()
    )

    page1 = MagicMock()
    page1.get_text.return_value = [(0, 0, 100, 100, "Treść strony 1", 0, 0)]
    
    pages = [page1]
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = len(pages)
    mock_doc.load_page.side_effect = lambda i: pages[i]
    mock_fitz_open.return_value.__enter__.return_value = mock_doc

    pages_data = await PDFService.extract_pages_from_url("1706.03762")

    assert len(pages_data) > 0


@pytest.mark.asyncio
@patch("app.services.pdf_service.httpx.AsyncClient.get")
@patch("app.services.pdf_service.fitz.open")
async def test_extract_pages_from_url_empty_pdf_raises_400(mock_fitz_open, mock_httpx_get):
    """Testuje rzucenie ValueError gdy z PDF nie wyekstrahowano żadnego tekstu."""
    mock_httpx_get.return_value = MagicMock(
        status_code=200, 
        content=b"%PDF mock", 
        raise_for_status=MagicMock()
    )

    mock_page = MagicMock()
    mock_page.get_text.return_value = []  # Pusta lista bloków
    
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 1
    mock_doc.load_page.return_value = mock_page
    mock_fitz_open.return_value.__enter__.return_value = mock_doc

    with pytest.raises(ValueError) as exc_info:
        await PDFService.extract_pages_from_url("1706.03762")
    
    assert "Plik PDF nie zawiera tekstu" in str(exc_info.value)


@pytest.mark.asyncio
@patch("app.services.pdf_service.httpx.AsyncClient.get")
async def test_extract_pages_from_url_httpx_error(mock_httpx_get):
    """Testuje obsługę błędu sieciowego httpx.HTTPError."""
    mock_httpx_get.side_effect = httpx.HTTPError("Błąd połączenia HTTP")

    with pytest.raises(RuntimeError) as exc_info:
        await PDFService.extract_pages_from_url("1706.03762")

    assert "Błąd połączenia z arXiv" in str(exc_info.value)


@pytest.mark.asyncio
@patch("app.services.pdf_service.httpx.AsyncClient.get")
@patch("app.services.pdf_service.fitz.open")
async def test_extract_pages_from_url_generic_exception(mock_fitz_open, mock_httpx_get):
    """Testuje obsługę niespodziewanego wyjątku (np. uszkodzony plik PDF)."""
    mock_httpx_get.return_value = MagicMock(
        status_code=200, 
        content=b"corrupted", 
        raise_for_status=MagicMock()
    )
    mock_fitz_open.side_effect = Exception("Plik jest uszkodzony")

    with pytest.raises(RuntimeError) as exc_info:
        await PDFService.extract_pages_from_url("1706.03762")

    assert "Błąd przetwarzania pliku PDF" in str(exc_info.value)

    
# ============================================================================
# TESTY: PDFService.build_grounded_context
# ============================================================================

def test_build_grounded_context():
    """Testuje budowanie sformatowanego kontekstu dla LLM z wyekstrahowanych stron."""
    pages_data = [
        {"page": 1, "text": "Pierwsza strona opisu."},
        {"page": 2, "text": "Druga strona opisu."}
    ]

    context = PDFService.build_grounded_context("1706.03762", pages_data)

    assert "=== START DOKUMENTU: arXiv:1706.03762 ===" in context
    assert "--- [DOKUMENT: 1706.03762 | STRONA: 1] ---" in context
    assert "Pierwsza strona opisu." in context
    assert "--- [DOKUMENT: 1706.03762 | STRONA: 2] ---" in context
    assert "Druga strona opisu." in context
    assert "=== KONIEC DOKUMENTU: arXiv:1706.03762 ===" in context