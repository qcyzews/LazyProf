import pytest
from unittest.mock import AsyncMock

from app.graph.workflow import multi_paper_graph


def test_workflow_structure():
    """Weryfikacja czy graf zawiera wszystkie wymagane węzły."""
    nodes = multi_paper_graph.get_graph().nodes
    
    expected_nodes = [
        "expand_query",
        "fetch_papers",
        "generate_synthesis",
        "python_verifier",
        "llm_judge",
        "record_failed_attempt",
        "format_final_report"
    ]
    
    for node in expected_nodes:
        assert node in nodes


@pytest.mark.asyncio
async def test_workflow_execution_flow(mock_state, mocker):
    """
    Test integracyjny przejścia przez graf od START do END przy użyciu mocków węzłów.
    """
    # Mockujemy ciężkie operacje (LLM, Pobieranie PDF)
    mocker.patch("app.graph.nodes.expand_keywords_with_llm", AsyncMock(return_value=["kw1"]))
    mocker.patch("app.graph.nodes.PDFService.extract_pages_from_url", AsyncMock(return_value=[{"page": 1, "text": "text"}]))
    mocker.patch("app.graph.nodes.ArxivService.fetch_paper_metadata", AsyncMock(return_value={"title": "Test Paper"}))
    
    # Mock wywołania modeli LLM w generatorze i sędzi
    mock_llm_response = mocker.MagicMock()
    mock_llm_response.content = "Wygenerowana analiza [arXiv:1706.03762, p. 1]"
    mocker.patch("app.graph.nodes.safe_llm_invoke", AsyncMock(return_value=mock_llm_response))
    
    # Executujemy skompilowany graf
    final_output = await multi_paper_graph.ainvoke(mock_state)

    assert "analysis_markdown" in final_output
    assert final_output["retry_count"] >= 1