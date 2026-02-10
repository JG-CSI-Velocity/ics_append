"""Match ICS accounts against ODD files and annotate with ICS columns."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from ics_append.normalizer import normalize_hash, normalize_series

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MatchMetadata:
    """Statistics from the account matching pass."""

    client_id: str
    run_date: str
    total_odd_rows: int
    matched_count: int
    unmatched_count: int
    ref_match_count: int
    dm_match_count: int
    both_match_count: int
    match_rate: float
    ref_file: str
    dm_file: str
    odd_file: str
    ics_not_in_dump: int

    @property
    def summary(self) -> str:
        return (
            f"Matched {self.matched_count}/{self.total_odd_rows} "
            f"({self.match_rate:.1%}): {self.ref_match_count} REF, "
            f"{self.dm_match_count} DM, {self.both_match_count} Both"
        )

    def to_dict(self) -> dict:
        return {
            "client_id": self.client_id,
            "run_date": self.run_date,
            "total_odd_rows": self.total_odd_rows,
            "matched_count": self.matched_count,
            "unmatched_count": self.unmatched_count,
            "ref_match_count": self.ref_match_count,
            "dm_match_count": self.dm_match_count,
            "both_match_count": self.both_match_count,
            "match_rate": round(self.match_rate, 4),
            "ics_not_in_dump": self.ics_not_in_dump,
            "ref_file": self.ref_file,
            "dm_file": self.dm_file,
            "odd_file": self.odd_file,
        }


def match_and_annotate(
    odd_df: pd.DataFrame,
    merged_df: pd.DataFrame,
    acct_column: str = "Acct Number",
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Match ICS accounts against ODD and append columns.

    Uses pd.merge for vectorized matching.

    Returns:
        Annotated ODD DataFrame with:
        - "ICS Account": "Yes" / "No" (NOT account hashes)
        - "ICS Source": "REF" / "DM" / "Both" / ""
        And a stats dict with match counts.
    """
    # Normalize both sides for matching
    odd_work = odd_df.copy()
    odd_work["_norm_acct"] = normalize_series(odd_work[acct_column])

    ics_lookup = merged_df[["Acct Hash", "Source"]].copy()
    ics_lookup = ics_lookup.rename(columns={"Source": "_ics_source"})
    ics_lookup["_norm_acct"] = ics_lookup["Acct Hash"].apply(normalize_hash)
    ics_lookup = ics_lookup.drop_duplicates(subset=["_norm_acct"], keep="first")

    # Left merge: all ODD rows preserved, matched rows get _ics_source
    merged = odd_work.merge(
        ics_lookup[["_norm_acct", "_ics_source"]],
        on="_norm_acct",
        how="left",
    )

    # Create ICS Account and ICS Source columns
    merged["ICS Account"] = merged["_ics_source"].notna().map({True: "Yes", False: "No"})
    merged["ICS Source"] = merged["_ics_source"].fillna("")

    # Count stats
    matched = (merged["ICS Account"] == "Yes").sum()
    ref_count = (merged["ICS Source"] == "REF").sum()
    dm_count = (merged["ICS Source"] == "DM").sum()
    both_count = (merged["ICS Source"] == "Both").sum()

    # Clean up temp columns
    result = merged.drop(columns=["_norm_acct", "_ics_source"])

    stats = {
        "matched": int(matched),
        "unmatched": int(len(result) - matched),
        "ref_match_count": int(ref_count),
        "dm_match_count": int(dm_count),
        "both_match_count": int(both_count),
    }

    return result, stats


def read_odd_file(file_path: Path) -> tuple[pd.DataFrame, str]:
    """Read an ODD file, preserving Acct Number as string.

    Returns (DataFrame, acct_column_name).
    Raises ValueError if Acct Number column not found.
    """
    suffix = file_path.suffix.lower()

    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(file_path, header=0, dtype={"Acct Number": str})
    elif suffix == ".csv":
        df = pd.read_csv(file_path, header=0, dtype={"Acct Number": str})
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    if "Acct Number" not in df.columns:
        raise ValueError(
            f"'Acct Number' column not found in {file_path.name}. "
            f"Available columns: {list(df.columns)}"
        )

    return df, "Acct Number"


def build_match_metadata(
    client_id: str,
    stats: dict[str, int],
    total_odd_rows: int,
    merged_count: int,
    ref_file: str,
    dm_file: str,
    odd_file: str,
) -> MatchMetadata:
    """Build MatchMetadata from raw stats."""
    matched = stats["matched"]
    rate = matched / total_odd_rows if total_odd_rows > 0 else 0.0
    ics_not_in_dump = max(0, merged_count - matched)

    return MatchMetadata(
        client_id=client_id,
        run_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_odd_rows=total_odd_rows,
        matched_count=matched,
        unmatched_count=stats["unmatched"],
        ref_match_count=stats["ref_match_count"],
        dm_match_count=stats["dm_match_count"],
        both_match_count=stats["both_match_count"],
        match_rate=rate,
        ref_file=ref_file,
        dm_file=dm_file,
        odd_file=odd_file,
        ics_not_in_dump=ics_not_in_dump,
    )


def write_metadata_json(metadata: MatchMetadata, output_path: Path) -> None:
    """Write match metadata as JSON sidecar file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata.to_dict(), f, indent=2)
    logger.info("Wrote metadata to %s", output_path)
