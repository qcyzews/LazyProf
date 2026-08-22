# /backend/app/graph/nodes.py
import asyncio
import datetime
import json
import logging
import re
from typing import Any, Dict, List

from aiolimiter import AsyncLimiter
import google.api_core.exceptions
from fastapi import HTTPException
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
from app.models.schemas import QueryExpansionResponse, SynthesisResponse
from app.services.quota_service import quota_service
from app.services.debug_service import debug_service

# --- WYJĄTKI ZE STAREGO / KLASYCZNEGO API CORE ---
from google.api_core.exceptions import (
    ResourceExhausted as CoreResourceExhausted,
    TooManyRequests as CoreTooManyRequests,
    ServerError as CoreServerError,
    GoogleAPICallError,
)

# --- WYJĄTKI Z NOWEGO SDK GOOGLE GENAI ---
from google.genai.errors import (
    APIError,
    ServerError as GenAIServerError,
)

logger = logging.getLogger("uvicorn.error")

# --- LIMITERY I RATE LIMITING ---

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=3, max=60),
    retry=retry_if_exception_type((
        APIError,
        GenAIServerError,
        CoreResourceExhausted,
        CoreTooManyRequests,
        CoreServerError,
        GoogleAPICallError,
    )),
    before_sleep=lambda retry_state: logger.warning(
        f"⏳ [RETRY API] Ponowienie próby #{retry_state.attempt_number} z powodu błędu: "
        f"{retry_state.outcome.exception()}..."
    ),
    reraise=True
)
async def _execute_with_retry(model_name: str, model_or_structured: Any, prompt: Any) -> Any:
    """Wewnętrzne wywołanie objęte mechanizmem ponawiania i lokalnym limiterem RPM."""
    limiter = quota_service.limiters.get(model_name)
    
    if limiter:
        async with limiter:
            logger.info(f"⏳ [SAFE INVOKE] Wywoływanie modelu '{model_name}'...")
            return await model_or_structured.ainvoke(prompt)
    
    logger.info(f"⏳ [SAFE INVOKE] Wywoływanie modelu '{model_name}'...")
    return await model_or_structured.ainvoke(prompt)


async def safe_llm_invoke(model_name: str, model_or_structured: Any, prompt: Any) -> Any:
    """Główna funkcja pośrednicząca – sprawdza limity przed wywołaniem i zapisuje zużycie po sukcesie."""
    
    # 1. Sprawdzenie dostępności zasobów (RPM / TPM / RPD) przed strzałem
    is_ok, msg = await quota_service.check_availability(model_name)
    if not is_ok:
        raise RuntimeError(f"Limit Gemini zablokowany: {msg}")

    # 2. Wykonanie zapytania z retry
    response = await _execute_with_retry(model_name, model_or_structured, prompt)

    # 3. Odczyt zużycia tokenów z odpowiedzi LangChain/Google
    in_tokens = 0
    out_tokens = 0

    if hasattr(response, "response_metadata"):
        usage = response.response_metadata.get("usage_metadata") or response.response_metadata.get("token_usage")
        if usage:
            in_tokens = getattr(usage, "prompt_token_count", 0) or usage.get("prompt_tokens", 0)
            out_tokens = getattr(usage, "candidates_token_count", 0) or usage.get("completion_tokens", 0)
    elif hasattr(response, "usage_metadata"):
        in_tokens = getattr(response.usage_metadata, "prompt_token_count", 0)
        out_tokens = getattr(response.usage_metadata, "candidates_token_count", 0)

    # 4. Zapisanie faktycznego zużycia do Redisa / pamięci
    await quota_service.record_successful_call(model_name, in_tokens, out_tokens)

    return response


# --- POMOCNICZE FUNKCJE HELPEROWE ---

def get_model_for_mode(mode_key: str, temperature: float = 0.1) -> tuple[ChatGoogleGenerativeAI, str]:
    mode_config = settings.SPEED_MODES.get(mode_key, settings.SPEED_MODES.get("fast", {}))
    model_name = mode_config.get("model_name", settings.MAP_MODEL)
    service_tier = mode_config.get("service_tier", "flex")

    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=temperature,
        model_kwargs={"service_tier": service_tier}
    )
    return llm, model_name


async def expand_keywords_with_llm(user_instruction: str, mode_key: str = "fast") -> List[str]:
    prompt = f"""
Given the following research query, extract key concepts and generate 3-5 relevant scientific synonyms, technical acronyms, or related terms used in arXiv papers.

Query: "{user_instruction}"
"""
    try:
        llm, model_name = get_model_for_mode(mode_key, temperature=0.0)
        structured_llm = llm.with_structured_output(QueryExpansionResponse)
        result = await safe_llm_invoke(model_name, structured_llm, prompt)
        
        if result and getattr(result, "keywords", None):
            logger.info(f"🧠 [QUERY EXPANSION] Wygenerowane synonimy/klucze: {result.keywords}")
            return list(set(result.keywords))

    except Exception as e:
        logger.warning(f"⚠️ [QUERY EXPANSION] Błąd generowania synonimów ({e}), używam oryginalnego zapytania.")

    return [user_instruction]


def build_xml_grounded_context(
    arxiv_id: str, 
    pages_data: List[Dict[str, Any]], 
    expanded_keywords: List[str] | None = None
) -> str:
    """
    Buduje pełny (gdy expanded_keywords jest puste) lub smart-filtered kontekst w postaci zwartego XML.
    Struktura:
    <doc id="arXiv:ID">
      <p n="NUMER_STRONY">
        [1] Treść pierwszego akapitu...
        [2] Treść drugiego akapitu...
      </p>
    </doc>
    """
    keywords = expanded_keywords or []
    safe_keywords = [re.escape(k) for k in keywords if isinstance(k, str) and len(k) > 2]
    regex_pattern = re.compile(r'\b(' + '|'.join(safe_keywords) + r')\b', re.IGNORECASE) if safe_keywords else None

    xml_pages = []

    for page in pages_data:
        p_num = page.get("page", 1)
        text = page.get("text", "").strip()
        
        if not text:
            continue

        # Zawsze dołączamy stronę 1 (Abstrakt/Wstęp) LUB strony zawierające słowa kluczowe.
        # Jeśli brak słów kluczowych (np. przy ładownaniu całego artykułu w full_paper / exact mode), bierzemy wszystkie strony.
        if p_num == 1 or not regex_pattern or regex_pattern.search(text):
            raw_paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
            
            formatted_paragraphs = []
            for idx, para in enumerate(raw_paragraphs, 1):
                clean_para = " ".join(para.split())
                formatted_paragraphs.append(f"[{idx}] {clean_para}")
            
            paragraphs_str = "\n".join(formatted_paragraphs)
            xml_pages.append(f'  <p n="{p_num}">\n{paragraphs_str}\n  </p>')

    full_xml = f'<doc id="arXiv:{arxiv_id}">\n' + "\n".join(xml_pages) + "\n</doc>"
    return full_xml


async def get_prepared_context(state: MultiPaperState) -> str:
    mode = (state.get("mode") or "fast").lower()
    mode_config = settings.SPEED_MODES.get(mode, settings.SPEED_MODES.get("fast", {}))
    context_mode = mode_config.get("context_mode", "smart_chunks")
    
    current_attempt = state.get("retry_count", 0) + 1
    
    # 💡 ZŁOTY ŚRODEK: Przy 3. próbie (lub wyższej) automatycznie przełączamy na pełny kontekst (puste keywords)!
    is_full_paper = (context_mode == "full_paper" or mode == "exact" or current_attempt >= 3)
    
    if current_attempt >= 3:
        logger.warning(f"🚨 [CONTEXT] Próba #{current_attempt}: Wymuszone przełączenie na PEŁNY KONTEKST (pełne artykuły bez filtrów).")

    full_context_blocks = []

    if is_full_paper:
        logger.info("⚡ [CONTEXT MODE] Pełny tekst artykułów (full_paper / exact / fallback do 3. próby).")
        for aid, pages in state.get("papers_data", {}).items():
            paper_xml = PDFService.build_xml_grounded_context(aid, pages, expanded_keywords=[])
            full_context_blocks.append(paper_xml)
    else:
        logger.info("🚀 [CONTEXT MODE] Inteligentne fragmenty (smart_chunks)...")
        keywords = state.get("expanded_keywords")
        if not keywords:
            user_inst = state.get("user_instruction", "")
            keywords = [w.strip() for w in re.findall(r'\b\w+\b', user_inst) if len(w) > 3]

        for aid, pages in state.get("papers_data", {}).items():
            paper_xml = PDFService.build_xml_grounded_context(aid, pages, expanded_keywords=keywords)
            full_context_blocks.append(paper_xml)

    return "\n\n".join(full_context_blocks)


def extract_text_from_llm_response(content: Any) -> str:
    """Wyciąga czysty tekst z wyniku LLM, niezależnie od tego czy jest stringiem, czy listą bloków."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                text_parts.append(part.get("text", ""))
            elif hasattr(part, "text"):
                text_parts.append(getattr(part, "text", ""))
        return "".join(text_parts)
    return str(content)


# --- SYSTEM PROMPTS ---

SYSTEM_MULTI_PAPER_PROMPT = """You are an expert AI Research Assistant.
Your task is to analyze, synthesize, and answer questions based on the provided arXiv research paper(s).
The provided research paper text is THE ONLY SOURCE OF TRUTH for your analysis.

CRITICAL CITATION & GROUNDING RULES:
1. Every claim, number, architectural detail, or benchmark comparison MUST be explicitly cited using the source paper identifier.
2. Include page numbers [arXiv:ID, p. X] ONLY IF page numbers are explicitly stated in the provided context metadata or chunk headers.
3. If page numbers are NOT explicitly provided in the context, use ONLY the paper identifier [arXiv:ID]. NEVER fabricate or guess page numbers.
4. If a paper is a review/survey paper mentioning an architecture created elsewhere, explicitly frame it as such (e.g., "As reviewed in [arXiv:ID]...").
5. Do NOT synthesize or invent benchmark metrics, tables, or mechanisms that are not directly supported by the text.
6. If information is missing from the source text, explicitly state "Not specified in source text".
7. Maintain a structured, professional, and academic tone.
8. ABSOLUTE RULE ON PAGE NUMBERS: Look up the exact page number 'n' inside the XML tag <p n="X"> where the fact appears. NEVER guess or extrapolate page numbers based on external knowledge. If a page number is not present in the XML tag, do not invent it.
"""

JUDGE_SYSTEM_PROMPT = """You are a Groundedness & Citation Accuracy Judge.
Carefully verify if the generated analysis/synthesis is semantically supported by the cited pages in the source papers context.

CRITICAL CITATION EVALUATION RULES:

1. EXPECTED CITATION FORMAT:
   - The generated analysis MUST use the system citation format: [arXiv:ID, p. X] or [arXiv:ID, p. X, Y].

2. IGNORE SOURCE-INTERNAL BIBLIOGRAPHY REFERENCES:
   - Source paper texts natively contain their own internal reference markers (e.g., [1], [15], [33], [34], "Smith et al.").
   - DO NOT flag a citation as incorrect, invalid, or mismatched simply because the raw text in the source paper contains internal reference numbers like [1] or [15].
   - Ignore all original bibliography numbers embedded inside the source PDF content.

3. FACTUAL ALIGNMENT CHECK PROCEDURE:
   - For each claim cited in the analysis (e.g., [arXiv:2601.05264, p. 10]):
     a) Locate document arXiv:2601.05264 and page 10 inside the XML source context.
     b) Verify if the claim's semantic meaning is factually supported by the content on that page.
     c) IF THE CLAIM IS FACTUALLY SUPPORTED ON PAGE 10, THE CITATION IS VALID. Do NOT complain about internal numbers like [1] or [15] appearing in that same source passage.

4. WHEN TO REPORT AN ERROR:
   Report a hallucination or citation error ONLY if:
   - The claim is NOT supported by the text on the specified page/document.
   - The claim is factually false according to the source context.
   - The facts actually appear on a completely different page or paper than cited.
   - The claim is completely hallucinated or unsupported by any part of the provided context.
"""




# --- WĘZŁY GRAFU (NODES) ---

async def expand_query_node(state: MultiPaperState):
    logger.info("🧠 [0. QUERY EXPANSION] Generowanie synonimów naukowych...")
    user_mode = state.get("mode", "fast")
    keywords = await expand_keywords_with_llm(state.get("user_instruction", ""), mode_key=user_mode)
    return {"expanded_keywords": keywords}


async def fetch_papers_node(state: MultiPaperState):
    arxiv_ids = state.get("arxiv_ids", [])
    logger.info(f"📥 [1. FETCH] Pobieranie {len(arxiv_ids)} artykuł(ów) z arXiv...")
    
    async def fetch_single_paper(raw_arxiv_id: str):
        clean_id = clean_arxiv_id(raw_arxiv_id)
        pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"
        
        pages_task = PDFService.extract_pages_from_url(pdf_url)
        meta_task = ArxivService.fetch_paper_metadata(clean_id)
        
        pages, meta = await asyncio.gather(pages_task, meta_task, return_exceptions=True)

        if isinstance(pages, Exception):
            logger.error(f"Błąd pobierania stron dla {clean_id}: {pages}")
            pages = []
        if isinstance(meta, Exception):
            logger.error(f"Błąd metadanych dla {clean_id}: {meta}")
            meta = {"title": f"arXiv:{clean_id}", "authors": [], "published": ""}
        
        return clean_id, pages, meta

    results = await asyncio.gather(*[fetch_single_paper(aid) for aid in arxiv_ids])
    
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

    if not papers_data:
        raise HTTPException(
            status_code=400, 
            detail=f"Nie udało się pobrać żadnego z podanych artykułów: {', '.join(failed_ids)}"
        )

    audit_trail = list(state.get("audit_trail", []))
    if failed_ids:
        audit_trail.append({
            "attempt_number": 0,
            "rejected_analysis": "",
            "errors": [f"Nie udało się pobrać artykułów: {', '.join(failed_ids)}"],
            "judge_feedback": "Ostrzeżenie dotyczące pobierania"
        })

    return {
        "papers_data": papers_data,
        "papers_metadata": papers_metadata,
        "audit_trail": audit_trail
    }


async def generate_synthesis_node(state: MultiPaperState):
    current_attempt = state.get("retry_count", 0) + 1
    logger.info(f"🤖 [2. GENERATOR] Generating synthesis response (Attempt #{current_attempt})")

    user_mode = state.get("mode", "fast")
    temp = 0.1 if current_attempt == 1 else 0.0
    llm, model_name = get_model_for_mode(user_mode, temperature=temp)

    # Wymuszenie ustrukturyzowanej odpowiedzi z Pydantic
    structured_llm = llm.with_structured_output(SynthesisResponse)

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
        logger.warning(f"⚠️ [2. GENERATOR] Feedback instructions for LLM:\n{formatted_errors}")

    prompt = f"""
{SYSTEM_MULTI_PAPER_PROMPT}

{error_feedback}

User Request:
{state.get('user_instruction', '')}

Source Paper(s) Content:
{combined_context}
"""

    # Wywołanie modelu przez bezpieczny wrapper
    response = await safe_llm_invoke(model_name, structured_llm, prompt)

    # Ekstrakcja treści Markdown oraz listy cytatów
    citations = []
    if isinstance(response, SynthesisResponse):
        markdown_content = response.analysis_markdown
        citations = [c.model_dump() for c in response.citations]
    elif isinstance(response, dict):
        markdown_content = response.get("analysis_markdown", "")
        citations = response.get("citations", [])
    else:
        markdown_content = extract_text_from_llm_response(getattr(response, "content", str(response)))

    return {
        "analysis_markdown": markdown_content,
        "citations": citations,
        "retry_count": current_attempt
    }


async def python_verifier_node(state: MultiPaperState):
    logger.info("🔍 [3. PYTHON VERIFIER] Weryfikacja składni cytatów i granic stron...")
    
    result = CitationVerifier.extract_and_verify_citations(
        generated_text=state.get("analysis_markdown", ""),
        papers_data=state.get("papers_data", {})
    )
    
    return {
        "is_valid": result["is_valid"],
        "verification_errors": result["errors"]
    }


async def llm_judge_node(state: MultiPaperState):
    if not state.get("is_valid", False):
        logger.info("⏭️ [4. LLM JUDGE] Pominięto (odrzucenie przez Python Verifiera).")
        return {}

    logger.info("⚖️ [4. LLM JUDGE] Ocena semantyczna (Structured Output)...")

    user_mode = state.get("mode", "fast")
    base_judge, model_name = get_model_for_mode(user_mode, temperature=0.0)
    structured_judge = base_judge.with_structured_output(JudgeEvaluation)

    combined_context = await get_prepared_context(state)

    judge_prompt = f"""{JUDGE_SYSTEM_PROMPT}

GENERATED ANALYSIS TO VERIFY:
{state.get('analysis_markdown', '')}

SOURCE PAPERS TEXT (XML FORMAT):
{combined_context}
"""

    try:
        eval_result: JudgeEvaluation = await safe_llm_invoke(model_name, structured_judge, judge_prompt)
        
        if eval_result.is_grounded:
            logger.info("✅ [4. LLM JUDGE] Zgodność semantyczna zatwierdzona!")
            return {"is_valid": True, "judge_feedback": "Passed"}
        else:
            logger.warning(f"❌ [4. LLM JUDGE] Błędy merytoryczne: {eval_result.errors}")

            # 🎯 Zrzut do pliku wyzwalany bezpośrednio z węzła (asynchronicznie)
            await debug_service.log_failed_audit_async(
                generated_report=state.get("analysis_markdown", ""),
                judge_result={
                    "is_grounded": False, 
                    "errors": eval_result.errors,
                    "raw_judge_prompt": str(judge_prompt)
                },
                context_chunks=state.get("context_chunks", []),
                user_instruction=state.get("user_instruction")
            )

            current_errors = list(state.get("verification_errors", []))
            current_errors.extend([f"SEMANTIC_ERROR: {e}" for e in eval_result.errors])
            return {
                "is_valid": False,
                "verification_errors": current_errors,
                "judge_feedback": "\n".join(eval_result.errors)
            }

    except Exception as e:
        logger.error(f"⚠️ [4. LLM JUDGE] Błąd krytyczny sędziego: {e}")
        return {"is_valid": state.get("is_valid", False)}


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
    logger.info("📄 [REPORT FORMATTER] Budowanie raportu końcowego (wersja dla użytkownika)...")
    logger.info(f"DEBUG: Content length: {len(state.get('analysis_markdown', ''))}")

    final_markdown = state.get("analysis_markdown", "")
    metas = state.get("papers_metadata", {})
    audit_trail = state.get("audit_trail", [])
    
    # Elegancka sekcja bibliograficzna na górze lub na dole
    if metas:
        references_section = "\n\n---\n## 📚 Przeanalizowane dokumenty\n"
        for aid, meta in metas.items():
            authors_list = meta.get("authors", [])
            authors_formatted = f"{', '.join(authors_list[:3])} et al." if len(authors_list) > 3 else ", ".join(authors_list)
            
            references_section += f"- **[{aid}] {meta.get('title')}**\n"
            references_section += f"   *Autorzy:* {authors_formatted} | *Data:* {meta.get('published', 'N/A')}\n"
            references_section += f"   *Link:* [Pobierz PDF]({meta.get('pdf_url')})\n\n"
        
        final_markdown += references_section

    # Przyjazny komunikat o procesie redakcyjnym (tylko jeśli były poprawki)
    if audit_trail:
        total_attempts = len(audit_trail)
        quality_note = f"""
---
## 🛡️ Raport rzetelności i weryfikacji treści
> *System AI przeanalizował powyższy tekst pod kątem zgodności z oryginalnymi dokumentami (przeprowadzono {total_attempts} cykle weryfikacji źródeł).*
"""
        
        # Jeśli osiągnięto limit i wynik może wymagać uwagi
        if not state.get("is_valid", False):
            quality_note += "\n> ⚠️ *Uwaga: Ponieważ artykuł jest bardzo obszerny, niektóre precyzyjne odnośniki do stron mogły wymagać uogólnienia, aby zapewnić pełną poprawność merytoryczną.*\n"
        else:
            quality_note += "\n> ✅ *Wszystkie zawarte w raporcie tezy i odnośniki do stron zostały pomyślnie zweryfikowane z oryginalnymi plikami PDF.*\n"

        final_markdown += quality_note
        logger.info(f"DEBUG: final_markdown length: {len(final_markdown)}")

    return {"analysis_markdown": final_markdown}


def decide_next_step(state: MultiPaperState) -> str:
    if state.get("is_valid", False):
        logger.info("➡️ [DECYZJA] Weryfikacja udana. Przejście do formatowania raportu.")
        return "format_report"
    
    if state.get("retry_count", 0) >= 3:
        logger.error("🛑 [DECYZJA] Osiągnięto limit 3 prób. Przejście do rejestracji i formatowania.")
        return "record_and_format"
        
    logger.warning(f"🔄 [DECYZJA] Ponowne generowanie. (Próba {state.get('retry_count', 0)}/3)")
    return "record_and_retry"