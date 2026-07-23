import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_health_endpoint():
    """Test health check endpoint returns 200 OK and valid status json."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "live-cricket-score-api"
    assert data["version"] == "1.0.0"


def test_root_dashboard():
    """Test root endpoint renders HTML dashboard."""
    response = client.get("/?match=12UZ")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "12UZ" in response.text


def test_overlay_endpoint():
    """Test overlay endpoint renders HTML overlay with transparent framing headers."""
    response = client.get("/overlay?match=12UZ&watermark=Chiluveru")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "DEFAULT_MATCH_ID = '12UZ'" in response.text
    # Verify frame embedding security headers for OBS Studio
    assert response.headers.get("x-frame-options") is None
    assert "frame-ancestors *" in response.headers.get("content-security-policy", "")


def test_api_score_text_format():
    """Test api score text query parameter returns plain text format."""
    response = client.get("/api/score?match=127D&text=true")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "Live Score" in response.text


def test_invalid_match_key_error():
    """Test invalid match key throws 422 validation error."""
    response = client.get("/api/score?match=INVALID_KEY_%%%")
    assert response.status_code == 422
    data = response.json()
    assert data["status"] == "error"
    assert data["code"] == 422


def test_404_error_handler():
    """Test non-existent route returns 404 error payload."""
    response = client.get("/non-existent-route")
    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["code"] == 404
    assert data["message"] == "invalid api route"
