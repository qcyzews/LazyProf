# /backend/app/services/search_service.py
import logging
from typing import List, Dict, Any
from app.services.arxiv_service import ArxivService
from app.graph.nodes import expand_keywords_with_llm  # Twoja istniejąca funkcja LLM

logger = logging.getLogger("uvicorn.error")

class SearchService:
    @staticmethod
    async def search_with_expansion(
        query: str, 
        max_results: int = 5,
        user_mode: str = "fast"
    ) -> Dict[str, Any]:
        """
        Orkiestruje cały proces wyszukiwania:
        1. Rozszerza zapytanie użytkownika o synonimy/pojęcia naukowe przez LLM.
        2. Przekazuje rozszerzoną frazę do ArxivService.
        """
        logger.info(f"🔍 [SearchService] Inicjalizacja szukania dla: '{query}'")

        # 1. Rozszerzenie słów kluczowych przez LLM
        try:
            expanded_keywords = await expand_keywords_with_llm(query, mode_key=user_mode)
            # Jeśli funkcja zwroci listę słów kluczowych, łączymy je w zapytanie or
            if isinstance(expanded_keywords, list):
                search_query = " OR ".join([f'"{kw}"' for kw in expanded_keywords])
            else:
                search_query = expanded_keywords
        except Exception as e:
            logger.warning(f"⚠️ [SearchService] Błąd ekspansji query, użycie oryginalnego zapytania: {e}")
            search_query = query

        logger.info(f"🧠 [SearchService] Rozszerzone zapytanie: {search_query}")

        # 2. Pobranie artykułów z arXiv
        articles = await ArxivService.search_papers(query=search_query, max_results=max_results)

        # 3. Zwracamy artykuły oraz metadane wyszukiwania
        return {
            "original_query": query,
            "expanded_query": search_query,
            "articles": articles
        }
    