"""Tests for trends.py -- month-over-month trend tracking."""

import pandas as pd

from ics_append.merger import MergeResult
from ics_append.trends import build_summary_row, update_summary


class TestBuildSummaryRow:
    def test_basic(self):
        df = pd.DataFrame({"Acct Hash": ["A", "B"], "Source": ["REF", "DM"]})
        result = MergeResult(
            client_id="1453",
            merged_df=df,
            ref_count=1,
            dm_count=1,
            ref_status="Present",
            dm_status="Present",
        )
        row = build_summary_row(result, month="2026.01")
        assert row["Month"] == "2026.01"
        assert row["Client ID"] == "1453"
        assert row["REF Rows"] == 1
        assert row["DM Rows"] == 1
        assert row["Total Merged"] == 2
        assert row["REF Status"] == "Present"
        assert row["DM Status"] == "Present"

    def test_default_month(self):
        df = pd.DataFrame(columns=["Acct Hash", "Source"])
        result = MergeResult(client_id="1453", merged_df=df)
        row = build_summary_row(result)
        # Should have current month in YYYY.MM format
        assert len(row["Month"]) == 7
        assert "." in row["Month"]


class TestUpdateSummary:
    def test_creates_new_file(self, tmp_path):
        path = tmp_path / "trends" / "summary.csv"
        rows = [
            {
                "Month": "2026.01",
                "Client ID": "1453",
                "REF Rows": 10,
                "DM Rows": 5,
                "Total Merged": 15,
                "REF Status": "Present",
                "DM Status": "Present",
            }
        ]
        result = update_summary(rows, path)
        assert path.exists()
        assert len(result) == 1
        assert result.iloc[0]["Total Merged"] == 15

    def test_appends_to_existing(self, tmp_path):
        path = tmp_path / "summary.csv"
        # Write initial data
        initial = pd.DataFrame(
            [
                {
                    "Month": "2025.12",
                    "Client ID": "1453",
                    "REF Rows": 8,
                    "DM Rows": 4,
                    "Total Merged": 12,
                    "REF Status": "Present",
                    "DM Status": "Present",
                }
            ]
        )
        initial.to_csv(path, index=False)

        # Append new month
        rows = [
            {
                "Month": "2026.01",
                "Client ID": "1453",
                "REF Rows": 10,
                "DM Rows": 5,
                "Total Merged": 15,
                "REF Status": "Present",
                "DM Status": "Present",
            }
        ]
        result = update_summary(rows, path)
        assert len(result) == 2

    def test_deduplicates(self, tmp_path):
        path = tmp_path / "summary.csv"
        # Write initial data
        initial = pd.DataFrame(
            [
                {
                    "Month": "2026.01",
                    "Client ID": "1453",
                    "REF Rows": 8,
                    "DM Rows": 4,
                    "Total Merged": 12,
                    "REF Status": "Present",
                    "DM Status": "Present",
                }
            ]
        )
        initial.to_csv(path, index=False)

        # Update same month (should replace, not duplicate)
        rows = [
            {
                "Month": "2026.01",
                "Client ID": "1453",
                "REF Rows": 10,
                "DM Rows": 5,
                "Total Merged": 15,
                "REF Status": "Present",
                "DM Status": "Present",
            }
        ]
        result = update_summary(rows, path)
        assert len(result) == 1
        assert result.iloc[0]["Total Merged"] == 15

    def test_computes_mom_metrics(self, tmp_path):
        path = tmp_path / "summary.csv"
        initial = pd.DataFrame(
            [
                {
                    "Month": "2025.12",
                    "Client ID": "1453",
                    "REF Rows": 10,
                    "DM Rows": 5,
                    "Total Merged": 15,
                    "REF Status": "Present",
                    "DM Status": "Present",
                }
            ]
        )
        initial.to_csv(path, index=False)

        rows = [
            {
                "Month": "2026.01",
                "Client ID": "1453",
                "REF Rows": 20,
                "DM Rows": 10,
                "Total Merged": 30,
                "REF Status": "Present",
                "DM Status": "Present",
            }
        ]
        result = update_summary(rows, path)
        assert "Total_delta" in result.columns
        assert "Trend" in result.columns
        # 30 - 15 = 15 delta, trend should be "up"
        jan_row = result[result["Month"] == "2026.01"].iloc[0]
        assert jan_row["Total_delta"] == 15.0
        assert jan_row["Trend"] == "up"

    def test_dry_run(self, tmp_path):
        path = tmp_path / "summary.csv"
        rows = [
            {
                "Month": "2026.01",
                "Client ID": "1453",
                "REF Rows": 10,
                "DM Rows": 5,
                "Total Merged": 15,
                "REF Status": "Present",
                "DM Status": "Present",
            }
        ]
        result = update_summary(rows, path, dry_run=True)
        assert not path.exists()
        assert len(result) == 1

    def test_multiple_clients(self, tmp_path):
        path = tmp_path / "summary.csv"
        rows = [
            {
                "Month": "2026.01",
                "Client ID": "1453",
                "REF Rows": 10,
                "DM Rows": 5,
                "Total Merged": 15,
                "REF Status": "Present",
                "DM Status": "Present",
            },
            {
                "Month": "2026.01",
                "Client ID": "1217",
                "REF Rows": 20,
                "DM Rows": 10,
                "Total Merged": 30,
                "REF Status": "Present",
                "DM Status": "Present",
            },
        ]
        result = update_summary(rows, path)
        assert len(result) == 2
