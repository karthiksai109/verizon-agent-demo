"""Simulated Amazon Bedrock Converse API.

Mirrors the real boto3 bedrock-runtime converse() call:
- same request shape: messages list (role/content), system prompt,
  inferenceConfig (maxTokens, temperature)
- same response shape: output.message.content[0].text,
  usage.inputTokens/outputTokens/totalTokens, metrics.latencyMs
- stateless: this class remembers NOTHING between calls. Everything the
  model 'knows' about the conversation arrives inside this call's messages.
  That is the single most important property of the real Bedrock too.

In production the engine swaps this class for boto3.client('bedrock-runtime').
Nothing else in the codebase changes.
"""

import random
import re
import time

MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0 (simulated)"

# Real Claude 3.5 Sonnet list prices on Bedrock, per token.
PRICE_IN_PER_TOKEN = 3.00 / 1_000_000
PRICE_OUT_PER_TOKEN = 15.00 / 1_000_000


def estimate_tokens(text: str) -> int:
    """Crude tokenizer stand-in. Real models use a BPE tokenizer where
    ~1 token ~= 3/4 of an English word, so words*1.3 is close enough
    for demonstrating token economics."""
    return max(1, int(len(re.findall(r"\w+", text)) * 1.3))


class BedrockConverse:
    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    def converse(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 600,
        temperature: float = 0.2,
        persona: str = "support",
    ) -> dict:
        started = time.perf_counter()

        last = messages[-1]["content"]
        input_tokens = estimate_tokens(system + " " + " ".join(m["content"] for m in messages))

        answer = self._generate(system, last, persona)

        output_tokens = min(estimate_tokens(answer), max_tokens)
        latency_ms = (time.perf_counter() - started) * 1000 + self._rng.uniform(180, 420) + output_tokens * 1.2

        return {
            "modelId": MODEL_ID,
            "output": {"message": {"role": "assistant", "content": [{"text": answer}]}},
            "usage": {
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "totalTokens": input_tokens + output_tokens,
            },
            "metrics": {"latencyMs": round(latency_ms, 1)},
            "cost_estimate_usd": round(
                input_tokens * PRICE_IN_PER_TOKEN + output_tokens * PRICE_OUT_PER_TOKEN, 6
            ),
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
        }

    def _generate(self, system: str, user_message: str, persona: str) -> str:
        """Deterministic stand-in for sampling: compose an answer strictly from
        the retrieved context block and tool-result block inside the user message.
        This demonstrates grounding: the model can ONLY use what the pipeline
        fed it — exactly the property the real system is engineered for."""
        openings = {
            "billing": "Happy to help with the billing question.",
            "network": "Let's check the network side of this.",
            "plans": "Here is how the plans and upgrades work in your case.",
            "device": "I can help with the device issue.",
            "onboarding": "Welcome aboard - let me walk you through activation.",
            "generalist": "Here is what I found for you.",
        }
        cited = re.findall(r"\[\d+\] (.+?)(?=\n\[\d+\]|\n\n|\Z)", user_message, flags=re.S)
        bullets = []
        for i, chunk in enumerate(cited[:3], start=1):
            sentences = [s.strip() for s in re.split(r"(?<=[.!?]) ", chunk) if s.strip()]
            if sentences:
                bullets.append(f"- {sentences[0]} [{i}]")
                if len(sentences) > 1:
                    bullets.append(f"- {sentences[1]} [{i}]")
        tool_lines = [l.strip() for l in re.findall(r"^TOOL: (.+)$", user_message, flags=re.M)]
        parts = [openings.get(persona, openings["generalist"])]
        if tool_lines:
            parts.append("I checked our systems: " + " ".join(tool_lines))
        parts.append("Based on our policy:")
        parts.extend(bullets)
        parts.append("Anything else you would like me to dig into?")
        return "\n".join(parts)
