"""Typer CLI for ics_append."""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from ics_append.settings import Settings

app = typer.Typer(
    name="ics-append",
    help="ICS data pipeline: organize, merge, match, run-all.",
    no_args_is_help=True,
)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)-8s %(message)s",
    )


def _build_settings(
    config: Path | None = None,
    base_dir: Path | None = None,
    ars_dir: Path | None = None,
    dry_run: bool | None = None,
    match_month: str | None = None,
    overwrite: bool | None = None,
    csv_copy: bool | None = None,
) -> Settings:
    """Build Settings from CLI options, falling back to YAML + env."""
    overrides: dict = {}
    if config is not None:
        overrides["yaml_file"] = str(config)
    if base_dir is not None:
        overrides["base_dir"] = base_dir
    if ars_dir is not None:
        overrides["ars_dir"] = ars_dir
    if dry_run is not None:
        overrides["dry_run"] = dry_run
    if match_month is not None:
        overrides["match_month"] = match_month
    if overwrite is not None:
        overrides["overwrite"] = overwrite
    if csv_copy is not None:
        overrides["csv_copy"] = csv_copy
    return Settings(**overrides)


@app.callback()
def main(
    ctx: typer.Context,
    config: Path | None = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    base_dir: Path | None = typer.Option(None, "--base-dir", "-d", help="Base ICS directory"),
    ars_dir: Path | None = typer.Option(None, "--ars-dir", help="ARS directory with ODD files"),
    dry_run: bool | None = typer.Option(None, "--dry-run", "-n", help="Preview without changes"),
    match_month: str | None = typer.Option(None, "--match-month", "-m", help="Month (YYYY.MM)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging"),
) -> None:
    """ICS Pipeline -- config.yaml < env vars < CLI flags."""
    _configure_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["base_dir"] = base_dir
    ctx.obj["ars_dir"] = ars_dir
    ctx.obj["dry_run"] = dry_run
    ctx.obj["match_month"] = match_month


@app.command()
def organize(ctx: typer.Context) -> None:
    """Organize loose files into client folders."""
    from ics_append.pipeline import run_organize

    settings = _build_settings(
        config=ctx.obj.get("config"),
        base_dir=ctx.obj.get("base_dir"),
        dry_run=ctx.obj.get("dry_run"),
    )
    moved = run_organize(settings)
    total = sum(len(v) for v in moved.values())
    typer.echo(f"Organized {total} files into {len(moved)} folders")


@app.command()
def merge(
    ctx: typer.Context,
    client: str | None = typer.Option(None, "--client", help="Single client ID"),
) -> None:
    """Merge REF+DM files per client."""
    from ics_append.pipeline import run_merge

    settings = _build_settings(
        config=ctx.obj.get("config"),
        base_dir=ctx.obj.get("base_dir"),
        dry_run=ctx.obj.get("dry_run"),
        match_month=ctx.obj.get("match_month"),
    )
    client_ids = [client] if client else None
    results = run_merge(settings, client_ids=client_ids)
    for r in results:
        typer.echo(f"{r.client_id}: REF={r.ref_count} DM={r.dm_count} Total={r.total}")


@app.command()
def match(
    ctx: typer.Context,
    client: str | None = typer.Option(None, "--client", help="Single client ID"),
) -> None:
    """Match ICS accounts against ODD files."""
    from ics_append.pipeline import run_match

    settings = _build_settings(
        config=ctx.obj.get("config"),
        base_dir=ctx.obj.get("base_dir"),
        ars_dir=ctx.obj.get("ars_dir"),
        dry_run=ctx.obj.get("dry_run"),
        match_month=ctx.obj.get("match_month"),
    )
    metadata = run_match(settings)
    for m in metadata:
        typer.echo(m.summary)


@app.command(name="run-all")
def run_all(ctx: typer.Context) -> None:
    """Execute full pipeline: organize -> merge -> match."""
    from ics_append.pipeline import run_pipeline

    settings = _build_settings(
        config=ctx.obj.get("config"),
        base_dir=ctx.obj.get("base_dir"),
        ars_dir=ctx.obj.get("ars_dir"),
        dry_run=ctx.obj.get("dry_run"),
        match_month=ctx.obj.get("match_month"),
    )
    result = run_pipeline(settings)
    typer.echo(
        f"Pipeline complete: {len(result.merge_results)} merges, "
        f"{len(result.match_metadata)} matches"
    )
    if result.errors:
        for err in result.errors:
            typer.echo(f"ERROR: {err}", err=True)
