# backend/app/services/citation_service.py
import re
import logging

logger = logging.getLogger(__name__)

class CitationVerifier:
    @staticmethod
    def extract_and_verify_citations(
        generated_text: str, 
        arxiv_id: str, 
        pages_data: list[dict]
    ) -> dict:
        """
        Deterministycznie sprawdza:
        1. Obecność cytowań w formacie [arXiv_ID, p. X] lub [arXiv_ID, Str. X].
        2. Poprawność numerów stron (czy nie wykraczają poza długość PDF).
        """
        max_page = max(p["page"] for p in pages_data) if pages_data else 0
        pages_dict = {p["page"]: p["text"] for p in pages_data}

        # Regex pasujący do: [1706.03762, p. 7], [arXiv:1706.03762, Str. 7] itp.
        citation_pattern = r'\[(?:arXiv:)?' + re.escape(arxiv_id) + r',\s*(?:p\.|p|Str\.|str\.)\s*(\d+)\]'
        
        matches = list(re.finditer(citation_pattern, generated_text))
        
        errors = []
        valid_citations = []

        if not matches:
            errors.append("MISSING_CITATIONS: Response does not contain any valid citations in format [arXiv_ID, p. X].")

        for match in matches:
            cited_page = int(match.group(1))
            
            # Weryfikacja zakresu stron w pliku PDF
            if cited_page < 1 or cited_page > max_page:
                errors.append(
                    f"OUT_OF_BOUNDS_PAGE: Cited page {cited_page}, but paper only has {max_page} pages."
                )
            else:
                valid_citations.append({
                    "page": cited_page,
                    "raw_citation": match.group(0)
                })

        is_valid = len(errors) == 0

        return {
            "is_valid": is_valid,
            "total_citations_found": len(matches),
            "valid_citations_count": len(valid_citations),
            "errors": errors,
            "valid_citations": valid_citations
        }