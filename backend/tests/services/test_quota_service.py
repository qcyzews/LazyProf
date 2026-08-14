# backend/tests/services/test_quota_service.py
import pytest
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.quota_service import QuotaService


# ============================================================================
# TESTY: Inicjalizacja QuotaService
# ============================================================================

def test_quota_service_init_missing_redis_import_raises_error():
    """Testuje wyrzucenie ImportError przy braku pakiety redis w trybie redis."""
    with patch("app.services.quota_service.redis", None):
        with patch("app.core.config.settings.QUOTA_BACKEND", "redis"):
            with pytest.raises(ImportError) as exc_info:
                QuotaService()
            assert "Brak pakiety 'redis'" in str(exc_info.value)


def test_quota_service_init_redis_backend_success():
    """Testuje poprawną inicjalizację klienta Redis w trybie redis."""
    mock_redis = MagicMock()
    with patch("app.services.quota_service.redis", mock_redis):
        with patch("app.core.config.settings.QUOTA_BACKEND", "redis"):
            service = QuotaService()
            assert service.backend_type == "redis"
            mock_redis.from_url.assert_called_once()


def test_quota_service_init_memory_backend():
    """Testuje inicjalizację w domyślnym trybie pamięciowym."""
    with patch("app.core.config.settings.QUOTA_BACKEND", "in_memory"):
        service = QuotaService()
        assert service.backend_type == "in_memory"
        assert service._redis_client is None


# ============================================================================
# TESTY: check_and_increment_rpd (Redis Backend)
# ============================================================================

@pytest.mark.asyncio
async def test_check_and_increment_rpd_redis_first_call_sets_ttl():
    """Testuje, czy przy pierwszym zapytaniu w dniu (count == 1) wywoływana jest metoda expire."""
    service = QuotaService()
    service.backend_type = "redis"
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1
    service._redis_client = mock_redis

    res = await service.check_and_increment_rpd("gemini-2.5-flash")

    assert res is True
    mock_redis.incr.assert_called_once()
    mock_redis.expire.assert_called_once()


@pytest.mark.asyncio
async def test_check_and_increment_rpd_redis_limit_exceeded():
    """Testuje przekroczenie limitu RPD w trybie Redis."""
    service = QuotaService()
    service.backend_type = "redis"
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1000  # Przekroczenie limitu
    service._redis_client = mock_redis

    res = await service.check_and_increment_rpd("gemini-2.5-flash")

    assert res is False


# ============================================================================
# TESTY: check_and_increment_rpd (In-Memory Backend)
# ============================================================================

@pytest.mark.asyncio
async def test_check_and_increment_rpd_memory_success_and_increment():
    """Testuje sukces i inkrementację licznika w trybie pamięciowym."""
    service = QuotaService()
    service.backend_type = "in_memory"

    model_name = "test-model-unique"
    res = await service.check_and_increment_rpd(model_name)

    assert res is True
    assert service._in_memory_tracker[model_name]["count"] == 1


@pytest.mark.asyncio
async def test_check_and_increment_rpd_memory_limit_exceeded():
    """Testuje odrzucenie zapytania po osiągnięciu max_rpd w trybie pamięciowym."""
    service = QuotaService()
    service.backend_type = "in_memory"
    today = str(datetime.date.today())

    model_name = "test-model-limit"
    # Sztuczne ustawienie maksymalnej liczby zapytań
    service._in_memory_tracker[model_name] = {"date": today, "count": 20}

    res = await service.check_and_increment_rpd(model_name)

    assert res is False
    assert service._in_memory_tracker[model_name]["count"] == 20


@pytest.mark.asyncio
async def test_check_and_increment_rpd_memory_date_rollover():
    """Testuje resetowanie licznika pamięciowego po zmianie dnia."""
    service = QuotaService()
    service.backend_type = "in_memory"

    model_name = "test-model-rollover"
    # Zapisan ze starą datą
    service._in_memory_tracker[model_name] = {"date": "2020-01-01", "count": 20}

    res = await service.check_and_increment_rpd(model_name)

    assert res is True
    assert service._in_memory_tracker[model_name]["count"] == 1
    assert service._in_memory_tracker[model_name]["date"] == str(datetime.date.today())


# ============================================================================
# TESTY: get_available_modes_status
# ============================================================================

@pytest.mark.asyncio
async def test_get_available_modes_status_redis_backend():
    """Testuje pobieranie statusów trybów z backendu Redis."""
    service = QuotaService()
    service.backend_type = "redis"
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = lambda key: "5" if "flash" in key else None
    service._redis_client = mock_redis

    status = await service.get_available_modes_status()

    assert isinstance(status, dict)
    assert len(status) > 0


@pytest.mark.asyncio
async def test_get_available_modes_status_memory_backend():
    """Testuje pobieranie statusów trybów z backendu In-Memory (z uwzględnieniem starych wpisów)."""
    service = QuotaService()
    service.backend_type = "in_memory"
    today = str(datetime.date.today())

    # Zasilamy tracker jednym nowym i jednym przestarzałym wpisem
    service._in_memory_tracker = {
        "gemini-2.5-flash": {"date": today, "count": 10},
        "gemini-2.5-pro": {"date": "2020-01-01", "count": 18}
    }

    status = await service.get_available_modes_status()

    assert isinstance(status, dict)
    assert len(status) > 0