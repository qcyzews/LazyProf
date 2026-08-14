# backend/tests/performance/locustfile.py
from locust import HttpUser, task, between

class APIUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def test_health_check(self):
        self.client.get("/health")

    @task(2)
    def test_search_arxiv(self):
        headers = {"Content-Type": "application/json"}
        payload = {
            "query": "Quantum Computing",
            "max_results": 5
        }
        self.client.post("/api/v1/search", json=payload, headers=headers)

    @task(1)
    def test_parse_pdf(self):
        headers = {"Content-Type": "application/json"}
        # Przekazujemy PEŁNY URL do PDF-a
        payload = {
            "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
            "max_pages": 5
        }
        self.client.post("/api/v1/parse-pdf", json=payload, headers=headers)