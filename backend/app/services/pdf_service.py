# /backend/app/services/pdf_service.py
import fitz  # PyMuPDF
import io
import re
import httpx
import logging
import asyncio
from fastapi import HTTPException
from app.core.config import settings

logger = logging.getLogger(__name__)

# Globalny semafor chroniący CPU i RAM przed zapchaniem.
# Wartość pobierana z .env (z wartością domyślną 4 w przypadku braku zmiennej).
_pdf_semaphore = asyncio.Semaphore(getattr(settings, "MAX_CONCURRENT_PDF_PARSES", 4))

def clean_arxiv_id(raw_input: str) -> str:
    """Wyciąga czysty ID arXiv (np. '1706.03762') z dowolnego ciągu, URL-a lub Markdowna."""
    match = re.search(r'(\d{4}\.\d{4,5}(?:v\d+)?|[a-zA-Z\-]+/\d{7})', raw_input)
    if match:
        return match.group(1)
    return raw_input.strip().rstrip('/').split('/')[-1].replace('.pdf', '').strip("[]()\"' ")

# --- Pomocnicze funkcje synchroniczne do wykonania w osobnych wątkach ---

def _parse_pdf_bytes_to_text(pdf_bytes: bytes, max_pages: int) -> str:
    """Synchroniczne przetwarzanie PyMuPDF do postaci pojedynczego tekstu."""
    full_text = []
    with fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf") as doc:
        pages_to_process = min(len(doc), max_pages)
        for page_num in range(pages_to_process):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            if text.strip():
                full_text.append(f"--- STRONA {page_num + 1} ---\n{text}")
    return "\n\n".join(full_text)

def _parse_pdf_bytes_to_pages(pdf_bytes: bytes, max_pages: int) -> list[dict]:
    """Synchroniczne przetwarzanie PyMuPDF do ustrukturyzowanej listy stron."""
    pages_data = []
    with fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf") as doc:
        pages_to_process = min(len(doc), max_pages)
        for page_num in range(pages_to_process):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            cleaned_text = text.strip()
            if cleaned_text:
                pages_data.append({
                    "page": page_num + 1,
                    "text": cleaned_text
                })
    return pages_data


class PDFService:
    @staticmethod
    async def extract_text_from_url(pdf_url: str, max_pages: int = 15) -> str:
        """
        Pobiera plik PDF z URL i wyciąga tekst bez zamrażania pętli zdarzeń.
        """
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(pdf_url)
            response.raise_for_status()
            pdf_bytes = response.content

        # Kontrolowana obróbka CPU w tle z ograniczeniem przez semafor
        async with _pdf_semaphore:
            return await asyncio.to_thread(_parse_pdf_bytes_to_text, pdf_bytes, max_pages)

    @staticmethod
    async def extract_pages_from_url(pdf_url: str, max_pages: int = 25) -> list[dict]:
        """
        Pobiera PDF z URL i zwraca ustrukturyzowaną listę stron bez blokowania event loopa.
        """
        clean_id = clean_arxiv_id(pdf_url)
        clean_url = f"https://arxiv.org/pdf/{clean_id}.pdf"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
                response = await client.get(clean_url)
                response.raise_for_status()
                pdf_bytes = response.content

            # Kontrolowana obróbka CPU w tle z ograniczeniem przez semafor
            async with _pdf_semaphore:
                pages_data = await asyncio.to_thread(_parse_pdf_bytes_to_pages, pdf_bytes, max_pages)

            if not pages_data:
                raise HTTPException(status_code=400, detail="Nie udało się wyekstrahować tekstu z podanego pliku PDF.")

            return pages_data

        except HTTPException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"Błąd HTTP podczas pobierania PDF z {clean_url}: {e}")
            raise HTTPException(status_code=500, detail=f"Błąd pobierania pliku PDF: {str(e)}")
        except Exception as e:
            logger.error(f"Błąd przetwarzania PDF z {clean_url}: {e}")
            raise HTTPException(status_code=500, detail=f"Błąd przetwarzania pliku PDF: {str(e)}")

    @staticmethod
    def build_grounded_context(arxiv_id: str, pages_data: list[dict]) -> str:
        """
        Formatuje wyekstrahowane strony do postaci kontekstu dla LLM.
        """
        formatted_context = f"=== START DOKUMENTU: arXiv:{arxiv_id} ===\n"
        for p in pages_data:
            formatted_context += f"\n--- [DOKUMENT: {arxiv_id} | STRONA: {p['page']}] ---\n"
            formatted_context += p["text"] + "\n"
        formatted_context += f"\n=== KONIEC DOKUMENTU: arXiv:{arxiv_id} ==="
        return formatted_context