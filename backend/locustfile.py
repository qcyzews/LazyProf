from locust import HttpUser, task, between

class LazyProfUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def test_status_endpoint(self):
        self.client.get("/api/v1/status")

    @task(1)
    def test_health_check(self):
        self.client.get("/docs")