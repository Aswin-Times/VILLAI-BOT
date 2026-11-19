"""Live golden-set eval for the Claude parser (plan §10: nightly with the LLM provider).

Skipped unless RUN_LLM_EVALS=1 and ANTHROPIC_API_KEY are set: it makes ~70 real
API calls, so it costs money (cents with Haiku) and is never run by default.
"""

from __future__ import annotations

import os

import pytest

from app.conversation.llm_parser import AnthropicIntentParser
from tests.conversation.golden import score

LIVE = os.environ.get("RUN_LLM_EVALS") == "1" and bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.mark.skipif(not LIVE, reason="live LLM eval: set RUN_LLM_EVALS=1 and ANTHROPIC_API_KEY")
def test_claude_parser_golden_accuracy() -> None:
    import anthropic

    accuracy, misses = score(AnthropicIntentParser(anthropic.Anthropic()))

    report = "\n".join(f"  {m.text!r}: expected {m.expected}, got {m.got}" for m in misses)
    print(f"claude parser golden accuracy: {accuracy:.1%}\n{report}")
    assert accuracy >= 0.90, report
