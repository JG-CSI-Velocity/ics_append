"""Month-over-month trend tracking for merge summaries."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from ics_append.merger import MergeResult

logger = logging.getLogger(__name__)

SUMMARY_COLUMNS = [
    "Month",
    "Client ID",
    "REF Rows",
    "DM Rows",
    "Total Merged",
    "REF Status",
    "DM Status",
]


def build_summary_row(
    result: MergeResult,
    month: str | None = None,
) -> dict:
    """Build a summary row dict from a MergeResult."""
    if month is None:
        month = datetime.now().strftime("%Y.%m")
    return {
        "Month": month,
        "Client ID": result.client_id,
        "REF Rows": result.ref_count,
        "DM Rows": result.dm_count,
        "Total Merged": result.total,
        "REF Status": result.ref_status,
        "DM Status": result.dm_status,
    }


def update_summary(
    new_rows: list[dict],
    summary_path: Path,
    dry_run: bool = False,
) -> pd.DataFrame:
    """Append new summary rows and compute growth metrics.

    Deduplicates by (Month, Client ID) before appending.
    """
    new_df = pd.DataFrame(new_rows, columns=SUMMARY_COLUMNS)

    if summary_path.exists():
        old_df = pd.read_csv(summary_path, dtype={"Month": str, "Client ID": str})
        # Keep only base columns from old data (drop computed columns)
        base_cols = [c for c in SUMMARY_COLUMNS if c in old_df.columns]
        old_df = old_df[base_cols]
        # Deduplicate: remove old rows for same (Month, Client ID) combos
        keys = set(zip(new_df["Month"], new_df["Client ID"]))
        mask = ~old_df.apply(lambda r: (str(r["Month"]), str(r["Client ID"])) in keys, axis=1)
        old_df = old_df[mask]
        combined = pd.concat([old_df, new_df], ignore_index=True)
    else:
        combined = new_df

    combined = combined.sort_values(["Client ID", "Month"]).reset_index(drop=True)

    # Compute MoM metrics per client
    for col in ["REF Rows", "DM Rows", "Total Merged"]:
        combined[col] = pd.to_numeric(combined[col], errors="coerce").fillna(0).astype(int)

    combined["Total_pct_change"] = combined.groupby("Client ID")["Total Merged"].pct_change()
    combined["Total_delta"] = combined.groupby("Client ID")["Total Merged"].diff()

    def trend_arrow(val: float) -> str:
        if pd.isna(val):
            return ""
        if val > 0:
            return "up"
        if val < 0:
            return "down"
        return "flat"

    combined["Trend"] = combined["Total_delta"].apply(trend_arrow)

    if dry_run:
        logger.info("DRY-RUN: Would update summary at %s", summary_path)
    else:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(summary_path, index=False, encoding="utf-8")
        logger.info("Summary updated at %s", summary_path)

    return combined
