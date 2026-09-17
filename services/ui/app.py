import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8011")

st.set_page_config(page_title="Verizon 6-Agent Platform (demo)", page_icon="🛰️", layout="wide")
st.title("Verizon 6-Agent Platform — Local Demo")
st.caption("Simulated replica: every resume claim is visible in the right-hand Trace panel after each message.")

if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "chat" not in st.session_state:
    st.session_state.chat = []
if "last_trace" not in st.session_state:
    st.session_state.last_trace = None

with st.sidebar:
    st.header("Session")
    st.write("Session:", st.session_state.session_id or "(new)")
    if st.button("New conversation"):
        st.session_state.session_id = None
        st.session_state.chat = []
        st.session_state.last_trace = None
    st.markdown("---")
    st.header("Try these")
    st.code("why is my bill so high this month", language=None)
    st.code("my internet is down in 75024", language=None)
    st.code("compare unlimited plans which is cheaper", language=None)
    st.code("my phone screen is frozen", language=None)
    st.code("something something quantum banana", language=None)
    st.caption("Last one = off-domain → watch the abstention gate refuse instead of hallucinating.")

tab_chat, tab_metrics, tab_arch, tab_resume = st.tabs(["💬 Chat + Trace", "📊 Metrics", "🏗 Architecture", "📄 Resume claims map"])


def render_trace(trace: dict, resp: dict):
    st.subheader("What just happened (the interview walkthrough, live)")
    cols = st.columns(5)
    cols[0].metric("Agent", resp["agent_title"].replace(" Agent", ""))
    cols[1].metric("Router confidence", f"{resp['confidence']:.3f}")
    cols[2].metric("Tokens in/out", f"{resp['bedrock']['usage']['inputTokens']} / {resp['bedrock']['usage']['outputTokens']}")
    cols[3].metric("Latency", f"{resp['total_latency_ms']} ms")
    cols[4].metric("Est. call cost", f"${resp['bedrock'].get('cost_estimate_usd', 0) or 0:.5f}")
    for step in trace["steps"]:
        with st.expander(f"Step {step['n']}: {step['name']}", expanded=step["n"] in (2, 7)):
            st.write(step["detail"])
            if "scores" in step:
                st.bar_chart(step["scores"])
            if step.get("calls"):
                for c in step["calls"]:
                    st.code(f"{c['tool']} → {c['result']}", language="json")
            if step.get("hits"):
                for h in step["hits"]:
                    st.caption(f"[{h['source']} > {h['heading']}] score {h['score']}: {h['text']}…")
            st.info("తెలుగులో: " + step["te"])


with tab_chat:
    col_chat, col_trace = st.columns([1, 1])
    with col_chat:
        st.subheader("Customer chat")
        for m in st.session_state.chat:
            with st.chat_message(m["role"]):
                st.write(m["content"])
                if m["role"] == "assistant" and m.get("citations"):
                    st.caption("Sources: " + "; ".join(f"[{c['ref']}] {c['source']} > {c['heading']}" for c in m["citations"]))
                if m["role"] == "assistant" and m.get("event_id") is not None:
                    c1, c2 = st.columns(2)
                    if c1.button("👍 correct", key=f"up{m['event_id']}"):
                        requests.post(f"{API_URL}/feedback", json={"event_id": m["event_id"], "rating": 1})
                        st.toast("Feedback logged — these become eval cases")
                    if c2.button("👎 wrong", key=f"dn{m['event_id']}"):
                        requests.post(f"{API_URL}/feedback", json={"event_id": m["event_id"], "rating": 0})
                        st.toast("Feedback logged — this is how eval sets grow")
        if prompt := st.chat_input("Type a customer message…"):
            st.session_state.chat.append({"role": "user", "content": prompt})
            r = requests.post(f"{API_URL}/chat", json={"text": prompt, "session_id": st.session_state.session_id})
            if r.status_code == 200:
                resp = r.json()
                st.session_state.session_id = resp["session_id"]
                st.session_state.chat.append({
                    "role": "assistant", "content": resp["answer"],
                    "citations": resp["citations"], "event_id": resp["event_id"],
                })
                st.session_state.last_trace = resp
            st.rerun()
    with col_trace:
        if st.session_state.last_trace:
            render_trace(st.session_state.last_trace["trace"], st.session_state.last_trace)
        else:
            st.info("Send a message — every internal step appears here.")

with tab_metrics:
    st.subheader("Telemetry per call (≈ Datadog RUM + QuickSight in prod)")
    try:
        m = requests.get(f"{API_URL}/metrics").json()
        c = st.columns(4)
        c[0].metric("Total requests", m["total_requests"])
        c[1].metric("p50 / p95 latency", f"{m['latency_ms']['p50']} / {m['latency_ms']['p95']} ms")
        c[2].metric("Tokens in / out", f"{m['tokens']['in']} / {m['tokens']['out']}")
        c[3].metric("Total est. cost", f"${m['total_cost_usd']}")
        c2 = st.columns(3)
        c2[0].metric("Avg router confidence", f"{m['avg_confidence']:.3f}")
        c2[1].metric("Abstention rate", f"{m['abstention_rate']*100:.1f}%")
        c2[2].metric("Feedback 👍 / 👎", f"{m['feedback']['up']} / {m['feedback']['down']}")
        if m["by_agent"]:
            st.write("Requests per agent")
            st.bar_chart(m["by_agent"])
    except Exception as e:
        st.error(f"metrics unavailable: {e}")

with tab_arch:
    st.subheader("Production architecture → local demo mapping")
    dot = """
    digraph G {
      rankdir=LR;
      node [shape=box, style=rounded];
      Customer -> "Chat UI (React/Next → here: Streamlit)";
      "Chat UI" -> "API Gateway → Lambda (here: FastAPI)";
      "API Gateway → Lambda" -> Router;
      Router -> Billing; Router -> Network; Router -> Plans; Router -> Device; Router -> Onboarding; Router -> Generalist;
      Billing -> "Scoped index (OpenSearch; here TF-IDF)";
      Network -> "Scoped index"; Plans -> "Scoped index"; Device -> "Scoped index"; Onboarding -> "Scoped index"; Generalist -> "Scoped index";
      Billing -> "Tools (account APIs)";
      Network -> "Tools (outage APIs)";
      "Scoped index" -> "Amazon Bedrock Converse (here: simulated)";
      "Tools (account APIs)" -> "Amazon Bedrock Converse";
      "Session store DynamoDB (here: SQLite)" -> Router;
      "Amazon Bedrock Converse" -> "Telemetry: Datadog/RUM, QuickSight (here: events table + Metrics tab)";
    }
    """
    st.graphviz_chart(dot)
    st.markdown("""
**Swap points (what changes in real deployment):**
- `mock_bedrock.py` → `boto3.client('bedrock-runtime').converse(...)` — identical request/response shape
- `services/engine/sessions.py` SQLite → DynamoDB tables (`sessions`, `messages`), TTL on sessions
- TF-IDF `VectorIndex` → Elasticsearch/OpenSearch + Titan embeddings (same `search()` interface)
- FastAPI container → Lambda handlers behind API Gateway (serverless, spiky chat traffic)
- SQLite `events` → Datadog RUM metrics; this Metrics tab → QuickSight dataset for exec KPIs
""")

with tab_resume:
    st.subheader("Every resume bullet → where to show it live")
    rows = [
        ("6 specialized agents + prompt engineering for cross-agent query routing",
         "services/engine/agents.py (6 scoped prompts) + router.py (scores/threshold/stickiness)",
         "Send 'my internet is down' then 'why is my bill high' — watch Step 2 scores switch agents."),
        ("AWS Bedrock via AWS SDK for AI reasoning with latency, token-usage, metadata tracking",
         "mock_bedrock.py returns usage/metrics blocks identical to real Converse API; sessions.log_event stores them",
         "Step 7 of any trace: modelId, input/output tokens, latencyMs, est. cost."),
        ("Serverless Python backend: Lambda + DynamoDB event-driven workflows",
         "This demo's FastAPI handlers are 1:1 Lambda handler bodies; SQLite schema maps to DynamoDB tables shown in Architecture tab",
         "Show data/demo.db after chatting; paste mapping table."),
        ("Executive dashboards (QuickSight) for KPIs, usage trends, performance",
         "Metrics tab computes p50/p95, per-agent volume, cost, abstention rate from the same events table QuickSight would read",
         "Chat ~10 times (mix domains + one nonsense query) then open Metrics tab."),
        ("Monitoring with Datadog RUM, Grafana, Kibana — AI latency, API performance, error rates",
         "Every request logs tokens/latency/cost/confidence events; thumbs up/down = feedback ingestion",
         "The five chips at top of Trace panel mirror RUM spans."),
        ("TDD + code quality gates across SDLC",
         "pytest suite covers router, retrieval, sessions, abstention, API; GitHub Actions CI runs it on push",
         "Run `pytest -q` in front of them — 15 green tests."),
    ]
    for claim, where, demo in rows:
        st.markdown(f"**Claim:** {claim}")
        st.markdown(f"- **Code:** `{where}`")
        st.markdown(f"- **Live demo:** {demo}")
        st.markdown("---")
