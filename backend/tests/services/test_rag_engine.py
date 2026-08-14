# /backend/tests/services/test_rag_engine.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from google.genai.errors import APIError

from app.services.rag_engine import RAGEngine


# Tworzymy klasę pomocniczą do symulowania APIError bez budowania pełnego response_json
class DummyAPIError(APIError):
    def __init__(self, message="Google API Error"):
        # Omijamy wywołanie super().__init__ z brakującym response_json
        Exception.__init__(self, message)


@pytest.fixture
def rag_engine():
    """Tworzy instancję RAGEngine z zamockowanymi modelami LangChain."""
    with patch("app.services.rag_engine.ChatGoogleGenerativeAI"):
        engine = RAGEngine()
        engine.map_llm = AsyncMock()
        engine.reduce_llm = AsyncMock()
        return engine


async def mock_async_generator(chunks):
    """Funkcja pomocnicza symulująca asynchroniczny generator dla astream."""
    for chunk in chunks:
        yield chunk


# ============================================================================
# TESTY: analyze_single_article (MAP STAGE)
# ============================================================================

@pytest.mark.asyncio
async def test_analyze_single_article_success_string(rag_engine):
    """Testuje udaną analizę artykułu gdy LLM zwraca zwykły tekst."""
    mock_response = MagicMock()
    mock_response.content = "Wyekstrahowane wnioski z artykułu."
    rag_engine.map_llm.ainvoke.return_value = mock_response

    result = await rag_engine.analyze_single_article("Treść artykułu", "Instrukcja")

    assert result == "Wyekstrahowane wnioski z artykułu."
    rag_engine.map_llm.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_single_article_success_list_dict(rag_engine):
    """Testuje przypadek, gdy LLM zwraca odpowiedź w strukturze list[dict]."""
    mock_response = MagicMock()
    mock_response.content = [{"text": "Wniosek z listy dict"}]
    rag_engine.map_llm.ainvoke.return_value = mock_response

    result = await rag_engine.analyze_single_article("Treść", "Instrukcja")

    assert result == "Wniosek z listy dict"


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_analyze_single_article_retry_and_fail(mock_sleep, rag_engine):
    """Testuje mechanizm ponawiania prób i ostateczny wyjątek."""
    rag_engine.map_llm.ainvoke.side_effect = DummyAPIError("Błąd API Google")

    with pytest.raises(APIError):
        await rag_engine.analyze_single_article("Tekst", "Instrukcja")


# ============================================================================
# TESTY: run_map_stage_parallel
# ============================================================================

@pytest.mark.asyncio
async def test_run_map_stage_parallel(rag_engine):
    """Testuje równoległe przetwarzanie wielu artykułów w fazie MAP."""
    with patch.object(rag_engine, "analyze_single_article", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.side_effect = ["Podsumowanie 1", "Podsumowanie 2"]

        articles = [
            {"title": "Paper 1", "arxiv_id": "111", "text": "Tekst 1"},
            {"title": "Paper 2", "arxiv_id": "222", "text": "Tekst 2"},
        ]

        summaries = await rag_engine.run_map_stage_parallel(articles, "Instrukcja")

        assert len(summaries) == 2
        assert summaries[0] == {"title": "Paper 1", "arxiv_id": "111", "summary": "Podsumowanie 1"}
        assert summaries[1] == {"title": "Paper 2", "arxiv_id": "222", "summary": "Podsumowanie 2"}


# ============================================================================
# TESTY: stream_reduce_stage (REDUCE STAGE)
# ============================================================================

@pytest.mark.asyncio
async def test_stream_reduce_stage_various_chunk_types(rag_engine):
    """Testuje strumieniowanie z różnymi typami danych w kawałkach (chunkach)."""
    chunks = [
        MagicMock(content=""),                              # Pusty chunk -> ignorowany
        MagicMock(content="Fragment 1 "),                   # str
        MagicMock(content=[{"text": "Fragment 2 "}]),       # list[dict]
        MagicMock(content=["Fragment 3 "]),                 # list[str]
        MagicMock(content=[123]),                           # list[inne]
        MagicMock(content={"text": "Fragment 4 "}),         # dict z 'text'
        MagicMock(content={"key": "val"}),                  # dict bez 'text'
    ]

    rag_engine.reduce_llm.astream = MagicMock(return_value=mock_async_generator(chunks))

    map_summaries = [{"title": "Art 1", "arxiv_id": "001", "summary": "Sum 1"}]
    collected_text = []

    async for chunk in rag_engine.stream_reduce_stage(map_summaries, "Instrukcja"):
        collected_text.append(chunk)

    full_output = "".join(collected_text)
    assert "Fragment 1" in full_output
    assert "Fragment 2" in full_output
    assert "Fragment 3" in full_output
    assert "123" in full_output
    assert "Fragment 4" in full_output
    assert "{'key': 'val'}" in full_output


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_stream_reduce_stage_retry_and_fail(mock_sleep, rag_engine):
    """Testuje obsługę błędów i ponawianie prób podczas strumieniowania REDUCE."""
    async def failing_generator(messages):
        raise DummyAPIError("Stream error")
        yield

    rag_engine.reduce_llm.astream = MagicMock(side_effect=failing_generator)
    map_summaries = [{"title": "Art 1", "arxiv_id": "001", "summary": "Sum 1"}]

    with pytest.raises(APIError):
        async for _ in rag_engine.stream_reduce_stage(map_summaries, "Instrukcja"):
            pass


# ============================================================================
# TESTY: stream_translation
# ============================================================================

@pytest.mark.asyncio
async def test_stream_translation_success(rag_engine):
    """Testuje strumieniowe tłumaczenie tekstu."""
    chunks = [
        MagicMock(content="Oto "),
        MagicMock(content=[{"text": "przetłumaczony "}]),
        MagicMock(content={"text": "tekst."}),
    ]

    rag_engine.reduce_llm.astream = MagicMock(return_value=mock_async_generator(chunks))

    translated_chunks = []
    async for chunk in rag_engine.stream_translation("# Report", "Polish"):
        translated_chunks.append(chunk)

    assert "".join(translated_chunks) == "Oto przetłumaczony tekst."


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_stream_translation_retry_and_fail(mock_sleep, rag_engine):
    """Testuje niepowodzenie tłumaczenia po wyczerpaniu limitu prób."""
    async def failing_generator(messages):
        raise Exception("Translation network glitch")
        yield

    rag_engine.reduce_llm.astream = MagicMock(side_effect=failing_generator)

    with pytest.raises(Exception, match="Translation network glitch"):
        async for _ in rag_engine.stream_translation("Text", "Polish"):
            pass

    assert rag_engine.reduce_llm.astream.call_count == 3
    assert mock_sleep.call_count == 2