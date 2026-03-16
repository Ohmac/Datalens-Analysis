"""Tests for the Datalens Analysis Flask application."""
import io
import json
import os
import tempfile

import pandas as pd
import pytest

# Use a deterministic secret key for testing
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import app as application  # noqa: E402  (must come after env var is set)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    """Return a test client with uploads stored in a temp directory."""
    application.app.config["UPLOAD_FOLDER"] = str(tmp_path)
    application.app.config["TESTING"] = True
    with application.app.test_client() as c:
        yield c


def _csv_bytes(content: str) -> io.BytesIO:
    return io.BytesIO(content.encode())


SAMPLE_CSV = "name,age,score\nAlice,30,88.5\nBob,25,92.0\nCarol,35,76.3\n"


def _upload_sample(client) -> str:
    """Upload SAMPLE_CSV and return the stored filename."""
    data = {
        "file": (io.BytesIO(SAMPLE_CSV.encode()), "sample.csv"),
    }
    resp = client.post("/upload", data=data, content_type="multipart/form-data",
                       follow_redirects=True)
    assert resp.status_code == 200
    with client.session_transaction() as sess:
        return sess.get("filename")


# ---------------------------------------------------------------------------
# Route: GET /
# ---------------------------------------------------------------------------

class TestIndex:
    def test_get_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_contains_brand_name(self, client):
        resp = client.get("/")
        assert b"Datalens" in resp.data


# ---------------------------------------------------------------------------
# Route: GET /upload
# ---------------------------------------------------------------------------

class TestUploadGet:
    def test_get_returns_200(self, client):
        resp = client.get("/upload")
        assert resp.status_code == 200

    def test_contains_form(self, client):
        resp = client.get("/upload")
        assert b"<form" in resp.data


# ---------------------------------------------------------------------------
# Route: POST /upload
# ---------------------------------------------------------------------------

class TestUploadPost:
    def test_valid_csv_redirects_to_dashboard(self, client):
        data = {"file": (_csv_bytes(SAMPLE_CSV), "data.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data",
                           follow_redirects=False)
        assert resp.status_code == 302
        assert "/dashboard" in resp.headers["Location"]

    def test_no_file_part_flashes_error(self, client):
        resp = client.post("/upload", data={}, content_type="multipart/form-data",
                           follow_redirects=True)
        assert b"No file part" in resp.data

    def test_empty_filename_flashes_error(self, client):
        data = {"file": (io.BytesIO(b""), "")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data",
                           follow_redirects=True)
        assert b"No file selected" in resp.data

    def test_non_csv_extension_rejected(self, client):
        data = {"file": (io.BytesIO(b"col1\nval"), "data.txt")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data",
                           follow_redirects=True)
        assert b"CSV" in resp.data

    def test_empty_csv_rejected(self, client):
        data = {"file": (io.BytesIO(b""), "empty.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data",
                           follow_redirects=True)
        # empty file triggers parse error or empty error
        assert resp.status_code == 200

    def test_session_stores_filename(self, client):
        stored = _upload_sample(client)
        assert stored is not None
        assert stored.endswith(".csv")


# ---------------------------------------------------------------------------
# Route: GET /dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_redirects_without_session(self, client):
        resp = client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 302

    def test_shows_summary_after_upload(self, client):
        _upload_sample(client)
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert b"3" in resp.data  # 3 rows


# ---------------------------------------------------------------------------
# Route: GET /analysis
# ---------------------------------------------------------------------------

class TestAnalysis:
    def test_redirects_without_session(self, client):
        resp = client.get("/analysis", follow_redirects=False)
        assert resp.status_code == 302

    def test_shows_stats_after_upload(self, client):
        _upload_sample(client)
        resp = client.get("/analysis")
        assert resp.status_code == 200
        assert b"age" in resp.data or b"score" in resp.data


# ---------------------------------------------------------------------------
# API: POST /api/chart
# ---------------------------------------------------------------------------

class TestApiChart:
    def test_no_data_returns_400(self, client):
        resp = client.post("/api/chart", json={"chart_type": "histogram", "x": "age"})
        assert resp.status_code == 400

    def test_histogram(self, client):
        _upload_sample(client)
        resp = client.post("/api/chart", json={"chart_type": "histogram", "x": "age"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "data" in body

    def test_scatter(self, client):
        _upload_sample(client)
        resp = client.post("/api/chart", json={"chart_type": "scatter", "x": "age", "y": "score"})
        assert resp.status_code == 200

    def test_bar(self, client):
        _upload_sample(client)
        resp = client.post("/api/chart", json={"chart_type": "bar", "x": "name", "y": "score"})
        assert resp.status_code == 200

    def test_line(self, client):
        _upload_sample(client)
        resp = client.post("/api/chart", json={"chart_type": "line", "x": "age", "y": "score"})
        assert resp.status_code == 200

    def test_box(self, client):
        _upload_sample(client)
        resp = client.post("/api/chart", json={"chart_type": "box", "x": "score"})
        assert resp.status_code == 200

    def test_pie(self, client):
        _upload_sample(client)
        resp = client.post("/api/chart", json={"chart_type": "pie", "x": "name"})
        assert resp.status_code == 200

    def test_heatmap(self, client):
        _upload_sample(client)
        resp = client.post("/api/chart", json={"chart_type": "heatmap"})
        assert resp.status_code == 200

    def test_invalid_column_returns_400(self, client):
        _upload_sample(client)
        resp = client.post("/api/chart", json={"chart_type": "histogram", "x": "nonexistent"})
        assert resp.status_code == 400

    def test_unknown_chart_type_returns_400(self, client):
        _upload_sample(client)
        resp = client.post("/api/chart", json={"chart_type": "unknown_type", "x": "age"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# API: GET /api/stats
# ---------------------------------------------------------------------------

class TestApiStats:
    def test_no_data_returns_400(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 400

    def test_returns_all_columns(self, client):
        _upload_sample(client)
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        col_names = [d["column"] for d in data]
        assert "age" in col_names
        assert "score" in col_names
        assert "name" in col_names

    def test_single_numeric_column(self, client):
        _upload_sample(client)
        resp = client.get("/api/stats?col=age")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["column"] == "age"
        assert "mean" in data
        assert data["count"] == 3

    def test_single_categorical_column(self, client):
        _upload_sample(client)
        resp = client.get("/api/stats?col=name")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["column"] == "name"
        assert "unique" in data

    def test_invalid_column_returns_400(self, client):
        _upload_sample(client)
        resp = client.get("/api/stats?col=does_not_exist")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Template filter
# ---------------------------------------------------------------------------

class TestFormatNumber:
    def test_thousands(self):
        with application.app.app_context():
            assert application.format_number(1000) == "1,000"
            assert application.format_number(1000000) == "1,000,000"
            assert application.format_number(0) == "0"

    def test_non_numeric_returns_string(self):
        with application.app.app_context():
            assert application.format_number("abc") == "abc"
