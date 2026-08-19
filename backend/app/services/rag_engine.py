# /backend/app/services/rag_engine.py
import asyncio
import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional, Union
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings
from app.graph.state import JudgeEvaluation

logger = logging.getLogger(__name__)


class RAGEngine:
    def __init__(self):
        self.map_llm = ChatGoogleGenerativeAI(
            model=settings.MAP_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.0,
            model_kwargs={"service_tier": "flex"}
        )
        self.reduce_llm = ChatGoogleGenerativeAI(
            model=settings.REDUCE_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.1,
            streaming=True,
            model_kwargs={"service_tier": "flex"}
        )
        self.judge_llm = ChatGoogleGenerativeAI(
            model=settings.REDUCE_MODEL,
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
    
        # 1. Normalizacja i bezpieczne konwertowanie bloków na ciągi znaków (str)
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
    
        # 2. Tworzenie promptu korygującego (Feedback/Retry)
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

    async def run_map_llm(self, messages: List[Any]) -> str:
        response = await self.map_llm.ainvoke(messages)
        content = response.content
        if isinstance(content, list) and len(content) > 0 and isinstance(content[0], dict):
            return content[0].get("text", str(content))
        return str(content)

    async def run_reduce_llm(self, messages: List[Any]) -> str:
        response = await self.reduce_llm.ainvoke(messages)
        content = response.content
        if isinstance(content, list):
            return "".join([p.get("text", "") if isinstance(p, dict) else str(p) for p in content])
        return str(content)

    async def run_judge_llm(self, messages: List[Any]) -> JudgeEvaluation:
        try:
            structured_judge = self.judge_llm.with_structured_output(JudgeEvaluation)
            result: JudgeEvaluation = await structured_judge.ainvoke(messages)
            return result
        except Exception as e:
            logger.warning(f"Judge evaluation failed: {e}")
            return JudgeEvaluation(is_grounded=True, errors=[])

    # --- NOWE METODY OBSŁUGUJĄCE API/SSE ---

    async def run_map_stage_parallel(self, articles_data: List[Dict[str, Any]], user_instruction: str) -> List[str]:
        """Uruchamia etap MAP równolegle dla listy artykułów."""
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

    async def stream_reduce_stage(self, map_summaries: List[str], user_instruction: str) -> AsyncGenerator[str, None]:
        """Strumieniuje generowanie raportu końcowego w etapie REDUCE."""
        messages = self.get_reduce_messages(
            context_blocks=map_summaries,
            user_instruction=user_instruction
        )
        async for chunk in self.reduce_llm.astream(messages):
            if chunk.content:
                yield str(chunk.content)

    async def stream_translation(self, markdown_text: str, target_language: str) -> AsyncGenerator[str, None]:
        """Strumieniuje tłumaczenie raportu Markdown na podany język docelowy."""
        system_prompt = (
            f"You are a professional scientific translator. Translate the provided Markdown report into {target_language}.\n"
            "CRITICAL RULES:\n"
            "1. Preserve ALL Markdown formatting, tables, headings, and bolding exactly.\n"
            "2. Preserve ALL citations like [arXiv:ID] or [arXiv:ID, p. X] UNCHANGED.\n"
            "3. Keep technical terms accurate and natural in {target_language}."
        )
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=markdown_text)]
        try:
            async for chunk in self.reduce_llm.astream(messages):
                content = chunk.content
                if not content:
                    continue
            
                # Jeśli content jest zwykłym stringiem (np. OpenAI)
                if isinstance(content, str):
                    yield content
            
                # Jeśli content jest listą bloków (np. Anthropic / Claude)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, str):
                            yield block
                        elif isinstance(block, dict) and block.get("type") == "text":
                            yield block.get("text", "")

        except Exception as e:
            import logging
            logging.error(f"Błąd podczas strumieniowania tłumaczenia: {e}", exc_info=True)
            raise e

rag_engine = RAGEngine()