"""Tests for column_detect.py -- file and column detection."""

import pandas as pd

from ics_append.column_detect import (
    _letter_to_index,
    detect_file_by_keywords,
    extract_account_column_by_inference,
    extract_account_column_by_name,
    extract_accounts,
)


class TestDetectFileByKeywords:
    def test_finds_ref_file(self, tmp_path):
        ref = tmp_path / "1453-Referral-2026.01.xlsx"
        other = tmp_path / "1453-data.xlsx"
        ref.touch()
        other.touch()
        result = detect_file_by_keywords([ref, other], ["referral", "ref"])
        assert result == ref

    def test_finds_dm_file(self, tmp_path):
        dm = tmp_path / "1453-Direct Mail New Accounts-2026.01.xlsx"
        dm.touch()
        result = detect_file_by_keywords([dm], ["direct mail", "new accounts"])
        assert result == dm

    def test_returns_none_no_match(self, tmp_path):
        other = tmp_path / "random_file.xlsx"
        other.touch()
        result = detect_file_by_keywords([other], ["referral"])
        assert result is None

    def test_empty_file_list(self):
        result = detect_file_by_keywords([], ["referral"])
        assert result is None

    def test_prefers_newest(self, tmp_path):
        import time

        old = tmp_path / "old-referral.xlsx"
        old.touch()
        time.sleep(0.05)
        new = tmp_path / "new-referral.xlsx"
        new.touch()
        result = detect_file_by_keywords([old, new], ["referral"])
        assert result == new

    def test_case_insensitive(self, tmp_path):
        f = tmp_path / "1453-REFERRAL-Report.xlsx"
        f.touch()
        result = detect_file_by_keywords([f], ["referral"])
        assert result == f


class TestExtractAccountColumnByName:
    def test_extracts_by_letter(self, tmp_path):
        df = pd.DataFrame({"A": [1, 2], "B": ["ABC", "DEF"], "C": [3, 4]})
        path = tmp_path / "test.xlsx"
        df.to_excel(path, index=False)
        result = extract_account_column_by_name(path, "B", 1)
        assert len(result) == 2
        assert "ABC" in result.values

    def test_extracts_by_column_name(self, tmp_path):
        df = pd.DataFrame({"Account Number": ["X1", "X2"], "Name": ["A", "B"]})
        path = tmp_path / "test.xlsx"
        df.to_excel(path, index=False)
        result = extract_account_column_by_name(path, "Account Number", 1)
        assert len(result) == 2

    def test_empty_on_bad_column(self, tmp_path):
        df = pd.DataFrame({"A": [1]})
        path = tmp_path / "test.xlsx"
        df.to_excel(path, index=False)
        result = extract_account_column_by_name(path, "Z", 1)
        assert len(result) == 0

    def test_csv_file(self, tmp_path):
        df = pd.DataFrame({"Acct": ["A1", "A2"], "Val": [1, 2]})
        path = tmp_path / "test.csv"
        df.to_csv(path, index=False)
        result = extract_account_column_by_name(path, "A", 1)
        assert len(result) == 2

    def test_unsupported_format(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text("{}")
        result = extract_account_column_by_name(path, "A", 1)
        assert len(result) == 0


class TestExtractAccountColumnByInference:
    def test_detects_account_column(self, tmp_path):
        df = pd.DataFrame(
            {
                "Name": ["Alice", "Bob"],
                "Account Number": ["ABC123456", "DEF789012"],
                "Balance": [100, 200],
            }
        )
        path = tmp_path / "test.xlsx"
        df.to_excel(path, index=False)
        result = extract_account_column_by_inference(path)
        assert len(result) == 2
        assert "ABC123456" in result.values

    def test_falls_back_to_long_values(self, tmp_path):
        df = pd.DataFrame(
            {
                "Col1": ["Short", "Hi"],
                "Col2": ["ABCDEF123456", "GHIJKL789012"],
            }
        )
        path = tmp_path / "test.xlsx"
        df.to_excel(path, index=False)
        result = extract_account_column_by_inference(path, hash_min_length=6)
        assert len(result) == 2

    def test_empty_file(self, tmp_path):
        df = pd.DataFrame()
        path = tmp_path / "empty.xlsx"
        df.to_excel(path, index=False)
        result = extract_account_column_by_inference(path)
        assert len(result) == 0


class TestExtractAccounts:
    def test_with_config(self, tmp_path):
        df = pd.DataFrame({"A": [1, 2], "B": ["ACC100", "ACC200"]})
        path = tmp_path / "test.xlsx"
        df.to_excel(path, index=False)
        result = extract_accounts(path, column="B", header_row=1)
        assert len(result) == 2

    def test_falls_back_to_inference(self, tmp_path):
        df = pd.DataFrame({"Account ID": ["HASH123456", "HASH789012"]})
        path = tmp_path / "test.xlsx"
        df.to_excel(path, index=False)
        result = extract_accounts(path)
        assert len(result) == 2

    def test_config_empty_falls_back(self, tmp_path):
        df = pd.DataFrame({"Account ID": ["HASH123456", "HASH789012"]})
        path = tmp_path / "test.xlsx"
        df.to_excel(path, index=False)
        # Column "Z" won't exist, so it falls back to inference
        result = extract_accounts(path, column="Z", header_row=1)
        assert len(result) == 2


class TestLetterToIndex:
    def test_a(self):
        assert _letter_to_index("A") == 0

    def test_g(self):
        assert _letter_to_index("G") == 6

    def test_lowercase(self):
        assert _letter_to_index("a") == 0

    def test_z(self):
        assert _letter_to_index("Z") == 25
