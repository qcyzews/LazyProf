# backend/tests/api/test_status_api.py
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_get_system_status_endpoint():
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
        data = response.json()
        assert data["status"] == "ok"
        assert "modes" in data
        assert "fast" in data["modes"]
        assert data["modes"]["fast"]["available"] is True