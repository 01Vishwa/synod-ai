"""
tests/unit/test_redact_identity.py — Unit tests for redact_identity().

Verifies that each provider pattern is correctly redacted, that clean text
is not mangled, and that technical terms sharing substrings with provider
names are left untouched (catches overly broad regex).

No I/O — redact_identity() is a pure function.
"""
from __future__ import annotations

import pytest

from app.domain.rules.anonymization import redact_identity

_FAKE_MEMBER_ID = "member-abc123"
_REDACTED = "[REDACTED]"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _redact(text: str) -> str:
    """Shorthand: redact with a fixed, non-interfering member_id."""
    return redact_identity(text, _FAKE_MEMBER_ID)


# ---------------------------------------------------------------------------
# Provider-name redaction tests
# ---------------------------------------------------------------------------

class TestOpenAIRedaction:
    def test_openai_provider_name_is_redacted(self) -> None:
        """A sentence containing 'OpenAI' must have that token replaced with [REDACTED]."""
        result = _redact("OpenAI suggests using chain-of-thought prompting.")
        assert "OpenAI" not in result
        assert _REDACTED in result

    def test_gpt_model_mention_is_redacted(self) -> None:
        """A sentence starting with 'As GPT, I' must be redacted."""
        result = _redact("As gpt, I will answer your question.")
        assert "gpt" not in result.lower().replace(_REDACTED.lower(), "")

    def test_clean_text_not_mangled_by_openai_pattern(self) -> None:
        """Text with no provider names must be returned unchanged."""
        original = "The quick brown fox jumps over the lazy dog."
        assert _redact(original) == original


class TestAnthropicRedaction:
    def test_anthropic_provider_name_is_redacted(self) -> None:
        """A sentence containing 'Anthropic' must have that token replaced with [REDACTED]."""
        result = _redact("Anthropic's approach to safety is RLHF-based.")
        assert "Anthropic" not in result
        assert _REDACTED in result

    def test_claude_model_mention_is_redacted(self) -> None:
        """A sentence starting with 'As Claude, I' must be redacted."""
        result = _redact("As claude, I try to be helpful.")
        assert "claude" not in result.lower().replace(_REDACTED.lower(), "")

    def test_clean_text_not_mangled_by_anthropic_pattern(self) -> None:
        """Clean prose must pass through the Anthropic pattern unmodified."""
        original = "The council reached a unanimous decision."
        assert _redact(original) == original


class TestGoogleGeminiRedaction:
    def test_gemini_model_mention_is_redacted(self) -> None:
        """A sentence starting with 'As Gemini, I' must be redacted."""
        result = _redact("As gemini, I excel at multimodal tasks.")
        assert "gemini" not in result.lower().replace(_REDACTED.lower(), "")

    def test_google_deepmind_brand_is_redacted(self) -> None:
        """The phrase 'Google DeepMind' in prose must be redacted."""
        result = _redact("Google DeepMind developed this model.")
        assert "Google DeepMind" not in result
        assert _REDACTED in result

    def test_clean_text_not_mangled_by_gemini_pattern(self) -> None:
        """Clean sentences must not be altered by the Gemini pattern."""
        original = "The analysis covers three main pillars."
        assert _redact(original) == original


class TestXAIGrokRedaction:
    def test_grok_model_mention_is_redacted(self) -> None:
        """The standalone word 'grok' used as a model name must be redacted."""
        result = _redact("grok-2 is a frontier model by xAI.")
        assert "grok" not in result.lower().replace(_REDACTED.lower(), "")

    def test_xai_brand_is_redacted(self) -> None:
        """The brand 'xAI' must be redacted."""
        result = _redact("xAI released Grok with real-time web access.")
        assert "xAI" not in result

    def test_clean_text_not_mangled_by_xai_pattern(self) -> None:
        """Clean sentences must not be altered by the xAI/Grok pattern."""
        original = "The system processes data in real time."
        assert _redact(original) == original


class TestDeepSeekRedaction:
    def test_deepseek_brand_is_redacted(self) -> None:
        """The brand 'DeepSeek' must be redacted."""
        result = _redact("DeepSeek released a new open-weight model.")
        assert "DeepSeek" not in result
        assert _REDACTED in result

    def test_deepseek_model_variant_is_redacted(self) -> None:
        """A specific DeepSeek model variant like 'deepseek-r1' must be redacted."""
        result = _redact("I am based on deepseek-r1 architecture.")
        assert "deepseek" not in result.lower().replace(_REDACTED.lower(), "")

    def test_clean_text_not_mangled_by_deepseek_pattern(self) -> None:
        """Clean text must pass through the DeepSeek pattern unmodified."""
        original = "The report examines economic indicators for 2024."
        assert _redact(original) == original


class TestCohereRedaction:
    def test_cohere_brand_is_redacted(self) -> None:
        """The brand 'Cohere' must be redacted."""
        result = _redact("Cohere specialises in enterprise NLP solutions.")
        assert "Cohere" not in result
        assert _REDACTED in result

    def test_command_r_model_is_redacted(self) -> None:
        """The model name 'Command R+' must be redacted."""
        result = _redact("Command R+ achieves strong RAG benchmarks.")
        assert "Command R+" not in result

    def test_clean_text_not_mangled_by_cohere_pattern(self) -> None:
        """Clean text must pass through the Cohere pattern unmodified."""
        original = "The summary includes quantitative findings."
        assert _redact(original) == original


class TestMetaLlamaRedaction:
    def test_meta_ai_brand_is_redacted(self) -> None:
        """The phrase 'Meta AI' must be redacted."""
        result = _redact("Meta AI published the LLaMA model family.")
        assert "Meta AI" not in result
        assert _REDACTED in result

    def test_llama_model_mention_is_redacted(self) -> None:
        """A sentence starting with 'As llama, I' must be redacted."""
        result = _redact("As llama, I was trained on public data.")
        assert "llama" not in result.lower().replace(_REDACTED.lower(), "")

    def test_clean_text_not_mangled_by_llama_pattern(self) -> None:
        """Clean text must pass through the Meta/Llama pattern unmodified."""
        original = "All perspectives have been carefully considered."
        assert _redact(original) == original


class TestMistralRedaction:
    def test_mistral_ai_brand_is_redacted(self) -> None:
        """The phrase 'Mistral AI' must be redacted."""
        result = _redact("Mistral AI is a European AI company.")
        assert "Mistral AI" not in result
        assert _REDACTED in result

    def test_mixtral_model_mention_is_redacted(self) -> None:
        """The model name 'Mixtral' must be redacted."""
        result = _redact("Mixtral uses a mixture-of-experts architecture.")
        assert "Mixtral" not in result

    def test_clean_text_not_mangled_by_mistral_pattern(self) -> None:
        """Clean text must pass through the Mistral pattern unmodified."""
        original = "The final answer synthesises all viewpoints."
        assert _redact(original) == original


# ---------------------------------------------------------------------------
# Self-identity (training cutoff / LLM self-disclosure) tests
# ---------------------------------------------------------------------------

class TestSelfDisclosureRedaction:
    def test_large_language_model_disclosure_is_redacted(self) -> None:
        """'I am a large language model' must be redacted to prevent self-disclosure."""
        result = _redact("I am a large language model trained by a major lab.")
        assert "large language model" not in result.lower()

    def test_training_cutoff_disclosure_is_redacted(self) -> None:
        """'My training data ends in' must be redacted to prevent cutoff self-disclosure."""
        result = _redact("My training data ends in early 2024.")
        assert "training" not in result.lower().replace(_REDACTED.lower(), "")

    def test_knowledge_cutoff_disclosure_is_redacted(self) -> None:
        """'My knowledge cutoff' must be redacted to prevent cutoff self-disclosure."""
        result = _redact("My knowledge cutoff is January 2025.")
        assert "knowledge" not in result.lower().replace(_REDACTED.lower(), "")


# ---------------------------------------------------------------------------
# Technical-term false-positive guard
# ---------------------------------------------------------------------------

class TestTechnicalTermsSafe:
    def test_open_source_not_redacted(self) -> None:
        """The hyphenated word 'open-source' must NOT be redacted (substring of 'OpenAI')."""
        original = "This is an open-source implementation."
        assert _redact(original) == original

    def test_gemstone_not_redacted(self) -> None:
        """The word 'gemstone' must NOT be redacted (shares prefix with 'Gemini')."""
        original = "The gemstone analysis revealed quartz deposits."
        assert _redact(original) == original

    def test_commander_not_redacted(self) -> None:
        """The word 'commander' must NOT be redacted (shares prefix with 'Command R')."""
        original = "The commander issued a strategic directive."
        assert _redact(original) == original

    def test_member_id_literal_is_redacted(self) -> None:
        """Any literal occurrence of the member_id string in text must be replaced."""
        text = f"This response was generated by {_FAKE_MEMBER_ID} for testing."
        result = redact_identity(text, _FAKE_MEMBER_ID)
        assert _FAKE_MEMBER_ID not in result
        assert _REDACTED in result
