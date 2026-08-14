# /backend/tests/test_core_and_main.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.models.schemas import StatusResponse

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
    """Testuje czy endpoint /status odpowiada prawidłowo i zwraca poprawny schemat."""
    response = client.get("/api/v1/status")  # Jeśli Twój endpoint jest pod prefiksem, zmień na np. /api/v1/status
    assert response.status_code == 200
    
    # Walidacja odpowiedzi za pomocą schematu Pydantic
    data = response.json()
    status_model = StatusResponse(**data)
    
    assert status_model.status == "ok"
    assert isinstance(status_model.modes, dict)


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