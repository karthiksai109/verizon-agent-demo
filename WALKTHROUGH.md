# WALKTHROUGH — What Is Actually Happening, Step by Step

This document answers, in order:
1. What happens when you type a prompt (interface walkthrough)
2. What an agent IS
3. How agents get assigned
4. How agents get responses from Bedrock
5. How YOU know if an answer is right or wrong
6. How Bedrock models were actually trained
7. Every resume claim on this project → proof

Read this once slowly alongside the running demo (Chat + Trace tab). Then you will never need to "battify" (memorize) answers — you will be explaining something you can see.

---

## 1. What happens when you type a prompt (trace of one message)

Type **"my internet is down in 75024"** in the chat. The right panel shows these exact steps executing:

```
Step 1  Session & memory     → services/engine/sessions.py
Step 2  Intent routing        → services/engine/router.py
Step 3  Tool execution        → services/engine/tools.py
Step 4  Retrieval (scoped RAG)→ services/engine/retriever.py
Step 5  Abstention gate       → services/engine/pipeline.py
Step 6  Context assembly      → services/engine/pipeline.py
Step 7  Bedrock Converse call → services/engine/mock_bedrock.py
Step 8  Persist + telemetry   → services/engine/sessions.py
```

Follow it live:
- Message arrives → session opened (or reused), past turns loaded **because Bedrock itself remembers nothing**.
- **Router** scores the message against all 6 agents' example utterances. "internet is down" matches the network examples strongest → bar chart shows network winning. Confidence displayed (say, 0.31). Threshold ≈ 0.18 → proceed.
- **Tools:** the network agent owns `check_outage` and `run_speed_test`. Your message contains a zip → `check_outage("75024")` executes. *The model did not run this — our Python did. The model only proposes; code disposes.*
- **Retrieval:** the message is searched against the **network agent's own scoped index** (network doc only) → top 3 policy chunks with similarity scores shown.
- **Abstention gate:** top score above ~0.06 → proceed. Below → we *do not call the model at all*; we say "I don't have enough information." Try "quantum banana therapy" to see it refuse.
- **Context assembly:** system prompt + budgeted history + tool results + policy chunks → one big prompt string.
- **Bedrock Converse call:** exactly ONE API call. Response carries `usage` (input/output/total tokens), `metrics` (latencyMs), and we compute estimated cost. **This is the "latency, token-usage, and metadata tracking" bullet on your resume — it is literally these fields.**
- **Persist + telemetry:** turn saved; an `events` row written (agent, confidence, tokens, latency, cost). The Metrics tab reads those rows — that's your QuickSight/Datadog analog.

---

## 2. What IS an agent?

**Agent = model + system prompt + scoped tools + scoped knowledge + memory + a loop.**

Same model serves all six agents (Claude via Bedrock in prod; the simulator here). What makes the billing agent *billing* is not a different model — it is:

| Component | In this demo | In production |
|---|---|---|
| Model | `mock_bedrock.BedrockConverse` | Bedrock `converse()` → Claude 3.5 Sonnet |
| System prompt | `agents.py → AGENTS["billing"]["system_prompt"]` | versioned prompt in repo |
| Tools | `tools.py → TOOL_REGISTRY["billing"]` (allow-list) | Lambda functions behind tool gateway |
| Knowledge | `docs/billing_payments.md` → own TF-IDF index | S3 docs → Titan embeddings → OpenSearch scoped index |
| Memory | `sessions.py` (SQLite) | DynamoDB tables, TTL'd |

The **loop** (ReAct) is: reason → propose tool → observe tool result → answer. Here tools run deterministically before the model call; in prod the model emits a `toolUse` block mid-response and the app executes it and calls back.

## 3. How are agents assigned (the router)

`router.py` scores your message against ~8 example utterances per agent (TF-IDF + cosine; production used a fine-tuned classifier + LLM fallback):

1. **Intent classification** → per-agent scores (visible as the bar chart in Step 2).
2. **Confidence threshold** (0.18): below it → generalist asks a clarifying question. Misrouting a billing question to the device agent is worse than one extra turn.
3. **Session stickiness** (band 0.07): mid-conversation, if the current agent scores within the band of the winner, we KEEP it. A customer mid-bill-dispute shouldn't be bounced by a stray keyword. Try: set context with a billing question, then ask "can I pay half now?" — the sticky note shows in the trace.

Production also layered **cost/latency per agent** (cheap model for simple routes) and **permissions** (only billing holds account tools).

## 4. How do agents get responses from Bedrock?

- Bedrock is a **stateless inference API**. Call shape: `converse(modelId, system, messages, inferenceConfig)`. It remembers **zero** between calls.
- So "the agent knows our conversation" = **we** loaded history from the store and resent it in `messages`. Watch Step 1 and Step 6 count turns and tokens.
- The response object is where your resume's "latency, token-usage, metadata tracking" lives: `usage.inputTokens`, `usage.outputTokens`, `metrics.latencyMs`. We log all of it per call (Step 8) — per-agent cost attribution comes straight from these numbers.
- The LLM is **not** reading loose files; it only sees: system prompt + resent history + tool results + retrieved policy chunks. It is engineered to be **grounded**: its instructions say answer ONLY from the retrieved context and cite [1], [2].

## 5. How do you know the answer is correct or wrong?

Never by vibes. Five mechanisms, all visible in the demo:

1. **Citations** — every claim carries [ref] → expandable source chunk with its similarity score (under each assistant bubble, and in Step 4).
2. **Abstention gate** — weak retrieval → refuse instead of hallucinate. A *lower* abstention rate is a quality metric; a *zero* abstention rate on junk input is a red flag (Metrics tab tracks it).
3. **Deterministic tools** — account data comes from code, not the model's imagination. If the model says a balance, it came from a tool call you can see (Step 3).
4. **Telemetry + feedback** — every call logs confidence/tokens/latency/cost; the UI's 👍/👎 writes ratings. In prod, flagged answers became new golden-set eval cases in CI.
5. **Golden-set evals (prod/CI)** — curated Q→expected-source pairs fail the build on prompt/index regressions, exactly like unit tests (this repo's own pytest suite plays that role).

## 6. How were the Bedrock models trained? (the deep question)

- Claude family is trained by **Anthropic**, not on Verizon/Citi data: (a) **pretraining** — next-token prediction over trillions of public/licensed tokens, which bakes in *parametric knowledge* frozen at a cutoff date; (b) **post-training** — instruction tuning + Constitutional AI/RLHF for helpfulness and safety.
- Consequences that drive the whole architecture:
  - Frozen cutoff → says nothing correct about *your* plans/policies/accounts unless you feed it context per call (**RAG**).
  - Pattern completion → fluent, confident text even when wrong (**hallucination**) → hence citations, thresholds, abstention.
  - Weights fixed → updating knowledge = update the **index**, not the model. That's why re-indexing pipelines and doc versioning exist.
- Bedrock adds the enterprise shell: managed hosting, private endpoints, Guardrails, and usage metadata (the fields we log).

## 7. Resume claims → proof map

| Resume bullet | Where in the code | How to SHOW it |
|---|---|---|
| 6 specialized agents + prompt engineering for cross-agent routing | `agents.py`, `router.py` | Send messages from 3 domains; point at Step 2 bar chart + sticky notes |
| Bedrock via AWS SDK with latency/token/metadata tracking | `mock_bedrock.py` response shape == real Converse; `sessions.log_event` | Step 7 of any trace: modelId, tokens, latencyMs, cost |
| Serverless Python (Lambda + DynamoDB event-driven) | `api/main.py` handlers = Lambda bodies; SQLite schema maps 1:1 to DynamoDB tables | Architecture tab mapping list |
| QuickSight exec dashboards for KPIs | Metrics tab reads the events table QuickSight would read | Chat 10× mixed domains + one junk query → Metrics tab |
| Datadog RUM / Grafana / Kibana monitoring | per-call events with confidence, latency, tokens, cost | top metric chips on the Trace panel |
| TDD, quality gates | `tests/` (17 tests), GitHub Actions CI | run `pytest -q` live |

## 8. Telugu quick glossary (interview English in parens)

- ఏజెంట్ = model + prompt + tools + knowledge + memory (an agent, not a magic box)
- రౌటర్ = intent score + threshold + stickiness (router with confidence threshold)
- కాంటెక్స్ట్ = history + policy chunks + tool data కలిపిన prompt (context assembly)
- హాలుసినేషన్ నియంత్రణ = retrieval threshold + citations + abstain (grounding & abstention)
- మెమరీ = మన స్టోర్ నుంచి ప్రతీ కాల్ లో పంపడం (Bedrock is stateless)
- మెట్రిక్స్ = tokens/latency/cost per call → dashboard (observability)
