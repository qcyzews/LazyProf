import pytest
from fastapi.testclient import TestClient
from app.main import app  # importuj swoją instancję FastAPI

client = TestClient(app)

PROD_FRONTEND_ORIGIN = "https://lazy-prof.vercel.app"

def test_cors_preflight_allowed_origin():
    """Sprawdza czy serwer zwraca poprawne nagłówki CORS dla produkcyjnego frontendu."""
    response = client.options(
        "/api/v1/status",
        headers={
            "Origin": PROD_FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization",
        },
    )
    
    # Kod statusu preflight powinien być 200 lub 204
    assert response.status_code in [200, 204]
    
    # Kluczowe nagłówki CORS
    assert response.headers.get("access-control-allow-origin") == PROD_FRONTEND_ORIGIN
    assert "POST" in response.headers.get("access-control-allow-methods", "")

def test_cors_disallowed_origin():
    """Sprawdza czy nieznana domena nie dostaje nagłówka Access-Control-Allow-Origin."""
    response = client.options(
        "/api/v1/status",
        headers={
            "Origin": "https://zlosliwa-domena.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers.get("access-control-allow-origin") != "https://zlosliwa-domena.com"