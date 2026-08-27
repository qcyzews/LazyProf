# /backend/app/services/quota_service.py
import asyncio
from datetime import datetime, timezone
import logging
from typing import Dict, Any, Tuple
from aiolimiter import AsyncLimiter
from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

try:
    import redis.asyncio as redis
except ImportError:
    redis = None


class LoopAwareLimiters:
    """Słownik tworzący instancje AsyncLimiter powiązane z bieżącą pętlą zdarzeń."""
    def __init__(self, limits: Dict[str, Dict[str, Any]]):
        self._limits = limits
        # Klucz: (model_name, loop_id) -> AsyncLimiter
        self._pool: Dict[Tuple[str, int], AsyncLimiter] = {}

    def get(self, model_name: str, default=None) -> AsyncLimiter | None:
        if model_name not in self._limits:
            return default
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return default

        key = (model_name, id(loop))
        if key not in self._pool:
            safe_rpm = max(1, self._limits[model_name].get("rpm", 5) - 1)
            self._pool[key] = AsyncLimiter(max_rate=safe_rpm, time_period=60)
        return self._pool[key]

    def __getitem__(self, model_name: str) -> AsyncLimiter:
        limiter = self.get(model_name)
        if limiter is None:
            raise KeyError(model_name)
        return limiter
class QuotaService:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(QuotaService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.backend_type = settings.QUOTA_BACKEND.lower()
        self.limits = settings.MODEL_LIMITS
        
        # Lokalne limitery RPM jako fallback/in-memory
        self.limiters = LoopAwareLimiters(self.limits)

        self._in_memory_tracker: Dict[str, Dict[str, Any]] = {}
        self._redis_client = None

        if self.backend_type == "redis":
            if redis is None:
                raise ImportError("Brak pakietu 'redis'. Zainstaluj go: pip install redis")
            logger.info(f"🔌 [QUOTA SERVICE] Inicjalizacja połączenia Redis ({settings.REDIS_URL})...")
            self._redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        else:
            logger.info("🧠 [QUOTA SERVICE] Używanie trybu pamięciowego (in_memory).")

        self._initialized = True

    def _get_time_keys(self, model_name: str) -> Tuple[str, str, str]:
        now = datetime.now(timezone.utc)
        min_str = now.strftime("%Y%m%d%H%M")
        day_str = now.strftime("%Y%m%d")
        return (
            f"gemini:{model_name}:rpm:{min_str}",
            f"gemini:{model_name}:tpm:{min_str}",
            f"gemini:{model_name}:rpd:{day_str}"
        )

    async def check_availability(self, model_name: str, estimated_tokens: int = 1500) -> Tuple[bool, str]:
        """Sprawdza przed wykonaniem strzału, czy nie przekroczymy RPM, TPM lub RPD."""
        limits = self.limits.get(model_name, {"rpm": 5, "tpm": 250_000, "rpd": 20})
        rpm_key, tpm_key, rpd_key = self._get_time_keys(model_name)

        if self.backend_type == "redis" and self._redis_client:
            async with self._redis_client.pipeline(transaction=False) as pipe:
                pipe.get(rpm_key)
                pipe.get(tpm_key)
                pipe.get(rpd_key)
                rpm_val, tpm_val, rpd_val = await pipe.execute()

            current_rpm = int(rpm_val or 0)
            current_tpm = int(tpm_val or 0)
            current_rpd = int(rpd_val or 0)
        else:
            current_rpm = self._in_memory_tracker.get(rpm_key, 0)
            current_tpm = self._in_memory_tracker.get(tpm_key, 0)
            current_rpd = self._in_memory_tracker.get(rpd_key, 0)

        if current_rpm >= limits.get("rpm", 5):
            return False, f"Osiągnięto limit RPM dla {model_name} ({current_rpm}/{limits.get('rpm')}). Poczekaj chwilę."

        if current_tpm + estimated_tokens > limits.get("tpm", 250_000):
            return False, f"Przekroczono limit TPM dla {model_name} ({current_tpm}/{limits.get('tpm')})."

        if current_rpd >= limits.get("rpd", 20):
            return False, f"Wyczerpano dzienny limit RPD dla {model_name} ({current_rpd}/{limits.get('rpd')})."

        return True, "OK"

    async def record_successful_call(self, model_name: str, input_tokens: int = 0, output_tokens: int = 0):
        """Rejestruje zużycie po faktycznym udanym zapytaniu."""
        total_tokens = max(1, input_tokens + output_tokens)
        rpm_key, tpm_key, rpd_key = self._get_time_keys(model_name)

        if self.backend_type == "redis" and self._redis_client:
            async with self._redis_client.pipeline(transaction=True) as pipe:
                pipe.incr(rpm_key)
                pipe.expire(rpm_key, 65)

                pipe.incrby(tpm_key, total_tokens)
                pipe.expire(tpm_key, 65)

                pipe.incr(rpd_key)
                pipe.expire(rpd_key, 90000)

                # Globalna analityka
                pipe.incr(f"gemini:{model_name}:total_requests")
                pipe.incrby(f"gemini:{model_name}:total_tokens", total_tokens)
                await pipe.execute()
        else:
            self._in_memory_tracker[rpm_key] = self._in_memory_tracker.get(rpm_key, 0) + 1
            self._in_memory_tracker[tpm_key] = self._in_memory_tracker.get(tpm_key, 0) + total_tokens
            self._in_memory_tracker[rpd_key] = self._in_memory_tracker.get(rpd_key, 0) + 1

    async def get_available_modes_status(self) -> Dict[str, Any]:
        """
        Zwraca status dostępności trybów dla API / frontendu.
        W przypadku braku połączenia z Redisem zwraca bezpieczny brak dostępności (Fail-Closed).
        """
        modes_status = {}

        for mode_key, mode_cfg in settings.SPEED_MODES.items():
            model_name = mode_cfg.get("model_name")
            limits = settings.MODEL_LIMITS.get(model_name, {"rpd": 20, "rpm": 5, "tpm": 250_000})
            max_rpd = limits.get("rpd", 20)
            _, _, rpd_key = self._get_time_keys(model_name)

            if self.backend_type == "redis" and self._redis_client:
                try:
                    val = await self._redis_client.get(rpd_key)
                    current_count = int(val) if val else 0
                    is_available = current_count < max_rpd

                    modes_status[mode_key] = {
                        "available": is_available,
                        "model_name": model_name,
                        "remaining_rpd": max(0, max_rpd - current_count),
                        "max_rpd": max_rpd,
                        "current_rpd_usage": current_count,
                        "status_code": "ok"
                    }

                except RedisError as e:
                    # Brak pewności co do stanu limitów -> Odrzucamy dostępność (Fail-Closed)
                    logger.error(f"❌ [QuotaService] Błąd połączenia z Redisem dla {mode_key}: {e}")
                    modes_status[mode_key] = {
                        "available": False,
                        "model_name": model_name,
                        "remaining_rpd": 0,
                        "max_rpd": max_rpd,
                        "current_rpd_usage": 0,
                        "status_code": "service_unavailable",
                        "error_message": "Nie można zweryfikować limitów usługi."
                    }
            else:
                current_count = self._in_memory_tracker.get(rpd_key, 0)
                is_available = current_count < max_rpd
                modes_status[mode_key] = {
                    "available": is_available,
                    "model_name": model_name,
                    "remaining_rpd": max(0, max_rpd - current_count),
                    "max_rpd": max_rpd,
                    "current_rpd_usage": current_count,
                    "status_code": "ok"
                }

        return modes_status

quota_service = QuotaService()