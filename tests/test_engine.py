import os
import tempfile

os.environ["DEMO_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from services.engine import sessions
from services.engine.mock_bedrock import BedrockConverse, estimate_tokens
from services.engine.pipeline import Platform
from services.engine.retriever import VectorIndex, load_agent_chunks
from services.engine.router import Router


def test_router_picks_billing():
    r = Router()
    d = r.score("why is my bill so high this month")
    assert d["picked"] == "billing"
    assert d["confidence"] > 0.1


def test_router_picks_network():
    r = Router()
    assert r.score("my internet is down, no service")["picked"] == "network"


def test_router_clarifies_on_garbage():
    r = Router()
    d = r.score("xyzzy quantum banana")
    assert d["clarify"] is True
    assert d["picked"] == "generalist"


def test_router_stickiness_keeps_last_agent():
    r = Router()
    first = r.score("dispute a charge on my bill and set up a payment arrangement")
    assert first["picked"] == "billing"
    followup = r.score("can i pay half now?", last_agent="billing")
    assert followup["sticky_note"] is not None or followup["picked"] == "billing"


def test_retriever_scoped_per_agent():
    idx = VectorIndex(load_agent_chunks("device_setup.md", "device"))
    hits = idx.search("battery swelling what do i do", k=1)
    assert hits[0][0].heading == "Common device issues"


def test_bedrock_response_shape_matches_converse():
    b = BedrockConverse(seed=1)
    resp = b.converse(system="s", messages=[{"role": "user", "content": "Customer message: hi\n\n## Retrieved policy context (cite as [1], [2])\n[1] Bills are generated on cycle date. They cover the upcoming month."}], persona="billing")
    assert resp["output"]["message"]["content"][0]["text"]
    assert resp["usage"]["inputTokens"] > 0
    assert resp["usage"]["outputTokens"] > 0
    assert resp["metrics"]["latencyMs"] > 0
    assert resp["usage"]["totalTokens"] == resp["usage"]["inputTokens"] + resp["usage"]["outputTokens"]


def test_bedrock_is_stateless_between_calls():
    b = BedrockConverse(seed=1)
    b.converse(system="", messages=[{"role": "user", "content": "Customer message: remember number forty two"}], persona="generalist")
    r2 = b.converse(system="", messages=[{"role": "user", "content": "Customer message: what number did I say"}], persona="generalist")
    assert "42" not in r2["output"]["message"]["content"][0]["text"]


def test_estimated_tokens():
    assert estimate_tokens("one two three four") == 5
    assert estimate_tokens("") == 1


def test_session_memory_replay_and_budget():
    conn = sessions.connect()
    ses = sessions.get_or_create_session(conn, None)
    sid = ses["session_id"]
    sessions.save_message(conn, sid, "user", "remember my zip 75024")
    sessions.save_message(conn, sid, "assistant", "noted 75024")
    hist = sessions.load_history(conn, sid)
    assert len(hist) == 2 and hist[0]["content"].startswith("remember")
    conn.close()


def test_pipeline_routes_and_logs_event():
    p = Platform()
    resp = p.chat("dispute a charge on my bill please")
    assert resp["agent"] == "billing"
    assert resp["event_id"] > 0
    assert len(resp["trace"]["steps"]) == 8
    conn = sessions.connect()
    m = sessions.metrics_summary(conn)
    assert m["total_requests"] >= 1
    conn.close()


def test_pipeline_conversation_memory_across_turns():
    p = Platform()
    r1 = p.chat("my internet is down in 75024")
    r2 = p.chat("and what about my bill too", r1["session_id"])
    assert r1["agent"] == "network"
    assert r2["session_id"] == r1["session_id"]


def test_pipeline_abstains_off_domain():
    p = Platform()
    resp = p.chat("tell me about quantum banana therapy")
    assert resp["abstained"] is True
    assert "don't have enough" in resp["answer"]
