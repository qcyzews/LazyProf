# /backend/tests/test_nodes.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from app.graph.nodes import (
    extract_text_from_llm_response,
    build_xml_grounded_context,
    decide_next_step,
    expand_query_node,
    fetch_papers_node,
    generate_synthesis_node,
    python_verifier_node,
    llm_judge_node,
    record_failed_attempt_node,
    format_final_report_node,
)
from app.models.schemas import SynthesisResponse
from app.graph.state import JudgeEvaluation


# --- TESTY FUNKCJI POMOCNICZYCH (HELPERS) ---

def test_extract_text_from_llm_response_string():
    content = "To jest testowy tekst."
    assert extract_text_from_llm_response(content) == "To jest testowy tekst."


def test_extract_text_from_llm_response_list():
    class DummyPart:
        def __init__(self, text):
            self.text = text

    content = [
        "Część 1 ",
        {"text": "Część 2 "},
        DummyPart("Część 3")
    ]
    assert extract_text_from_llm_response(content) == "Część 1 Część 2 Część 3"


def test_build_xml_grounded_context_basic():
    pages_data = [
        {"page": 1, "text": "Abstrakt artykułu.\n\nTo jest wstęp."},
        {"page": 2, "text": "Wyniki badania:\n\nModel osiągnął 95% accuracy."}
    ]
    xml = build_xml_grounded_context("2601.05264", pages_data, expanded_keywords=None)
    
    assert '<doc id="arXiv:2601.05264">' in xml
    assert '<p n="1">' in xml
    assert '[1] Abstrakt artykułu.' in xml
    assert '[2] To jest wstęp.' in xml
    assert '<p n="2">' in xml


def test_build_xml_grounded_context_filtered():
    pages_data = [
        {"page": 1, "text": "Wstęp o niczym."},
        {"page": 2, "text": "Ważny model o nazwie Transformer."},
        {"page": 3, "text": "Podsumowanie."}
    ]
    # Strona 1 zawsze wchodzi, strona 2 bo zawiera "Transformer", strona 3 pominięta
    xml = build_xml_grounded_context("2601.05264", pages_data, expanded_keywords=["Transformer"])
    
    assert '<p n="1">' in xml
    assert '<p n="2">' in xml
    assert '<p n="3">' not in xml


def test_decide_next_step():
    # 1. Sukces weryfikacji
    assert decide_next_step({"is_valid": True}) == "format_report"
    
    # 2. Przekroczony limit prób (>=3)
    assert decide_next_step({"is_valid": False, "retry_count": 3}) == "record_and_format"
    
    # 3. Kolejna próba ponowienia
    assert decide_next_step({"is_valid": False, "retry_count": 1}) == "record_and_retry"


# --- TESTY WĘZŁÓW GRAFU (NODES) ---

@pytest.mark.asyncio
@patch("app.graph.nodes.expand_keywords_with_llm", new_callable=AsyncMock)
async def test_expand_query_node(mock_expand):
    mock_expand.return_value = ["synonym1", "synonym2"]
    state = {"user_instruction": "test query", "mode": "fast"}
    
    result = await expand_query_node(state)
    
    assert result == {"expanded_keywords": ["synonym1", "synonym2"]}
    mock_expand.assert_awaited_once_with("test query", mode_key="fast")


@pytest.mark.asyncio
@patch("app.graph.nodes.PDFService.extract_pages_from_url", new_callable=AsyncMock)
@patch("app.graph.nodes.ArxivService.fetch_paper_metadata", new_callable=AsyncMock)
async def test_fetch_papers_node_success(mock_meta, mock_pdf):
    mock_pdf.return_value = [{"page": 1, "text": "Strona 1"}]
    mock_meta.return_value = {"title": "Test Paper", "authors": ["Jan Kowalski"], "published": "2026-01-01", "pdf_url": "url"}
    
    state = {"arxiv_ids": ["2601.05264"], "audit_trail": []}
    result = await fetch_papers_node(state)
    
    assert "2601.05264" in result["papers_data"]
    assert "2601.05264" in result["papers_metadata"]
    assert result["audit_trail"] == []


@pytest.mark.asyncio
@patch("app.graph.nodes.PDFService.extract_pages_from_url", new_callable=AsyncMock)
@patch("app.graph.nodes.ArxivService.fetch_paper_metadata", new_callable=AsyncMock)
async def test_fetch_papers_node_all_failed(mock_meta, mock_pdf):
    mock_pdf.return_value = [] # puste strony oznaczają błąd pobierania
    mock_meta.return_value = {}
    
    state = {"arxiv_ids": ["9999.99999"], "audit_trail": []}
    
    with pytest.raises(HTTPException) as exc_info:
        await fetch_papers_node(state)
    
    assert exc_info.value.status_code == 400
    assert "Nie udało się pobrać żadnego" in exc_info.value.detail


@pytest.mark.asyncio
@patch("app.graph.nodes.get_model_for_mode")
@patch("app.graph.nodes.safe_llm_invoke", new_callable=AsyncMock)
@patch("app.graph.nodes.get_prepared_context", new_callable=AsyncMock)
async def test_generate_synthesis_node(mock_context, mock_safe_invoke, mock_get_model):
    mock_context.return_value = "<doc>Context</doc>"
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_model.return_value = (mock_llm, "gemini-model")
    
    mock_response = SynthesisResponse(
        analysis_markdown="Wynik analizy tekstu.",
        citations=[
            {
                "arxiv_id": "2601.05264",
                "page": "1",  # Zmiana int -> str
                "claim_summary": "Podsumowanie twierdzenia",  # Dodanie wymaganego pola
            }
        ],
    )
    mock_safe_invoke.return_value = mock_response
    
    state = {
        "mode": "fast",
        "retry_count": 0,
        "user_instruction": "Przeanalizuj papier",
        "papers_data": {}
    }
    
    result = await generate_synthesis_node(state)
    
    assert result["analysis_markdown"] == "Wynik analizy tekstu."
    assert len(result["citations"]) == 1
    assert result["retry_count"] == 1


@pytest.mark.asyncio
@patch("app.graph.nodes.CitationVerifier.extract_and_verify_citations")
async def test_python_verifier_node(mock_verifier):
    mock_verifier.return_value = {"is_valid": True, "errors": []}
    
    state = {"analysis_markdown": "Test [arXiv:2601.05264, p. 1]", "papers_data": {}}
    result = await python_verifier_node(state)
    
    assert result["is_valid"] is True
    assert result["verification_errors"] == []


@pytest.mark.asyncio
@patch("app.graph.nodes.get_model_for_mode")
@patch("app.graph.nodes.safe_llm_invoke", new_callable=AsyncMock)
@patch("app.graph.nodes.get_prepared_context", new_callable=AsyncMock)
async def test_llm_judge_node_valid(mock_context, mock_safe_invoke, mock_get_model):
    mock_context.return_value = "<doc>Context</doc>"
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_get_model.return_value = (mock_llm, "model")
    
    mock_eval = JudgeEvaluation(is_grounded=True, errors=[])
    mock_safe_invoke.return_value = mock_eval
    
    state = {"is_valid": True, "analysis_markdown": "Test", "mode": "fast"}
    result = await llm_judge_node(state)
    
    assert result["is_valid"] is True
    assert result["judge_feedback"] == "Passed"


@pytest.mark.asyncio
@patch("app.graph.nodes.get_model_for_mode")
@patch("app.graph.nodes.safe_llm_invoke", new_callable=AsyncMock)
@patch("app.graph.nodes.get_prepared_context", new_callable=AsyncMock)
@patch("app.services.debug_service.debug_service.log_failed_audit_async", new_callable=AsyncMock)
async def test_llm_judge_node_invalid(mock_debug_log, mock_context, mock_safe_invoke, mock_get_model):
    mock_context.return_value = "<doc>Context</doc>"
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_get_model.return_value = (mock_llm, "model")
    
    mock_eval = JudgeEvaluation(is_grounded=False, errors=["Błąd halucynacji na stronie 2"])
    mock_safe_invoke.return_value = mock_eval
    
    state = {"is_valid": True, "analysis_markdown": "Test", "mode": "fast", "verification_errors": []}
    result = await llm_judge_node(state)
    
    assert result["is_valid"] is False
    assert len(result["verification_errors"]) == 1
    assert "SEMANTIC_ERROR" in result["verification_errors"][0]
    mock_debug_log.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_failed_attempt_node():
    state = {
        "retry_count": 2,
        "analysis_markdown": "Zła analiza",
        "verification_errors": ["Błąd 1"],
        "judge_feedback": "Odrzucone",
        "audit_trail": []
    }
    
    result = await record_failed_attempt_node(state)
    
    assert len(result["audit_trail"]) == 1
    assert result["audit_trail"][0]["attempt_number"] == 2
    assert result["audit_trail"][0]["rejected_analysis"] == "Zła analiza"


@pytest.mark.asyncio
async def test_format_final_report_node():
    state = {
        "analysis_markdown": "Główny tekst raportu.",
        "papers_metadata": {
            "2601.05264": {
                "title": "Badania nad AI",
                "authors": ["Jan Kowalski", "Anna Nowak"],
                "published": "2026-02-01",
                "pdf_url": "https://arxiv.org/pdf/2601.05264.pdf"
            }
        },
        "audit_trail": [{"attempt_number": 1}],
        "is_valid": True
    }
    
    result = await format_final_report_node(state)
    markdown = result["analysis_markdown"]
    
    assert "Główny tekst raportu." in markdown
    assert "Badania nad AI" in markdown
    assert "Jan Kowalski, Anna Nowak" in markdown
    assert "Raport rzetelności i weryfikacji treści" in markdown
    assert "Wszystkie zawarte w raporcie tezy" in markdown