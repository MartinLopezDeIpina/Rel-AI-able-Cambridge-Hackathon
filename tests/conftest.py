"""Shared fixtures + agent-optimized logging for the combined unit/integration suite.

The `agent` fixture emits structured, greppable log lines for every case a step can
land in:

    [STEP3][CASE name_hit_wins] resolve_one
      INPUT   : citation='Lumley v Gye (1853) 2 E&B 216'
      EXPECT  : method=name, needs_web=False
      ACTUAL  : method=name, needs_web=False
      RESULT  : PASS

Run with `pytest` (logging is live via pytest.ini `log_cli`). Capability flags below
let integration tests SKIP cleanly (with a logged reason) when an optional dep, the
built index, or Vertex credentials are unavailable — so the suite always runs.
"""
from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("agent")


# --------------------------------------------------------------------------
# Capability detection (drives skips; surfaced in the log so an agent sees why)
# --------------------------------------------------------------------------
def _have(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except ModuleNotFoundError:
        return False


HAS_FASTEMBED = _have("fastembed")
HAS_RAPIDFUZZ = _have("rapidfuzz")
HAS_FITZ = _have("fitz")          # PyMuPDF, for OCR extraction
HAS_VERTEXAI = _have("langchain_google_vertexai")


def _have_vertex_creds() -> bool:
    """ADC file present AND a project configured -> a real Gemini call can be made."""
    adc = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    try:
        from app.core.config import get_settings
        proj = get_settings().google_project
    except Exception:
        proj = os.environ.get("GOOGLE_PROJECT")
    return HAS_VERTEXAI and adc.is_file() and bool(proj)


HAS_VERTEX_CREDS = _have_vertex_creds()

requires_fastembed = pytest.mark.skipif(not HAS_FASTEMBED, reason="fastembed not installed")
requires_fitz = pytest.mark.skipif(not HAS_FITZ, reason="PyMuPDF (fitz) not installed")
requires_live_llm = pytest.mark.skipif(
    not HAS_VERTEX_CREDS, reason="no Vertex/ADC credentials (GOOGLE_PROJECT + ADC)")


# --------------------------------------------------------------------------
# Agent logger
# --------------------------------------------------------------------------
class AgentCase:
    """One logged test case: declares INPUT/EXPECT, then checks ACTUAL == EXPECT."""

    def __init__(self, step: str, name: str, fn: str = ""):
        self.step, self.name, self.fn = step, name, fn
        self._inputs: dict = {}
        self._expect: dict = {}

    def _fmt(self, d: dict) -> str:
        return ", ".join(f"{k}={v!r}" for k, v in d.items())

    def input(self, **kw) -> "AgentCase":
        self._inputs.update(kw)
        return self

    def expect(self, **kw) -> "AgentCase":
        self._expect.update(kw)
        return self

    def header(self) -> None:
        log.info("[%s][CASE %s] %s", self.step, self.name, self.fn)
        if self._inputs:
            log.info("  INPUT   : %s", self._fmt(self._inputs))
        if self._expect:
            log.info("  EXPECT  : %s", self._fmt(self._expect))

    def check(self, **actual) -> None:
        """Log ACTUAL, then assert it matches EXPECT key-by-key (PASS/FAIL logged)."""
        self.header()
        log.info("  ACTUAL  : %s", self._fmt(actual))
        mismatches = {k: (self._expect[k], actual.get(k))
                      for k in self._expect if actual.get(k) != self._expect[k]}
        if mismatches:
            log.error("  RESULT  : FAIL  -> %s", self._fmt(
                {k: f"want {w!r} got {g!r}" for k, (w, g) in mismatches.items()}))
            raise AssertionError(f"[{self.step}/{self.name}] mismatch: {mismatches}")
        log.info("  RESULT  : PASS")

    def note(self, msg: str) -> None:
        log.info("  NOTE    : %s", msg)

    def skip(self, reason: str):
        self.header()
        log.warning("  RESULT  : SKIP  -> %s", reason)
        pytest.skip(reason)


class Agent:
    """Factory for logged cases, bound to a step label."""

    def __init__(self, step: str):
        self.step = step

    def case(self, name: str, fn: str = "") -> AgentCase:
        return AgentCase(self.step, name, fn)


@pytest.fixture
def agent(request) -> Agent:
    # Derive the step label from the test file name, e.g. test_step3_resolution -> STEP3.
    stem = request.node.fspath.purebasename  # e.g. "test_step3_resolution"
    step = "STEP?"
    for part in stem.split("_"):
        if part.startswith("step") and part[4:].isdigit():
            step = f"STEP{part[4:]}"
            break
    return Agent(step)


# --------------------------------------------------------------------------
# Data / corpus fixtures
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def sample_pdf() -> Path:
    """A real brief PDF for Step 1 integration (skips if absent)."""
    p = REPO_ROOT / "case_demo.pdf"
    if not p.is_file():
        pytest.skip("case_demo.pdf not present")
    return p


@pytest.fixture(scope="session")
def tiny_corpus(tmp_path_factory) -> Path:
    """A 3-document .txt corpus with recognisable case names (for index + resolver)."""
    d = tmp_path_factory.mktemp("corpus")
    docs = {
        "Lumley v Gye (1853) 2 E&B 216.txt":
            "Lumley v Gye. He who procures the violation of a right is a joint "
            "wrongdoer. Procurement of a breach of contract is an actionable wrong "
            "where one party maliciously induces another to break their contract.",
        "Hadley v Baxendale (1854) 9 Ex 341.txt":
            "Hadley v Baxendale. Damages for breach of contract are limited to losses "
            "arising naturally from the breach, or such as were in the reasonable "
            "contemplation of both parties at the time they made the contract.",
        "American Cyanamid Co v Ethicon Ltd [1975] AC 396.txt":
            "American Cyanamid v Ethicon. For an interlocutory injunction the court "
            "must be satisfied only that there is a serious question to be tried, not "
            "that there is a strong prima facie case on the merits.",
    }
    for name, text in docs.items():
        (d / name).write_text(text, encoding="utf-8")
    return d


@pytest.fixture(scope="session")
def tiny_index(tmp_path_factory, tiny_corpus) -> Path:
    """Build a real semantic index from `tiny_corpus` (needs fastembed; first run
    downloads the bge-small model). Skips the dependent tests if unavailable."""
    if not HAS_FASTEMBED:
        pytest.skip("fastembed not installed - cannot build a real index")
    out = tmp_path_factory.mktemp("index")
    try:
        from app.services import indexer
        indexer.build(tiny_corpus, out)
    except Exception as exc:  # offline model download, etc.
        pytest.skip(f"index build failed ({type(exc).__name__}: {exc})")
    return out


@pytest.fixture
def mock_backend():
    from app.services.distortion_backend import get_backend
    return get_backend("mock")
