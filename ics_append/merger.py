"""Merge REF and DM account hashes into a combined ICS list."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ics_append.column_detect import detect_file_by_keywords, extract_accounts
from ics_append.normalizer import normalize_hash
from ics_append.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """Result of merging REF and DM files for a single client."""

    client_id: str
    merged_df: pd.DataFrame
    ref_count: int = 0
    dm_count: int = 0
    ref_file: str = ""
    dm_file: str = ""
    ref_status: str = "Missing"
    dm_status: str = "Missing"

    @property
    def total(self) -> int:
        return len(self.merged_df)


def merge_sources(
    ref_series: pd.Series | None,
    dm_series: pd.Series | None,
) -> pd.DataFrame:
    """Merge REF and DM account hashes into a combined DataFrame.

    Returns DataFrame with columns: ["Acct Hash", "Source"].
    Deduplicates by normalized hash, tagging accounts in both as "Both".
    """
    rows: list[dict[str, str]] = []

    if ref_series is not None:
        for val in ref_series:
            rows.append({"Acct Hash": str(val), "Source": "REF"})

    if dm_series is not None:
        for val in dm_series:
            rows.append({"Acct Hash": str(val), "Source": "DM"})

    if not rows:
        return pd.DataFrame(columns=["Acct Hash", "Source"])

    df = pd.DataFrame(rows)
    df["Acct Hash"] = df["Acct Hash"].astype(str)

    # Deduplicate: if same normalized hash appears in both REF and DM, tag as "Both"
    df["_norm"] = df["Acct Hash"].apply(normalize_hash)
    source_by_hash = df.groupby("_norm")["Source"].apply(set).to_dict()

    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for _, row in df.iterrows():
        norm = row["_norm"]
        if norm in seen or not norm:
            continue
        seen.add(norm)
        sources = source_by_hash[norm]
        source = "Both" if len(sources) > 1 else sources.pop()
        deduped.append({"Acct Hash": row["Acct Hash"], "Source": source})

    return pd.DataFrame(deduped, columns=["Acct Hash", "Source"])


def merge_client_files(
    client_dir: Path,
    client_id: str,
    settings: Settings,
) -> MergeResult:
    """Detect, read, and merge REF+DM files from a client directory."""
    client_config = settings.get_client(client_id)
    files = [f for f in client_dir.iterdir() if f.is_file()]

    # Detect REF file
    ref_file = detect_file_by_keywords(files, settings.default_ref_keywords)
    ref_series = None
    ref_status = "Missing"
    ref_count = 0

    if ref_file is not None:
        ref_status = "Present"
        ref_series = extract_accounts(
            ref_file,
            column=client_config.ref_column,
            header_row=client_config.ref_header_row,
            hash_min_length=settings.hash_min_length,
        )
        ref_count = len(ref_series)
        if ref_count == 0:
            logger.warning("%s: REF file %s produced no accounts", client_id, ref_file.name)
    else:
        logger.info("%s: No REF file found", client_id)

    # Detect DM file
    dm_file = detect_file_by_keywords(files, settings.default_dm_keywords)
    dm_series = None
    dm_status = "Missing"
    dm_count = 0

    if dm_file is not None:
        dm_status = "Present"
        dm_series = extract_accounts(
            dm_file,
            column=client_config.dm_column,
            header_row=client_config.dm_header_row,
            hash_min_length=settings.hash_min_length,
        )
        dm_count = len(dm_series)
        if dm_count == 0:
            logger.warning("%s: DM file %s produced no accounts", client_id, dm_file.name)
    else:
        logger.info("%s: No DM file found", client_id)

    merged_df = merge_sources(ref_series, dm_series)

    logger.info(
        "%s: REF=%d, DM=%d, Total merged=%d",
        client_id,
        ref_count,
        dm_count,
        len(merged_df),
    )

    return MergeResult(
        client_id=client_id,
        merged_df=merged_df,
        ref_count=ref_count,
        dm_count=dm_count,
        ref_file=ref_file.name if ref_file else "",
        dm_file=dm_file.name if dm_file else "",
        ref_status=ref_status,
        dm_status=dm_status,
    )
