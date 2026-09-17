"""Scoped per-agent retrieval over that agent's policy doc.

Each agent gets its own vector index (TF-IDF stands in for embeddings here;
the interface is identical: embed -> index -> top-k by cosine similarity).
In the real system these indexes live in Elasticsearch/OpenSearch with Titan
embeddings; the swap is this one class.

Pipeline analogy you should be able to draw:
  doc -> parse -> chunk (heading-aware, overlap-ish via sentence groups)
      -> embed (TF-IDF here / Titan in prod) -> scoped index
      -> at query time: embed query -> cosine top-k -> chunks into prompt
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

DOCS_DIR = Path(__file__).parent / "docs"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


@dataclass
class Chunk:
    agent: str
    source: str
    heading: str
    text: str


def load_agent_chunks(doc_file: str, agent: str) -> list[Chunk]:
    src = DOCS_DIR / doc_file
    chunks: list[Chunk] = []
    heading, body = "Intro", []
    for line in src.read_text(encoding="utf-8").splitlines():
        h = re.match(r"^#{1,2}\s+(.*)", line)
        if h:
            if body:
                chunks.append(Chunk(agent, src.name, heading, " ".join(body).strip()))
            heading, body = h.group(1).strip(), []
        elif line.strip() and not line.startswith("#!"):
            body.append(line.strip().lstrip("- "))
    if body:
        chunks.append(Chunk(agent, src.name, heading, " ".join(body).strip()))
    return chunks


class VectorIndex:
    """Minimal TF-IDF + cosine index. Mirrors an embedding index API:
    add docs, search(query, k) -> [(chunk, score)]."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.doc_tokens = [_tokenize(f"{c.heading} {c.text}") for c in chunks]
        df: Counter[str] = Counter()
        for toks in self.doc_tokens:
            df.update(set(toks))
        self.df = df
        self.n = len(chunks)

    def _tfidf(self, toks: list[str]) -> dict[str, float]:
        tf = Counter(toks)
        return {t: (n / max(1, len(toks))) * math.log(self.n / (1 + self.df.get(t, 0))) for t, n in tf.items()}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        dot = sum(v * b.get(t, 0.0) for t, v in a.items())
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb + 1e-9)

    def search(self, query: str, k: int = 3) -> list[tuple[Chunk, float]]:
        q = self._tfidf(_tokenize(query))
        scored = [(c, self._cosine(q, self._tfidf(toks))) for c, toks in zip(self.chunks, self.doc_tokens)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]
