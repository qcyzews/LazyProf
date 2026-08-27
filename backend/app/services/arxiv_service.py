import asyncio
import time
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
import httpx

from app.core.config import settings
from app.services.quota_service import quota_service

logger = logging.getLogger("uvicorn.error")

class ArxivService:
    _last_request_time: float = 0.0
    _local_rate_lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    async def _wait_for_rate_limit(cls):
        """
        Globalny Rate Limiter.
        Używa Redisa (Distributed Lock) dla wielu instancji backendu,
        lub lokalnego asyncio.Lock jeśli backend działa w trybie in_memory.
        """
        redis_client = getattr(quota_service, "_redis_client", None)

        if settings.QUOTA_BACKEND == "redis" and redis_client:
            lock_key = "lock:arxiv_rate_limit"
            interval_ms = int(settings.ARXIV_REQUEST_INTERVAL_SECONDS * 1000)

            # Pętla oczekiwania na wolne okienko w Redisie
            while True:
                # Atomowy SET z ograniczeniem czasowym (PX) i warunkiem NX (tylko gdy klucz nie istnieje)
                acquired = await redis_client.set(lock_key, "locked", px=interval_ms, nx=True)
                if acquired:
                    logger.debug("🌐 [arXiv RateLimiter (Redis)] Uzyskano dostęp do API arXiv.")
                    break
                
                # Jeśli inna instancja właśnie wysłała zapytanie, czekamy 200ms i sprawdzamy ponownie
                await asyncio.sleep(0.2)
        else:
            # Fallback dla pojedynczej instancji / in_memory
            async with cls._local_rate_lock:
                now = time.monotonic()
                elapsed = now - cls._last_request_time
                wait_time = settings.ARXIV_REQUEST_INTERVAL_SECONDS - elapsed
                if wait_time > 0:
                    logger.debug(f"⏳ [arXiv RateLimiter (Local)] Oczekiwanie {wait_time:.2f}s...")
                    await asyncio.sleep(wait_time)
                cls._last_request_time = time.monotonic()

    @classmethod
    def _get_headers(cls) -> Dict[str, str]:
        return {
            "User-Agent": settings.ARXIV_USER_AGENT
        }

    @classmethod
    async def fetch_paper_metadata(cls, arxiv_id: str) -> Dict[str, Any]:
        """Pobiera metadane artykułu z API arXiv z uwzględnieniem globalnego limitu."""
        url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
        logger.info(f"🌐 [arXiv API] Pobieranie metadanych dla ID: {arxiv_id}")
        
        await cls._wait_for_rate_limit()

        try:
            async with httpx.AsyncClient(headers=cls._get_headers()) as client:
                response = await client.get(url, timeout=settings.ARXIV_TIMEOUT_SECONDS)
                response.raise_for_status()

            root = ET.fromstring(response.text)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entry = root.find('atom:entry', ns)

            if entry is None:
                logger.warning(f"⚠️ [arXiv API] Nie znaleziono wpisu dla ID: {arxiv_id}")
                return cls._fallback_metadata(arxiv_id)

            return cls._parse_entry(entry, ns)

        except httpx.HTTPStatusError as e:
            logger.error(f"❌ [arXiv API] Błąd HTTP {e.response.status_code} dla ID {arxiv_id}: {e}")
            return cls._fallback_metadata(arxiv_id)
        except Exception as e:
            logger.error(f"❌ [arXiv API] Błąd podczas pobierania metadanych: {e}")
            return cls._fallback_metadata(arxiv_id)

    @classmethod
    async def search_papers(cls, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Wyszukuje artykuły w arXiv z uwzględnieniem globalnego limitu."""
        url = f"https://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results={max_results}"
        logger.info(f"🌐 [arXiv API] Wyszukiwanie frazy: '{query}' (max: {max_results})")

        await cls._wait_for_rate_limit()

        try:
            async with httpx.AsyncClient(headers=cls._get_headers()) as client:
                response = await client.get(url, timeout=settings.ARXIV_TIMEOUT_SECONDS)
                response.raise_for_status()

            root = ET.fromstring(response.text)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entries = root.findall('atom:entry', ns)

            return [cls._parse_entry(entry, ns) for entry in entries]

        except Exception as e:
            logger.error(f"❌ [arXiv API] Błąd podczas wyszukiwania: {e}")
            return []

    @classmethod
    async def download_pdf_bytes(cls, pdf_url: str) -> Optional[bytes]:
        """Pobiera zawartość PDF z arXiv z uwzględnieniem limitów prędkości."""
        logger.info(f"📥 [arXiv Download] Pobieranie PDF: {pdf_url}")
        await cls._wait_for_rate_limit()

        try:
            async with httpx.AsyncClient(headers=cls._get_headers(), follow_redirects=True) as client:
                response = await client.get(pdf_url, timeout=30.0)
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error(f"❌ [arXiv Download] Nie udało się pobrać PDF ({pdf_url}): {e}")
            return None

    @staticmethod
    def _parse_entry(entry: ET.Element, ns: dict) -> Dict[str, Any]:
        raw_id = entry.find('atom:id', ns).text.strip()
        arxiv_id = raw_id.split('/abs/')[-1].split('v')[0]

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