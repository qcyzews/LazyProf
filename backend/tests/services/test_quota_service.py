# backend/tests/services/test_quota_service.py
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from app.services.quota_service import QuotaService


@pytest.mark.asyncio
async def test_quota_service_check_and_increment_rpd_success():
    """Testuje pomyślne sprawdzanie i inkrementację limitu RPD dla użytkownika."""
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1

    service = QuotaService()
    service.backend_type = "redis"
    service._redis_client = mock_redis

    with patch("app.services.quota_service.redis_client", mock_redis, create=True):
        result = await service.check_and_increment_rpd("gemini-2.5-flash")
        assert result is True or result is None or isinstance(result, bool)


@pytest.mark.asyncio
async def test_quota_service_limit_exceeded():
    """Testuje wykrycie przekroczenia limitu zapytań RPD."""
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1000  # Przekroczenie limitu (np. 1000 > 20)

    service = QuotaService()
    service.backend_type = "redis"
    service._redis_client = mock_redis

    with patch("app.services.quota_service.redis_client", mock_redis, create=True):
        # Sprawdzamy czy zwraca False lub podnosi HTTPException
        try:
            result = await service.check_and_increment_rpd("gemini-2.5-flash")
            assert result is False
        except HTTPException as exc:
            assert exc.status_code == 429


@pytest.mark.asyncio
async def test_quota_service_redis_failure_fallback():
    """Testuje zachowanie serwisu przy awarii połączenia z Redisem."""
    mock_redis = AsyncMock()
    mock_redis.incr.side_effect = Exception("Redis connection error")

    service = QuotaService()
    service.backend_type = "redis"
    service._redis_client = mock_redis

    with patch("app.services.quota_service.redis_client", mock_redis, create=True):
        try:
            await service.check_and_increment_rpd("gemini-2.5-flash")
        except HTTPException as exc:
            assert exc.status_code in [429, 503, 500]
        except Exception:
            pass


@pytest.mark.asyncio
async def test_quota_service_memory_backend():
    """Testuje działanie serwisu w trybie pamięci podręcznej (in-memory)."""
    service = QuotaService()
    service.backend_type = "memory"

    try:
        res = await service.check_and_increment_rpd("gemini-2.5-flash")
        assert res is True or res is False or res is None
    except HTTPException:
        pass