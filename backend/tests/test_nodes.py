import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.graph.nodes import (
    check_and_increment_rpd,
    expand_keywords_with_llm,
    build_smart_grounded_context,
    get_prepared_context,
    expand_query_node,
    fetch_papers_node,
    generate_synthesis_node,
    python_verifier_node,
    llm_judge_node,
    record_failed_attempt_node,
    format_final_report_node,
    decide_next_step,
)


# --- 1. TESTY LOGIKI STEROWANIA (Funkcje czyste) ---

def test_decide_next_step_success(mock_state):
    """Gdy analiza jest poprawna, przechodzimy do formatowania."""
    mock_state["is_valid"] = True
    assert decide_next_step(mock_state) == "format_report"


def test_decide_next_step_retry(mock_state):
    """Gdy analiza zawiera błędy i mamy zapas prób, ponawiamy."""
    mock_state["is_valid"] = False
    mock_state["retry_count"] = 1
    assert decide_next_step(mock_state) == "record_and_retry"


def test_decide_next_step_max_retries(mock_state):
    """Gdy osiagnięto limit 3 prób, rejestrujemy błąd i formatujemy raport."""
    mock_state["is_valid"] = False
    mock_state["retry_count"] = 3
    assert decide_next_step(mock_state) == "record_and_format"


# --- 2. TESTY WĘZŁÓW ASYNCHRONICZNYCH (Async Nodes) ---

@pytest.mark.asyncio
async def test_python_verifier_node_success(mock_state, mocker):
    """Test weryfikatora Python z za-mockowaną usługą CitationVerifier."""
    mocker.patch(
        "app.graph.nodes.CitationVerifier.extract_and_verify_citations",
        return_value={"is_valid": True, "errors": []}
    )

    result = await python_verifier_node(mock_state)

    assert result["is_valid"] is True
    assert result["verification_errors"] == []


@pytest.mark.asyncio
async def test_python_verifier_node_failure(mock_state, mocker):
    """Test wykrycia błędnego cytatu przez Python Verifier."""
    mocker.patch(
        "app.graph.nodes.CitationVerifier.extract_and_verify_citations",
        return_value={
            "is_valid": False, 
            "errors": ["Nieprawidłowy numer strony: [arXiv:1706.03762, p. 99] (max: 5)"]
        }
    )

    result = await python_verifier_node(mock_state)

    assert result["is_valid"] is False
    assert len(result["verification_errors"]) == 1


@pytest.mark.asyncio
async def test_record_failed_attempt_node(mock_state):
    """Test rejestrowania odrzuconej próby w Audit Trail."""
    mock_state["retry_count"] = 1
    mock_state["verification_errors"] = ["Błędna strona"]
    mock_state["judge_feedback"] = "Niezgodność merytoryczna"

    result = await record_failed_attempt_node(mock_state)

    assert "audit_trail" in result
    assert len(result["audit_trail"]) == 1
    assert result["audit_trail"][0]["attempt_number"] == 1
    assert result["audit_trail"][0]["errors"] == ["Błędna strona"]


@pytest.mark.asyncio
async def test_format_final_report_node(mock_state):
    """Test dodawania sekcji bibliografii i historii poprawek do raportu."""
    mock_state["audit_trail"] = [{
        "attempt_number": 1,
        "rejected_analysis": "Zła treść",
        "errors": ["Błąd cytowania"],
        "judge_feedback": "Zła strona"
    }]

    result = await format_final_report_node(mock_state)

    assert "analysis_markdown" in result
    # Sprawdzamy czy bibliografia oraz sekcja Audit Trail dołączyły do markdowna
    assert "References & Analyzed Papers" in result["analysis_markdown"]
    assert "Supplementary Note: Audit Trail" in result["analysis_markdown"]


@pytest.mark.asyncio
async def test_expand_query_node(mock_state, mocker):
    """Test wywołania expand_query_node z mockowaniem LLM."""
    mocker.patch(
        "app.graph.nodes.expand_keywords_with_llm",
        new_callable=AsyncMock,
        return_value=["transformer", "attention", "neural networks"]
    )

    result = await expand_query_node(mock_state)

    assert "expanded_keywords" in result
    assert "transformer" in result["expanded_keywords"]

def test_check_and_increment_rpd():
    assert check_and_increment_rpd("gemini-2.5-flash") is True

@pytest.mark.asyncio
@patch("app.graph.nodes.safe_llm_invoke", new_callable=AsyncMock)
async def test_expand_keywords_with_llm_json_parsing(mock_safe_invoke):
    mock_response = MagicMock()
    mock_response.content = '```json\n["transformer", "attention"]\n```'
    mock_safe_invoke.return_value = mock_response

    keywords = await expand_keywords_with_llm("Explain transformer attention")
    assert "transformer" in keywords

@pytest.mark.asyncio
@patch("app.graph.nodes.safe_llm_invoke", side_effect=Exception("LLM Fail"))
async def test_expand_keywords_with_llm_fallback(mock_safe_invoke):
    keywords = await expand_keywords_with_llm("Explain transformer attention mechanisms")
    assert len(keywords) > 0

def test_build_smart_grounded_context():
    pages_data = [
        {"page": 1, "text": "Abstract and introduction to deep learning."},
        {"page": 2, "text": "The transformer architecture uses multi-head attention."}
    ]
    context = build_smart_grounded_context("1706.03762", pages_data, ["transformer"])
    assert "arXiv:1706.03762" in context

@pytest.mark.asyncio
async def test_get_prepared_context_full_and_smart():
    state = {
        "mode": "exact",
        "papers_data": {"1706.03762": [{"page": 1, "text": "Full paper content"}]},
        "user_instruction": "test"
    }
    ctx_full = await get_prepared_context(state)
    assert "START PAPER arXiv:1706.03762" in ctx_full

@pytest.mark.asyncio
@patch("app.graph.nodes.safe_llm_invoke", new_callable=AsyncMock)
async def test_generate_synthesis_node(mock_invoke):
    mock_resp = MagicMock()
    mock_resp.content = "Generated synthesis content [arXiv:1706.03762, p. 1]."
    mock_invoke.return_value = mock_resp

    state = {
        "retry_count": 1,
        "mode": "fast",
        "user_instruction": "Compare",
        "papers_data": {"1706.03762": [{"page": 1, "text": "Content"}]},
        "verification_errors": ["Fix citation"]
    }
    res = await generate_synthesis_node(state)
    assert "Generated synthesis" in res["analysis_markdown"]

@pytest.mark.asyncio
@patch("app.graph.nodes.safe_llm_invoke", new_callable=AsyncMock)
async def test_llm_judge_node_passed(mock_invoke):
    eval_mock = MagicMock()
    eval_mock.is_grounded = True
    mock_invoke.return_value = eval_mock

    state = {
        "is_valid": True,
        "mode": "fast",
        "analysis_markdown": "Analysis text",
        "papers_data": {"1706.03762": []},
        "user_instruction": "Przeanalizuj podane artykuły"  # <--- DODAJDŹ TĘ LINIĘ
    }
    res = await llm_judge_node(state)
    assert res["is_valid"] is True

def test_decide_next_step():
    assert decide_next_step({"is_valid": True, "retry_count": 1}) == "format_report"
    assert decide_next_step({"is_valid": False, "retry_count": 3}) == "record_and_format"
    assert decide_next_step({"is_valid": False, "retry_count": 1}) == "record_and_retry"