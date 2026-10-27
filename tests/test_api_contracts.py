"""
API contract tests verifying endpoint statuses, validation rules, and standardized error schemas.
"""

from fastapi.testclient import TestClient
import pytest

from app.main import app

client = TestClient(app)


class TestAPIContracts:
    """Test suite for FastAPI contracts and typed errors."""

    def test_health_check_endpoint(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "llm_configured" in data
        assert "version" in data

    def test_apps_validate_invalid_country(self):
        resp = client.post(
            "/apps/validate",
            json={
                "stores": ["playstore"],
                "play_package": "com.test.app",
                "country": "us",  # Non-India storefront
            },
        )
        assert resp.status_code == 422
        data = resp.json()
        assert "error" in data["detail"]
        assert data["detail"]["error"]["code"] == "INVALID_CONFIG"

    def test_create_run_validation_errors(self):
        # 1. Sample size too small (< 50)
        resp = client.post(
            "/runs",
            json={
                "app_name": "Test App",
                "stores": ["playstore"],
                "play_package": "com.test.app",
                "sample_size": 20,  # Below min 50
                "country": "in",
            },
        )
        assert resp.status_code == 422

        # 2. Missing play_package when playstore in stores
        resp = client.post(
            "/runs",
            json={
                "app_name": "Test App",
                "stores": ["playstore"],
                "play_package": None,
                "country": "in",
            },
        )
        assert resp.status_code == 422

        # 3. Country != 'in'
        resp = client.post(
            "/runs",
            json={
                "app_name": "Test App",
                "stores": ["playstore"],
                "play_package": "com.test.app",
                "country": "uk",
            },
        )
        assert resp.status_code == 422

    def test_get_nonexistent_run_404(self):
        resp = client.get("/runs/non_existent_run_id_999")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["error"]["code"] == "RUN_NOT_FOUND"

    def test_list_runs_returns_list(self):
        resp = client.get("/runs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
