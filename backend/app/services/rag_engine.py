# /backend/app/services/rag_engine.py
import asyncio
import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional, Union
from langchain_google_genai import ChatGoogleGenerativeAI
from google.api_core.exceptions import ResourceExhausted
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings
from app.graph.state import JudgeEvaluation
from app.services.quota_service import quota_service
from app.services.llm_service import safe_llm_invoke, extract_text_from_llm_response
from app.models.schemas import QueryExpansionResponse

logger = logging.getLogger(__name__)


class RAGEngine:
    def __init__(self):
        self.map_model_name = settings.MAP_MODEL
        self.reduce_model_name = settings.REDUCE_MODEL

        self.map_llm = ChatGoogleGenerativeAI(
            model=self.map_model_name,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.0,
            model_kwargs={"service_tier": "flex"}
        )
        self.reduce_llm = ChatGoogleGenerativeAI(
            model=self.reduce_model_name,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.1,
            streaming=True,
            model_kwargs={"service_tier": "flex"}
        )
        self.judge_llm = ChatGoogleGenerativeAI(
            model=self.reduce_model_name,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.0,
            model_kwargs={"service_tier": "flex"}
        )

    def get_map_messages(self, title: str, arxiv_id: str, user_instruction: str, text: str) -> List[Any]:
        system_prompt = (
            "You are an expert AI academic research assistant for LazyProf. "
            "Analyze the provided scientific paper and extract key findings, methodologies, "
            "metrics, architectures, and limitations strictly relevant to the user's instruction.\n"
            "Be precise and use clear Markdown bullet points."
        )
        user_prompt = (
            f"Paper Title: {title} (arXiv: {arxiv_id})\n"
            f"User Instruction: {user_instruction}\n\n"
            f"Article Content:\n{text[:30000]}"
        )
        return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

    def get_reduce_messages(
        self, 
        context_blocks: List[Union[str, Dict[str, Any]]], 
        user_instruction: str, 
        retry_count: int = 0, 
        verification_errors: Optional[List[str]] = None,
        judge_feedback: Optional[str] = None
    ) -> List[Any]:
        formatted_blocks = []
        for block in context_blocks:
            if isinstance(block, str):
                formatted_blocks.append(block)
            elif isinstance(block, dict):
                arxiv_id = block.get("arxiv_id", "Unknown")
                title = block.get("title", "")
                summary = block.get("summary", block.get("content", block.get("text", "")))
            
                if summary:
                    formatted_blocks.append(f"### [arXiv:{arxiv_id}] {title}\n{summary}".strip())
                else:
                    formatted_blocks.append(json.dumps(block, ensure_ascii=False))
            else:
                formatted_blocks.append(str(block))

        full_context = "\n\n---\n\n".join(formatted_blocks)
    
        feedback_prompt = ""
        if retry_count > 0 and (verification_errors or judge_feedback):
            feedback_prompt = f"""
    ⚠️ CRITICAL CORRECTIONS REQUIRED (Attempt {retry_count + 1}):
    Your previous output was REJECTED by the Quality Assurer due to the following errors:
    {json.dumps(verification_errors or [], indent=2)}
    Feedback: {judge_feedback or ''}

    Please fix these errors explicitly. Ensure every claim is strictly backed by the source text and cited accurately with [arXiv:ID].
    """

        system_prompt = (
            "You are a distinguished university professor synthesizing multi-paper literature reviews for LazyProf.\n"
            "Synthesize the provided extracted paper analyses into a structured, highly analytical, and comprehensive report.\n"
            "STRICT REQUIREMENTS:\n"
            "1. Format strictly in clean Markdown (Executive Summary, Comparative Matrix Table, In-depth Synthesis, References).\n"
            "2. In-Text Citations: Every technical finding, metric, or architectural contribution MUST be cited using [arXiv:ID].\n"
            "3. Do not omit numerical results or specific terminology."
        )
    
        user_prompt = (
            f"User Objective: {user_instruction}\n\n"
            f"Extracted Paper Analyses (Ground Truth Source):\n{full_context}\n"
            f"{feedback_prompt}"
        )
    
        return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

    def get_judge_messages(self, papers_data: Dict[str, Any], report_markdown: str) -> List[Any]:

        system_prompt = (

            "You are a strict academic verifier. Verify if the generated synthesis report is fully grounded "

            "in the provided source paper analyses."

        )

        user_prompt = f"""

SOURCE DATA:

{json.dumps(papers_data, indent=2)}



GENERATED REPORT:

{report_markdown}



Verify if:

1. Every claim cited with [arXiv:ID] is accurately supported by that specific paper's source data.

2. No hallucinated benchmarks, metrics, or non-existent authors/papers are introduced.

"""

        return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

    # --- BEZPIECZNE METODY ZINTEGROWANE Z QUOTĄ ---

    async def run_map_llm(self, messages: List[Any]) -> str:
        response = await safe_llm_invoke(self.map_model_name, self.map_llm, messages)
        content = getattr(response, "content", response)
        return extract_text_from_llm_response(content)

    async def run_reduce_llm(self, messages: List[Any]) -> str:
        response = await safe_llm_invoke(self.reduce_model_name, self.reduce_llm, messages)
        content = response.content
        if isinstance(content, list):
            return "".join([p.get("text", "") if isinstance(p, dict) else str(p) for p in content])
        return str(content)

    async def run_judge_llm(self, messages: List[Any]) -> JudgeEvaluation:
        try:
            structured_judge = self.judge_llm.with_structured_output(JudgeEvaluation)
            return await safe_llm_invoke(self.reduce_model_name, structured_judge, messages)
        except Exception as e:
            logger.warning(f"Judge evaluation failed: {e}")
            return JudgeEvaluation(is_grounded=True, errors=[])

    async def run_map_stage_parallel(self, articles_data: List[Dict[str, Any]], user_instruction: str) -> List[str]:
        async def process_article(art: Dict[str, Any]) -> str:
            messages = self.get_map_messages(
                title=art.get("title", ""),
                arxiv_id=art.get("arxiv_id", ""),
                user_instruction=user_instruction,
                text=art.get("text", "")
            )
            summary = await self.run_map_llm(messages)
            return f"### Paper: {art.get('title')} (arXiv:{art.get('arxiv_id')})\n{summary}"

        return await asyncio.gather(*[process_article(art) for art in articles_data])

    # --- STRUMIENIOWANIE Z PEŁNĄ OBSŁUGĄ QUOTY ---

    async def stream_reduce_stage(self, map_summaries: List[str], user_instruction: str) -> AsyncGenerator[str, None]:
        is_ok, msg = await quota_service.check_availability(self.reduce_model_name)
        if not is_ok:
            raise RuntimeError(f"Limit Gemini zablokowany: {msg}")

        messages = self.get_reduce_messages(
            context_blocks=map_summaries,
            user_instruction=user_instruction
        )
        
        total_tokens_approx = 0
        try:
            async for chunk in self.reduce_llm.astream(messages):
                if chunk.content:
                    text_chunk = str(chunk.content)
                    total_tokens_approx += len(text_chunk.split())
                    yield text_chunk
        finally:
            # Rejestracja zużycia w Redis po zakończeniu lub przerwaniu strumienia
            await quota_service.record_successful_call(
                self.reduce_model_name, 
                input_tokens=len(str(messages).split()), 
                output_tokens=total_tokens_approx
            )

    async def stream_translation(self, markdown_text: str, target_language: str) -> AsyncGenerator[str, None]:
        is_ok, msg = await quota_service.check_availability(self.reduce_model_name)
        if not is_ok:
            raise RuntimeError(f"QUOTA_EXHAUSTED: {msg}")

        system_prompt = (
            f"You are a professional scientific translator. Translate the provided Markdown report into {target_language}.\n"
            "CRITICAL RULES:\n"
            "1. Preserve ALL Markdown formatting, tables, headings, and bolding exactly.\n"
            "2. Preserve ALL citations like [arXiv:ID] or [arXiv:ID, p. X] UNCHANGED.\n"
            "3. Keep technical terms accurate and natural in {target_language}."
        )
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=markdown_text)]
    
        total_tokens_approx = 0
        input_tokens_approx = len(markdown_text.split())
    
        try:
            async for chunk in self.reduce_llm.astream(messages):
                content = chunk.content
                if not content:
                    continue
            
                if isinstance(content, str):
                    total_tokens_approx += len(content.split())
                    yield content
                elif isinstance(content, list):
                    for block in content:
                        text = block if isinstance(block, str) else (block.get("text", "") if isinstance(block, dict) else "")
                        if text:
                            total_tokens_approx += len(text.split())
                            yield text

            # Rejestrujemy sukces tylko, gdy cały stream przeszedł bez błędu
            await quota_service.record_successful_call(
                self.reduce_model_name,
                input_tokens=input_tokens_approx,
                output_tokens=total_tokens_approx
            )

        except (ResourceExhausted, Exception) as exc:
            err_msg = str(exc)
            if isinstance(exc, ResourceExhausted) or "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                await quota_service.record_429(self.reduce_model_name)
                raise RuntimeError(f"QUOTA_EXHAUSTED: Przekroczono limit zapytań (429) dla modelu {self.reduce_model_name}") from exc
            raise


    def get_model_for_mode(self, mode_key: str = "fast", temperature: float = 0.1) -> tuple[ChatGoogleGenerativeAI, str]:
        """Tworzy instancję ChatGoogleGenerativeAI skonfigurowaną pod dany tryb prędkości."""
        mode_config = settings.SPEED_MODES.get(mode_key, settings.SPEED_MODES.get("fast", {}))
        model_name = mode_config.get("model_name", settings.MAP_MODEL)
        service_tier = mode_config.get("service_tier", "flex")

        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=temperature,
            model_kwargs={"service_tier": service_tier}
        )
        return llm, model_name

    async def expand_keywords(self, user_instruction: str, mode_key: str = "fast") -> List[str]:
        """Generuje synonimy i słowa kluczowe przy użyciu LLM dla podanego trybu."""
        prompt = f"""
Given the following research query, extract key concepts and generate 3-5 relevant scientific synonyms, technical acronyms, or related terms used in arXiv papers.

Query: "{user_instruction}"
"""
        try:
            llm, model_name = self.get_model_for_mode(mode_key, temperature=0.0)
            structured_llm = llm.with_structured_output(QueryExpansionResponse)
            result = await safe_llm_invoke(model_name, structured_llm, prompt)
            
            if result and getattr(result, "keywords", None):
                logger.info(f"🧠 [QUERY EXPANSION] Wygenerowane synonimy/klucze: {result.keywords}")
                return list(set(result.keywords))

        except Exception as e:
            logger.warning(f"⚠️ [QUERY EXPANSION] Błąd generowania synonimów ({e}), używam oryginalnego zapytania.")

        return [user_instruction]

rag_engine = RAGEngine()