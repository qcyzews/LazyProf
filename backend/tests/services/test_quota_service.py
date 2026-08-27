# backend/tests/services/test_quota_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.quota_service import QuotaService
from app.core.config import settings

@pytest.fixture(autouse=True)
def reset_quota_singleton():
    """Resetuje stan singletonu QuotaService przed i po każdym teście."""
    QuotaService._instance = None
    yield
    QuotaService._instance = None


# ============================================================================
# Inicjalizacja
# ============================================================================

def test_quota_service_init_missing_redis_import_raises_error():
    with patch("app.services.quota_service.redis", None):
        with patch("app.core.config.settings.QUOTA_BACKEND", "redis"):
            with pytest.raises(ImportError) as exc_info:
                QuotaService()
            assert "Brak pakietu 'redis'" in str(exc_info.value)


def test_quota_service_init_redis_backend_success():
    # Czyścimy instancję Singletona na potrzeby testu
    QuotaService._instance = None
    
    mock_redis = MagicMock()
    with patch("app.services.quota_service.redis", mock_redis):
        with patch("app.core.config.settings.QUOTA_BACKEND", "redis"):
            service = QuotaService()
            assert service.backend_type == "redis"
            # Sprawdzamy nowe wywołanie ConnectionPool zamiast starego from_url
            mock_redis.ConnectionPool.from_url.assert_called_once()


def test_quota_service_init_memory_backend():
    with patch("app.core.config.settings.QUOTA_BACKEND", "in_memory"):
        service = QuotaService()
        assert service.backend_type == "in_memory"
        assert service._redis_client is None


# ============================================================================
# check_availability
# ============================================================================

@pytest.mark.asyncio
async def test_check_availability_memory_success():
    service = QuotaService()
    service.backend_type = "in_memory"
    service._in_memory_tracker = {}

    ok, msg = await service.check_availability("gemini-2.5-flash", estimated_tokens=1000)
    assert ok is True
    assert msg == "OK"


@pytest.mark.asyncio
async def test_check_availability_memory_rpm_exceeded():
    service = QuotaService()
    service.backend_type = "in_memory"
    rpm_key, _, _ = service._get_time_keys("gemini-2.5-flash")
    service._in_memory_tracker[rpm_key] = 100

    ok, msg = await service.check_availability("gemini-2.5-flash")
    assert ok is False
    assert "limit RPM" in msg


@pytest.mark.asyncio
async def test_check_availability_memory_tpm_exceeded():
    service = QuotaService()
    service.backend_type = "in_memory"
    _, tpm_key, _ = service._get_time_keys("gemini-2.5-flash")
    service._in_memory_tracker[tpm_key] = 249_000

    ok, msg = await service.check_availability("gemini-2.5-flash", estimated_tokens=2000)
    assert ok is False
    assert "limit TPM" in msg


@pytest.mark.asyncio
async def test_check_availability_memory_rpd_exceeded():
    service = QuotaService()
    service.backend_type = "in_memory"
    _, _, rpd_key = service._get_time_keys("gemini-2.5-flash")
    service._in_memory_tracker[rpd_key] = 50

    ok, msg = await service.check_availability("gemini-2.5-flash")
    assert ok is False
    assert "limit RPD" in msg


@pytest.mark.asyncio
async def test_check_availability_redis_success():
    QuotaService._instance = None
    service = QuotaService()
    service.backend_type = "redis"

    mock_pipe = MagicMock()
    mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
    mock_pipe.__aexit__ = AsyncMock(return_value=None)
    mock_pipe.execute = AsyncMock(return_value=["1", "500", "5"])
    
    # Jawnie definiujemy synchroniczne wywołanie get
    mock_pipe.get = MagicMock()

    mock_redis = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    service._redis_client = mock_redis

    ok, msg = await service.check_availability("gemini-2.5-flash", estimated_tokens=1000)
    assert ok is True
    assert msg == "OK"
    assert mock_pipe.get.call_count == 3


# ============================================================================
# record_successful_call
# ============================================================================

@pytest.mark.asyncio
async def test_record_successful_call_memory():
    service = QuotaService()
    service.backend_type = "in_memory"
    service._in_memory_tracker = {}

    model_name = "gemini-2.5-flash"
    await service.record_successful_call(model_name, input_tokens=100, output_tokens=200)

    rpm_key, tpm_key, rpd_key = service._get_time_keys(model_name)
    assert service._in_memory_tracker[rpm_key] == 1
    assert service._in_memory_tracker[tpm_key] == 300
    assert service._in_memory_tracker[rpd_key] == 1


@pytest.mark.asyncio
async def test_record_successful_call_redis():
    service = QuotaService()
    service.backend_type = "redis"

    mock_pipe = MagicMock()
    mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
    mock_pipe.__aexit__ = AsyncMock(return_value=None)
    mock_pipe.execute = AsyncMock(return_value=None)

    mock_redis = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    service._redis_client = mock_redis

    await service.record_successful_call("gemini-2.5-flash", input_tokens=50, output_tokens=50)

    assert mock_pipe.incr.call_count >= 2
    assert mock_pipe.incrby.call_count >= 2
    assert mock_pipe.expire.call_count == 3
    mock_pipe.execute.assert_called_once()


# ============================================================================
# get_available_modes_status
# ============================================================================

@pytest.mark.asyncio
async def test_get_available_modes_status_memory_backend():
    service = QuotaService()
    service.backend_type = "in_memory"
    service._in_memory_tracker = {}

    status = await service.get_available_modes_status()
    assert isinstance(status, dict)
    assert len(status) > 0
    for mode_data in status.values():
        assert "available" in mode_data
        assert "remaining_rpd" in mode_data


@pytest.mark.asyncio
async def test_get_available_modes_status_redis_backend():
    QuotaService._instance = None
    service = QuotaService()
    service.backend_type = "redis"

    num_modes = len(settings.SPEED_MODES)

    # Tworzymy mock dla pipeline
    mock_pipe = MagicMock()
    mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
    mock_pipe.__aexit__ = AsyncMock(return_value=None)
    mock_pipe.execute = AsyncMock(return_value=["3"] * num_modes)
    
    # pipe.get jest synchroniczne w pipeline Redisa!
    mock_pipe.get = MagicMock()

    mock_redis = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    service._redis_client = mock_redis

    status = await service.get_available_modes_status()
    
    assert isinstance(status, dict)
    assert len(status) > 0
    for mode_data in status.values():
        assert mode_data["current_rpd_usage"] == 3