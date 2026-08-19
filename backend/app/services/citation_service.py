# /backend/app/services/citation_service.py
import re
from typing import List, Dict, Any

class CitationVerifier:
    # Wzorzec dopasowuje [arXiv:ID, p. X] lub [arXiv:ID, p. X-Y]
    CITATION_PATTERN = re.compile(
        r'\[arXiv:(?P<id>[a-zA-Z0-9\.\/-]+),\s*p\.\s*(?P<start_page>\d+)(?:-(?P<end_page>\d+))?\]'
    )

    @classmethod
    def extract_and_verify_citations(
        cls, 
        generated_text: str, 
        papers_data: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """
        Weryfikuje cytaty dla WIELU artykułów naraz.
        papers_data: słownik { "1706.03762": [strona1, strona2, ...], "2005.14165": [...] }
        """
        citations = cls.CITATION_PATTERN.findall(generated_text)
        errors = []

        if not citations:
            return {
                "is_valid": False,
                "errors": ["NO_CITATIONS_FOUND: The analysis does not contain any required [arXiv:ID, p. X] citations."]
            }

        valid_arxiv_ids = set(papers_data.keys())

        for match in cls.CITATION_PATTERN.finditer(generated_text):
            paper_id = match.group("id")
            start_page = int(match.group("start_page"))
            end_page = int(match.group("end_page")) if match.group("end_page") else start_page

            # 1. Weryfikacja czy ID artykułu jest na liście analizowanych
            if paper_id not in valid_arxiv_ids:
                errors.append(f"INVALID_ARXIV_ID: Cited paper ID '{paper_id}' is not among the requested papers {list(valid_arxiv_ids)}.")
                continue

            # 2. Weryfikacja granic stron dla danego artykułu
            total_pages = len(papers_data[paper_id])
            if start_page < 1 or end_page > total_pages or start_page > end_page:
                errors.append(
                    f"PAGE_OUT_OF_BOUNDS: Citation [arXiv:{paper_id}, p. {start_page}{'-' + str(end_page) if end_page != start_page else ''}] "
                    f"exceeds valid range (1-{total_pages})."
                )

        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }