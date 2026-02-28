"""
Unit tests — FastAPI agent service (routes, models, config).
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Force LOCAL_MODE before importing anything
os.environ["LOCAL_MODE"] = "true"

from fastapi.testclient import TestClient
from agent.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_ok(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert isinstance(body["local_mode"], bool)
        assert "model" in body

    def test_health_reports_local_mode(self):
        resp = client.get("/api/health")
        assert resp.json()["local_mode"] is True


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

class TestChat:
    def test_chat_requires_message(self):
        resp = client.post("/api/chat", json={})
        assert resp.status_code == 422  # validation error

    def test_chat_empty_message_rejected(self):
        resp = client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 422

    def test_chat_returns_answer(self):
        resp = client.post("/api/chat", json={"message": "hello"})
        assert resp.status_code == 200
        body = resp.json()
        assert "answer" in body
        assert isinstance(body["answer"], str)
        assert "tool_calls" in body


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_overview(self):
        resp = client.get("/api/dashboard/overview")
        assert resp.status_code == 200
        body = resp.json()
        for key in ("forecast", "top_combos", "expansion_ranking",
                     "staffing_summary", "growth_ranking"):
            assert key in body

    def test_forecast(self):
        resp = client.get("/api/dashboard/forecast")
        assert resp.status_code == 200
        assert resp.json()["feature"] == "forecast"

    def test_combo(self):
        resp = client.get("/api/dashboard/combo")
        assert resp.status_code == 200
        assert resp.json()["feature"] == "combo"

    def test_expansion(self):
        resp = client.get("/api/dashboard/expansion")
        assert resp.status_code == 200
        assert resp.json()["feature"] == "expansion"

    def test_staffing(self):
        resp = client.get("/api/dashboard/staffing")
        assert resp.status_code == 200
        assert resp.json()["feature"] == "staffing"

    def test_growth(self):
        resp = client.get("/api/dashboard/growth")
        assert resp.status_code == 200
        assert resp.json()["feature"] == "growth"


# ---------------------------------------------------------------------------
# Upload endpoints (LOCAL_MODE → 400)
# ---------------------------------------------------------------------------

class TestUpload:
    def test_presign_blocked_in_local_mode(self):
        resp = client.post("/api/upload/presign", json={"filename": "test.csv"})
        assert resp.status_code == 400

    def test_trigger_blocked_in_local_mode(self):
        resp = client.post("/api/upload/trigger", json={"s3_key": ""})
        assert resp.status_code == 400

    def test_status_blocked_in_local_mode(self):
        resp = client.post("/api/upload/status",
                           json={"execution_arn": "arn:aws:states:eu-west-1:123:test"})
        assert resp.status_code == 400

    def test_prepare_blocked_in_local_mode(self):
        resp = client.post("/api/upload/prepare")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TestModels:
    def test_chat_request_validation(self):
        from agent.models import ChatRequest
        req = ChatRequest(message="test")
        assert req.message == "test"

    def test_chat_request_max_length(self):
        from agent.models import ChatRequest
        with pytest.raises(Exception):
            ChatRequest(message="x" * 2001)

    def test_dashboard_section(self):
        from agent.models import DashboardSection
        s = DashboardSection(feature="test", data={"a": 1})
        assert s.feature == "test"

    def test_tool_call_info(self):
        from agent.models import ToolCallInfo
        tc = ToolCallInfo(tool="my_tool", input={"k": "v"}, output_preview="ok")
        assert tc.tool == "my_tool"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_table_names_follow_convention(self):
        from agent import config
        assert "forecast" in config.FORECAST_TABLE
        assert "combo" in config.COMBO_TABLE
        assert "expansion" in config.EXPANSION_TABLE
        assert "staffing" in config.STAFFING_TABLE
        assert "growth" in config.GROWTH_TABLE

    def test_s3_bucket_name(self):
        from agent import config
        assert "conut-ops" in config.S3_DATA_BUCKET

    def test_bedrock_defaults(self):
        from agent import config
        assert config.BEDROCK_MAX_TOKENS > 0
        assert 0 <= config.BEDROCK_TEMPERATURE <= 1.0
