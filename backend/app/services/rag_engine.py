import asyncio
import logging
from typing import AsyncGenerator, List, Dict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from google.genai.errors import ServerError, APIError

from app.core.config import settings

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
            temperature=0.0,
            streaming=True,
            model_kwargs={"service_tier": "flex"}
        )

    async def analyze_single_article(self, text: str, user_instruction: str) -> str:
        """[MAP STAGE] Extracts key findings from a single research paper."""
        system_prompt = (
            "You are an expert AI academic research assistant for LazyProf. "
            "Analyze the provided scientific paper and extract key findings, methodology, "
            "and insights strictly relevant to the user's instruction.\n"
            "Be concise and structure your response using bullet points."
        )

        user_prompt = f"User Instruction: {user_instruction}\n\nArticle Text:\n{text[:30000]}"

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                response = await self.map_llm.ainvoke(messages)
                content = response.content
                if isinstance(content, list) and len(content) > 0 and isinstance(content[0], dict):
                    return content[0].get("text", str(content))
                return str(content)
            except (ServerError, APIError, Exception) as e:
                logger.warning(f"[MAP Stage] API Error (attempt {attempt}/{max_attempts}): {e}")
                if attempt == max_attempts:
                    raise e
                await asyncio.sleep(2 * attempt)

    async def run_map_stage_parallel(
        self, 
        articles_data: List[Dict[str, str]], 
        user_instruction: str
    ) -> List[Dict[str, str]]:
        """Runs the MAP stage concurrently for all downloaded articles."""
        tasks = [
            self.analyze_single_article(art["text"], user_instruction)
            for art in articles_data
        ]

        results = await asyncio.gather(*tasks)

        summaries = []
        for i, summary in enumerate(results):
            summaries.append({
                "title": articles_data[i]["title"],
                "arxiv_id": articles_data[i]["arxiv_id"],
                "summary": summary
            })
        return summaries

    async def stream_reduce_stage(
        self, 
        map_summaries: List[Dict[str, str]], 
        user_instruction: str
    ) -> AsyncGenerator[str, None]:
        """[REDUCE STAGE] Synthesizes all extracted information into a comprehensive report in English."""

        context_blocks = []
        for item in map_summaries:
            context_blocks.append(
                f"### Paper: {item['title']} (arXiv: {item['arxiv_id']})\n{item['summary']}"
            )
        full_context = "\n\n---\n\n".join(context_blocks)

        system_prompt = (
            "You are a distinguished university professor synthesizing multi-paper literature reviews for LazyProf. "
            "Synthesize the provided extracted summaries into a structured, comprehensive, and cohesive report.\n"
            "Format the output strictly in clean Markdown (headings, key takeaways, summary tables, bullet points)."
        )

        user_prompt = (
            f"User Objective: {user_instruction}\n\n"
            f"Extracted Paper Summaries:\n{full_context}"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        max_attempts = 3
        delay = 2.0

        for attempt in range(1, max_attempts + 1):
            try:
                async for chunk in self.reduce_llm.astream(messages):
                    content = chunk.content
                    if not content:
                        continue

                    if isinstance(content, str):
                        yield content
                    elif isinstance(content, list) and len(content) > 0:
                        first = content[0]
                        if isinstance(first, dict) and "text" in first:
                            yield first["text"]
                        elif isinstance(first, str):
                            yield first
                        else:
                            yield str(first)
                    elif isinstance(content, dict) and "text" in content:
                        yield content["text"]
                    else:
                        yield str(content)
                return
            except (ServerError, APIError, Exception) as e:
                logger.warning(f"[REDUCE Stage] API Error (attempt {attempt}/{max_attempts}): {e}")
                if attempt == max_attempts:
                    raise e
                await asyncio.sleep(delay * attempt)

    async def stream_translation(
        self, 
        text: str, 
        target_language: str = "Polish"
    ) -> AsyncGenerator[str, None]:
        """Translates a Markdown report into the target language while preserving formatting."""
        
        system_prompt = (
            f"You are a professional academic translator. Translate the following Markdown report into {target_language}.\n"
            "CRITICAL REQUIREMENTS:\n"
            "1. Maintain all Markdown formatting (headings, bold text, bullet points, tables) EXACTLY as they appear.\n"
            "2. Preserve all paper titles, author names, arXiv IDs, equations, and specialized technical terms accurately.\n"
            "3. Do NOT add any intro, outro, or meta-comments—output ONLY the translated Markdown text."
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=text)
        ]

        max_attempts = 3
        delay = 2.0

        for attempt in range(1, max_attempts + 1):
            try:
                async for chunk in self.reduce_llm.astream(messages):
                    content = chunk.content
                    if not content:
                        continue

                    if isinstance(content, str):
                        yield content
                    elif isinstance(content, list) and len(content) > 0:
                        first = content[0]
                        if isinstance(first, dict) and "text" in first:
                            yield first["text"]
                        else:
                            yield str(first)
                    elif isinstance(content, dict) and "text" in content:
                        yield content["text"]
                    else:
                        yield str(content)
                return
            except (ServerError, APIError, Exception) as e:
                logger.warning(f"[TRANSLATION] API Error (attempt {attempt}/{max_attempts}): {e}")
                if attempt == max_attempts:
                    raise e
                await asyncio.sleep(delay * attempt)