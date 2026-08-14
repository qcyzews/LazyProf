from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_get_system_status_endpoint():
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "ok"
    assert "modes" in data
    assert "fast" in data["modes"]
    assert "available" in data["modes"]["fast"]