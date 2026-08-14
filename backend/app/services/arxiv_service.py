# backend/app/services/arxiv_service.py
import httpx
import xml.etree.ElementTree as ET
from typing import Dict, Any
import logging

logger = logging.getLogger("uvicorn.error")

class ArxivService:
    @staticmethod
    async def fetch_paper_metadata(arxiv_id: str) -> Dict[str, Any]:
        """Pobiera metadane artykułu (tytuł, autorzy, data, URL) bezpośrednio z API arXiv."""
        url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
        logger.info(f"🌐 [arXiv API] Pobieranie metadanych dla: {arxiv_id}")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()

            root = ET.fromstring(response.text)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entry = root.find('atom:entry', ns)

            if entry is None:
                logger.warning(f"⚠️ [arXiv API] Nie znaleziono wpisu dla ID: {arxiv_id}")
                return ArxivService._fallback_metadata(arxiv_id)

            title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
            published = entry.find('atom:published', ns).text[:10]  # Format YYYY-MM-DD
            authors = [author.find('atom:name', ns).text for author in entry.findall('atom:author', ns)]

            return {
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": authors,
                "published": published,
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                "abs_url": f"https://arxiv.org/abs/{arxiv_id}"
            }

        except Exception as e:
            logger.error(f"❌ [arXiv API] Błąd podczas pobierania metadanych: {e}")
            return ArxivService._fallback_metadata(arxiv_id)

    @staticmethod
    def _fallback_metadata(arxiv_id: str) -> Dict[str, Any]:
        return {
            "arxiv_id": arxiv_id,
            "title": f"Paper arXiv:{arxiv_id}",
            "authors": ["Unknown Authors"],
            "published": "N/A",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            "abs_url": f"https://arxiv.org/abs/{arxiv_id}"
        }