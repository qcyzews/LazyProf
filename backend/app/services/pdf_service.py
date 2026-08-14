# /backend/app/services/pdf_service.py
import fitz  # PyMuPDF
import io
import re
import httpx
import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)

def clean_arxiv_id(raw_input: str) -> str:
    """Wyciąga czysty ID arXiv (np. '1706.03762') z dowolnego ciągu, URL-a lub Markdowna."""
    match = re.search(r'(\d{4}\.\d{4,5}(?:v\d+)?|[a-zA-Z\-]+/\d{7})', raw_input)
    if match:
        return match.group(1)
    return raw_input.strip().rstrip('/').split('/')[-1].replace('.pdf', '').strip("[]()\"' ")

class PDFService:
    @staticmethod
    async def extract_text_from_url(pdf_url: str, max_pages: int = 15) -> str:
        """
        Pobiera plik PDF z podanego URL bezpośrednio do RAM
        i wyciąga z niego tekst bez zapisu na dysku.
        """
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(pdf_url)
            response.raise_for_status()
            pdf_bytes = response.content

        # Parsowanie w pamięci RAM z użyciem streamu BytesIO
        full_text = []
        with fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf") as doc:
            # Ograniczenie liczby stron chroni przed skrajnie długimi publikacjami
            pages_to_process = min(len(doc), max_pages)
            
            for page_num in range(pages_to_process):
                page = doc.load_page(page_num)
                text = page.get_text("text")
                if text.strip():
                    full_text.append(f"--- STRONA {page_num + 1} ---\n{text}")
                    
        return "\n\n".join(full_text)

    @staticmethod
    async def extract_pages_from_url(pdf_url: str, max_pages: int = 25) -> list[dict]:
        """
        Pobiera PDF z URL i zwraca ustrukturyzowaną listę stron z numerami.
        """
        # Wyciągamy czysty ID i budujemy pewny URL do PDF-a
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

            if not pages_data:
                raise HTTPException(status_code=400, detail="Nie udało się wyekstrahować tekstu z podanego pliku PDF.")

            return pages_data

        except httpx.HTTPError as e:
            logger.error(f"Błąd HTTP podczas pobierania PDF z {clean_url}: {e}")
            raise HTTPException(status_code=500, detail=f"Błąd pobierania pliku PDF: {str(e)}")
        except Exception as e:
            logger.error(f"Błąd przetwarzania PDF z {clean_url}: {e}")
            raise HTTPException(status_code=500, detail=f"Błąd przetwarzania pliku PDF: {str(e)}")
        

    @staticmethod
    def build_grounded_context(arxiv_id: str, pages_data: list[dict]) -> str:
        """
        Formatuje wyekstrahowane strony do postaci kontekstu dla LLM
        z wyraźnymi znacznikami arXiv ID oraz numeracji stron.
        """
        formatted_context = f"=== START DOKUMENTU: arXiv:{arxiv_id} ===\n"
        for p in pages_data:
            formatted_context += f"\n--- [DOKUMENT: {arxiv_id} | STRONA: {p['page']}] ---\n"
            formatted_context += p["text"] + "\n"
        formatted_context += f"\n=== KONIEC DOKUMENTU: arXiv:{arxiv_id} ==="
        return formatted_context