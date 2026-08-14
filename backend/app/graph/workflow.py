import asyncio
import logging
import re
import json
from typing import List, Dict, Any
from langgraph.graph import StateGraph, START, END
from app.graph.state import MultiPaperState, AttemptRecord, JudgeEvaluation
from app.services.pdf_service import PDFService
from app.services.arxiv_service import ArxivService
from app.services.citation_service import CitationVerifier
from langchain_google_genai import ChatGoogleGenerativeAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import google.api_core.exceptions
from app.services.pdf_service import PDFService, clean_arxiv_id

# Logger bezpośrednio wpięty w konsolę Uvicorna
logger = logging.getLogger("uvicorn.error")

# --- RATE LIMITER & RETRY LOGIC ---
LLM_SEMAPHORE = asyncio.Semaphore(2)
LAST_CALL_TIMESTAMP = 0.0
RPM_DELAY_SECONDS = 2.0

async def apply_rpm_rate_limit():
    global LAST_CALL_TIMESTAMP
    async with LLM_SEMAPHORE:
        now = asyncio.get_event_loop().time()
        elapsed = now - LAST_CALL_TIMESTAMP
        if elapsed < RPM_DELAY_SECONDS:
            await asyncio.sleep(RPM_DELAY_SECONDS - elapsed)
        LAST_CALL_TIMESTAMP = asyncio.get_event_loop().time()

@retry(
    wait=wait_exponential(min=4, max=60),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((
        google.api_core.exceptions.ResourceExhausted,
        google.api_core.exceptions.TooManyRequests
    )),
    before_sleep=lambda retry_state: logger.warning(
        f"⏳ [RATE LIMIT 429] Przekroczono limit. Ponowienie próby #{retry_state.attempt_number}..."
    )
)
async def safe_llm_invoke(model_or_structured, prompt):
    await apply_rpm_rate_limit()
    return await model_or_structured.ainvoke(prompt)


# --- MODELS (GEMINI 2.5 FLASH) ---
llm_generator = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.1,
    model_kwargs={"service_tier": "flex"}
)

base_judge = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.0,
    model_kwargs={"service_tier": "flex"}
)
structured_judge = base_judge.with_structured_output(JudgeEvaluation)


# --- HELPER FUNCTIONS FOR SMART CONTEXT & SYNONYMS ---

async def expand_keywords_with_llm(user_instruction: str) -> List[str]:
    """Generuje listę pojęć, synonimów i wariantów naukowych na podstawie zapytania użytkownika."""
    prompt = f"""
Given the following research query, extract key concepts and generate 5-10 relevant scientific synonyms, technical acronyms, or related terms used in arXiv papers.

Query: "{user_instruction}"

Return ONLY a valid JSON array of strings. Example: ["transformer", "attention mechanism", "self-attention", "VRAM", "parameters"]
"""
    try:
        response = await safe_llm_invoke(llm_generator, prompt)
        text = response.content if isinstance(response.content, str) else str(response.content)
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].strip()
        
        keywords = json.loads(text)
        if isinstance(keywords, list):
            logger.info(f"🧠 [QUERY EXPANSION] Wygenerowane synonimy/klucze: {keywords}")
            return list(set(keywords))
    except Exception as e:
        logger.warning(f"⚠️ [QUERY EXPANSION] Błąd generowania synonimów ({e}), używam słów podstawowych.")
    
    # Fallback - słowa z zapytania o długości > 3
    return [w.strip() for w in re.findall(r'\b\w+\b', user_instruction) if len(w) > 3]


def build_smart_grounded_context(
    arxiv_id: str, 
    pages_data: List[Dict[str, Any]], 
    expanded_keywords: List[str],
    window_sentences: int = 3
) -> str:
    """
    Skanuje strony PDF i wyciąga okna zdań zawierające słowa kluczowe LUB synonimy.
    Zachowuje dokładne nagłówki [arXiv:ID, p. X] dla weryfikacji cytatów!
    """
    extracted_blocks = []
    
    # 1. Zawsze dołączamy Stronę 1 (Abstrakt + Wstęp)
    if pages_data:
        first_page = pages_data[0]
        p_num = first_page.get("page", 1)
        p_text = first_page.get("text", "")[:3000]
        extracted_blocks.append(f"--- arXiv:{arxiv_id}, p. {p_num} (ABSTRACT & INTRO) ---\n{p_text}")

    # Regex do wyszukiwania słów kluczowych i synonimów
    safe_keywords = [re.escape(k) for k in expanded_keywords if len(k) > 2]
    if not safe_keywords:
        return PDFService.build_grounded_context(arxiv_id, pages_data)
        
    regex_pattern = re.compile(r'\b(' + '|'.join(safe_keywords) + r')\b', re.IGNORECASE)

    for page in pages_data:
        p_num = page.get("page", 1)
        if p_num == 1:
            continue  # Pierwsza strona już dodana
            
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
    """Przygotowuje kontekst w zależności od wybranego trybu: 'fast' lub 'exact'."""
    mode = state.get("mode", "fast").lower()
    full_context_blocks = []

    if mode == "exact":
        logger.info("⚡ [CONTEXT MODE] Tryb DOKŁADNY (Exact) - Przekazywanie pełnego tekstu artykułów.")
        for aid, pages in state["papers_data"].items():
            paper_context = PDFService.build_grounded_context(aid, pages)
            full_context_blocks.append(f"=== START PAPER arXiv:{aid} ===\n{paper_context}\n=== END PAPER arXiv:{aid} ===")
    else:
        logger.info("🚀 [CONTEXT MODE] Tryb SZYBKI (Fast) - Ekstrakcja inteligentnych fragmentów z użyciem gotowych synonimów...")
        keywords = state.get("expanded_keywords")
        if not keywords:
            keywords = [w.strip() for w in re.findall(r'\b\w+\b', state["user_instruction"]) if len(w) > 3]

        for aid, pages in state["papers_data"].items():
            paper_context = build_smart_grounded_context(aid, pages, keywords)
            full_context_blocks.append(f"=== START PAPER arXiv:{aid} ===\n{paper_context}\n=== END PAPER arXiv:{aid} ===")

    return "\n\n".join(full_context_blocks)


# --- PROMPTS ---

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


# --- NODES ---

async def expand_query_node(state: MultiPaperState):
    """Pierwszy krok grafu: Generuje synonimy/klucze raz dla całego cyklu wykonania."""
    logger.info("🧠 [0. QUERY EXPANSION] Generowanie synonimów naukowych dla całego przepływu...")
    keywords = await expand_keywords_with_llm(state["user_instruction"])
    return {"expanded_keywords": keywords}


async def fetch_papers_node(state: MultiPaperState):
    logger.info(f"📥 [1. FETCH] Pobieranie {len(state['arxiv_ids'])} artykuł(ów) oraz metadanych z arXiv...")
    
    async def fetch_single_paper(raw_arxiv_id: str):
        # Wyciągamy czysty ID, np. '1706.03762'
        clean_id = clean_arxiv_id(raw_arxiv_id)
        pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"
        
        pages_task = PDFService.extract_pages_from_url(pdf_url)
        meta_task = ArxivService.fetch_paper_metadata(clean_id)
        pages, meta = await asyncio.gather(pages_task, meta_task)
        
        return clean_id, pages, meta

    results = await asyncio.gather(*[fetch_single_paper(aid) for aid in state["arxiv_ids"]])
    
    papers_data = {}
    papers_metadata = {}
    for clean_id, pages, meta in results:
        papers_data[clean_id] = pages
        papers_metadata[clean_id] = meta
        logger.info(f"✅ [1. FETCH] Pobrano arXiv:{clean_id} ('{meta.get('title')}') - {len(pages)} stron.")

    return {
        "papers_data": papers_data,
        "papers_metadata": papers_metadata,
        "audit_trail": state.get("audit_trail", [])
    }


async def generate_synthesis_node(state: MultiPaperState):
    current_attempt = state.get("retry_count", 0) + 1
    logger.info(f"🤖 [2. GENERATOR] Generowanie odpowiedzi (Próba #{current_attempt})")

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
        logger.warning(f"⚠️ [2. GENERATOR] Przekazuję instrukcje poprawek do LLM:\n{formatted_errors}")

    prompt = f"""
{SYSTEM_MULTI_PAPER_PROMPT}

{error_feedback}

User Request:
{state['user_instruction']}

Source Paper(s) Content:
{combined_context}
"""
    model = llm_generator if current_attempt == 1 else llm_generator.copy(update={"temperature": 0.0})
    response = await safe_llm_invoke(model, prompt)
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

    logger.info("⚖️ [4. LLM JUDGE] Uruchamianie oceny semantycznej (Structured Output)...")

    combined_context = await get_prepared_context(state)

    judge_prompt = f"""
{JUDGE_SYSTEM_PROMPT}

GENERATED ANALYSIS TO VERIFY:
{state['analysis_markdown']}

SOURCE PAPERS TEXT:
{combined_context}
"""

    try:
        eval_result: JudgeEvaluation = await safe_llm_invoke(structured_judge, judge_prompt)
        
        if eval_result.is_grounded:
            logger.info("✅ [4. LLM JUDGE] Sędzia zatwierdził zgodność semantyczną!")
            return {"is_valid": True, "judge_feedback": "Passed"}
        else:
            logger.warning(f"❌ [4. LLM JUDGE] Sędzia wykrył błędy merytoryczne: {eval_result.errors}")
            current_errors = list(state.get("verification_errors", []))
            current_errors.extend([f"SEMANTIC_ERROR: {e}" for e in eval_result.errors])
            return {
                "is_valid": False,
                "verification_errors": current_errors,
                "judge_feedback": "\n".join(eval_result.errors)
            }

    except Exception as e:
        logger.error(f"⚠️ [4. LLM JUDGE] Błąd krytyczny podczas wywołania sędziego: {e}")
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
    logger.info(f"📝 [AUDIT TRAIL] Zapisano nieudaną próbę #{failed_record['attempt_number']} do historii.")
    
    return {"audit_trail": audit_trail}


async def format_final_report_node(state: MultiPaperState):
    logger.info("📄 [REPORT FORMATTER] Budowanie końcowego raportu (References + Audit Trail)...")
    
    final_markdown = state["analysis_markdown"]
    metas = state.get("papers_metadata", {})
    
    # 1. Dołączanie sekcji References
    if metas:
        references_section = "\n\n---\n## 📚 References & Analyzed Papers\n"
        for aid, meta in metas.items():
            authors_list = meta.get("authors", [])
            authors_formatted = f"{', '.join(authors_list[:3])} et al." if len(authors_list) > 3 else ", ".join(authors_list)
            
            references_section += f"- **[{aid}] {meta.get('title')}** ({meta.get('published', 'N/A')})\n"
            references_section += f"  *Authors:* {authors_formatted}\n"
            references_section += f"  *Links:* [Abstract]({meta.get('abs_url')}) | [PDF Document]({meta.get('pdf_url')})\n\n"
        
        final_markdown += references_section

    # 2. Dołączanie sekcji Audit Trail (jeśli wystąpiły odrzucone próby)
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


# --- ROUTER ---

def decide_next_step(state: MultiPaperState) -> str:
    if state["is_valid"]:
        logger.info("➡️ [DECYZJA] Weryfikacja udana. Przejście do formatowania raportu.")
        return "format_report"
    
    if state["retry_count"] >= 3:
        logger.error("🛑 [DECYZJA] Osiągnięto limit 3 prób. Przejście do formatowania z tym co mamy.")
        return "record_and_format"
        
    logger.warning(f"🔄 [DECYZJA] Rejestracja błędu i ponowne generowanie. (Próba {state['retry_count']}/3)")
    return "record_and_retry"


# --- BUILD GRAPH ---

builder = StateGraph(MultiPaperState)

builder.add_node("expand_query", expand_query_node)
builder.add_node("fetch_papers", fetch_papers_node)
builder.add_node("generate_synthesis", generate_synthesis_node)
builder.add_node("python_verifier", python_verifier_node)
builder.add_node("llm_judge", llm_judge_node)
builder.add_node("record_failed_attempt", record_failed_attempt_node)
builder.add_node("format_final_report", format_final_report_node)

builder.add_edge(START, "expand_query")
builder.add_edge("expand_query", "fetch_papers")
builder.add_edge("fetch_papers", "generate_synthesis")
builder.add_edge("generate_synthesis", "python_verifier")
builder.add_edge("python_verifier", "llm_judge")

builder.add_conditional_edges(
    "llm_judge",
    decide_next_step,
    {
        "record_and_retry": "record_failed_attempt",
        "format_report": "format_final_report",
        "record_and_format": "record_failed_attempt"
    }
)

builder.add_edge("record_failed_attempt", "generate_synthesis")
builder.add_edge("format_final_report", END)

multi_paper_graph = builder.compile()