"""Session memory + telemetry store.

SQLite locally; in production this maps to:
  sessions  -> DynamoDB table keyed by session_id
  messages  -> DynamoDB table keyed by session_id + sort key ts
  events    -> per-call telemetry rows (what Datadog/CloudWatch ingest in prod)

THE core lesson: Bedrock remembers nothing. Memory = OUR store + resending
the history inside every subsequent call. That second half is what this file
exists to demonstrate.
"""

import os
import sqlite3
import time
import uuid
from pathlib import Path

DB_PATH = os.getenv("DEMO_DB", str(Path(__file__).resolve().parents[2] / "data" / "demo.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(
  session_id TEXT PRIMARY KEY,
  created_at REAL,
  last_agent TEXT
);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  role TEXT,
  content TEXT,
  ts REAL
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  agent TEXT,
  confidence REAL,
  clarified INTEGER,
  abstained INTEGER,
  tokens_in INTEGER,
  tokens_out INTEGER,
  latency_ms REAL,
  cost_usd REAL,
  rating INTEGER,
  ts REAL
);
"""

HISTORY_TOKEN_BUDGET = 1200  # context-window budget for replayed history


def connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def get_or_create_session(conn: sqlite3.Connection, session_id: str | None) -> sqlite3.Row:
    if session_id:
        row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row:
            return row
    sid = session_id or uuid.uuid4().hex[:12]
    conn.execute("INSERT INTO sessions(session_id, created_at, last_agent) VALUES (?,?,?)",
                 (sid, time.time(), None))
    conn.commit()
    return conn.execute("SELECT * FROM sessions WHERE session_id=?", (sid,)).fetchone()


def save_message(conn: sqlite3.Connection, session_id: str, role: str, content: str) -> None:
    conn.execute("INSERT INTO messages(session_id, role, content, ts) VALUES (?,?,?,?)",
                 (session_id, role, content, time.time()))
    conn.commit()


def load_history(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """Replay history with a token budget: newest turns kept, oldest dropped.
    Production equivalent: DynamoDB query + token-budget truncation before the
    Converse call; beyond the budget we would summarize instead of drop."""
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE session_id=? ORDER BY id", (session_id,)
    ).fetchall()
    msgs = [{"role": r["role"], "content": r["content"]} for r in rows]
    kept, budget = [], HISTORY_TOKEN_BUDGET
    from .mock_bedrock import estimate_tokens
    for m in reversed(msgs):  # walk newest -> oldest
        t = estimate_tokens(m["content"])
        if budget - t < 0 and kept:
            break
        budget -= t
        kept.append(m)
    return list(reversed(kept))


def set_last_agent(conn: sqlite3.Connection, session_id: str, agent: str) -> None:
    conn.execute("UPDATE sessions SET last_agent=? WHERE session_id=?", (agent, session_id))
    conn.commit()


def log_event(conn: sqlite3.Connection, **kw) -> int:
    cur = conn.execute(
        """INSERT INTO events(session_id, agent, confidence, clarified, abstained,
           tokens_in, tokens_out, latency_ms, cost_usd, ts)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (kw["session_id"], kw["agent"], kw["confidence"], kw["clarified"], kw["abstained"],
         kw["tokens_in"], kw["tokens_out"], kw["latency_ms"], kw["cost_usd"], time.time()),
    )
    conn.commit()
    return cur.lastrowid


def rate_event(conn: sqlite3.Connection, event_id: int, rating: int) -> None:
    conn.execute("UPDATE events SET rating=? WHERE id=?", (rating, event_id))
    conn.commit()


def metrics_summary(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT * FROM events").fetchall()
    if not rows:
        return {"total_requests": 0, "by_agent": {}, "latency_ms": {"p50": 0, "p95": 0},
                "tokens": {"in": 0, "out": 0}, "total_cost_usd": 0.0,
                "abstention_rate": 0.0, "avg_confidence": 0.0,
                "feedback": {"up": 0, "down": 0}}
    lat = sorted(r["latency_ms"] for r in rows)
    def pct(p):
        i = min(len(lat) - 1, int(round((p / 100) * (len(lat) - 1))))
        return round(lat[i], 1)
    by_agent: dict[str, int] = {}
    for r in rows:
        by_agent[r["agent"]] = by_agent.get(r["agent"], 0) + 1
    ups = sum(1 for r in rows if r["rating"] == 1)
    downs = sum(1 for r in rows if r["rating"] == 0)
    return {
        "total_requests": len(rows),
        "by_agent": by_agent,
        "latency_ms": {"p50": pct(50), "p95": pct(95)},
        "tokens": {"in": sum(r["tokens_in"] for r in rows), "out": sum(r["tokens_out"] for r in rows)},
        "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
        "abstention_rate": round(sum(r["abstained"] for r in rows) / len(rows), 3),
        "avg_confidence": round(sum(r["confidence"] for r in rows) / len(rows), 3),
        "feedback": {"up": ups, "down": downs},
    }
