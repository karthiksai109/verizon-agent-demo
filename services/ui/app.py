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

tab_chat, tab_metrics, tab_arch, tab_story, tab_whiteboard, tab_resume = st.tabs(["💬 Chat + Trace", "📊 Metrics", "🏗 Architecture", "� Story walkthrough", "✏️ Whiteboard drill", "�📄 Resume claims map"])


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

with tab_story:
    st.subheader("Inbox → answer: one message's journey (the recitable story)")
    st.markdown("Customer types **\u201cmy internet is down in 75024\u201d** — follow the journey:")
    dot_story = """
    digraph S {
      rankdir=TB; node [shape=box, style="rounded,filled", fillcolor="#f6f8fa"];
      M1 [label="1 · Message arrives\nAPI layer (Lambda/API GW)", fillcolor="#fff3cd"];
      M2 [label="2 · Session & memory\nDynamoDB: load past turns\n(Bedrock remembers NOTHING)"];
      M3 [label="3 · Router assigns agent\nscore all 6 → threshold → stickiness\nnetwork 0.41 wins", fillcolor="#d1ecf1"];
      M4 [label="4 · Network agent's tools\ncheck_outage(\"75024\")\nmodel proposes, code disposes"];
      M5 [label="5 · Scoped RAG\nnetwork policy index only\ntop-3 chunks + scores"];
      M6 [label="6 · Abstention gate\nweak retrieval? → refuse, don't invent"];
      M7 [label="7 · One Bedrock Converse call\nreturns answer + token usage + latency"];
      M8 [label="8 · Persist + telemetry\nsave turn, log cost/tokens/confidence", fillcolor="#d4edda"];
      M1 -> M2 -> M3 -> M4 -> M5 -> M6 -> M7 -> M8;
      M3 -> G [label="all scores < threshold"];
      G [label="Generalist asks ONE\nclarifying question", fillcolor="#f8d7da"];
    }
    """
    st.graphviz_chart(dot_story)
    st.markdown("""**Trust chain (how you know the answer is right):**
- **Citations** — every claim carrys [ref] you can expand to the policy text
- **Tools for facts** — balances/outages come from API calls, never model memory
- **Abstain > hallucinate** — below threshold it says 'I don't know' and escalates
- **Telemetry** — every call logs tokens/latency/cost/confidence; 👍/👎 feeds evals

**తెలుగులో:** Message → memory load → router score చేసి agent ఇస్తుంది → tools run → scoped docs retrieve → confidence తక్కువైతే refuse → OK అయితే ఒక Bedrock call → metrics log. ఈ వరుసే interview లో చెప్పాలి.""")

with tab_whiteboard:
    st.subheader("Draw this on the interview whiteboard in ~90 seconds")
    st.markdown("Practice until you can draw this **unaided, in this order, while narrating**:")
    st.code("""
[CUSTOMER]
     │ ① types question
     ▼
[ROUTER] ② scores all 6 agents, threshold, stickiness
     │ low conf ──► [GENERALIST: clarify]
     ▼
┌──── 6 SPECIALIST AGENTS ────┐   ③ routing = code + scores, not vibes
│ Billing │ Network │ Plans   │
│ Device  │ Onboarding│ ...   │   each = prompt + tools + OWN policy index
└──┬───────────┬─────────────┘
   ▼ ④ tools   ▼ ⑤ scoped RAG
[APIs/DB]   [vector store]
   └────┬──────┘
        ▼ ⑥ assemble: system + history(DynamoDB↔store) + chunks
 [AMAZON BEDROCK — Claude]  ⑦ ONE stateless call → answer+tokens+latency
        ▼
 [Telemetry: Datadog/QuickSight]  ⑧ cost + trust per call
        ▼
 [CUSTOMER: cited, grounded answer]
""", language=None)
    c1, c2 = st.columns(2)
    c1.markdown("""**Drawing script (order matters):**
1. Customer box, arrow down
2. Router box + side arrow to clarify box
3. One wide box, divide into 6 cells (name 3 only, say 'and so on')
4. Two arrows down: tools (left), policy index (right)
5. Merging arrow into Bedrock box; label it **stateless**
6. Small arrow sideways: DynamoDB with label 'we resend history'
7. Down arrow out: telemetry box, label tokens/latency/cost
8. Final arrow to customer, label 'cited answer ~1-2s'
""")
    c2.markdown("""**Say while drawing (the killer lines):**
- *\u201CThe model proposes, code disposes — tools never run inside the model.\u201D*
- *\u201CBedrock is stateless; memory is our store re-sent each call.\u201D*
- *\u201CBelow the routing threshold we clarify — misrouting is worse than an extra turn.\u201D*
- *\u201CWeak retrieval triggers abstention: no call, no cost, no hallucination.\u201D*
- *\u201CEvery call logs tokens and latency — that's per-agent spend attribution.\u201D*

**Time-check:** steps 1–3 by 20s, full diagram by 60s, then narrate trust chain 30s.
""")
    st.info("Drill: draw it on paper 3× today, 1× tomorrow morning. Day of interview: once in the waiting room.")

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
