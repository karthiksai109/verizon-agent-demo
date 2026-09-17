from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.engine import sessions
from services.engine.pipeline import Platform
from .schemas import ChatIn, FeedbackIn


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.platform = Platform()
    yield


app = FastAPI(title="Verizon 6-Agent Platform Demo", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(payload: ChatIn):
    return app.state.platform.chat(payload.text, payload.session_id)


@app.get("/history/{session_id}")
def history(session_id: str):
    conn = sessions.connect()
    msgs = sessions.load_history(conn, session_id)
    conn.close()
    return {"session_id": session_id, "messages": msgs}


@app.get("/metrics")
def metrics():
    conn = sessions.connect()
    data = sessions.metrics_summary(conn)
    conn.close()
    return data


@app.post("/feedback")
def feedback(payload: FeedbackIn):
    conn = sessions.connect()
    sessions.rate_event(conn, payload.event_id, payload.rating)
    conn.close()
    return {"ok": True}
