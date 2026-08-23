# backend/app/services/llm_service.py
import logging
from typing import Any
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from google.genai.errors import (
    APIError,
    ServerError as GenAIServerError,
)
from google.api_core.exceptions import (
    ResourceExhausted as CoreResourceExhausted,
    TooManyRequests as CoreTooManyRequests,
    ServerError as CoreServerError,
    GoogleAPICallError,
)
from app.services.quota_service import quota_service

logger = logging.getLogger(__name__)


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

def _safe_int(val: Any, default: int = 0) -> int:
    """Zwraca int tylko jeśli wartość jest faktyczną liczbą (zapobiega mockom)."""
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return int(val)
    return default

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

    if hasattr(response, "response_metadata") and isinstance(response.response_metadata, dict):
        usage = response.response_metadata.get("usage_metadata") or response.response_metadata.get("token_usage")
        if isinstance(usage, dict):
            in_tokens = _safe_int(usage.get("prompt_tokens") or usage.get("prompt_token_count"))
            out_tokens = _safe_int(usage.get("completion_tokens") or usage.get("candidates_token_count"))
        elif usage is not None:
            in_tokens = _safe_int(getattr(usage, "prompt_token_count", getattr(usage, "prompt_tokens", 0)))
            out_tokens = _safe_int(getattr(usage, "candidates_token_count", getattr(usage, "completion_tokens", 0)))
            
    elif hasattr(response, "usage_metadata") and response.usage_metadata is not None:
        usage = response.usage_metadata
        if isinstance(usage, dict):
            in_tokens = _safe_int(usage.get("prompt_token_count"))
            out_tokens = _safe_int(usage.get("candidates_token_count"))
        else:
            in_tokens = _safe_int(getattr(usage, "prompt_token_count", 0))
            out_tokens = _safe_int(getattr(usage, "candidates_token_count", 0))

    # 4. Zapisanie faktycznego zużycia
    await quota_service.record_successful_call(model_name, in_tokens, out_tokens)

    return response


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