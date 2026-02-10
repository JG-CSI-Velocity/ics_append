"""Data quality validation for REF, DM, and ODD files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd


@dataclass(frozen=True)
class QualityIssue:
    """A single data quality finding."""

    severity: Literal["error", "warning"]
    column: str
    message: str
    row_indices: list[int] = field(default_factory=list)
    count: int = 0


@dataclass
class DataQualityReport:
    """Validation results from data quality checks."""

    issues: list[QualityIssue] = field(default_factory=list)
    row_count: int = 0
    valid_row_count: int = 0

    @property
    def errors(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def summary(self) -> str:
        return (
            f"{self.valid_row_count}/{self.row_count} valid rows, "
            f"{len(self.errors)} errors, {len(self.warnings)} warnings"
        )


def validate_account_series(
    series: pd.Series,
    source_name: str,
    min_length: int = 6,
) -> DataQualityReport:
    """Validate a series of account hashes from a REF or DM file."""
    report = DataQualityReport(row_count=len(series))
    issues: list[QualityIssue] = []

    if series.empty:
        issues.append(
            QualityIssue(
                severity="error",
                column="accounts",
                message=f"{source_name} file produced no accounts",
            )
        )
        report.issues = issues
        return report

    # Check for nulls/blanks
    str_series = series.astype(str).str.strip()
    blanks = str_series.isin(["", "nan", "None", "NaN"])
    blank_count = int(blanks.sum())
    if blank_count > 0:
        issues.append(
            QualityIssue(
                severity="warning",
                column="accounts",
                message=f"{blank_count} blank/null values found",
                count=blank_count,
            )
        )

    # Check for short values (probably not valid hashes)
    valid = str_series[~blanks]
    short = valid.str.len() < min_length
    short_count = int(short.sum())
    if short_count > 0:
        issues.append(
            QualityIssue(
                severity="warning",
                column="accounts",
                message=f"{short_count} values shorter than {min_length} chars",
                count=short_count,
            )
        )

    # Check for duplicates
    dupes = valid.duplicated()
    dupe_count = int(dupes.sum())
    if dupe_count > 0:
        issues.append(
            QualityIssue(
                severity="warning",
                column="accounts",
                message=f"{dupe_count} duplicate values",
                count=dupe_count,
            )
        )

    report.issues = issues
    report.valid_row_count = int(len(valid) - short_count)
    return report


def validate_odd_file(
    df: pd.DataFrame,
    acct_column: str = "Acct Number",
) -> DataQualityReport:
    """Validate an ODD file before matching."""
    report = DataQualityReport(row_count=len(df))
    issues: list[QualityIssue] = []

    if df.empty:
        issues.append(
            QualityIssue(
                severity="error",
                column="all",
                message="ODD file is empty",
            )
        )
        report.issues = issues
        return report

    # Check required column
    if acct_column not in df.columns:
        issues.append(
            QualityIssue(
                severity="error",
                column=acct_column,
                message=f"Required column '{acct_column}' not found",
            )
        )
        report.issues = issues
        return report

    # Check for null account numbers
    nulls = df[acct_column].isna()
    null_count = int(nulls.sum())
    if null_count > 0:
        issues.append(
            QualityIssue(
                severity="warning",
                column=acct_column,
                message=f"{null_count} null account numbers",
                count=null_count,
            )
        )

    report.issues = issues
    report.valid_row_count = len(df) - null_count
    return report


def validate_annotated_output(
    df: pd.DataFrame,
) -> DataQualityReport:
    """Validate the annotated ODD output before writing."""
    report = DataQualityReport(row_count=len(df))
    issues: list[QualityIssue] = []

    # Check ICS Account column exists with correct values
    if "ICS Account" not in df.columns:
        issues.append(
            QualityIssue(
                severity="error",
                column="ICS Account",
                message="ICS Account column missing from output",
            )
        )
    else:
        valid_values = {"Yes", "No"}
        invalid = ~df["ICS Account"].isin(valid_values)
        invalid_count = int(invalid.sum())
        if invalid_count > 0:
            issues.append(
                QualityIssue(
                    severity="error",
                    column="ICS Account",
                    message=f"{invalid_count} rows with invalid ICS Account values",
                    count=invalid_count,
                )
            )

    # Check ICS Source column
    if "ICS Source" not in df.columns:
        issues.append(
            QualityIssue(
                severity="error",
                column="ICS Source",
                message="ICS Source column missing from output",
            )
        )
    else:
        valid_sources = {"REF", "DM", "Both", ""}
        invalid = ~df["ICS Source"].isin(valid_sources)
        invalid_count = int(invalid.sum())
        if invalid_count > 0:
            issues.append(
                QualityIssue(
                    severity="error",
                    column="ICS Source",
                    message=f"{invalid_count} rows with invalid ICS Source values",
                    count=invalid_count,
                )
            )

    report.issues = issues
    report.valid_row_count = len(df) - sum(i.count for i in issues if i.severity == "error")
    return report
