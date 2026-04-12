"""Tests for sampler summarizer."""

import pytest
from services.sampler.summarizer import summarize_body
from shared.shared.constants import SUMMARY_CHAR_THRESHOLD


def test_summarize_body_short():
    """Short body is stored as-is, summary is None."""
    body = "Ini adalah artikel pendek."
    body_stored, summary_stored = summarize_body(body)
    assert body_stored == body
    assert summary_stored is None


def test_summarize_body_long():
    """Long body is stored as None, summary is truncated with marker."""
    body = "A" * (SUMMARY_CHAR_THRESHOLD + 500)
    body_stored, summary_stored = summarize_body(body)
    assert body_stored is None
    assert summary_stored is not None
    assert summary_stored.endswith("... [truncated]")
    assert len(summary_stored) == SUMMARY_CHAR_THRESHOLD + len("... [truncated]")


def test_summarize_body_exactly_threshold():
    """Body exactly at threshold gets stored, not summarized."""
    body = "A" * SUMMARY_CHAR_THRESHOLD
    body_stored, summary_stored = summarize_body(body)
    assert body_stored == body
    assert summary_stored is None


def test_summarize_body_none():
    """None body returns (None, None)."""
    body_stored, summary_stored = summarize_body(None)
    assert body_stored is None
    assert summary_stored is None
