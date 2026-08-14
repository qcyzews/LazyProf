import pytest
from app.graph.state import MultiPaperState


@pytest.fixture
def mock_state() -> MultiPaperState:
    return {
        "user_instruction": "Przeanalizuj mechanizmy uwagi w sieciach Transformer.",
        "arxiv_ids": ["1706.03762"],
        "mode": "fast",
        "expanded_keywords": ["transformer", "self-attention", "multi-head"],
        "papers_data": {
            "1706.03762": [
                {"page": 1, "text": "Attention Is All You Need. We propose the Transformer..."},
                {"page": 5, "text": "Multi-head attention uses 8 parallel attention heads."}
            ]
        },
        "papers_metadata": {
            "1706.03762": {
                "title": "Attention Is All You Need",
                "authors": ["Ashish Vaswani", "Noam Shazeer"],
                "published": "2017",
                "abs_url": "https://arxiv.org/abs/1706.03762",
                "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf"
            }
        },
        "analysis_markdown": "Model wykorzystuje 8 głowic uwagi [arXiv:1706.03762, p. 5].",
        "is_valid": True,
        "retry_count": 0,
        "verification_errors": [],
        "audit_trail": [],
        "judge_feedback": ""
    }