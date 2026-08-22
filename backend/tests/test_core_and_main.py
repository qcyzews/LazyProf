# /backend/tests/test_core_and_main.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.models.schemas import StatusResponse
from unittest.mock import AsyncMock, MagicMock, patch

client = TestClient(app)


def test_main_root_endpoint():
    """Testuje czy aplikacja startuje i odpowiada na zapytania w korzeniu lub docs."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_config_loading():
    """Weryfikuje czy konfiguracja ładuje podstawowe zmienne środowiskowe."""
    assert settings.MAP_MODEL is not None
    assert settings.REDUCE_MODEL is not None


def test_status_endpoint():
    mock_status = {
        "fast": {
            "available": True,
            "model_name": "gemini-2.5-flash",
            "remaining_rpd": 20,
            "max_rpd": 20,
            "current_rpd_usage": 0
        }
    }
    with patch("app.api.v1.endpoints.quota_service.get_available_modes_status", new_callable=AsyncMock) as mock_get_status:
        mock_get_status.return_value = mock_status
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_schemas_validation():
    """Sprawdza poprawność walidacji modeli Pydantic na sztucznych danych."""
    sample_data = {
        "status": "ok",
        "modes": {
            "fast": {
                "available": True,
                "model_name": "gemini-2.5-flash",
                "remaining_rpd": 19,
                "max_rpd": 20
            }
        }
    }
    
    model = StatusResponse(**sample_data)
    
    assert model.status == "ok"
    assert "fast" in model.modes
    assert model.modes["fast"].available is True
    assert model.modes["fast"].remaining_rpd == 19