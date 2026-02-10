"""Tests for cli.py -- Typer CLI interface."""

from typer.testing import CliRunner

from ics_append.cli import app

runner = CliRunner()


class TestCLI:
    def test_no_args_shows_help(self):
        result = runner.invoke(app)
        # no_args_is_help=True returns exit code 0, but Typer may return 2
        assert result.exit_code in (0, 2)
        assert "organize" in result.output.lower() or "Usage" in result.output

    def test_help_flag(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "organize" in result.output.lower()
        assert "merge" in result.output.lower()
        assert "match" in result.output.lower()
        assert "run-all" in result.output.lower()

    def test_organize_command(self, base_dir):
        (base_dir / "1453-ref.xlsx").touch()
        result = runner.invoke(
            app,
            [
                "--base-dir",
                str(base_dir),
                "organize",
            ],
        )
        assert result.exit_code == 0
        assert "Organized" in result.output

    def test_merge_command(self, base_dir, client_dir, ref_excel):
        result = runner.invoke(
            app,
            [
                "--base-dir",
                str(base_dir),
                "merge",
            ],
        )
        assert result.exit_code == 0

    def test_run_all_command(self, base_dir, client_dir, ref_excel):
        result = runner.invoke(
            app,
            [
                "--base-dir",
                str(base_dir),
                "run-all",
            ],
        )
        assert result.exit_code == 0
        assert "Pipeline complete" in result.output

    def test_dry_run_flag(self, base_dir):
        (base_dir / "1453-ref.xlsx").touch()
        result = runner.invoke(
            app,
            [
                "--base-dir",
                str(base_dir),
                "--dry-run",
                "organize",
            ],
        )
        assert result.exit_code == 0

    def test_verbose_flag(self, base_dir, client_dir, ref_excel):
        result = runner.invoke(
            app,
            [
                "--base-dir",
                str(base_dir),
                "--verbose",
                "merge",
            ],
        )
        assert result.exit_code == 0
