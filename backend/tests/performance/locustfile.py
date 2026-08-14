# backend/tests/performance/locustfile.py
from locust import HttpUser, task, between, events
import random

class APIUser(HttpUser):
    # Czas oczekiwania użytkownika między zapytaniami (od 1 do 3 sekund)
    wait_time = between(1, 3)

    @task(3)
    def test_health_check(self):
        """Testuje prosty punkt końcowy (np. status API)."""
        self.client.get("/health")

    @task(2)
    def test_get_modes_status(self):
        """Testuje pobieranie statusu limitów/trybów (odpytuje QuotaService)."""
        self.client.get("/api/v1/modes-status")

    @task(1)
    def test_pdf_extraction_mock(self):
        """
        Przykładowe zapytanie do serwisu PDF.
        Używamy przykładowego ID arXiv.
        """
        headers = {"Content-Type": "application/json"}
        payload = {
            "arxiv_id": "1706.03762",
            "max_pages": 5
        }
        self.client.post("/api/v1/extract-pdf", json=payload, headers=headers)