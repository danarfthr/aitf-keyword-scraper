import pytest
from keyword_scraper.filters import governance_signals, match_rule_filter


def test_match_rule_filter_exact():
    assert match_rule_filter("korupsi") is True


def test_match_rule_filter_word_boundary():
    # "pemilu" should match in "pemilu anak jakarta"
    assert match_rule_filter("pemilu anak jakarta") is True
    # "pemilu" should match as standalone word
    assert match_rule_filter("pemilu") is True


def test_match_rule_filter_substring_false_positive():
    # "kriminalitas" contains "kriminal" which is not a signal
    # so it should return False (no governance signal matches)
    assert match_rule_filter("kriminalitas") is False


def test_match_rule_filter_no_signal():
    assert match_rule_filter("(reserved)") is False


def test_governance_signals_is_list():
    assert isinstance(governance_signals, list)
    assert len(governance_signals) >= 50
