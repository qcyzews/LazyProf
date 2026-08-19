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

_pdf_semaphore = asyncio.Semaphore(getattr(settings, "MAX_CONCURRENT_PDF_PARSES", 4))


def clean_arxiv_id(raw_input: str) -> str:
    """Wyciąga czysty ID arXiv (np. '1706.03762') z dowolnego ciągu, URL-a lub Markdowna."""
    if not raw_input:
        return ""
    match = re.search(r'(\d{4}\.\d{4,5}(?:v\d+)?|[a-zA-Z\-]+/\d{7})', raw_input)
    if match:
        return match.group(1)
    return raw_input.strip().rstrip('/').split('/')[-1].replace('.pdf', '').strip("[]()\"' ")


def build_pdf_url(raw_input: str) -> str:
    """Buduje poprawny bezpośredni URL do PDF-a."""
    clean_id = clean_arxiv_id(raw_input)
    return f"https://arxiv.org/pdf/{clean_id}.pdf"


def _parse_pdf_bytes_to_text(pdf_bytes: bytes, max_pages: int) -> str:
    full_text = []
    with fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf") as doc:
        pages_to_process = min(len(doc), max_pages)
        for page_num in range(pages_to_process):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            if text.strip():
                full_text.append(f"--- STRONA {page_num + 1} ---\n{text.strip()}")
    return "\n\n".join(full_text)


def _parse_pdf_bytes_to_pages(pdf_bytes: bytes, max_pages: int) -> list[dict]:
    """Stara metoda (zostawiona dla wstecznej kompatybilności)"""
    pages_data = []
    with fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf") as doc:
        pages_to_process = min(len(doc), max_pages)
        for page_num in range(pages_to_process):
            page = doc.load_page(page_num)
            text = page.get_text("text").strip()
            if text:
                pages_data.append({
                    "page": page_num + 1,
                    "text": text
                })
    return pages_data


def _parse_pdf_bytes_to_structured_pages(pdf_bytes: bytes, max_pages: int) -> list[dict]:
    """
    Nowa metoda: parsowanie opartem na blokach (PyMuPDF blocks).
    Dzięki sort=True poprawnie radzi sobie z układem dwuszpaltowym artykułów arXiv
    i grupuje tekst w naturalne akapity.
    """
    pages_data = []
    with fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf") as doc:
        pages_to_process = min(len(doc), max_pages)
        for page_num in range(pages_to_process):
            page = doc.load_page(page_num)
            # Pobieramy bloki z automatycznym sortowaniem w kolejności czytania (góra->dół, kolumny)
            blocks = page.get_text("blocks", sort=True)
            
            page_paragraphs = []
            for b in blocks:
                # b to krotka: (x0, y0, x1, y1, text, block_no, block_type)
                # block_type == 0 oznacza blok tekstowy (1 to obraz)
                if len(b) >= 7 and b[6] == 0:
                    block_text = b[4].strip()
                    if block_text:
                        # Usuwamy wewnętrzne miękkie złamania linii wewnątrz bloku/akapitu
                        clean_block = " ".join(block_text.splitlines())
                        if clean_block:
                            page_paragraphs.append(clean_block)
            
            if page_paragraphs:
                pages_data.append({
                    "page": page_num + 1,
                    "paragraphs": page_paragraphs,
                    # Fallback dla kompatybilności ze starym kodem
                    "text": "\n\n".join(page_paragraphs)
                })
    return pages_data


class PDFService:
    @staticmethod
    async def extract_text_from_url(pdf_url: str, max_pages: int = 15) -> str:
        target_url = build_pdf_url(pdf_url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
                response = await client.get(target_url)
                response.raise_for_status()
                pdf_bytes = response.content

            async with _pdf_semaphore:
                return await asyncio.to_thread(_parse_pdf_bytes_to_text, pdf_bytes, max_pages)
        except Exception as e:
            logger.error(f"❌ Błąd pobierania/parsowania PDF z {target_url}: {e}")
            raise HTTPException(status_code=400, detail=f"Nie udało się pobrać lub otworzyć PDF: {str(e)}")

    @staticmethod
    async def extract_pages_from_url(pdf_url: str, max_pages: int = 25) -> list[dict]:
        target_url = build_pdf_url(pdf_url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
                response = await client.get(target_url)
                response.raise_for_status()
                pdf_bytes = response.content

            async with _pdf_semaphore:
                # Używamy nowej struktury z podziałem na akapity (blocks)
                pages_data = await asyncio.to_thread(_parse_pdf_bytes_to_structured_pages, pdf_bytes, max_pages)

        except httpx.HTTPError as e:
            logger.error(f"❌ Błąd HTTP podczas pobierania PDF z {target_url}: {e}")
            raise RuntimeError(f"Błąd połączenia z arXiv: {e}") from e
        except Exception as e:
            logger.error(f"❌ Błąd parsowania PDF z {target_url}: {e}")
            raise RuntimeError(f"Błąd przetwarzania pliku PDF: {e}") from e

        if not pages_data:
            raise ValueError("Plik PDF nie zawiera tekstu (może być skanem).")

        return pages_data

    @staticmethod
    def build_grounded_context(arxiv_id: str, pages_data: list[dict]) -> str:
        """Starsza metoda tekstowa (zachowana dla trybu full_paper / exact)"""
        clean_id = clean_arxiv_id(arxiv_id)
        formatted_context = f"=== START DOKUMENTU: arXiv:{clean_id} ===\n"
        for p in pages_data:
            formatted_context += f"\n--- [DOKUMENT: {clean_id} | STRONA: {p['page']}] ---\n"
            formatted_context += p.get("text", "") + "\n"
        formatted_context += f"\n=== KONIEC DOKUMENTU: arXiv:{clean_id} ==="
        return formatted_context

    @staticmethod
    def build_xml_grounded_context(
        arxiv_id: str, 
        pages_data: list[dict], 
        expanded_keywords: list[str] | None = None
    ) -> str:
        """
        Nowa funkcja: Buduje ustrukturyzowany kontekst XML oparty na akapitach.
        Jeśli expanded_keywords jest puste (lub brak filtrów), pobiera wszystkie akapity (pełny artykuł).
        W przeciwnym razie filtruje strony i akapity powiązane ze słowami kluczowymi.
        """
        clean_id = clean_arxiv_id(arxiv_id)
        keywords = expanded_keywords or []
        safe_keywords = [re.escape(k) for k in keywords if isinstance(k, str) and len(k) > 2]
        regex_pattern = re.compile(r'\b(' + '|'.join(safe_keywords) + r')\b', re.IGNORECASE) if safe_keywords else None

        xml_pages = []

        for page in pages_data:
            p_num = page.get("page", 1)
            paragraphs = page.get("paragraphs", [])
            
            if not paragraphs:
                # Awaryjny split jeśli w pages_data był tylko plain text
                raw_text = page.get("text", "")
                paragraphs = [p.strip() for p in raw_text.split('\n\n') if p.strip()]

            if not paragraphs:
                continue

            # Logika filtrowania: Strona 1 zawsze wchodzi (Abstrakt/Wstęp). 
            # Pozostałe strony przechodzą, jeśli nie ma filtra (pełny kontekst) lub pasuje regex.
            if p_num == 1 or not regex_pattern or regex_pattern.search(" ".join(paragraphs)):
                formatted_paragraphs = []
                for idx, para in enumerate(paragraphs, 1):
                    clean_para = " ".join(para.split())
                    formatted_paragraphs.append(f"[{idx}] {clean_para}")
                
                paragraphs_str = "\n".join(formatted_paragraphs)
                xml_pages.append(f'  <p n="{p_num}">\n{paragraphs_str}\n  </p>')

        full_xml = f'<doc id="arXiv:{clean_id}">\n' + "\n".join(xml_pages) + "\n</doc>"
        return full_xml