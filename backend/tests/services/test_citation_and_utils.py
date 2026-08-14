import pytest
from app.services.citation_service import CitationVerifier
from app.services.pdf_service import clean_arxiv_id

class TestCleanArxivID:
    def test_clean_arxiv_id_variants(self):
        """Testuje różne warianty wprowadzanych ID arXiv oraz linków."""
        assert clean_arxiv_id("1706.03762") == "1706.03762"
        assert clean_arxiv_id("https://arxiv.org/abs/1706.03762") == "1706.03762"
        assert clean_arxiv_id("https://arxiv.org/pdf/1706.03762.pdf") == "1706.03762"
        assert clean_arxiv_id("[1706.03762v1]") == "1706.03762v1"
        assert clean_arxiv_id("arxiv:1706.03762") == "1706.03762"


class TestCitationVerifier:
    @pytest.fixture
    def sample_papers_data(self):
        return {
            "1706.03762": [{"page": 1, "text": "A"}, {"page": 2, "text": "B"}, {"page": 3, "text": "C"}],
            "2005.14165": [{"page": 1, "text": "X"}, {"page": 2, "text": "Y"}]
        }

    def test_valid_single_page_citation(self, sample_papers_data):
        text = "Transformer architecture is great [arXiv:1706.03762, p. 2]."
        result = CitationVerifier.extract_and_verify_citations(text, sample_papers_data)
        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    def test_valid_page_range_citation(self, sample_papers_data):
        text = "GPT-3 analysis [arXiv:2005.14165, p. 1-2]."
        result = CitationVerifier.extract_and_verify_citations(text, sample_papers_data)
        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    def test_no_citations_found(self, sample_papers_data):
        text = "This text has no citations at all."
        result = CitationVerifier.extract_and_verify_citations(text, sample_papers_data)
        assert result["is_valid"] is False
        assert "NO_CITATIONS_FOUND" in result["errors"][0]

    def test_invalid_arxiv_id(self, sample_papers_data):
        text = "Cited paper does not exist [arXiv:9999.99999, p. 1]."
        result = CitationVerifier.extract_and_verify_citations(text, sample_papers_data)
        assert result["is_valid"] is False
        assert "INVALID_ARXIV_ID" in result["errors"][0]

    def test_page_out_of_bounds(self, sample_papers_data):
        # 1706.03762 ma tylko 3 strony w naszym obiekcie mocka
        text = "Cited page 10 which is out of range [arXiv:1706.03762, p. 10]."
        result = CitationVerifier.extract_and_verify_citations(text, sample_papers_data)
        assert result["is_valid"] is False
        assert "PAGE_OUT_OF_BOUNDS" in result["errors"][0]