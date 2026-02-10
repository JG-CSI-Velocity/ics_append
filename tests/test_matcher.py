"""Tests for matcher.py -- ODD matching and annotation."""

import json

import pandas as pd
import pytest

from ics_append.matcher import (
    MatchMetadata,
    build_match_metadata,
    match_and_annotate,
    read_odd_file,
    write_metadata_json,
)


class TestMatchAndAnnotate:
    def test_basic_matching(self, sample_odd_df, sample_merged_df):
        result, stats = match_and_annotate(sample_odd_df, sample_merged_df)
        assert "ICS Account" in result.columns
        assert "ICS Source" in result.columns
        assert set(result["ICS Account"].unique()) == {"Yes", "No"}
        assert stats["matched"] > 0
        assert stats["matched"] + stats["unmatched"] == len(result)

    def test_no_matches(self, sample_odd_df):
        merged = pd.DataFrame(
            {
                "Acct Hash": ["ZZZZZ1", "ZZZZZ2"],
                "Source": ["REF", "DM"],
            }
        )
        result, stats = match_and_annotate(sample_odd_df, merged)
        assert (result["ICS Account"] == "No").all()
        assert (result["ICS Source"] == "").all()
        assert stats["matched"] == 0

    def test_all_match(self):
        odd = pd.DataFrame({"Acct Number": ["A1", "A2", "A3"]})
        merged = pd.DataFrame(
            {
                "Acct Hash": ["A1", "A2", "A3"],
                "Source": ["REF", "DM", "Both"],
            }
        )
        result, stats = match_and_annotate(odd, merged)
        assert (result["ICS Account"] == "Yes").all()
        assert stats["matched"] == 3

    def test_preserves_odd_columns(self, sample_odd_df, sample_merged_df):
        result, _ = match_and_annotate(sample_odd_df, sample_merged_df)
        for col in ["Acct Number", "Stat Code", "Debit?", "Curr Bal"]:
            assert col in result.columns

    def test_preserves_row_count(self, sample_odd_df, sample_merged_df):
        result, _ = match_and_annotate(sample_odd_df, sample_merged_df)
        assert len(result) == len(sample_odd_df)

    def test_source_values(self, sample_odd_df, sample_merged_df):
        result, stats = match_and_annotate(sample_odd_df, sample_merged_df)
        sources = set(result["ICS Source"].unique())
        assert sources <= {"REF", "DM", "Both", ""}

    def test_empty_merged(self, sample_odd_df):
        merged = pd.DataFrame(columns=["Acct Hash", "Source"])
        result, stats = match_and_annotate(sample_odd_df, merged)
        assert len(result) == len(sample_odd_df)
        assert (result["ICS Account"] == "No").all()

    def test_normalized_matching(self):
        odd = pd.DataFrame({"Acct Number": ["ABC-123", "DEF 456"]})
        merged = pd.DataFrame(
            {
                "Acct Hash": ["ABC123", "DEF456"],
                "Source": ["REF", "DM"],
            }
        )
        result, stats = match_and_annotate(odd, merged)
        assert stats["matched"] == 2


class TestReadOddFile:
    def test_reads_excel(self, odd_excel):
        df, col = read_odd_file(odd_excel)
        assert col == "Acct Number"
        assert len(df) == 10

    def test_reads_csv(self, tmp_path, sample_odd_df):
        path = tmp_path / "test.csv"
        sample_odd_df.to_csv(path, index=False)
        df, col = read_odd_file(path)
        assert col == "Acct Number"
        assert len(df) == 10

    def test_missing_acct_column(self, tmp_path):
        df = pd.DataFrame({"Name": ["A", "B"]})
        path = tmp_path / "bad.xlsx"
        df.to_excel(path, index=False)
        with pytest.raises(ValueError, match="Acct Number.*not found"):
            read_odd_file(path)

    def test_unsupported_format(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text("{}")
        with pytest.raises(ValueError, match="Unsupported"):
            read_odd_file(path)


class TestMatchMetadata:
    def test_summary(self):
        meta = MatchMetadata(
            client_id="1453",
            run_date="2026-01-15",
            total_odd_rows=100,
            matched_count=80,
            unmatched_count=20,
            ref_match_count=50,
            dm_match_count=25,
            both_match_count=5,
            match_rate=0.8,
            ref_file="ref.xlsx",
            dm_file="dm.xlsx",
            odd_file="odd.xlsx",
            ics_not_in_dump=10,
        )
        assert "80/100" in meta.summary
        assert "80.0%" in meta.summary
        assert "50 REF" in meta.summary
        assert "25 DM" in meta.summary

    def test_to_dict(self):
        meta = MatchMetadata(
            client_id="1453",
            run_date="2026-01-15",
            total_odd_rows=100,
            matched_count=80,
            unmatched_count=20,
            ref_match_count=50,
            dm_match_count=25,
            both_match_count=5,
            match_rate=0.8,
            ref_file="ref.xlsx",
            dm_file="dm.xlsx",
            odd_file="odd.xlsx",
            ics_not_in_dump=10,
        )
        d = meta.to_dict()
        assert d["client_id"] == "1453"
        assert d["match_rate"] == 0.8

    def test_frozen(self):
        meta = MatchMetadata(
            client_id="1453",
            run_date="",
            total_odd_rows=0,
            matched_count=0,
            unmatched_count=0,
            ref_match_count=0,
            dm_match_count=0,
            both_match_count=0,
            match_rate=0.0,
            ref_file="",
            dm_file="",
            odd_file="",
            ics_not_in_dump=0,
        )
        with pytest.raises(Exception):
            meta.client_id = "9999"


class TestBuildMatchMetadata:
    def test_basic(self):
        stats = {
            "matched": 80,
            "unmatched": 20,
            "ref_match_count": 50,
            "dm_match_count": 25,
            "both_match_count": 5,
        }
        meta = build_match_metadata(
            client_id="1453",
            stats=stats,
            total_odd_rows=100,
            merged_count=90,
            ref_file="ref.xlsx",
            dm_file="dm.xlsx",
            odd_file="odd.xlsx",
        )
        assert meta.matched_count == 80
        assert meta.match_rate == 0.8
        assert meta.ics_not_in_dump == 10

    def test_zero_odd_rows(self):
        stats = {
            "matched": 0,
            "unmatched": 0,
            "ref_match_count": 0,
            "dm_match_count": 0,
            "both_match_count": 0,
        }
        meta = build_match_metadata("1453", stats, 0, 0, "", "", "")
        assert meta.match_rate == 0.0


class TestWriteMetadataJson:
    def test_writes_file(self, tmp_path):
        meta = MatchMetadata(
            client_id="1453",
            run_date="2026-01-15",
            total_odd_rows=100,
            matched_count=80,
            unmatched_count=20,
            ref_match_count=50,
            dm_match_count=25,
            both_match_count=5,
            match_rate=0.8,
            ref_file="ref.xlsx",
            dm_file="dm.xlsx",
            odd_file="odd.xlsx",
            ics_not_in_dump=10,
        )
        path = tmp_path / "meta.json"
        write_metadata_json(meta, path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["client_id"] == "1453"
        assert data["matched_count"] == 80

    def test_creates_parent_dirs(self, tmp_path):
        meta = MatchMetadata(
            client_id="1453",
            run_date="",
            total_odd_rows=0,
            matched_count=0,
            unmatched_count=0,
            ref_match_count=0,
            dm_match_count=0,
            both_match_count=0,
            match_rate=0.0,
            ref_file="",
            dm_file="",
            odd_file="",
            ics_not_in_dump=0,
        )
        path = tmp_path / "sub" / "dir" / "meta.json"
        write_metadata_json(meta, path)
        assert path.exists()
