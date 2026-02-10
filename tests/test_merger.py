"""Tests for merger.py -- REF/DM merge logic."""

import pandas as pd

from ics_append.merger import MergeResult, merge_client_files, merge_sources
from ics_append.settings import ClientConfig, Settings


class TestMergeSources:
    def test_ref_only(self):
        ref = pd.Series(["A1", "A2", "A3"])
        result = merge_sources(ref, None)
        assert len(result) == 3
        assert list(result.columns) == ["Acct Hash", "Source"]
        assert (result["Source"] == "REF").all()

    def test_dm_only(self):
        dm = pd.Series(["B1", "B2"])
        result = merge_sources(None, dm)
        assert len(result) == 2
        assert (result["Source"] == "DM").all()

    def test_both_sources(self):
        ref = pd.Series(["A1", "A2"])
        dm = pd.Series(["B1", "B2"])
        result = merge_sources(ref, dm)
        assert len(result) == 4
        assert set(result["Source"]) == {"REF", "DM"}

    def test_deduplication_tags_both(self):
        ref = pd.Series(["ABC123", "DEF456"])
        dm = pd.Series(["ABC123", "GHI789"])
        result = merge_sources(ref, dm)
        # ABC123 appears in both -> "Both"
        both_rows = result[result["Source"] == "Both"]
        assert len(both_rows) == 1
        assert both_rows.iloc[0]["Acct Hash"] == "ABC123"
        # Total should be 3 unique accounts
        assert len(result) == 3

    def test_empty_both(self):
        result = merge_sources(None, None)
        assert len(result) == 0
        assert list(result.columns) == ["Acct Hash", "Source"]

    def test_empty_series(self):
        ref = pd.Series([], dtype=str)
        dm = pd.Series([], dtype=str)
        result = merge_sources(ref, dm)
        assert len(result) == 0

    def test_preserves_original_hash(self):
        # Hash with special chars -- dedup by normalized, but keep original
        ref = pd.Series(["ABC-123"])
        dm = pd.Series(["ABC123"])
        result = merge_sources(ref, dm)
        # Both normalize to "ABC123" so should be tagged as "Both"
        assert len(result) == 1
        assert result.iloc[0]["Source"] == "Both"


class TestMergeClientFiles:
    def test_merges_ref_and_dm(self, client_dir, ref_excel, dm_excel, sample_settings):
        result = merge_client_files(client_dir, "1453", sample_settings)
        assert isinstance(result, MergeResult)
        assert result.client_id == "1453"
        assert result.ref_count > 0
        assert result.dm_count > 0
        assert result.total > 0
        assert result.ref_status == "Present"
        assert result.dm_status == "Present"

    def test_ref_only(self, client_dir, ref_excel, sample_settings):
        result = merge_client_files(client_dir, "1453", sample_settings)
        assert result.ref_count > 0
        assert result.dm_count == 0
        assert result.dm_status == "Missing"

    def test_no_files(self, client_dir, sample_settings):
        result = merge_client_files(client_dir, "1453", sample_settings)
        assert result.total == 0
        assert result.ref_status == "Missing"
        assert result.dm_status == "Missing"

    def test_with_client_config(self, client_dir, sample_settings, sample_ref_df):
        # Write REF file with account data in column A (index 0)
        path = client_dir / "1453-referral-2026.01.xlsx"
        sample_ref_df.to_excel(path, index=False)
        # Client config says ref is in column A, header row 1
        settings = Settings(
            base_dir=sample_settings.base_dir,
            clients={
                "1453": ClientConfig(ref_column="A", ref_header_row=1),
            },
        )
        result = merge_client_files(client_dir, "1453", settings)
        assert result.ref_count > 0


class TestMergeResult:
    def test_total_property(self):
        df = pd.DataFrame({"Acct Hash": ["A", "B", "C"], "Source": ["REF", "DM", "REF"]})
        result = MergeResult(client_id="1453", merged_df=df, ref_count=2, dm_count=1)
        assert result.total == 3

    def test_total_empty(self):
        df = pd.DataFrame(columns=["Acct Hash", "Source"])
        result = MergeResult(client_id="1453", merged_df=df)
        assert result.total == 0
