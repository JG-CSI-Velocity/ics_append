"""Tests for pipeline.py -- end-to-end orchestration."""

import pandas as pd

from ics_append.pipeline import (
    PipelineResult,
    _atomic_write_excel,
    _find_merged_file,
    run_match,
    run_merge,
    run_organize,
    run_pipeline,
)
from ics_append.settings import Settings


class TestRunOrganize:
    def test_organizes_files(self, base_dir):
        (base_dir / "1453-ref.xlsx").touch()
        settings = Settings(base_dir=base_dir)
        moved = run_organize(settings)
        assert "1453" in moved
        assert (base_dir / "1453" / "1453-ref.xlsx").exists()

    def test_dry_run(self, base_dir):
        (base_dir / "1453-ref.xlsx").touch()
        settings = Settings(base_dir=base_dir, dry_run=True)
        moved = run_organize(settings)
        assert "1453" in moved
        assert (base_dir / "1453-ref.xlsx").exists()


class TestRunMerge:
    def test_merges_client(self, base_dir, client_dir, ref_excel, dm_excel):
        settings = Settings(base_dir=base_dir)
        results = run_merge(settings)
        assert len(results) == 1
        assert results[0].client_id == "1453"
        assert results[0].total > 0

    def test_writes_merged_file(self, base_dir, client_dir, ref_excel, dm_excel):
        settings = Settings(base_dir=base_dir, match_month="2026.01")
        run_merge(settings)
        merged_files = list(client_dir.glob("*ICS Accounts-All*"))
        assert len(merged_files) >= 1

    def test_specific_client(self, base_dir, client_dir, ref_excel):
        settings = Settings(base_dir=base_dir)
        results = run_merge(settings, client_ids=["1453"])
        assert len(results) == 1

    def test_no_clients(self, base_dir):
        settings = Settings(base_dir=base_dir)
        results = run_merge(settings)
        assert len(results) == 0

    def test_dry_run_no_files(self, base_dir, client_dir, ref_excel, dm_excel):
        settings = Settings(base_dir=base_dir, dry_run=True)
        results = run_merge(settings)
        # Results computed but no files written
        assert len(results) == 1
        merged_files = list(client_dir.glob("*ICS Accounts-All*"))
        assert len(merged_files) == 0

    def test_overwrite_false_creates_versioned(self, base_dir, client_dir, ref_excel, dm_excel):
        settings = Settings(base_dir=base_dir, match_month="2026.01", overwrite=False)
        # First merge creates the base file
        run_merge(settings)
        files_v0 = list(client_dir.glob("*ICS Accounts-All*"))
        assert len(files_v0) == 1

        # Second merge with overwrite=False creates _v1
        run_merge(settings)
        files_all = list(client_dir.glob("*ICS Accounts-All*"))
        assert len(files_all) == 2
        names = [f.name for f in files_all]
        assert any("_v1" in n for n in names)

    def test_csv_copy_creates_csv(self, base_dir, client_dir, ref_excel, dm_excel):
        settings = Settings(base_dir=base_dir, match_month="2026.01", csv_copy=True)
        run_merge(settings)
        csv_files = list(client_dir.glob("*ICS Accounts-All*.csv"))
        assert len(csv_files) == 1

    def test_missing_client_dir_skipped(self, base_dir):
        settings = Settings(base_dir=base_dir)
        results = run_merge(settings, client_ids=["9999"])
        assert len(results) == 0


class TestRunPipeline:
    def test_full_pipeline(self, base_dir, client_dir, ref_excel, dm_excel):
        settings = Settings(base_dir=base_dir, match_month="2026.01")
        result = run_pipeline(settings)
        assert isinstance(result, PipelineResult)
        assert len(result.merge_results) >= 1
        assert len(result.errors) == 0

    def test_with_progress_callback(self, base_dir, client_dir, ref_excel):
        progress_calls = []
        settings = Settings(base_dir=base_dir)
        run_pipeline(settings, on_progress=lambda cid, msg: progress_calls.append((cid, msg)))
        assert len(progress_calls) > 0

    def test_dry_run(self, base_dir, client_dir, ref_excel, dm_excel):
        settings = Settings(base_dir=base_dir, dry_run=True)
        result = run_pipeline(settings)
        assert len(result.errors) == 0

    def test_pipeline_with_match(self, tmp_path, base_dir, client_dir, ref_excel, dm_excel):
        # Create ARS directory with ODD file
        ars_dir = tmp_path / "ars"
        ars_month = ars_dir / "2026.01" / "1453"
        ars_month.mkdir(parents=True)
        odd_df = pd.DataFrame(
            {
                "Acct Number": ["ABC123", "DEF456", "GHI789", "ZZZ999"],
                "Stat Code": ["O", "O", "C", "O"],
                "Debit?": ["Yes", "No", "Yes", "No"],
            }
        )
        odd_df.to_excel(ars_month / "1453_oddd.xlsx", index=False)
        settings = Settings(base_dir=base_dir, ars_dir=ars_dir, match_month="2026.01")
        result = run_pipeline(settings)
        assert len(result.errors) == 0
        assert len(result.merge_results) == 1
        assert len(result.match_metadata) == 1

    def test_pipeline_writes_trends(self, base_dir, client_dir, ref_excel, dm_excel):
        settings = Settings(base_dir=base_dir, match_month="2026.01")
        run_pipeline(settings)
        trends_file = base_dir / "trends" / "merge_summary.csv"
        assert trends_file.exists()
        df = pd.read_csv(trends_file)
        assert len(df) == 1
        assert str(df.iloc[0]["Client ID"]) == "1453"


class TestRunMatch:
    def _setup_ars(self, tmp_path, base_dir, client_dir, ref_excel, dm_excel):
        """Helper: create ARS dir with ODD file and run merge to produce merged file."""
        # Run merge first to produce the merged ICS file
        settings = Settings(base_dir=base_dir, match_month="2026.01")
        run_merge(settings)

        # Create ARS directory structure: ars_dir/2026.01/1453/
        ars_dir = tmp_path / "ars"
        ars_month = ars_dir / "2026.01" / "1453"
        ars_month.mkdir(parents=True)

        # Write an ODD file with known accounts
        odd_df = pd.DataFrame(
            {
                "Acct Number": ["ABC123", "DEF456", "GHI789", "ZZZ999"],
                "Stat Code": ["O", "O", "C", "O"],
                "Debit?": ["Yes", "No", "Yes", "No"],
            }
        )
        odd_path = ars_month / "1453_oddd.xlsx"
        odd_df.to_excel(odd_path, index=False)
        return ars_dir

    def test_no_ars_dir(self, base_dir, client_dir, ref_excel):
        settings = Settings(base_dir=base_dir)
        result = run_match(settings)
        assert result == []

    def test_missing_ars_month_dir(self, tmp_path, base_dir, client_dir, ref_excel):
        ars_dir = tmp_path / "ars"
        ars_dir.mkdir()
        settings = Settings(base_dir=base_dir, ars_dir=ars_dir, match_month="2026.01")
        result = run_match(settings)
        assert result == []

    def test_matches_accounts(self, tmp_path, base_dir, client_dir, ref_excel, dm_excel):
        ars_dir = self._setup_ars(tmp_path, base_dir, client_dir, ref_excel, dm_excel)
        settings = Settings(base_dir=base_dir, ars_dir=ars_dir, match_month="2026.01")
        metadata = run_match(settings)
        assert len(metadata) == 1
        meta = metadata[0]
        assert meta.client_id == "1453"
        assert meta.total_odd_rows == 4
        assert meta.matched_count > 0

    def test_writes_annotated_file(self, tmp_path, base_dir, client_dir, ref_excel, dm_excel):
        ars_dir = self._setup_ars(tmp_path, base_dir, client_dir, ref_excel, dm_excel)
        settings = Settings(base_dir=base_dir, ars_dir=ars_dir, match_month="2026.01")
        run_match(settings)
        ars_client = ars_dir / "2026.01" / "1453"
        annotated = list(ars_client.glob("*_annotated.xlsx"))
        assert len(annotated) == 1

    def test_writes_metadata_json(self, tmp_path, base_dir, client_dir, ref_excel, dm_excel):
        ars_dir = self._setup_ars(tmp_path, base_dir, client_dir, ref_excel, dm_excel)
        settings = Settings(base_dir=base_dir, ars_dir=ars_dir, match_month="2026.01")
        run_match(settings)
        ars_client = ars_dir / "2026.01" / "1453"
        json_files = list(ars_client.glob("*_match_metadata.json"))
        assert len(json_files) == 1

    def test_dry_run_no_output(self, tmp_path, base_dir, client_dir, ref_excel, dm_excel):
        ars_dir = self._setup_ars(tmp_path, base_dir, client_dir, ref_excel, dm_excel)
        settings = Settings(base_dir=base_dir, ars_dir=ars_dir, match_month="2026.01", dry_run=True)
        metadata = run_match(settings)
        assert metadata == []
        ars_client = ars_dir / "2026.01" / "1453"
        annotated = list(ars_client.glob("*_annotated.xlsx"))
        assert len(annotated) == 0

    def test_with_progress_callback(self, tmp_path, base_dir, client_dir, ref_excel, dm_excel):
        ars_dir = self._setup_ars(tmp_path, base_dir, client_dir, ref_excel, dm_excel)
        settings = Settings(base_dir=base_dir, ars_dir=ars_dir, match_month="2026.01")
        progress = []
        run_match(settings, on_progress=lambda cid, msg: progress.append((cid, msg)))
        assert len(progress) >= 1
        assert progress[0][0] == "1453"

    def test_skips_non_digit_dirs(self, tmp_path, base_dir, client_dir, ref_excel, dm_excel):
        ars_dir = self._setup_ars(tmp_path, base_dir, client_dir, ref_excel, dm_excel)
        # Add a non-client directory
        (ars_dir / "2026.01" / "logs").mkdir()
        settings = Settings(base_dir=base_dir, ars_dir=ars_dir, match_month="2026.01")
        metadata = run_match(settings)
        # Should only match 1453, not "logs"
        assert len(metadata) == 1

    def test_no_odd_file_skips(self, tmp_path, base_dir, client_dir, ref_excel, dm_excel):
        # Merge first
        settings = Settings(base_dir=base_dir, match_month="2026.01")
        run_merge(settings)

        # Create ARS dir with client folder but no ODD file
        ars_dir = tmp_path / "ars"
        (ars_dir / "2026.01" / "1453").mkdir(parents=True)
        (ars_dir / "2026.01" / "1453" / "some_other_file.xlsx").touch()

        settings = Settings(base_dir=base_dir, ars_dir=ars_dir, match_month="2026.01")
        metadata = run_match(settings)
        assert metadata == []


class TestFindMergedFile:
    def test_finds_file(self, client_dir, merged_excel):
        result = _find_merged_file(client_dir, "1453", "2026.01")
        assert result is not None
        assert "ICS Accounts-All" in result.name

    def test_returns_none_if_missing(self, client_dir):
        result = _find_merged_file(client_dir, "1453", "2099.01")
        assert result is None

    def test_nonexistent_dir(self, tmp_path):
        result = _find_merged_file(tmp_path / "nonexistent", "1453", "2026.01")
        assert result is None

    def test_fallback_no_month_match(self, client_dir):
        # File without matching month should still be found as fallback
        path = client_dir / "1453-ICS Accounts-All.xlsx"
        pd.DataFrame({"A": [1]}).to_excel(path, index=False)
        result = _find_merged_file(client_dir, "1453", "2099.12")
        assert result is not None
        assert result.name == "1453-ICS Accounts-All.xlsx"

    def test_prefers_month_match(self, client_dir):
        # When both month-specific and generic exist, prefer month-specific
        generic = client_dir / "1453-ICS Accounts-All.xlsx"
        specific = client_dir / "1453-ICS Accounts-All-2026.01.xlsx"
        pd.DataFrame({"A": [1]}).to_excel(generic, index=False)
        pd.DataFrame({"A": [1]}).to_excel(specific, index=False)
        result = _find_merged_file(client_dir, "1453", "2026.01")
        assert result is not None
        assert "2026.01" in result.name


class TestAtomicWriteExcel:
    def test_writes_file(self, tmp_path):
        df = pd.DataFrame({"A": [1, 2, 3]})
        path = tmp_path / "test.xlsx"
        _atomic_write_excel(df, path)
        assert path.exists()
        result = pd.read_excel(path)
        assert len(result) == 3

    def test_creates_parent_dirs(self, tmp_path):
        df = pd.DataFrame({"A": [1]})
        path = tmp_path / "sub" / "dir" / "test.xlsx"
        _atomic_write_excel(df, path)
        assert path.exists()

    def test_overwrites_existing(self, tmp_path):
        path = tmp_path / "test.xlsx"
        pd.DataFrame({"A": [1]}).to_excel(path, index=False)
        _atomic_write_excel(pd.DataFrame({"B": [2, 3]}), path)
        result = pd.read_excel(path)
        assert "B" in result.columns
        assert len(result) == 2
