import os
import tempfile

os.environ["DEMO_DB"] = os.path.join(tempfile.mkdtemp(), "test_api.db")

from fastapi.testclient import TestClient

from services.api.main import app


def test_health():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_chat_endpoint_returns_trace():
    with TestClient(app) as client:
        r = client.post("/chat", json={"text": "compare unlimited plans please"})
        assert r.status_code == 200
        body = r.json()
        assert body["agent"] == "plans"
        assert len(body["trace"]["steps"]) == 8
        assert body["bedrock"]["usage"]["outputTokens"] > 0
        assert body["citations"]


def test_chat_session_persists():
    with TestClient(app) as client:
        r1 = client.post("/chat", json={"text": "my esim is not activating"}).json()
        r2 = client.post("/chat", json={"text": "how do i transfer it", "session_id": r1["session_id"]}).json()
        assert r2["session_id"] == r1["session_id"]


def test_metrics_and_feedback():
    with TestClient(app) as client:
        chat = client.post("/chat", json={"text": "port my number from another carrier"}).json()
        f = client.post("/feedback", json={"event_id": chat["event_id"], "rating": 1})
        assert f.status_code == 200
        m = client.get("/metrics").json()
        assert m["total_requests"] >= 1
        assert m["feedback"]["up"] >= 1


def test_history_endpoint():
    with TestClient(app) as client:
        c = client.post("/chat", json={"text": "why is my first bill so high"}).json()
        h = client.get(f"/history/{c['session_id']}").json()
        assert len(h["messages"]) >= 2
