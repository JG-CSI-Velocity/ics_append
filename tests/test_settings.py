"""Tests for settings.py -- Pydantic BaseSettings configuration."""

import pytest

from ics_append.exceptions import ConfigError
from ics_append.settings import MATCH_MONTH_PATTERN, ClientConfig, Settings


class TestClientConfig:
    def test_defaults(self):
        config = ClientConfig()
        assert config.ref_column is None
        assert config.ref_header_row is None
        assert config.dm_column is None
        assert config.dm_header_row is None

    def test_valid_config(self):
        config = ClientConfig(ref_column="G", ref_header_row=1, dm_column="I", dm_header_row=10)
        assert config.ref_column == "G"
        assert config.ref_header_row == 1

    def test_column_requires_header_row(self):
        with pytest.raises(ValueError, match="ref_header_row required"):
            ClientConfig(ref_column="G")

    def test_dm_column_requires_header_row(self):
        with pytest.raises(ValueError, match="dm_header_row required"):
            ClientConfig(dm_column="I")

    def test_blank_column_rejected(self):
        with pytest.raises(ValueError, match="must not be blank"):
            ClientConfig(ref_column="  ", ref_header_row=1)

    def test_strips_whitespace(self):
        config = ClientConfig(ref_column="  G  ", ref_header_row=1)
        assert config.ref_column == "G"

    def test_frozen(self):
        config = ClientConfig()
        with pytest.raises(Exception):
            config.ref_column = "G"

    def test_extra_forbid(self):
        with pytest.raises(Exception):
            ClientConfig(unknown_field="x")

    def test_header_row_bounds(self):
        with pytest.raises(ValueError):
            ClientConfig(ref_column="G", ref_header_row=-1)
        with pytest.raises(ValueError):
            ClientConfig(ref_column="G", ref_header_row=101)


class TestSettings:
    def test_minimal(self, base_dir):
        s = Settings(base_dir=base_dir)
        assert s.base_dir == base_dir
        assert s.dry_run is False
        assert s.overwrite is True
        assert s.csv_copy is False
        assert s.match_month is None
        assert s.clients == {}
        assert len(s.default_ref_keywords) > 0
        assert len(s.default_dm_keywords) > 0
        assert s.hash_min_length == 6
        assert s.match_rate_warn_threshold == 0.5

    def test_path_expansion(self, tmp_path):
        s = Settings(base_dir=str(tmp_path))
        assert s.base_dir == tmp_path.resolve()

    def test_match_month_valid(self, base_dir):
        s = Settings(base_dir=base_dir, match_month="2026.01")
        assert s.match_month == "2026.01"

    def test_match_month_invalid(self, base_dir):
        with pytest.raises(ValueError, match="YYYY.MM"):
            Settings(base_dir=base_dir, match_month="2026-01")

    def test_match_month_invalid_month(self, base_dir):
        with pytest.raises(ValueError, match="YYYY.MM"):
            Settings(base_dir=base_dir, match_month="2026.13")

    def test_frozen(self, base_dir):
        s = Settings(base_dir=base_dir)
        with pytest.raises(Exception):
            s.dry_run = True

    def test_extra_forbid(self, base_dir):
        with pytest.raises(Exception):
            Settings(base_dir=base_dir, unknown_field="x")

    def test_get_client_exists(self, base_dir):
        client = ClientConfig(ref_column="G", ref_header_row=1)
        s = Settings(base_dir=base_dir, clients={"1453": client})
        assert s.get_client("1453").ref_column == "G"

    def test_get_client_missing(self, base_dir):
        s = Settings(base_dir=base_dir)
        config = s.get_client("9999")
        assert config.ref_column is None

    def test_get_client_strips_whitespace(self, base_dir):
        client = ClientConfig(ref_column="G", ref_header_row=1)
        s = Settings(base_dir=base_dir, clients={"1453": client})
        assert s.get_client("  1453  ").ref_column == "G"

    def test_normalize_client_keys(self, base_dir):
        client = ClientConfig()
        s = Settings(base_dir=base_dir, clients={"  1453  ": client})
        assert "1453" in s.clients
        assert "  1453  " not in s.clients

    def test_duplicate_client_keys_after_strip(self, base_dir):
        # Duplicate keys happen after whitespace normalization, not from Python dict literals
        with pytest.raises(ValueError, match="Duplicate client key"):
            Settings(
                base_dir=base_dir,
                clients={"1453": ClientConfig(), "1453 ": ClientConfig()},
            )

    def test_empty_client_key(self, base_dir):
        with pytest.raises(ValueError, match="must not be empty"):
            Settings(base_dir=base_dir, clients={"  ": ClientConfig()})

    def test_from_args(self, base_dir):
        s = Settings.from_args(base_dir=base_dir, dry_run=True)
        assert s.dry_run is True

    def test_from_args_config_error(self, tmp_path):
        with pytest.raises(ConfigError):
            Settings.from_args(base_dir=tmp_path, match_month="bad-format")

    def test_with_clients(self, base_dir):
        s = Settings(
            base_dir=base_dir,
            clients={
                "1453": ClientConfig(ref_column="G", ref_header_row=1),
                "1217": ClientConfig(dm_column="I", dm_header_row=10),
            },
        )
        assert len(s.clients) == 2
        assert s.get_client("1453").ref_column == "G"
        assert s.get_client("1217").dm_column == "I"


class TestMatchMonthPattern:
    def test_valid_months(self):
        for m in ["2026.01", "2025.12", "2024.06", "2023.09"]:
            assert MATCH_MONTH_PATTERN.match(m) is not None

    def test_invalid_months(self):
        for m in ["2026-01", "2026.00", "2026.13", "26.01", "2026.1", "abcd.01"]:
            assert MATCH_MONTH_PATTERN.match(m) is None
