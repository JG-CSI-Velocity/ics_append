"""ICS Append -- organize, merge, and match ICS account data."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ics_append.pipeline import PipelineResult

__version__ = "1.0.0"


def run_client(
    base_dir: str | Path,
    ars_dir: str | Path | None = None,
    match_month: str | None = None,
    dry_run: bool = False,
    on_progress: Callable[[str, str], None] | None = None,
) -> PipelineResult:
    """Convenience function for Jupyter/REPL usage.

    Example:
        from ics_append import run_client
        result = run_client("/path/to/ics", ars_dir="/path/to/ars")
    """
    from ics_append.pipeline import run_pipeline
    from ics_append.settings import Settings

    settings = Settings(
        base_dir=Path(base_dir),
        ars_dir=Path(ars_dir) if ars_dir else None,
        match_month=match_month,
        dry_run=dry_run,
    )
    return run_pipeline(settings, on_progress=on_progress)
