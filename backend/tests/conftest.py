import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.graph.state import MultiPaperState
from app.services.quota_service import quota_service
from app.core.config import settings

@pytest.fixture(scope="function")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

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

@pytest.fixture(autouse=True)
def mock_redis():
    mock_pipe = MagicMock()
    mock_pipe.get = MagicMock()
    mock_pipe.incr = MagicMock()
    mock_pipe.incrby = MagicMock()
    mock_pipe.expire = MagicMock()
    mock_pipe.execute = AsyncMock(return_value=[0, 0, 0])

    mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
    mock_pipe.__aexit__ = AsyncMock(return_value=None)

    mock_client = AsyncMock()
    mock_client.pipeline = MagicMock(return_value=mock_pipe)
    mock_client.get = AsyncMock(return_value="0")

    # Używamy _redis_client zamiast redis
    with patch(
        "app.services.quota_service.quota_service._redis_client", mock_client
    ):
        yield mock_client

@pytest.fixture(autouse=True)
def configure_quota_service_for_tests():
    """Konfiguruje QuotaService tak, aby testy nie odpytywały zewnętrznego serwera Redis,

    ustawiając bezpiecznie pola wewnętrzne lub mockując metody sprawdzające.
    """
    # 1. Bezpieczne ustawienie pól instancji bez walidacji istnienia przez monkeypatch
    setattr(quota_service, "backend_type", "in_memory")

    tracker = getattr(quota_service, "_in_memory_tracker", None)
    if isinstance(tracker, dict):
        tracker.clear()

    # 2. Przygotowanie mocka klienta Redis
    mock_pipe = MagicMock()
    mock_pipe.get = MagicMock()
    mock_pipe.incr = MagicMock()
    mock_pipe.incrby = MagicMock()
    mock_pipe.expire = MagicMock()
    mock_pipe.execute = AsyncMock(return_value=[0, 0, 0])

    mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
    mock_pipe.__aexit__ = AsyncMock(return_value=None)

    mock_client = AsyncMock()
    mock_client.pipeline = MagicMock(return_value=mock_pipe)
    mock_client.get = AsyncMock(return_value="0")

    # Ustawiamy pod obiema potencjalnymi nazwami klienta
    setattr(quota_service, "_redis_client", mock_client)
    setattr(quota_service, "redis_client", mock_client)