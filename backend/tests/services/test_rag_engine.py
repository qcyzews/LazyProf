import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.rag_engine import RAGEngine
from app.graph.state import JudgeEvaluation


@pytest.fixture
def rag_engine():
    """Tworzy instancję RAGEngine z zamockowanymi modelami LangChain."""
    with patch("app.services.rag_engine.ChatGoogleGenerativeAI"):
        engine = RAGEngine()
        engine.map_llm = MagicMock()
        engine.reduce_llm = MagicMock()
        engine.judge_llm = MagicMock()
        return engine


async def mock_async_generator(items):
    """Funkcja pomocnicza symulująca asynchroniczny generator dla astream."""
    for item in items:
        yield item


# ============================================================================
# TESTY METOD BUDUJĄCYCH PROMPTY (get_*_messages)
# ============================================================================

def test_get_map_messages(rag_engine):
    """Testuje poprawność budowania wiadomości dla etapu MAP."""
    messages = rag_engine.get_map_messages(
        title="Attention Is All You Need",
        arxiv_id="1706.03762",
        user_instruction="Podsumuj architekturę Transformer",
        text="Sample article content " * 1000
    )

    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert "Attention Is All You Need" in messages[1].content
    assert "1706.03762" in messages[1].content


def test_get_reduce_messages_formatting_and_retry(rag_engine):
    """Testuje formatowanie bloków kontekstu i sekcję poprawek (retry) w REDUCE."""
    context_blocks = [
        "Czysty tekst podsumowania",
        {"arxiv_id": "111", "title": "Paper A", "summary": "Podsumowanie A"},
        {"arxiv_id": "222", "title": "Paper B", "content": "Treść B"},
        {"other_key": "custom_data"}  # Fallback do json.dumps
    ]

    # Test dla retry_count = 0 (bez błędów)
    messages_normal = rag_engine.get_reduce_messages(
        context_blocks=context_blocks,
        user_instruction="Napisz przegląd literatury"
    )
    assert "CRITICAL CORRECTIONS REQUIRED" not in messages_normal[1].content
    assert "### [arXiv:111] Paper A\nPodsumowanie A" in messages_normal[1].content

    # Test dla retry_count > 0 z błędami weryfikacji
    messages_retry = rag_engine.get_reduce_messages(
        context_blocks=context_blocks,
        user_instruction="Napisz przegląd literatury",
        retry_count=1,
        verification_errors=["Brak cytowania dla metryki X"],
        judge_feedback="Uzupełnij brakujące dane"
    )
    assert "CRITICAL CORRECTIONS REQUIRED (Attempt 2)" in messages_retry[1].content
    assert "Brak cytowania dla metryki X" in messages_retry[1].content
    assert "Uzupełnij brakujące dane" in messages_retry[1].content


def test_get_judge_messages(rag_engine):
    """Testuje tworzenie wiadomości dla ewaluatora (Judge)."""
    papers_data = {"1706.03762": {"title": "Transformer"}}
    report_markdown = "# Raport końcowy\nTransfomer [arXiv:1706.03762] jest skuteczny."

    messages = rag_engine.get_judge_messages(papers_data, report_markdown)

    assert len(messages) == 2
    assert "1706.03762" in messages[1].content
    assert "# Raport końcowy" in messages[1].content


# ============================================================================
# TESTY WYWOŁAŃ MODELI LLM (run_*_llm)
# ============================================================================

@pytest.mark.asyncio
async def test_run_map_llm_various_responses(rag_engine):
    """Testuje wywołanie map_llm dla odpowiedzi tekstowych i struktur typu list/dict."""
    # Przypadek 1: Zwykły str
    rag_engine.map_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Wynik MAP w tekście"))
    result_str = await rag_engine.run_map_llm([])
    assert result_str == "Wynik MAP w tekście"

    # Przypadek 2: Lista dictów z kluczem 'text'
    rag_engine.map_llm.ainvoke = AsyncMock(return_value=MagicMock(content=[{"text": "Wynik z listy"}]))
    result_list = await rag_engine.run_map_llm([])
    assert result_list == "Wynik z listy"


@pytest.mark.asyncio
async def test_run_reduce_llm_various_responses(rag_engine):
    """Testuje wywołanie reduce_llm i scalanie wyników."""
    # Odpowiedź w postaci listy bloków
    mock_content = [{"text": "Część 1. "}, {"text": "Część 2."}]
    rag_engine.reduce_llm.ainvoke = AsyncMock(return_value=MagicMock(content=mock_content))

    result = await rag_engine.run_reduce_llm([])
    assert result == "Część 1. Część 2."


@pytest.mark.asyncio
async def test_run_judge_llm_success_and_fallback(rag_engine):
    """Testuje działanie Judge LLM przy sukcesie oraz fallback w przypadku wyjątku."""
    mock_structured = AsyncMock()
    expected_eval = JudgeEvaluation(is_grounded=True, errors=[])
    mock_structured.ainvoke.return_value = expected_eval
    rag_engine.judge_llm.with_structured_output.return_value = mock_structured

    # 1. Sukces
    result = await rag_engine.run_judge_llm([])
    assert result == expected_eval

    # 2. Błąd w wywołaniu -> Oczekiwany fallback z domyślnym obiektem
    mock_structured.ainvoke.side_effect = Exception("API Timeout")
    fallback_result = await rag_engine.run_judge_llm([])
    assert fallback_result.is_grounded is True
    assert fallback_result.errors == []


# ============================================================================
# TESTY METOD PROCESU (run_map_stage_parallel, stream_*)
# ============================================================================

@pytest.mark.asyncio
async def test_run_map_stage_parallel(rag_engine):
    """Testuje równoległe przetwarzanie etapu MAP dla listy artykułów."""
    with patch.object(rag_engine, "run_map_llm", new_callable=AsyncMock) as mock_run_map:
        mock_run_map.side_effect = ["Podsumowanie Paper 1", "Podsumowanie Paper 2"]

        articles = [
            {"title": "Paper 1", "arxiv_id": "111", "text": "Tekst 1"},
            {"title": "Paper 2", "arxiv_id": "222", "text": "Tekst 2"},
        ]

        results = await rag_engine.run_map_stage_parallel(articles, "Instrukcja użytkownika")

        assert len(results) == 2
        assert "### Paper: Paper 1 (arXiv:111)\nPodsumowanie Paper 1" in results[0]
        assert "### Paper: Paper 2 (arXiv:222)\nPodsumowanie Paper 2" in results[1]
        assert mock_run_map.call_count == 2


@pytest.mark.asyncio
async def test_stream_reduce_stage(rag_engine):
    """Testuje strumieniowanie z etapu REDUCE."""
    chunks = [
        MagicMock(content="Oto "),
        MagicMock(content="raport "),
        MagicMock(content="końcowy."),
        MagicMock(content="")  # Pusty chunk -> ignorowany
    ]
    rag_engine.reduce_llm.astream.side_effect = lambda messages: mock_async_generator(chunks)

    collected = []
    async for token in rag_engine.stream_reduce_stage(["Sum 1", "Sum 2"], "Instrukcja"):
        collected.append(token)

    assert "".join(collected) == "Oto raport końcowy."


@pytest.mark.asyncio
async def test_stream_translation_various_chunk_structures(rag_engine):
    """Testuje strumieniowanie tłumaczenia dla różnych formatów chunków (stringi, listy, słowniki)."""
    chunks = [
        MagicMock(content="Tekst jako string. "),
        MagicMock(content=["Tekst jako element listy. "]),
        MagicMock(content=[{"type": "text", "text": "Tekst z dict w stylu Anthropic."}]),
        MagicMock(content=None)  # Ignorowany
    ]
    rag_engine.reduce_llm.astream.side_effect = lambda messages: mock_async_generator(chunks)

    output_chunks = []
    async for chunk in rag_engine.stream_translation("# Report Markdown", "Polish"):
        output_chunks.append(chunk)

    full_translation = "".join(output_chunks)
    assert "Tekst jako string." in full_translation
    assert "Tekst jako element listy." in full_translation
    assert "Tekst z dict w stylu Anthropic." in full_translation


@pytest.mark.asyncio
async def test_stream_translation_error_handling(rag_engine):
    """Testuje przekazywanie i logowanie błędów podczas tłumaczenia."""
    def failing_generator(messages):
        async def _gen():
            raise RuntimeError("Błąd połączenia ze strumieniem LLM")
            yield
        return _gen()

    rag_engine.reduce_llm.astream.side_effect = failing_generator

    with pytest.raises(RuntimeError, match="Błąd połączenia ze strumieniem LLM"):
        async for _ in rag_engine.stream_translation("# Report", "German"):
            pass