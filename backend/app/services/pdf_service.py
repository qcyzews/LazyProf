import fitz  # PyMuPDF
import io
import httpx
import logging

logger = logging.getLogger(__name__)

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