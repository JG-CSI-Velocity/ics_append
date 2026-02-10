"""Tests for validation.py -- data quality checks."""

import pandas as pd
import pytest

from ics_append.validation import (
    DataQualityReport,
    QualityIssue,
    validate_account_series,
    validate_annotated_output,
    validate_odd_file,
)


class TestQualityIssue:
    def test_defaults(self):
        issue = QualityIssue(severity="error", column="test", message="fail")
        assert issue.row_indices == []
        assert issue.count == 0

    def test_frozen(self):
        issue = QualityIssue(severity="error", column="test", message="fail")
        with pytest.raises(Exception):
            issue.severity = "warning"


class TestDataQualityReport:
    def test_empty_report_is_valid(self):
        report = DataQualityReport()
        assert report.is_valid
        assert len(report.errors) == 0
        assert len(report.warnings) == 0

    def test_with_errors(self):
        report = DataQualityReport(
            issues=[
                QualityIssue(severity="error", column="x", message="bad"),
                QualityIssue(severity="warning", column="y", message="warn"),
            ]
        )
        assert not report.is_valid
        assert len(report.errors) == 1
        assert len(report.warnings) == 1

    def test_summary(self):
        report = DataQualityReport(row_count=100, valid_row_count=95)
        assert "95/100" in report.summary

    def test_warnings_only_is_valid(self):
        report = DataQualityReport(
            issues=[QualityIssue(severity="warning", column="x", message="warn")]
        )
        assert report.is_valid


class TestValidateAccountSeries:
    def test_valid_series(self):
        s = pd.Series(["ABC123456", "DEF789012", "GHI345678"])
        report = validate_account_series(s, "REF")
        assert report.is_valid
        assert report.valid_row_count == 3

    def test_empty_series(self):
        s = pd.Series([], dtype=str)
        report = validate_account_series(s, "REF")
        assert not report.is_valid
        assert len(report.errors) == 1

    def test_blanks_warned(self):
        s = pd.Series(["ABC123456", "", "nan", "DEF789012"])
        report = validate_account_series(s, "DM")
        blank_warnings = [i for i in report.warnings if "blank" in i.message]
        assert len(blank_warnings) == 1

    def test_short_values_warned(self):
        s = pd.Series(["AB", "CD", "EFGHIJ123456"])
        report = validate_account_series(s, "REF", min_length=6)
        short_warnings = [i for i in report.warnings if "shorter" in i.message]
        assert len(short_warnings) == 1
        assert short_warnings[0].count == 2

    def test_duplicates_warned(self):
        s = pd.Series(["ABC123456", "ABC123456", "DEF789012"])
        report = validate_account_series(s, "REF")
        dup_warnings = [i for i in report.warnings if "duplicate" in i.message]
        assert len(dup_warnings) == 1


class TestValidateOddFile:
    def test_valid_odd(self, sample_odd_df):
        report = validate_odd_file(sample_odd_df)
        assert report.is_valid
        assert report.valid_row_count == 10

    def test_empty_odd(self):
        report = validate_odd_file(pd.DataFrame())
        assert not report.is_valid

    def test_missing_acct_column(self):
        df = pd.DataFrame({"Name": ["A", "B"]})
        report = validate_odd_file(df)
        assert not report.is_valid
        assert any("Acct Number" in e.message for e in report.errors)

    def test_null_acct_numbers(self, sample_odd_df):
        sample_odd_df.loc[0, "Acct Number"] = None
        sample_odd_df.loc[1, "Acct Number"] = None
        report = validate_odd_file(sample_odd_df)
        assert report.is_valid  # nulls are warnings, not errors
        null_warnings = [w for w in report.warnings if "null" in w.message]
        assert len(null_warnings) == 1
        assert null_warnings[0].count == 2


class TestValidateAnnotatedOutput:
    def test_valid_output(self):
        df = pd.DataFrame(
            {
                "Acct Number": ["A1", "A2", "A3"],
                "ICS Account": ["Yes", "No", "Yes"],
                "ICS Source": ["REF", "", "DM"],
            }
        )
        report = validate_annotated_output(df)
        assert report.is_valid

    def test_missing_ics_account(self):
        df = pd.DataFrame(
            {
                "Acct Number": ["A1"],
                "ICS Source": ["REF"],
            }
        )
        report = validate_annotated_output(df)
        assert not report.is_valid

    def test_missing_ics_source(self):
        df = pd.DataFrame(
            {
                "Acct Number": ["A1"],
                "ICS Account": ["Yes"],
            }
        )
        report = validate_annotated_output(df)
        assert not report.is_valid

    def test_invalid_ics_account_values(self):
        df = pd.DataFrame(
            {
                "Acct Number": ["A1", "A2"],
                "ICS Account": ["Yes", "Maybe"],
                "ICS Source": ["REF", ""],
            }
        )
        report = validate_annotated_output(df)
        assert not report.is_valid

    def test_invalid_ics_source_values(self):
        df = pd.DataFrame(
            {
                "Acct Number": ["A1"],
                "ICS Account": ["Yes"],
                "ICS Source": ["INVALID"],
            }
        )
        report = validate_annotated_output(df)
        assert not report.is_valid

    def test_both_source_is_valid(self):
        df = pd.DataFrame(
            {
                "ICS Account": ["Yes"],
                "ICS Source": ["Both"],
            }
        )
        report = validate_annotated_output(df)
        assert report.is_valid
