# /backend/app/services/debug_service.py
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from app.core.config import settings

class DebugService:
    def __init__(self, output_dir: str = "debug_logs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def log_failed_audit_async(
        self,
        generated_report: str,
        judge_result: Dict[str, Any],
        context_chunks: List[Any],
        user_instruction: Optional[str] = None
    ) -> None:
        """Uruchamia zapis w tle, nie blokując głównego wątku RAG."""
        if not getattr(settings, "ENABLE_DEBUG_DUMP", False):
            return
        asyncio.create_task(
            self._save_to_disk(generated_report, judge_result, context_chunks, user_instruction)
        )

    async def _save_to_disk(
        self,
        generated_report: str,
        judge_result: Dict[str, Any],
        context_chunks: List[Any],
        user_instruction: Optional[str]
    ) -> None:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = self.output_dir / f"audit_fail_{timestamp}.json"

            payload = {
                "timestamp": datetime.now().isoformat(),
                "user_instruction": user_instruction,
                "judge_output": judge_result,
                "generated_report": generated_report,
                "context_provided": context_chunks,
            }

            # Zapis pliku
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            print(f"⚠️ [DebugService] Zrzut błędnego audytu zapisany w: {filename}")
        except Exception as e:
            print(f"❌ [DebugService] Błąd podczas zapisu zrzutu debugowego: {e}")

# Singleton dla aplikacji
debug_service = DebugService()