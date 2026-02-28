"""
OpsClaw Test Endpoint — FastAPI echo stub.

Verifies OpenClaw → local endpoint connectivity before the real agent is wired.

Usage:
    uvicorn openclaw.test_endpoint.test_endpoint:app --host 0.0.0.0 --port 8000
"""

from datetime import datetime, timezone
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="OpsClaw Test Endpoint")


class QueryRequest(BaseModel):
    message: str
    user_id: str = "anonymous"


@app.get("/health")
def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/query")
def query(req: QueryRequest):
    return {
        "text": f"Test endpoint connected ✅ You said: {req.message}",
        "user_id": req.user_id,
    }
