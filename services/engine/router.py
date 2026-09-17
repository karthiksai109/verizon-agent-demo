"""Router model: decides WHICH agent handles an incoming message.

Three-layer policy, same as production:
  1. Intent classifier scores the message against every agent's example
     utterances (TF-IDF cosine here; fine-tuned classifier + LLM fallback in prod).
  2. Confidence threshold: below it we do NOT guess a specialist — we ask a
     clarifying question via the generalist. Misrouting is worse than one
     extra turn.
  3. Session stickiness: if the conversation's current agent scores within
     STICKINESS_BAND of the best score, we stay with it. Customers in a billing
     flow shouldn't bounce to another agent because of a stray keyword.
"""

from .retriever import VectorIndex, Chunk

THRESHOLD = 0.18
STICKINESS_BAND = 0.07

EXAMPLES = {
    "billing": [
        "why is my bill so high this month",
        "dispute a charge on my bill",
        "payment arrangement extension due date",
        "refund for service outage credit",
        "autopay discount not applied",
        "late fee on my account",
        "understand charges one-time fees",
        "pay my bill balance due",
    ],
    "network": [
        "no service in my area outage",
        "internet is down not working",
        "slow speeds buffering speed test",
        "5g not working coverage map",
        "calls dropping bad signal",
        "wifi calling issues indoors",
        "fiber cut when will it be fixed",
        "data not working on my phone",
    ],
    "plans": [
        "upgrade my plan unlimited",
        "compare plans which is cheaper",
        "trade in my old phone value",
        "international travel pass roaming",
        "add a line to my account",
        "change my plan next month",
        "device upgrade eligibility",
        "promotion discount new customer",
    ],
    "device": [
        "my phone won't turn on",
        "esim activation new phone transfer",
        "replacement sim card",
        "phone battery swelling",
        "screen cracked repair deductible",
        "visual voicemail not working",
        "restart frozen screen unresponsive",
        "unlock my phone device unlock",
    ],
    "onboarding": [
        "port my number from another carrier",
        "activate my new phone first time",
        "new account setup first bill",
        "why is my first bill so high",
        "activation fee waived online order",
        "cancel within 14 days return",
        "send trade in within 30 days",
        "when will my port complete transfer number",
    ],
    "generalist": [
        "how do i contact support",
        "reset my account password login",
        "app not working sign in",
        "store near me appointment",
        "talk to a human representative",
        "privacy settings data sharing",
        "account manager add user",
        "where is my order tracking",
    ],
}


class Router:
    def __init__(self):
        self.agents = list(EXAMPLES.keys())
        self.indexes = {
            a: VectorIndex([Chunk(a, "intents", a, e) for e in EXAMPLES[a]]) for a in self.agents
        }

    def score(self, text: str, last_agent: str | None = None) -> dict:
        raw = {}
        for agent in self.agents:
            best = max((s for _, s in self.indexes[agent].search(text, k=1)), default=0.0)
            raw[agent] = round(best, 3)
        best_agent = max(raw, key=raw.get)
        best_score = raw[best_agent]

        decision = {
            "scores": raw,
            "picked": best_agent,
            "confidence": best_score,
            "clarify": best_score < THRESHOLD,
            "sticky_note": None,
        }
        if decision["clarify"]:
            decision["picked"] = "generalist"
        elif last_agent and last_agent in raw and raw[last_agent] >= best_score - STICKINESS_BAND:
            decision["picked"] = last_agent
            decision["sticky_note"] = (
                f"stayed with '{last_agent}' (score {raw[last_agent]:.3f} within "
                f"{STICKINESS_BAND} of best {best_agent} {best_score:.3f})"
            )
        return decision
