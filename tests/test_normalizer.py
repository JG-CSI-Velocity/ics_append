"""Tests for normalizer.py -- account hash normalization."""

import pandas as pd

from ics_append.normalizer import normalize_hash, normalize_series


class TestNormalizeHash:
    def test_none_returns_empty(self):
        assert normalize_hash(None) == ""

    def test_empty_string(self):
        assert normalize_hash("") == ""

    def test_whitespace_only(self):
        assert normalize_hash("   ") == ""

    def test_strips_whitespace(self):
        assert normalize_hash("  ABC123  ") == "ABC123"

    def test_removes_non_alnum(self):
        assert normalize_hash("ABC-123-DEF") == "ABC123DEF"

    def test_preserves_casing(self):
        assert normalize_hash("AbCdEf") == "AbCdEf"

    def test_preserves_leading_zeros(self):
        assert normalize_hash("0001234") == "0001234"

    def test_removes_special_chars(self):
        assert normalize_hash("A@B#C$D%E") == "ABCDE"

    def test_removes_spaces_in_middle(self):
        assert normalize_hash("ABC 123 DEF") == "ABC123DEF"

    def test_numeric_input(self):
        assert normalize_hash(12345) == "12345"

    def test_float_input(self):
        assert normalize_hash(123.45) == "12345"

    def test_pure_digits(self):
        assert normalize_hash("9876543210") == "9876543210"

    def test_unicode_stripped(self):
        assert normalize_hash("ABC\u2013123") == "ABC123"


class TestNormalizeSeries:
    def test_basic_series(self):
        s = pd.Series(["ABC-123", " DEF 456 ", "GHI.789"])
        result = normalize_series(s)
        assert result.tolist() == ["ABC123", "DEF456", "GHI789"]

    def test_preserves_index(self):
        s = pd.Series(["A-1", "B-2"], index=[10, 20])
        result = normalize_series(s)
        assert result.index.tolist() == [10, 20]

    def test_handles_nan(self):
        s = pd.Series(["ABC", None, "DEF"])
        result = normalize_series(s)
        assert result.iloc[0] == "ABC"
        assert result.iloc[2] == "DEF"

    def test_empty_series(self):
        s = pd.Series([], dtype=str)
        result = normalize_series(s)
        assert len(result) == 0
