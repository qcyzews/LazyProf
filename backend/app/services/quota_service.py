# backend/app/services/quota_service.py
import datetime
import logging
from typing import Dict, Any
from aiolimiter import AsyncLimiter
from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

# Opcjonalny import redis (zabezpieczony, jeśli paczka nie jest zainstalowana lokalnie)
try:
    import redis.asyncio as redis
except ImportError:
    redis = None


class QuotaService:
    def __init__(self):
        # Limity RPM w pamięci (działają per-proces)
        self.limiters: Dict[str, AsyncLimiter] = {}
        for model_name, limits in settings.MODEL_LIMITS.items():
            safe_rpm = max(1, limits.get("rpm", 5) - 1)
            self.limiters[model_name] = AsyncLimiter(max_rate=safe_rpm, time_period=60)

        # Inicjalizacja wybranego backendu dla RPD
        self.backend_type = settings.QUOTA_BACKEND.lower()
        self._in_memory_tracker: Dict[str, Dict[str, Any]] = {}
        self._redis_client = None

        if self.backend_type == "redis":
            if redis is None:
                raise ImportError("Brak pakiety 'redis'. Zainstaluj go używając: pip install redis")
            logger.info(f"🔌 [QUOTA SERVICE] Inicjalizacja połączenia Redis ({settings.REDIS_URL})...")
            self._redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        else:
            logger.info("🧠 [QUOTA SERVICE] Używanie trybu pamięciowego (in_memory).")

    async def check_and_increment_rpd(self, model_name: str) -> bool:
        """Sprawdza i inkrementuje RPD w zależności od wybranego w settings backendu."""
        today = str(datetime.date.today())
        limits = settings.MODEL_LIMITS.get(model_name, {"rpd": 20})
        max_rpd = limits.get("rpd", 20)

        # --- OPTION A: REDIS BACKEND ---
        if self.backend_type == "redis" and self._redis_client:
            key = f"rpd:{model_name}:{today}"
            current_count = await self._redis_client.incr(key)

            # Ustawienie TTL na 24h przy pierwszym zapytaniu w danym dniu
            if current_count == 1:
                await self._redis_client.expire(key, 86400)

            if current_count > max_rpd:
                logger.error(f"🛑 [RPD LIMIT - REDIS] Model {model_name} osiągnął limit {max_rpd}!")
                return False
            return True

        # --- OPTION B: IN_MEMORY BACKEND ---
        else:
            if model_name not in self._in_memory_tracker or self._in_memory_tracker[model_name]["date"] != today:
                self._in_memory_tracker[model_name] = {"date": today, "count": 0}

            if self._in_memory_tracker[model_name]["count"] >= max_rpd:
                logger.error(f"🛑 [RPD LIMIT - MEMORY] Model {model_name} osiągnął limit {max_rpd}!")
                return False

            self._in_memory_tracker[model_name]["count"] += 1
            return True

    async def get_available_modes_status(self) -> Dict[str, Any]:
        """Zwraca status dostępności trybów dla API / frontendu."""
        today = str(datetime.date.today())
        modes_status = {}

        for mode_key, mode_cfg in settings.SPEED_MODES.items():
            model_name = mode_cfg.get("model_name")
            max_rpd = settings.MODEL_LIMITS.get(model_name, {}).get("rpd", 20)
            
            # Odczyt liczby zapytań z odpowiedniego backendu
            if self.backend_type == "redis" and self._redis_client:
                key = f"rpd:{model_name}:{today}"
                val = await self._redis_client.get(key)
                current_count = int(val) if val else 0
            else:
                tracker = self._in_memory_tracker.get(model_name, {"date": today, "count": 0})
                current_count = tracker["count"] if tracker["date"] == today else 0

            is_available = current_count < max_rpd
            modes_status[mode_key] = {
                "available": is_available,
                "model_name": model_name,
                "remaining_rpd": max(0, max_rpd - current_count),
                "max_rpd": max_rpd
            }

        return modes_status


# Instancja globalna (Singleton)
quota_service = QuotaService()