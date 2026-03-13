"""
Unit tests — FastAPI agent service (routes, models, config).
"""

import os
import sys
from pathlib import Path

import httpx
import pytest
from botocore.exceptions import ClientError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Force LOCAL_MODE before importing anything
os.environ["LOCAL_MODE"] = "true"

from agent.main import app

pytestmark = pytest.mark.anyio


@pytest.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.fixture
async def remote_async_client():
    transport = httpx.ASGITransport(app=app, client=("203.0.113.10", 12345))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealth:
    async def test_health_returns_ok(self, async_client):
        resp = await async_client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert isinstance(body["local_mode"], bool)
        assert "model" in body

    async def test_health_reports_local_mode(self, async_client):
        resp = await async_client.get("/api/health")
        assert resp.json()["local_mode"] is True

    async def test_local_mode_bypasses_origin_guard(self, async_client):
        resp = await async_client.get("/api/health")
        assert resp.status_code == 200

    async def test_cloud_mode_rejects_missing_origin_header(self, monkeypatch, remote_async_client):
        from agent import config

        monkeypatch.setattr(config, "LOCAL_MODE", False)
        monkeypatch.setattr(config, "ORIGIN_VERIFY_HEADER_VALUE", "test-secret")

        resp = await remote_async_client.get("/api/health")
        assert resp.status_code == 403

    async def test_cloud_mode_accepts_valid_origin_header(self, monkeypatch, remote_async_client):
        from agent import config

        monkeypatch.setattr(config, "LOCAL_MODE", False)
        monkeypatch.setattr(config, "ORIGIN_VERIFY_HEADER_NAME", "X-Origin-Verify")
        monkeypatch.setattr(config, "ORIGIN_VERIFY_HEADER_VALUE", "test-secret")

        resp = await remote_async_client.get(
            "/api/health",
            headers={"X-Origin-Verify": "test-secret"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

class TestChat:
    async def test_chat_requires_message(self, async_client):
        resp = await async_client.post("/api/chat", json={})
        assert resp.status_code == 422  # validation error

    async def test_chat_empty_message_rejected(self, async_client):
        resp = await async_client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 422

    async def test_chat_returns_answer(self, async_client):
        resp = await async_client.post("/api/chat", json={"message": "hello"})
        assert resp.status_code == 200
        body = resp.json()
        assert "answer" in body
        assert isinstance(body["answer"], str)
        assert "tool_calls" in body


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------

class TestDashboard:
    async def test_overview(self, async_client):
        resp = await async_client.get("/api/dashboard/overview")
        assert resp.status_code == 200
        body = resp.json()
        for key in ("forecast", "top_combos", "expansion_ranking",
                     "staffing_summary", "growth_ranking"):
            assert key in body

    async def test_forecast(self, async_client):
        resp = await async_client.get("/api/dashboard/forecast")
        assert resp.status_code == 200
        assert resp.json()["feature"] == "forecast"

    async def test_combo(self, async_client):
        resp = await async_client.get("/api/dashboard/combo")
        assert resp.status_code == 200
        assert resp.json()["feature"] == "combo"

    async def test_expansion(self, async_client):
        resp = await async_client.get("/api/dashboard/expansion")
        assert resp.status_code == 200
        assert resp.json()["feature"] == "expansion"

    async def test_staffing(self, async_client):
        resp = await async_client.get("/api/dashboard/staffing")
        assert resp.status_code == 200
        assert resp.json()["feature"] == "staffing"

    async def test_growth(self, async_client):
        resp = await async_client.get("/api/dashboard/growth")
        assert resp.status_code == 200
        assert resp.json()["feature"] == "growth"


# ---------------------------------------------------------------------------
# Upload endpoints (LOCAL_MODE → 400)
# ---------------------------------------------------------------------------

class TestUpload:
    async def test_presign_blocked_in_local_mode(self, async_client):
        resp = await async_client.post("/api/upload/presign", json={"filename": "test.csv"})
        assert resp.status_code == 400

    async def test_trigger_blocked_in_local_mode(self, async_client):
        resp = await async_client.post("/api/upload/trigger", json={"s3_key": ""})
        assert resp.status_code == 400

    async def test_status_blocked_in_local_mode(self, async_client):
        resp = await async_client.post(
            "/api/upload/status",
            json={"execution_arn": "arn:aws:states:eu-west-1:123:test"},
        )
        assert resp.status_code == 400

    async def test_prepare_blocked_in_local_mode(self, async_client):
        resp = await async_client.post("/api/upload/prepare")
        assert resp.status_code == 400

    async def test_status_returns_execution_state_in_cloud_mode(self, monkeypatch, remote_async_client):
        from agent import config
        from agent.routes import upload

        class FakeSfn:
            def describe_execution(self, executionArn):
                assert executionArn.endswith(":upload-1")
                from datetime import datetime, timezone

                return {
                    "executionArn": executionArn,
                    "status": "SUCCEEDED",
                    "startDate": datetime.now(timezone.utc),
                    "stopDate": datetime.now(timezone.utc),
                }

        monkeypatch.setattr(config, "LOCAL_MODE", False)
        monkeypatch.setattr(config, "ORIGIN_VERIFY_HEADER_NAME", "X-Origin-Verify")
        monkeypatch.setattr(config, "ORIGIN_VERIFY_HEADER_VALUE", "test-secret")
        monkeypatch.setattr(upload, "_sfn", lambda: FakeSfn())

        resp = await remote_async_client.post(
            "/api/upload/status",
            json={"execution_arn": "arn:aws:states:eu-west-1:123:execution:conut-ops-pipeline-dev:upload-1"},
            headers={"X-Origin-Verify": "test-secret"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "SUCCEEDED"

    async def test_status_maps_stepfunctions_access_denied(self, monkeypatch, remote_async_client):
        from agent import config
        from agent.routes import upload

        class FakeSfn:
            def describe_execution(self, executionArn):
                raise ClientError(
                    {
                        "Error": {
                            "Code": "AccessDeniedException",
                            "Message": "not allowed",
                        }
                    },
                    "DescribeExecution",
                )

        monkeypatch.setattr(config, "LOCAL_MODE", False)
        monkeypatch.setattr(config, "ORIGIN_VERIFY_HEADER_NAME", "X-Origin-Verify")
        monkeypatch.setattr(config, "ORIGIN_VERIFY_HEADER_VALUE", "test-secret")
        monkeypatch.setattr(upload, "_sfn", lambda: FakeSfn())

        resp = await remote_async_client.post(
            "/api/upload/status",
            json={"execution_arn": "arn:aws:states:eu-west-1:123:execution:conut-ops-pipeline-dev:upload-1"},
            headers={"X-Origin-Verify": "test-secret"},
        )
        assert resp.status_code == 502


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
