"""Pipeline orchestration: organize -> merge -> match."""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from ics_append.matcher import (
    MatchMetadata,
    build_match_metadata,
    match_and_annotate,
    read_odd_file,
    write_metadata_json,
)
from ics_append.merger import MergeResult, merge_client_files
from ics_append.organizer import list_client_dirs, organize_directory
from ics_append.settings import Settings
from ics_append.trends import build_summary_row, update_summary
from ics_append.validation import validate_annotated_output, validate_odd_file

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of running the full pipeline."""

    settings: Settings
    organized: dict[str, list[str]] = field(default_factory=dict)
    merge_results: list[MergeResult] = field(default_factory=list)
    match_metadata: list[MatchMetadata] = field(default_factory=list)
    output_files: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run_organize(settings: Settings) -> dict[str, list[str]]:
    """Step 1: Organize loose files into client folders."""
    logger.info("Step 1: Organizing files in %s", settings.base_dir)
    return organize_directory(settings.base_dir, dry_run=settings.dry_run)


def run_merge(
    settings: Settings,
    client_ids: list[str] | None = None,
    on_progress: Callable[[str, str], None] | None = None,
) -> list[MergeResult]:
    """Step 2: Merge REF+DM files for each client."""
    logger.info("Step 2: Merging files")

    if client_ids is None:
        client_ids = list_client_dirs(settings.base_dir)

    results: list[MergeResult] = []
    for cid in client_ids:
        client_dir = settings.base_dir / cid
        if not client_dir.is_dir():
            logger.warning("Client dir not found: %s", client_dir)
            continue

        if on_progress:
            on_progress(cid, f"Merging {cid}")

        result = merge_client_files(client_dir, cid, settings)
        results.append(result)

        # Write merged file if data exists
        if result.total > 0 and not settings.dry_run:
            month = settings.match_month or datetime.now().strftime("%Y.%m")
            output_name = f"{cid}-ICS Accounts-All-{month}.xlsx"
            output_path = client_dir / output_name

            if output_path.exists() and not settings.overwrite:
                base = output_path.stem
                ext = output_path.suffix
                i = 1
                while (client_dir / f"{base}_v{i}{ext}").exists():
                    i += 1
                output_path = client_dir / f"{base}_v{i}{ext}"

            _atomic_write_excel(result.merged_df, output_path)

            if settings.csv_copy:
                csv_path = output_path.with_suffix(".csv")
                result.merged_df.to_csv(csv_path, index=False, encoding="utf-8")

            logger.info("%s: Wrote merged file with %d rows", cid, result.total)

    return results


def run_match(
    settings: Settings,
    merge_results: list[MergeResult] | None = None,
    on_progress: Callable[[str, str], None] | None = None,
) -> list[MatchMetadata]:
    """Step 3: Match ICS accounts against ODD files."""
    if settings.ars_dir is None:
        logger.info("Step 3: Skipped (no ars_dir configured)")
        return []

    logger.info("Step 3: Matching against ODD files in %s", settings.ars_dir)

    month = settings.match_month or datetime.now().strftime("%Y.%m")
    month_dir = settings.ars_dir / month

    if not month_dir.is_dir():
        logger.warning("ARS month directory not found: %s", month_dir)
        return []

    metadata_list: list[MatchMetadata] = []
    merge_lookup = {r.client_id: r for r in (merge_results or [])}

    for client_dir in sorted(month_dir.iterdir()):
        if not client_dir.is_dir():
            continue
        cid = client_dir.name
        if not (cid.isdigit() and len(cid) == 4):
            continue

        if on_progress:
            on_progress(cid, f"Matching {cid}")

        # Find ODD file
        odd_files = [
            f
            for f in client_dir.iterdir()
            if f.is_file()
            and "odd" in f.name.lower()
            and f.suffix.lower() in (".xlsx", ".xls", ".csv")
        ]
        if not odd_files:
            logger.info("%s %s: No ODD file found", month, cid)
            continue

        odd_path = odd_files[0]

        # Find merged ICS file
        merged_path = _find_merged_file(settings.base_dir / cid, cid, month)
        if merged_path is None:
            logger.info("%s %s: No merged ICS file found", month, cid)
            continue

        if settings.dry_run:
            logger.info("DRY-RUN: Would match %s against %s", odd_path.name, merged_path.name)
            continue

        try:
            # Validate ODD
            odd_df, acct_col = read_odd_file(odd_path)
            odd_report = validate_odd_file(odd_df, acct_col)
            if not odd_report.is_valid:
                logger.error("%s %s: ODD validation failed: %s", month, cid, odd_report.summary)
                continue

            # Read merged ICS
            merged_df = pd.read_excel(merged_path, dtype=str)

            # Match and annotate
            annotated_df, stats = match_and_annotate(odd_df, merged_df, acct_col)

            # Validate output
            out_report = validate_annotated_output(annotated_df)
            if not out_report.is_valid:
                logger.error("%s %s: Output validation failed: %s", month, cid, out_report.summary)

            # Build metadata
            merge_result = merge_lookup.get(cid)
            meta = build_match_metadata(
                client_id=cid,
                stats=stats,
                total_odd_rows=len(odd_df),
                merged_count=len(merged_df),
                ref_file=merge_result.ref_file if merge_result else "",
                dm_file=merge_result.dm_file if merge_result else "",
                odd_file=odd_path.name,
            )

            # Warn on low match rate
            if meta.match_rate < settings.match_rate_warn_threshold:
                logger.warning(
                    "%s %s: Low match rate %.1f%% (threshold: %.0f%%)",
                    month,
                    cid,
                    meta.match_rate * 100,
                    settings.match_rate_warn_threshold * 100,
                )

            logger.info("%s %s: %s", month, cid, meta.summary)

            # Write outputs
            out_name = odd_path.stem + "_annotated.xlsx"
            out_path = client_dir / out_name
            _atomic_write_excel(annotated_df, out_path)

            json_path = client_dir / f"{cid}_match_metadata.json"
            write_metadata_json(meta, json_path)

            metadata_list.append(meta)

        except Exception as e:
            logger.error("%s %s: Match failed: %s", month, cid, e)

    return metadata_list


def run_pipeline(
    settings: Settings,
    on_progress: Callable[[str, str], None] | None = None,
) -> PipelineResult:
    """Execute full pipeline: organize -> merge -> match."""
    result = PipelineResult(settings=settings)

    try:
        result.organized = run_organize(settings)
    except Exception as e:
        result.errors.append(f"Organize failed: {e}")
        logger.error("Organize step failed: %s", e)

    try:
        result.merge_results = run_merge(settings, on_progress=on_progress)
    except Exception as e:
        result.errors.append(f"Merge failed: {e}")
        logger.error("Merge step failed: %s", e)

    # Update trends summary
    if result.merge_results and not settings.dry_run:
        month = settings.match_month or datetime.now().strftime("%Y.%m")
        summary_rows = [build_summary_row(r, month) for r in result.merge_results]
        trends_dir = settings.base_dir / "trends"
        summary_path = trends_dir / "merge_summary.csv"
        update_summary(summary_rows, summary_path)

    try:
        result.match_metadata = run_match(settings, result.merge_results, on_progress=on_progress)
    except Exception as e:
        result.errors.append(f"Match failed: {e}")
        logger.error("Match step failed: %s", e)

    return result


def _find_merged_file(client_dir: Path, client_id: str, month: str) -> Path | None:
    """Find the merged ICS file for a client and month."""
    if not client_dir.is_dir():
        return None

    month_variants = {month, month.replace(".", "-"), month.replace("-", ".")}
    pattern = f"{client_id}-ics accounts-all"

    candidates = []
    for f in client_dir.iterdir():
        if not f.is_file():
            continue
        if pattern in f.name.lower():
            if any(mv in f.name for mv in month_variants):
                candidates.append(f)

    # Fallback: any ICS Accounts-All file for this client
    if not candidates:
        for f in client_dir.iterdir():
            if f.is_file() and pattern in f.name.lower():
                candidates.append(f)

    if not candidates:
        return None

    return max(candidates, key=lambda p: p.stat().st_mtime)


def _atomic_write_excel(df: pd.DataFrame, output_path: Path) -> None:
    """Write DataFrame to Excel using atomic write pattern."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".xlsx", dir=str(output_path.parent))
    try:
        os.close(fd)
        df.to_excel(tmp_path, index=False)
        os.replace(tmp_path, str(output_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
