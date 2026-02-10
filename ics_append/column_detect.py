"""File and column detection for REF/DM data files."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

ACCOUNT_KEYWORDS = ("acct", "account", "hash", "id", "number")


def detect_file_by_keywords(
    files: list[Path],
    keywords: list[str],
) -> Path | None:
    """Detect a file from a directory listing by matching keywords in the filename.

    Returns the most recently modified match, or None if no match.
    """
    matches: list[Path] = []
    for f in files:
        name_lower = f.stem.lower()
        if any(kw in name_lower for kw in keywords):
            matches.append(f)

    if not matches:
        return None

    return max(matches, key=lambda p: p.stat().st_mtime)


def extract_account_column_by_name(
    file_path: Path,
    column: str,
    header_row: int,
) -> pd.Series:
    """Extract account numbers from a known column letter and header row.

    Args:
        file_path: Path to Excel/CSV file.
        column: Column letter (e.g., "G") or column name.
        header_row: 1-based row number where the header lives.

    Returns:
        Series of account values (strings), or empty Series on failure.
    """
    try:
        col_index = _letter_to_index(column) if len(column) == 1 and column.isalpha() else None
        suffix = file_path.suffix.lower()

        if suffix in (".xlsx", ".xls"):
            df = pd.read_excel(file_path, header=header_row - 1, dtype=str)
        elif suffix == ".csv":
            df = pd.read_csv(
                file_path,
                header=header_row - 1,
                dtype=str,
                engine="python",
                on_bad_lines="skip",
            )
        else:
            return pd.Series(dtype=str)

        if df.empty:
            return pd.Series(dtype=str)

        if col_index is not None:
            if col_index >= df.shape[1]:
                return pd.Series(dtype=str)
            return df.iloc[:, col_index].dropna().astype(str)

        # Try matching by column name
        for col_name in df.columns:
            if str(col_name).strip().lower() == column.lower():
                return df[col_name].dropna().astype(str)

        return pd.Series(dtype=str)

    except Exception as e:
        logger.warning("Failed to extract column from %s: %s", file_path, e)
        return pd.Series(dtype=str)


def extract_account_column_by_inference(
    file_path: Path,
    hash_min_length: int = 6,
    max_header_rows: int = 10,
) -> pd.Series:
    """Infer and extract the account number column when no config is available.

    Probes up to max_header_rows header positions, preferring columns with
    names suggesting account fields, then falling back to columns whose
    values look like hashes/IDs.
    """
    suffix = file_path.suffix.lower()

    for header_row in range(max_header_rows):
        try:
            if suffix in (".xlsx", ".xls"):
                df = pd.read_excel(file_path, header=header_row, dtype=str)
            elif suffix == ".csv":
                df = pd.read_csv(
                    file_path,
                    header=header_row,
                    dtype=str,
                    engine="python",
                    on_bad_lines="skip",
                )
            else:
                return pd.Series(dtype=str)
        except Exception:
            continue

        if df.empty:
            continue

        # Prefer columns with account-related names
        for col in df.columns:
            cname = str(col).strip().lower()
            if any(kw in cname for kw in ACCOUNT_KEYWORDS):
                series = df[col].dropna().astype(str)
                if not series.empty:
                    return series

        # Fallback: first column with values that look like hashes/IDs
        for col in df.columns:
            series = df[col].dropna().astype(str)
            if series.empty:
                continue
            sample = series.head(10).tolist()
            if any(len(s) >= hash_min_length for s in sample):
                return series

    return pd.Series(dtype=str)


def extract_accounts(
    file_path: Path,
    column: str | None = None,
    header_row: int | None = None,
    hash_min_length: int = 6,
) -> pd.Series:
    """Extract account hashes from a file, using config or inference.

    If column and header_row are provided, uses exact extraction.
    Otherwise falls back to heuristic inference.
    """
    if column is not None and header_row is not None:
        result = extract_account_column_by_name(file_path, column, header_row)
        if not result.empty:
            return result
        logger.info("Config-based extraction empty for %s, trying inference", file_path.name)

    return extract_account_column_by_inference(file_path, hash_min_length)


def _letter_to_index(letter: str) -> int:
    """Convert a column letter (A-Z) to a 0-based index."""
    return ord(letter.upper()) - ord("A")
