import httpx
import xml.etree.ElementTree as ET
from typing import Dict, Any, List
import logging

logger = logging.getLogger("uvicorn.error")

class ArxivService:
    @staticmethod
    async def fetch_paper_metadata(arxiv_id: str) -> Dict[str, Any]:
        """Pobiera metadane artykułu bezpośrednio z API arXiv na podstawie ID."""
        url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
        logger.info(f"🌐 [arXiv API] Pobieranie metadanych dla ID: {arxiv_id}")
        
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

            return ArxivService._parse_entry(entry, ns)

        except Exception as e:
            logger.error(f"❌ [arXiv API] Błąd podczas pobierania metadanych: {e}")
            return ArxivService._fallback_metadata(arxiv_id)

    @staticmethod
    async def search_papers(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Wyszukuje artykuły w arXiv na podstawie zapytania wyszukiwania."""
        url = f"https://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results={max_results}"
        logger.info(f"🌐 [arXiv API] Wyszukiwanie frazy: '{query}' (max: {max_results})")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()

            root = ET.fromstring(response.text)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entries = root.findall('atom:entry', ns)

            results = []
            for entry in entries:
                results.append(ArxivService._parse_entry(entry, ns))

            return results

        except Exception as e:
            logger.error(f"❌ [arXiv API] Błąd podczas wyszukiwania artykułów: {e}")
            return []

    @staticmethod
    def _parse_entry(entry: ET.Element, ns: dict) -> Dict[str, Any]:
        """Pomocnicza funkcja do parsowania węzła XML entry z arXiv."""
        raw_id = entry.find('atom:id', ns).text.strip()
        arxiv_id = raw_id.split('/abs/')[-1].split('v')[0]  # Oczyszczenie ID z wersji np. 1706.03762v5 -> 1706.03762

        title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
        published = entry.find('atom:published', ns).text[:10]
        summary = entry.find('atom:summary', ns).text.strip().replace('\n', ' ') if entry.find('atom:summary', ns) is not None else ""
        authors = [author.find('atom:name', ns).text for author in entry.findall('atom:author', ns)]

        return {
            "arxiv_id": arxiv_id,
            "title": title,
            "summary": summary,
            "authors": authors,
            "published": published,
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            "abs_url": f"https://arxiv.org/abs/{arxiv_id}"
        }

    @staticmethod
    def _fallback_metadata(arxiv_id: str) -> Dict[str, Any]:
        return {
            "arxiv_id": arxiv_id,
            "title": f"Paper arXiv:{arxiv_id}",
            "summary": "N/A",
            "authors": ["Unknown Authors"],
            "published": "N/A",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            "abs_url": f"https://arxiv.org/abs/{arxiv_id}"
        }