"""Semantic-entropy uncertainty for the Step-4 faithfulness check.

Standard semantic-entropy method (Kuhn et al. 2023; Farquhar et al., Nature 2024)
applied to "does this source paragraph support the citing claim?":

  1. Sample the support/contradict judgement N times (temperature > 0), each returning
     YES/NO + a one-sentence reason. The N samples are issued concurrently.
  2. Weight each sample by its sequence probability = product of token probabilities =
     ``exp(sum of token logprobs)`` (Gemini returns per-token logprobs).
  3. Cluster the samples by meaning (same yes/no AND same essential reason) with a
     judge LLM.
  4. Cluster probability = (sum of its samples' probabilities) / (sum over all
     samples). Entropy over those cluster probabilities is the model's uncertainty
     about whether the paragraph supports the citation.

Gemini-only (needs token logprobs); if logprobs are unavailable the weights fall back
to uniform (the discrete semantic-entropy variant).
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.services.distortion_backend import _loads_json

_SAMPLE_PROMPT = """You assess whether a SOURCE passage from a court judgment supports \
how a legal brief uses (cites) that case.

CLAIM (the brief's use of the case):
\"\"\"{claim}\"\"\"

SOURCE passage (from the cited judgment):
\"\"\"{source}\"\"\"

Does the source passage support the claim? Reply with "YES" or "NO" on the first line, \
then one sentence giving the reason."""

_CLUSTER_PROMPT = """Several assistants judged whether a source supports a claim. Group \
the answers that express the SAME position — i.e. the same YES/NO conclusion AND the \
same essential reason — into one cluster.

ANSWERS:
{answers}

Return ONLY JSON of the form {{"clusters": [[0,2],[1],[3,4]]}}, where each inner list \
holds the 0-based answer indices in one cluster. Every index 0..{last} must appear \
exactly once."""


@dataclass
class _Sample:
    text: str
    logprob: float | None  # sequence logprob (sum of token logprobs)
    answer: str            # "yes" | "no" | "unknown"


def _build_sampler(settings: Settings):
    """Gemini configured for diverse sampling with token logprobs, thinking off."""
    from langchain_google_vertexai import ChatVertexAI

    return ChatVertexAI(
        model=settings.google_model,
        project=settings.google_project,
        location=settings.google_location,
        temperature=settings.semantic_entropy_temperature,
        thinking_budget=0,
        logprobs=True,
        max_output_tokens=256,
    )


def _seq_logprob(resp) -> float | None:
    """Sequence logprob = sum of per-token logprobs (None if not provided)."""
    md = getattr(resp, "response_metadata", {}) or {}
    tokens = md.get("logprobs_result")
    if tokens:
        return float(sum(t.get("logprob", 0.0) for t in tokens))
    avg = md.get("avg_logprobs")
    n = (getattr(resp, "usage_metadata", None) or {}).get("output_tokens")
    if avg is not None and n:
        return float(avg) * int(n)
    return None


def _answer(text: str) -> str:
    head = text.strip().lower()[:8]
    if head.startswith("yes"):
        return "yes"
    if head.startswith("no"):
        return "no"
    return "unknown"


def _sample_once(llm, prompt: str) -> _Sample:
    from langchain_core.messages import HumanMessage

    resp = llm.invoke([HumanMessage(content=prompt)])
    text = str(resp.content).strip()
    return _Sample(text=text, logprob=_seq_logprob(resp), answer=_answer(text))


def _sample_n(llm, prompt: str, n: int) -> list[_Sample]:
    """Draw N samples concurrently (the expensive part — kept parallel)."""
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(lambda _: _sample_once(llm, prompt), range(n)))


def _cluster(judge_llm, samples: list[_Sample]) -> list[list[int]]:
    """Group sample indices by meaning via one judge call; fall back to grouping by the
    yes/no answer if the judge reply can't be used."""
    from langchain_core.messages import HumanMessage

    answers = "\n".join(f"[{i}] {s.text}" for i, s in enumerate(samples))
    try:
        resp = judge_llm.invoke([HumanMessage(
            content=_CLUSTER_PROMPT.format(answers=answers, last=len(samples) - 1))])
        clusters = [
            [i for i in group if isinstance(i, int) and 0 <= i < len(samples)]
            for group in _loads_json(str(resp.content)).get("clusters", [])
        ]
        seen = [i for cl in clusters for i in cl]
        if sorted(seen) == list(range(len(samples))):  # valid partition
            return [cl for cl in clusters if cl]
    except Exception:  # noqa: BLE001 - degrade to answer-based clustering
        pass
    by_answer: dict[str, list[int]] = {}
    for i, s in enumerate(samples):
        by_answer.setdefault(s.answer, []).append(i)
    return list(by_answer.values())


def _weights(samples: list[_Sample]) -> tuple[list[float], bool]:
    """Per-sample probability weights from sequence logprobs (log-sum-exp stabilised);
    uniform if any logprob is missing."""
    if all(s.logprob is not None for s in samples):
        hi = max(s.logprob for s in samples)  # type: ignore[type-var]
        return [math.exp(s.logprob - hi) for s in samples], True  # type: ignore[operator]
    return [1.0] * len(samples), False


def compute(claim: str, source: str | list[str], settings: Settings | None = None) -> dict | None:
    """Semantic-entropy uncertainty that ``source`` supports ``claim``.

    Returns a dict (uncertainty in nats + normalised 0..1, cluster breakdown) or
    ``None`` when there is nothing to assess.
    """
    settings = settings or get_settings()
    text = "\n\n".join(source) if isinstance(source, list) else (source or "")
    if not claim.strip() or not text.strip():
        return None

    n = max(2, settings.semantic_entropy_samples)
    sampler = _build_sampler(settings)
    prompt = _SAMPLE_PROMPT.format(claim=claim.strip(), source=text.strip()[:6000])
    samples = _sample_n(sampler, prompt, n)

    weights, logprob_weighted = _weights(samples)
    # Deterministic judge for clustering (temperature 0 via the shared client).
    from app.services.citation_llm_service import build_llm
    clusters = _cluster(build_llm(settings), samples)

    cluster_w = [sum(weights[i] for i in cl) for cl in clusters]
    total = sum(cluster_w) or 1.0
    probs = [w / total for w in cluster_w]
    entropy = max(0.0, -sum(p * math.log(p) for p in probs if p > 0))  # nats (no -0.0)
    max_entropy = math.log(n)  # max possible with N samples

    yes = sum(1 for s in samples if s.answer == "yes")
    no = sum(1 for s in samples if s.answer == "no")
    return {
        "uncertainty": round(entropy, 4),
        "uncertainty_norm": round(entropy / max_entropy, 4) if max_entropy else 0.0,
        "n_samples": n,
        "n_clusters": len(clusters),
        "logprob_weighted": logprob_weighted,
        "answer_distribution": {"yes": yes, "no": no, "unknown": n - yes - no},
        "clusters": [
            {
                "probability": round(probs[c], 4),
                "answer": samples[cl[0]].answer,
                "reason": samples[cl[0]].text,
                "size": len(cl),
            }
            for c, cl in enumerate(clusters)
        ],
    }
