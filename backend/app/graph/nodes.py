# /backend/app/graph/nodes.py
import asyncio
import datetime
import json
import logging
import re
from typing import Any, Dict, List

from aiolimiter import AsyncLimiter
import google.api_core.exceptions
from langchain_google_genai import ChatGoogleGenerativeAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.graph.state import AttemptRecord, JudgeEvaluation, MultiPaperState
from app.services.arxiv_service import ArxivService
from app.services.citation_service import CitationVerifier
from app.services.pdf_service import PDFService, clean_arxiv_id
from app.models.schemas import QueryExpansionResponse

logger = logging.getLogger("uvicorn.error")

# --- LIMITERY I RATE LIMITING ---

LIMITERS: Dict[str, AsyncLimiter] = {}
for model_name, limits in settings.MODEL_LIMITS.items():
    safe_rpm = max(1, limits.get("rpm", 5) - 1)
    LIMITERS[model_name] = AsyncLimiter(max_rate=safe_rpm, time_period=60)

RPD_TRACKER: Dict[str, Dict[str, Any]] = {}


def check_and_increment_rpd(model_name: str) -> bool:
    today = str(datetime.date.today())
    limits = settings.MODEL_LIMITS.get(model_name, {"rpd": 20})
    max_rpd = limits.get("rpd", 20)

    if model_name not in RPD_TRACKER or RPD_TRACKER[model_name]["date"] != today:
        RPD_TRACKER[model_name] = {"date": today, "count": 0}

    if RPD_TRACKER[model_name]["count"] >= max_rpd:
        logger.error(f"🛑 [RPD LIMIT] Model {model_name} osiągnął dzisiejszy limit {max_rpd} zapytań!")
        return False

    RPD_TRACKER[model_name]["count"] += 1
    logger.info(f"📊 [USAGE] {model_name} RPD: {RPD_TRACKER[model_name]['count']}/{max_rpd}")
    return True


@retry(
    wait=wait_exponential(min=5, max=120),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((
        google.api_core.exceptions.ResourceExhausted,
        google.api_core.exceptions.TooManyRequests
    )),
    before_sleep=lambda retry_state: logger.warning(
        f"⏳ [RATE LIMIT 429] Przekroczono limit API. Ponowienie próby #{retry_state.attempt_number}..."
    )
)
async def safe_llm_invoke(model_name: str, model_or_structured, prompt: Any):
    if not check_and_increment_rpd(model_name):
        raise RuntimeError(f"Osiągnięto dzienny limit zapytań (RPD) dla modelu: {model_name}")

    limiter = LIMITERS.get(model_name, AsyncLimiter(max_rate=3, time_period=60))

    async with limiter:
        logger.info(f"⏳ [SAFE INVOKE] Wywoływanie modelu '{model_name}'...")
        return await model_or_structured.ainvoke(prompt)


# --- POMOCNICZE FUNKCJE HELPEROWE ---

def get_model_for_mode(mode_key: str, temperature: float = 0.1) -> tuple[ChatGoogleGenerativeAI, str]:
    mode_config = settings.SPEED_MODES.get(mode_key, settings.SPEED_MODES.get("fast"))
    model_name = mode_config.get("model_name", settings.MAP_MODEL)
    service_tier = mode_config.get("service_tier", "flex")

    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=temperature,
        model_kwargs={"service_tier": service_tier}
    )
    return llm, model_name


import json
import re
from typing import List

async def expand_keywords_with_llm(user_instruction: str, mode_key: str = "fast") -> List[str]:
    prompt = f"""
Given the following research query, extract key concepts and generate 3-5 relevant scientific synonyms, technical acronyms, or related terms used in arXiv papers.

Query: "{user_instruction}"
"""
    try:
        llm, model_name = get_model_for_mode(mode_key, temperature=0.0)
        structured_llm = llm.with_structured_output(QueryExpansionResponse)
        result = await structured_llm.ainvoke(prompt)
        
        if result and result.keywords:
            logger.info(f"🧠 [QUERY EXPANSION] Wygenerowane synonimy/klucze: {result.keywords}")
            return list(set(result.keywords))

    except Exception as e:
        logger.warning(f"⚠️ [QUERY EXPANSION] Błąd generowania synonimów ({e}), używam oryginalnego zapytania.")

    # FALLBACK: Wracamy całe, nienaruszone zapytanie zamiast rozbijać je na pojedyncze słowa
    return [user_instruction]


def build_smart_grounded_context(
    arxiv_id: str, 
    pages_data: List[Dict[str, Any]], 
    expanded_keywords: List[str],
    window_sentences: int = 3
) -> str:
    extracted_blocks = []
    
    if pages_data:
        first_page = pages_data[0]
        p_num = first_page.get("page", 1)
        p_text = first_page.get("text", "")[:3000]
        extracted_blocks.append(f"--- arXiv:{arxiv_id}, p. {p_num} (ABSTRACT & INTRO) ---\n{p_text}")

    safe_keywords = [re.escape(k) for k in expanded_keywords if len(k) > 2]
    if not safe_keywords:
        return PDFService.build_grounded_context(arxiv_id, pages_data)
        
    regex_pattern = re.compile(r'\b(' + '|'.join(safe_keywords) + r')\b', re.IGNORECASE)

    for page in pages_data:
        p_num = page.get("page", 1)
        if p_num == 1:
            continue
            
        text = page.get("text", "")
        if regex_pattern.search(text):
            sentences = re.split(r'(?<=[.!?]) +', text)
            matching_indices = [i for i, s in enumerate(sentences) if regex_pattern.search(s)]
            
            selected_indices = set()
            for idx in matching_indices:
                start = max(0, idx - window_sentences)
                end = min(len(sentences), idx + window_sentences + 1)
                selected_indices.update(range(start, end))
            
            snippet = " ".join([sentences[i] for i in sorted(selected_indices)])
            extracted_blocks.append(f"--- arXiv:{arxiv_id}, p. {p_num} ---\n... {snippet} ...")

    return "\n\n".join(extracted_blocks)


async def get_prepared_context(state: MultiPaperState) -> str:
    mode = state.get("mode", "fast").lower() if "mode" in state else "fast"
    mode_config = settings.SPEED_MODES.get(mode, settings.SPEED_MODES["fast"])
    context_mode = mode_config.get("context_mode", "smart_chunks")
    
    full_context_blocks = []

    if context_mode == "full_paper" or mode == "exact":
        logger.info("⚡ [CONTEXT MODE] Pełny tekst artykułów (full_paper/exact).")
        for aid, pages in state["papers_data"].items():
            paper_context = PDFService.build_grounded_context(aid, pages)
            full_context_blocks.append(f"=== START PAPER arXiv:{aid} ===\n{paper_context}\n=== END PAPER arXiv:{aid} ===")
    else:
        logger.info("🚀 [CONTEXT MODE] Inteligentne fragmenty (smart_chunks)...")
        keywords = state.get("expanded_keywords")
        if not keywords:
            keywords = [w.strip() for w in re.findall(r'\b\w+\b', state["user_instruction"]) if len(w) > 3]

        for aid, pages in state["papers_data"].items():
            paper_context = build_smart_grounded_context(aid, pages, keywords)
            full_context_blocks.append(f"=== START PAPER arXiv:{aid} ===\n{paper_context}\n=== END PAPER arXiv:{aid} ===")

    return "\n\n".join(full_context_blocks)


# --- SYSTEM PROMPTS ---

SYSTEM_MULTI_PAPER_PROMPT = """
You are an expert AI Research Assistant.
Your task is to analyze, synthesize, and answer questions based on the provided arXiv research paper(s).

CRITICAL CITATION RULES:
1. Every claim, number, architectural detail, or comparison MUST be explicitly cited using [arXiv:ID, p. X] format.
2. Example: "Transformer uses 8 attention heads [arXiv:1706.03762, p. 5]."
3. If information is missing from the source text, explicitly state "Not specified in source text".
4. Maintain a structured, professional, and academic tone.
"""

JUDGE_SYSTEM_PROMPT = """
You are a Groundedness & Citation Accuracy Judge. 
Carefully verify if the generated analysis/synthesis is semantically supported by the cited pages.
Identify any hallucinations, unsupported claims, or incorrect citations.
"""


# --- WĘZŁY GRAFU (NODES) ---

async def expand_query_node(state: MultiPaperState):
    logger.info("🧠 [0. QUERY EXPANSION] Generowanie synonimów naukowych...")
    user_mode = state.get("mode", "fast")
    keywords = await expand_keywords_with_llm(state["user_instruction"], mode_key=user_mode)
    return {"expanded_keywords": keywords}


async def fetch_papers_node(state: MultiPaperState):
    logger.info(f"📥 [1. FETCH] Pobieranie {len(state['arxiv_ids'])} artykuł(ów) z arXiv...")
    
    async def fetch_single_paper(raw_arxiv_id: str):
        clean_id = clean_arxiv_id(raw_arxiv_id)
        pdf_url = f"[https://arxiv.org/pdf/](https://arxiv.org/pdf/){clean_id}.pdf"
        
        pages_task = PDFService.extract_pages_from_url(pdf_url)
        meta_task = ArxivService.fetch_paper_metadata(clean_id)
        # return_exceptions=True chroni przed awarią całego gather, gdy jeden task rzuci wyjątek
        pages, meta = await asyncio.gather(pages_task, meta_task, return_exceptions=True)

        # Obsługa przypadków, gdy metadane lub strony zwróciły błąd/są puste
        if isinstance(pages, Exception) or not pages:
            pages = []
        if isinstance(meta, Exception) or not meta:
            meta = {"title": f"arXiv:{clean_id}", "authors": [], "published": ""}
        
        return clean_id, pages, meta

    results = await asyncio.gather(*[fetch_single_paper(aid) for aid in state["arxiv_ids"]])
    
    papers_data = {}
    papers_metadata = {}
    failed_ids = []

    for clean_id, pages, meta in results:
        if pages: 
            papers_data[clean_id] = pages
            papers_metadata[clean_id] = meta
            logger.info(f"✅ [1. FETCH] Pobrano arXiv:{clean_id} ('{meta.get('title')}') - {len(pages)} stron.")
        else:
            failed_ids.append(clean_id)
            logger.warning(f"⚠️ [1. FETCH] Nie udało się pobrać treści dla arXiv:{clean_id}.")

    # Gdy żaden artykuł nie mógł zostać pobrany — zatrzymujemy proces
    if not papers_data:
        raise HTTPException(
            status_code=400, 
            detail=f"Nie udało się pobrać żadnego z podanych artykułów: {', '.join(failed_ids)}"
        )

    # Przygotowanie informacji audit_trail
    audit_trail = list(state.get("audit_trail", []))
    if failed_ids:
        audit_trail.append(f"⚠️ Ostrzeżenie: Nie udało się pobrać artykułów: {', '.join(failed_ids)}. Analiza została przeprowadzona dla pozostałych dostępnych prac.")

    return {
        "papers_data": papers_data,
        "papers_metadata": papers_metadata,
        "audit_trail": state.get("audit_trail", [])
    }


async def generate_synthesis_node(state: MultiPaperState):
    current_attempt = state.get("retry_count", 0) + 1
    logger.info(f"🤖 [2. GENERATOR] Generowanie odpowiedzi (Próba #{current_attempt})")

    user_mode = state.get("mode", "fast")
    temp = 0.1 if current_attempt == 1 else 0.0
    llm, model_name = get_model_for_mode(user_mode, temperature=temp)

    combined_context = await get_prepared_context(state)

    error_feedback = ""
    if state.get("verification_errors"):
        formatted_errors = "\n- ".join(state["verification_errors"])
        error_feedback = f"""
CRITICAL CORRECTIONS REQUIRED FROM PREVIOUS ATTEMPT (Attempt #{current_attempt - 1}):
- {formatted_errors}

INSTRUCTIONS FOR CORRECTION:
1. Fix or remove ONLY the specific unsupported claims or page citations listed above.
2. DO NOT shorten or summarize the rest of the valid analysis. Maintain full depth and formatting.
"""
        logger.warning(f"⚠️ [2. GENERATOR] Instrukcje poprawek dla LLM:\n{formatted_errors}")

    prompt = f"""
{SYSTEM_MULTI_PAPER_PROMPT}

{error_feedback}

User Request:
{state['user_instruction']}

Source Paper(s) Content:
{combined_context}
"""
    response = await safe_llm_invoke(model_name, llm, prompt)
    markdown_content = response.content if isinstance(response.content, str) else str(response.content)

    return {
        "analysis_markdown": markdown_content,
        "retry_count": current_attempt
    }


async def python_verifier_node(state: MultiPaperState):
    logger.info("🔍 [3. PYTHON VERIFIER] Weryfikacja składni cytatów i granic stron...")
    
    result = CitationVerifier.extract_and_verify_citations(
        generated_text=state["analysis_markdown"],
        papers_data=state["papers_data"]
    )
    
    return {
        "is_valid": result["is_valid"],
        "verification_errors": result["errors"]
    }


async def llm_judge_node(state: MultiPaperState):
    if not state["is_valid"]:
        logger.info("⏭️ [4. LLM JUDGE] Pominięto (odrzucenie przez Python Verifiera).")
        return {}

    logger.info("⚖️ [4. LLM JUDGE] Ocena semantyczna (Structured Output)...")

    user_mode = state.get("mode", "fast")
    base_judge, model_name = get_model_for_mode(user_mode, temperature=0.0)
    structured_judge = base_judge.with_structured_output(JudgeEvaluation)

    combined_context = await get_prepared_context(state)

    judge_prompt = f"""
{JUDGE_SYSTEM_PROMPT}

GENERATED ANALYSIS TO VERIFY:
{state['analysis_markdown']}

SOURCE PAPERS TEXT:
{combined_context}
"""

    try:
        eval_result: JudgeEvaluation = await safe_llm_invoke(model_name, structured_judge, judge_prompt)
        
        if eval_result.is_grounded:
            logger.info("✅ [4. LLM JUDGE] Zgodność semantyczna zatwierdzona!")
            return {"is_valid": True, "judge_feedback": "Passed"}
        else:
            logger.warning(f"❌ [4. LLM JUDGE] Błędy merytoryczne: {eval_result.errors}")
            current_errors = list(state.get("verification_errors", []))
            current_errors.extend([f"SEMANTIC_ERROR: {e}" for e in eval_result.errors])
            return {
                "is_valid": False,
                "verification_errors": current_errors,
                "judge_feedback": "\n".join(eval_result.errors)
            }

    except Exception as e:
        logger.error(f"⚠️ [4. LLM JUDGE] Błąd krytyczny sędziego: {e}")
        return {"is_valid": state["is_valid"]}


async def record_failed_attempt_node(state: MultiPaperState):
    audit_trail = list(state.get("audit_trail", []))
    
    failed_record: AttemptRecord = {
        "attempt_number": state.get("retry_count", 1),
        "rejected_analysis": state.get("analysis_markdown", ""),
        "errors": list(state.get("verification_errors", [])),
        "judge_feedback": state.get("judge_feedback", "")
    }
    
    audit_trail.append(failed_record)
    logger.info(f"📝 [AUDIT TRAIL] Zapisano nieudaną próbę #{failed_record['attempt_number']}.")
    
    return {"audit_trail": audit_trail}


async def format_final_report_node(state: MultiPaperState):
    logger.info("📄 [REPORT FORMATTER] Budowanie raportu końcowego...")
    
    final_markdown = state["analysis_markdown"]
    metas = state.get("papers_metadata", {})
    
    if metas:
        references_section = "\n\n---\n## 📚 References & Analyzed Papers\n"
        for aid, meta in metas.items():
            authors_list = meta.get("authors", [])
            authors_formatted = f"{', '.join(authors_list[:3])} et al." if len(authors_list) > 3 else ", ".join(authors_list)
            
            references_section += f"- **[{aid}] {meta.get('title')}** ({meta.get('published', 'N/A')})\n"
            references_section += f"   *Authors:* {authors_formatted}\n"
            references_section += f"   *Links:* [Abstract]({meta.get('abs_url')}) | [PDF Document]({meta.get('pdf_url')})\n\n"
        
        final_markdown += references_section

    audit_trail = state.get("audit_trail", [])
    if audit_trail:
        supplementary_note = "\n---\n## 📋 Supplementary Note: Audit Trail & Self-Correction Log\n"
        supplementary_note += "> *Ten raport został przetworzony przez automatyczny system weryfikacji cytowań i ugruntowania (Grounding). Poniżej znajduje się rejestr wniosków, które zostały skorygowane lub usunięte z powodu braku pokrycia w tekście źródłowym.*\n\n"

        for record in audit_trail:
            supplementary_note += f"### ⚠️ Odrzucona Próba #{record['attempt_number']}\n"
            supplementary_note += "**Wykryte niezgodności / błędne cytaty:**\n"
            for err in record["errors"]:
                supplementary_note += f"- `{err}`\n"
            
            if record.get("judge_feedback") and record["judge_feedback"] != "Passed":
                supplementary_note += f"**Uwagi Sędziego Semantycznego:** {record['judge_feedback']}\n"
            
            supplementary_note += "\n"

        final_markdown += supplementary_note

    return {"analysis_markdown": final_markdown}


# --- STRUKTURA STEROWANIA / DECISION LOGIC ---

def decide_next_step(state: MultiPaperState) -> str:
    if state["is_valid"]:
        logger.info("➡️ [DECYZJA] Weryfikacja udana. Przejście do formatowania raportu.")
        return "format_report"
    
    if state["retry_count"] >= 3:
        logger.error("🛑 [DECYZJA] Osiągnięto limit 3 prób. Przejście do rejestracji i formatowania.")
        return "record_and_format"
        
    logger.warning(f"🔄 [DECYZJA] Ponowne generowanie. (Próba {state['retry_count']}/3)")
    return "record_and_retry"