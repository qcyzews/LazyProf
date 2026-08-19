# /backend/tests/test_workflow.py
import pytest
from unittest.mock import AsyncMock, patch
from langgraph.graph import END, START

from app.graph.workflow import create_workflow, app_graph


# --- TESTY STRUKTURY GRAFU ---

def test_graph_nodes_registration():
    """Testuje, czy wszystkie wymagane węzły zostały zarejestrowane w grafie."""
    nodes = app_graph.nodes
    expected_nodes = {
        "fetch_papers",
        "generate_synthesis",
        "python_verifier",
        "llm_judge",
        "record_failed_attempt",
        "format_final_report",
    }
    for node in expected_nodes:
        assert node in nodes


def test_graph_edges_structure():
    """Sprawdza połączenia statyczne i obecność krawędzi warunkowych w obiekcie grafu."""
    graph_dict = app_graph.get_graph().to_json()
    edges = [(e["source"], e["target"]) for e in graph_dict.get("edges", [])]
    
    # Krawędzie statyczne
    assert (START, "fetch_papers") in edges
    assert ("fetch_papers", "generate_synthesis") in edges
    assert ("generate_synthesis", "python_verifier") in edges
    assert ("python_verifier", "llm_judge") in edges
    assert ("format_final_report", END) in edges


# --- TESTY INTEGRACYJNE PRZEPŁYWU (WORKFLOW EXECUTION) ---

@pytest.mark.asyncio
@patch("app.graph.nodes.fetch_papers_node", new_callable=AsyncMock)
@patch("app.graph.nodes.generate_synthesis_node", new_callable=AsyncMock)
@patch("app.graph.nodes.python_verifier_node", new_callable=AsyncMock)
@patch("app.graph.nodes.llm_judge_node", new_callable=AsyncMock)
@patch("app.graph.nodes.record_failed_attempt_node", new_callable=AsyncMock)
@patch("app.graph.nodes.format_final_report_node", new_callable=AsyncMock)
async def test_workflow_happy_path(
    mock_format_final_report,
    mock_record_failed_attempt,
    mock_llm_judge,
    mock_python_verifier,
    mock_generate_synthesis,
    mock_fetch_papers,
):
    """Testuje przejście przez graf w przypadku natychmiastowego sukcesu (bez pętli poprawek)."""
    test_graph = create_workflow()
    mock_fetch_papers.side_effect = lambda state: {"papers_data": {"2601.05264": {}}}
    mock_generate_synthesis.side_effect = lambda state: {"analysis_markdown": "Syntetyzowany tekst", "retry_count": 1}
    mock_python_verifier.side_effect = lambda state: {"is_valid": True, "verification_errors": []}
    mock_llm_judge.side_effect = lambda state: {"is_valid": True, "judge_feedback": "Passed"}
    mock_format_final_report.side_effect = lambda state: {"analysis_markdown": "Finalny Raport"}

    initial_state = {
        "arxiv_ids": ["2601.05264"],
        "user_instruction": "Przeanalizuj papier",
        "retry_count": 0,
        "audit_trail": []
    }

    final_state = await test_graph.ainvoke(initial_state)

    # Weryfikacja
    assert final_state["analysis_markdown"] == "Finalny Raport"
    
    # Usługi wywołane po 1 razie
    mock_fetch_papers.assert_awaited_once()
    mock_generate_synthesis.assert_awaited_once()
    mock_python_verifier.assert_awaited_once()
    mock_llm_judge.assert_awaited_once()
    mock_format_final_report.assert_awaited_once()
    
    # Rekord pomyłek nie powinien być wywołany
    mock_record_failed_attempt.assert_not_called()


@pytest.mark.asyncio
@patch("app.graph.nodes.fetch_papers_node", new_callable=AsyncMock)
@patch("app.graph.nodes.generate_synthesis_node", new_callable=AsyncMock)
@patch("app.graph.nodes.python_verifier_node", new_callable=AsyncMock)
@patch("app.graph.nodes.llm_judge_node", new_callable=AsyncMock)
@patch("app.graph.nodes.record_failed_attempt_node", new_callable=AsyncMock)
@patch("app.graph.nodes.format_final_report_node", new_callable=AsyncMock)
async def test_workflow_retry_loop_then_success(
    mock_format_final_report,
    mock_record_failed_attempt,
    mock_llm_judge,
    mock_python_verifier,
    mock_generate_synthesis,
    mock_fetch_papers,
):
    test_graph = create_workflow()
    """Testuje sytuację, w której pierwsza próba zawodzi, a druga kończy się sukcesem."""
    mock_fetch_papers.side_effect = lambda state: {"papers_data": {"2601.05264": {}}}
    
    # Pierwsze wywołanie: retry_count=1 (odrzucone), Drugie wywołanie: retry_count=2 (zaakceptowane)
    synthesis_call_count = 0
    def mock_synthesis_logic(state):
        nonlocal synthesis_call_count
        synthesis_call_count += 1
        return {"analysis_markdown": f"Analiza {synthesis_call_count}", "retry_count": synthesis_call_count}
    
    mock_generate_synthesis.side_effect = mock_synthesis_logic
    mock_python_verifier.side_effect = lambda state: {"is_valid": True, "verification_errors": []}
    
    # Pierwsza ocena Sędziego: Niepoprawny, Druga ocena: Poprawny
    judge_call_count = 0
    def mock_judge_logic(state):
        nonlocal judge_call_count
        judge_call_count += 1
        if judge_call_count == 1:
            return {"is_valid": False, "judge_feedback": "Błąd merytoryczny"}
        return {"is_valid": True, "judge_feedback": "Passed"}

    mock_llm_judge.side_effect = mock_judge_logic

    def mock_record_logic(state):
        return {
            "audit_trail": state.get("audit_trail", []) + [{"attempt": state.get("retry_count")}],
            "retry_count": state.get("retry_count", 0)
        }
    
    mock_record_failed_attempt.side_effect = mock_record_logic
    mock_format_final_report.side_effect = lambda state: {"analysis_markdown": "Ostateczny Raport Po Poprawce"}

    initial_state = {
        "arxiv_ids": ["2601.05264"],
        "user_instruction": "Test",
        "retry_count": 0,
        "audit_trail": []
    }

    final_state = await test_graph.ainvoke(initial_state)

    assert final_state["analysis_markdown"] == "Ostateczny Raport Po Poprawce"
    assert mock_generate_synthesis.call_count == 2
    assert mock_llm_judge.call_count == 2
    assert mock_record_failed_attempt.call_count == 1
    assert mock_format_final_report.call_count == 1


@pytest.mark.asyncio
@patch("app.graph.nodes.fetch_papers_node", new_callable=AsyncMock)
@patch("app.graph.nodes.generate_synthesis_node", new_callable=AsyncMock)
@patch("app.graph.nodes.python_verifier_node", new_callable=AsyncMock)
@patch("app.graph.nodes.llm_judge_node", new_callable=AsyncMock)
@patch("app.graph.nodes.record_failed_attempt_node", new_callable=AsyncMock)
@patch("app.graph.nodes.format_final_report_node", new_callable=AsyncMock)
async def test_workflow_max_retries_exceeded(
    mock_format_final_report,
    mock_record_failed_attempt,
    mock_llm_judge,
    mock_python_verifier,
    mock_generate_synthesis,
    mock_fetch_papers,
):
    test_graph = create_workflow()
    """Testuje przejście, w którym osiagamy limit 3 nieudanych prób i graf wymusza wygenerowanie raportu końcowego."""
    mock_fetch_papers.side_effect = lambda state: {"papers_data": {"2601.05264": {}}}
    
    # Węzeł generowania zawsze podbija licznik do 3
    mock_generate_synthesis.side_effect = lambda state: {"analysis_markdown": "Błędna synteza", "retry_count": 3}
    mock_python_verifier.side_effect = lambda state: {"is_valid": False, "verification_errors": ["Niepoprawna cytacja"]}
    mock_llm_judge.side_effect = lambda state: {"is_valid": False, "judge_feedback": "Odrzucono"}
    
    mock_record_failed_attempt.side_effect = lambda state: {
        "audit_trail": [{"attempt": 3}],
        "retry_count": 3
    }
    mock_format_final_report.side_effect = lambda state: {"analysis_markdown": "Raport z zastrzeżeniami"}

    initial_state = {
        "arxiv_ids": ["2601.05264"],
        "retry_count": 2,  # Ustawiamy stan początkowy wskazujący na ostatnią szansę
        "audit_trail": []
    }

    final_state = await test_graph.ainvoke(initial_state)

    assert final_state["analysis_markdown"] == "Raport z zastrzeżeniami"
    mock_record_failed_attempt.assert_awaited_once()
    mock_format_final_report.assert_awaited_once()