# backend/tests/performance/locustfile.py
import random
from locust import HttpUser, task, between

# Lista stabilnych artykułów do rotacji w testach
SAMPLE_PDF_URLS = [
    "https://arxiv.org/pdf/1706.03762.pdf", # Attention Is All You Need
    "https://arxiv.org/pdf/2005.14165.pdf", # GPT-3
    "https://arxiv.org/pdf/2103.00020.pdf", # CLIP
]

class APIUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def test_health_check(self):
        self.client.get("/api/v1/status")

    @task(2)
    def test_search_arxiv(self):
        payload = {
            "query": "Quantum Computing",
            "max_results": 5
        }
        self.client.post("/api/v1/search", json=payload)

    @task(1)
    def test_parse_pdf(self):
        payload = {
            "pdf_url": random.choice(SAMPLE_PDF_URLS),
            "max_pages": 5
        }
        # Catch_response pozwala poprawnie rejestrować ewentualne bloki ze strony arXiv
        with self.client.post("/api/v1/parse-pdf", json=payload, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}: {response.text}")